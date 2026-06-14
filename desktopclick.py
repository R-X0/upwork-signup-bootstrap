#!/usr/bin/env python3
"""Full Upwork signup with a REAL hardware click on an ISOLATED Windows desktop.

Strategy (the proven differentiator: a real hardware/SendInput click passes
reCAPTCHA where a CDP-synthetic click fails, and your manual click already proved
patchright's browser itself isn't flagged): launch Chrome on a SEPARATE Win32
desktop, drive it over CDP (fill form), then issue a genuine SendInput mouse click
from a thread bound to that desktop — so it's hardware-level input that never
touches the visible cursor. Then the normal downstream finishes the account.
"""
import ctypes, ctypes.wintypes as wt, time, os, threading, random, string, re, asyncio
from curl_cffi import requests as cffi

ROOT = r"C:\Users\Bona\upwork-signup"; CAP = os.path.join(ROOT, "cap")
PROFILE = os.path.join(ROOT, "chrome-desk"); FACE = os.path.join(CAP, "face.jpg")
CHROME = r"C:\Users\Bona\AppData\Local\ms-playwright\chromium-1208\chrome-win64\chrome.exe"
import config
WORKER = config.EMAIL_WORKER
TV_KEY = config.TV_API_KEY; TV_USER = config.TV_USER; TVB = config.TV_BASE
DESK = "upworkbot"

u32 = ctypes.windll.user32; k32 = ctypes.windll.kernel32
def log(m): print(f">>> {m}", flush=True)

FIRST=["James","Emma","Liam","Olivia","Noah","Ava","Ethan","Sophia","Lucas","Mia"]
LAST=["Smith","Johnson","Brown","Garcia","Miller","Davis","Wilson","Clark","Lewis","Walker"]
fn=random.choice(FIRST); ln=random.choice(LAST)
tag="".join(random.choices(string.ascii_lowercase+string.digits,k=6))
EMAIL=f"{fn.lower()}.{ln.lower()}.{tag}@eldenstats.com"
PW="".join(random.choices(string.ascii_uppercase,k=2))+"".join(random.choices(string.ascii_lowercase,k=5))+str(random.randint(10,99))+"!"
BIO=("Experienced customer service representative skilled in email, chat and phone support, "
     "problem solving, and fast professional resolution of client issues.")

# ---- Win32 structs ----
class STARTUPINFOW(ctypes.Structure):
    _fields_=[("cb",wt.DWORD),("lpReserved",wt.LPWSTR),("lpDesktop",wt.LPWSTR),("lpTitle",wt.LPWSTR),
              ("dwX",wt.DWORD),("dwY",wt.DWORD),("dwXSize",wt.DWORD),("dwYSize",wt.DWORD),
              ("dwXCountChars",wt.DWORD),("dwYCountChars",wt.DWORD),("dwFillAttribute",wt.DWORD),
              ("dwFlags",wt.DWORD),("wShowWindow",wt.WORD),("cbReserved2",wt.WORD),
              ("lpReserved2",ctypes.POINTER(ctypes.c_byte)),("hStdInput",wt.HANDLE),
              ("hStdOutput",wt.HANDLE),("hStdError",wt.HANDLE)]
class PROCESS_INFORMATION(ctypes.Structure):
    _fields_=[("hProcess",wt.HANDLE),("hThread",wt.HANDLE),("dwProcessId",wt.DWORD),("dwThreadId",wt.DWORD)]
class MOUSEINPUT(ctypes.Structure):
    _fields_=[("dx",wt.LONG),("dy",wt.LONG),("mouseData",wt.DWORD),("dwFlags",wt.DWORD),("time",wt.DWORD),("dwExtraInfo",ctypes.POINTER(wt.ULONG))]
class INPUT(ctypes.Structure):
    class _I(ctypes.Union): _fields_=[("mi",MOUSEINPUT)]
    _anonymous_=("i",); _fields_=[("type",wt.DWORD),("i",_I)]

MOUSEEVENTF_MOVE=0x0001; MOUSEEVENTF_ABSOLUTE=0x8000; MOUSEEVENTF_LEFTDOWN=0x0002; MOUSEEVENTF_LEFTUP=0x0004
SM_CXSCREEN=0; SM_CYSCREEN=1

def make_desktop():
    GENERIC_ALL=0x10000000
    h=u32.CreateDesktopW(DESK,None,None,0,GENERIC_ALL,None)
    if not h: log(f"CreateDesktop failed err={k32.GetLastError()}")
    return h

def launch_chrome_on_desktop():
    si=STARTUPINFOW(); si.cb=ctypes.sizeof(si); si.lpDesktop=DESK
    pi=PROCESS_INFORMATION()
    args=(f'"{CHROME}" --remote-debugging-port=9223 --user-data-dir="{PROFILE}" '
          f'--no-first-run --no-default-browser-check --disable-blink-features=AutomationControlled '
          f'--window-size=1280,800 --window-position=0,0 https://www.upwork.com/nx/signup/?dest=home')
    CREATE_NEW_CONSOLE=0x00000010
    ok=k32.CreateProcessW(None, args, None,None,False, CREATE_NEW_CONSOLE, None, None, ctypes.byref(si), ctypes.byref(pi))
    if not ok: log(f"CreateProcess failed err={k32.GetLastError()}")
    return ok

def hardware_click_on_desktop(hdesk, sx, sy, w_, h_):
    """SwitchDesktop to hdesk (so SendInput reaches it), real move+click, switch back.
    Briefly displays the bot desktop (~1s) but never moves the user's own cursor."""
    GENERIC_ALL=0x10000000
    hdefault=u32.OpenDesktopW("Default",0,False,GENERIC_ALL)
    def worker():
        st=u32.SetThreadDesktop(hdesk)
        sw=u32.SwitchDesktop(hdesk); time.sleep(0.4)
        log(f"SetThreadDesktop={st} SwitchDesktop={sw} (1=ok)")
        ax=int(sx*65535/w_); ay=int(sy*65535/h_)
        for f in (0.6,0.8,1.0):
            mi=MOUSEINPUT(int(ax*f),int(ay*f),0,MOUSEEVENTF_MOVE|MOUSEEVENTF_ABSOLUTE,0,None)
            inp=INPUT(); inp.type=0; inp.mi=mi; u32.SendInput(1,ctypes.byref(inp),ctypes.sizeof(inp)); time.sleep(0.06)
        for flag in (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP):
            mi=MOUSEINPUT(ax,ay,0,MOUSEEVENTF_ABSOLUTE|flag,0,None)
            inp=INPUT(); inp.type=0; inp.mi=mi; u32.SendInput(1,ctypes.byref(inp),ctypes.sizeof(inp)); time.sleep(0.08)
        time.sleep(0.3)
        if hdefault: u32.SwitchDesktop(hdefault)
    t=threading.Thread(target=worker); t.start(); t.join()

# ---- worker email / textverified ----
def get_verify_link(tries=120,delay=3):
    for _ in range(tries):
        try:
            raw=cffi.get(f"{WORKER}/debug",params={"email":EMAIL},impersonate="chrome",timeout=8).json().get("rawContent")
            if raw:
                flat=raw.replace("=\r\n","").replace("=\n","").replace("=3D","=")
                m=re.findall(r'https?://www\.upwork\.com/nx/signup/verify-email/token/[^\s"<>\)\]]+',flat)
                if m: return m[0].rstrip('=')
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
        if v.get("code"): return v["code"]
        try:
            sms=s.get(f"{TVB}/api/pub/v2/sms?reservationId={vid}",headers=h,timeout=30).json()
            data=sms.get("data") if isinstance(sms,dict) else sms
            for m in (data or []):
                if m.get("parsedCode") or m.get("code"): return m.get("parsedCode") or m.get("code")
        except Exception: pass
        time.sleep(delay)
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

async def main():
    log(f"identity {fn} {ln} <{EMAIL}> pw={PW}")
    open(os.path.join(CAP,"run_creds.txt"),"w").write(f"{EMAIL}\n{PW}\n")
    hdesk=make_desktop()
    if not launch_chrome_on_desktop(): return
    log("chrome launched on isolated desktop; connecting CDP...")
    from patchright.async_api import async_playwright
    # wait for CDP
    import urllib.request
    for _ in range(30):
        try: urllib.request.urlopen("http://localhost:9223/json/version",timeout=2); break
        except Exception: await asyncio.sleep(1)
    sw=u32.GetSystemMetrics(SM_CXSCREEN); sh=u32.GetSystemMetrics(SM_CYSCREEN)
    log(f"screen {sw}x{sh}")
    async with async_playwright() as p:
        b=await p.chromium.connect_over_cdp("http://localhost:9223")
        ctx=b.contexts[0]; page=ctx.pages[-1] if ctx.pages else await ctx.new_page()
        async def on_resp(r):
            if "gql-mutation-register" in r.url:
                try:
                    j=await r.json(); err=(j.get("errors") or [{}])[0]
                    log(f"REGISTER_RESP status={r.status} err={err.get('message')} code={err.get('extensions',{}).get('code')} data={(j.get('data') or {}).get('register')}")
                except Exception as e: log(f"REGISTER_RESP status={r.status} ({e})")
        page.on("response", lambda r: asyncio.create_task(on_resp(r)))
        await page.wait_for_timeout(4000); await dismiss_cookies(page)
        try: fr=await page.wait_for_selector("[data-qa=btn-apply-freelancer]",timeout=20000)
        except Exception: fr=None
        if fr: await fr.click()
        await page.wait_for_timeout(5000); await dismiss_cookies(page)
        await page.fill("#first-name-input",fn); await page.fill("#last-name-input",ln)
        await page.fill("#redesigned-input-email",EMAIL); await page.fill("#password-input",PW)
        await dismiss_cookies(page)
        for lab in ["checkbox-terms","checkbox-promo"]:
            try:
                el=await page.query_selector(f'label#{lab}, #{lab}')
                if el:
                    box=await el.bounding_box()
                    if box: await page.mouse.click(box["x"]+12,box["y"]+box["height"]/2); await page.wait_for_timeout(250)
            except Exception: pass
        for bx in await page.query_selector_all("input[type=checkbox]"):
            try:
                if not await bx.is_checked(): await bx.check(force=True)
            except Exception: pass
        log(f"form filled checkboxes={[await b.is_checked() for b in await page.query_selector_all('input[type=checkbox]')]}")
        # compute the create button's SCREEN coords for the hardware click
        btn=await page.query_selector("#button-submit-form")
        await btn.scroll_into_view_if_needed(); await page.wait_for_timeout(500)
        box=await btn.bounding_box()
        geo=await page.evaluate("()=>({sx:window.screenX,sy:window.screenY,oh:window.outerHeight,ih:window.innerHeight,ow:window.outerWidth,iw:window.innerWidth,dpr:window.devicePixelRatio})")
        cx=box["x"]+box["width"]/2; cy=box["y"]+box["height"]/2
        screen_x=(geo["sx"]+cx)*geo["dpr"]; screen_y=(geo["sy"]+(geo["oh"]-geo["ih"])+cy)*geo["dpr"]
        log(f"GEO {geo} BOX x={box['x']:.0f} y={box['y']:.0f} w={box['width']:.0f} h={box['height']:.0f} cx={cx:.0f} cy={cy:.0f}")
        # sanity: what element is at the button's viewport center?
        try:
            tagat=await page.evaluate("([x,y])=>{const e=document.elementFromPoint(x,y);return e?(e.id||e.tagName)+' :: '+(e.innerText||'').slice(0,20):'none'}", [cx,cy])
            log(f"elementFromPoint(viewport {cx:.0f},{cy:.0f}) = {tagat}")
        except Exception as e: log(f"efp err {e}")
        log(f"HARDWARE click at screen ({int(screen_x)},{int(screen_y)}) dpr={geo['dpr']}")
        hardware_click_on_desktop(hdesk,screen_x,screen_y,sw,sh)
        log("hardware click sent")
        created=False
        for i in range(60):
            await page.wait_for_timeout(2000)
            if "verify" in page.url or "create-profile" in page.url or "please-verify" in page.url:
                created=True; log(f"ACCOUNT CREATED url={page.url}"); break
        if not created:
            await page.screenshot(path=os.path.join(CAP,"desk_after.png"))
            log("NOT_CREATED after hardware click");
            while True: await asyncio.sleep(5)

        # ---- downstream finish ----
        if "verify" in page.url or "please-verify" in page.url:
            link=get_verify_link(); log(f"verify link {link}")
            if link: await page.goto(link,wait_until="domcontentloaded",timeout=60000); await page.wait_for_timeout(5000)
        await page.goto("https://www.upwork.com/nx/create-profile/",wait_until="domcontentloaded",timeout=60000); await page.wait_for_timeout(4000)
        await click_text(page,"Get started"); await page.wait_for_timeout(4000)
        if "create-profile" in page.url:
            cat=await page.query_selector('text=Customer Service')
            if cat:
                try: await cat.click()
                except Exception: pass
                await page.wait_for_timeout(1500)
                for bx in await page.query_selector_all("input[type=checkbox]"):
                    try: await bx.check(force=True); break
                    except Exception: pass
            await click_text(page,"Next, add your skills","Next"); await page.wait_for_timeout(2500)
        try:
            inp=await page.query_selector("input[type=search]")
            if inp:
                await inp.click()
                for ch in "Customer Service": await page.keyboard.type(ch); await page.wait_for_timeout(70)
                await page.wait_for_timeout(2000)
                o=await page.query_selector('li[role=option]')
                if o: await o.click()
        except Exception: pass
        await click_text(page,"Next, your profile title","Next"); await page.wait_for_timeout(2500)
        try: await page.fill('input[type=text]',"Customer Service Representative")
        except Exception: pass
        await click_text(page,"Next, add your experience","Next"); await page.wait_for_timeout(2500)
        for i in range(16):
            await page.wait_for_timeout(1500); url=page.url
            if "create-profile/location" in url: log("reached final page"); break
            if "languages" in url:
                dd=await page.query_selector('[role=combobox], button:has-text("My level is")')
                if dd:
                    await dd.click(); await page.wait_for_timeout(800); picked=False
                    for o in await page.query_selector_all('li[role=option]'):
                        if await o.is_visible() and "fluent" in (await o.inner_text()).lower(): await o.click(); picked=True; break
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
            c=await click_text(page,"Skip for now","Next","Continue"); log(f"step {i} {url} -> {c}")
            if c is None: break
        await page.wait_for_timeout(1500)
        try:
            if not await page.query_selector('button:has-text("Edit photo")'):
                await click_text(page,"Upload photo"); await page.wait_for_timeout(1500)
                fin=await page.query_selector_all("input[type=file]")
                if fin:
                    await fin[-1].set_input_files(FACE); await page.wait_for_timeout(3000)
                    for _ in range(8):
                        at=await page.query_selector('button:has-text("Attach photo")')
                        if at and await at.is_enabled(): await at.click(); log("photo attached"); break
                        await page.wait_for_timeout(1000)
                    await page.wait_for_timeout(2000)
        except Exception as e: log(f"photo err {e}")
        try: await page.fill('input[placeholder*="mm/dd" i]',"05/14/1995")
        except Exception: pass
        try:
            el=await page.query_selector('input[placeholder*="street" i]')
            await el.click(); await page.keyboard.press("Control+A"); await page.keyboard.press("Delete")
            for ch in "100 Congress Avenue, Austin, TX": await page.keyboard.type(ch); await page.wait_for_timeout(120)
            await page.wait_for_timeout(2000)
            for s in ['[role=option]','ul[role=listbox] li','[class*=dropdown] li','[class*=menu] li']:
                o=await page.query_selector(s)
                if o and await o.is_visible(): await o.click(); log("address picked"); break
            await page.wait_for_timeout(1200)
        except Exception as e: log(f"addr err {e}")
        s,h=tv(); vid,number=tv_number(s,h)
        digits="".join(c for c in (number or "") if c.isdigit())
        if len(digits)==11 and digits[0]=="1": digits=digits[1:]
        log(f"TV vid={vid} number={number}")
        try:
            el=await page.query_selector('input[type=tel], input[placeholder*="phone" i]')
            await el.click(); await page.keyboard.press("Control+A"); await page.keyboard.press("Delete")
            for ch in digits: await page.keyboard.type(ch); await page.wait_for_timeout(50)
        except Exception as e: log(f"phone err {e}")
        await click_text(page,"Review your profile"); await page.wait_for_timeout(5000)
        await click_text(page,"Send code"); log("Send code clicked"); await page.wait_for_timeout(2500)
        code=tv_code(s,h,vid); log(f"SMS CODE={code}")
        if code:
            for sel in ["input[autocomplete=one-time-code]","input[inputmode=numeric]","input[name*=code i]","input[maxlength='6']"]:
                el=await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click(); await el.fill("")
                    for ch in str(code): await page.keyboard.type(ch); await page.wait_for_timeout(110)
                    break
            await page.wait_for_timeout(1500)
            await click_text(page,"Verify","Confirm","Submit","Next","Done"); await page.wait_for_timeout(6000)
        await page.screenshot(path=os.path.join(CAP,"desk_done.png"))
        log(f"FINISHED url={page.url}")
        while True: await asyncio.sleep(5)

asyncio.run(main())
