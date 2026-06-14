#!/usr/bin/env python3
"""Street/City are autocomplete fields requiring a picked suggestion. Type slowly,
capture the dropdown, click the first real suggestion (auto-fills city/state/zip)."""
import asyncio, os, json
from patchright.async_api import async_playwright
CAP = r"C:\Users\Bona\upwork-signup\cap"


async def type_and_pick(page, sel, text, tag):
    el = await page.query_selector(sel)
    await el.click()
    await page.keyboard.press("Control+A"); await page.keyboard.press("Delete")
    for ch in text:
        await page.keyboard.type(ch); await page.wait_for_timeout(140)
    await page.wait_for_timeout(2000)
    await page.screenshot(path=os.path.join(CAP, f"dd_{tag}.png"))
    opts = await page.evaluate("""()=>[...document.querySelectorAll('[role=option],li[role=option],ul[role=listbox] li,[class*=dropdown] li,[class*=menu] li')].filter(e=>e.offsetParent&&e.innerText.trim()).slice(0,12).map(e=>e.innerText.trim())""")
    print(f"{tag} options:", json.dumps(opts)[:400], flush=True)
    # click first suggestion
    for s in ['[role=option]', 'ul[role=listbox] li', '[class*=dropdown] li', '[class*=menu] li']:
        els = await page.query_selector_all(s)
        for e in els:
            if await e.is_visible() and (await e.inner_text()).strip():
                await e.click()
                await page.wait_for_timeout(1200)
                print(f"{tag} picked: {(await e.inner_text())[:50]}", flush=True)
                return True
    return False


async def main():
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp("http://localhost:9223")
        page = b.contexts[0].pages[-1]
        await page.bring_to_front()
        # street: type a real address and pick suggestion (fills city/state/zip)
        await type_and_pick(page, 'input[placeholder*="street" i]', "100 Congress Avenue, Austin, TX", "street")
        await page.wait_for_timeout(1000)
        # if city still empty, do city autocomplete
        cityval = await page.input_value('input[placeholder*="city" i]')
        print("city now:", cityval, flush=True)
        if not cityval.strip():
            await type_and_pick(page, 'input[placeholder*="city" i]', "Austin", "city")
        await page.wait_for_timeout(800)
        await page.screenshot(path=os.path.join(CAP, "addr_done.png"), full_page=True)
        # report current field values
        for ph in ["street", "city", "state", "zip"]:
            try:
                print(ph, "=", await page.input_value(f'input[placeholder*="{ph}" i]'), flush=True)
            except Exception:
                pass
        print("DONE finish6", flush=True)

asyncio.run(main())
