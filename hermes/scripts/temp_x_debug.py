#!/usr/bin/env python3
"""Test Playwright + X cookies - debug empty page"""
import asyncio
from playwright.async_api import async_playwright

COOKIES = [
    {"name": "auth_token", "value": "94c33a4433814a44ae685c46c0611d8eeef8c363", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "7125be269b3185ac33e8e90cc0c924f24d9fb77d5a45318d5974ff3e86f4c386a6d40072dd1179589f00f2d8dd05b45418ade6de9c24bc5f2a5ec8f5748b826305e117cdf5a387b0933ff69f27b9867c", "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D488154571", "domain": ".x.com", "path": "/"},
    {"name": "guest_id", "value": "v1%3A177297400447928763", "domain": ".x.com", "path": "/"},
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

        await page.goto("https://x.com/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(8)
        print(f'Title: "{await page.title()}"')
        print(f"URL: {page.url}")

        # Check what's inside root
        root_html = await page.evaluate("""() => {
            let root = document.getElementById("react-root");
            if (!root) {
                root = document.querySelector("#layers");
                if (!root) return "NO_ROOT_OR_LAYERS";
            }
            return root.innerHTML.substring(0, 500);
        }""")
        print(f"Root inner: {root_html[:300]}")

        # Check all top-level elements
        top = await page.evaluate("""() => {
            const divs = document.body.children;
            return Array.from(divs).slice(0,10).map(
                d => d.tagName + (d.id ? "#" + d.id : "") + "." + d.className.toString().substring(0,30)
            ).join(" | ");
        }""")
        print(f"Top elements: {top[:300]}")

        await context.close()
        await browser.close()

asyncio.run(test())
