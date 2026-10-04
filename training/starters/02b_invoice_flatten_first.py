"""PART 2 -- DATA STRUCTURE, sub-page 1 of 2: invoice data, flatten first,
then define columns -- built against the XML response.

See 02_data_structure.py for the full explanation of JSON, this API's data
structure, flattened vs. unflattened data, and GET vs. POST.

POST /v1/invoices/search now returns XML, not JSON. xmltodict.parse()
turns that XML into a normal Python dict -- the same data type you
already know from JSON. Flattening it uses the exact same
pd.json_normalize you already used in 04_flatten.py.

Install once:  .\\.venv\\Scripts\\python.exe -m pip install -r requirements-training.txt

Run it:   python training/starters/02b_invoice_flatten_first.py
"""
import os

import pandas as pd
import requests
import xmltodict

BASE_URL = os.environ.get(
    "WORKSHOP_BASE_URL",
    "https://processdetraining-d8a8h6dtdhhvh7e2.westeurope-01.azurewebsites.net",
).rstrip("/")
# >>> Replace the two defaults below with YOUR OWN workshop username and
# >>> password before running this file. Everyone sharing the "student"
# >>> account shares one rate-limit budget -- your calls can get throttled
# >>> by whatever someone else is running at the same time.
USERNAME = os.environ.get("WORKSHOP_USERNAME", "student")
PASSWORD = os.environ.get("WORKSHOP_PASSWORD", "student-pass-123")

# --- Step 1: establish the connection --------------------------------------
session = requests.Session()
auth_response = session.post(
    f"{BASE_URL}/v1/auth/token",
    data={"username": USERNAME, "password": PASSWORD},
    timeout=30,
)
auth_response.raise_for_status()
token = auth_response.json()["access_token"]
HEADERS = {"Authorization": f"Bearer {token}"}
print(f"Connected to {BASE_URL} as {USERNAME}\n")

# POST, not GET -- still a read, but the filters are structured enough to
# need a body instead of a URL query string. See 02_data_structure.py.
search_response = session.post(
    f"{BASE_URL}/v1/invoices/search", json={"page_size": 10}, headers=HEADERS, timeout=30
)

# --- Step 2: turn the XML text into a plain Python dict ---------------------
data = xmltodict.parse(search_response.text, force_list=("item",))
invoices = data["invoice_search_response"]["data"]["item"]


# ==============================================================================
# Step 3 -- flatten EVERYTHING first, with clean column names
# ==============================================================================
# `record_path` (below, as `path_to_one_row`) says which nested list to
# explode all the way down to -- that's what decides one row = one what.
# `meta` (below, as `columns_to_carry_down`) says which parent fields to
# copy onto every one of those rows -- we ask for every simple field there
# is, including ones we may not use yet.
path_to_one_row = ["line_items", "item", "postings", "item"]  # one row = one posting
columns_to_carry_down = [
    "invoice_number",
    "vendor_number",
    "accounting_date",
    ["line_items", "item", "line_item"],
    ["line_items", "item", "purchasing_line_description"],
    ["line_items", "item", "quantity"],
]

flat_everything = pd.json_normalize(
    invoices,
    record_path=path_to_one_row,
    meta=columns_to_carry_down,
)

# A nested meta path like ["line_items", "item", "quantity"] gives the new
# column a clunky name: "line_items.item.quantity". We rename everything
# to its plain name ONCE here, right after flattening -- so from this
# point on, flat_everything only ever has simple, plain column names.
flat_everything = flat_everything.rename(columns={
    "line_items.item.line_item": "line_item",
    "line_items.item.purchasing_line_description": "purchasing_line_description",
    "line_items.item.quantity": "quantity",
})
print("flattened everything, all columns (already renamed to plain names):")
print(flat_everything.columns.tolist())
print()


# ==============================================================================
# Step 4 -- now just pick the columns we want
# ==============================================================================
# Because Step 3 already gave every column a plain name, picking columns
# here is nothing more than listing the plain names you want. Want one
# more column later? Just add its plain name to this list -- nothing else
# to change.
invoice_flatten_first = flat_everything[[
    "invoice_number",
    "vendor_number",
    "accounting_date",
    "purchasing_line_description",
    "account_number",
    "line_amount",
    "quantity"
]]

print(invoice_flatten_first.to_string(index=False))
