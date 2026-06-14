#!/usr/bin/env python3
"""Upwork freelancer signup via SeleniumBase UC mode (Michael Mintz) — a maximally
UNDETECTED, higher-TRUST Chrome. Hypothesis: patchright's lower browser trust is what
gets bot-created accounts denied the phone-verification SMS; a higher-trust UC-mode
session may dispatch it. UC mode also handles Cloudflare/Turnstile via real
PyAutoGUI clicks (uc_gui_click_captcha) if a challenge appears.

Pure-HTTP helpers (eldenstats email worker, TextVerified) are reused unchanged.
Run on Windows python:  python.exe sb_signup.py  [--phone]
Prints >>> markers for monitoring.
"""
import os, sys, time, random, string, json
from seleniumbase import SB
import config
import account_store
from signup_utils import extract_verify_link, normalize_phone, parse_sms_code
from curl_cffi import requests as cffi

PIPELINE = "seleniumbase-uc"

DO_PHONE = "--phone" in sys.argv
WORKER = config.EMAIL_WORKER
TV_KEY = config.TV_API_KEY; TV_USER = config.TV_USER; TVB = config.TV_BASE
CAP = config.CAP; FACE = config.FACE
FIRST=["James","Emma","Liam","Olivia","Noah","Ava","Ethan","Sophia","Lucas","Mia","Henry","Ella","Jack","Zoe"]
LAST=["Smith","Johnson","Brown","Garcia","Miller","Davis","Wilson","Clark","Lewis","Walker","Hall","Young","King","Reed"]
fn=random.choice(FIRST); ln=random.choice(LAST)
tag="".join(random.choices(string.ascii_lowercase+string.digits,k=6))
EMAIL=f"{fn.lower()}.{ln.lower()}.{tag}@{config.EMAIL_DOMAIN}"
PW="".join(random.choices(string.ascii_uppercase,k=2))+"".join(random.choices(string.ascii_lowercase,k=5))+str(random.randint(10,99))+"!"
BIO=("Experienced customer service representative skilled in email, chat and phone support, "
     "problem solving, and fast professional resolution of client issues.")
def log(m):
    try: print(f">>> {m}", flush=True)
    except Exception: print((">>> "+str(m)).encode("ascii","replace").decode(), flush=True)

def save(status, **extra):
    """Record this account's current status to the local ledger + Postgres."""
    return account_store.record(status, EMAIL, PW, first=fn, last=ln, pipeline=PIPELINE, **extra)

# ---------- HTTP helpers (browser-independent) ----------
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
        log(f"sms {i*delay}s state={v.get('state')}"); time.sleep(delay)
    return None

# ---------- SB helpers ----------
def kill_cookies(sb):
    try: sb.execute_script("for(const id of ['onetrust-banner-sdk','onetrust-consent-sdk']){const e=document.getElementById(id); if(e)e.remove();}")
    except Exception: pass
def safe_click_text(sb, *texts):
    for t in texts:
        try:
            if sb.is_element_visible(f'button:contains("{t}")'):
                sb.click(f'button:contains("{t}")'); return t
        except Exception: pass
        try:
            if sb.is_element_visible(f'a:contains("{t}")'):
                sb.click(f'a:contains("{t}")'); return t
        except Exception: pass
    return None
def present(sb, sel):
    try: return sb.is_element_visible(sel)
    except Exception: return False


def run(sb):
    log(f"identity {fn} {ln} <{EMAIL}> pw={PW} (SeleniumBase UC)")
    open(os.path.join(CAP,"run_creds.txt"),"w").write(f"{EMAIL}\n{PW}\n")
    save("started")
    # open signup with UC stealth (disconnect during load so automation isn't observed)
    sb.uc_open_with_reconnect("https://www.upwork.com/nx/signup/?dest=home", 6)
    sb.sleep(3); kill_cookies(sb)
    # in case a Cloudflare/Turnstile interstitial shows
    try: sb.uc_gui_click_captcha()
    except Exception: pass
    sb.sleep(1); kill_cookies(sb)

    # choose Freelancer + WAIT for the form (Upwork A/B-tests two chooser variants:
    # A = thumbnail button [btn-apply-freelancer]; B = radio cards + "Create Account")
    got_form=False
    for attempt in range(3):
        try:
            if present(sb,'[data-qa=btn-apply-freelancer]'):
                sb.click('[data-qa=btn-apply-freelancer]')
            elif present(sb,'input[type=radio]'):
                try: sb.js_click('input[type=radio]')
                except Exception: pass
                safe_click_text(sb,"Create Account","Create account","Apply as a freelancer","Continue")
        except Exception as e: log(f"freelancer click err {str(e)[:50]}")
        sb.sleep(3); kill_cookies(sb)
        try:
            sb.wait_for_element_visible("#first-name-input", timeout=8); got_form=True; break
        except Exception:
            log(f"form not ready (attempt {attempt}) url={sb.get_current_url()}")
            try: sb.uc_gui_click_captcha()
            except Exception: pass
            sb.sleep(2)
    if not got_form:
        sb.save_screenshot(os.path.join(CAP,"sb_noform.png")); log("NO FORM — aborting this run")
        save("no_form", final_url=sb.get_current_url()); return

    # fill the form
    try:
        sb.type("#first-name-input", fn)
        sb.type("#last-name-input", ln)
        sb.type("#redesigned-input-email", EMAIL)
        sb.type("#password-input", PW)
    except Exception as e: log(f"fill err {e}")
    kill_cookies(sb)
    # check the (required) terms + promo checkboxes
    try:
        sb.execute_script("document.querySelectorAll('input[type=checkbox]').forEach(c=>{if(!c.checked)c.click();});")
    except Exception: pass
    sb.sleep(1)
    log("form filled — clicking Create my account (UC trusted click)")
    try: sb.uc_click("#button-submit-form")
    except Exception:
        try: sb.click("#button-submit-form")
        except Exception as e: log(f"submit err {e}")
    sb.sleep(8)
    try: sb.uc_gui_click_captcha()   # if a challenge gates the submit
    except Exception: pass
    sb.sleep(4)
    url=sb.get_current_url(); log(f"after submit url={url}")
    if "registration-success" not in url and "create-profile" not in url and "verify" not in url:
        sb.save_screenshot(os.path.join(CAP,"sb_after_submit.png"))
        body=""
        try: body=sb.get_text("body").lower()
        except Exception: pass
        log(f"NOT CREATED — likely score/checkpoint. body has 'score'={'score' in body}")
        save("not_created", final_url=url, score_in_body=("score" in body)); return
    log(f"ACCOUNT CREATED <{EMAIL}>")
    save("created", final_url=url)

    # email verify
    log("fetching verify link...")
    link=get_verify_link()
    log(f"verify link: {link}")
    if link:
        sb.uc_open_with_reconnect(link, 4); sb.sleep(4)
    log(f"after verify url={sb.get_current_url()}")
    save("verified" if link else "created_unverified", final_url=sb.get_current_url())

    # onboarding (best-effort, known steps)
    sb.uc_open_with_reconnect("https://www.upwork.com/nx/create-profile/", 2); sb.sleep(3); kill_cookies(sb)
    prev=""; same=0
    for i in range(40):
        sb.sleep(0.4); kill_cookies(sb)
        url=sb.get_current_url()
        short=url.split("/create-profile/")[-1].split("?")[0] if "create-profile/" in url else url
        if short==prev: same+=1
        else: same=0; prev=short
        if same>=4:
            log(f"STUCK on {short} after {same} tries"); sb.save_screenshot(os.path.join(CAP,f"sb_stuck_{short.replace('/','_') or 'welcome'}.png"))
            try:
                info=sb.execute_script("return [...document.querySelectorAll('li,button,[role],input,label')].filter(e=>e.offsetParent).slice(0,45).map(e=>e.tagName+'|'+(e.getAttribute('role')||'')+'|dq='+(e.getAttribute('data-qa')||'')+'|'+(e.textContent||'').trim().slice(0,28))")
                log("STUCK_DOM "+json.dumps(info)[:1800])
            except Exception: pass
            break
        log(f"[{i}] step={short}")
        if present(sb,'[data-qa=get-started-btn]'):
            try: sb.uc_click('[data-qa=get-started-btn]')
            except Exception: sb.click('[data-qa=get-started-btn]')
            log("clicked Get started"); sb.sleep(1); continue
        if "submit" in short or "profile-submit" in short: log("REACHED SUBMIT/REVIEW"); break
        handled=False
        try:
            if "resume-import" in short:
                # MUST pick "Fill out manually" to advance (Skip just re-renders this step)
                for sel in ['[data-qa=resume-fill-manually-btn]','button:contains("Fill out manually")','a:contains("Fill out manually")']:
                    if present(sb,sel):
                        try: sb.uc_click(sel)
                        except Exception: sb.click(sel)
                        handled=True; break
            elif "categories" in short:
                # 1) select the LEFT category with a REAL click on the exact-text element
                for csel in ['//span[normalize-space(text())="Customer Service"]','//*[normalize-space(text())="Customer Service"]']:
                    try: sb.click(csel); break
                    except Exception: continue
                sb.sleep(1)   # specialties render on the right
                # 2) pick the FIRST specialty (real click on its checkbox/label)
                picked=False
                for spsel in ['//*[contains(text(),"Tech Support")]','//*[contains(text(),"Community")]','input[type=checkbox]']:
                    try:
                        if sb.is_element_visible(spsel):
                            try: sb.click(spsel)
                            except Exception: sb.js_click(spsel)
                            picked=True; break
                    except Exception: pass
                log(f"categories picked_specialty={picked}")
                sb.sleep(1.2)
                handled=safe_click_text(sb,"Next, add your skills","Next") is not None
            elif "skills" in short:
                # type the skill, wait for the typeahead, then click the FIRST real option.
                # at least 1 skill must be added or "Next" stays disabled.
                if present(sb,"input[type=search]"):
                    try: sb.click("input[type=search]")
                    except Exception: pass
                    sb.type("input[type=search]","Customer Service"); sb.sleep(1.5)
                    picked=False
                    for osel in ['li[role=option]','[role=option]','[role=listbox] li','[class*=menu i] li']:
                        try:
                            if sb.is_element_visible(osel):
                                try: sb.js_click(osel)
                                except Exception: sb.click(osel)
                                picked=True; break
                        except Exception: pass
                    if not picked:
                        # keyboard fallback: ArrowDown + Enter selects the highlighted option
                        try: sb.execute_script("const i=document.querySelector('input[type=search]'); i&&i.focus();")
                        except Exception: pass
                        try:
                            from selenium.webdriver.common.keys import Keys
                            sb.send_keys("input[type=search]", Keys.ARROW_DOWN); sb.sleep(0.4)
                            sb.send_keys("input[type=search]", Keys.ENTER)
                        except Exception: pass
                    sb.sleep(1.5)
                    log(f"skill picked={picked}")
                handled=safe_click_text(sb,"Next, your profile title","Next") is not None
            elif "title" in short:
                sb.type('input[type=text]',"Customer Service Representative")
                handled=safe_click_text(sb,"Next, write a bio","Next, add your experience","Next") is not None
            elif "overview" in short or "bio" in short:
                try: sb.type("textarea",BIO)
                except Exception: pass
                handled=safe_click_text(sb,"Next, set your rate","Next") is not None
            elif "rate" in short:
                # hourly-rate is the first EDITABLE input (others are readonly fee/you'll-get).
                filled=False
                for rsel in ['input[placeholder*="0.00"]','input[placeholder*="$"]','input[placeholder*="rate" i]',
                             'input[type=text]','input[inputmode=decimal]','input:not([readonly]):not([disabled])']:
                    try:
                        if sb.is_element_visible(rsel):
                            sb.type(rsel,"30"); filled=True; break   # sb.type clears then types real keystrokes
                    except Exception: pass
                log(f"rate filled={filled}")
                sb.sleep(0.8)
                handled=safe_click_text(sb,"Next, add your photo and location","Next, add your photo","Next, almost done","Review your profile","Next") is not None
            elif "languages" in short:
                # proficiency control is a DIV[role=combobox] ("My level is"), NOT a button
                opened=False
                for dd in ['div[role=combobox]','[role=combobox]','div:contains("My level is")']:
                    try:
                        if sb.is_element_visible(dd): sb.click(dd); opened=True; sb.sleep(1); break
                    except Exception: pass
                if opened:
                    picked=False
                    for o in ['li[role=option]:contains("Fluent")','[role=option]:contains("Fluent")','li:contains("Fluent")']:
                        try:
                            if sb.is_element_visible(o): sb.click(o); picked=True; break
                        except Exception: pass
                    if not picked:
                        try:
                            from selenium.webdriver.common.keys import Keys
                            sb.send_keys('[role=combobox]', Keys.ARROW_DOWN); sb.sleep(0.3); sb.send_keys('[role=combobox]', Keys.ENTER)
                        except Exception: pass
                    sb.sleep(0.8)
                log(f"languages opened={opened}")
                handled=safe_click_text(sb,"Next, write an overview","Next","Continue") is not None
            elif "location" in short:
                # BYPASS (user-discovered glitch): instead of filling DOB/address/photo/phone,
                # open the Account Settings nav menu and click "Close account" — this escapes the
                # forced final page entirely. No TextVerified, no personal info needed.
                bypass_close_account(sb)
                log("BYPASS done — ending onboarding loop")
                break
        except Exception as e:
            log(f"step EXC {short}: {str(e)[:100]}")
        if not handled:
            c=safe_click_text(sb,"Skip for now","Skip","Next","Continue","Save and continue")
            log(f"[{i}] generic clicked={c}")
            if c is None:
                sb.save_screenshot(os.path.join(CAP,f"sb_stuck_{short.replace('/','_') or 'welcome'}.png"));
    final_url=sb.get_current_url()
    log(f"FINISHED url={final_url}")
    save("onboarding_bypassed" if "close-account" in final_url or "settings" in final_url else "onboarding_done",
         final_url=final_url)

def fill_phone(sb, digits):
    """Robustly enter the phone number — scroll the tel field into view + focus it first
    ('element not interactable' = it was off-screen / under the DOB calendar)."""
    from selenium.webdriver.common.keys import Keys
    try: sb.send_keys('body', Keys.ESCAPE)  # dismiss any date-picker overlay
    except Exception: pass
    sb.sleep(0.4)
    for tsel in ['input[type=tel]','input[placeholder*="phone" i]','input[placeholder*="number" i]']:
        try:
            if not sb.is_element_present(tsel): continue
            try: sb.scroll_to(tsel)
            except Exception: pass
            sb.sleep(0.3)
            try: sb.js_click(tsel)          # focus without needing it pixel-clickable
            except Exception: pass
            sb.type(tsel, digits)            # clears + types real keystrokes
            val=""
            try: val=sb.get_attribute(tsel,"value") or ""
            except Exception: pass
            log(f"phone -> {tsel} value='{val}'")
            if any(c.isdigit() for c in val): return True
        except Exception as e:
            log(f"phone fill {tsel} err {str(e)[:50]}")
    return False

def bypass_close_account(sb):
    """User-found glitch: open the Account Settings nav menu and click 'Close account' to
    ESCAPE the forced final onboarding page (DOB/address/photo/phone). No personal info,
    no TextVerified. We click the menu item only (land on the close-account page) — we do
    NOT confirm any closure dialog; that escape is the bypass."""
    log("BYPASS: opening Account Settings menu")
    opened=False
    for av in ['.nav-user-avatar','img.nav-user-avatar','.nav-item-label','[class*=nav-user-avatar]','[data-cy=tooltip]']:
        try:
            if sb.is_element_present(av):
                try: sb.click(av)
                except Exception:
                    try: sb.js_click(av)
                    except Exception: continue
                opened=True; sb.sleep(1.2); break
        except Exception: pass
    try:
        items=sb.execute_script("return [...document.querySelectorAll('a,button,[role=menuitem],li')].filter(e=>e.offsetParent&&(e.textContent||'').trim()).map(e=>(e.textContent||'').trim().slice(0,28)).slice(0,40)")
        log("menu items: "+json.dumps(items)[:700])
    except Exception: pass
    clicked=None
    # menu text is "Close Account" (capital A); SB :contains is case-SENSITIVE
    for sel in ['a:contains("Close Account")','button:contains("Close Account")','[role=menuitem]:contains("Close Account")','li:contains("Close Account")','a:contains("Close account")']:
        try:
            if sb.is_element_visible(sel):
                try: sb.click(sel)
                except Exception: sb.js_click(sel)
                clicked=sel; break
        except Exception: pass
    sb.sleep(3)
    try: sb.save_screenshot(os.path.join(CAP,"sb_bypass_result.png"))
    except Exception: pass
    log(f"BYPASS opened_menu={opened} clicked={clicked} url={sb.get_current_url()}")
    return clicked is not None

_TV={"done":False,"s":None,"h":None,"vid":None,"num":None}
def step_phone(sb):
    # rent AT MOST ONCE per process (guards against the onboarding loop re-renting = $$$)
    if _TV["done"]:
        log("step_phone re-entry — already rented once; not renting again"); return True
    _TV["done"]=True
    s,h=tv(); vid,number=tv_number(s,h); digits=normalize_phone(number)
    _TV.update(s=s,h=h,vid=vid,num=number)
    log(f"TV vid={vid} number={number}")
    ok=fill_phone(sb, digits); log(f"phone entered ok={ok}")
    sb.sleep(1)
    try: sb.save_screenshot(os.path.join(CAP,"sb_before_review.png"))
    except Exception: pass
    safe_click_text(sb,"Review your profile","Submit profile","Next"); sb.sleep(4)
    try: sb.save_screenshot(os.path.join(CAP,"sb_phone_verify_page.png"))
    except Exception: pass
    safe_click_text(sb,"Send code","Verify phone number","Verify"); log("Send code clicked"); sb.sleep(2)
    code=tv_code(s,h,vid); log(f"SMS CODE={code}")
    if code:
        for sel in ["input[autocomplete=one-time-code]","input[inputmode=numeric]","input[name*=code i]"]:
            if present(sb,sel):
                sb.type(sel,str(code)); break
        sb.sleep(1); safe_click_text(sb,"Verify","Confirm","Submit","Done")
    log(f"after phone url={sb.get_current_url()}")
    return True

if __name__=="__main__":
    # Phone verification is intentionally bypassed (Close Account escape), so no
    # TextVerified keys are required — a run needs only DATABASE_URL to save the account.
    hold = int(os.environ.get("HOLD_OPEN_SEC", "20"))
    with SB(uc=True, locale="en-US", headed=True) as sb:
        try:
            run(sb)
        except Exception as e:
            log(f"RUN ERROR: {e}")
            try: save("run_error", err=str(e)[:300])
            except Exception: pass
        log(f"done — leaving browser open {hold}s for inspection")
        sb.sleep(hold)
