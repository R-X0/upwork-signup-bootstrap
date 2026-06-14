#!/usr/bin/env python3
"""Fill the stubborn City field via real keystrokes, then click Review your profile
and capture the verification step. CDP attach."""
import asyncio, os
from patchright.async_api import async_playwright
CAP = r"C:\Users\Bona\upwork-signup\cap"


async def main():
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp("http://localhost:9223")
        page = b.contexts[0].pages[-1]
        await page.bring_to_front()
        sel = 'input[placeholder*="city" i]'
        for attempt in range(3):
            el = await page.query_selector(sel)
            await el.click()
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Delete")
            for ch in "Austin":
                await page.keyboard.type(ch)
                await page.wait_for_timeout(110)
            await page.wait_for_timeout(900)
            val = await page.input_value(sel)
            print(f"attempt {attempt}: city='{val}'", flush=True)
            if val.strip():
                break
        await page.screenshot(path=os.path.join(CAP, "all_filled.png"))

        # click Review your profile
        rv = await page.query_selector('button:has-text("Review your profile"), a:has-text("Review your profile")')
        if rv:
            await rv.click()
            print("clicked Review your profile", flush=True)
            await page.wait_for_timeout(6000)
        print("url after review:", page.url, flush=True)
        await page.screenshot(path=os.path.join(CAP, "review_page.png"), full_page=True)
        # look for phone verification / SMS code UI
        body = (await page.inner_text("body")).lower()
        for kw in ["verify", "code", "we sent", "enter the", "phone"]:
            if kw in body:
                print("HINT:", kw, flush=True)
        print("DONE finish5", flush=True)

asyncio.run(main())
