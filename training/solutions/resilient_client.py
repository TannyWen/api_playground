"""SOLUTION -- Error-handling challenges E1-E3.

Builds the client you would actually want against a real vendor API:

    E1  parse the error envelope and surface error.code + error.request_id
    E2  retry transient failures with exponential backoff and jitter
    E3  fail fast on errors that retrying can never fix

    python training/solutions/resilient_client.py
"""
import os
import random
import time

import requests

BASE_URL = os.environ.get("WORKSHOP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
USERNAME = os.environ.get("WORKSHOP_USERNAME", "student")
PASSWORD = os.environ.get("WORKSHOP_PASSWORD", "student-pass-123")

MAX_ATTEMPTS = 5
BASE_DELAY = 0.25
MAX_DELAY = 8.0

# E3: the whole point. Retrying a 422 will fail identically every time -- the
# request itself is wrong, so nothing about waiting changes the outcome. Only
# transient conditions are worth another attempt.
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


def should_retry(status: int) -> bool:
    return status in RETRYABLE_STATUSES


class ApiError(Exception):
    """An error carrying enough context to be actionable.

    The request_id is the part that matters in practice: it is what lets someone
    running the API find *your* failed call in their logs.
    """

    def __init__(self, status, code, message, request_id=None, details=None):
        super().__init__(f"[{status} {code}] {message} (request_id={request_id})")
        self.status = status
        self.code = code
        self.message = message
        self.request_id = request_id
        self.details = details or []

    @classmethod
    def from_response(cls, response: requests.Response) -> "ApiError":
        """Parse a /v1 error envelope, degrading gracefully if it isn't one.

        Every /v1 route uses this envelope, but a defensive client never
        assumes the shape of a response it hasn't checked -- an unexpected
        proxy error page or a route typo would otherwise crash the parser
        instead of surfacing a readable message.
        """
        try:
            body = response.json()
        except ValueError:
            body = {}
        err = body.get("error")
        if isinstance(err, dict):
            return cls(
                status=err.get("status", response.status_code),
                code=err.get("code", "unknown"),
                message=err.get("message", ""),
                request_id=err.get("request_id"),
                details=err.get("details"),
            )
        return cls(
            status=response.status_code,
            code="unstructured_error",
            message=str(body.get("detail", response.text[:200])),
            request_id=response.headers.get("x-request-id"),
        )


def backoff_delay(attempt: int, response: requests.Response | None) -> float:
    """Honour Retry-After when the server sends one; otherwise back off.

    Guessing when the server has told you exactly how long to wait is both
    slower and ruder than reading the header.
    """
    if response is not None:
        retry_after = response.headers.get("retry-after")
        if retry_after and str(retry_after).isdigit():
            return float(retry_after)

    # Exponential, capped, with jitter. The jitter matters as soon as more than
    # one client is retrying: without it they synchronise and hammer the server
    # in lockstep the moment the window opens.
    exponential = min(MAX_DELAY, BASE_DELAY * (2**attempt))
    return exponential * (0.5 + random.random() / 2)


def request_with_retry(session, method, path, *, token=None, verbose=False, **kwargs):
    """Issue a request, retrying only what is worth retrying."""
    headers = dict(kwargs.pop("headers", {}))
    if token:
        headers["Authorization"] = f"Bearer {token}"

    attempts = 0
    for attempt in range(MAX_ATTEMPTS):
        attempts += 1
        response = session.request(
            method, f"{BASE_URL}{path}", headers=headers, timeout=60, **kwargs
        )
        if response.ok:
            return response, attempts

        error = ApiError.from_response(response)
        if not should_retry(response.status_code):
            # Fail immediately -- do not burn the remaining attempts.
            if verbose:
                print(f"    {error.status} {error.code}: not retryable, giving up")
            raise error

        if attempt == MAX_ATTEMPTS - 1:
            raise error

        delay = backoff_delay(attempt, response)
        if verbose:
            print(
                f"    {error.status} {error.code}: retryable, "
                f"attempt {attempt + 1}/{MAX_ATTEMPTS}, sleeping {delay:.2f}s"
            )
        time.sleep(delay)

    raise RuntimeError("unreachable")


def get_token(session) -> str:
    r = session.post(
        f"{BASE_URL}/v1/auth/token",
        data={"username": USERNAME, "password": PASSWORD},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def main() -> None:
    session = requests.Session()
    token = get_token(session)
    failures = []

    # --- E1: read the envelope ------------------------------------------------
    print("E1  Parsing the error envelope")
    try:
        request_with_retry(
            session,
            "POST",
            "/v1/invoices/search",
            token=token,
            json={"page_size": 0, "filters": {"currency": "EURO"}},
        )
        failures.append("E1: a 422 was expected but the request succeeded")
    except ApiError as e:
        print(f"    caught: {e}")
        print(f"    offending fields: {[d.get('field') for d in e.details]}")
        if e.request_id is None:
            failures.append("E1: envelope carried no request_id")
    print()

    # --- E2: retry transient failures ----------------------------------------
    print("E2  Retrying an endpoint that fails every third call")
    successes, total_attempts = 0, 0
    for i in range(20):
        try:
            _, attempts = request_with_retry(
                session,
                "GET",
                "/v1/unstable/invoices",
                token=token,
                params={"page_size": 1},
                verbose=(i == 0),
            )
            successes += 1
            total_attempts += attempts
        except ApiError as e:
            failures.append(f"E2: extract {i + 1} failed -- {e}")
    print(f"    {successes}/20 extracts succeeded, {total_attempts} HTTP calls total")
    if successes != 20:
        failures.append(f"E2: only {successes}/20 succeeded")

    # --- E3: do not retry the unretryable ------------------------------------
    print("\nE3  Failing fast on errors that retrying cannot fix")
    for label, status, call in [
        ("422 invalid request", 422,
         lambda: request_with_retry(session, "POST", "/v1/invoices/search",
                                    token=token, json={"page_size": 99}, verbose=True)),
        ("404 not found", 404,
         lambda: request_with_retry(session, "GET", "/v1/invoices/INV-nope",
                                    token=token, verbose=True)),
        ("401 bad token", 401,
         lambda: request_with_retry(session, "GET", "/v1/whoami",
                                    token="garbage", verbose=True)),
    ]:
        started = time.perf_counter()
        try:
            call()
            failures.append(f"E3: {label} unexpectedly succeeded")
        except ApiError as e:
            elapsed = time.perf_counter() - started
            ok = e.status == status and elapsed < 1.0
            print(f"    {label:22} -> {e.status} in {elapsed * 1000:.0f}ms "
                  f"{'(no retries, correct)' if ok else '(RETRIED -- wrong)'}")
            if not ok:
                failures.append(f"E3: {label} took {elapsed:.2f}s, so it was retried")

    print(f"\n  should_retry() verdicts:")
    for status in (200, 401, 404, 422, 429, 500, 503):
        print(f"    {status} -> {'retry' if should_retry(status) else 'fail fast'}")

    if failures:
        print("\nFAIL:")
        for f in failures:
            print(f"  - {f}")
        raise SystemExit(1)
    print("\nPASS: transient failures retried, permanent failures surfaced immediately.")


if __name__ == "__main__":
    main()
