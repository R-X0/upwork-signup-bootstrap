import asyncio
from patchright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        print("connecting...", flush=True)
        b = await p.chromium.connect_over_cdp("http://localhost:9223")
        print("connected, contexts:", len(b.contexts), flush=True)
        ctx = b.contexts[0]
        print("pages:", len(ctx.pages), flush=True)
        page = ctx.pages[-1]
        print("url:", page.url, flush=True)
        await b.close()
        print("done", flush=True)
asyncio.run(main())
