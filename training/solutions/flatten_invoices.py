"""SOLUTION -- Flattening challenges F1-F3.

Turns the nested API payload into three flat tables, one per grain:

    F1  suppliers.csv                 one row per supplier
    F2  invoice_lines.csv             one row per line item
    F3  invoice_line_allocations.csv  one row per allocation

and reconciles F3 back to the line totals, which must come out at exactly zero.

    python training/solutions/flatten_invoices.py

Reads the JSON saved by drain_invoices.py if it is present, and fetches it
otherwise, so this works offline once the data has been pulled once.
"""
import json
import os
import pathlib
from decimal import Decimal

import pandas as pd
import requests

BASE_URL = os.environ.get("WORKSHOP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
USERNAME = os.environ.get("WORKSHOP_USERNAME", "student")
PASSWORD = os.environ.get("WORKSHOP_PASSWORD", "student-pass-123")

DATA = pathlib.Path(__file__).resolve().parents[1] / "data"
OUT = DATA / "flattened"


def token() -> str:
    r = requests.post(
        f"{BASE_URL}/v1/auth/token",
        data={"username": USERNAME, "password": PASSWORD},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def load_or_fetch(filename: str, fetch):
    """Prefer a saved response; fall back to the API."""
    path = DATA / filename
    if path.exists():
        print(f"  reading {path.name}")
        return json.loads(path.read_text(encoding="utf-8"))
    print(f"  {path.name} not found -- fetching from the API")
    payload = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def fetch_suppliers() -> list[dict]:
    """Drain the offset-paginated master data endpoint."""
    headers = {"Authorization": f"Bearer {token()}"}
    items, offset = [], 0
    while True:
        r = requests.get(
            f"{BASE_URL}/v1/master-data/suppliers",
            params={"limit": 50, "offset": offset},
            headers=headers,
            timeout=60,
        )
        r.raise_for_status()
        page = r.json()
        items += page["items"]
        nxt = page["page"]["next_offset"]
        if nxt is None:
            return items
        offset = nxt


def fetch_invoices() -> list[dict]:
    headers = {"Authorization": f"Bearer {token()}"}
    out, cursor = [], None
    while True:
        r = requests.post(
            f"{BASE_URL}/v1/invoices/search",
            json={"page_size": 25, "cursor": cursor},
            headers=headers,
            timeout=60,
        )
        r.raise_for_status()
        payload = r.json()
        out += payload["data"]
        cursor = payload["page"]["next_cursor"]
        if cursor is None:
            return out


def money(series: pd.Series) -> pd.Series:
    """Convert JSON money strings to Decimal.

    This is the trap at the heart of the exercise. Pydantic serialises Decimal
    to a JSON *string*, so pandas infers `object` dtype -- and `.sum()` on a
    column of strings silently concatenates them into one enormous string
    instead of adding them up.

    Decimal rather than float, so the reconciliation lands on exactly zero
    rather than 1e-10 away from it.
    """
    return series.map(lambda v: Decimal(str(v)))


# ---------------------------------------------------------------------------
# F1 -- one row per supplier
# ---------------------------------------------------------------------------
def flatten_suppliers(suppliers: list[dict]) -> pd.DataFrame:
    """json_normalize flattens nested *objects* into dotted columns.

    `address` and `payment_terms` become address.city, payment_terms.days and
    so on. `contacts` is an array, so it stays a column of lists -- arrays need
    record_path (see F2), not dotted columns.
    """
    df = pd.json_normalize(suppliers)
    df["contact_count"] = df["contacts"].map(len)
    df["primary_contact"] = df["contacts"].map(
        lambda cs: next((c["name"] for c in cs if c["is_primary"]), None)
    )
    return df.drop(columns=["contacts"])


# ---------------------------------------------------------------------------
# F2 -- one row per line item
# ---------------------------------------------------------------------------
LINE_META = [
    "invoice_id",
    "invoice_number",
    "status",
    "currency",
    "issue_date",
    "due_date",
    "total_amount",
    ["supplier", "supplier_code"],
    ["supplier", "name"],
    ["supplier", "country_code"],
]


def flatten_lines(invoices: list[dict]) -> pd.DataFrame:
    """record_path picks the array to explode; meta carries the parent down.

    Nested meta fields are given as lists, e.g. ["supplier", "supplier_code"],
    which pandas joins into a "supplier.supplier_code" column.
    """
    df = pd.json_normalize(
        invoices,
        record_path=["line_items"],
        meta=LINE_META,
        errors="ignore",
    )
    df["line_total"] = money(df["line_total"])
    df["unit_price"] = money(df["unit_price"])
    df["total_amount"] = money(df["total_amount"])
    return df


# ---------------------------------------------------------------------------
# F3 -- one row per allocation, keeping the line context
# ---------------------------------------------------------------------------
def flatten_allocations(lines: pd.DataFrame) -> pd.DataFrame:
    """Two levels deep needs two steps, not one json_normalize.

    `record_path=["line_items", "allocations"]` would reach the allocations,
    but it drops the line-level fields in between -- you would lose description,
    quantity and line_total. So: explode the allocations column, then normalize
    the exploded dicts and glue them back beside their line context.
    """
    exploded = lines.explode("allocations", ignore_index=True)
    exploded = exploded[exploded["allocations"].notna()]

    allocation_cols = pd.json_normalize(exploded["allocations"]).reset_index(drop=True)
    context = exploded.drop(columns=["allocations"]).reset_index(drop=True)

    df = pd.concat([context, allocation_cols], axis=1)
    df["amount"] = money(df["amount"])
    df["percentage"] = money(df["percentage"])
    return df


def reconcile(allocations: pd.DataFrame, lines: pd.DataFrame) -> pd.DataFrame:
    """Every line's allocations must sum to exactly that line's total."""
    per_line = (
        allocations.groupby(["invoice_number", "line_number"], as_index=False)["amount"]
        .sum()
        .rename(columns={"amount": "allocated"})
    )
    expected = lines[["invoice_number", "line_number", "line_total"]]
    merged = per_line.merge(expected, on=["invoice_number", "line_number"], how="outer")
    merged["variance"] = merged["allocated"] - merged["line_total"]
    return merged


def main() -> None:
    print(f"Loading data (base URL {BASE_URL})")
    suppliers = load_or_fetch("master_data_all_pages.json", fetch_suppliers)
    invoices = load_or_fetch("invoices_all_pages.json", fetch_invoices)
    print(f"  {len(suppliers)} suppliers, {len(invoices)} invoices\n")

    OUT.mkdir(parents=True, exist_ok=True)

    # F1
    supplier_df = flatten_suppliers(suppliers)
    supplier_df.to_csv(OUT / "suppliers.csv", index=False)
    print(f"F1  suppliers.csv                {len(supplier_df):>6} rows, "
          f"{len(supplier_df.columns)} cols")
    assert len(supplier_df) == len(suppliers), "F1 must be one row per supplier"

    # F2
    lines_df = flatten_lines(invoices)
    lines_df.drop(columns=["allocations"]).to_csv(OUT / "invoice_lines.csv", index=False)
    expected_lines = sum(len(i["line_items"]) for i in invoices)
    print(f"F2  invoice_lines.csv            {len(lines_df):>6} rows, "
          f"{len(lines_df.columns) - 1} cols")
    assert len(lines_df) == expected_lines, (
        f"F2 must be one row per line item ({expected_lines})"
    )

    # F3
    alloc_df = flatten_allocations(lines_df)
    alloc_df.to_csv(OUT / "invoice_line_allocations.csv", index=False)
    expected_allocs = sum(
        len(li["allocations"]) for i in invoices for li in i["line_items"]
    )
    print(f"F3  invoice_line_allocations.csv {len(alloc_df):>6} rows, "
          f"{len(alloc_df.columns)} cols")
    assert len(alloc_df) == expected_allocs, (
        f"F3 must be one row per allocation ({expected_allocs})"
    )

    # The reconciliation -- the point of the whole exercise.
    check = reconcile(alloc_df, lines_df)
    off = check[check["variance"] != Decimal("0")]
    total_allocated = sum(alloc_df["amount"], Decimal("0"))
    total_lines = sum(lines_df["line_total"], Decimal("0"))

    print(f"\nReconciliation")
    print(f"  sum of line totals   : {total_lines}")
    print(f"  sum of allocations   : {total_allocated}")
    print(f"  difference           : {total_allocated - total_lines}")
    print(f"  lines out of balance : {len(off)} of {len(check)}")

    # Show what the trap looks like if you skip the Decimal conversion.
    naive = pd.json_normalize(invoices, record_path=["line_items"])["line_total"]
    print(f"\n  Without converting money from strings, dtype is '{naive.dtype}' "
          f"and .sum() gives a {len(str(naive.sum()))}-character string, not a number.")

    if len(off) or total_allocated != total_lines:
        print("\nFAIL: reconciliation does not balance.")
        raise SystemExit(1)
    print(f"\nPASS: three files written to {OUT.relative_to(DATA.parents[0])}, "
          f"reconciliation is exactly zero.")


if __name__ == "__main__":
    main()
