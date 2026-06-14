#!/usr/bin/env python3
"""FULL Upwork freelancer signup, end-to-end, one fast run (Windows python).
Owns a fresh browser profile. Humanized interaction to pass reCAPTCHA on account
creation. eldenstats worker for email verify. TextVerified number rented+entered
LAST (right before Send code) so the reservation is fresh. Prints >>> markers."""
import asyncio, os, random, string, time, re
from patchright.async_api import async_playwright
from curl_cffi import requests as cffi
import config
from signup_utils import extract_verify_link, normalize_phone, parse_sms_code, classify_signup_state

ROOT = config.ROOT; CAP = config.CAP
PROFILE = config.PROFILE  # fresh profile
FACE = config.FACE
WORKER = config.EMAIL_WORKER
TV_KEY = config.TV_API_KEY; TV_USER = config.TV_USER; TVB = config.TV_BASE
config.require("TV_API_KEY", "TV_USER")

FIRST = ["James","Emma","Liam","Olivia","Noah","Ava","Ethan","Sophia","Lucas","Mia","Henry","Ella"]
LAST = ["Smith","Johnson","Brown","Garcia","Miller","Davis","Wilson","Clark","Lewis","Walker","Hall","Young"]

fn = random.choice(FIRST); ln = random.choice(LAST)
tag = "".join(random.choices(string.ascii_lowercase+string.digits, k=6))
EMAIL = f"{fn.lower()}.{ln.lower()}.{tag}@{config.EMAIL_DOMAIN}"
PW = "".join(random.choices(string.ascii_uppercase,k=2))+"".join(random.choices(string.ascii_lowercase,k=5))+str(random.randint(10,99))+"!"


def log(m): print(f">>> {m}", flush=True)

# ---------- email worker ----------
def get_verify_link(tries=40, delay=3):
    for _ in range(tries):
        try:
            raw = cffi.get(f"{WORKER}/debug", params={"email": EMAIL}, impersonate="chrome", timeout=8).json().get("rawContent")
            link = extract_verify_link(raw)
            if link:
                return link
        except Exception:
            pass
        time.sleep(delay)
    return None

# ---------- textverified ----------
def tv():
    s = cffi.Session(impersonate="chrome")
    tok = s.post(f"{TVB}/api/pub/v2/auth", headers={"X-API-KEY":TV_KEY,"X-API-USERNAME":TV_USER,"Accept":"application/json"}, timeout=30).json()["token"]
    return s, {"Authorization":f"Bearer {tok}","Accept":"application/json","Content-Type":"application/json"}

def tv_number(s,h):
    vid = s.post(f"{TVB}/api/pub/v2/verifications", headers=h, json={"serviceName":"upwork","capability":"sms"}, timeout=30).json()["href"].rstrip("/").split("/")[-1]
    for _ in range(20):
        v = s.get(f"{TVB}/api/pub/v2/verifications/{vid}", headers=h, timeout=30).json()
        if v.get("number"): return vid, v["number"]
        time.sleep(3)
    return vid, None

def tv_code(s,h,vid,tries=40,delay=4):
    for i in range(tries):
        v = s.get(f"{TVB}/api/pub/v2/verifications/{vid}", headers=h, timeout=30).json()
        code = parse_sms_code(v)
        if code: return code
        try:
            sms = s.get(f"{TVB}/api/pub/v2/sms?reservationId={vid}", headers=h, timeout=30).json()
            code = parse_sms_code(sms)
            if code: return code
        except Exception: pass
        print(f"    sms poll {i*delay}s state={v.get('state')}", flush=True)
        time.sleep(delay)
    return None

# ---------- humanized browser helpers ----------
async def hmove_click(page, el):
    if el is None:
        log("hmove_click: element is None — skipping"); return
    try:
        await el.scroll_into_view_if_needed(timeout=4000)
    except Exception:
        pass
    box = await el.bounding_box()
    if not box:
        await el.click(force=True, timeout=5000); return
    tx = box["x"]+box["width"]/2+random.uniform(-5,5); ty = box["y"]+box["height"]/2+random.uniform(-3,3)
    await page.mouse.move(tx-random.uniform(40,90), ty-random.uniform(30,60), steps=8)
    await page.mouse.move(tx, ty, steps=random.randint(14,26))
    await page.wait_for_timeout(random.randint(120,300))
    await page.mouse.down(); await page.wait_for_timeout(random.randint(40,90)); await page.mouse.up()

async def htype(page, sel, text):
    el = await page.query_selector(sel); await hmove_click(page, el)
    for ch in text:
        await page.keyboard.type(ch); await page.wait_for_timeout(random.randint(45,130))

async def click_text(page, *texts, human=False):
    for t in texts:
        for el in await page.query_selector_all(f'button:has-text("{t}"), a:has-text("{t}")'):
            try:
                if await el.is_visible() and await el.is_enabled():
                    if human: await hmove_click(page, el)
                    else: await el.click(timeout=5000)
                    return t
            except Exception: continue
    return None

async def shot(page,n):
    try: await page.screenshot(path=os.path.join(CAP,n+".png"))
    except Exception: pass

async def dismiss_cookies(page):
    for sel in ["#onetrust-accept-btn-handler", "button#onetrust-accept-btn-handler",
                'button:has-text("Accept All")', 'button:has-text("Accept")']:
        try:
            e = await page.query_selector(sel)
            if e and await e.is_visible():
                await e.click(timeout=3000); await page.wait_for_timeout(600); return True
        except Exception: pass
    # nuke the OneTrust banner from the DOM so it can't intercept the terms checkbox
    try:
        await page.evaluate("""()=>{for(const id of ['onetrust-banner-sdk','onetrust-consent-sdk']){const e=document.getElementById(id); if(e) e.remove();}}""")
    except Exception: pass
    return False


async def main():
    log(f"identity {fn} {ln} <{EMAIL}> pw={PW}")
    open(os.path.join(CAP,"run_creds.txt"),"w").write(f"{EMAIL}\n{PW}\n")
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            PROFILE, headless=False,
            args=["--remote-debugging-port=9223","--disable-blink-features=AutomationControlled",
                  "--no-first-run","--no-default-browser-check","--start-maximized"],
            viewport=None, locale="en-US")
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # log the register response so we know exactly why submit fails
        async def on_resp(r):
            if "gql-mutation-register" in r.url:
                try:
                    j = await r.json()
                    err = (j.get("errors") or [{}])[0]
                    log(f"REGISTER_RESP status={r.status} err={err.get('message')} code={err.get('extensions',{}).get('code')} success={(j.get('data') or {}).get('register',{})}")
                except Exception as e:
                    log(f"REGISTER_RESP status={r.status} (non-json {e})")
        page.on("response", lambda r: asyncio.create_task(on_resp(r)))

        # 0) WARM the profile (~2min) to build reCAPTCHA v3 reputation before signing up
        log("warming profile (~2 min browsing)...")
        for url in ["https://www.upwork.com/", "https://www.upwork.com/nx/find-work/",
                    "https://www.upwork.com/freelance-jobs/"]:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            except Exception: pass
            await dismiss_cookies(page)
            for _ in range(6):
                await page.mouse.move(random.uniform(200,1100), random.uniform(200,700), steps=random.randint(10,20))
                await page.mouse.wheel(0, random.randint(200,600))
                await page.wait_for_timeout(random.randint(2500,5000))
        log("warm-up done")

        # 1) signup landing
        await page.goto("https://www.upwork.com/nx/signup/?dest=home", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        await dismiss_cookies(page)
        try:
            fr = await page.wait_for_selector("[data-qa=btn-apply-freelancer]", timeout=20000)
        except Exception:
            fr = await page.query_selector("[data-qa=btn-apply-freelancer]")
        await hmove_click(page, fr); log("freelancer clicked")
        await page.wait_for_timeout(5000)
        await dismiss_cookies(page)  # banner can reappear on the form

        # 2) signup form — FULL humanized typing (behavioral signal for reCAPTCHA v3)
        await dismiss_cookies(page)
        await htype(page, "#first-name-input", fn)
        await page.wait_for_timeout(random.randint(300,700))
        await htype(page, "#last-name-input", ln)
        await page.wait_for_timeout(random.randint(300,700))
        await htype(page, "#redesigned-input-email", EMAIL)
        await page.wait_for_timeout(random.randint(400,900))
        await htype(page, "#password-input", PW)
        await dismiss_cookies(page)
        # REAL-click the terms checkbox (via its label) so React registers onChange
        for lab in ["checkbox-terms", "checkbox-promo"]:
            try:
                el = await page.query_selector(f'label#{lab}, #{lab}')
                if el:
                    box = await el.bounding_box()
                    if box:
                        await page.mouse.click(box["x"]+12, box["y"]+box["height"]/2)
                        await page.wait_for_timeout(300)
            except Exception as e: log(f"{lab} click err {e}")
        # ensure both ended up checked
        try:
            boxes = await page.query_selector_all("input[type=checkbox]")
            for bx in boxes:
                if not await bx.is_checked():
                    await bx.check(force=True)
            log(f"checkboxes checked: {[await b.is_checked() for b in boxes]}")
        except Exception as e: log(f"checkbox verify err {e}")
        # human signal for recaptcha: wiggle the mouse around + dwell
        for _ in range(4):
            await page.mouse.move(random.uniform(250,1000), random.uniform(250,650), steps=random.randint(10,22))
            await page.wait_for_timeout(random.randint(150,350))
        await shot(page,"r_form")
        btn = await page.query_selector("#button-submit-form")
        await btn.scroll_into_view_if_needed()
        await hmove_click(page, btn); log("create-account clicked")
        await page.wait_for_timeout(9000)
        await shot(page,"r_after_submit")
        log(f"after submit url={page.url}")
        body = await page.inner_text("body")
        state = classify_signup_state(page.url, body)
        if state == "rejected":
            log("RECAPTCHA_REJECTED (score<threshold / code 83) — automated click scored below Upwork's bar. "
                "Use hybrid.py and click 'Create my account' yourself.")
        elif state != "created":
            log("SUBMIT_ISSUE — not on a created/verify URL; check r_after_submit.png")

        # 3) email verify
        log("waiting for verify email...")
        link = get_verify_link()
        log(f"verify link: {link}")
        if link:
            await page.goto(link, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000)
        log(f"after verify url={page.url}")

        # 4) onboarding
        await page.goto("https://www.upwork.com/nx/create-profile/", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        await click_text(page, "Get started")
        await page.wait_for_timeout(4000)
        # category + specialty
        if "create-profile" in page.url:
            cat = await page.query_selector('text=Customer Service')
            if cat:
                try: await cat.click()
                except Exception: pass
                await page.wait_for_timeout(1500)
                for bx in await page.query_selector_all("input[type=checkbox]"):
                    try: await bx.check(force=True); break
                    except Exception: pass
            await click_text(page,"Next, add your skills","Next")
            await page.wait_for_timeout(2500)
        # skill via search
        try:
            inp = await page.query_selector("input[type=search]")
            if inp:
                await inp.click()
                for ch in "Customer Service": await page.keyboard.type(ch); await page.wait_for_timeout(70)
                await page.wait_for_timeout(2000)
                for s in ['li[role=option]','[role=option]']:
                    o = await page.query_selector(s)
                    if o and await o.is_visible(): await o.click(); break
        except Exception as e: log(f"skill err {e}")
        await click_text(page,"Next, your profile title","Next"); await page.wait_for_timeout(2500)
        # title
        await page.fill('input[type=text]', "Customer Service Representative");
        await click_text(page,"Next, add your experience","Next"); await page.wait_for_timeout(2500)

        # loop through remaining steps generically
        BIO=("Experienced customer service representative skilled in email, chat and phone "
             "support, problem solving, and fast professional resolution of client issues.")
        for i in range(16):
            await page.wait_for_timeout(1500)
            url = page.url
            if "create-profile/location" in url: log("reached final location page"); break
            if "languages" in url:
                dd = await page.query_selector('[role=combobox], button:has-text("My level is")')
                if dd:
                    await dd.click(); await page.wait_for_timeout(800)
                    picked=False
                    for o in await page.query_selector_all('li[role=option]'):
                        if await o.is_visible() and "fluent" in (await o.inner_text()).lower():
                            await o.click(); picked=True; break
                    if not picked:
                        for _ in range(3): await page.keyboard.press("ArrowDown"); await page.wait_for_timeout(200)
                        await page.keyboard.press("Enter")
                    await page.wait_for_timeout(600)
            for ta in await page.query_selector_all("textarea"):
                try:
                    if await ta.is_visible() and not (await ta.input_value()).strip(): await ta.fill(BIO)
                except Exception: pass
            if "rate" in url:
                for inp in await page.query_selector_all("input[type=text], input:not([type])"):
                    try:
                        if await inp.is_visible() and (await inp.get_attribute("readonly")) is None and not await inp.is_disabled():
                            await inp.click(); await inp.fill(""); await page.keyboard.type("30"); break
                    except Exception: pass
            c = await click_text(page,"Skip for now","Next","Continue")
            log(f"step {i} url={url} clicked={c}")
            if c is None: log(f"STUCK {url}"); break

        # 5) final page: photo, dob, address (slow stuff first)
        await page.wait_for_timeout(1500)
        # photo
        try:
            if not await page.query_selector('button:has-text("Edit photo")'):
                await click_text(page,"Upload photo")
                await page.wait_for_timeout(1500)
                fin = await page.query_selector_all("input[type=file]")
                if fin:
                    await fin[-1].set_input_files(FACE); await page.wait_for_timeout(3000)
                    for _ in range(8):
                        at = await page.query_selector('button:has-text("Attach photo")')
                        if at and await at.is_enabled(): await at.click(); log("photo attached"); break
                        await page.wait_for_timeout(1000)
                    await page.wait_for_timeout(2000)
        except Exception as e: log(f"photo err {e}")
        # dob
        try: await page.fill('input[placeholder*="mm/dd" i]', "05/14/1995")
        except Exception: pass
        # street autocomplete -> fills city/state/zip
        try:
            el = await page.query_selector('input[placeholder*="street" i]')
            await el.click(); await page.keyboard.press("Control+A"); await page.keyboard.press("Delete")
            for ch in "100 Congress Avenue, Austin, TX": await page.keyboard.type(ch); await page.wait_for_timeout(120)
            await page.wait_for_timeout(2000)
            for s in ['[role=option]','ul[role=listbox] li','[class*=dropdown] li','[class*=menu] li']:
                o = await page.query_selector(s)
                if o and await o.is_visible(): await o.click(); log("address picked"); break
            await page.wait_for_timeout(1200)
        except Exception as e: log(f"addr err {e}")
        await shot(page,"r_final_filled")

        # 6) PHONE LAST: rent fresh number, fill, Review -> Send code -> poll -> enter code
        s,h = tv(); vid, number = tv_number(s,h)
        digits = normalize_phone(number)
        log(f"TV fresh vid={vid} number={number}")
        try:
            el = await page.query_selector('input[type=tel], input[placeholder*="phone" i]')
            await el.click(); await page.keyboard.press("Control+A"); await page.keyboard.press("Delete")
            for ch in digits: await page.keyboard.type(ch); await page.wait_for_timeout(50)
        except Exception as e: log(f"phone fill err {e}")
        await click_text(page,"Review your profile"); await page.wait_for_timeout(5000)
        await shot(page,"r_verify_modal")
        # Send code in modal
        await click_text(page,"Send code"); log("Send code clicked"); await page.wait_for_timeout(2500)
        log("polling SMS...")
        code = tv_code(s,h,vid)
        log(f"SMS CODE = {code}")
        if code:
            for sel in ["input[autocomplete=one-time-code]","input[inputmode=numeric]","input[name*=code i]","input[maxlength='6']"]:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click(); await el.fill("")
                    for ch in str(code): await page.keyboard.type(ch); await page.wait_for_timeout(110)
                    log(f"code entered via {sel}"); break
            await page.wait_for_timeout(1500)
            await click_text(page,"Verify","Confirm","Submit","Next","Done")
            await page.wait_for_timeout(6000)
        await shot(page,"r_done")
        log(f"FINISHED url={page.url}")
        while True: await asyncio.sleep(5)

asyncio.run(main())
