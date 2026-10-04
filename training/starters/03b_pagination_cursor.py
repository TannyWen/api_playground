"""PART 3 -- PAGINATION, sub-page 2 of 2: cursor pagination on invoice
search -- this script has a real bug in it.

See 03_pagination.py for the full explanation of why pagination exists, the
two styles this API uses, and how to know when you're actually done.

POST /v1/invoices/search returns XML, not JSON (see Part 2 -- Data
Structure). xmltodict.parse() turns that XML into a normal Python dict, the
same as 02b/02d already did.

THE TICKET
  A colleague reports: "our invoice export never seems to finish -- it just
  keeps giving us the same handful of invoices over and over." Below is (a
  simplified version of) the script they used. Run it. Compare what it
  prints against Postman P4 (training/postman/ -- note estimated_total and
  next_cursor on page 1). Then find the one-line bug and fix it.

Run it:   python training/starters/03b_pagination_cursor.py
"""
import os

import requests
import xmltodict

BASE_URL = os.environ.get(
    "WORKSHOP_BASE_URL",
    "https://processdetraining-d8a8h6dtdhhvh7e2.westeurope-01.azurewebsites.net",
).rstrip("/")
USERNAME = os.environ.get("WORKSHOP_USERNAME", "sapana")
PASSWORD = os.environ.get("WORKSHOP_PASSWORD", "~QEMX_JAOhr5Gr")

session = requests.Session()
_auth = session.post(
    f"{BASE_URL}/v1/auth/token",
    data={"username": USERNAME, "password": PASSWORD},
    timeout=30,
)
_auth.raise_for_status()
TOKEN = _auth.json()["access_token"]
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
print(f"Connected to {BASE_URL} as {USERNAME}\n")


def fetch_invoice_page(cursor=None, page_size=10):
    """One page of invoices. Already written.

    Returns the <invoice_search_response> content as a plain Python dict:
    {"data": {"item": [...]}, "page": {...}, "meta": {...}}
    """
    response = session.post(
        f"{BASE_URL}/v1/invoices/search",
        json={"page_size": page_size, "cursor": cursor},
        headers=HEADERS,
        timeout=60,
    )
    response.raise_for_status()
    parsed = xmltodict.parse(response.text, force_list=("item",))
    return parsed["invoice_search_response"]


# A safety cap: without the fix below, cursor never advances, so has_more
# stays true forever and this would otherwise keep re-requesting page 1
# without end.
MAX_PAGES = 5

all_invoices = []
cursor = None
estimated_total = None

for page_num in range(MAX_PAGES):
    page = fetch_invoice_page(cursor=cursor)
    invoices = page["data"]["item"]
    invoice_numbers = [inv["invoice_number"] for inv in invoices]
    print(f"page {page_num + 1}  cursor sent={cursor}  -> {invoice_numbers}")

    if page_num == 0:
        estimated_total = page["page"]["estimated_total"]

    all_invoices.extend(invoices)

    if page["page"]["has_more"] != "true":
        break
    cursor = page["page"]["cursor"]

print()
print(f"collected (raw rows)    : {len(all_invoices)}")
unique_invoice_numbers = {inv["invoice_number"] for inv in all_invoices}
print(f"unique invoice_numbers  : {len(unique_invoice_numbers)}")
print(f"estimated_total (page 1): {estimated_total}")
if len(unique_invoice_numbers) != len(all_invoices):
    print(f"  -> {len(all_invoices) - len(unique_invoice_numbers)} duplicate row(s)!")
