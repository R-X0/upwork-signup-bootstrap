#!/usr/bin/env python3
"""One-shot finisher (Windows python). Logs back in, fills DOB+address, uploads
photo, rents a TextVerified number and enters it, screenshots the phone/verify
area, and stays open. Single process => no session loss. CDP on :9223 for follow-up."""
import asyncio, os, time
from patchright.async_api import async_playwright
from curl_cffi import requests as cffi

ROOT = r"C:\Users\Bona\upwork-signup"; CAP = os.path.join(ROOT, "cap")
PROFILE = os.path.join(ROOT, "chrome-profile"); AVATAR = os.path.join(CAP, "avatar.jpg")
EMAIL = "noah.jones.m0w7vx@eldenstats.com"; PW = "ALtB9!ndbxXz"
DOB = "05/14/1995"; ADDR = {"street": "1247 Maple Avenue", "city": "Austin", "state": "Texas", "zip": "78701"}

import config
TV_KEY = config.TV_API_KEY; TV_USER = config.TV_USER; TVB = config.TV_BASE


def tv_token():
    s = cffi.Session(impersonate="chrome")
    r = s.post(f"{TVB}/api/pub/v2/auth", headers={"X-API-KEY": TV_KEY, "X-API-USERNAME": TV_USER, "Accept": "application/json"}, timeout=30)
    return s, r.json()["token"]


def tv_create_number():
    s, tok = tv_token()
    h = {"Authorization": f"Bearer {tok}", "Accept": "application/json", "Content-Type": "application/json"}
    r = s.post(f"{TVB}/api/pub/v2/verifications", headers=h, json={"serviceName": "upwork", "capability": "sms"}, timeout=30)
    print("TV create:", r.status_code, r.text[:200], flush=True)
    href = r.json().get("href") or ""
    vid = href.rstrip("/").split("/")[-1]
    number = None
    for _ in range(20):
        v = s.get(f"{TVB}/api/pub/v2/verifications/{vid}", headers=h, timeout=30).json()
        number = v.get("number")
        if number:
            break
        time.sleep(3)
    return vid, number


async def fill_first(page, sels, value, typed=True):
    for sel in sels:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click(); await el.fill("")
                if typed:
                    await page.keyboard.type(value, delay=45)
                else:
                    await el.fill(value)
                return True
        except Exception:
            pass
    return False


async def click_text(page, *texts):
    for t in texts:
        el = await page.query_selector(f'button:has-text("{t}"), a:has-text("{t}")')
        if el and await el.is_visible() and await el.is_enabled():
            await el.click(); return t
    return None


async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            PROFILE, headless=False,
            args=["--remote-debugging-port=9223", "--disable-blink-features=AutomationControlled",
                  "--no-first-run", "--no-default-browser-check", "--start-maximized"],
            viewport=None, locale="en-US")
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://www.upwork.com/nx/create-profile/location", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        print("start url:", page.url, flush=True)

        # ---- login if needed ----
        if "login" in page.url:
            await fill_first(page, ["#login_username", 'input[name="login[username]"]', 'input[type=text]'], EMAIL)
            await click_text(page, "Continue")
            await page.wait_for_timeout(3500)
            await fill_first(page, ["#login_password", 'input[name="login[password]"]', 'input[type=password]'], PW)
            await page.screenshot(path=os.path.join(CAP, "login_pw.png"))
            await click_text(page, "Log in", "Continue")
            await page.wait_for_timeout(6000)
            print("after login url:", page.url, flush=True)
            await page.screenshot(path=os.path.join(CAP, "after_login.png"))
            if "create-profile" not in page.url:
                await page.goto("https://www.upwork.com/nx/create-profile/location", wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(4000)
        print("on:", page.url, flush=True)
        if "login" in page.url:
            await page.screenshot(path=os.path.join(CAP, "login_blocked.png"))
            print("LOGIN_FAILED (captcha?) — see login_blocked.png", flush=True)
            while True:
                await asyncio.sleep(5)

        # ---- fill DOB + address ----
        await fill_first(page, ['input[placeholder*="mm/dd" i]'], DOB)
        await fill_first(page, ['input[placeholder*="street" i]'], ADDR["street"])
        await fill_first(page, ['input[placeholder*="city" i]'], ADDR["city"])
        await fill_first(page, ['input[placeholder*="state" i]', 'input[placeholder*="province" i]'], ADDR["state"])
        await fill_first(page, ['input[placeholder*="zip" i]', 'input[placeholder*="postal" i]'], ADDR["zip"])
        print("dob+address filled", flush=True)

        # ---- photo ----
        try:
            finputs = await page.query_selector_all("input[type=file]")
            if finputs:
                await finputs[0].set_input_files(AVATAR)
                await page.wait_for_timeout(2500)
                await page.screenshot(path=os.path.join(CAP, "photo_modal.png"))
                await click_text(page, "Save", "Attach photo", "Apply", "Done")
                await page.wait_for_timeout(2000)
                print("photo uploaded", flush=True)
        except Exception as e:
            print("photo err", e, flush=True)

        # ---- TextVerified number ----
        vid, number = tv_create_number()
        print(f"TV vid={vid} number={number}", flush=True)
        open(os.path.join(CAP, "tv.txt"), "w").write(f"{vid}\n{number}\n")
        if number:
            digits = "".join(c for c in number if c.isdigit())
            if len(digits) == 11 and digits[0] == "1":
                digits = digits[1:]  # strip US country code for the national field
            await fill_first(page, ['input[type=tel]', 'input[placeholder*="phone" i]', 'input[name*="phone" i]'], digits)
            print("phone entered:", digits, flush=True)
        await page.wait_for_timeout(1500)
        await page.screenshot(path=os.path.join(CAP, "before_verify.png"), full_page=True)
        print("READY_AT_PHONE — filled everything; number in place. See before_verify.png", flush=True)
        while True:
            await asyncio.sleep(5)

asyncio.run(main())
