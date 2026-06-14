import asyncio, os
from patchright.async_api import async_playwright
CAP=r"C:\Users\Bona\upwork-signup\cap"
async def main():
    async with async_playwright() as p:
        b=await p.chromium.connect_over_cdp("http://localhost:9223")
        page=b.contexts[0].pages[-1]; await page.bring_to_front()
        rv=await page.query_selector('button:has-text("Review your profile"), a:has-text("Review your profile")')
        if rv: await rv.click(); print("clicked Review",flush=True); await page.wait_for_timeout(7000)
        print("url:",page.url,flush=True)
        await page.screenshot(path=os.path.join(CAP,"review2.png"),full_page=True)
        body=(await page.inner_text("body"))
        low=body.lower()
        for kw in ["verify your phone","verification code","we sent","enter the code","send code","could not be found","type slowly","verify phone"]:
            if kw in low: print("HINT:",kw,flush=True)
        # any tel/code inputs?
        for sel in ["input[type=tel]","input[autocomplete=one-time-code]","input[name*=code i]","input[maxlength='6']","input[inputmode=numeric]"]:
            els=await page.query_selector_all(sel)
            for e in els:
                if await e.is_visible(): print("INPUT:",sel,flush=True); break
        print("DONE finish7",flush=True)
asyncio.run(main())
