# upwork-signup-bot

Automated Upwork **freelancer** account creation + full profile onboarding, end-to-end,
using a maximally-undetected stealth browser (SeleniumBase UC mode)
+ the eldenstats.com Cloudflare catch-all email. Reverse-engineered and built against the
live `nx/signup` + `create-profile` flow.

One clean session does: **create account → auto-pass reCAPTCHA → verify email → run the
create-profile wizard → Close-Account bypass (skips phone verification) → save the account
to a Postgres database**.

---

## 🚀 One command on a brand-new Windows machine

Open **cmd.exe** (or PowerShell) on a fresh Windows box with *nothing* installed and paste a
single command. It installs Python + Google Chrome, downloads this bot, installs deps, creates
one account, and saves it to the Postgres database:

```bat
powershell -ExecutionPolicy Bypass -Command "$env:DATABASE_URL='postgresql://USER:PASS@HOST:PORT/railway'; irm https://raw.githubusercontent.com/R-X0/upwork-signup-bootstrap/main/bootstrap.ps1 | iex"
```

- Replace the `DATABASE_URL` with your Railway Postgres **public** connection string.
- Optional env vars (set before the `irm`): `RUN_COUNT` (accounts to create in a row),
  `HOLD_OPEN_SEC` (browser hold time), `DO_PHONE=1` (re-enable TextVerified phone — needs `TV_*`).
- Created accounts are saved to Postgres **and** a local `cap/accounts.jsonl`. View them with
  `\.venv\Scripts\python.exe view_accounts.py`.

> The default pipeline **bypasses phone verification** (the Close-Account escape), so a run
> needs only `DATABASE_URL` — no TextVerified/CapSolver keys.

---

## Accounts database

Every run records the account (email, password, name, status, final URL, machine, run id, and
a JSONB `extra`) via `account_store.record()` → `db.py` → Postgres. The table is auto-created.
`status` progresses `started → created → verified → onboarding_bypassed` (or an error state).
Set `DATABASE_URL` (or `DATABASE_PUBLIC_URL`) in `.env`; without it, runs still save locally.

---

## TL;DR — running it

```bash
# full pipeline: create + verify + full profile onboarding (NO phone):
python3 hybrid.py

# same, but also do the phone/SMS step (rents ONE TextVerified number):
ONBOARD_PHONE=1 python3 hybrid.py

# iterate on ONBOARDING ONLY against an already-created account (no re-creation):
python3 onboard.py <email> <password> [--phone]
```

---

## reCAPTCHA v3 Enterprise — SOLVED (no human click needed)

> ⚠️ This supersedes older notes that said only a human hardware click works.

The `register` mutation is gated by reCAPTCHA v3 Enterprise (action `signup`); an automated
click used to score below threshold → `{message:"Score less than threshold", code:83}`.

**It now auto-passes**, reliably (verified across many consecutive runs, `code=None`), via:
- **Warm, reused profile** (`chrome-run/`): reCAPTCHA reputation (cookies + history)
  accumulates across runs. At start the bot clears only `upwork.com` cookies (logout) so the
  signup form renders, while keeping the Google `_GRECAPTCHA` reputation cookie.
- **Humanized interaction**: ~90s profile warm-up, per-character typing (`htype`), and a real
  mouse-trajectory click (`hmove_click`). A synthetic `element.click()` (`isTrusted=false`)
  is the #1 thing that floors the score — never use it for submit.
- **`REGISTER_RESP` listener** reads the verdict from the GraphQL network response (not the
  page body), so the loop detects success / `code 83` instantly instead of hanging 20 min.

Tradeoff: all accounts share `chrome-run/`'s device fingerprint + your IP, so Upwork can
**link** them (see the phone-gate wall below). To unlink, give each run its own residential
proxy + fresh profile (which then needs CapSolver/warming to pass reCAPTCHA again).

---

## The pipeline

1. **Create** (`hybrid.py`) — warm profile, logout, humanized fill, auto-click, handles both
   signup-chooser A/B variants (thumbnail button vs radio + "Create Account").
2. **Verify email** — always runs (post-signup URL is `registration-success`; create-profile
   bounces to `please-verify` until the emailed link is opened). Link comes from the
   eldenstats Email Worker.
3. **Onboarding** — `onboard.py::run_onboarding()`, imported by `hybrid.py` so it's one
   session. Every step guarded; final step runs **exactly once** (`_DONE`/`_TV_STATE`) so
   re-entry can't corrupt fields or double-rent:
   resume-import ("Fill out manually") · categories + specialty checkboxes · skill typeahead ·
   title · bio · `$0.00` rate · languages ("Fluent", visible-combobox guard) ·
   **location (10/10)**: address-first + `focus()` (so keystrokes don't leak into the DOB
   field under the date-picker), Google-Places select via type→ArrowDown/Enter, city/state/zip,
   photo via `[data-qa=open-loader]`→file input→"Attach photo", DOB last + close calendar ·
   phone (TextVerified rent → fill `input[type=tel]` → Review → SMS).
4. **Ledger** — every account is appended to **`cap/accounts.jsonl`** (gitignored) at creation
   and final status (`run_creds.txt` is overwritten each run; the ledger is the durable record):
   `ts, email, password, first, last, status, final_url, phone, tv_vid`.

---

## ⚠️ Known wall: phone verification is blocked for multi-account clusters

Creation, email verification, and the **entire** onboarding work. The **only** step that
doesn't complete is **phone verification — and it's not a code issue**, it's Upwork's
anti-fraud.

Creating many accounts from the **same profile + same IP** in a short window flags the
cluster. The phone step then shows:

> **"Phone verification isn't available right now. Complete the required steps on your
> account to continue."**

…and **no SMS is ever sent** (TextVerified stays `verificationPending`) — Upwork rejects the
account *before* dispatching the code. **Verified live:** a brand-new, never-touched account
created from the same profile/IP hits this **identically** → it's the **device/IP/cluster**
that's flagged, not any single (over-used) account.

- A **real (non-VOIP) mobile number does NOT fix it** — the block is upstream of the number.
- Each extra account from this profile/IP **deepens** the flag (toward a hardware-level block).
- To get an account that can publish/submit proposals: **fresh device + fresh network (not
  this IP) + a real mobile number + matching identity**, created slowly. Multi-account on one
  machine is a losing game vs. Upwork's current (post‑March‑2026, Incognia) detection.

---

## Files

| File | Purpose |
|------|---------|
| `hybrid.py` | **Main pipeline**: create → verify → `run_onboarding()` → phone (`ONBOARD_PHONE=1`) |
| `hybrid_full_backup.py` | Backup of `hybrid.py` **with the full inline onboarding kept** — fallback if the `onboard` import path ever breaks |
| `onboard.py` | `run_onboarding()` (shared wizard driver) + standalone login-and-onboard tester (`--phone`) |
| `signup_utils.py` | pure helpers: verify-link extraction, phone/SMS parse, `classify_signup_state()` (detects `code 83`) — tested by `test_utils.py` |
| `capsolver_client.py` | reCAPTCHA v3 Enterprise token minting (needs a residential proxy to score; **not** used by the warm-profile native path) |
| `textverified_client.py` / `email_client.py` | TextVerified V2 + eldenstats worker clients |
| `email-worker/` | patched Cloudflare Email Worker (stores full raw email so link-based verifications work; `wrangler deploy`) |
| `config.py` | `.env` loader + cross-platform paths |
| `autorun.py` | legacy one-shot end-to-end (reference) |
| `cap/` | screenshots, `accounts.jsonl` ledger, `face.jpg` (creds/profiles gitignored) |

## Config / secrets

Runtime keys read from a gitignored `.env` via `config.py` — **no secret literals in source**.
Copy `.env.example` → `.env`: `TV_API_KEY`, `TV_USER`, `EMAIL_WORKER`, `EMAIL_DOMAIN`,
optional `CAPSOLVER_KEY`/`RECAPTCHA_SITEKEY`. Loaded with override semantics; an entrypoint
calls `config.require("TV_API_KEY","TV_USER")` so a missing key fails loudly. Working dirs
default to the repo (`cap/`, `chrome-run/`), overridable via `UPWORK_BOT_*` env vars.
Plaintext creds (`accounts.jsonl`, `run_creds.txt`, `creds.txt`, `tv.txt`) and Chrome
profiles (`chrome-run*/`) are gitignored — **never pushed**.

## Caveats

Evading Upwork's bot defense / creating multiple accounts may violate Upwork's Terms
regardless of whether it works technically. For authorized testing/research only.
