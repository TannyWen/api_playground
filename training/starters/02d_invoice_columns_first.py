"""PART 2 -- DATA STRUCTURE, sub-page 2 of 2: invoice data, define columns
first, then flatten -- built against the XML response.

See 02_data_structure.py for the full explanation of JSON, this API's data
structure, flattened vs. unflattened data, and GET vs. POST.

Same first step as 02b -- xmltodict turns the XML into a normal Python
dict, made of the same dict/list/str types JSON always gave you. From
there, this file takes a different, more explicit path than 02b:

  1. decide the column names we want
  2. walk the data by hand, and for each row, define each column's value
  3. gather those values into one row, and save that row to a dataset
  4. only once every row is collected, flatten the dataset into a table

Run it:   python training/starters/02d_invoice_columns_first.py
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
# Step 3 -- decide the column names we want, before touching any data
# ==============================================================================
wanted_columns = [
    "invoice_number",
    "vendor_number",
    "accounting_date",
    "purchasing_line_description",
    "account_number",
    "line_amount",
    "line_item",
    "quantity"
]
print("wanted_columns:", wanted_columns)
print()


# ==============================================================================
# Step 4 -- walk the data by hand, and define each column's value
# ==============================================================================
# `invoices` is a list of dicts. Each invoice dict has a "line_items" key,
# which is itself a dict holding an "item" key -- a list of line items.
# Same one level deeper for postings. So reaching one posting means three
# plain `for` loops, one inside the next: invoice, then its line items,
# then that line item's postings.
dataset = []

for invoice in invoices:
    invoice_number = invoice["invoice_number"]
    vendor_number = invoice["vendor_number"]
    accounting_date = invoice["accounting_date"]

    line_items = invoice["line_items"]["item"]

    for line_item in line_items:
        purchasing_line_description = line_item["purchasing_line_description"]
        quantity = line_item["quantity"]

        # Usually the variable name can just match the dict key, like
        # purchasing_line_description does above -- but not here. The loop
        # variable above is ALSO called `line_item`, and it holds the whole
        # dict (so we can still read postings out of it below). If we wrote
        # `line_item = line_item["line_item"]`, we'd overwrite that dict
        # with just the number inside it -- and then `line_item["postings"]`
        # on the next line would break, because a number can't be indexed
        # like a dict. So: match the key's name UNLESS that name is already
        # taken by something you still need -- here, by the loop variable
        # itself.
        line_item_number = line_item["line_item"]

        postings = line_item["postings"]["item"]

        for posting in postings:
            account_number = posting["account_number"]
            line_amount = posting["line_amount"]

            # Gather this row's defined values into one dict, using the
            # exact names from wanted_columns, then save that row to the
            # dataset.
            row = {
                "invoice_number": invoice_number,
                "vendor_number": vendor_number,
                "accounting_date": accounting_date,
                "purchasing_line_description": purchasing_line_description,
                "account_number": account_number,
                "line_amount": line_amount,
                "line_item": line_item_number,
                "quantity": quantity,
            }
            dataset.append(row)

print("dataset is a", type(dataset), "of", type(dataset[0]), "-- one per posting")
print("rows collected:", len(dataset))
print()


# ==============================================================================
# Step 5 -- flatten the dataset into a table
# ==============================================================================
# Every row in `dataset` is already a flat dict, with every value already
# defined in Step 4 -- so turning it into a table is one line.
invoice_columns_first = pd.DataFrame(dataset)[wanted_columns]

print(invoice_columns_first.to_string(index=False))
