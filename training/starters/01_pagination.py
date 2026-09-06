"""STARTER -- Pagination challenge P3.

The connection is already wired. Your job is the loop.

Goal: collect EVERY invoice, then prove you got each one exactly once.

Run it:   python training/starters/01_pagination.py
"""
import os

import requests

# ---------------------------------------------------------------------------
# Setup -- already done for you. Set these as environment variables, or just
# edit the defaults below.
# ---------------------------------------------------------------------------
BASE_URL = os.environ.get("WORKSHOP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
USERNAME = os.environ.get("WORKSHOP_USERNAME", "student")
PASSWORD = os.environ.get("WORKSHOP_PASSWORD", "student-pass-123")

session = requests.Session()

# Note `data=` not `json=` -- this endpoint is form-encoded (that was C2).
_auth = session.post(
    f"{BASE_URL}/v1/auth/token",
    data={"username": USERNAME, "password": PASSWORD},
    timeout=30,
)
_auth.raise_for_status()
TOKEN = _auth.json()["access_token"]
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
print(f"Connected to {BASE_URL} as {USERNAME}\n")


def fetch_page(cursor=None, page_size=25):
    """One page of invoices. Already written -- call this in your loop.

    Returns the whole response body:
        {"data": [...], "page": {...}, "meta": {...}}
    """
    response = session.post(
        f"{BASE_URL}/v1/invoices/search",
        json={"page_size": page_size, "cursor": cursor},
        headers=HEADERS,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# YOUR TURN
# ---------------------------------------------------------------------------
# Look at one page first, to see what you are working with:
first = fetch_page()
print("keys in the response :", list(first))
print("keys in 'page'       :", list(first["page"]))
print("invoices on page 1   :", len(first["data"]))
print("estimated_total      :", first["page"]["estimated_total"])
print("next_cursor          :", first["page"]["next_cursor"])
print()

# TODO 1: Write a loop that keeps calling fetch_page(cursor=...) and collects
#         every invoice into `all_invoices`.
#
#         Hint: page 1 gives you a next_cursor. Feed it back in. Stop when
#         next_cursor comes back as None -- NOT when the page looks short,
#         and not by dividing estimated_total by page_size (check what
#         estimated_total is on page 2 and you will see why).

all_invoices = []

# ... your loop here ...


# TODO 2: Prove you got everything exactly once.
#         - How many did you collect?
#         - Does that match estimated_total from page 1?
#         - Are all the invoice_id values unique? (a set is your friend)

print(f"collected: {len(all_invoices)}")

# TODO 3 (stretch): Every response carries these headers:
#           x-ratelimit-limit, x-ratelimit-remaining, x-ratelimit-reset
#         Make your loop slow down when the budget runs low, so you are never
#         throttled in the first place. You will need fetch_page to return the
#         response object, or read the headers inside it.
