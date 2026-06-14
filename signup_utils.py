"""Pure helpers shared by the signup flows — no browser, no network, so they are
unit-testable. Behaviour matches the inline versions previously copy-pasted across
autorun.py / hybrid.py, with one addition: classify_signup_state() lets the flow
detect a reCAPTCHA-rejected click (code 83) instead of silently waiting forever.
"""
import re

# A successful "Create my account" click lands on one of these.
CREATED_URL_MARKERS = (
    "verify-email",
    "please-verify",
    "create-profile",
    "account-security",
    "/nx/onboarding",
)

# reCAPTCHA v3 Enterprise rejection of the register mutation.
REJECTED_BODY_MARKERS = (
    "score less than threshold",
    '"code":83',
    '"code": 83',
    "code 83",
)

_VERIFY_RE = re.compile(
    r'https?://www\.upwork\.com/nx/signup/verify-email/token/[^\s"<>\)\]]+'
)


def dequote_printable(raw: str) -> str:
    """Undo the quoted-printable soft-wraps Upwork's MIME email uses so the
    verify URL is contiguous again."""
    return raw.replace("=\r\n", "").replace("=\n", "").replace("=3D", "=")


def extract_verify_link(raw: str):
    """Return the Upwork verify-email link from a raw MIME email body, or None."""
    if not raw:
        return None
    flat = dequote_printable(raw)
    m = _VERIFY_RE.findall(flat)
    return m[0].rstrip("=") if m else None


def normalize_phone(number) -> str:
    """Strip to digits; drop a US country-code leading '1' from an 11-digit number."""
    digits = "".join(c for c in (number or "") if c.isdigit())
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    return digits


def parse_sms_code(payload):
    """Pull a verification code out of a TextVerified SMS payload.

    Accepts either the verification object ({'code': ...}) or the /sms list
    response ({'data': [{'parsedCode'|'code': ...}]} or a bare list).
    Returns the code string or None.
    """
    if payload is None:
        return None
    if isinstance(payload, dict):
        if payload.get("code"):
            return str(payload["code"])
        nested = payload.get("sms")
        if isinstance(nested, dict) and (nested.get("parsedCode") or nested.get("code")):
            return str(nested.get("parsedCode") or nested.get("code"))
        data = payload.get("data", payload)
    else:
        data = payload
    if isinstance(data, list):
        for m in data:
            if isinstance(m, dict) and (m.get("parsedCode") or m.get("code")):
                return str(m.get("parsedCode") or m.get("code"))
    return None


def classify_signup_state(url: str, body: str = "") -> str:
    """Decide what happened after the 'Create my account' click.

    Returns:
      'created'  — account exists, the flow can take over (email verify -> onboarding)
      'rejected' — reCAPTCHA scored the click below threshold (code 83); human should re-click
      'waiting'  — still on the form, nothing decided yet
    """
    u = (url or "").lower()
    b = (body or "").lower()
    if any(mk in u for mk in CREATED_URL_MARKERS):
        return "created"
    if any(mk in b for mk in REJECTED_BODY_MARKERS):
        return "rejected"
    return "waiting"
