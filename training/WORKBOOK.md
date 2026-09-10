# API Workshop — Participant Workbook

**Thursday 13:00–15:00**

You'll extract data from a real API: connect to it, work out the shape of what
it returns, page through it, save it, and flatten it into tables you could load
somewhere. Then you'll make your code survive the API failing.

That's the whole arc — the same one you'd follow against any vendor API.

**No prior API experience needed.** If you get stuck, ask — being stuck on
challenge 1 while someone else is on challenge 9 is completely normal and not a
measure of anything.

---

## Before you start

You should have, from the pre-session email:

- **Postman** installed
- **VS Code** with the Python extension
- `.\.venv\Scripts\python.exe -m pip install -r requirements-training.txt` done (`requests`, `pandas`)
- The workshop folder on your machine

You'll be handed a **card with your username and password**.

### Set up Postman (2 minutes)

1. **File -> Import** → drag in all three files from `training/postman/`
![alt text](image.png)
2. Environment dropdown, top right → **Workshop API (local)** (or **Azure**, whichever you're told)
3. Click the eye icon 👁 next to it (it can also look like a bunch of lines with an 'X') → **Edit** → put your own `username` and `password` in the **Current value** column → save

> **The Initial vs Current value thing.** The variables table has two value
> columns. *Current value* is what actually gets sent and stays on your machine.
> *Initial value* is what travels if the file is shared. Put your credentials in
> **Current value**. This confuses everyone the first time.

4. Open **View → Show Postman Console** (`Ctrl+Alt+C`) and leave it open. Several requests print useful things there.

Then open folder **1. Connection** and run **C1**.

The bearer token is fetched automatically — you never paste one.

### A note on the requests

Every request has a **description** — click its name and read the Documentation
pane on the right. Those descriptions are part of this workbook.

**Requests whose names end in `-> 422` or `-> 503` are supposed to fail.** That
is the exercise, not a broken collection.

---

## 1. Connection · 13:10–13:30

*Postman. The goal is to reach the API and prove who you are — and to learn to
tell those two problems apart.*

### C1 — Reach the API

Run **C1  GET /v1/ping**. No token needed.

**Done when:** you get `200` and `{"status": "ok", ...}`.

If it fails, work down this list before touching anything else:

| Symptom | Likely cause |
|---|---|
| Could not send request / connection refused | Wrong host or port. Local needs `:8000`; Azure must **not** have a port |
| Hangs, then times out | On Azure, the first call can take 20–30s (cold start). Send it again |
| SSL error | You used `https://` against local, or `http://` against Azure |
| Works in a browser but not Postman | A proxy is intercepting. Flag it |

**Question to answer:** why does this endpoint need no token at all? What would
you lose if it did?

### C2 — Get a token

Run **C2a** first. It sends your credentials as JSON and **fails with 422**.

Read the error body before moving on. It says `username` and `password` are
missing — even though you sent both.

Now run **C2b**. Identical credentials, sent as form fields. `200`, and you get
an `access_token`.

**Done when:** you have a token, *and* you can explain why C2a failed.

**Hint:** look at the `Content-Type` header each one sends, and where the server
was looking for those fields.

**Hint 2:** Google what error code 422 means.

**Why this matters:** "the API rejected my credentials" and "the API never
received my credentials" produce a similar-looking failure and have completely
different fixes.

**Note:** Error codes like (422, 429, 503, 500, etc.) are simply conventions and no API provider is forced to respect them. 
Google's rapid ratings API, for instance, would return error 500 in the exact same case in which this API would return 422. Could you guess why?

### C3 — Use the token, and read two rejections

Run these three in order and note the status code of each:

| Request | What it sends | Status |
|---|---|---|
| **C3a** | no `Authorization` header at all | ? |
| **C3b** | `Authorization: Bearer this-is-not-a-real-token` | ? |
| **C3c** | a valid token | ? |

**Tip:** In Postman, you can hover over the value of one of the parameters in a header or body and click "Variables in request" in order to see the actual value.

**Done when:** you can say, in your own words, which code means *"you didn't
present credentials"* and which means *"you presented credentials and they were
rejected"*.

**Then look at C3c's response body.** Find `token_expires_in_seconds`. Work out
the wall-clock time your token dies.

Write it on your card. If requests start failing later, this is the first thing
to check.

---

## 2. Data structure · 13:30–13:45

*Now that you can read the data, work out its shape — before writing any code
against it. This is the part people skip and then regret.*

### D1 — Read the contract

Open **{{base_url}}/docs** in a browser. That's the API documenting itself.

Find `POST /v1/invoices/search` and expand its response schema. Then run **D1**
to see the same thing as raw JSON (`/openapi.json`) — that's the
machine-readable version a code generator would consume.

**Done when:** you have a written list of the fields on one invoice, with the
JSON type of each.

### D2 — Map the nesting

Run **D2  GET /v1/invoices/{number}** — one invoice, fully expanded.

Sketch its structure. Mark each level with its cardinality — is it one-to-one or
one-to-many?

```
invoice
├── supplier            (one per invoice, or many?)
│   └── address
└── line_items[]        (how many?)
    └── allocations[]   (how many per line?)
```

**Done when:** your sketch is right, and you can answer: **how many rows would a
single fully-flattened table have for this one invoice?**

(Check the Postman Console — D2 prints the answer, so you can see if you were
right.)

### D3 — Map the types, and find the traps

Build a table: for every field, the JSON type, the pandas dtype you'd expect,
and the SQL type you'd land it in.

| Field | JSON type | pandas dtype | SQL type |
|---|---|---|---|
| `invoice_number` | string | object | VARCHAR(40) |
| `total_amount` | ? | ? | ? |
| `issue_date` | ? | ? | ? |
| `status` | ? | ? | ? |
| `notes` | ? | ? | ? |
| `quantity` | ? | ? | ? |

**There are four traps in that list.** Find them.

**Hints, one per trap:**
- Look *very* carefully at how `total_amount` is written in the JSON. Is it a number?
- `issue_date` and `created_at` are not the same kind of thing.
- `status` only ever takes a small fixed set of values. How many? (`/docs` will tell you.)
- One field is sometimes absent. What does that do to a column's type?

**Done when:** your table has all four traps identified. **This table is the
thing you'll actually reuse at work** — it's the same exercise for any API.

---

## 3. Pagination · 13:45–14:05

*APIs don't hand you everything at once. Two different styles here, because
you'll meet both.*

### P1 — Offset pagination, by hand

Run **P1a** (`limit=5&offset=0`). Look at the `page` object in the response.

Then, **before running P1b** — predict what `has_more` and `next_offset` will
be. Then run it and check.

Run **P1c** (offset past the end). It returns `200` with an empty list, **not**
a 404.

**Done when:** you can explain why "no results" is a success, not an error — and
what your extraction code would do differently in each case.

Run **P1d** (`limit=999`) → `422`. **Read the cap out of the error body**, not
out of the docs. That's what you'd have to do against a real API.

### P2 — Cursor pagination, by hand

Run **P2a**. Note two things in `page`:
- `next_cursor` — an opaque token
- `estimated_total` — a count

Run **P2b** (it uses the cursor P2a saved for you). Look at `estimated_total`
now.

**It's `null`.**

**Done when:** you can explain why you *cannot* calculate the number of pages up
front, and what the only correct stopping condition is.

Run **P2c** (a broken cursor) → `400`, not `422`. Why the different code? The
request shape was fine; the *value* was meaningless.

**Curiosity, optional:** the cursor is base64-encoded JSON. Decode one. It's
less magic than it looks.

### P3 — Drain every page, in Python

Switch to VS Code. Open **`training/starters/01_pagination.py`**.

The connection is already written. Your job is the loop.

```powershell
python training/starters/01_pagination.py
```

**Done when:** you've collected **every** invoice, and can prove it:
- your count matches `estimated_total` from page 1
- every `invoice_id` is unique (a `set` is your friend)

**Two hints:**
- Stop when `next_cursor` is `None`. Not when a page looks short — the last full page looks identical to a middle one.
- Don't divide `estimated_total` by `page_size`. You saw why in P2b.

---

## 4. Flatten to files · 14:05–14:35

*The longest block, and the part that transfers most directly to real work.*

### F1 — Save a response, then flatten it

In Postman, run **F1** (folder 4). Then use the **Save Response** dropdown at
the top right of the response pane → **Save to a file** → put it in
`training/data/`.

Open it in VS Code. Note that what you saved is the **whole response** — the
rows are nested inside `items`, not at the top level.

> Pre-saved copies are already in `training/data/samples/` if you'd rather not
> wait, or if your connection is still misbehaving. Nobody should be blocked
> here.

Now open **`training/starters/02_flatten.py`** and do TODO 1: one row per
supplier, written to CSV.

**Done when:** your CSV has exactly one row per supplier, and `address.city` is
a real column.

**Notice:** `address` became dotted columns. `contacts` did **not**. Why are
those two treated differently? That difference is the whole point of the next
challenge.

### F2 — One row per line item

TODO 2 in the same file.

You need one row per **line item**, each carrying its invoice's context
(`invoice_number`, `status`, the supplier code).

`pd.json_normalize` takes:
- `record_path=["line_items"]` — the array to explode
- `meta=["invoice_number", ...]` — parent fields to carry down
- for a nested parent field, pass a list: `["supplier", "supplier_code"]`

**Done when:** your row count equals the total number of line items. Work that
number out from the raw JSON and `assert` it.

### F3 — One row per allocation, and reconcile

TODO 3 and 4 — the real one.

Go one level deeper: one row per **allocation**, still carrying the line context
(`description`, `quantity`, `line_total`).

**Try `record_path=["line_items", "allocations"]` first.** It reaches the
allocations but silently drops everything at the line level. Seeing that fail is
worth more than being told.

The working approach starts from your F2 frame:
```python
exploded = lines_df.explode("allocations", ignore_index=True)
allocation_cols = pd.json_normalize(exploded["allocations"])
# ... then glue them side by side with pd.concat
```

**Then TODO 4 — the reconciliation.** For each line, the allocation amounts
should sum to exactly that line's `line_total`.

Before you check, run this:
```python
print(lines_df["line_total"].dtype)
print(lines_df["line_total"].sum())
```

**Done when:** every line reconciles with **exactly zero** variance. Not nearly
zero — exactly.

**Hint if your sum looks insane:** look again at what `.dtype` told you, and at
trap #1 from challenge D3.

---

## 5. Error handling · 14:35–14:55

*Everything above assumed the API works. It won't always. This is what separates
a script that ran once from one you'd schedule.*

### E1 — Provoke errors and read them properly

Open **`training/starters/03_error_handling.py`**. One broken request is already
written for you.

Run it, then work through TODOs 1–2. Use Postman folder **5** to trigger each
one interactively if that's easier.

Build this table:

| Status | What it means | Would retrying help? |
|---|---|---|
| 401 | | |
| 403 | | |
| 404 | | |
| 422 | | |
| 429 | | |
| 503 | | |

**Done when:** the table is filled in, and your Python prints the `request_id`
from the error body.

**Why `request_id` matters:** it's the one thing that lets whoever runs the API
find *your* failed call in their logs. Quote it in the ticket and you get a real
answer; describe the error in prose and you get twenty questions.

### E2 — Retry what's worth retrying

`GET /v1/unstable/invoices` fails roughly every third call, on purpose, with
`503` and a `Retry-After` header.

TODO 3: write a retry loop that succeeds anyway.

Three things to get right:
- Wait longer between attempts each time (0.25s, 0.5s, 1s, 2s…) rather than hammering
- Add a little randomness to the wait. Ten people retrying in lockstep is its own outage
- If the response carries `Retry-After`, **use that number**. The server is telling you the answer; guessing is both slower and ruder

**Done when:** 20 extracts give 20 successes.

### E3 — Fail fast on what can never succeed

Your loop from E2 will happily retry *anything*. That's wrong.

A `422` means your request is malformed. Waiting and sending the identical
request again will fail identically — five times, slowly.

TODO 4: write

```python
def should_retry(status: int) -> bool:
    ...
```

Decide for 401, 404, 422, 429, 500, 503.

**Rule of thumb:** is the problem at your end or theirs — and could waiting
plausibly change the outcome?

**Done when:** a `422` fails in milliseconds instead of after five attempts.
Time it and prove it.

**Then look back at any error body:** there's a `retryable` field. The server
was telling you all along. Real APIs mostly don't, which is why you needed to
reason it out first.

---

## Before 15:00

You should be leaving with three things. Bring them to the recap:

1. **Your type-mapping table** from D3, with the four traps identified
2. **Three CSVs** at three different grains, with a reconciliation that balances
3. **Your status-code table** from E1

---

## Stretch — if you're ahead

Not on the clock. All of these work.

**C4** Add a collection-level script that refreshes your token automatically —
then look at how the shipped collection already does it.

**C5** Ask the instructor to restart the server. Your token stops working. Why?
And what does that tell you about where the token's validity actually lives?

**D4** Write the `CREATE TABLE` DDL for your three flat files — with primary and
foreign keys. Would your CSVs actually load into it?

**D5** Compare the supplier record from `/v1/master-data/suppliers` with the
`supplier` object embedded inside an invoice. Which fields are in one but not
the other? Why would an embedded copy ever disagree with the master record?

**P4** Every response carries `x-ratelimit-remaining`. Make your drain loop slow
down when the budget runs low, so you're never throttled at all.

**P5** Re-run the same cursor twice. Same rows? Now imagine an invoice is
created halfway through a 25-page extract. What does offset pagination do that
cursor pagination doesn't?

**F4** Combine all 25 pages into one dataset, de-duplicate, and write three
join-clean CSVs.

**E4** Hit `/v1/unstable/throttled-invoices` until you get `429`, then make your
client honour `Retry-After` exactly.

---

## Quick reference

| Thing | Where |
|---|---|
| Interactive docs | `{{base_url}}/docs` |
| Machine-readable contract | `{{base_url}}/openapi.json` |
| Is it up? | `{{base_url}}/v1/ping` |
| Who am I? | `{{base_url}}/v1/whoami` |
| Pre-saved responses | `training/data/samples/` |
| Your starters | `training/starters/` |
| Postman console | `Ctrl+Alt+C` |

**Endpoints**

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/ping` | No auth |
| POST | `/v1/auth/token` | **Form-encoded**, not JSON |
| GET | `/v1/whoami` | Auth. Token expiry lives here |
| GET | `/v1/master-data/suppliers` | Offset pagination, `limit` max 50 |
| POST | `/v1/invoices/search` | Cursor pagination, `page_size` max 25 |
| GET | `/v1/invoices/{invoice_number}` | By business key |
| GET | `/v1/unstable/invoices` | Fails ~1 in 3, on purpose |
| GET | `/v1/unstable/throttled-invoices` | Tight rate limit, on purpose |
