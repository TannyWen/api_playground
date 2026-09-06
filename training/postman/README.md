# Postman setup

## Import

1. Open Postman → **Import** (top left)
2. Drag in all three files from this folder:
   - `API_Workshop.postman_collection.json` — the requests
   - `Workshop_local.postman_environment.json` — points at `http://127.0.0.1:8000`
   - `Workshop_azure.postman_environment.json` — points at the Azure host
3. Top right, pick the environment: **Workshop API (local)**

## Then

Open **1. Connection** and run **C1**. That's all the setup there is.

The bearer token is fetched automatically by a collection-level pre-request
script and refreshed when it expires — you never paste a token by hand. If you
want to see the login happen explicitly, run **C2b**.

## Reading the collection

Every request has a **description** — click the request name and read the
Documentation pane on the right. Those descriptions *are* the workbook: they say
what to look for and what question the request is answering.

Requests whose names end in `-> 422`, `-> 403`, `-> 503` and so on are
**supposed to fail**. That's the exercise.

Several requests write to the Postman **Console** (View → Show Postman Console,
or `Ctrl+Alt+C`). Keep it open — row counts, cursors and rate-limit budgets are
printed there.

## Folders

| Folder | What it covers |
|---|---|
| 1. Connection | Reach the API, get a token, understand 403 vs 401 |
| 2. Data structure | Read the contract, map the nesting, spot the type traps |
| 3. Pagination | Offset style and cursor style, side by side |
| 4. Flatten to files | Save two responses to disk, then move to VS Code |
| 5. Error handling | Every failure mode, deliberately triggered |

## Switching to Azure

Change the environment dropdown from **Workshop API (local)** to
**Workshop API (Azure)**. Nothing else changes — every request uses
`{{base_url}}`.

Two things to expect on Azure: the first call may take 20–30 seconds (cold
start — just send it again), and the URL has **no port number**, unlike local.

## If a request shows no URL

You imported the collection but not into a workspace with the environment
selected, or the environment dropdown still says "No Environment". Every URL is
`{{base_url}}/...`, so without an environment there's nothing to resolve it to.

## Credentials

The local environment ships with `student` / `student-pass-123`.

For the workshop you'll be given your own username and password — put them in
the environment's `username` and `password` values, then clear `token` so the
next request logs in as you.
