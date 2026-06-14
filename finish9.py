#!/usr/bin/env python3
"""Rent a FRESH TextVerified number, swap it into the verify modal, click Send code,
and poll immediately (within the reservation window). Enter the code + verify."""
import asyncio, os, time
from patchright.async_api import async_playwright
from curl_cffi import requests as cffi

CAP = r"C:\Users\Bona\upwork-signup\cap"
import config
TV_KEY = config.TV_API_KEY; TV_USER = config.TV_USER; TVB = config.TV_BASE


def tv_session():
    s = cffi.Session(impersonate="chrome")
    tok = s.post(f"{TVB}/api/pub/v2/auth", headers={"X-API-KEY": TV_KEY, "X-API-USERNAME": TV_USER, "Accept": "application/json"}, timeout=30).json()["token"]
    return s, {"Authorization": f"Bearer {tok}", "Accept": "application/json", "Content-Type": "application/json"}


def tv_new_number(s, h):
    r = s.post(f"{TVB}/api/pub/v2/verifications", headers=h, json={"serviceName": "upwork", "capability": "sms"}, timeout=30)
    vid = r.json()["href"].rstrip("/").split("/")[-1]
    for _ in range(20):
        v = s.get(f"{TVB}/api/pub/v2/verifications/{vid}", headers=h, timeout=30).json()
        if v.get("number"):
            return vid, v["number"]
        time.sleep(3)
    return vid, None


def tv_poll(s, h, vid, tries=36, delay=5):
    for i in range(tries):
        v = s.get(f"{TVB}/api/pub/v2/verifications/{vid}", headers=h, timeout=30).json()
        if v.get("code"):
            return v["code"]
        try:
            sms = s.get(f"{TVB}/api/pub/v2/sms?reservationId={vid}", headers=h, timeout=30).json()
            data = sms.get("data") if isinstance(sms, dict) else sms
            for m in (data or []):
                if m.get("parsedCode") or m.get("code"):
                    return m.get("parsedCode") or m.get("code")
        except Exception:
            pass
        print(f"  poll {i*delay}s state={v.get('state')}", flush=True)
        time.sleep(delay)
    return None


async def main():
    s, h = tv_session()
    vid, number = tv_new_number(s, h)
    digits = "".join(c for c in (number or "") if c.isdigit())
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    print(f"FRESH vid={vid} number={number} digits={digits}", flush=True)
    open(os.path.join(CAP, "tv.txt"), "w").write(f"{vid}\n{number}\n")

    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp("http://localhost:9223")
        page = b.contexts[0].pages[-1]; await page.bring_to_front()
        # swap number in the modal's tel input
        tel = await page.query_selector('input[type=tel]')
        await tel.click(); await page.keyboard.press("Control+A"); await page.keyboard.press("Delete")
        for ch in digits:
            await page.keyboard.type(ch); await page.wait_for_timeout(60)
        await page.wait_for_timeout(800)
        print("number swapped", flush=True)
        sc = await page.query_selector('button:has-text("Send code")')
        if sc and await sc.is_enabled():
            await sc.click(); print("Send code clicked", flush=True)
        await page.wait_for_timeout(3000)
        await page.screenshot(path=os.path.join(CAP, "code_entry.png"))
        print("polling fresh reservation...", flush=True)
        code = tv_poll(s, h, vid)
        print("CODE =", code, flush=True)
        if code:
            for sel in ["input[autocomplete=one-time-code]", "input[inputmode=numeric]", "input[name*=code i]", "input[maxlength='6']"]:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click(); await el.fill("")
                    for ch in str(code):
                        await page.keyboard.type(ch); await page.wait_for_timeout(120)
                    print("code entered via", sel, flush=True); break
            await page.wait_for_timeout(1500)
            for t in ["Verify", "Confirm", "Submit", "Next", "Done"]:
                el = await page.query_selector(f'button:has-text("{t}")')
                if el and await el.is_visible() and await el.is_enabled():
                    await el.click(); print("verify-clicked", t, flush=True); break
            await page.wait_for_timeout(6000)
        await page.screenshot(path=os.path.join(CAP, "after_verify.png"), full_page=True)
        print("url:", page.url, flush=True)
        print("DONE finish9", flush=True)

asyncio.run(main())
