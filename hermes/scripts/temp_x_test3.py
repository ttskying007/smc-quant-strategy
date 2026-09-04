#!/usr/bin/env python3
"""Test Playwright - separate page per search"""
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

        # Open homepage to establish session
        hp = await context.new_page()
        await hp.goto("https://x.com/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(4)
        print(f'Session: {await hp.title()} @ {hp.url}')
        print(f'Logged in: {"home" in hp.url.lower() or "timeline" in hp.url.lower()}')
        await hp.close()

        # Now open new page for each search
        keywords = ["AI agent", "Smart Money Concepts", "ICT SMC trading"]
        for kw in keywords:
            page = await context.new_page()
            url = f"https://x.com/search?q={urllib.parse.quote(kw)}&src=typed_query&f=live"
            print(f'\nSearch: {kw}')
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)
            print(f'  URL: {page.url[:70]}')
            print(f'  Title: "{await page.title()}"')
            
            # Check for login redirect
            current_url = page.url.lower()
            if "login" in current_url:
                print(f'  -> LOGIN REDIRECT!')
                await page.close()
                continue
                
            # Try multiple scrolls
            for s in range(3):
                await page.evaluate("window.scrollBy(0, 1000)")
                await asyncio.sleep(2)
            
            count = await page.evaluate("document.querySelectorAll('article[data-testid=tweet]').length")
            print(f'  Tweets: {count}')
            
            if count > 0:
                texts = await page.evaluate("""() => {
                    const articles = document.querySelectorAll('article[data-testid=tweet]');
                    return Array.from(articles).slice(0,3).map(a => {
                        const t = a.querySelector('[data-testid=tweetText]');
                        return t ? t.textContent.substring(0,100) : '';
                    });
                }""")
                for i, t in enumerate(texts):
                    print(f'  [{i+1}] {t[:80]}')
            
            await page.close()
            await asyncio.sleep(1)

        await context.close()
        await browser.close()

asyncio.run(test())
