#!/usr/bin/env python3
"""Attach to the live browser (CDP :9223) and finish the location page:
re-fill street/city, upload the photo via file-chooser, screenshot. No restart."""
import asyncio, os
from patchright.async_api import async_playwright
CAP = r"C:\Users\Bona\upwork-signup\cap"; AVATAR = os.path.join(CAP, "avatar.jpg")


async def main():
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp("http://localhost:9223")
        page = b.contexts[0].pages[-1]
        await page.bring_to_front()
        print("url", page.url, flush=True)

        # re-fill street + city (page.fill auto-waits + re-resolves stale nodes)
        for ph, val in [("street", "1247 Maple Avenue"), ("city", "Austin")]:
            try:
                sel = f'input[placeholder*="{ph}" i]'
                await page.fill(sel, val, timeout=8000)
                await page.wait_for_timeout(600)
                await page.keyboard.press("Escape")  # dismiss autocomplete, keep text
                print(f"{ph} filled = {await page.input_value(sel)}", flush=True)
            except Exception as e:
                print(f"{ph} err {e}", flush=True)

        # upload photo via file chooser
        try:
            async with page.expect_file_chooser(timeout=8000) as fc_info:
                btn = await page.query_selector('button:has-text("Upload photo"), a:has-text("Upload photo")')
                await btn.click()
            fc = await fc_info.value
            await fc.set_input_files(AVATAR)
            print("photo chosen", flush=True)
            await page.wait_for_timeout(2500)
            await page.screenshot(path=os.path.join(CAP, "crop_modal.png"))
            for t in ["Attach photo", "Save", "Apply", "Done", "Upload photo"]:
                el = await page.query_selector(f'button:has-text("{t}")')
                if el and await el.is_visible() and await el.is_enabled():
                    await el.click(); print("crop-clicked", t, flush=True); break
            await page.wait_for_timeout(2000)
        except Exception as e:
            print("photo err", e, flush=True)

        await page.wait_for_timeout(800)
        await page.screenshot(path=os.path.join(CAP, "after_photo.png"), full_page=True)
        print("DONE street/city/photo", flush=True)

asyncio.run(main())
