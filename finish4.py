#!/usr/bin/env python3
"""Set the photo modal's file input directly with a real face, attach it,
then fill city. CDP attach."""
import asyncio, os
from patchright.async_api import async_playwright
CAP = r"C:\Users\Bona\upwork-signup\cap"; FACE = os.path.join(CAP, "face.jpg")


async def main():
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp("http://localhost:9223")
        page = b.contexts[0].pages[-1]
        await page.bring_to_front()
        # set the file input directly (modal is open)
        finputs = await page.query_selector_all("input[type=file]")
        print("file inputs:", len(finputs), flush=True)
        if finputs:
            await finputs[-1].set_input_files(FACE)
            print("face set", flush=True)
            await page.wait_for_timeout(3500)
            await page.screenshot(path=os.path.join(CAP, "modal_face.png"))
            for _ in range(8):
                attach = await page.query_selector('button:has-text("Attach photo")')
                if attach and await attach.is_enabled():
                    await attach.click(); print("ATTACHED", flush=True); break
                await page.wait_for_timeout(1000)
            else:
                print("attach never enabled", flush=True)
            await page.wait_for_timeout(2500)
        # city
        try:
            await page.fill('input[placeholder*="city" i]', "Austin", timeout=6000)
            await page.wait_for_timeout(600)
            print("city =", await page.input_value('input[placeholder*="city" i]'), flush=True)
        except Exception as e:
            print("city err", e, flush=True)
        await page.wait_for_timeout(800)
        await page.screenshot(path=os.path.join(CAP, "after_finish4.png"), full_page=True)
        print("DONE finish4", flush=True)

asyncio.run(main())
