"""Seed, inspect or clear the procurement invoice database.

Usage:
    python manage.py seed [--suppliers 118] [--invoices 613] [--fresh] [--seed 20260903]
    python manage.py seed-users --members alice,bob,carol [--format markdown] [--out creds.md]
    python manage.py seed-users --count 8 [--prefix ws-]
    python manage.py backfill                  # add master data to rows that lack it
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
import secrets
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

from faker import Faker
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database import Base, SessionLocal, engine
from app.models import (
    Invoice,
    InvoiceLineAllocation,
    InvoiceLineItem,
    InvoiceStatus,
    Supplier,
    SupplierContact,
    SupplierProfile,
    User,
)
from app.security import hash_password

fake = Faker()

DEFAULT_USERS = {
    "student": "student-pass-123",
    "instructor": "instructor-pass-456",
}

STATUSES = list(InvoiceStatus)
CURRENCIES = ["USD", "EUR", "GBP"]
ITEM_CATALOG = [
    "Office chairs",
    "Laptop docking stations",
    "Printer toner cartridges",
    "Cloud hosting services",
    "Consulting hours",
    "Steel pipes",
    "Safety helmets",
    "Warehouse shelving",
    "Fleet fuel cards",
    "Software licenses",
    "Packaging materials",
    "Industrial lubricant",
]

# Keeping the legacy `suppliers.country` full name coherent with the ISO-2 code in
# supplier_profiles. The mismatch between the two representations is deliberate
# teaching material: /suppliers?country=FI returns nothing, ?country=Finland works.
COUNTRIES = [
    # (name, iso2, default_currency, vat_prefix)
    ("Finland", "FI", "EUR", "FI"),
    ("Germany", "DE", "EUR", "DE"),
    ("Sweden", "SE", "SEK", "SE"),
    ("Netherlands", "NL", "EUR", "NL"),
    ("France", "FR", "EUR", "FR"),
    ("Poland", "PL", "PLN", "PL"),
    ("United Kingdom", "GB", "GBP", "GB"),
    ("United States", "US", "USD", None),
    ("Spain", "ES", "EUR", "ES"),
    ("Italy", "IT", "EUR", "IT"),
]

PAYMENT_TERMS = ["NET15", "NET30", "NET45", "NET60", "IMMEDIATE"]
SUPPLIER_STATUSES = ["active", "active", "active", "active", "blocked", "pending"]

COST_CENTERS = [
    ("CC-1002", "R&D Helsinki"),
    ("CC-1040", "R&D Stuttgart"),
    ("CC-2001", "Sales Nordics"),
    ("CC-2210", "Sales DACH"),
    ("CC-3010", "IT Shared Services"),
    ("CC-3400", "Facilities"),
    ("CC-4100", "Logistics"),
    ("CC-5000", "Group Functions"),
]

# Each catalog item maps to a stable GL account, so code-to-label joins in the
# workshop reference exercise produce sensible results.
GL_BY_ITEM = {
    "Office chairs": ("6300", "Furniture and fixtures"),
    "Laptop docking stations": ("6410", "IT hardware"),
    "Printer toner cartridges": ("6100", "Office supplies"),
    "Cloud hosting services": ("6420", "IT services"),
    "Consulting hours": ("6120", "Professional services"),
    "Steel pipes": ("5100", "Raw materials"),
    "Safety helmets": ("6210", "Health and safety"),
    "Warehouse shelving": ("6310", "Warehouse equipment"),
    "Fleet fuel cards": ("6510", "Fleet and travel"),
    "Software licenses": ("6430", "Software licences"),
    "Packaging materials": ("5200", "Packaging"),
    "Industrial lubricant": ("5300", "Consumables"),
}

UOM_BY_ITEM = {
    "Consulting hours": "HUR",
    "Cloud hosting services": "MON",
    "Steel pipes": "MTR",
    "Industrial lubricant": "LTR",
    "Packaging materials": "KGM",
}

# Fixed splits, so allocation percentages always total exactly 100.
ALLOCATION_SPLITS = [
    (Decimal("100.00"),),
    (Decimal("60.00"), Decimal("40.00")),
    (Decimal("50.00"), Decimal("50.00")),
    (Decimal("70.00"), Decimal("30.00")),
    (Decimal("50.00"), Decimal("30.00"), Decimal("20.00")),
    (Decimal("40.00"), Decimal("30.00"), Decimal("30.00")),
]

# Deliberately unambiguous: no 0/O, no 1/l/I, nothing that breaks when dictated
# across a room or typed by hand into Postman.
WORDLIST = """
amber anchor apple arbor arrow aspen atlas autumn azure basin beacon berry
birch bishop bramble branch brass bravo breeze bridge bronze brook cactus
canyon carbon cedar chalk cherry cinder citrus clover cobalt comet copper
coral cotton crane crater crest crimson crystal cypress dahlia dapple delta
dune ember fable falcon fern flint forest fossil garnet gentle ginger granite
gravel grove harbor harvest hazel heather hollow indigo ivory jasper juniper
kestrel lagoon lantern laurel lentil lichen lilac linen lotus lumen maple
marble meadow mesa mineral mistral nectar nimbus nutmeg oasis olive onyx opal
orchard osprey pebble pepper pewter pine plateau plum pollen poplar prairie
quarry quartz quiver ravine reed ridge rowan rubble saffron sage sandal sequoia
shale silver socket spruce steppe summit tamarind teak thistle thorn tide
timber topaz trellis tulip tundra turret velvet vesper walnut willow zephyr
""".split()
WORDLIST = [w for w in WORDLIST if w.isascii() and w.isalpha()]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "member"


def _make_password(rng: random.Random | None = None) -> str:
    """Word-word-NNNN, e.g. amber-falcon-4827.

    Cryptographically random by default (manual `seed-users` runs). Pass a
    seeded `random.Random` for deterministic output instead -- used by
    `auto_seed_on_start` so a restart regenerates the exact same passwords
    rather than invalidating every printed credential card.
    """
    choose = rng.choice if rng else secrets.choice
    number = rng.randrange(1000, 10000) if rng else (secrets.randbelow(9000) + 1000)
    a, b = choose(WORDLIST), choose(WORDLIST)
    while b == a:
        b = choose(WORDLIST)
    return f"{a}-{b}-{number}"


def _next_invoice_base(db) -> int:
    """Continue numbering past whatever is already stored.

    The original seeder hardcoded INV-{2024000 + i}, so a second run collided on
    the unique constraint and aborted.
    """
    suffixes = []
    for (number,) in db.query(Invoice.invoice_number).all():
        m = re.match(r"^INV-(\d+)$", number or "")
        if m:
            suffixes.append(int(m.group(1)))
    return (max(suffixes) + 1) if suffixes else 2024001


def _allocation_rows(line_total: Decimal, rng: random.Random):
    """Split a line total into allocations that sum to it *exactly*.

    Every amount but the last is rounded normally; the last absorbs the rounding
    remainder. This is what makes the workshop reconciliation land on zero.
    """
    split = rng.choice(ALLOCATION_SPLITS)
    rows, running = [], Decimal("0.00")
    for idx, pct in enumerate(split):
        if idx == len(split) - 1:
            amount = line_total - running
        else:
            amount = (line_total * pct / Decimal("100")).quantize(Decimal("0.01"))
            running += amount
        centre, centre_name = rng.choice(COST_CENTERS)
        rows.append(
            {
                "cost_center": centre,
                "cost_center_name": centre_name,
                "percentage": pct,
                "amount": amount,
                "project_code": f"PRJ-{rng.randint(10, 99)}" if rng.random() < 0.4 else None,
            }
        )
    return rows


def _profile_for(supplier: Supplier, index: int, rng: random.Random) -> SupplierProfile:
    name, iso2, currency, vat_prefix = rng.choice(COUNTRIES)
    supplier.country = name  # keep legacy field coherent with the ISO-2 code
    return SupplierProfile(
        supplier_id=supplier.id,
        supplier_code=f"SUP-{index:06d}",
        country_code=iso2,
        vat_number=f"{vat_prefix}{rng.randint(10**7, 10**9)}" if vat_prefix else None,
        duns=str(rng.randint(100000000, 999999999)),
        payment_terms=rng.choice(PAYMENT_TERMS),
        default_currency=currency,
        status=rng.choice(SUPPLIER_STATUSES),
        is_preferred=rng.random() < 0.3,
        address_line1=fake.street_address(),
        address_city=fake.city(),
        address_postal_code=fake.postcode(),
        updated_at=datetime.utcnow() - timedelta(days=rng.randint(0, 400)),
    )


def _contacts_for(supplier: Supplier, rng: random.Random) -> list[SupplierContact]:
    roles = ["Account Manager", "AP Clerk", "Sales", "Support", "Contract Owner"]
    rows = []
    for i in range(rng.randint(1, 3)):
        rows.append(
            SupplierContact(
                supplier_id=supplier.id,
                full_name=fake.name(),
                role=roles[i % len(roles)],
                email=fake.company_email(),
                phone=fake.phone_number() if rng.random() < 0.8 else None,
                is_primary=(i == 0),
            )
        )
    return rows


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


def seed(num_suppliers: int, num_invoices: int, fresh: bool, rng_seed: int | None) -> None:
    if fresh:
        clear(quiet=True)

    rng = random.Random(rng_seed)
    if rng_seed is not None:
        Faker.seed(rng_seed)

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_users(db)

        suppliers = [
            Supplier(
                name=fake.company(),
                contact_email=fake.company_email(),
                country="",  # replaced by _profile_for, kept coherent with country_code
            )
            for _ in range(num_suppliers)
        ]
        db.add_all(suppliers)
        db.commit()
        for s in suppliers:
            db.refresh(s)

        # Master data: 1:1 profile plus 1-3 contacts per supplier.
        code_base = db.query(SupplierProfile).count()
        for offset, supplier in enumerate(suppliers, start=1):
            db.add(_profile_for(supplier, code_base + offset, rng))
            db.add_all(_contacts_for(supplier, rng))
        db.commit()

        base = _next_invoice_base(db)
        created = skipped = 0
        for i in range(num_invoices):
            supplier = rng.choice(suppliers)
            issue_date = date.today() - timedelta(days=rng.randint(0, 365))
            due_date = issue_date + timedelta(days=rng.choice([15, 30, 45, 60]))

            line_items = []
            for _ in range(rng.randint(1, 5)):
                description = rng.choice(ITEM_CATALOG)
                qty = rng.randint(1, 50)
                unit_price = Decimal(str(round(rng.uniform(5, 500), 2)))
                line_total = (unit_price * qty).quantize(Decimal("0.01"))
                item = InvoiceLineItem(
                    description=description,
                    quantity=qty,
                    unit_price=unit_price,
                    line_total=line_total,
                )
                item.allocations = [
                    InvoiceLineAllocation(
                        gl_account=GL_BY_ITEM[description][0], **row
                    )
                    for row in _allocation_rows(line_total, rng)
                ]
                line_items.append(item)

            total_amount = sum((li.line_total for li in line_items), Decimal("0"))

            invoice = Invoice(
                invoice_number=f"INV-{base + i}",
                supplier_id=supplier.id,
                status=rng.choice(STATUSES),
                issue_date=issue_date,
                due_date=due_date,
                currency=rng.choice(CURRENCIES),
                total_amount=total_amount,
                notes=fake.sentence() if rng.random() < 0.3 else None,
                line_items=line_items,
            )
            db.add(invoice)
            try:
                db.commit()
                created += 1
            except IntegrityError:
                # A residual invoice_number clash degrades to a skip rather than
                # aborting the whole seed.
                db.rollback()
                skipped += 1

        allocations = db.query(InvoiceLineAllocation).count()
        lines = db.query(InvoiceLineItem).count()
        print(
            f"Seeded {num_suppliers} suppliers, {created} invoices, "
            f"{lines} line items, {allocations} allocations."
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
    seed(num_suppliers=118, num_invoices=613, fresh=True, rng_seed=data_seed)

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


def backfill() -> None:
    """Add master data to rows that predate it. Additive; never overwrites."""
    Base.metadata.create_all(bind=engine)
    rng = random.Random()
    db = SessionLocal()
    try:
        added_profiles = added_contacts = added_allocs = 0

        code_base = db.query(SupplierProfile).count()
        for supplier in db.query(Supplier).all():
            if not supplier.profile:
                code_base += 1
                db.add(_profile_for(supplier, code_base, rng))
                added_profiles += 1
            if not supplier.contacts:
                db.add_all(_contacts_for(supplier, rng))
                added_contacts += 1
        db.commit()

        for item in db.query(InvoiceLineItem).all():
            if not item.allocations:
                description = item.description
                gl = GL_BY_ITEM.get(description, ("6100", "Office supplies"))[0]
                item.allocations = [
                    InvoiceLineAllocation(gl_account=gl, **row)
                    for row in _allocation_rows(Decimal(str(item.line_total)), rng)
                ]
                added_allocs += 1
        db.commit()

        print(
            f"Backfilled {added_profiles} profiles, {added_contacts} contact sets, "
            f"{added_allocs} line-item allocation sets."
        )
    finally:
        db.close()


ORPHAN_CHECKS = {
    "allocations without a line item": (
        "SELECT COUNT(*) FROM invoice_line_allocations a "
        "LEFT JOIN invoice_line_items l ON l.id = a.line_item_id WHERE l.id IS NULL"
    ),
    "line items without an invoice": (
        "SELECT COUNT(*) FROM invoice_line_items l "
        "LEFT JOIN invoices i ON i.id = l.invoice_id WHERE i.id IS NULL"
    ),
    "invoices without a supplier": (
        "SELECT COUNT(*) FROM invoices i "
        "LEFT JOIN suppliers s ON s.id = i.supplier_id WHERE s.id IS NULL"
    ),
    "profiles without a supplier": (
        "SELECT COUNT(*) FROM supplier_profiles p "
        "LEFT JOIN suppliers s ON s.id = p.supplier_id WHERE s.id IS NULL"
    ),
    "contacts without a supplier": (
        "SELECT COUNT(*) FROM supplier_contacts c "
        "LEFT JOIN suppliers s ON s.id = c.supplier_id WHERE s.id IS NULL"
    ),
}

EXPECTED_TABLES = [
    "users",
    "suppliers",
    "supplier_profiles",
    "supplier_contacts",
    "invoices",
    "invoice_line_items",
    "invoice_line_allocations",
]


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
            ("suppliers", Supplier),
            ("supplier_profiles", SupplierProfile),
            ("supplier_contacts", SupplierContact),
            ("invoices", Invoice),
            ("invoice_line_items", InvoiceLineItem),
            ("invoice_line_allocations", InvoiceLineAllocation),
        ]:
            print(f"  {label:28} {db.query(model).count():>7}")

        print("\nOrphan checks:")
        for label, sql in ORPHAN_CHECKS.items():
            n = db.execute(text(sql)).scalar()
            problems += 0 if n == 0 else 1
            print(f"  [{'ok' if n == 0 else 'FAIL'}] {label}: {n}")

        # The reconciliation the workshop depends on.
        mismatch = db.execute(
            text(
                "SELECT COUNT(*) FROM ("
                "  SELECT l.id, l.line_total, SUM(a.amount) AS alloc"
                "  FROM invoice_line_items l"
                "  JOIN invoice_line_allocations a ON a.line_item_id = l.id"
                "  GROUP BY l.id HAVING ROUND(l.line_total, 2) != ROUND(SUM(a.amount), 2)"
                ")"
            )
        ).scalar()
        problems += 0 if mismatch == 0 else 1
        print(
            f"  [{'ok' if mismatch == 0 else 'FAIL'}] line totals matching allocation sums: "
            f"{mismatch} mismatched"
        )

        print("\nEnvironment:")
        for var, critical in [
            # No longer critical: app/security.py falls back to a fixed dev
            # secret when this is unset, so tokens still survive a restart
            # without it -- fine for this training deployment's fake,
            # read-only data; set a real one only if that ever changes.
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

        max_suffix = _next_invoice_base(db) - 1
        print(f"\nHighest invoice number in use: INV-{max_suffix}")
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
            "allocations": db.query(InvoiceLineAllocation).delete(),
            "line items": db.query(InvoiceLineItem).delete(),
            "invoices": db.query(Invoice).delete(),
            "contacts": db.query(SupplierContact).delete(),
            "profiles": db.query(SupplierProfile).delete(),
            "suppliers": db.query(Supplier).delete(),
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
    seed_parser.add_argument("--suppliers", type=int, default=118)
    seed_parser.add_argument("--invoices", type=int, default=613)
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

    sub.add_parser("backfill", help="Add master data to rows that lack it")
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
        seed(args.suppliers, args.invoices, args.fresh, args.seed)
    elif args.command == "seed-users":
        seed_workshop_users(
            _read_members(args),
            args.prefix,
            args.reset,
            args.format,
            args.out,
            args.base_url,
        )
    elif args.command == "backfill":
        backfill()
    elif args.command == "doctor":
        sys.exit(doctor())
    elif args.command == "clear":
        clear()
    elif args.command == "auto-seed":
        auto_seed_on_start()


if __name__ == "__main__":
    main()
