#!/usr/bin/env python3
"""Final create-profile page: fill DOB + random US address, upload photo,
screenshot the phone area. Owns the browser directly (no CDP)."""
import asyncio, os
from patchright.async_api import async_playwright

ROOT = r"C:\Users\Bona\upwork-signup"; CAP = os.path.join(ROOT, "cap")
PROFILE = os.path.join(ROOT, "chrome-profile"); AVATAR = os.path.join(CAP, "avatar.jpg")

DOB = "05/14/1995"
ADDR = {"street": "1247 Maple Avenue", "city": "Austin", "state": "Texas", "zip": "78701"}


async def fill_first(page, selectors, value):
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                await el.fill("")
                await page.keyboard.type(value, delay=40)
                return True
        except Exception:
            pass
    return False


async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            PROFILE, headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-first-run",
                  "--no-default-browser-check", "--start-maximized"],
            viewport=None, locale="en-US")
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://www.upwork.com/nx/create-profile/location",
                        wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        print("URL", page.url, flush=True)

        await fill_first(page, ['input[placeholder*="mm/dd" i]', 'input[aria-label*="birth" i]'], DOB)
        await fill_first(page, ['input[placeholder*="street" i]'], ADDR["street"])
        await fill_first(page, ['input[placeholder*="city" i]'], ADDR["city"])
        await fill_first(page, ['input[placeholder*="state" i]', 'input[placeholder*="province" i]'], ADDR["state"])
        await fill_first(page, ['input[placeholder*="zip" i]', 'input[placeholder*="postal" i]'], ADDR["zip"])
        print("address+dob filled", flush=True)

        # upload photo: set the hidden file input directly
        try:
            finputs = await page.query_selector_all("input[type=file]")
            if finputs:
                await finputs[0].set_input_files(AVATAR)
                print("photo set on file input", flush=True)
                await page.wait_for_timeout(2500)
                await page.screenshot(path=os.path.join(CAP, "photo_modal.png"))
                # crop/save modal: click a save/attach/apply button
                for t in ["Save", "Attach photo", "Apply", "Done", "Crop"]:
                    el = await page.query_selector(f'button:has-text("{t}")')
                    if el and await el.is_visible():
                        await el.click(); print("clicked", t, flush=True); break
                await page.wait_for_timeout(2000)
        except Exception as e:
            print("photo err", e, flush=True)

        await page.wait_for_timeout(1000)
        # scroll to phone
        try:
            tel = await page.query_selector("input[type=tel], input[placeholder*=phone i]")
            if tel:
                await tel.scroll_into_view_if_needed()
        except Exception:
            pass
        await page.screenshot(path=os.path.join(CAP, "final_filled.png"), full_page=True)
        print("DONE filled+photo; screenshot final_filled.png", flush=True)
        while True:
            await asyncio.sleep(5)

asyncio.run(main())
