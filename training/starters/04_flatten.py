"""STARTER -- Flatten challenges (CASE_STUDIES.md, Tickets 8-9).

Reads the pre-saved sample responses, so this works even if your connection
is misbehaving. No network needed.

Vendor master data is still JSON. Invoice search is now XML (see Part 2 --
Data Structure) -- xmltodict.parse() turns that XML into a normal Python
dict, the same dict/list/str types JSON always gave you, so the flattening
code below is otherwise identical either way.

Run it:   python training/starters/04_flatten.py
"""
import json
import pathlib
from decimal import Decimal

import pandas as pd
import xmltodict

HERE = pathlib.Path(__file__).resolve().parent
SAMPLES = HERE.parent / "data" / "samples"
OUT = HERE.parent / "data" / "my_output"
OUT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Setup -- the saved responses, loaded for you.
# ---------------------------------------------------------------------------
master = json.loads((SAMPLES / "master_data_page1.json").read_text(encoding="utf-8"))

invoices_xml = (SAMPLES / "invoices_page1.xml").read_text(encoding="utf-8")
invoices_response = xmltodict.parse(invoices_xml, force_list=("item",))

# Ticket 9 -- both responses are the FULL API response, exactly as saved. The
# rows you want are nested one level in, alongside `page`/`meta` siblings --
# NOT at the top level. For the XML one, there's one more level than JSON
# gave you: xmltodict wraps every repeated element in {"item": [...]}, since
# XML has no native array syntax -- so the invoices are at
# ["invoice_search_response"]["data"]["item"], not just ["data"].
vendors = master["items"]
invoices = invoices_response["invoice_search_response"]["data"]["item"]

print(f"{len(vendors)} vendors, {len(invoices)} invoices loaded\n")
print("one invoice, top-level keys:", list(invoices[0]))
print("a line item's keys         :", list(invoices[0]["line_items"]["item"][0]))
print("a posting's keys           :", list(invoices[0]["line_items"]["item"][0]["postings"]["item"][0]))
print()


# ---------------------------------------------------------------------------
# Step 1 -- one row per vendor (the shallowest grain)
# ---------------------------------------------------------------------------
# TODO 1: Use pd.json_normalize(vendors) and look at the columns. Every
#         vendor field here is already flat (no nested objects to worry
#         about) -- write it to OUT / "vendors.csv" with one row per vendor.

# vendors_df = pd.json_normalize(vendors)
# print(vendors_df.columns.tolist())
# vendors_df.to_csv(OUT / "vendors.csv", index=False)


# ---------------------------------------------------------------------------
# Step 2 -- one row per line item
# ---------------------------------------------------------------------------
# TODO 2: Flatten to one row per LINE ITEM, keeping the invoice context
#         (invoice_number, vendor_number, accounting_date).
#
#         pd.json_normalize takes:
#           record_path=["line_items", "item"]             the array to explode
#                                                            (note the extra
#                                                            "item" level --
#                                                            that's XML's
#                                                            repeated-element
#                                                            wrapper, not a
#                                                            typo)
#           meta=["invoice_number", "vendor_number", ...]   parent fields to carry down
#
#         Check: your row count should equal the total number of line items.
#         Work that number out from `invoices` and assert it.

# lines_df = pd.json_normalize(
#     invoices,
#     record_path=["line_items", "item"],
#     meta=["invoice_number", "vendor_number", "accounting_date"],
# )
# expected = sum(len(inv["line_items"]["item"]) for inv in invoices)
# assert len(lines_df) == expected, (len(lines_df), expected)
# print(f"lines_df: {len(lines_df)} rows (expected {expected})")


# ---------------------------------------------------------------------------
# Step 3 -- one row per posting, then reconcile (Ticket 3's lesson, again)
# ---------------------------------------------------------------------------
# TODO 3: Now go one level deeper: one row per POSTING, still carrying the
#         line context (line_item, purchasing_line_description, quantity).
#
#         Careful: record_path=["line_items", "item", "postings", "item"]
#         reaches the postings but drops the line-level fields in between.
#         Try it and see. Then try this instead, starting from lines_df:
#
#           lines_df = lines_df.rename(columns={"postings.item": "postings"})
#           exploded = lines_df.explode("postings", ignore_index=True)
#           posting_cols = pd.json_normalize(exploded["postings"])
#           postings_df = pd.concat(
#               [exploded.drop(columns=["postings"]), posting_cols], axis=1
#           )
#
#         (lines_df's own "postings" column came out of Step 2 named
#         "postings.item" -- same XML wrapper as above -- so it's renamed
#         back to "postings" first, to keep this step readable.)
#
# TODO 4: THE IMPORTANT ONE. For each invoice, its postings should sum to
#         exactly zero (this is the API's double-entry invariant -- see
#         Ticket 3). Check it.
#
#         Before you do -- look at this:
#
#             print(postings_df["line_amount"].dtype)
#             print(postings_df["line_amount"].sum())
#
#         Money arrives as a *string* (XML has no native number type, same
#         lesson as JSON's Decimal-as-string), so pandas gives you `object`
#         dtype and .sum() glues the strings together instead of adding them
#         (exactly Ticket 3's bug, now inside a dataframe). Convert first:
#
#             postings_df["line_amount"] = postings_df["line_amount"].map(Decimal)
#
#         Then group by invoice_number, sum line_amount, and assert every
#         invoice's total is exactly Decimal("0.00") -- not nearly zero.
#
#             totals = postings_df.groupby("invoice_number")["line_amount"].sum()
#             assert (totals == Decimal("0.00")).all(), totals[totals != Decimal("0.00")]
#             postings_df.to_csv(OUT / "postings.csv", index=False)
