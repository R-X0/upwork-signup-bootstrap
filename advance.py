#!/usr/bin/env python3
"""Autopilot the Upwork freelancer onboarding toward the phone-number step.
Connects to the live logged-in browser over CDP (:9223). Each loop: detect a
phone-number field (STOP + report), else click Skip-for-now / Next / Continue /
primary button, and advance. Windows python.exe."""
import asyncio, os, sys
from patchright.async_api import async_playwright

CAP = r"C:\Users\Bona\upwork-signup\cap"
CDP = "http://localhost:9223"
MAX = int(sys.argv[1]) if len(sys.argv) > 1 else 25

PHONE_HINTS = ["input[type=tel]", "input[name*=phone i]", "input[id*=phone i]",
               "input[placeholder*=phone i]"]
ADVANCE_TEXTS = ["Skip for now", "Skip", "Next", "Continue", "Review your profile",
                 "Submit profile", "Looks good", "Get started", "Done"]


async def find_phone(page):
    for sel in PHONE_HINTS:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                return True
        except Exception:
            pass
    # text hint
    try:
        body = (await page.inner_text("body")).lower()
        if "phone number" in body and ("verify" in body or "add a phone" in body or "send code" in body):
            return True
    except Exception:
        pass
    return False


async def click_advance(page):
    for t in ADVANCE_TEXTS:
        try:
            el = await page.query_selector(f'button:has-text("{t}"), a:has-text("{t}")')
            if el and await el.is_visible() and await el.is_enabled():
                box = await el.bounding_box()
                if box:
                    await page.mouse.move(box["x"]+box["width"]/2, box["y"]+box["height"]/2, steps=12)
                    await page.wait_for_timeout(150)
                await el.click(timeout=4000)
                return t
        except Exception:
            continue
    return None


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        page = ctx.pages[-1]
        await page.bring_to_front()
        for i in range(MAX):
            await page.wait_for_timeout(1800)
            url = page.url
            if await find_phone(page):
                await page.screenshot(path=os.path.join(CAP, "PHONE_STEP.png"))
                print(f"PHONE_STEP_REACHED url={url}")
                return
            clicked = await click_advance(page)
            print(f"[{i}] url={url} clicked={clicked}")
            await page.screenshot(path=os.path.join(CAP, f"adv_{i:02d}.png"))
            if clicked is None:
                print("NO_ADVANCE_BUTTON — manual look needed")
                return
        print("MAX_STEPS reached without phone")

asyncio.run(main())
