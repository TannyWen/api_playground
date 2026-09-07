<#
.SYNOPSIS
    Starts the Procurement Invoice API locally for the workshop.

.DESCRIPTION
    Checks the virtual environment, installs anything missing, seeds the
    database on first run, pins the JWT secret and token lifetime, and starts
    uvicorn in the foreground. Press Ctrl+C to stop.

    Pinning JWT_SECRET_KEY is the important part: without it the signing key is
    regenerated on every restart, so every token already issued stops working.

.EXAMPLE
    .\run_api.ps1
    Start on http://127.0.0.1:8000

.EXAMPLE
    .\run_api.ps1 -Reseed
    Wipe and rebuild the database first.

.EXAMPLE
    .\run_api.ps1 -Lan
    Also listen on the machine's LAN address, so others can reach it.

.EXAMPLE
    .\run_api.ps1 -Reload
    Auto-restart when a source file changes. Handy while developing, but it
    voids everyone's tokens on each restart -- do not use during a session.
#>
[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$Reseed,
    [switch]$Lan,
    [switch]$Reload,
    [int]$Suppliers = 118,
    [int]$Invoices = 613
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$DbPath = Join-Path $PSScriptRoot "procurement.db"

function Write-Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host "    $text" -ForegroundColor DarkGray }
function Write-Warn($text) { Write-Host "    $text" -ForegroundColor Yellow }

# Runs `python -c "import ..."` and returns $true/$false for whether it
# succeeded. A missing package makes Python print a traceback to stderr, which
# is expected here -- but under $ErrorActionPreference = "Stop", Windows
# PowerShell 5.1 wraps ANY native-process stderr output into a terminating
# ErrorRecord before a `2>$null` redirect gets a chance to discard it. So a
# plain `& $Python -c "..." 2>$null` crashes the whole script on a fresh venv
# instead of reporting "not installed yet" -- silencing EAP for just this one
# call is what actually lets the redirect do its job.
function Test-PythonImport($pythonExe, $importLine) {
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        & $pythonExe -c $importLine 2>$null
        return $LASTEXITCODE -eq 0
    } finally {
        $ErrorActionPreference = $prevEAP
    }
}

Write-Host "Procurement Invoice API - workshop launcher" -ForegroundColor White

# ---------------------------------------------------------------------------
# 1. Virtual environment
# ---------------------------------------------------------------------------
Write-Step "Checking the virtual environment"
if (-not (Test-Path $Python)) {
    Write-Warn "No .venv found. Creating one on Python 3.12..."
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    $py312 = (& py -3.12 -c "import sys; print(sys.executable)" 2>$null)
    $ErrorActionPreference = $prevEAP
    if (-not $py312) {
        Write-Host "    Python 3.12 was not found." -ForegroundColor Red
        Write-Host "    The pinned dependencies have no wheels for 3.13/3.14, so 3.12 is required." -ForegroundColor Red
        Write-Host "    Install it from the Microsoft Store or python.org, then re-run." -ForegroundColor Red
        exit 1
    }
    & py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { Write-Host "    venv creation failed." -ForegroundColor Red; exit 1 }
}

$version = & $Python --version
Write-Ok "$version"
if ($version -notmatch "3\.12") {
    Write-Warn "Expected Python 3.12 (runtime.txt pins it). Dependency installs may fail."
}

# ---------------------------------------------------------------------------
# 2. Dependencies
# ---------------------------------------------------------------------------
Write-Step "Checking dependencies"
if (-not (Test-PythonImport $Python "import fastapi, pydantic, sqlalchemy, jwt, faker")) {
    Write-Warn "Installing from requirements.txt (this takes a minute)..."
    & $Python -m pip install --upgrade pip --quiet
    & $Python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { Write-Host "    Install failed." -ForegroundColor Red; exit 1 }
}
Write-Ok "server dependencies present"

if (Test-PythonImport $Python "import requests, pandas") {
    Write-Ok "participant dependencies present (requests, pandas)"
} else {
    Write-Warn "pandas/requests missing - needed only for the Python exercises."
    Write-Warn "Install with:  .\.venv\Scripts\python.exe -m pip install -r requirements-training.txt"
}

# ---------------------------------------------------------------------------
# 3. Environment -- pin the secret and the token lifetime
# ---------------------------------------------------------------------------
Write-Step "Setting environment"

# A fixed development secret. It only needs to be STABLE, not secret, for local
# use: what matters is that restarting the server does not invalidate tokens
# people are already holding. On Azure, set a real random value as an App
# Setting instead.
if (-not $env:JWT_SECRET_KEY) {
    $env:JWT_SECRET_KEY = "workshop-local-dev-secret-do-not-use-in-production-0a1b2c3d"
    Write-Ok "JWT_SECRET_KEY pinned (local dev value)"
} else {
    Write-Ok "JWT_SECRET_KEY already set in this shell - using yours"
}

if (-not $env:ACCESS_TOKEN_EXPIRE_MINUTES) {
    $env:ACCESS_TOKEN_EXPIRE_MINUTES = "480"
}
Write-Ok "token lifetime: $($env:ACCESS_TOKEN_EXPIRE_MINUTES) minutes"

# ---------------------------------------------------------------------------
# 4. Database
# ---------------------------------------------------------------------------
Write-Step "Checking the database"
if ($Reseed) {
    Write-Warn "-Reseed given: wiping and rebuilding..."
    & $Python manage.py seed --fresh --suppliers $Suppliers --invoices $Invoices --seed 20260903
    if ($LASTEXITCODE -ne 0) { Write-Host "    Seed failed." -ForegroundColor Red; exit 1 }
}
elseif (-not (Test-Path $DbPath)) {
    Write-Warn "No database yet. Seeding $Suppliers suppliers and $Invoices invoices..."
    & $Python manage.py seed --fresh --suppliers $Suppliers --invoices $Invoices --seed 20260903
    if ($LASTEXITCODE -ne 0) { Write-Host "    Seed failed." -ForegroundColor Red; exit 1 }
}
else {
    $sizeKb = [math]::Round((Get-Item $DbPath).Length / 1KB)
    Write-Ok "procurement.db present ($sizeKb KB). Use -Reseed to rebuild."
}

# ---------------------------------------------------------------------------
# 5. Where to point Postman
# ---------------------------------------------------------------------------
$bindHost = if ($Lan) { "0.0.0.0" } else { "127.0.0.1" }
$localUrl = "http://127.0.0.1:$Port"

Write-Step "Starting the API"
Write-Host ""
Write-Host "  Local URL      " -NoNewline -ForegroundColor DarkGray
Write-Host $localUrl -ForegroundColor Green
Write-Host "  Interactive docs " -NoNewline -ForegroundColor DarkGray
Write-Host "$localUrl/docs" -ForegroundColor Green
Write-Host "  Start here     " -NoNewline -ForegroundColor DarkGray
Write-Host "$localUrl/v1/ping" -ForegroundColor Green

if ($Lan) {
    $ips = Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
        Select-Object -ExpandProperty IPAddress
    foreach ($ip in $ips) {
        Write-Host "  LAN URL        " -NoNewline -ForegroundColor DarkGray
        Write-Host "http://${ip}:$Port" -ForegroundColor Green
    }
    Write-Warn "If others cannot reach it, Windows Firewall is the usual cause:"
    Write-Warn "  New-NetFirewallRule -DisplayName 'Workshop API' -Direction Inbound ``"
    Write-Warn "    -LocalPort $Port -Protocol TCP -Action Allow -Profile Private"
}

Write-Host ""
Write-Host "  Postman: import training\postman\*.json, pick the 'Workshop API (local)'" -ForegroundColor DarkGray
Write-Host "           environment, then run 'Connection / C1'. The token is automatic." -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Test credentials: student / student-pass-123" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

$uvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", $bindHost, "--port", "$Port")
if ($Reload) {
    Write-Warn "-Reload is on: each restart invalidates every issued token. Fine for"
    Write-Warn "development, but never during a live session."
    $uvicornArgs += "--reload"
}

& $Python @uvicornArgs
