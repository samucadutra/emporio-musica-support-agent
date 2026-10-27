"""Throwaway, read-only inspection of data/ (CSVs and policy PDF).

Run: uv run python scripts/inspect_data.py
Nothing under data/ is modified.
"""

import csv
import io
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd
from pypdf import PdfReader

DATA = Path(__file__).resolve().parent.parent / "data"
PREFIX = "desafio_tecnico_ai_eng - "
TODAY = date(2026, 10, 27)
TABLES = ["categories", "customers", "products", "promotions", "orders", "order_items"]
PKS = {
    "categories": "category_id",
    "customers": "customer_id",
    "products": "product_id",
    "promotions": "promotion_id",
    "orders": "order_id",
}
CATEGORICAL = {
    "customers": ["city"],
    "products": ["category_id", "status"],
    "promotions": ["description", "is_active", "discount_percent"],
    "orders": ["status", "payment_method"],
}

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)
pd.set_option("display.max_colwidth", 60)


def h(title: str) -> None:
    print(f"\n{'=' * 80}\n{title}\n{'=' * 80}")


def raw_format(path: Path) -> None:
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw.decode("utf-8")
        enc = "utf-8"
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
        enc = "latin-1"
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n")
    dialect = csv.Sniffer().sniff(text[:2000], delimiters=",;\t")
    print(
        f"bytes={len(raw)} encoding={enc} bom={bom} delimiter={dialect.delimiter!r} "
        f"crlf={crlf} lf={lf} trailing_newline={raw.endswith(b'\n')} "
        f"non_ascii={any(b > 127 for b in raw)} has_R$={'R$' in text}"
    )
    # Decimal format: any numeric-looking field with a comma decimal?
    comma_dec = re.findall(r"(?<![\w.])\d{1,3}(?:\.\d{3})*,\d{2}(?![\w])", text)
    print(f"comma-decimal-looking tokens: {comma_dec[:5]}")


def load(name: str) -> pd.DataFrame:
    path = DATA / f"{PREFIX}{name}.csv"
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")


def profile(name: str, df: pd.DataFrame) -> None:
    print(f"rows={len(df)} cols={list(df.columns)}")
    inferred = pd.read_csv(io.StringIO(df.to_csv(index=False))).dtypes
    print("inferred dtypes:", dict(inferred.astype(str)))
    print("sample rows:\n", df.head(3).to_string(index=False))
    for col in df.columns:
        s = df[col]
        empty = int((s == "").sum())
        ws = int((s != s.str.strip()).sum())
        dbl = int(s.str.contains(r"\s{2,}").sum())
        if empty or ws or dbl:
            print(
                f"  {col}: empty={empty} leading/trailing_ws={ws} double_spaces={dbl}"
            )
    print("full-row duplicates:", int(df.duplicated().sum()))
    if name in PKS:
        pk = PKS[name]
        print(f"PK {pk} duplicates:", int(df[pk].duplicated().sum()))
        ids = df[pk].astype(int)
        print(f"PK range {ids.min()}..{ids.max()} sorted={ids.is_monotonic_increasing}")
    else:
        print(
            "order_items (order_id, product_id) duplicates:",
            int(df.duplicated(["order_id", "product_id"]).sum()),
        )
    for col in CATEGORICAL.get(name, []):
        print(f"  distinct {col}: {df[col].value_counts().to_dict()}")


def main() -> None:
    h("FILES")
    for p in sorted(DATA.iterdir()):
        print(f"{p.name!r} size={p.stat().st_size}")

    dfs: dict[str, pd.DataFrame] = {}
    for t in TABLES:
        h(f"TABLE {t}")
        raw_format(DATA / f"{PREFIX}{t}.csv")
        dfs[t] = load(t)
        profile(t, dfs[t])

    cat, cus, prod, promo, orders, items = (dfs[t] for t in TABLES)
    for df, cols in [
        (prod, ["product_id", "category_id", "stock_quantity"]),
        (cus, ["customer_id"]),
        (cat, ["category_id"]),
        (promo, ["promotion_id", "product_id", "discount_percent", "is_active"]),
        (orders, ["order_id", "customer_id"]),
        (items, ["order_id", "product_id", "quantity"]),
    ]:
        for c in cols:
            df[c] = df[c].astype(int)
    prod["price_brl"] = prod["price_brl"].astype(float)
    orders["total_brl"] = orders["total_brl"].astype(float)

    h("PRODUCTS: values")
    print("price<=0:", prod[prod.price_brl <= 0].product_id.tolist())
    print("stock<0:", prod[prod.stock_quantity < 0].product_id.tolist())
    print(
        "stock==0:",
        prod[prod.stock_quantity == 0][["product_id", "name", "status"]].to_dict(
            "records"
        ),
    )
    print(
        "non-active:",
        prod[prod.status != "active"][
            ["product_id", "name", "status", "stock_quantity"]
        ].to_dict("records"),
    )
    print("price range:", prod.price_brl.min(), prod.price_brl.max())
    print("created_at range:", prod.created_at.min(), prod.created_at.max())
    bad_dates = [
        d for d in prod.created_at if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d)
    ]
    print("non-ISO created_at:", bad_dates)
    print(
        "products per category:", prod.category_id.value_counts().sort_index().to_dict()
    )
    print(
        "categories without products:",
        sorted(set(cat.category_id) - set(prod.category_id)),
    )
    print(
        "duplicate names:",
        prod[prod.name.str.lower().duplicated(keep=False)].name.tolist(),
    )
    keysets: dict[int, set[tuple[str, ...]]] = {}
    for _, r in prod.iterrows():
        try:
            spec = json.loads(r.specs)
        except json.JSONDecodeError as e:
            print(f"  invalid specs JSON product {r.product_id}: {e}")
            continue
        keysets.setdefault(r.category_id, set()).add(tuple(sorted(spec)))
    for c, ks in sorted(keysets.items()):
        print(f"  category {c} specs keysets: {ks}")
    spaced = prod[prod.specs.str.contains('": "')].product_id.tolist()
    print("specs with '\": \"' spacing:", spaced)
    print("\nnames vs descriptions (brand check):")
    brands = [
        "Fender",
        "Gibson",
        "Ibanez",
        "PRS",
        "Music Man",
        "Yamaha",
        "Pearl",
        "Tama",
        "Korg",
        "Nord",
        "Roland",
    ]
    for _, r in prod[prod.category_id.isin([1, 2, 3, 4])].iterrows():
        nb = [b for b in brands if b in r["name"]]
        db = [b for b in brands if b in r.description]
        flag = "" if set(nb) & set(db) else "  <-- MISMATCH"
        print(
            f"  {r.product_id} name={r['name']!r} name_brand={nb} desc_brand={db}{flag}"
        )
    for _, r in prod[prod.category_id == 4].iterrows():
        print(f"  {r.product_id} specs={r.specs} desc={r.description[:70]!r}")

    h("CUSTOMERS")
    print(
        "email duplicates:",
        cus[cus.email.str.lower().duplicated(keep=False)][
            ["customer_id", "name", "email"]
        ].to_dict("records"),
    )
    print(
        "phone duplicates:",
        cus[cus.phone.duplicated(keep=False)][["customer_id", "phone"]].to_dict(
            "records"
        ),
    )
    print(
        "bad phone format:",
        cus[~cus.phone.str.fullmatch(r"\(\d{2}\) 9\d{4}-\d{4}")].phone.tolist(),
    )
    print(
        "bad email format:",
        cus[~cus.email.str.fullmatch(r"[\w.]+@[\w.]+\.\w+")].email.tolist(),
    )
    print("email domains:", cus.email.str.split("@").str[1].value_counts().to_dict())
    print("name word counts:", cus.name.str.split().str.len().value_counts().to_dict())
    print("first-name duplicates (same first+last):")
    fl = cus.name.str.split().apply(lambda w: f"{w[0]} {w[-1]}")
    print(
        "  ", cus[fl.duplicated(keep=False)][["customer_id", "name"]].to_dict("records")
    )
    print(
        "customers with orders:",
        orders.customer_id.nunique(),
        sorted(orders.customer_id.unique()),
    )

    h("RELATIONSHIPS / ORPHANS")
    print(
        "orders -> customers orphans:",
        sorted(set(orders.customer_id) - set(cus.customer_id)),
    )
    print(
        "items -> orders orphans:", sorted(set(items.order_id) - set(orders.order_id))
    )
    print("orders without items:", sorted(set(orders.order_id) - set(items.order_id)))
    print(
        "items -> products orphans:",
        sorted(set(items.product_id) - set(prod.product_id)),
    )
    print(
        "products -> categories orphans:",
        sorted(set(prod.category_id) - set(cat.category_id)),
    )
    print(
        "promotions -> products orphans:",
        sorted(set(promo.product_id) - set(prod.product_id)),
    )
    print(
        "products with >1 promotion:",
        promo.product_id.value_counts()[lambda s: s > 1].to_dict(),
    )
    print(
        "products with >1 ACTIVE promotion:",
        promo[promo.is_active == 1]
        .product_id.value_counts()[lambda s: s > 1]
        .to_dict(),
    )

    h("PROMOTIONS")
    pm = promo.merge(
        prod[["product_id", "name", "price_brl", "status", "stock_quantity"]],
        on="product_id",
    )
    pm["promo_price"] = (pm.price_brl * (1 - pm.discount_percent / 100)).round(2)
    print(pm.to_string(index=False))
    print("discount range:", promo.discount_percent.min(), promo.discount_percent.max())

    h("ORDERS")
    for c in ["order_date", "estimated_delivery"]:
        vals = orders[c][orders[c] != ""]
        print(
            f"{c} non-ISO: {[d for d in vals if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', d)]} range={vals.min()}..{vals.max()}"
        )
    print("orders per status:", orders.status.value_counts().to_dict())
    print(
        "status vs tracking present:",
        orders.groupby("status")
        .apply(lambda g: (g.tracking_code != "").sum(), include_groups=False)
        .to_dict(),
    )
    print(
        "status vs notes present:",
        orders.groupby("status")
        .apply(lambda g: (g.notes != "").sum(), include_groups=False)
        .to_dict(),
    )
    tc = orders.tracking_code[orders.tracking_code != ""]
    print(
        "tracking codes not matching BR+9alnum+BR:",
        [t for t in tc if not re.fullmatch(r"BR[A-Z0-9]{9}BR", t)],
    )
    print(
        "delivery before order date:",
        orders[
            (orders.estimated_delivery != "")
            & (orders.estimated_delivery < orders.order_date)
        ].order_id.tolist(),
    )

    li = items.merge(
        prod[["product_id", "name", "price_brl", "status", "category_id"]],
        on="product_id",
    )
    li["line"] = li.price_brl * li.quantity
    sums = li.groupby("order_id").line.sum()
    o = orders.set_index("order_id").join(sums.rename("items_sum"))
    o["diff"] = (o.total_brl - o.items_sum).round(2)
    print("\norder totals vs items:")
    print(o[["status", "payment_method", "total_brl", "items_sum", "diff"]].to_string())
    print("\nline items:")
    print(
        li.sort_values("order_id")[
            ["order_id", "product_id", "name", "quantity", "price_brl", "status"]
        ].to_string(index=False)
    )

    print(
        "\ninstallment check (policy 3.1: <=3x min R$50 ; 4-6x min R$80 ; 7-12x min R$100):"
    )
    for oid, r in o.iterrows():
        m = re.fullmatch(r"credit_(\d+)x", r.payment_method)
        if not m:
            continue
        n = int(m.group(1))
        per = r.total_brl / n
        minimum = 50 if n <= 3 else 80 if n <= 6 else 100
        flag = "  <-- BELOW MIN" if per < minimum else ""
        print(f"  order {oid}: {r.total_brl} / {n}x = {per:.2f} (min {minimum}){flag}")
    pix = o[o.payment_method == "pix"]
    print(
        "\npix orders total/items ratio (5% discount would be 0.95):",
        (pix.total_brl / pix.items_sum).round(4).to_dict(),
    )

    print(f"\nreturn windows relative to TODAY={TODAY}:")
    for oid, r in o.iterrows():
        od = date.fromisoformat(r.order_date)
        ed = date.fromisoformat(r.estimated_delivery) if r.estimated_delivery else None
        since_order = (TODAY - od).days
        since_deliv = (TODAY - ed).days if ed else None
        print(
            f"  order {oid} {r.status:9} order_date={od} est_delivery={ed} days_since_order={since_order} "
            f"days_since_delivery={since_deliv} regret7={since_deliv is not None and since_deliv <= 7} "
            f"defect30={since_order <= 30} warranty90={since_deliv is not None and since_deliv <= 90} "
            f"est_delivery-order_date={(ed - od).days if ed else None}"
        )

    h("CHALLENGE EXAMPLES")
    print(
        prod[prod.name.str.contains("takamine", case=False)][
            ["product_id", "name", "price_brl", "stock_quantity", "status"]
        ].to_string(index=False)
    )
    print(
        promo[
            promo.product_id.isin(prod[prod.name.str.contains("GD20")].product_id)
        ].to_string(index=False)
    )
    v = prod[(prod.category_id == 5) & (prod.price_brl <= 1000)].sort_values(
        "price_brl"
    )
    print("\nviolões <= R$1000 (all):")
    print(
        v[["product_id", "name", "price_brl", "stock_quantity", "status"]].to_string(
            index=False
        )
    )
    sellable = v[(v.status == "active") & (v.stock_quantity > 0)]
    print("sellable ids:", sellable.product_id.tolist(), "count:", len(sellable))
    act = promo[promo.is_active == 1].product_id
    print("violões <= 1000 with active promo:", sorted(set(v.product_id) & set(act)))
    print("violões with active promo and promo price <= 1000:")
    print(
        pm[(pm.is_active == 1)]
        .query("promo_price <= 1000")[
            ["product_id", "name", "price_brl", "promo_price"]
        ]
        .to_string(index=False)
    )

    h("POLICY PDF")
    reader = PdfReader(DATA / "políticas_da_loja.pdf")
    print("pages:", len(reader.pages), "metadata:", reader.metadata)
    full = ""
    for i, page in enumerate(reader.pages, 1):
        plain = page.extract_text() or ""
        t = page.extract_text(extraction_mode="layout") or ""
        full += t + "\n"
        print(
            f"page {i}: layout_chars={len(t)} replacement_chars={t.count(chr(0xFFFD))} "
            f"plain_mode_lines={plain.count(chr(10))} plain_mode_words={len(plain.split())}"
        )
    compact = re.sub(r"[ \t]+", " ", full)
    print(
        "layout chars:",
        len(full),
        "compact chars:",
        len(compact),
        "approx tokens (compact/4):",
        len(compact) // 4,
    )
    print("words:", len(full.split()))
    print("\nheadings:")
    for line in full.splitlines():
        if re.match(r"^\d+(\.\d+)?\.?\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]", line) and len(line) < 80:
            print("  ", line.strip())
    print("\nemails:", sorted(set(re.findall(r"[\w.\-ó]+@[\w.\-ó]+", full))))
    print("phones:", sorted(set(re.findall(r"\(\d{2}\) \d{4,5}-\d{4}", full))))
    print("money:", sorted(set(re.findall(r"R\$ ?[\d.,]+", full))))
    print("day windows:", sorted(set(re.findall(r"\d+ \(\w+\) dias[^.]*", full))))
    print("\n--- full text ---\n", full)


if __name__ == "__main__":
    main()
