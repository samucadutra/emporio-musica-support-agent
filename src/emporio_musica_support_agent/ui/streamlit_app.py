"""Minimal web chat over the same graph, checkpointer and tools as the CLI (T33).

Run: `uv sync --extra ui`, then
`uv run streamlit run src/emporio_musica_support_agent/ui/streamlit_app.py`.
"""

from dataclasses import dataclass
from zoneinfo import ZoneInfo

import streamlit as st
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.state import CompiledStateGraph

from emporio_musica_support_agent.agent.graph import build_graph, run_turn
from emporio_musica_support_agent.app import Deps, build_deps
from emporio_musica_support_agent.cli import INSTABILITY_MESSAGE, make_embeddings
from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.data.validation import validate
from emporio_musica_support_agent.llm import check_api_key, is_retryable
from emporio_musica_support_agent.logging_setup import configure
from emporio_musica_support_agent.rag.extract import extract_policy
from emporio_musica_support_agent.sessions import (
    new_session_id,
    open_checkpointer,
    session_messages,
)
from emporio_musica_support_agent.tools.orders import reference_date
from emporio_musica_support_agent.ui.turns import split_turns


@dataclass(frozen=True)
class Runtime:
    deps: Deps
    graph: CompiledStateGraph
    checkpointer: SqliteSaver


@st.cache_resource(show_spinner="Carregando dados e índice de políticas…")
def load_runtime() -> Runtime:
    """Same start-up order as the CLI; raises on any problem (shown with st.error)."""
    settings = Settings()
    settings.export_provider_env()
    configure(settings, verbose=False)
    check_api_key(settings)
    deps = build_deps(settings, embeddings=make_embeddings(settings))
    validate(deps.repo, extract_policy(deps.policy_index.pdf_path).text)
    if deps.policy_index.status().state != "ok":
        deps.policy_index.build()
    checkpointer = open_checkpointer(settings.sqlite_path)
    return Runtime(deps, build_graph(deps, checkpointer), checkpointer)


def start_session(runtime: Runtime, session_id: str | None) -> str:
    """The session from `?session=`, or a new one. Stops the page on an unknown ID."""
    if session_id is None:
        tz = ZoneInfo(runtime.deps.settings.store_timezone)
        return new_session_id(runtime.deps.clock.now(tz))
    if session_messages(runtime.checkpointer, session_id) is None:
        st.error(f"Sessão desconhecida: {session_id}")
        st.stop()
    return session_id


def main() -> None:
    st.set_page_config(page_title="Empório da Música · Lia", page_icon="🎸")
    st.title("Empório da Música · Lia")
    try:
        runtime = load_runtime()
    except Exception as error:
        st.error(f"Não foi possível iniciar: {error}")
        st.stop()
    settings = runtime.deps.settings

    if "session_id" not in st.session_state:
        st.session_state.session_id = start_session(runtime, st.query_params.get("session"))
    session_id: str = st.session_state.session_id
    st.query_params["session"] = session_id

    with st.sidebar:
        st.markdown(f"**Sessão**\n\n`{session_id}`")
        st.caption(f"Modelo: {settings.llm_model}")
        simulated = " (simulada)" if settings.store_today else ""
        st.caption(f"Data de referência: {reference_date(settings, runtime.deps.clock)}{simulated}")
        show_tools = st.toggle("Mostrar ferramentas", value=False)
        if st.button("Nova sessão"):
            del st.session_state["session_id"]
            del st.query_params["session"]
            st.rerun()

    for turn in split_turns(session_messages(runtime.checkpointer, session_id) or []):
        with st.chat_message("user"):
            st.markdown(turn.question)
        with st.chat_message("assistant"):
            if show_tools and turn.trace:
                with st.expander("Ferramentas"):
                    st.code("\n".join(turn.trace), language=None)
            if turn.answer is not None:
                st.markdown(turn.answer)

    if text := st.chat_input("Escreva sua mensagem"):
        with st.chat_message("user"):
            st.markdown(text)
        try:
            with st.spinner("Lia está digitando…"):
                run_turn(runtime.graph, settings, session_id, text)
        except Exception as error:
            if is_retryable(error):
                st.error(INSTABILITY_MESSAGE)
            else:
                st.error(f"Erro do modelo: {error}. Verifique a chave e o LLM_MODEL.")
            return
        st.rerun()


if __name__ == "__main__":
    main()
