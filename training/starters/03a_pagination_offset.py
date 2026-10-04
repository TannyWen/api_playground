"""PART 3 -- PAGINATION, sub-page 1 of 2: offset pagination on vendor master
data -- this script has a real bug in it.

See 03_pagination.py for the full explanation of why pagination exists, the
two styles this API uses, and how to know when you're actually done.

THE TICKET
  A colleague reports: "our vendor export has duplicate rows, and it never
  seems to collect everyone." Below is (a simplified version of) the script
  they used. Run it. Compare what it prints against Postman P3 (training/
  postman/ -- note page.total there). Then find the one-line bug and fix it.

Run it:   python training/starters/03a_pagination_offset.py
"""
import os

import requests

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


def fetch_vendor_page(offset, limit=5):
    """One page of vendors. Already written.

    Returns the whole response body: {"items": [...], "page": {...}}
    """
    response = session.get(
        f"{BASE_URL}/v1/master-data/vendors",
        params={"limit": limit, "offset": offset},
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


# A safety cap: without the fix below, offset never advances, so has_more
# stays true forever and this would otherwise keep re-requesting the same
# page without end.
MAX_PAGES = 10

all_vendors = []
offset = 0

for page_num in range(MAX_PAGES):
    page = fetch_vendor_page(offset)
    vendor_numbers = [v["vendor_number"] for v in page["items"]]
    print(f"page {page_num + 1}  offset sent={offset}  -> {vendor_numbers}")

    all_vendors.extend(page["items"])

    if not page["page"]["has_more"]:
        break
    offset = page["page"]["offset"]

print()
print(f"collected (raw rows)   : {len(all_vendors)}")
unique_vendor_numbers = {v["vendor_number"] for v in all_vendors}
print(f"unique vendor_numbers  : {len(unique_vendor_numbers)}")
if len(unique_vendor_numbers) != len(all_vendors):
    print(f"  -> {len(all_vendors) - len(unique_vendor_numbers)} duplicate row(s)!")
