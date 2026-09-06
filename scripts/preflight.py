"""Pre-flight check for the API workshop. Standard library only.

Runs against any host, so it works under a bare Python with no virtualenv --
which means it can also be run from a participant's laptop to prove the API is
reachable from where they will actually be sitting.

    python scripts/preflight.py --base-url https://processdetraining.azurewebsites.net \
                                --username alice --password amber-falcon-4827

Exits non-zero if any check fails.
"""
import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal

PASS, FAIL = "PASS", "FAIL"
results = []


def record(ok, label, detail=""):
    results.append((PASS if ok else FAIL, label, detail))
    print(f"  [{PASS if ok else FAIL}] {label}" + (f" -- {detail}" if detail else ""))
    return ok


def _lower(headers):
    """HTTP header names are case-insensitive; Starlette emits them lowercased."""
    return {k.lower(): v for k, v in headers.items()}


def call(base, method, path, token=None, body=None, form=None, headers=None, timeout=60):
    """Returns (status, parsed_body, response_headers)."""
    url = base.rstrip("/") + path
    data = None
    hdrs = dict(headers or {})
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    if token:
        hdrs["Authorization"] = "Bearer " + token

    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else None), _lower(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = {"_raw": raw[:300]}
        return e.code, parsed, _lower(e.headers)
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        # Nothing listening, DNS failure, a proxy refusing, a TLS problem. Report
        # it as status 0 so the caller can say something useful instead of
        # dumping a traceback on someone who just wants to know if it is up.
        return 0, {"_transport_error": str(getattr(e, "reason", e))}, {}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--username", default="student")
    ap.add_argument("--password", default="student-pass-123")
    ap.add_argument(
        "--skip-slow",
        action="store_true",
        help="Skip the rate-limit and retry checks, which sleep.",
    )
    args = ap.parse_args()
    base = args.base_url

    print("\nPre-flight against " + base + "\n")

    # ---- Connection --------------------------------------------------------
    print("Connection")
    t0 = time.perf_counter()
    st, body, _ = call(base, "GET", "/v1/ping")
    elapsed = time.perf_counter() - t0
    if st == 0:
        record(False, "GET /v1/ping", (body or {}).get("_transport_error", "unreachable"))
        print()
        print("  Could not reach the API at all. Nothing else can be checked.")
        print("  Things to try, in order:")
        print(r"    1. Is it running?  .\run_api.ps1   (then retry)")
        print(f"    2. Is the URL right? You used: {base}")
        print("       Local needs the port (:8000); Azure must not have one.")
        print("       Local is http://, Azure is https://.")
        print("    3. Open it in a browser: " + base + "/v1/ping")
        print("    4. If the browser works but this does not, a proxy is in the way.")
        return 1
    record(
        st == 200 and (body or {}).get("status") == "ok",
        "GET /v1/ping",
        f"{elapsed:.1f}s",
    )
    if elapsed > 15:
        print("         ^ a slow first call is normal on Azure (cold start); re-run")

    # The form-vs-JSON trap, asserted so the workshop step cannot silently break.
    st, _, _ = call(
        base,
        "POST",
        "/v1/auth/token",
        body={"username": args.username, "password": args.password},
    )
    record(st == 422, "POST /v1/auth/token with a JSON body is rejected", f"got {st}")

    st, tok, _ = call(
        base,
        "POST",
        "/v1/auth/token",
        form={"username": args.username, "password": args.password},
    )
    if not record(
        st == 200 and "access_token" in (tok or {}),
        "POST /v1/auth/token form-encoded",
        f"got {st}",
    ):
        print("\nCannot continue without a token.")
        return 1
    token = tok["access_token"]

    # The 403-vs-401 distinction the workshop teaches.
    st, _, _ = call(base, "GET", "/v1/whoami")
    record(st == 403, "GET /v1/whoami with no header -> 403", f"got {st}")
    st, _, _ = call(base, "GET", "/v1/whoami", token="garbage")
    record(st == 401, "GET /v1/whoami with a bad token -> 401", f"got {st}")

    st, me, hdrs = call(base, "GET", "/v1/whoami", token=token)
    record(
        st == 200 and (me or {}).get("username") == args.username,
        "GET /v1/whoami",
        (me or {}).get("username", ""),
    )
    ttl = (me or {}).get("token_expires_in_seconds") or 0
    record(ttl > 0, "token has a positive lifetime", f"{ttl}s (~{ttl // 60} min)")
    if 0 < ttl < 9000:
        print("         ^ under 2.5h -- set ACCESS_TOKEN_EXPIRE_MINUTES=480")
    record(
        "x-ratelimit-remaining" in hdrs,
        "rate-limit headers present",
        hdrs.get("x-ratelimit-remaining", ""),
    )
    record("x-request-id" in hdrs, "X-Request-Id header present", hdrs.get("x-request-id", ""))

    # ---- Master data, offset pagination ------------------------------------
    print("\nMaster data (offset pagination)")
    st, page, _ = call(base, "GET", "/v1/master-data/suppliers?limit=5&offset=0", token=token)
    if not record(
        st == 200 and len(((page or {}).get("items") or [])) == 5,
        "GET /v1/master-data/suppliers?limit=5",
        f"got {st}",
    ):
        return 1
    total_suppliers = page["page"]["total"]
    print(f"         total suppliers: {total_suppliers}")
    first = page["items"][0]
    record(
        isinstance(first.get("contacts"), list),
        "suppliers carry a contacts[] array",
        f"{len(first['contacts'])} on the first row",
    )
    record(isinstance(first.get("address"), dict), "suppliers carry a nested address{}")

    st, _, _ = call(base, "GET", "/v1/master-data/suppliers?limit=999", token=token)
    record(st == 422, "limit above the cap -> 422", f"got {st}")

    collected = []
    offset = 0
    pages = 0
    while True:
        st, page, _ = call(
            base, "GET", f"/v1/master-data/suppliers?limit=50&offset={offset}", token=token
        )
        if st != 200:
            record(False, "offset drain", f"page {pages} returned {st}")
            break
        collected += [s["supplier_code"] for s in page["items"]]
        pages += 1
        nxt = page["page"]["next_offset"]
        if nxt is None or pages > 60:
            break
        offset = nxt
    record(
        len(collected) == total_suppliers and len(set(collected)) == len(collected),
        "offset drain collects every supplier exactly once",
        f"{len(collected)} rows over {pages} pages, {len(set(collected))} unique",
    )

    # ---- Invoice search, cursor pagination ---------------------------------
    print("\nInvoice search (cursor pagination)")
    st, res, _ = call(base, "POST", "/v1/invoices/search", token=token, body={})
    if not record(st == 200, "POST /v1/invoices/search with an empty {} body", f"got {st}"):
        return 1
    estimated = res["page"]["estimated_total"]
    record(estimated is not None, "page 1 carries estimated_total", str(estimated))
    record(res["page"]["next_cursor"] is not None, "page 1 carries next_cursor")

    st, res2, _ = call(
        base,
        "POST",
        "/v1/invoices/search",
        token=token,
        body={"cursor": res["page"]["next_cursor"]},
    )
    record(st == 200, "page 2 fetched via next_cursor", f"got {st}")
    record(
        res2["page"]["estimated_total"] is None,
        "page 2 omits estimated_total, forcing a real drain loop",
    )

    st, _, _ = call(
        base, "POST", "/v1/invoices/search", token=token, body={"cursor": "!!!not-a-cursor"}
    )
    record(st == 400, "a malformed cursor -> 400 invalid_cursor", f"got {st}")

    st, _, _ = call(base, "POST", "/v1/invoices/search", token=token, body={"limit": 25})
    record(st == 422, "a parameter at the wrong nesting level -> 422", f"got {st}")

    # Nesting depth, which the flattening exercises depend on.
    deep = None
    for inv in res["data"]:
        lines = inv.get("line_items") or []
        if any(len(li.get("allocations") or []) >= 2 for li in lines):
            deep = inv
            break
    record(
        deep is not None,
        "an invoice exists with 2+ allocations on one line",
        deep["invoice_number"] if deep else "none on page 1",
    )

    if deep:
        # Money must arrive as a JSON string -- the central flattening lesson.
        record(
            isinstance(deep["total_amount"], str),
            "total_amount arrives as a JSON string, not a number",
            repr(deep["total_amount"]),
        )
        for li in deep["line_items"]:
            allocs = li.get("allocations") or []
            if len(allocs) >= 2:
                s = sum(Decimal(a["amount"]) for a in allocs)
                record(
                    s == Decimal(li["line_total"]),
                    "allocations reconcile exactly to line_total",
                    f"{s} vs {li['line_total']}",
                )
                break

    seen = []
    cursor = None
    pages = 0
    while True:
        st, r, _ = call(
            base,
            "POST",
            "/v1/invoices/search",
            token=token,
            body={
                "page_size": 25,
                "cursor": cursor,
                "include": {"supplier": False, "line_items": False, "allocations": False},
            },
        )
        if st != 200:
            record(False, "cursor drain", f"page {pages} returned {st}")
            break
        seen += [i["invoice_id"] for i in r["data"]]
        pages += 1
        cursor = r["page"]["next_cursor"]
        if cursor is None or pages > 200:
            break
    record(
        len(seen) == estimated and len(set(seen)) == len(seen),
        "cursor drain collects every invoice exactly once",
        f"{len(seen)} rows over {pages} pages vs estimated {estimated}",
    )

    number = res2["data"][0]["invoice_number"]
    st, _, _ = call(base, "GET", "/v1/invoices/" + number, token=token)
    record(st == 200, "GET /v1/invoices/{invoice_number}", number)
    st, _, _ = call(base, "GET", "/v1/invoices/INV-does-not-exist", token=token)
    record(st == 404, "an unknown invoice number -> 404", f"got {st}")

    # ---- Error handling ----------------------------------------------------
    print("\nError handling")
    st, err, _ = call(
        base,
        "POST",
        "/v1/invoices/search",
        token=token,
        body={"page_size": 0, "filters": {"currency": "EURO"}},
    )
    e = (err or {}).get("error") or {}
    required = {"code", "message", "status", "request_id", "retryable", "details"}
    record(
        st == 422 and required <= set(e),
        "422 returns the full error envelope",
        f"code={e.get('code')}",
    )
    record(
        len(e.get("details") or []) >= 2,
        "the envelope lists every offending field",
        ", ".join(str(d.get("field")) for d in (e.get("details") or [])),
    )
    record(e.get("retryable") is False, "422 is flagged as not retryable")

    st, err, _ = call(base, "GET", "/invoices/999999", token=token)
    legacy = err or {}
    record(
        st == 404 and "detail" in legacy and "error" not in legacy,
        "legacy endpoints keep their bare `detail` error shape",
        str(sorted(legacy))[:40],
    )

    if not args.skip_slow:
        got429 = False
        retry_after = None
        err = None
        for _ in range(12):
            st, err, hdrs = call(
                base, "GET", "/v1/unstable/throttled-invoices?page_size=1", token=token
            )
            if st == 429:
                got429 = True
                retry_after = hdrs.get("retry-after")
                break
        record(got429, "the throttled route eventually returns 429")
        record(
            retry_after is not None and str(retry_after).isdigit() and int(retry_after) > 0,
            "429 carries a positive integer Retry-After",
            f"{retry_after}s",
        )
        if got429 and err:
            record(
                ((err.get("error") or {}).get("retryable")) is True,
                "429 is flagged as retryable",
            )

        st, _, hdrs = call(
            base,
            "GET",
            "/v1/unstable/invoices?page_size=1",
            token=token,
            headers={"X-Chaos": "fail"},
        )
        record(st == 503, "X-Chaos: fail forces a 503", f"got {st}")
        record(hdrs.get("retry-after") is not None, "503 carries Retry-After")

        successes = 0
        attempts = 0
        for _ in range(20):
            for attempt in range(5):
                attempts += 1
                st, _, _ = call(base, "GET", "/v1/unstable/invoices?page_size=1", token=token)
                if st == 200:
                    successes += 1
                    break
                if st != 503:
                    break
                time.sleep(0.05 * (2**attempt))
        record(
            successes == 20,
            "retry-with-backoff achieves 20/20 successes",
            f"{successes}/20 in {attempts} attempts",
        )

    failed = [r for r in results if r[0] == FAIL]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print("\nFailures:")
        for _, label, detail in failed:
            print(f"  - {label} ({detail})")
        return 1
    print("Ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
