#!/usr/bin/env python3
"""TextVerified V2 API client — rent a US number to receive Upwork's SMS code.
API is Cloudflare-fronted, so use curl_cffi. Auth needs X-API-KEY + X-API-USERNAME."""
import os, time
from curl_cffi import requests as cffi

import config
API_KEY = config.TV_API_KEY
USERNAME = config.TV_USER
B = config.TV_BASE

_session = cffi.Session(impersonate="chrome")
_token = {"v": None, "exp": 0}


def _auth():
    if _token["v"] and time.time() < _token["exp"] - 30:
        return _token["v"]
    r = _session.post(f"{B}/api/pub/v2/auth",
                      headers={"X-API-KEY": API_KEY, "X-API-USERNAME": USERNAME,
                               "Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    j = r.json()
    _token["v"] = j["token"]
    _token["exp"] = time.time() + 3000  # ~50 min; tokens last ~1h
    return _token["v"]


def _h(extra=None):
    h = {"Authorization": f"Bearer {_auth()}", "Accept": "application/json",
         "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


def get(path):
    return _session.get(B + path, headers=_h(), timeout=30)


def account():
    return get("/api/pub/v2/account/me").json()


def find_service(keyword="upwork"):
    r = get("/api/pub/v2/services?numberType=mobile&reservationType=verification")
    svcs = r.json()
    kw = keyword.lower()
    hits = [s for s in svcs if kw in str(s.get("serviceName", "")).lower()]
    return hits, len(svcs)


def create_verification(service_name="upwork"):
    body = {"serviceName": service_name, "capability": "sms"}
    r = _session.post(f"{B}/api/pub/v2/verifications", headers=_h(),
                      json=body, timeout=30)
    return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text)


def get_verification(vid):
    return get(f"/api/pub/v2/verifications/{vid}").json()


def poll_sms(vid, tries=60, delay=5):
    """Poll the verification until an SMS code arrives."""
    for _ in range(tries):
        v = get_verification(vid)
        # the code shows up on the verification or via /sms
        code = v.get("code") or (v.get("sms") or {}).get("code")
        if code:
            return code, v
        time.sleep(delay)
    return None, None


if __name__ == "__main__":
    print("account:", account())
    hits, total = find_service("upwork")
    print(f"services total={total}; upwork matches:", hits[:5])
