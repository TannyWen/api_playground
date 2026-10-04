"""Seed, inspect or clear the vendor-posting database.

Usage:
    python manage.py seed [--vendors 20] [--fresh] [--seed 20260903]
    python manage.py seed-users --members alice,bob,carol [--format markdown] [--out creds.md]
    python manage.py seed-users --count 8 [--prefix ws-]
    python manage.py doctor                    # read-only health check
    python manage.py clear
    python manage.py auto-seed                 # wipe + deterministic rebuild, reads
                                                # WORKSHOP_DATA_SEED / WORKSHOP_MEMBERS
                                                # from the environment (see app/main.py)
"""
import argparse
import os
import random
import re
import string
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

from faker import Faker
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database import Base, SessionLocal, engine
from app.models import Account, Invoice, InvoiceLineItem, Posting, User, Vendor
from app.security import hash_password

fake = Faker()

DEFAULT_USERS = {
    "student": "student-pass-123",
    "instructor": "instructor-pass-456",
}

# ---------------------------------------------------------------------------
# Chart of accounts -- fixed and hand-authored, like a real one. Not randomly
# generated: a chart of accounts should look deliberate and stay stable
# across reseeds.
#
# The accounting pattern per invoice line: an expense account (debit) + VAT
# Payable (debit) + Vendor Payable (credit, forced onto the invoice's first
# line item) -- which is exactly standard double-entry AP posting, and
# exactly why 100 + 10 + (-110) = 0 in the simplest case.
# ---------------------------------------------------------------------------
ACCOUNT_SET_ID = "AS-01"
ACCOUNT_SET_NAME = "Global Chart of Accounts"

CHART_OF_ACCOUNTS = [
    # (account_number, account_name, account_group_number, account_group_name)
    ("2000", "Vendor Payable", "AG-10", "Payables"),
    ("2100", "VAT Payable", "AG-20", "Tax"),
    ("6100", "Office Supplies", "AG-40", "Expenses"),
    ("6120", "Professional Services", "AG-40", "Expenses"),
    ("6300", "Furniture and Fixtures", "AG-40", "Expenses"),
    ("6430", "Software Licences", "AG-40", "Expenses"),
    ("6510", "Fleet and Travel", "AG-40", "Expenses"),
]
VENDOR_PAYABLE_ACCOUNT = "2000"
VAT_PAYABLE_ACCOUNT = "2100"
VAT_RATE = Decimal("0.24")

# Each purchasing description maps to the expense account it posts to.
PURCHASING_ITEMS = {
    "Office supplies": "6100",
    "Consulting hours": "6120",
    "Office furniture": "6300",
    "Software licenses": "6430",
    "Fleet fuel": "6510",
}

VENDOR_GROUPS = ["Goods Suppliers", "Service Providers", "Professional Services", "Utilities"]

# (country name, ISO-2, VAT prefix or None)
VENDOR_COUNTRIES = [
    ("Finland", "FI"),
    ("Germany", "DE"),
    ("Sweden", "SE"),
    ("Netherlands", "NL"),
    ("France", "FR"),
    ("United Kingdom", "GB"),
    ("United States", None),
    ("Poland", "PL"),
]

# Deliberately unambiguous: no 0/O, no 1/l/I, nothing that breaks when dictated
# across a room or typed by hand into Postman.
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "member"


PASSWORD_LENGTH = 14
# Deliberately excludes shell-special characters (` $ \ ! " ' ; & | < > ( ) { } [ ]
# and space) so a password is still safe to paste straight into a terminal
# (e.g. a curl command), not just into Postman.
_SPECIAL_CHARS = "-_@#%^*+=~"


def _make_password(rng: random.Random | None = None, length: int = PASSWORD_LENGTH) -> str:
    """A random `length`-character password with upper, lower, digit, and a
    special character all guaranteed present -- no dictionary-word pattern.

    Cryptographically random by default (manual `seed-users` runs), via
    `random.SystemRandom` (the OS's CSPRNG -- the same source `secrets`
    itself draws from). Pass a seeded `random.Random` instead for
    deterministic output -- used by `auto_seed_on_start` so a restart
    regenerates the exact same passwords rather than invalidating every
    printed credential card.
    """
    source = rng or random.SystemRandom()
    pools = (string.ascii_uppercase, string.ascii_lowercase, string.digits, _SPECIAL_CHARS)

    chars = [source.choice(pool) for pool in pools]
    all_chars = "".join(pools)
    chars += [source.choice(all_chars) for _ in range(length - len(chars))]
    source.shuffle(chars)
    return "".join(chars)


def _next_invoice_suffix(db) -> int:
    """Continue numbering past whatever is already stored (INV-2025-NNN)."""
    suffixes = []
    for (number,) in db.query(Invoice.invoice_number).all():
        m = re.match(r"^INV-2025-(\d+)$", number or "")
        if m:
            suffixes.append(int(m.group(1)))
    return (max(suffixes) + 1) if suffixes else 1


def _make_vendor(index: int, rng: random.Random) -> Vendor:
    country, iso2 = rng.choice(VENDOR_COUNTRIES)
    number = rng.randint(100, 999)
    return Vendor(
        vendor_number=f"V-{number:04d}",
        vendor_name=fake.company(),
        vendor_address=fake.street_address(),
        vendor_post_code=fake.postcode(),
        vendor_country=country,
        vendor_group=rng.choice(VENDOR_GROUPS),
        vendor_tax_number=f"{iso2}{rng.randint(10**7, 10**9)}" if iso2 else None,
    )


def _make_invoice(
    invoice_number: str,
    vendor: Vendor,
    accounting_date: date,
    accounts: dict,
    rng: random.Random,
) -> Invoice:
    """Build one invoice with 1-4 line items, whose postings sum to exactly
    zero -- an expense + VAT posting per line, and a single Vendor Payable
    posting (the credit that balances the whole invoice) forced onto the
    first line item.
    """
    num_lines = rng.randint(1, 4)
    line_items = []
    running_total = Decimal("0.00")

    for i in range(1, num_lines + 1):
        description = rng.choice(list(PURCHASING_ITEMS))
        expense_account = accounts[PURCHASING_ITEMS[description]]
        vat_account = accounts[VAT_PAYABLE_ACCOUNT]

        expense_amount = Decimal(str(round(rng.uniform(50, 2500), 2)))
        vat_amount = (expense_amount * VAT_RATE).quantize(Decimal("0.01"))
        running_total += expense_amount + vat_amount

        line_items.append(
            InvoiceLineItem(
                line_item=i,
                purchasing_line_description=description,
                quantity=rng.randint(1, 50),
                postings=[
                    Posting(account=expense_account, line_amount=expense_amount),
                    Posting(account=vat_account, line_amount=vat_amount),
                ],
            )
        )

    # The balancing entry -- forced onto the first line item so the payload
    # stays a clean 3-level tree with nothing floating at the invoice level.
    line_items[0].postings.append(
        Posting(account=accounts[VENDOR_PAYABLE_ACCOUNT], line_amount=-running_total)
    )

    return Invoice(
        invoice_number=invoice_number,
        vendor_id=vendor.id,
        accounting_date=accounting_date,
        line_items=line_items,
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def seed_users(db) -> None:
    print("\nSeeded credentials:")
    for username, password in DEFAULT_USERS.items():
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            db.delete(existing)
            db.flush()

        password_hash, salt = hash_password(password)
        db.add(User(username=username, password_hash=password_hash, password_salt=salt))
        print(f"  username={username!r:<14} password={password}")
    db.commit()
    print(
        "\nExchange these for a bearer token via:\n"
        "  POST /auth/token  (form fields: username, password)\n"
    )


def _seed_accounts(db) -> dict:
    """Idempotent: existing accounts are reused, not duplicated."""
    accounts = {}
    for number, name, group_number, group_name in CHART_OF_ACCOUNTS:
        acct = db.query(Account).filter(Account.account_number == number).first()
        if not acct:
            acct = Account(
                account_number=number,
                account_name=name,
                account_group_number=group_number,
                account_group_name=group_name,
                account_set_id=ACCOUNT_SET_ID,
                account_set_name=ACCOUNT_SET_NAME,
            )
            db.add(acct)
            db.flush()
        accounts[number] = acct
    db.commit()
    return accounts


def seed(num_vendors: int, fresh: bool, rng_seed: int | None) -> None:
    """Rebuild vendors, the chart of accounts, and a year of invoices (2025).

    ~5 invoices per month, 1-4 line items each, every invoice's postings
    summing to exactly zero.
    """
    if fresh:
        clear(quiet=True)

    rng = random.Random(rng_seed)
    if rng_seed is not None:
        Faker.seed(rng_seed)

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_users(db)
        accounts = _seed_accounts(db)

        vendors = [_make_vendor(i, rng) for i in range(num_vendors)]
        db.add_all(vendors)
        db.commit()
        for v in vendors:
            db.refresh(v)

        suffix = _next_invoice_suffix(db)
        created = skipped = 0
        for month in range(1, 13):
            for _ in range(rng.randint(4, 6)):
                vendor = rng.choice(vendors)
                day = rng.randint(1, 28)
                accounting_date = date(2025, month, day)
                invoice = _make_invoice(
                    f"INV-2025-{suffix:03d}", vendor, accounting_date, accounts, rng
                )
                db.add(invoice)
                try:
                    db.commit()
                    created += 1
                except IntegrityError:
                    # A residual invoice_number clash degrades to a skip
                    # rather than aborting the whole seed.
                    db.rollback()
                    skipped += 1
                suffix += 1

        line_items = db.query(InvoiceLineItem).count()
        postings = db.query(Posting).count()
        print(
            f"Seeded {num_vendors} vendors, {len(accounts)} accounts, {created} invoices, "
            f"{line_items} line items, {postings} postings."
            + (f" Skipped {skipped} on number collision." if skipped else "")
        )
    finally:
        db.close()


def seed_workshop_users(
    members: list[str],
    prefix: str,
    reset: bool,
    fmt: str,
    out: str | None,
    base_url: str,
    rng_seed: int | None = None,
) -> None:
    """Create one account per workshop participant and print a credential sheet.

    With `rng_seed` set, passwords are deterministic: the same member list, in
    the same order, always produces the same usernames and passwords. That is
    what lets `auto_seed_on_start` wipe and rebuild on every process restart
    without invalidating credentials already printed and handed out.
    """
    rng = random.Random(rng_seed) if rng_seed is not None else None
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        rows, created, skipped, rotated = [], 0, 0, 0
        used: set[str] = set()

        for display in members:
            username = prefix + _slugify(display)
            candidate, n = username, 2
            while candidate in used:
                candidate, n = f"{username}-{n}", n + 1
            username = candidate
            used.add(username)

            existing = db.query(User).filter(User.username == username).first()
            if existing and not reset:
                rows.append((display, username, "(existing - not recoverable)"))
                skipped += 1
                continue

            password = _make_password(rng)
            if existing:
                db.delete(existing)
                db.flush()
                rotated += 1
            else:
                created += 1

            password_hash, salt = hash_password(password)
            db.add(
                User(username=username, password_hash=password_hash, password_salt=salt)
            )
            rows.append((display, username, password))

        # Always keep an instructor account available.
        if not db.query(User).filter(User.username == "instructor").first():
            pw_hash, salt = hash_password(DEFAULT_USERS["instructor"])
            db.add(
                User(
                    username="instructor",
                    password_hash=pw_hash,
                    password_salt=salt,
                )
            )
        db.commit()

        sheet = _render_sheet(rows, fmt, base_url)
        print(sheet)
        if out:
            with open(out, "w", encoding="utf-8") as f:
                f.write(sheet + "\n")
            print(f"\nWrote {out}")

        print(f"\n{created} created, {skipped} skipped, {rotated} reset.")
        if rotated:
            print(
                "WARNING: rotated passwords for: "
                + ", ".join(u for _, u, p in rows if not p.startswith("("))
            )
        if not os.getenv("JWT_SECRET_KEY"):
            print(
                "\nNote: JWT_SECRET_KEY is not set, so app/security.py's fixed\n"
                "      fallback is signing tokens. That's fine for this training\n"
                "      deployment (tokens still survive a restart) -- set your own\n"
                "      JWT_SECRET_KEY instead only if this ever guards real data."
            )
    finally:
        db.close()


def auto_seed_on_start() -> None:
    """Wipe and deterministically rebuild everything. Meant to run once, at
    process startup, when AUTO_SEED_ON_START is set.

    The point: a restart is no longer a risk to work around (a wiped
    database, stale credentials) -- it is the *normal* way this dataset
    exists. Every boot lands in the same known-good state, so there is no
    persistent-storage requirement and no manual seeding step, on Azure or
    anywhere else.

    WORKSHOP_MEMBERS (comma-separated display names) are seeded on top of the
    two fixed dev accounts (student/instructor), with the same fixed seed --
    so the same member list always yields the same usernames and passwords,
    and a mid-session restart never invalidates a card already handed out.
    """
    data_seed = int(os.getenv("WORKSHOP_DATA_SEED", "20260903"))
    print(f"[auto-seed] rebuilding with fixed seed {data_seed} ...")
    seed(num_vendors=20, fresh=True, rng_seed=data_seed)

    members = [m.strip() for m in os.getenv("WORKSHOP_MEMBERS", "").split(",") if m.strip()]
    if members:
        print(f"[auto-seed] seeding {len(members)} workshop account(s) ...")
        seed_workshop_users(
            members=members,
            prefix="",
            reset=True,
            fmt="table",
            out=None,
            base_url=os.getenv("WORKSHOP_BASE_URL", "(see the App Service URL)"),
            rng_seed=data_seed,
        )
    else:
        print("[auto-seed] WORKSHOP_MEMBERS not set -- only the default dev accounts exist.")


def _render_sheet(rows, fmt: str, base_url: str) -> str:
    header = (
        "Workshop credentials - Procurement Training API\n"
        f"Base URL: {base_url}\n"
        "Token:    POST /auth/token   (Body -> x-www-form-urlencoded: username, password)\n"
    )
    if fmt == "csv":
        body = "member,username,password\n" + "\n".join(
            f"{d},{u},{p}" for d, u, p in rows
        )
        return body
    if fmt == "markdown":
        body = "| Member | Username | Password |\n|---|---|---|\n" + "\n".join(
            f"| {d} | `{u}` | `{p}` |" for d, u, p in rows
        )
        return header + "\n" + body
    width = max([len(u) for _, u, _ in rows] + [8])
    body = "\n".join(f"  {d:<16} {u:<{width}}  {p}" for d, u, p in rows)
    return header + "\n" + body


EXPECTED_TABLES = [
    "users",
    "vendors",
    "accounts",
    "invoices",
    "invoice_line_items",
    "postings",
]

ORPHAN_CHECKS = {
    "postings without a line item": (
        "SELECT COUNT(*) FROM postings p "
        "LEFT JOIN invoice_line_items l ON l.id = p.line_item_id WHERE l.id IS NULL"
    ),
    "postings without an account": (
        "SELECT COUNT(*) FROM postings p "
        "LEFT JOIN accounts a ON a.id = p.account_id WHERE a.id IS NULL"
    ),
    "line items without an invoice": (
        "SELECT COUNT(*) FROM invoice_line_items l "
        "LEFT JOIN invoices i ON i.id = l.invoice_id WHERE i.id IS NULL"
    ),
    "invoices without a vendor": (
        "SELECT COUNT(*) FROM invoices i "
        "LEFT JOIN vendors v ON v.id = i.vendor_id WHERE v.id IS NULL"
    ),
}


def doctor() -> int:
    """Read-only pre-flight check. Exits non-zero if anything looks wrong."""
    import sqlalchemy as sa

    problems = 0
    print(f"Database URL: {engine.url}")

    insp = sa.inspect(engine)
    present = set(insp.get_table_names())
    print("\nTables:")
    for t in EXPECTED_TABLES:
        ok = t in present
        problems += 0 if ok else 1
        print(f"  [{'ok' if ok else 'MISSING'}] {t}")

    db = SessionLocal()
    try:
        print("\nRow counts:")
        for label, model in [
            ("users", User),
            ("vendors", Vendor),
            ("accounts", Account),
            ("invoices", Invoice),
            ("invoice_line_items", InvoiceLineItem),
            ("postings", Posting),
        ]:
            print(f"  {label:28} {db.query(model).count():>7}")

        print("\nOrphan checks:")
        for label, sql in ORPHAN_CHECKS.items():
            n = db.execute(text(sql)).scalar()
            problems += 0 if n == 0 else 1
            print(f"  [{'ok' if n == 0 else 'FAIL'}] {label}: {n}")

        # The reconciliation the workshop depends on: every invoice's postings
        # sum to exactly zero, the way a real double-entry journal balances.
        mismatch = db.execute(
            text(
                "SELECT COUNT(*) FROM ("
                "  SELECT i.id, SUM(p.line_amount) AS total"
                "  FROM invoices i"
                "  JOIN invoice_line_items l ON l.invoice_id = i.id"
                "  JOIN postings p ON p.line_item_id = l.id"
                "  GROUP BY i.id HAVING ROUND(SUM(p.line_amount), 2) != 0.00"
                ")"
            )
        ).scalar()
        problems += 0 if mismatch == 0 else 1
        print(
            f"  [{'ok' if mismatch == 0 else 'FAIL'}] invoices balancing to zero: "
            f"{mismatch} mismatched"
        )

        print("\nEnvironment:")
        for var, critical in [
            # Not critical: app/security.py falls back to a fixed dev secret
            # when this is unset, so tokens still survive a restart without
            # it -- fine for this training deployment's fake, read-only data.
            ("JWT_SECRET_KEY", False),
            ("ACCESS_TOKEN_EXPIRE_MINUTES", False),
            ("DATABASE_URL", False),
        ]:
            val = os.getenv(var)
            if var == "JWT_SECRET_KEY":
                shown = f"set ({len(val)} chars)" if val else "not set (using fixed dev fallback)"
            else:
                shown = val or "not set"
            flag = "ok" if val else ("FAIL" if critical else "default")
            if critical and not val:
                problems += 1
            print(f"  [{flag}] {var} = {shown}")

        max_suffix = _next_invoice_suffix(db) - 1
        print(f"\nHighest invoice number in use: INV-2025-{max_suffix:03d}")
    finally:
        db.close()

    print(f"\n{'ALL CHECKS PASSED' if problems == 0 else f'{problems} PROBLEM(S) FOUND'}")
    return 0 if problems == 0 else 1


def clear(quiet: bool = False) -> None:
    """Delete everything, child tables first.

    Bulk .delete() bypasses ORM cascades, and SQLite does not enforce foreign
    keys by default, so the deletion order here is what prevents orphaned rows.
    """
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        counts = {
            "postings": db.query(Posting).delete(),
            "line items": db.query(InvoiceLineItem).delete(),
            "invoices": db.query(Invoice).delete(),
            "vendors": db.query(Vendor).delete(),
            "accounts": db.query(Account).delete(),
            "users": db.query(User).delete(),
        }
        db.commit()
        if not quiet:
            print("Cleared " + ", ".join(f"{n} {label}" for label, n in counts.items()) + ".")
    finally:
        db.close()


def _read_members(args) -> list[str]:
    if args.members:
        return [m.strip() for m in args.members.split(",") if m.strip()]
    if args.members_file:
        with open(args.members_file, encoding="utf-8") as f:
            return [
                line.strip()
                for line in f
                if line.strip() and not line.lstrip().startswith("#")
            ]
    if args.count:
        return [f"trainee{i:02d}" for i in range(1, args.count + 1)]
    raise SystemExit("Provide one of --members, --members-file or --count.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    seed_parser = sub.add_parser("seed", help="Populate the database with fake data")
    seed_parser.add_argument("--vendors", type=int, default=20)
    seed_parser.add_argument(
        "--fresh", action="store_true", help="Clear everything first"
    )
    seed_parser.add_argument(
        "--seed", type=int, default=None, help="Fix the RNG for reproducible data"
    )

    users_parser = sub.add_parser(
        "seed-users", help="Create one account per workshop participant"
    )
    group = users_parser.add_mutually_exclusive_group()
    group.add_argument("--members", help="Comma-separated names")
    group.add_argument("--members-file", help="One name per line; # comments ignored")
    group.add_argument("--count", type=int, help="Generate trainee01..traineeNN")
    users_parser.add_argument("--prefix", default="", help="Username prefix")
    users_parser.add_argument(
        "--reset", action="store_true", help="Rotate passwords for existing users"
    )
    users_parser.add_argument(
        "--format", choices=["table", "markdown", "csv"], default="table"
    )
    users_parser.add_argument("--out", help="Also write the sheet to this file")
    users_parser.add_argument("--base-url", default="http://127.0.0.1:8000")

    sub.add_parser("doctor", help="Read-only health check")
    sub.add_parser("clear", help="Delete all data from the database")
    sub.add_parser(
        "auto-seed",
        help=(
            "Deterministically wipe and rebuild everything, reading "
            "WORKSHOP_DATA_SEED / WORKSHOP_MEMBERS from the environment. "
            "Runs automatically at app startup when AUTO_SEED_ON_START is "
            "set; this lets you test the exact same code path by hand."
        ),
    )

    args = parser.parse_args()

    if args.command == "seed":
        seed(args.vendors, args.fresh, args.seed)
    elif args.command == "seed-users":
        seed_workshop_users(
            _read_members(args),
            args.prefix,
            args.reset,
            args.format,
            args.out,
            args.base_url,
        )
    elif args.command == "doctor":
        sys.exit(doctor())
    elif args.command == "clear":
        clear()
    elif args.command == "auto-seed":
        auto_seed_on_start()


if __name__ == "__main__":
    main()
