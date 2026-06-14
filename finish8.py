#!/usr/bin/env python3
"""Click 'Send code', poll TextVerified for the SMS code, enter it, verify."""
import asyncio, os, time
from patchright.async_api import async_playwright
from curl_cffi import requests as cffi

CAP = r"C:\Users\Bona\upwork-signup\cap"
import config
TV_KEY = config.TV_API_KEY; TV_USER = config.TV_USER; TVB = config.TV_BASE
VID = open(os.path.join(CAP, "tv.txt")).read().split("\n")[0].strip()


def tv_poll_code(tries=40, delay=5):
    s = cffi.Session(impersonate="chrome")
    tok = s.post(f"{TVB}/api/pub/v2/auth", headers={"X-API-KEY": TV_KEY, "X-API-USERNAME": TV_USER, "Accept": "application/json"}, timeout=30).json()["token"]
    h = {"Authorization": f"Bearer {tok}", "Accept": "application/json"}
    for i in range(tries):
        v = s.get(f"{TVB}/api/pub/v2/verifications/{VID}", headers=h, timeout=30).json()
        code = v.get("code")
        if code:
            return code
        # also check sms list
        try:
            sms = s.get(f"{TVB}/api/pub/v2/sms?reservationId={VID}", headers=h, timeout=30).json()
            data = sms.get("data") if isinstance(sms, dict) else sms
            if data:
                for m in data:
                    c = m.get("parsedCode") or m.get("code")
                    if c:
                        return c
        except Exception:
            pass
        print(f"  poll {i*delay}s: state={v.get('state')}", flush=True)
        time.sleep(delay)
    return None


async def main():
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp("http://localhost:9223")
        page = b.contexts[0].pages[-1]; await page.bring_to_front()
        sc = await page.query_selector('button:has-text("Send code")')
        if sc:
            await sc.click(); print("Send code clicked", flush=True)
            await page.wait_for_timeout(3000)
        await page.screenshot(path=os.path.join(CAP, "code_entry.png"))
        print("polling TextVerified for SMS code...", flush=True)
        code = tv_poll_code()
        print("CODE =", code, flush=True)
        if code:
            # enter code into the numeric/code input
            entered = False
            for sel in ["input[autocomplete=one-time-code]", "input[inputmode=numeric]", "input[name*=code i]", "input[maxlength='6']"]:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click(); await el.fill("")
                    for ch in str(code):
                        await page.keyboard.type(ch); await page.wait_for_timeout(120)
                    entered = True; print("code entered via", sel, flush=True); break
            await page.wait_for_timeout(1500)
            # click verify/confirm
            for t in ["Verify", "Confirm", "Submit", "Next", "Verify phone number", "Done"]:
                el = await page.query_selector(f'button:has-text("{t}")')
                if el and await el.is_visible() and await el.is_enabled():
                    await el.click(); print("verify-clicked", t, flush=True); break
            await page.wait_for_timeout(5000)
        await page.screenshot(path=os.path.join(CAP, "after_verify.png"), full_page=True)
        print("url:", page.url, flush=True)
        print("DONE finish8", flush=True)

asyncio.run(main())
