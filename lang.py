import asyncio, os, json
from patchright.async_api import async_playwright
ROOT=r"C:\Users\Bona\upwork-signup"; CAP=os.path.join(ROOT,"cap"); PROFILE=os.path.join(ROOT,"chrome-profile")
async def main():
    async with async_playwright() as p:
        ctx=await p.chromium.launch_persistent_context(PROFILE,headless=False,
            args=["--disable-blink-features=AutomationControlled","--no-first-run","--no-default-browser-check","--start-maximized"],
            viewport=None,locale="en-US")
        page=ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://www.upwork.com/nx/create-profile/languages",wait_until="domcontentloaded",timeout=60000)
        await page.wait_for_timeout(4000)
        print("URL", page.url, flush=True)
        # open the proficiency dropdown
        dd=await page.query_selector('[role=combobox], button:has-text("My level is")')
        print("dd found:", bool(dd), flush=True)
        if dd:
            await dd.click(); await page.wait_for_timeout(1000)
            await page.screenshot(path=os.path.join(CAP,"dd_open.png"))
            # dump candidate options
            opts=await page.evaluate("""()=>[...document.querySelectorAll('[role=option],li,[role=listbox] *,[class*=menu] *')].filter(e=>e.offsetParent&&e.innerText&&e.innerText.length<40).slice(0,40).map(e=>({t:e.tagName,r:e.getAttribute('role'),txt:e.innerText.trim()}))""")
            print("OPTS:", json.dumps(opts)[:1200], flush=True)
            # try keyboard select
            await page.keyboard.press("ArrowDown"); await page.wait_for_timeout(300)
            await page.keyboard.press("ArrowDown"); await page.wait_for_timeout(300)
            await page.keyboard.press("Enter"); await page.wait_for_timeout(800)
            await page.screenshot(path=os.path.join(CAP,"dd_after.png"))
        body=(await page.inner_text("body")).lower()
        print("still_error:", "select your english" in body, flush=True)
        while True: await asyncio.sleep(5)
asyncio.run(main())
