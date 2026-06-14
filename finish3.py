#!/usr/bin/env python3
"""Photo modal is open: upload avatar via the in-modal 'Upload' link, click
Attach photo; then re-fill city. CDP attach, no restart."""
import asyncio, os
from patchright.async_api import async_playwright
CAP = r"C:\Users\Bona\upwork-signup\cap"; AVATAR = os.path.join(CAP, "avatar.jpg")


async def main():
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp("http://localhost:9223")
        page = b.contexts[0].pages[-1]
        await page.bring_to_front()

        # photo modal should be open; the in-modal "Upload" triggers the chooser
        try:
            async with page.expect_file_chooser(timeout=8000) as fc_info:
                up = await page.query_selector('text=Upload')
                await up.click()
            fc = await fc_info.value
            await fc.set_input_files(AVATAR)
            print("photo set via modal", flush=True)
            await page.wait_for_timeout(3000)
            await page.screenshot(path=os.path.join(CAP, "modal_after_upload.png"))
            attach = await page.query_selector('button:has-text("Attach photo")')
            if attach and await attach.is_enabled():
                await attach.click(); print("attached", flush=True)
            else:
                print("Attach disabled (photo maybe rejected)", flush=True)
            await page.wait_for_timeout(2500)
        except Exception as e:
            print("photo err", e, flush=True)

        # close modal if still open
        x = await page.query_selector('button[aria-label="Close" i], button:has-text("Cancel")')
        # re-fill city (type, blur by Tab — no Escape)
        try:
            await page.fill('input[placeholder*="city" i]', "Austin", timeout=6000)
            await page.wait_for_timeout(500)
            await page.keyboard.press("Tab")
            print("city =", await page.input_value('input[placeholder*="city" i]'), flush=True)
        except Exception as e:
            print("city err", e, flush=True)

        await page.wait_for_timeout(800)
        await page.screenshot(path=os.path.join(CAP, "after_finish3.png"), full_page=True)
        print("DONE finish3", flush=True)

asyncio.run(main())
