#!/usr/bin/env python3
"""Browserless Upwork freelancer signup — curl_cffi (TLS-impersonate Chrome),
the same method as upwork-intel. No browser, no GPU, no Cloudflare.

Flow (reverse-engineered from a one-time capture):
  1. GET /nx/signup/?dest=home          -> visitor cookies + visitor_signup_gql_token (bearer)
  2. CapSolver reCAPTCHA v3 token        -> satisfies the "Score less than threshold" gate
  3. POST /api/graphql/v1?alias=gql-mutation-register  with the captured RegisterUserRequestInput
  4. poll eldenstats worker -> GET verify-email token link  (email confirmed)
  5. onboarding ... -> phone step  (where the SMS API gets hooked up)

Run:  python3 upwork_signup.py
"""
from __future__ import annotations
import json, random, string, time, sys, os, uuid, secrets
from curl_cffi import requests as cffi

sys.path.insert(0, os.path.dirname(__file__))
import capsolver_client as cap
import email_client as mail

# IPRoyal residential proxy (sticky session) — clean US IP so reCAPTCHA scores high.
# Credentials are env-only now (never hardcode secrets — set IPROYAL_USER/PASS in .env).
IPROYAL_USER = os.environ.get("IPROYAL_USER", "")
IPROYAL_PASS = os.environ.get("IPROYAL_PASS", "")
IPROYAL_CC = os.environ.get("IPROYAL_COUNTRY", "us")


IPROYAL_HOST, IPROYAL_PORT = "geo.iproyal.com", "12321"


def iproyal_session(sess: str | None = None):
    """Return (curl_cffi_url, capsolver_str) for one sticky residential session."""
    sess = sess or secrets.token_hex(4)
    pw = f"{IPROYAL_PASS}_country-{IPROYAL_CC}_session-{sess}_lifetime-8m"
    curl_url = f"http://{IPROYAL_USER}:{pw}@{IPROYAL_HOST}:{IPROYAL_PORT}"
    # CapSolver wants  proxyType:host:port:user:pass  (NOT a URL)
    capsolver_str = f"http:{IPROYAL_HOST}:{IPROYAL_PORT}:{IPROYAL_USER}:{pw}"
    return curl_url, capsolver_str

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
SIGNUP_PAGE = "https://www.upwork.com/nx/signup/?dest=home"
GQL = "https://www.upwork.com/api/graphql/v1?alias=gql-mutation-register"

FIRST = ["James","Emma","Liam","Olivia","Noah","Ava","Ethan","Sophia","Mason","Mia",
         "Lucas","Charlotte","Henry","Amelia","Benjamin","Harper","Sebastian","Evelyn"]
LAST  = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Wilson",
         "Anderson","Taylor","Thomas","Moore","Martin","Lee","Thompson","White","Harris"]

REGISTER_QUERY = ("\nmutation ($inputData: RegisterUserRequestInput) {\n"
                  "  register(input: $inputData) {\n    success\n    user\n  }\n}\n")


def rand_password() -> str:
    return ("".join(random.choices(string.ascii_uppercase, k=2))
            + "".join(random.choices(string.ascii_lowercase, k=5))
            + str(random.randint(10, 99)) + random.choice("!@#$"))


def new_session(proxy=None):
    s = cffi.Session(impersonate="chrome")
    if proxy:
        s.proxies = {"http": proxy, "https": proxy}
    r = s.get(SIGNUP_PAGE, headers={"user-agent": UA}, timeout=45)
    jar = {c.name: c.value for c in s.cookies.jar}
    bearer = jar.get("visitor_signup_gql_token")
    return s, jar, bearer, r.status_code


def register(action="signup", use_proxy=True, verbose=True):
    curl_proxy = capsolver_proxy = None
    if use_proxy:
        curl_proxy, capsolver_proxy = iproyal_session()
        if verbose:
            print(f"[0] residential proxy session (IPRoyal {IPROYAL_CC})")
    s, jar, bearer, page_status = new_session(proxy=curl_proxy)
    if verbose:
        print(f"[1] signup page {page_status} | bearer={'yes' if bearer else 'NO'} | "
              f"visitor_id={jar.get('visitor_id','?')}")
    if not bearer:
        print("    ! no visitor_signup_gql_token cookie — abort"); return None

    fn, ln = random.choice(FIRST), random.choice(LAST)
    email = mail.new_address(fn, ln)
    pw = rand_password()
    if verbose:
        print(f"[2] solving reCAPTCHA v3 (action={action}) for {fn} {ln} <{email}>")
    token = cap.recaptcha_v3(action=action, proxy=capsolver_proxy)
    if not token:
        print("    ! CapSolver failed"); return None
    if verbose:
        print(f"    token ok ({len(token)} chars)")

    input_data = {
        "flowName": "freelancer_high_potential",
        "standalone": True,
        "recaptchaToken": token,
        "invitationUid": None,
        "inviteToken": None,
        "useVerificationCodeForEmail": None,
        "queryParams": {
            "userAgent": UA,
            "referral": SIGNUP_PAGE,
            "invitationKey": None, "secretKey": None, "directContractId": None,
        },
        "userAccount": {
            "firstName": fn, "lastName": ln, "email": email,
            "country": "United States", "timezone": "-08:00,1", "password": pw,
            "termsAccepted": True, "promotionalEmailOptIn": True,
            "landingPage": None, "companyName": None, "username": None,
            "idToken": None, "ssoProvider": None, "ssoUserId": None,
            "ssoVendorClientId": None, "googleImageUrl": None,
        },
    }
    visitor_id = jar.get("visitor_id", "")
    headers = {
        "accept": "*/*",
        "accept-language": "en-US",
        "authorization": f"Bearer {bearer}",
        "content-type": "application/json",
        "origin": "https://www.upwork.com",
        "referer": SIGNUP_PAGE,
        "user-agent": UA,
        "x-upwork-accept-language": "en-US",
        "x-correlation-id": str(uuid.uuid4()),
        "vnd-eo-visitorid": visitor_id,
        "vnd-eo-trace-id": uuid.uuid4().hex[:16] + "-LAX",
        "vnd-eo-span-id": str(uuid.uuid4()),
        "vnd-eo-parent-span-id": str(uuid.uuid4()),
    }
    body = json.dumps({"query": REGISTER_QUERY, "variables": {"inputData": input_data}})
    if verbose:
        print("[3] POST gql-mutation-register …")
    r = s.post(GQL, data=body, headers=headers, timeout=45)  # session already carries proxy
    try:
        j = r.json()
    except Exception:
        print(f"    HTTP {r.status_code} non-JSON: {r.text[:200]}"); return None

    errs = j.get("errors")
    if errs:
        msg = errs[0].get("message"); code = errs[0].get("extensions", {}).get("code")
        print(f"    ✗ register error: {msg} (code {code})")
        return {"ok": False, "error": msg, "code": code, "email": email, "pw": pw,
                "session": s, "raw": j}
    data = (j.get("data") or {}).get("register") or {}
    if data.get("success"):
        print(f"    ✓ ACCOUNT CREATED — {email} / {pw}")
        return {"ok": True, "email": email, "pw": pw, "user": data.get("user"),
                "session": s, "raw": j}
    print(f"    ? unexpected: {json.dumps(j)[:300]}")
    return {"ok": False, "email": email, "pw": pw, "session": s, "raw": j}


if __name__ == "__main__":
    act = sys.argv[1] if len(sys.argv) > 1 else "register"
    res = register(action=act)
    if res and res.get("ok"):
        print("\n[4] waiting for verification email …")
        link = mail.wait_verify_link(res["email"], tries=40, delay=2)
        if link:
            print("    verify link:", link[:90])
            res["session"].get(link, headers={"user-agent": UA}, timeout=30, allow_redirects=True)
            print("    ✓ email verified")
        else:
            print("    ! no verify email yet")
