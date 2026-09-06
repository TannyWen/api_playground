"""STARTER -- Flattening challenges F1, F2, F3.

Reads the pre-saved sample responses, so this works even if your connection is
still misbehaving. No network needed.

Run it:   python training/starters/02_flatten.py
"""
import json
import pathlib
from decimal import Decimal

import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
SAMPLES = HERE.parent / "data" / "samples"
OUT = HERE.parent / "data" / "my_output"
OUT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Setup -- the saved responses, loaded for you.
# ---------------------------------------------------------------------------
master = json.loads((SAMPLES / "master_data_page1.json").read_text(encoding="utf-8"))
invoices_response = json.loads((SAMPLES / "invoices_page1.json").read_text(encoding="utf-8"))

# Both files are the FULL API response, exactly as Postman saved it. The rows
# you want are nested one level in.
suppliers = master["items"]
invoices = invoices_response["data"]

print(f"{len(suppliers)} suppliers, {len(invoices)} invoices loaded\n")
print("one invoice, top-level keys:", list(invoices[0]))
print("a line item's keys         :", list(invoices[0]["line_items"][0]))
print("an allocation's keys       :", list(invoices[0]["line_items"][0]["allocations"][0]))
print()


# ---------------------------------------------------------------------------
# F1 -- one row per supplier
# ---------------------------------------------------------------------------
# TODO 1: Use pd.json_normalize(suppliers) and look at the columns.
#         What happened to the nested `address` object?
#         What happened to the `contacts` array? Why are they different?
#         Then write it to OUT / "suppliers.csv" with one row per supplier.

# suppliers_df = ...
# print(suppliers_df.columns.tolist())


# ---------------------------------------------------------------------------
# F2 -- one row per line item
# ---------------------------------------------------------------------------
# TODO 2: Flatten to one row per LINE ITEM, keeping the invoice context
#         (invoice_number, status, currency, and the supplier code).
#
#         pd.json_normalize takes:
#           record_path=["line_items"]     the array to explode
#           meta=["invoice_number", ...]   parent fields to carry down
#
#         For a nested parent field, pass a list:
#           ["supplier", "supplier_code"]  ->  column "supplier.supplier_code"
#
#         Check: your row count should equal the total number of line items.
#         Work that out from `invoices` and assert it.

# lines_df = ...


# ---------------------------------------------------------------------------
# F3 -- one row per allocation, then reconcile
# ---------------------------------------------------------------------------
# TODO 3: Now go one level deeper: one row per ALLOCATION, still carrying the
#         line context (description, quantity, line_total).
#
#         Careful: record_path=["line_items", "allocations"] reaches the
#         allocations but throws away the line-level fields in between. Try it
#         and see. Then try this instead, starting from lines_df:
#
#           exploded = lines_df.explode("allocations", ignore_index=True)
#           allocation_cols = pd.json_normalize(exploded["allocations"])
#           ... then glue them back together side by side with pd.concat
#
# TODO 4: THE IMPORTANT ONE. For each line, the allocation amounts should sum
#         to exactly that line's line_total. Check it.
#
#         Before you do -- look at this:
#
#             print(lines_df["line_total"].dtype)
#             print(lines_df["line_total"].sum())
#
#         Money arrives from JSON as a *string*, so pandas gives you `object`
#         dtype and .sum() glues the strings together instead of adding them.
#         Convert first:
#
#             .map(lambda v: Decimal(str(v)))     exact, no float error
#             pd.to_numeric(...)                  easier, tiny rounding error
#
#         Then group by invoice_number + line_number, sum the amounts, and
#         compare. The variance should be exactly zero on every line.
