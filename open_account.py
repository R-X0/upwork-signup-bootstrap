#!/usr/bin/env python3
"""Open an already-created account in a browser so you can see it logged in.
Uses a SEPARATE 'chrome-view' profile so it never collides with hybrid.py's
warm creation profile. Brief warm-up first so login reCAPTCHA passes."""
import asyncio, os, random, sys
from patchright.async_api import async_playwright
import config
PROFILE=config.PROFILE+"-view"
# creds via argv only — no creds in source. If omitted, fall back to the most recent
# account in the gitignored ledger (cap/accounts.jsonl).
def _last_ledger_account():
    try:
        import json
        last=None
        with open(os.path.join(config.CAP,"accounts.jsonl"),encoding="utf-8") as fh:
            for line in fh:
                if line.strip(): last=json.loads(line)
        if last: return last.get("email"), last.get("password")
    except Exception: pass
    return None, None
if len(sys.argv)>2:
    EMAIL,PW=sys.argv[1],sys.argv[2]
else:
    EMAIL,PW=_last_ledger_account()
    if not EMAIL:
        print("usage: python3 open_account.py <email> <password>  (or populate cap/accounts.jsonl)"); sys.exit(1)

def log(m): print(f">>> {m}", flush=True)

async def fill_first(page, sels, value):
    for sel in sels:
        try:
            el=await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click(); await el.fill(""); await el.fill(value); return True
        except Exception: pass
    return False

async def click_text(page,*texts):
    for t in texts:
        el=await page.query_selector(f'button:has-text("{t}"), a:has-text("{t}")')
        if el and await el.is_visible() and await el.is_enabled(): await el.click(); return t
    return None

async def main():
    log(f"opening account {EMAIL}")
    async with async_playwright() as p:
        _args=dict(headless=False,args=["--disable-blink-features=AutomationControlled","--no-first-run","--no-default-browser-check","--start-maximized"],viewport=None,locale="en-US")
        try: ctx=await p.chromium.launch_persistent_context(PROFILE,channel="chrome",**_args)
        except Exception: ctx=await p.chromium.launch_persistent_context(PROFILE,**_args)
        page=ctx.pages[0] if ctx.pages else await ctx.new_page()
        # brief warm-up so the login reCAPTCHA scores ok on this view profile
        try:
            await page.goto("https://www.upwork.com/",wait_until="domcontentloaded",timeout=45000)
            for _ in range(4):
                await page.mouse.move(random.uniform(200,1100),random.uniform(200,700),steps=random.randint(10,18))
                await page.mouse.wheel(0,random.randint(200,500)); await page.wait_for_timeout(random.randint(1500,2500))
        except Exception: pass
        await page.goto("https://www.upwork.com/ab/account-security/login",wait_until="domcontentloaded",timeout=60000)
        await page.wait_for_timeout(3000)
        await fill_first(page,["#login_username",'input[name="login[username]"]','input[type=email]','input[type=text]'],EMAIL)
        await click_text(page,"Continue"); await page.wait_for_timeout(4000)
        await fill_first(page,["#login_password",'input[name="login[password]"]','input[type=password]'],PW)
        await click_text(page,"Log in","Continue"); await page.wait_for_timeout(7000)
        log(f"after login url={page.url}")
        if "login" in page.url:
            log("LOGIN may need a manual step (reCAPTCHA/checkpoint) — the window is open for you.")
        else:
            log("LOGGED IN — explore the account in the open window.")
        await page.screenshot(path=os.path.join(config.CAP,"view_account.png"),full_page=True)
        while True: await asyncio.sleep(5)

asyncio.run(main())
