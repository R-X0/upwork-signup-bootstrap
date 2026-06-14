"""Central config / secrets loader.

All runtime secrets are read from the environment. A local `.env` (gitignored)
is loaded with OVERRIDE semantics so a stale shell-exported var can never silently
shadow what you put in `.env`. There are NO secret literals in source anymore —
put real values in `.env` (see `.env.example`).
"""
import os


def _load_dotenv(path: str = ".env", override: bool = True) -> None:
    """Dependency-free .env loader. Sets os.environ from KEY=VALUE lines.

    override=True matches our house rule: values in .env win over a stale shell env.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    full = path if os.path.isabs(path) else os.path.join(here, path)
    if not os.path.exists(full):
        return
    try:
        with open(full, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and (override or key not in os.environ):
                    os.environ[key] = val
    except Exception:
        pass


_load_dotenv()


def _req(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# --- TextVerified (phone/SMS) ---
TV_API_KEY = _req("TV_API_KEY")
TV_USER = _req("TV_USER")
TV_BASE = _req("TV_BASE", "https://www.textverified.com")

# --- CapSolver (reCAPTCHA token minting; research only) ---
CAPSOLVER_KEY = _req("CAPSOLVER_KEY")

# --- eldenstats email worker ---
EMAIL_WORKER = _req("EMAIL_WORKER", "https://email-worker.eldenstats-email.workers.dev")
EMAIL_DOMAIN = _req("EMAIL_DOMAIN", "eldenstats.com")

# --- Upwork signup ---
SIGNUP_URL = _req("SIGNUP_URL", "https://www.upwork.com/nx/signup/?dest=home")
RECAPTCHA_SITEKEY = _req("RECAPTCHA_SITEKEY")

# --- paths (cross-platform; no Windows/user hardcoding) ---
# Default everything to the repo directory so it runs on Mac/Linux/Windows for any
# user. Override any of these with env vars if you want them elsewhere.
_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = _req("UPWORK_BOT_ROOT", _HERE)
CAP = _req("UPWORK_BOT_CAP", os.path.join(ROOT, "cap"))
PROFILE = _req("UPWORK_BOT_PROFILE", os.path.join(ROOT, "chrome-run"))
FACE = _req("UPWORK_BOT_FACE", os.path.join(CAP, "face.jpg"))
try:
    os.makedirs(CAP, exist_ok=True)
    os.makedirs(PROFILE, exist_ok=True)
except Exception:
    pass


def require(*names: str) -> None:
    """Raise if any named env var is empty — call at the top of an entrypoint
    so a missing key fails loudly instead of as a confusing 401 mid-run.
    Checks the environment only; a baked-in default does NOT satisfy require()."""
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise SystemExit(
            f"Missing required config: {', '.join(missing)}. "
            f"Copy .env.example to .env and fill it in."
        )
