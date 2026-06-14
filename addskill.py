import asyncio, os
from patchright.async_api import async_playwright
CAP=r"C:\Users\Bona\upwork-signup\cap"
async def main():
    async with async_playwright() as p:
        b=await p.chromium.connect_over_cdp("http://localhost:9223")
        page=b.contexts[0].pages[-1]
        inp=await page.query_selector("input[type=search]")
        await inp.click()
        for ch in "Customer Service":
            await page.keyboard.type(ch); await page.wait_for_timeout(80)
        await page.wait_for_timeout(2500)
        await page.screenshot(path=os.path.join(CAP,"skill_dd.png"))
        # try clicking first listbox/option
        opt=None
        for sel in ["[role=option]","li[role=option]","ul li","[role=listbox] *"]:
            els=await page.query_selector_all(sel)
            for e in els:
                if await e.is_visible():
                    opt=e; break
            if opt: break
        if opt:
            await opt.click(); print("clicked option", flush=True)
        else:
            await page.keyboard.press("Enter"); print("pressed Enter", flush=True)
        await page.wait_for_timeout(1500)
        await page.screenshot(path=os.path.join(CAP,"skill_added.png"))
        print("URL", page.url, flush=True)
asyncio.run(main())
