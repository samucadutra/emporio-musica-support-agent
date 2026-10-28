"""Policy tool: search_policies (design §6.5)."""

from typing import Protocol

from emporio_musica_support_agent.rag.index import PolicyChunk
from emporio_musica_support_agent.tools.schemas import PolicySearchResult, SearchPoliciesInput


class PolicySearcher(Protocol):
    """Anything that searches the policy; `rag.index.PolicyIndex` in the app."""

    def search(self, query: str, k: int) -> list[PolicyChunk]: ...


def search_policies(index: PolicySearcher, params: SearchPoliciesInput) -> PolicySearchResult:
    """Search the store's policy manual (version 2.1). Use for rules and conditions: exchanges,
    returns, withdrawal ("arrependimento"), defects, warranty, payment methods, installment
    rules, shipping and delivery times, tracking, promotion rules, privacy/LGPD. Write the query
    in Portuguese. Describe the situation in general policy terms rather than specifics, e.g.
    'frete para outra cidade' instead of a city name. Answer ONLY from the returned text and cite
    the section, e.g. "(seção 4.1)". If the chunks don't answer the question, say the policy
    doesn't cover it and offer to pass the case to the team. Never complete the answer from
    general knowledge or consumer law. For the address, phone or opening hours, prefer
    `get_store_info`.
    """
    chunks = index.search(params.question, params.k)
    return PolicySearchResult(chunks=sorted(chunks, key=lambda c: c.score, reverse=True))
