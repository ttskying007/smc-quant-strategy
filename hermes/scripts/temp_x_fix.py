#!/usr/bin/env python3
"""Quick test of fixed X scraper - single context, homepage first"""
import asyncio, urllib.parse, json
from playwright.async_api import async_playwright

COOKIES = [
    {"name": "auth_token", "value": "94c33a4433814a44ae685c46c0611d8eeef8c363", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "7125be269b3185ac33e8e90cc0c924f24d9fb77d5a45318d5974ff3e86f4c386a6d40072dd1179589f00f2d8dd05b45418ade6de9c24bc5f2a5ec8f5748b826305e117cdf5a387b0933ff69f27b9867c", "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D488154571", "domain": ".x.com", "path": "/"},
    {"name": "guest_id", "value": "v1%3A177297400447928763", "domain": ".x.com", "path": "/"},
]

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, proxy={"server": "http://127.0.0.1:7890"}, args=["--no-sandbox"])
        context = await browser.new_context(proxy={"server": "http://127.0.0.1:7890"})
        await context.add_cookies(COOKIES)

        # Step 1: Visit homepage to establish session
        hp = await context.new_page()
        await hp.goto("https://x.com/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        print(f"Session: {await hp.title()}")
        await hp.close()

        # Step 2: Search multiple keywords in same context
        test_kw = ["Smart Money Concepts", "AI agent", "ICT trading"]
        for kw in test_kw:
            page = await context.new_page()
            url = f"https://x.com/search?q={urllib.parse.quote(kw)}&src=typed_query&f=live"
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(4)
            print(f"\nKeyword: {kw}")
            print(f"  Title: {await page.title()}")
            print(f"  URL: {page.url[:80]}")
            tweets = await page.evaluate("document.querySelectorAll('article[data-testid=tweet]').length")
            print(f"  Tweets: {tweets}")
            if tweets > 0:
                texts = await page.evaluate("""() => {
                    const arts = document.querySelectorAll('article[data-testid=tweet]');
                    return Array.from(arts).slice(0,3).map(a => {
                        const t = a.querySelector('[data-testid=tweetText]');
                        return t ? t.textContent.substring(0,100) : '';
                    });
                }""")
                for t in texts:
                    print(f"    -> {t[:80]}")
            await page.close()

        await context.close()
        await browser.close()

asyncio.run(test())
