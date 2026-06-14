#!/usr/bin/env python3
"""HYBRID Upwork signup: bot fills everything, then WAITS (up to 15 min) for the
human to click 'Create my account' (the reCAPTCHA gate). The instant the account
is created it auto-finishes: email verify -> onboarding -> photo -> address ->
TextVerified phone/SMS. Number rented LAST. Prints >>> markers."""
import asyncio, os, random, string, time, re
from patchright.async_api import async_playwright
from curl_cffi import requests as cffi
import config
from signup_utils import extract_verify_link, normalize_phone, parse_sms_code, classify_signup_state

ROOT = config.ROOT; CAP = config.CAP; PROFILE = config.PROFILE; FACE = config.FACE
WORKER = config.EMAIL_WORKER
TV_KEY = config.TV_API_KEY; TV_USER = config.TV_USER; TVB = config.TV_BASE
config.require("TV_API_KEY", "TV_USER")

FIRST=["James","Emma","Liam","Olivia","Noah","Ava","Ethan","Sophia","Lucas","Mia","Henry","Ella"]
LAST=["Smith","Johnson","Brown","Garcia","Miller","Davis","Wilson","Clark","Lewis","Walker","Hall","Young"]
fn=random.choice(FIRST); ln=random.choice(LAST)
tag="".join(random.choices(string.ascii_lowercase+string.digits,k=6))
EMAIL=f"{fn.lower()}.{ln.lower()}.{tag}@{config.EMAIL_DOMAIN}"
PW="".join(random.choices(string.ascii_uppercase,k=2))+"".join(random.choices(string.ascii_lowercase,k=5))+str(random.randint(10,99))+"!"
BIO=("Experienced customer service representative skilled in email, chat and phone support, "
     "problem solving, and fast professional resolution of client issues.")

def log(m): print(f">>> {m}", flush=True)

import json
import account_store
def save_account(status, **extra):
    """Record this account to the durable JSONL ledger AND Postgres (via account_store).
    Called at creation (login creds saved even if onboarding later stalls) and again
    with final status/phone at the end. A DB hiccup never aborts the run."""
    return account_store.record(status, EMAIL, PW, first=fn, last=ln, pipeline="patchright-hybrid", **extra)

import ctypes
def os_mouse_click(sx, sy):
    """Real OS-level cursor move + left click (Win32 user32) at screen px (sx,sy)."""
    u = ctypes.windll.user32
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    cur = POINT(); u.GetCursorPos(ctypes.byref(cur))
    steps = 30
    for i in range(1, steps + 1):
        nx = int(cur.x + (sx - cur.x) * i / steps + (random.uniform(-2, 2)))
        ny = int(cur.y + (sy - cur.y) * i / steps + (random.uniform(-2, 2)))
        u.SetCursorPos(nx, ny); time.sleep(0.012)
    u.SetCursorPos(int(sx), int(sy)); time.sleep(0.12)
    u.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
    time.sleep(0.06)
    u.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP

def get_verify_link(tries=120, delay=3):
    for _ in range(tries):
        try:
            raw=cffi.get(f"{WORKER}/debug",params={"email":EMAIL},impersonate="chrome",timeout=8).json().get("rawContent")
            link=extract_verify_link(raw)
            if link: return link
        except Exception: pass
        time.sleep(delay)
    return None

def tv():
    s=cffi.Session(impersonate="chrome")
    tok=s.post(f"{TVB}/api/pub/v2/auth",headers={"X-API-KEY":TV_KEY,"X-API-USERNAME":TV_USER,"Accept":"application/json"},timeout=30).json()["token"]
    return s,{"Authorization":f"Bearer {tok}","Accept":"application/json","Content-Type":"application/json"}
def tv_number(s,h):
    vid=s.post(f"{TVB}/api/pub/v2/verifications",headers=h,json={"serviceName":"upwork","capability":"sms"},timeout=30).json()["href"].rstrip("/").split("/")[-1]
    for _ in range(20):
        v=s.get(f"{TVB}/api/pub/v2/verifications/{vid}",headers=h,timeout=30).json()
        if v.get("number"): return vid,v["number"]
        time.sleep(3)
    return vid,None
def tv_code(s,h,vid,tries=40,delay=4):
    for i in range(tries):
        v=s.get(f"{TVB}/api/pub/v2/verifications/{vid}",headers=h,timeout=30).json()
        code=parse_sms_code(v)
        if code: return code
        try:
            sms=s.get(f"{TVB}/api/pub/v2/sms?reservationId={vid}",headers=h,timeout=30).json()
            code=parse_sms_code(sms)
            if code: return code
        except Exception: pass
        print(f"    sms {i*delay}s state={v.get('state')}",flush=True); time.sleep(delay)
    return None

async def dismiss_cookies(page):
    for sel in ["#onetrust-accept-btn-handler",'button:has-text("Accept All")','button:has-text("Accept")']:
        try:
            e=await page.query_selector(sel)
            if e and await e.is_visible(): await e.click(timeout=3000); await page.wait_for_timeout(500); return
        except Exception: pass
    try: await page.evaluate("()=>{for(const id of ['onetrust-banner-sdk','onetrust-consent-sdk']){const e=document.getElementById(id); if(e)e.remove();}}")
    except Exception: pass

async def click_text(page,*texts):
    for t in texts:
        for el in await page.query_selector_all(f'button:has-text("{t}"), a:has-text("{t}")'):
            try:
                if await el.is_visible() and await el.is_enabled(): await el.click(timeout=5000); return t
            except Exception: continue
    return None

async def hmove_click(page, el):
    """Trusted, human-like click: curved mouse approach + real down/up with press
    duration. reCAPTCHA v3 mints its token on THIS event — a real mouse trajectory
    scores far higher than a synthetic element.click() (isTrusted=false)."""
    if el is None:
        log("hmove_click: element is None — skipping"); return
    try: await el.scroll_into_view_if_needed(timeout=4000)
    except Exception: pass
    box=await el.bounding_box()
    if not box:
        await el.click(force=True, timeout=5000); return
    tx=box["x"]+box["width"]/2+random.uniform(-5,5); ty=box["y"]+box["height"]/2+random.uniform(-3,3)
    await page.mouse.move(tx-random.uniform(40,90), ty-random.uniform(30,60), steps=8)
    await page.mouse.move(tx, ty, steps=random.randint(14,26))
    await page.wait_for_timeout(random.randint(120,300))
    await page.mouse.down(); await page.wait_for_timeout(random.randint(40,90)); await page.mouse.up()

async def htype(page, sel, text):
    """Focus a field by real mouse click, then type char-by-char with human cadence —
    generates real keydown/keyup telemetry (reCAPTCHA reads keystroke timing). page.fill
    sets .value with ZERO key events and reads as a bot."""
    el=await page.query_selector(sel); await hmove_click(page, el)
    for ch in text:
        await page.keyboard.type(ch); await page.wait_for_timeout(random.randint(45,130))

async def main():
    log(f"identity {fn} {ln} <{EMAIL}> pw={PW}")
    open(os.path.join(CAP,"run_creds.txt"),"w").write(f"{EMAIL}\n{PW}\n")
    # STABLE WARM profile, reused every run: reCAPTCHA v3 reputation (cookies + history)
    # accumulates so the AUTOMATED click passes without a human. We log OUT of Upwork at
    # the start (below) so the signup form still renders instead of a logged-in redirect.
    # TRADEOFF (chosen strategy): accounts share this profile's device fingerprint and can
    # be linked by Upwork. To unlink later, give each run its own residential proxy.
    PROFILE_RUN=PROFILE
    log(f"profile {PROFILE_RUN} (warm/reused)")
    async with async_playwright() as p:
        _args=dict(headless=False,
            args=["--disable-blink-features=AutomationControlled","--no-first-run","--no-default-browser-check","--start-maximized"],
            viewport=None,locale="en-US")
        try:
            # real installed Chrome scores higher on fingerprint coherence than bundled Chromium
            ctx=await p.chromium.launch_persistent_context(PROFILE_RUN,channel="chrome",**_args)
            log("launched real Chrome (channel=chrome)")
        except Exception as e:
            log(f"channel=chrome unavailable ({e}); falling back to bundled Chromium")
            ctx=await p.chromium.launch_persistent_context(PROFILE_RUN,**_args)
        page=ctx.pages[0] if ctx.pages else await ctx.new_page()
        # The register VERDICT (code 83 reject vs success) lives in the GraphQL response,
        # NOT in the page body — so the wait loop can't detect it by scraping text. Capture
        # it here into reg{} and let the loop read it. This is what makes the loop fail fast
        # instead of waiting 20 min after a reCAPTCHA reject it never "saw".
        reg={"status":None,"code":None,"err":None,"seen":False}
        async def on_resp(r):
            if "register" in r.url.lower():
                try:
                    j=await r.json(); err=(j.get("errors") or [{}])[0]
                    reg.update(status=r.status, code=err.get("extensions",{}).get("code"),
                               err=err.get("message"), seen=True)
                    log(f"REGISTER_RESP status={r.status} err={err.get('message')} code={reg['code']}")
                except Exception:
                    reg.update(status=r.status, code=None, err=None, seen=True)
                    log(f"REGISTER_RESP status={r.status} (non-json) url={r.url}")
        page.on("response", lambda r: asyncio.create_task(on_resp(r)))
        # Log OUT of Upwork by clearing ONLY upwork.com cookies — the google.com _GRECAPTCHA
        # reputation cookie is a DIFFERENT domain and survives, so we stay "warm" for
        # reCAPTCHA while the signup form renders (no logged-in redirect).
        _logged_out=False
        for dom in [".upwork.com","www.upwork.com","upwork.com"]:
            try: await ctx.clear_cookies(domain=dom); _logged_out=True
            except Exception: pass
        if not _logged_out:  # older API without domain filter: hit the logout endpoint
            try:
                await page.goto("https://www.upwork.com/ab/account-security/logout",wait_until="domcontentloaded",timeout=30000)
                await page.wait_for_timeout(2000)
            except Exception: pass
        log(f"upwork session cleared (via_cookie_filter={_logged_out}); reCAPTCHA reputation kept")
        # WARM the fresh profile (~90s) so reCAPTCHA v3 has same-origin behavioral history
        # + _GRECAPTCHA cookie reputation BEFORE the signup token mints. This is the single
        # biggest lever for a cold per-run profile (no cross-run cookie reputation exists).
        log("warming profile (~90s browsing) for reCAPTCHA reputation...")
        for url in ["https://www.upwork.com/","https://www.upwork.com/nx/find-work/",
                    "https://www.upwork.com/freelance-jobs/"]:
            try: await page.goto(url,wait_until="domcontentloaded",timeout=45000)
            except Exception: pass
            await dismiss_cookies(page)
            for _ in range(6):
                await page.mouse.move(random.uniform(200,1100),random.uniform(200,700),steps=random.randint(10,20))
                await page.mouse.wheel(0,random.randint(200,600))
                await page.wait_for_timeout(random.randint(2500,5000))
        log("warm-up done")
        await page.goto("https://www.upwork.com/nx/signup/?dest=home",wait_until="domcontentloaded",timeout=60000)
        await page.wait_for_timeout(3500); await dismiss_cookies(page)
        # Get past the account-type chooser to the freelancer FORM. Upwork A/B tests two
        # variants of the chooser (a warm/cookied profile skips it entirely):
        #   A) thumbnail buttons — clicking [data-qa=btn-apply-freelancer] advances to the form
        #   B) radio cards + a SEPARATE "Create Account" button — select freelancer, THEN click it
        # Handle both; poll for #first-name-input; dump controls if neither works.
        async def reach_form():
            for attempt in range(7):
                if await page.query_selector("#first-name-input"): return True
                await dismiss_cookies(page)
                # select the freelancer option (same data-qa in both variants; fall back to text)
                for sel in ["[data-qa=btn-apply-freelancer]","button:has-text(\"Freelancer\")",
                            "text=I'm a freelancer","label:has-text(\"freelancer\")"]:
                    el=await page.query_selector(sel)
                    if el:
                        try: await el.click()
                        except Exception: pass
                        await page.wait_for_timeout(1200); break
                if await page.query_selector("#first-name-input"): return True
                # variant B: click the (now enabled) Create Account CTA
                for ca in await page.query_selector_all('button:has-text("Create Account"), '
                          'button:has-text("Create account"), [data-qa=create-account-cta]'):
                    try:
                        if await ca.is_visible() and await ca.is_enabled():
                            await ca.click(); await page.wait_for_timeout(1800); break
                    except Exception: pass
                await page.wait_for_timeout(1500)
            return bool(await page.query_selector("#first-name-input"))

        if not await reach_form():
            ctrls=await page.evaluate("()=>[...document.querySelectorAll('button,a,input')]"
                ".filter(e=>e.offsetParent).map(e=>((e.innerText||e.value||e.getAttribute('data-qa')||'')+'').trim()).filter(Boolean).slice(0,30)")
            log(f"SIGNUP FORM NOT FOUND url={page.url} controls={ctrls} — aborting cleanly (see hybrid_noform.png)")
            try: await page.screenshot(path=os.path.join(CAP,"hybrid_noform.png"),full_page=True)
            except Exception: pass
            while True: await asyncio.sleep(5)
        await dismiss_cookies(page)
        # fill form with HUMANIZED typing (real keystroke telemetry for reCAPTCHA v3)
        await htype(page,"#first-name-input",fn); await page.wait_for_timeout(random.randint(300,700))
        await htype(page,"#last-name-input",ln); await page.wait_for_timeout(random.randint(300,700))
        await htype(page,"#redesigned-input-email",EMAIL); await page.wait_for_timeout(random.randint(400,900))
        await htype(page,"#password-input",PW)
        await dismiss_cookies(page)
        # --- Terms checkbox: it must REGISTER in Vue, not just flip the DOM input.
        #     is_checked() reads the raw <input>, which force-check sets WITHOUT
        #     firing Vue's onChange — so the reactive model stays termsAccepted=false
        #     and the submit button stays disabled even though is_checked()==True.
        #     A real mouse-coordinate click on the LABEL is what Vue actually registers.
        #     The only trustworthy "terms accepted" signal is the button enabling.
        async def check_terms():
            for lab in ["checkbox-terms","checkbox-promo"]:
                try:
                    el=await page.query_selector(f'label#{lab}, label[for="{lab}"], #{lab}')
                    if not el: continue
                    box=await el.bounding_box()
                    if box:
                        await page.mouse.move(box["x"]+12,box["y"]+box["height"]/2,steps=6)
                        await page.wait_for_timeout(120)
                        await page.mouse.click(box["x"]+12,box["y"]+box["height"]/2)
                        await page.wait_for_timeout(350)
                except Exception as e: log(f"{lab} click err {e}")
            # belt-and-suspenders: native .click() on any still-unchecked raw input
            try:
                await page.evaluate("()=>{for(const b of document.querySelectorAll('input[type=checkbox]')){if(!b.checked)b.click();}}")
            except Exception: pass

        async def form_state():
            return await page.evaluate("""()=>{
                const fields=['#first-name-input','#last-name-input','#redesigned-input-email','#password-input']
                    .map(s=>{const e=document.querySelector(s);return {s, has:!!(e&&e.value), valid:e?e.checkValidity():null};});
                const boxes=[...document.querySelectorAll('input[type=checkbox]')].map(b=>b.checked);
                const b=document.querySelector('#button-submit-form');
                const dis = b? (b.disabled||b.getAttribute('aria-disabled')==='true'||b.classList.contains('air3-btn-disabled')) : null;
                return {fields, boxes, btnDisabled:dis};
            }""")

        await check_terms()
        # POLL up to ~8s for the button to ENABLE — that is the proof Vue accepted the
        # terms box. This is the real "do it before the last step" gate: we do not fire
        # the submit click until the form itself reports ready.
        enabled=False
        for t in range(16):
            st=await form_state()
            if st["btnDisabled"] is False:
                enabled=True; log(f"button ENABLED after {t*0.5:.1f}s boxes={st['boxes']}"); break
            empty=[f["s"].split('-')[0].lstrip('#') for f in st["fields"] if not f["has"]]
            invalid=[f["s"].split('-')[0].lstrip('#') for f in st["fields"] if f["valid"] is False]
            if t%2==0: log(f"btn disabled t={t*0.5:.1f}s boxes={st['boxes']} empty={empty} invalid={invalid}")
            if not all(st["boxes"]) and t in (2,6,10): await check_terms()  # re-check if a box dropped
            await page.wait_for_timeout(500)
        st=await form_state()
        log(f"FORM FILLED — boxes={st['boxes']} btnDisabled={st['btnDisabled']}")
        if enabled:
            # fresh in-viewport mouse motion + dwell immediately before the click
            for _ in range(4):
                await page.mouse.move(random.uniform(250,1000),random.uniform(250,650),steps=random.randint(10,22))
                await page.wait_for_timeout(random.randint(150,350))
            try:
                btn=await page.query_selector("#button-submit-form")
                await btn.scroll_into_view_if_needed()
                await hmove_click(page,btn)  # trusted mouse trajectory + down/up mints the token on a real click
                log("auto hmove-click fired (button was enabled)")
            except Exception as e: log(f"hmove click err {e}")
            await page.wait_for_timeout(2000)
        else:
            log("button NEVER enabled in 8s — see empty/invalid fields above; reCAPTCHA may also gate it. Click manually if needed.")
        log("================ submit fired — awaiting register verdict (from network, not body) ===")
        # Drive the wait off the NETWORK verdict in reg{} (the GraphQL response), NOT page
        # body text — that's why it used to hang 20 min after a reject it never "saw".
        created=False; rejects=0; MAX_AUTO=2; TICK=1.5
        human_window=False; human_left=0; HUMAN_SECS=120
        while True:
            await page.wait_for_timeout(int(TICK*1000))
            u=page.url
            if classify_signup_state(u,"")=="created" or (reg["seen"] and reg["status"]==200 and not reg["code"]):
                created=True; log(f"ACCOUNT CREATED url={page.url}")
                save_account("created", final_url=page.url); break
            if reg["seen"] and reg["code"]==83:
                reg["seen"]=False; rejects+=1   # consume this verdict
                if rejects<=MAX_AUTO:
                    log(f"reCAPTCHA reject code=83 [{rejects}/{MAX_AUTO}] — trusted retry")
                    try:
                        await check_terms()
                        btn=await page.query_selector("#button-submit-form")
                        if btn and not await btn.is_disabled():
                            for _ in range(3):
                                await page.mouse.move(random.uniform(250,1000),random.uniform(250,650),steps=random.randint(10,20))
                                await page.wait_for_timeout(random.randint(150,300))
                            await hmove_click(page,btn)
                    except Exception: pass
                    continue
                elif not human_window:
                    human_window=True; human_left=int(HUMAN_SECS/TICK)
                    log(f"AUTO-CLICK CANNOT PASS reCAPTCHA on this cold profile. You have {HUMAN_SECS}s to click 'Create my account' yourself, then I STOP (no 20-min hang).")
            elif reg["seen"] and reg["code"]:
                log(f"register error code={reg['code']} err={reg['err']} — not a reCAPTCHA issue; stopping")
                save_account("register_error", final_url=page.url, err=str(reg['err']), code=str(reg['code'])); break
            if human_window:
                human_left-=1
                if human_left>0 and human_left%20==0: log(f"waiting for your manual click... {int(human_left*TICK)}s left")
                if human_left<=0:
                    log("STOP: reCAPTCHA blocked and no manual click in time.")
                    save_account("blocked_recaptcha", final_url=page.url); break
        if not created:
            log("not created (reCAPTCHA blocked / register error) — closing cleanly, no hang")
            try: await page.screenshot(path=os.path.join(CAP,"hybrid_blocked.png"),full_page=True)
            except Exception: pass
            try: await ctx.close()
            except Exception: pass
            return

        # email verify — ALWAYS run after creation. The post-signup URL varies
        # (registration-success / please-verify), and create-profile bounces back to
        # please-verify until the emailed link is opened. get_verify_link polls the worker.
        log("fetching email verify link...")
        link=get_verify_link(tries=40)
        log(f"verify link: {link}")
        if link:
            try:
                await page.goto(link,wait_until="domcontentloaded",timeout=60000); await page.wait_for_timeout(5000)
            except Exception as e: log(f"verify open err {e}")
        else:
            log("NO verify link from email worker (~2min) — account exists but stays UNVERIFIED")
            save_account("created_unverified", final_url=page.url)
            try: await ctx.close()
            except Exception: pass
            return
        log(f"after verify url={page.url}")

        # onboarding — consolidated, proven flow shared with onboard.py.
        # Set ONBOARD_PHONE=1 to also do the phone/SMS step (rents a TextVerified number).
        from onboard import run_onboarding
        await page.goto("https://www.upwork.com/nx/create-profile/",wait_until="domcontentloaded",timeout=60000)
        await page.wait_for_timeout(4000)
        await click_text(page,"Get started"); await page.wait_for_timeout(3000)
        final_url=await run_onboarding(page, do_phone=(os.environ.get("ONBOARD_PHONE")=="1"))
        save_account("profile_done" if "create-profile" not in final_url else "onboarding_partial", final_url=final_url)
        await page.screenshot(path=os.path.join(CAP,"hybrid_done.png"),full_page=True)
        log(f"FINISHED url={final_url}")
        while True: await asyncio.sleep(5)

asyncio.run(main())
