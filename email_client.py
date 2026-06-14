#!/usr/bin/env python3
"""eldenstats.com Cloudflare catch-all email reader.

Any address *@eldenstats.com is captured by the Cloudflare Worker. We poll it to
read the verification email and extract Upwork's verify-email token link / code.
"""
import os, re, time, random, string, requests

WORKER = os.environ.get("EMAIL_WORKER", "https://email-worker.eldenstats-email.workers.dev")
DOMAIN = os.environ.get("EMAIL_DOMAIN", "eldenstats.com")


def new_address(first: str, last: str) -> str:
    tag = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{first.lower()}.{last.lower()}.{tag}@{DOMAIN}"


def get_raw(email: str) -> str | None:
    try:
        r = requests.get(f"{WORKER}/debug", params={"email": email}, timeout=8)
        return r.json().get("rawContent")
    except Exception:
        return None


def get_code(email: str) -> str | None:
    try:
        r = requests.get(f"{WORKER}/code", params={"email": email}, timeout=8).json()
        return r.get("code")
    except Exception:
        return None


_LINK_PATTERNS = [
    r'https?://(?:www\.)?upwork\.com/[^\s"<>]*verify-email[^\s"<>]*',
    r'https?://(?:www\.)?upwork\.com/[^\s"<>]*token[^\s"<>]*',
    r'https?://(?:www\.)?upwork\.com/[^\s"<>]{20,}',
]


def wait_verify_link(email: str, tries: int = 60, delay: float = 2.0) -> str | None:
    """Poll the worker until Upwork's verification link arrives; return cleaned URL."""
    for _ in range(tries):
        raw = get_raw(email)
        if raw:
            for pat in _LINK_PATTERNS:
                m = re.findall(pat, raw)
                if m:
                    return (m[0].replace("=\n", "").replace("=3D", "=")
                            .replace("3D", "").rstrip('>)]=\n\r '))
        time.sleep(delay)
    return None


if __name__ == "__main__":
    import sys
    e = sys.argv[1] if len(sys.argv) > 1 else new_address("test", "user")
    print("addr:", e)
    print("raw:", (get_raw(e) or "")[:200])
