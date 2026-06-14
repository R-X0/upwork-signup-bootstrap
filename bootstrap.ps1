<#
  Upwork signup bot — ONE-COMMAND bootstrap for a brand-new Windows machine.

  Run from cmd.exe or PowerShell (nothing pre-installed required):

    powershell -ExecutionPolicy Bypass -Command "$env:DATABASE_URL='postgresql://...'; irm https://raw.githubusercontent.com/R-X0/upwork-signup-bootstrap/main/bootstrap.ps1 | iex"

  It will: install Python + Google Chrome (if missing) -> download the bot ->
  create a venv + install deps -> write .env -> run one signup -> the created
  account is saved to the Postgres database (and a local cap/accounts.jsonl).

  Optional env vars you can set before the `irm` call:
    $env:DATABASE_URL   (REQUIRED) Postgres connection string accounts are saved to
    $env:DO_PHONE       set to "1" to also do TextVerified phone (needs TV_* keys)
    $env:HOLD_OPEN_SEC  seconds to keep the browser open at the end (default 20)
    $env:RUN_COUNT      how many accounts to create in a row (default 1)
#>

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13 -bor [Net.ServicePointManager]::SecurityProtocol

$REPO_ZIP = 'https://github.com/R-X0/upwork-signup-bootstrap/archive/refs/heads/main.zip'
$DEST     = Join-Path $env:USERPROFILE 'upwork-signup-bot'

function Say($m) { Write-Host ">>> $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "!!! $m" -ForegroundColor Yellow }

# --- 0. sanity: DATABASE_URL ---------------------------------------------------
if (-not $env:DATABASE_URL) {
  Warn "DATABASE_URL is not set. The account will only be saved locally (cap/accounts.jsonl), NOT to Postgres."
  Warn "Re-run with:  `$env:DATABASE_URL='postgresql://...'; irm <url> | iex"
}

# --- helpers -------------------------------------------------------------------
function Have-Cmd($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }

function Find-Python {
  foreach ($c in @('python','python3')) {
    if (Have-Cmd $c) {
      try { & $c --version *> $null; if ($LASTEXITCODE -eq 0) { return (Get-Command $c).Source } } catch {}
    }
  }
  if (Have-Cmd 'py') { try { $p = & py -3 -c "import sys;print(sys.executable)" 2>$null; if ($p) { return $p.Trim() } } catch {} }
  $globs = @(
    "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
    "$env:ProgramFiles\Python3*\python.exe",
    "${env:ProgramFiles(x86)}\Python3*\python.exe"
  )
  foreach ($g in $globs) {
    $hit = Get-ChildItem $g -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
    if ($hit) { return $hit.FullName }
  }
  return $null
}

function Install-Python {
  Say "Installing Python 3.12 ..."
  if (Have-Cmd 'winget') {
    try {
      winget install -e --id Python.Python.3.12 --silent --accept-source-agreements --accept-package-agreements --scope user
    } catch { Warn "winget python failed: $_" }
  }
  if (-not (Find-Python)) {
    Say "winget unavailable/failed — downloading the official Python installer ..."
    $url = 'https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe'
    $exe = Join-Path $env:TEMP 'python-install.exe'
    Invoke-WebRequest $url -OutFile $exe
    Start-Process $exe -ArgumentList '/quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1' -Wait
  }
  $p = Find-Python
  if (-not $p) { throw "Python install failed — install Python 3.12 manually from python.org then re-run." }
  Say "Python: $p"
  return $p
}

function Find-Chrome {
  $paths = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
  )
  foreach ($p in $paths) { if (Test-Path $p) { return $p } }
  return $null
}

function Install-Chrome {
  if (Find-Chrome) { Say "Chrome already installed."; return }
  Say "Installing Google Chrome ..."
  if (Have-Cmd 'winget') {
    try { winget install -e --id Google.Chrome --silent --accept-source-agreements --accept-package-agreements } catch { Warn "winget chrome failed: $_" }
  }
  if (-not (Find-Chrome)) {
    Say "winget unavailable/failed — downloading the Chrome installer ..."
    $url = 'https://dl.google.com/chrome/install/standalonesetup64.exe'
    $exe = Join-Path $env:TEMP 'chrome-install.exe'
    Invoke-WebRequest $url -OutFile $exe
    Start-Process $exe -ArgumentList '/silent /install' -Wait
  }
  if (Find-Chrome) { Say "Chrome ready." } else { Warn "Chrome not detected — UC mode needs Chrome. Install it manually if the run fails." }
}

# --- 1. Python -----------------------------------------------------------------
$PY = Find-Python
if (-not $PY) { $PY = Install-Python } else { Say "Python: $PY" }

# --- 2. Chrome -----------------------------------------------------------------
Install-Chrome

# --- 3. download the bot -------------------------------------------------------
Say "Downloading the bot to $DEST ..."
$zip = Join-Path $env:TEMP 'upwork-signup-bot.zip'
Invoke-WebRequest $REPO_ZIP -OutFile $zip
$tmpx = Join-Path $env:TEMP ('usb_' + [guid]::NewGuid().ToString('N'))
Expand-Archive -Path $zip -DestinationPath $tmpx -Force
$inner = Get-ChildItem $tmpx -Directory | Select-Object -First 1   # <repo>-main
New-Item -ItemType Directory -Force -Path $DEST | Out-Null
Copy-Item (Join-Path $inner.FullName '*') $DEST -Recurse -Force
Remove-Item $tmpx, $zip -Recurse -Force -ErrorAction SilentlyContinue
Set-Location $DEST

# --- 4. venv + deps ------------------------------------------------------------
$venvPy = Join-Path $DEST '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
  Say "Creating virtual environment ..."
  & $PY -m venv .venv
}
if (-not (Test-Path $venvPy)) { throw "venv creation failed." }
Say "Installing Python dependencies (this can take a few minutes) ..."
& $venvPy -m pip install --upgrade pip *> $null
& $venvPy -m pip install -r requirements.txt

# --- 5. write .env -------------------------------------------------------------
Say "Writing .env ..."
$lines = @()
if ($env:DATABASE_URL) { $lines += "DATABASE_URL=$($env:DATABASE_URL)" }
if ($env:TV_API_KEY)   { $lines += "TV_API_KEY=$($env:TV_API_KEY)" }
if ($env:TV_USER)      { $lines += "TV_USER=$($env:TV_USER)" }
if ($env:EMAIL_WORKER) { $lines += "EMAIL_WORKER=$($env:EMAIL_WORKER)" }
if ($env:EMAIL_DOMAIN) { $lines += "EMAIL_DOMAIN=$($env:EMAIL_DOMAIN)" }
Set-Content -Path (Join-Path $DEST '.env') -Value ($lines -join "`n") -Encoding ASCII

if (-not $env:HOLD_OPEN_SEC) { $env:HOLD_OPEN_SEC = '20' }

# --- 6. run --------------------------------------------------------------------
$runs = 1
if ($env:RUN_COUNT) { [int]::TryParse($env:RUN_COUNT, [ref]$runs) | Out-Null; if ($runs -lt 1) { $runs = 1 } }
$phoneArg = @(); if ($env:DO_PHONE -eq '1') { $phoneArg = @('--phone') }

for ($i = 1; $i -le $runs; $i++) {
  Say "=== signup run $i / $runs ==="
  & $venvPy sb_signup.py @phoneArg
}

Say "All done. View saved accounts with:  $venvPy view_accounts.py"
