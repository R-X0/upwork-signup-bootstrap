#!/usr/bin/env python3
"""ONE-TIME network capture of Upwork's freelancer signup, run with Windows python.exe.

Launches a visible Chrome, logs every request/response to /api/graphql/v1 (and verify
endpoints) with full headers + post bodies to cap/requests.jsonl, drives the freelancer
signup form using a real eldenstats catch-all email, and screenshots each step.

Goal: capture the exact REGISTER GraphQL mutation (operationName, query doc, variables,
headers) so we can re-implement it browserless with curl_cffi + CapSolver. The
browser's own grecaptcha mints the v3 token for this capture.
"""
import asyncio, json, os, random, string, time
from patchright.async_api import async_playwright

ROOT = r"C:\Users\Bona\upwork-signup"
CAP = os.path.join(ROOT, "cap")
PROFILE = os.path.join(ROOT, "chrome-profile")
os.makedirs(CAP, exist_ok=True)

FIRST = ["James","Emma","Liam","Olivia","Noah","Ava","Ethan","Sophia","Mason","Mia"]
LAST = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Wilson","Lee"]

fn = random.choice(FIRST); ln = random.choice(LAST)
tag = "".join(random.choices(string.ascii_lowercase+string.digits, k=6))
EMAIL = f"{fn.lower()}.{ln.lower()}.{tag}@eldenstats.com"
PW = "".join(random.choices(string.ascii_letters, k=4)) + "9!" + "".join(random.choices(string.ascii_lowercase, k=4)) + "Xz"

reqlog = open(os.path.join(CAP, "requests.jsonl"), "w", encoding="utf-8")
def log(obj):
    reqlog.write(json.dumps(obj, ensure_ascii=False) + "\n"); reqlog.flush()

def interesting(url):
    return ("/api/graphql/v1" in url or "verify-email" in url or "verify-phone" in url
            or "/nx/signup/api" in url or "create" in url.lower())

async def main():
    print("EMAIL:", EMAIL, "PW:", PW, flush=True)
    open(os.path.join(CAP, "creds.txt"), "w").write(f"{EMAIL}\n{PW}\n")
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            PROFILE, headless=False,
            args=["--disable-blink-features=AutomationControlled","--no-first-run",
                  "--no-default-browser-check","--start-maximized"],
            viewport=None, locale="en-US",
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        async def on_request(req):
            if interesting(req.url):
                try: body = req.post_data
                except Exception: body = None
                log({"t":"req","method":req.method,"url":req.url,
                     "headers":dict(req.headers),"post_data":body,"ts":time.time()})
        async def on_response(resp):
            if interesting(resp.url):
                try: text = await resp.text()
                except Exception: text = None
                log({"t":"resp","status":resp.status,"url":resp.url,
                     "body":(text[:6000] if text else None),"ts":time.time()})
        page.on("request", lambda r: asyncio.create_task(on_request(r)))
        page.on("response", lambda r: asyncio.create_task(on_response(r)))

        async def shot(name):
            try: await page.screenshot(path=os.path.join(CAP, name+".png"))
            except Exception as e: print("shot err", e, flush=True)

        async def dump_dom(name):
            js = """() => {
              const els=[...document.querySelectorAll('input,button,a[role=button],select,[role=radio],label')];
              return els.slice(0,80).map(e=>({tag:e.tagName,type:e.type||'',name:e.name||'',
                id:e.id||'',ph:e.placeholder||'',text:(e.innerText||e.value||'').slice(0,40),
                qa:e.getAttribute('data-qa')||e.getAttribute('data-ev-label')||'',
                vis:!!(e.offsetParent)}));
            }"""
            try:
                els = await page.evaluate(js)
                open(os.path.join(CAP, name+".json"),"w",encoding="utf-8").write(json.dumps(els,indent=1))
            except Exception as e: print("dom err", e, flush=True)

        await page.goto("https://www.upwork.com/nx/signup/?dest=home", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(6000)
        await shot("01_landing"); await dump_dom("01_landing")
        print("STEP1 landing done — url:", page.url, flush=True)

        # dismiss OneTrust cookie banner (accept-all if present)
        for sel in ["#onetrust-accept-btn-handler", "#onetrust-pc-btn-handler ~ button", "button[aria-label=Close]"]:
            try:
                el = await page.query_selector(sel)
                if el:
                    await el.click(timeout=3000); print("cookie dismissed via", sel, flush=True); break
            except Exception: pass
        await page.wait_for_timeout(1500)

        # click Freelancer
        try:
            await page.click("[data-qa=btn-apply-freelancer]", timeout=10000)
            print("clicked freelancer", flush=True)
        except Exception as e:
            print("freelancer click err", e, flush=True)
        await page.wait_for_timeout(7000)
        await shot("02_form"); await dump_dom("02_form")
        print("STEP2 form reached — url:", page.url, flush=True)

        # fill the freelancer signup form
        try:
            await page.fill("#first-name-input", fn)
            await page.fill("#last-name-input", ln)
            await page.fill("#redesigned-input-email", EMAIL)
            await page.fill("#password-input", PW)
            # ensure ALL checkboxes (terms is required) are checked; real input is
            # hidden behind a styled span, so force the check.
            boxes = await page.query_selector_all("input[type=checkbox]")
            for b in boxes:
                try:
                    if not await b.is_checked():
                        await b.check(force=True, timeout=3000)
                except Exception as ce:
                    print("checkbox warn", ce, flush=True)
            await page.wait_for_timeout(800)
            await shot("03_filled")
            print("STEP3 filled", EMAIL, flush=True)
        except Exception as e:
            print("fill err", e, flush=True)

        # submit — this fires the REGISTER graphql mutation (grecaptcha auto-mints v3 token)
        try:
            await page.click("#button-submit-form", timeout=10000)
            print("STEP4 submit clicked", flush=True)
        except Exception as e:
            print("submit err", e, flush=True)
        await page.wait_for_timeout(9000)
        await shot("04_after_submit"); await dump_dom("04_after_submit")
        print("STEP4 after submit — url:", page.url, flush=True)

        # stay alive (so the verify-email flow + onboarding can be observed)
        while True:
            await page.wait_for_timeout(5000)
            await shot("live")

asyncio.run(main())
