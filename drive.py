#!/usr/bin/env python3
"""Drive the live logged-in Upwork browser over CDP (:9223). Windows python.exe.

Usage:
  python.exe drive.py snap [name]          # screenshot + DOM dump of current page
  python.exe drive.py goto <url>           # navigate
  python.exe drive.py click "<selector>"   # human-like click (mouse move + dwell)
  python.exe drive.py fill "<selector>" "<value>"
  python.exe drive.py type "<selector>" "<value>"   # per-char typing w/ delays
"""
import asyncio, json, os, random, sys
from patchright.async_api import async_playwright

CAP = r"C:\Users\Bona\upwork-signup\cap"
CDP = "http://localhost:9223"


async def human_move_click(page, el):
    box = await el.bounding_box()
    if not box:
        await el.click(); return
    tx = box["x"] + box["width"] / 2 + random.uniform(-4, 4)
    ty = box["y"] + box["height"] / 2 + random.uniform(-3, 3)
    steps = random.randint(18, 34)
    await page.mouse.move(tx, ty, steps=steps)
    await page.wait_for_timeout(random.randint(120, 380))
    await page.mouse.down(); await page.wait_for_timeout(random.randint(40, 110)); await page.mouse.up()


async def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "snap"
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        page = ctx.pages[-1] if ctx.pages else await ctx.new_page()
        await page.bring_to_front()

        if cmd == "goto":
            await page.goto(sys.argv[2], wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)
        elif cmd == "click":
            el = await page.query_selector(sys.argv[2])
            await human_move_click(page, el)
            await page.wait_for_timeout(2500)
        elif cmd == "fill":
            await page.fill(sys.argv[2], sys.argv[3])
        elif cmd == "type":
            el = await page.query_selector(sys.argv[2]); await el.click()
            for ch in sys.argv[3]:
                await page.keyboard.type(ch); await page.wait_for_timeout(random.randint(60, 170))

        name = (sys.argv[2] if cmd == "snap" and len(sys.argv) > 2 else "drive")
        await page.screenshot(path=os.path.join(CAP, name + ".png"))
        els = await page.evaluate("""() => [...document.querySelectorAll('input,button,a[role=button],select,[role=radio]')].slice(0,60).map(e=>({tag:e.tagName,type:e.type||'',id:e.id||'',qa:e.getAttribute('data-qa')||e.getAttribute('data-test')||'',ph:e.placeholder||'',text:(e.innerText||e.value||'').slice(0,40),vis:!!e.offsetParent}))""")
        open(os.path.join(CAP, name + ".json"), "w", encoding="utf-8").write(json.dumps(els, indent=1))
        print("URL:", page.url)
        print("DONE", cmd)

asyncio.run(main())
