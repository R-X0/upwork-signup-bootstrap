#!/usr/bin/env python3
"""Open the signup tab EXACTLY like hybrid.py does, then HAND IT TO THE HUMAN.

Replicates the bot's launch precisely (warm chrome-run profile, real Chrome channel,
same args, Upwork session cleared but _GRECAPTCHA reputation kept, same ~90s warm-up,
lands on /nx/signup/?dest=home). Then it just idles — no fill, no clicks — so you can
drive the whole application manually from the bot's exact starting state."""
import asyncio, os, random
from patchright.async_api import async_playwright
import config

PROFILE = config.PROFILE  # chrome-run (same warm profile the bot reuses)
def log(m): print(f">>> {m}", flush=True)

async def dismiss_cookies(page):
    for sel in ["#onetrust-accept-btn-handler",'button:has-text("Accept All")','button:has-text("Accept")']:
        try:
            e=await page.query_selector(sel)
            if e and await e.is_visible(): await e.click(timeout=3000); await page.wait_for_timeout(500); return
        except Exception: pass
    try: await page.evaluate("()=>{for(const id of ['onetrust-banner-sdk','onetrust-consent-sdk']){const e=document.getElementById(id); if(e)e.remove();}}")
    except Exception: pass

async def main():
    log(f"profile {PROFILE} (warm/reused — identical to the bot)")
    async with async_playwright() as p:
        _args=dict(headless=False,
            args=["--disable-blink-features=AutomationControlled","--no-first-run","--no-default-browser-check","--start-maximized"],
            viewport=None, locale="en-US")
        try:
            ctx=await p.chromium.launch_persistent_context(PROFILE, channel="chrome", **_args)
            log("launched real Chrome (channel=chrome)")
        except Exception as e:
            log(f"channel=chrome unavailable ({e}); bundled Chromium")
            ctx=await p.chromium.launch_persistent_context(PROFILE, **_args)
        page=ctx.pages[0] if ctx.pages else await ctx.new_page()
        # log OUT of Upwork (clear only upwork.com cookies; keep google _GRECAPTCHA reputation)
        _out=False
        for dom in [".upwork.com","www.upwork.com","upwork.com"]:
            try: await ctx.clear_cookies(domain=dom); _out=True
            except Exception: pass
        if not _out:
            try: await page.goto("https://www.upwork.com/ab/account-security/logout",wait_until="domcontentloaded",timeout=30000); await page.wait_for_timeout(2000)
            except Exception: pass
        log(f"upwork session cleared (via_cookie_filter={_out}); reCAPTCHA reputation kept")
        # same ~90s warm-up the bot does
        log("warming profile (~90s) — DON'T touch yet...")
        for url in ["https://www.upwork.com/","https://www.upwork.com/nx/find-work/","https://www.upwork.com/freelance-jobs/"]:
            try: await page.goto(url,wait_until="domcontentloaded",timeout=45000)
            except Exception: pass
            await dismiss_cookies(page)
            for _ in range(6):
                await page.mouse.move(random.uniform(200,1100),random.uniform(200,700),steps=random.randint(10,20))
                await page.mouse.wheel(0,random.randint(200,600))
                await page.wait_for_timeout(random.randint(2500,5000))
        await page.goto("https://www.upwork.com/nx/signup/?dest=home",wait_until="domcontentloaded",timeout=60000)
        await page.wait_for_timeout(3000); await dismiss_cookies(page)
        log("================ READY — on the Sign up page. IT'S YOURS — go through it manually. ================")
        # idle forever; the human drives. (browser stays open)
        while True:
            await asyncio.sleep(5)

asyncio.run(main())
