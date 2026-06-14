"""Unit tests for the pure signup helpers. Run: python3 test_utils.py
No browser, no network, no Upwork interaction — pure logic only."""
from signup_utils import (
    extract_verify_link,
    normalize_phone,
    parse_sms_code,
    classify_signup_state,
)

PASS = 0
FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}\n       got = {got!r}\n       want= {want!r}")


# --- extract_verify_link ---------------------------------------------------
RAW_EMAIL = (
    "Content-Type: text/html\r\n\r\n"
    "<a href=3D\"https://www.upwork.com/nx/signup/verify-email/token/abc12=\r\n"
    "3DEF456ghi\">Verify your email</a>\r\n"
)
check("verify link: quoted-printable de-wrapped",
      extract_verify_link(RAW_EMAIL),
      "https://www.upwork.com/nx/signup/verify-email/token/abc123DEF456ghi")
check("verify link: none in body", extract_verify_link("no link here"), None)
check("verify link: empty", extract_verify_link(""), None)
check("verify link: trailing = stripped",
      extract_verify_link("x https://www.upwork.com/nx/signup/verify-email/token/tok123= y"),
      "https://www.upwork.com/nx/signup/verify-email/token/tok123")

# --- normalize_phone -------------------------------------------------------
check("phone: 11-digit US strips leading 1", normalize_phone("+1 (512) 555-0143"), "5125550143")
check("phone: 10-digit untouched", normalize_phone("5125550143"), "5125550143")
check("phone: letters stripped", normalize_phone("tel:512-555-0143"), "5125550143")
check("phone: none", normalize_phone(None), "")
check("phone: 11-digit not starting with 1 kept", normalize_phone("25125550143"), "25125550143")

# --- parse_sms_code --------------------------------------------------------
check("sms: verification obj code", parse_sms_code({"code": "123456"}), "123456")
check("sms: /sms list parsedCode", parse_sms_code({"data": [{"parsedCode": "654321"}]}), "654321")
check("sms: bare list code", parse_sms_code([{"code": "111222"}]), "111222")
check("sms: int coerced to str", parse_sms_code({"code": 999888}), "999888")
check("sms: nested sms dict code", parse_sms_code({"sms": {"code": "707070"}}), "707070")
check("sms: nested sms parsedCode", parse_sms_code({"sms": {"parsedCode": "808080"}}), "808080")
check("sms: empty -> None", parse_sms_code({"data": []}), None)
check("sms: nested empty sms -> None", parse_sms_code({"sms": {}}), None)
check("sms: none -> None", parse_sms_code(None), None)

# --- classify_signup_state -------------------------------------------------
check("state: created via create-profile url",
      classify_signup_state("https://www.upwork.com/nx/create-profile/", ""), "created")
check("state: created via please-verify url",
      classify_signup_state("https://www.upwork.com/nx/signup/please-verify", ""), "created")
check("state: rejected via score body",
      classify_signup_state("https://www.upwork.com/nx/signup/", "Score less than threshold"), "rejected")
check("state: rejected via code 83 json",
      classify_signup_state("https://www.upwork.com/nx/signup/", '{"errors":[{"code":83}]}'), "rejected")
check("state: waiting when still on form",
      classify_signup_state("https://www.upwork.com/nx/signup/", "create my account"), "waiting")
check("state: created wins over body",
      classify_signup_state("https://www.upwork.com/nx/create-profile/", "score less than threshold"), "created")


print(f"\n{PASS} passed, {FAIL} failed")
raise SystemExit(1 if FAIL else 0)
