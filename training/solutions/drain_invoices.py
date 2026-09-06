"""SOLUTION -- Pagination challenges P1-P3 (and stretch P4).

Drains every invoice by following next_cursor until it comes back null, then
checks the count against estimated_total.

    python training/solutions/drain_invoices.py

Config comes from environment variables so the same file works against a local
server and against Azure:

    WORKSHOP_BASE_URL   default http://127.0.0.1:8000
    WORKSHOP_USERNAME   default student
    WORKSHOP_PASSWORD   default student-pass-123
"""
import json
import os
import pathlib
import time

import requests

BASE_URL = os.environ.get("WORKSHOP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
USERNAME = os.environ.get("WORKSHOP_USERNAME", "student")
PASSWORD = os.environ.get("WORKSHOP_PASSWORD", "student-pass-123")

PAGE_SIZE = 25
OUT_DIR = pathlib.Path(__file__).resolve().parents[1] / "data"


def get_token(session: requests.Session) -> str:
    """Exchange credentials for a bearer token.

    Note `data=` and not `json=`. This endpoint is form-encoded; sending JSON
    returns 422. That is challenge C2.
    """
    r = session.post(
        f"{BASE_URL}/v1/auth/token",
        data={"username": USERNAME, "password": PASSWORD},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def respect_budget(response: requests.Response) -> None:
    """Stretch P4: slow down before being throttled, not after.

    Every /v1 response reports the remaining budget, so a well-behaved client
    never needs to see a 429 at all.
    """
    remaining = response.headers.get("x-ratelimit-remaining")
    reset_in = response.headers.get("x-ratelimit-reset")
    if remaining is not None and int(remaining) <= 2:
        wait = int(reset_in or 1)
        print(f"  budget nearly spent ({remaining} left) -- pausing {wait}s")
        time.sleep(wait)


def drain_invoices(session: requests.Session, token: str) -> list[dict]:
    """Follow next_cursor until there is no next page.

    The only correct termination condition is `next_cursor is None`. The
    response gives no total after page 1, precisely so that computing a page
    count up front is not an option.
    """
    headers = {"Authorization": f"Bearer {token}"}
    invoices: list[dict] = []
    cursor = None
    page = 0
    estimated_total = None

    while True:
        body = {"page_size": PAGE_SIZE, "cursor": cursor}
        r = session.post(
            f"{BASE_URL}/v1/invoices/search", json=body, headers=headers, timeout=60
        )
        r.raise_for_status()
        payload = r.json()

        page += 1
        invoices.extend(payload["data"])

        if page == 1:
            estimated_total = payload["page"]["estimated_total"]
            print(f"  page 1: estimated_total = {estimated_total}")

        respect_budget(r)

        cursor = payload["page"]["next_cursor"]
        if cursor is None:
            break

        # A guard against an accidental infinite loop -- worth having in any
        # real extractor, since a server-side bug should not spin forever.
        if page > 500:
            raise RuntimeError("Aborting: more than 500 pages, cursor may not advance")

    print(f"  drained {page} pages")
    return invoices, estimated_total


def main() -> None:
    print(f"Draining invoices from {BASE_URL}")
    session = requests.Session()
    token = get_token(session)

    invoices, estimated_total = drain_invoices(session, token)

    ids = [i["invoice_id"] for i in invoices]
    unique = len(set(ids))

    print(f"\ncollected      : {len(invoices)}")
    print(f"unique ids     : {unique}")
    print(f"estimated_total: {estimated_total}")

    problems = []
    if unique != len(ids):
        problems.append(f"{len(ids) - unique} duplicate invoice(s) -- cursor overlap")
    if estimated_total is not None and len(invoices) != estimated_total:
        problems.append(f"expected {estimated_total}, collected {len(invoices)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "invoices_all_pages.json"
    out.write_text(json.dumps(invoices, indent=2), encoding="utf-8")
    print(f"\nwrote {out.relative_to(OUT_DIR.parents[1])} ({out.stat().st_size // 1024} KB)")

    if problems:
        print("\nFAIL: " + "; ".join(problems))
        raise SystemExit(1)
    print("PASS: every invoice collected exactly once.")


if __name__ == "__main__":
    main()
