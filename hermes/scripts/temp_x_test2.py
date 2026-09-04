#!/usr/bin/env python3
"""Test Playwright search with fixed args"""
import asyncio, urllib.parse
from playwright.async_api import async_playwright

COOKIES = [
    {"name": "auth_token", "value": "94c33a4433814a44ae685c46c0611d8eeef8c363", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "7125be269b3185ac33e8e90cc0c924f24d9fb77d5a45318d5974ff3e86f4c386a6d40072dd1179589f00f2d8dd05b45418ade6de9c24bc5f2a5ec8f5748b826305e117cdf5a387b0933ff69f27b9867c", "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D488154571", "domain": ".x.com", "path": "/"},
]

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy={"server": "http://127.0.0.1:7890"},
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        await context.add_cookies(COOKIES)
        page = await context.new_page()

        # Load homepage to establish session
        await page.goto("https://x.com/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        print(f'Session: {await page.title()} @ {page.url}')

        # Test searches
        keywords = ["Smart Money Concepts", "AI agent", "ICT SMC trading strategy",
                     "八字 紫微斗数 占星", "free API no credit card", "AI video generation"]
        for kw in keywords:
            url = f"https://x.com/search?q={urllib.parse.quote(kw)}&src=typed_query&f=live"
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(4)
            title = await page.title()
            count = await page.evaluate("document.querySelectorAll('article[data-testid=tweet]').length")
            print(f'  {kw[:30]}: {count} tweets | title="{title[:30]}"')

        await context.close()
        await browser.close()

asyncio.run(test())
