#!/usr/bin/env python3
"""Single-process onboarding pilot. Owns the persistent (logged-in) browser
directly — no CDP attach, so it can't wedge. Resumes Upwork freelancer
onboarding and advances toward the phone-number step, handling Skip/Next and
mandatory fields generically. Stops + screenshots when the phone step appears."""
import asyncio, os
from patchright.async_api import async_playwright

ROOT = r"C:\Users\Bona\upwork-signup"
CAP = os.path.join(ROOT, "cap")
PROFILE = os.path.join(ROOT, "chrome-profile")
os.makedirs(CAP, exist_ok=True)

ADVANCE = ["Skip for now", "Skip", "Next", "Continue", "Review your profile",
           "Submit profile", "Looks good"]
BIO = ("Experienced customer service representative with strong communication "
       "skills, problem-solving ability, and a track record of resolving client "
       "issues quickly and professionally across email, chat, and phone support.")


async def is_phone(page):
    for sel in ["input[type=tel]", "input[name*=phone i]", "input[id*=phone i]",
                "input[placeholder*=phone i]"]:
        el = await page.query_selector(sel)
        if el and await el.is_visible():
            return True
    try:
        t = (await page.inner_text("body")).lower()
        if "phone number" in t and ("verify" in t or "send" in t or "add a phone" in t):
            return True
    except Exception:
        pass
    return False


async def handle_languages(page):
    """Set the English proficiency dropdown. Options are li[role=option]
    (Basic/Conversational/Fluent/Native). Click 'Fluent' directly; keyboard fallback."""
    try:
        dd = await page.query_selector('[role=combobox], button:has-text("My level is")')
        if not (dd and await dd.is_visible()):
            return False
        await dd.click()
        await page.wait_for_timeout(900)
        # direct click on the Fluent option
        for opt in await page.query_selector_all('li[role=option]'):
            try:
                if await opt.is_visible() and "fluent" in (await opt.inner_text()).lower():
                    await opt.click(); await page.wait_for_timeout(600); return True
            except Exception:
                pass
        # keyboard fallback (proven to work): ArrowDown x3 -> Fluent, Enter
        for _ in range(3):
            await page.keyboard.press("ArrowDown"); await page.wait_for_timeout(250)
        await page.keyboard.press("Enter"); await page.wait_for_timeout(600)
        return True
    except Exception:
        return False


async def fill_required(page):
    """Fill empty mandatory widgets so Next isn't blocked."""
    # textareas (bio/overview)
    for ta in await page.query_selector_all("textarea"):
        try:
            if await ta.is_visible() and not (await ta.input_value()).strip():
                await ta.fill(BIO)
        except Exception:
            pass
    # number / rate inputs
    for sel in ["input[type=number]", "input[name*=rate i]", "input[id*=rate i]"]:
        for inp in await page.query_selector_all(sel):
            try:
                if await inp.is_visible() and not (await inp.input_value()).strip():
                    await inp.fill("25")
            except Exception:
                pass


async def click_advance(page):
    for t in ADVANCE:
        for el in await page.query_selector_all(f'button:has-text("{t}"), a:has-text("{t}")'):
            try:
                if await el.is_visible() and await el.is_enabled():
                    await el.scroll_into_view_if_needed(timeout=2000)
                    await el.click(timeout=4000)
                    return t
            except Exception:
                continue
    return None


async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            PROFILE, headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-first-run",
                  "--no-default-browser-check", "--start-maximized"],
            viewport=None, locale="en-US",
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://www.upwork.com/nx/create-profile/", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        for i in range(30):
            await page.wait_for_timeout(1500)
            url = page.url
            if await is_phone(page):
                await page.screenshot(path=os.path.join(CAP, "PHONE_STEP.png"))
                print(f"PHONE_STEP_REACHED url={url}", flush=True)
                break
            if "languages" in url:
                await handle_languages(page)
            if "rate" in url:
                # hourly rate is a masked currency text field; type into the first editable one
                for inp in await page.query_selector_all("input[type=text], input:not([type])"):
                    try:
                        if not await inp.is_visible():
                            continue
                        if (await inp.get_attribute("readonly")) is not None or await inp.is_disabled():
                            continue
                        await inp.click()
                        await inp.fill("")
                        await page.keyboard.type("30")
                        await page.wait_for_timeout(400)
                        break
                    except Exception:
                        pass
            await fill_required(page)
            clicked = await click_advance(page)
            await page.screenshot(path=os.path.join(CAP, f"pilot_{i:02d}.png"))
            print(f"[{i}] url={url} clicked={clicked}", flush=True)
            if clicked is None:
                print(f"STUCK at {url} — needs manual handling", flush=True)
                break
        else:
            print("MAX reached", flush=True)
        # keep browser open for follow-up
        while True:
            await asyncio.sleep(5)

asyncio.run(main())
