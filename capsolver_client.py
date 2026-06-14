#!/usr/bin/env python3
"""CapSolver reCAPTCHA v3 token minting for the Upwork signup sitekey.

Used by the browserless curl_cffi signup flow to satisfy Upwork's
RECAPTCHA_SCORE_LESS_THAN_THRESHOLD gate on account creation.
"""
import os, time, requests

import config
CAPSOLVER_KEY = config.CAPSOLVER_KEY
SITEKEY = "6LcduVgpAAAAAA6ChpOLZlcgbRDN4evTya6_r1sM"
PAGE_URL = "https://www.upwork.com/nx/signup/"
API = "https://api.capsolver.com"


def balance() -> float:
    r = requests.post(f"{API}/getBalance", json={"clientKey": CAPSOLVER_KEY}, timeout=20).json()
    return r.get("balance", 0.0)


def recaptcha_v3(action: str = "signup", page_url: str = PAGE_URL,
                 timeout: int = 180, min_score: float = 0.7,
                 proxy: str | None = None, user_agent: str | None = None) -> str | None:
    """Return a fresh reCAPTCHA v3 ENTERPRISE token for the Upwork signup sitekey.

    Upwork uses grecaptcha.enterprise.execute(siteKey, {action:'signup'}), so the
    token MUST be solved as Enterprise with the correct action or the assessment is
    invalid -> "Score less than threshold".

    The v3 score is set at SOLVE time by the IP/browser reputation, so when *proxy*
    (a clean residential proxy) is supplied we use the proxied Enterprise task and
    Google scores the solve high. Without a proxy, CapSolver's datacenter IPs score
    low and Upwork rejects.
    """
    inner = {
        "websiteURL": page_url,
        "websiteKey": SITEKEY,
        "pageAction": action,
        "minScore": min_score,
    }
    # reCAPTCHA tokens are bound to the solving User-Agent; force CapSolver to solve
    # with the SAME UA we redeem with, else the assessment scores low.
    if user_agent:
        inner["userAgent"] = user_agent
    if proxy:
        inner["type"] = "ReCaptchaV3EnterpriseTask"
        inner["proxy"] = proxy
    else:
        inner["type"] = "ReCaptchaV3EnterpriseTaskProxyLess"
    task = {"clientKey": CAPSOLVER_KEY, "task": inner}
    r = requests.post(f"{API}/createTask", json=task, timeout=30).json()
    tid = r.get("taskId")
    if not tid:
        return None
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(3)
        g = requests.post(f"{API}/getTaskResult",
                          json={"clientKey": CAPSOLVER_KEY, "taskId": tid}, timeout=30).json()
        if g.get("status") == "ready":
            return g["solution"]["gRecaptchaResponse"]
        if g.get("status") != "processing":
            return None
    return None


if __name__ == "__main__":
    print("balance:", balance())
    tok = recaptcha_v3()
    print("token len:", len(tok) if tok else None)
