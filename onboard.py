#!/usr/bin/env python3
"""FAST onboarding iteration harness. Logs into an already-created+verified account
on a dedicated warm 'chrome-onboard' profile and drives the create-profile flow to
completion, with rich per-step diagnostics. Lets me fix each onboarding step without
re-creating an account each time. Once this completes E2E, the handlers get ported
into hybrid.py. Phone/SMS (paid TextVerified) only runs with --phone.

Usage: python3 onboard.py [email] [password] [--phone]
"""
import asyncio, os, random, sys, json, time
from patchright.async_api import async_playwright
from curl_cffi import requests as cffi
import config
from signup_utils import normalize_phone, parse_sms_code

PROFILE=config.PROFILE+"-onboard"; CAP=config.CAP; FACE=config.FACE
TV_KEY=config.TV_API_KEY; TV_USER=config.TV_USER; TVB=config.TV_BASE
args=[a for a in sys.argv[1:] if not a.startswith("--")]
DO_PHONE="--phone" in sys.argv
EMAIL=args[0] if len(args)>0 else "lucas.smith.ftsqwz@eldenstats.com"
PW=args[1] if len(args)>1 else "CCepzeu26!"
BIO=("Experienced customer service representative skilled in email, chat and phone support, "
     "problem solving, and fast professional resolution of client issues.")
def log(m):
    try: print(f">>> {m}", flush=True)
    except Exception: print((">>> "+str(m)).encode("ascii","replace").decode(), flush=True)

# ---------- TextVerified (phone/SMS) ----------
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

async def hmove_click(page, el):
    if el is None: return False
    try: await el.scroll_into_view_if_needed(timeout=4000)
    except Exception: pass
    box=await el.bounding_box()
    if not box:
        try: await el.click(force=True, timeout=5000); return True
        except Exception: return False
    tx=box["x"]+box["width"]/2+random.uniform(-4,4); ty=box["y"]+box["height"]/2+random.uniform(-3,3)
    await page.mouse.move(tx-random.uniform(30,70), ty-random.uniform(20,50), steps=8)
    await page.mouse.move(tx, ty, steps=random.randint(12,22))
    await page.wait_for_timeout(random.randint(100,250))
    await page.mouse.down(); await page.wait_for_timeout(random.randint(40,90)); await page.mouse.up()
    return True

async def click_text(page,*texts):
    for t in texts:
        for el in await page.query_selector_all(f'button:has-text("{t}"), a:has-text("{t}")'):
            try:
                if await el.is_visible() and await el.is_enabled(): await el.click(timeout=5000); return t
            except Exception: continue
    return None

async def fill_first(page, sels, value, typed=True):
    for sel in sels:
        try:
            el=await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click(); await el.fill("")
                if typed:
                    await page.keyboard.type(value, delay=8)  # FAST keystrokes (still fires input events)
                else: await el.fill(value)
                return True
        except Exception: pass
    return False

async def dump(page, label):
    d=await page.evaluate(r"""()=>{
        const vis=e=>e.offsetParent!==null;
        const txt=e=>((e.innerText||e.value||'')+'').trim().slice(0,40);
        return {
          h:(document.querySelector('[data-qa=step-title],h1,h2')||{}).innerText||'',
          inputs:[...document.querySelectorAll('input,textarea')].filter(vis).map(e=>({t:e.type||e.tagName,ph:e.placeholder||'',name:e.name||'',dq:e.getAttribute('data-qa')||''})).slice(0,15),
          checks:[...document.querySelectorAll('input[type=checkbox],input[type=radio]')].filter(vis).map(e=>({near:(e.closest('label,li,div')||{}).innerText?.trim().slice(0,35),checked:e.checked})).slice(0,15),
          clickable:[...document.querySelectorAll('[data-qa]')].filter(vis).map(e=>({dq:e.getAttribute('data-qa'),tag:e.tagName,txt:txt(e)})).filter(x=>x.txt).slice(0,25),
          buttons:[...document.querySelectorAll('button')].filter(vis).map(e=>({txt:txt(e),dq:e.getAttribute('data-qa')||'',dis:e.disabled})).slice(0,15),
          errors:[...document.querySelectorAll('[class*=error i],[role=alert],[class*=danger i]')].filter(e=>e.offsetParent&&e.innerText&&e.innerText.trim().length<70).map(e=>e.innerText.trim()).slice(0,8),
        };
    }""")
    log(f"DUMP[{label}] {json.dumps(d)[:2000]}")

# ---------- per-step handlers ----------
async def step_categories(page):
    # left = pick 1 category; right = pick 1-3 specialties; then Next
    cat=await page.query_selector('text="Customer Service"')
    if cat:
        await cat.click(); await page.wait_for_timeout(700)
    await dump(page,"specialties")  # see what the right column actually is
    # try clickable specialty items in the right column
    picked=0
    for sel in ['[data-qa=specialty] ', '[data-qa*=specialty]', '[role=checkbox]', 'label']:
        for el in await page.query_selector_all(sel):
            try:
                t=(await el.inner_text() or "").strip()
                if t and await el.is_visible() and 2<len(t)<45 and t!="Customer Service":
                    await el.click(); picked+=1; await page.wait_for_timeout(500)
                    if picked>=1: break
            except Exception: pass
        if picked>=1: break
    if picked==0:  # fallback: any checkbox
        for s in await page.query_selector_all("input[type=checkbox]"):
            try:
                if await s.is_visible() and not await s.is_checked(): await s.check(force=True); picked+=1; break
            except Exception: pass
    await page.wait_for_timeout(800)
    c=await click_text(page,"Next, add your skills","Next")
    log(f"categories: picked={picked} next={c}")
    return c is not None

async def step_skills(page):
    inp=await page.query_selector("input[type=search]")
    if inp:
        await inp.click()
        await page.keyboard.type("Customer Service", delay=12)
        await page.wait_for_timeout(900)
        opt=None
        for sel in ["li[role=option]","[role=option]","[role=listbox] li"]:
            for e in await page.query_selector_all(sel):
                if await e.is_visible(): opt=e; break
            if opt: break
        if opt: await opt.click(); log("skill picked")
        await page.wait_for_timeout(1000)
    c=await click_text(page,"Next, your profile title","Next, write a bio","Next")
    log(f"skills: next={c}")
    return c is not None

async def step_title(page):
    await fill_first(page,['input[type=text]','input[data-qa*=title]'],"Customer Service Representative")
    c=await click_text(page,"Next, write a bio","Next, add your experience","Next")
    log(f"title: next={c}")
    return c is not None

async def step_bio(page):
    for ta in await page.query_selector_all("textarea"):
        try:
            if await ta.is_visible(): await ta.fill(BIO); break
        except Exception: pass
    c=await click_text(page,"Next, set your rate","Next")
    log(f"bio: next={c}")
    return c is not None

async def step_rate(page):
    # hourly-rate field has placeholder "$0.00"; fill the first editable one
    filled=False
    for sel in ['input[placeholder="$0.00"]','input[placeholder*="0.00"]','input[type=text]','input[type=number]','input:not([type])']:
        for inp in await page.query_selector_all(sel):
            try:
                if await inp.is_visible() and (await inp.get_attribute("readonly")) is None and not await inp.is_disabled():
                    await inp.click(); await inp.fill(""); await page.keyboard.type("30"); filled=True; break
            except Exception: pass
        if filled: break
    await page.wait_for_timeout(600)
    c=await click_text(page,"Next, almost done","Review your profile","Next","Continue")
    log(f"rate: filled={filled} next={c}")
    return c is not None

async def step_languages(page):
    await dump(page,"languages")
    # open the English-proficiency control — only ever click a VISIBLE element, guarded
    opened=False
    for sel in ['button:has-text("My level is")','[role=combobox]','select','[data-qa*=level]','[data-qa*=proficiency]','button:has-text("Select")']:
        for dd in await page.query_selector_all(sel):
            try:
                if await dd.is_visible(): await dd.click(timeout=4000); opened=True; await page.wait_for_timeout(800); break
            except Exception: pass
        if opened: break
    if opened:
        picked=False
        for o in await page.query_selector_all('li[role=option],[role=option],option'):
            try:
                if await o.is_visible() and "fluent" in (await o.inner_text()).lower(): await o.click(); picked=True; break
            except Exception: pass
        if not picked:
            try:
                for _ in range(2): await page.keyboard.press("ArrowDown"); await page.wait_for_timeout(200)
                await page.keyboard.press("Enter")
            except Exception: pass
        await page.wait_for_timeout(600)
    c=await click_text(page,"Next","Continue","Skip for now")
    log(f"languages: opened={opened} next={c}")
    return c is not None

async def upload_photo(page):
    # set the (often hidden) file input directly; reveal it via the uploader button if
    # needed; then confirm the crop modal. Photo is required to publish on the 10/10 page.
    try:
        fin=await page.query_selector_all("input[type=file]")
        if not fin:
            ob=await page.query_selector('[data-qa=open-loader],[data-qa=portrait-uploader-select-btn]')
            if ob:
                try: await ob.click(timeout=3000)
                except Exception: pass
                await page.wait_for_timeout(1200); fin=await page.query_selector_all("input[type=file]")
        if fin and os.path.exists(FACE):
            await fin[-1].set_input_files(FACE); await page.wait_for_timeout(3000)
            for _ in range(4):  # wait for crop modal, confirm
                c=await click_text(page,"Attach photo","Save","Apply","Crop & save","Crop","Done")
                if c: log(f"photo confirmed via '{c}'"); await page.wait_for_timeout(2000); return True
                await page.wait_for_timeout(1200)
            log("photo: file set but no confirm button found")
        else:
            log(f"photo: no file input (have FACE={os.path.exists(FACE)})")
    except Exception as e: log(f"photo err {str(e)[:60]}")
    return False

async def step_location(page):
    # final page: DOB + address (street autocomplete OR discrete) + photo. Every click
    # is guarded with a timeout so a hidden/unstable element can't hang the step.
    async def safe_fill(sels, value):
        for sel in sels:
            try:
                el=await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click(timeout=4000); await el.fill("")
                    await page.keyboard.type(value, delay=8)
                    return True
            except Exception: pass
        return False
    # Google-Places autocomplete: type, let suggestions render, then ArrowDown+Enter to
    # SELECT the first one (keyboard select is robust to the dropdown's DOM structure).
    # Without a SELECTED suggestion Upwork shows "address could not be found".
    async def autocomplete(sel, text, label):
        el=await page.query_selector(sel)
        if not el or not await el.is_visible(): return False
        try:
            try: await el.scroll_into_view_if_needed(timeout=3000)
            except Exception: pass
            await el.focus()  # focus the input DIRECTLY (coordinate-independent) so the
            # keystrokes can't leak into the DOB field under a date-picker overlay
            await page.keyboard.press("Control+A"); await page.keyboard.press("Delete")
            await page.keyboard.type(text, delay=25)  # autocomplete needs real keystrokes, but fast
            await page.wait_for_timeout(1400)          # let Google-Places suggestions render
            try: await page.screenshot(path=os.path.join(CAP,f"onb_dd_{label}.png"))
            except Exception: pass
            opts=await page.evaluate("""()=>[...document.querySelectorAll('[role=option],li[role=option],[role=listbox] li,[class*=menu i] li,[class*=suggestion i],[class*=dropdown i] li,[class*=autocomplete i] li')].filter(e=>e.offsetParent&&(e.innerText||'').trim()).map(e=>({t:e.tagName,r:e.getAttribute('role'),dq:e.getAttribute('data-qa')||'',txt:(e.innerText||'').trim().slice(0,50)})).slice(0,10)""")
            log(f"{label} suggestions: {json.dumps(opts)[:700]}")
            for s in ['[role=option]','li[role=option]','[role=listbox] li','[class*=suggestion i]','[class*=autocomplete i] li','[class*=menu i] li']:
                for o in await page.query_selector_all(s):
                    try:
                        t=(await o.inner_text() or '').strip()
                        if await o.is_visible() and len(t)>=5:
                            await o.click(timeout=3000); log(f"{label} clicked: {t[:45]}"); await page.wait_for_timeout(900); return True
                    except Exception: pass
            await page.keyboard.press("ArrowDown"); await page.wait_for_timeout(450); await page.keyboard.press("Enter")
            await page.wait_for_timeout(900); log(f"{label} keyboard-fallback"); return True
        except Exception as e: log(f"{label} err {str(e)[:50]}"); return False

    # ADDRESS FIRST — before touching DOB, so no date-picker popup covers these fields.
    await autocomplete('input[placeholder*="street" i]',"1247 Maple Avenue, Austin, TX","street")
    await page.wait_for_timeout(1000)
    try:
        city=await page.query_selector('input[placeholder*="city" i]')
        if city and not (await city.input_value()).strip(): await autocomplete('input[placeholder*="city" i]',"Austin","city")
    except Exception: pass
    try:
        st=await page.query_selector('[data-qa=address-state-input]')
        if st and not (await st.input_value()).strip(): await safe_fill(['[data-qa=address-state-input]','input[placeholder*="state" i]'],"Texas")
    except Exception: pass
    try:
        z=await page.query_selector('[data-qa=zip]')
        if z and not (await z.input_value()).strip(): await safe_fill(['[data-qa=zip]','input[placeholder*="zip" i]'],"78701")
    except Exception: pass
    await upload_photo(page)
    # DOB LAST, then CLOSE the calendar popup (Escape + click the heading) so it can't
    # cover the phone field below it.
    await safe_fill(['input[placeholder*="mm/dd" i]','input[placeholder*="yyyy" i]','input[aria-label*="birth" i]'],"05/14/1995")
    try:
        await page.keyboard.press("Escape")
        h=await page.query_selector('[data-qa=step-title], h2, h1')
        if h: await h.click(timeout=2000)
    except Exception: pass
    await page.wait_for_timeout(700)
    return True

_DONE={}  # run the final location+phone step exactly once (re-running corrupts filled fields)
_TV_STATE={"vid":None,"num":None,"s":None,"h":None}  # rent at most ONCE per run
async def step_phone(page):
    # final step: fill the tel field + SMS verify. Rents at most one TextVerified number
    # per run (or reuses TV_REUSE_VID/TV_REUSE_NUM from env to avoid spending on debug).
    tel=await page.query_selector('input[type=tel], input[placeholder*="number" i], input[placeholder*="phone" i]')
    if not tel:
        log("no tel field present — skipping phone (no rental)"); return False
    if _TV_STATE["num"] is None:
        rv=os.environ.get("TV_REUSE_VID"); rn=os.environ.get("TV_REUSE_NUM")
        if rv and rn:
            s,h=tv(); _TV_STATE.update(vid=rv,num=rn,s=s,h=h); log(f"REUSE TV vid={rv} number={rn} (no rental)")
        else:
            s,h=tv(); vid,num=tv_number(s,h); _TV_STATE.update(vid=vid,num=num,s=s,h=h); log(f"TV vid={vid} number={num}")
    s,h,vid,number=_TV_STATE["s"],_TV_STATE["h"],_TV_STATE["vid"],_TV_STATE["num"]
    digits=normalize_phone(number)
    try:
        try: await tel.scroll_into_view_if_needed(timeout=3000)
        except Exception: pass
        await tel.focus(); await page.keyboard.press("Control+A"); await page.keyboard.press("Delete")
        for ch in digits: await page.keyboard.type(ch); await page.wait_for_timeout(50)
    except Exception as e: log(f"phone fill err {str(e)[:60]}")
    await page.wait_for_timeout(1000)
    c=await click_text(page,"Review your profile","Submit profile","Next","Continue")
    log(f"clicked Review/Submit={c}"); await page.wait_for_timeout(4000)
    # phone-verify modal/page
    await click_text(page,"Send code","Send Code","Verify phone number","Verify"); log("Send code clicked"); await page.wait_for_timeout(2500)
    code=tv_code(s,h,vid); log(f"SMS CODE={code}")
    if code:
        for sel in ["input[autocomplete=one-time-code]","input[inputmode=numeric]","input[name*=code i]","input[maxlength='6']","input[maxlength='4']"]:
            el=await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click(); await el.fill("")
                for ch in str(code): await page.keyboard.type(ch); await page.wait_for_timeout(110)
                break
        await page.wait_for_timeout(1500)
        await click_text(page,"Verify","Confirm","Submit","Done","Next"); await page.wait_for_timeout(5000)
    log(f"after phone verify url={page.url}")
    return True

async def run_onboarding(page, do_phone=False):
    """Drive the Upwork create-profile wizard to completion (assumes already logged in,
    on/near create-profile). Phone/SMS step only runs if do_phone=True. Importable by
    hybrid.py so account creation + full onboarding happen in ONE clean session."""
    prev_url=""; same=0
    for i in range(40):
        await page.wait_for_timeout(450); url=page.url   # FAST: reCAPTCHA already passed; no need to dawdle post-creation
        short=url.split("/create-profile/")[-1].split("?")[0] if "create-profile/" in url else url
        if url==prev_url: same+=1
        else: same=0; prev_url=url
        if same>=4:
            log(f"STUCK on {short} after {same} tries"); await dump(page,f"stuck-{short}")
            try: await page.screenshot(path=os.path.join(CAP,f"onb_stuck_{short.replace('/','_')}.png"))
            except Exception: pass
            break
        log(f"[{i}] step={short}")
        # nuke any OneTrust cookie banner so it can't intercept clicks (it reappears on new pages)
        try: await page.evaluate("()=>{for(const id of ['onetrust-banner-sdk','onetrust-consent-sdk']){const e=document.getElementById(id); if(e) e.remove();}}")
        except Exception: pass
        # welcome screen ("Hey <name>. Ready for your next big opportunity?") — enter the wizard
        gs=await page.query_selector('[data-qa=get-started-btn]')
        if gs and await gs.is_visible():
            try: await gs.click(timeout=8000)
            except Exception: await gs.click(force=True, timeout=5000)
            log("clicked Get started -> entering wizard"); await page.wait_for_timeout(500); continue
        if "submit" in short or "profile-submit" in short:
            log("REACHED SUBMIT/REVIEW"); break
        handled=False
        try:
            if "resume-import" in short:
                b=await page.query_selector('[data-qa=resume-fill-manually-btn]')
                if b: await b.click(); handled=True
            elif "categories" in short: handled=await step_categories(page)
            elif "skills" in short: handled=await step_skills(page)
            elif "title" in short: handled=await step_title(page)
            elif "overview" in short or "bio" in short: handled=await step_bio(page)
            elif "rate" in short or "rates" in short: handled=await step_rate(page)
            elif "languages" in short: handled=await step_languages(page)
            elif "location" in short:
                if not _DONE.get("loc"):
                    _DONE["loc"]=True
                    await step_location(page)
                    if do_phone:
                        handled=await step_phone(page)
                    else:
                        c=await click_text(page,"Review your profile","Submit profile","Next","Continue")
                        handled=c is not None; log(f"location next={c}")
                else:
                    c=await click_text(page,"Review your profile","Submit profile")
                    log(f"location re-attempt advance={c}"); handled=False
        except Exception as e:
            log(f"step handler EXC on {short}: {str(e)[:120]}"); await dump(page,f"exc-{short}"); handled=False
        if not handled:
            c=await click_text(page,"Skip for now","Skip","Next","Continue","Save and continue","Looks good")
            if c is None: await dump(page,f"unknown-{short}")
            log(f"[{i}] generic step={short} clicked={c}")
    log(f"FINISHED onboarding loop at url={page.url}")
    return page.url

async def main():
    log(f"onboard account={EMAIL} phone={DO_PHONE}")
    async with async_playwright() as p:
        _a=dict(headless=False,args=["--disable-blink-features=AutomationControlled","--no-first-run","--no-default-browser-check","--start-maximized"],viewport=None,locale="en-US")
        try: ctx=await p.chromium.launch_persistent_context(PROFILE,channel="chrome",**_a)
        except Exception: ctx=await p.chromium.launch_persistent_context(PROFILE,**_a)
        page=ctx.pages[0] if ctx.pages else await ctx.new_page()
        # brief warm-up so login reCAPTCHA scores ok on this profile
        try:
            await page.goto("https://www.upwork.com/",wait_until="domcontentloaded",timeout=45000)
            for _ in range(3):
                await page.mouse.move(random.uniform(200,1000),random.uniform(200,600),steps=12)
                await page.mouse.wheel(0,random.randint(200,500)); await page.wait_for_timeout(1500)
        except Exception: pass
        await page.goto("https://www.upwork.com/nx/create-profile/",wait_until="domcontentloaded",timeout=60000)
        await page.wait_for_timeout(3500)
        if "login" in page.url:
            log("logging in...")
            # TYPE creds char-by-char so Vue fires input events and enables the buttons
            await fill_first(page,["#login_username",'input[name="login[username]"]','input[type=email]','input[type=text]'],EMAIL,typed=True)
            await page.wait_for_timeout(600); await click_text(page,"Continue")
            try: await page.wait_for_selector("#login_password, input[type=password]",timeout=15000)
            except Exception: pass
            await page.wait_for_timeout(1200)
            await fill_first(page,["#login_password",'input[name="login[password]"]','input[type=password]'],PW,typed=True)
            await page.wait_for_timeout(900); await click_text(page,"Log in","Log In","Continue")
            await page.wait_for_timeout(7000)
            log(f"after login url={page.url}")
            if "login" in page.url:
                log("LOGIN did not complete (checkpoint/captcha?) — dumping"); await dump(page,"login-stuck")
                await page.screenshot(path=os.path.join(CAP,"onb_login_stuck.png"));
            if "create-profile" not in page.url:
                await page.goto("https://www.upwork.com/nx/create-profile/",wait_until="domcontentloaded",timeout=60000); await page.wait_for_timeout(4000)
        await click_text(page,"Get started"); await page.wait_for_timeout(3000)
        await run_onboarding(page, DO_PHONE)
        await page.screenshot(path=os.path.join(CAP,"onb_final.png"),full_page=True)
        while True: await asyncio.sleep(5)

if __name__=="__main__":
    asyncio.run(main())
