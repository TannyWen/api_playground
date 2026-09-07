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

## Checking you're hitting the right deployment

Run **C1 (`GET /v1/ping`)** and look at the response body:

```json
{
  "app_version": "2.1.0",
  "git_commit": null,
  "process_started_at": "2026-09-07T20:16:10Z",
  "uptime_seconds": 244
}
```

`uptime_seconds` resets to near-zero on every restart or redeploy — the
fastest way to confirm a just-pushed change actually landed, without needing
the Azure portal or Kudu. `git_commit` comes back `null` on this deployment
(Oryx's zip-deploy doesn't keep `.git`), so `app_version` + a low
`uptime_seconds` is the signal that actually works here.

## If a request shows no URL

You imported the collection but not into a workspace with the environment
selected, or the environment dropdown still says "No Environment". Every URL is
`{{base_url}}/...`, so without an environment there's nothing to resolve it to.

## Credentials

Both environments ship with `student` / `student-pass-123`. On Azure this
account is **created automatically on every server start** — nothing needs
seeding by hand, and it survives restarts: the same fixed dataset and the
same signing key come back every time, so a token or credential card handed
out before a restart is still good afterward.

For the workshop you'll be given your own username and password — put them in
the environment's `username` and `password` values, then clear `token` so the
next request logs in as you.

## If tokens expire mid-session

Tokens last 60 minutes by default. For a session longer than that, whoever is
running the API needs `ACCESS_TOKEN_EXPIRE_MINUTES` set (480 covers a
half-day) as an Azure App Setting — check with them if `GET /v1/whoami`'s
`token_expires_in_seconds` looks short.
