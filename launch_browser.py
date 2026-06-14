#!/usr/bin/env python3
"""Launch a headed, stealth Chromium (Windows, visible) that stays alive with
CDP exposed on :9223. Drive it from drive.py via connect_over_cdp (same host)."""
import asyncio, os
from patchright.async_api import async_playwright

PROFILE = r"C:\Users\Bona\upwork-signup\chrome-profile"
START_URL = "https://www.upwork.com/nx/signup/?dest=home"

STEALTH_JS = r"""
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}, app: {}};
Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
"""

async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            PROFILE,
            headless=False,
            args=[
                "--remote-debugging-port=9223",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--start-maximized",
            ],
            viewport=None,
            locale="en-US",
        )
        await ctx.add_init_script(STEALTH_JS)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(START_URL, wait_until="domcontentloaded", timeout=60000)
        print("BROWSER UP on CDP :9223 — page:", page.url, flush=True)
        while True:
            await asyncio.sleep(5)

asyncio.run(main())
