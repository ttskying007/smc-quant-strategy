#!/usr/bin/env python3
"""Playwright X login + scrape - handles Cloudflare better than httpx"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy={"server": "http://127.0.0.1:7890"},
            args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15',
            viewport={'width': 1280, 'height': 720}
        )
        page = await context.new_page()
        
        print("Navigating to x.com login...")
        await page.goto('https://x.com/i/flow/login', wait_until='domcontentloaded', timeout=60000)
        await asyncio.sleep(5)
        
        # Check page state
        title = await page.title()
        print(f"Title: {title}")
        
        content = await page.content()
        if 'cloudflare' in content.lower()[:3000] or 'challenge' in content.lower()[:3000]:
            print("CLOUDFLARE challenge - taking screenshot")
            await page.screenshot(path='/tmp/x_cf_challenge.png')
        
        # Try to enter username
        print("Looking for username input...")
        username_input = await page.query_selector('input[autocomplete="username"], input[name="text"], input[type="text"]')
        
        if username_input:
            await username_input.fill('ttskying')
            print("Entered username")
            
            # Click Next
            next_btn = await page.query_selector('button[role="button"]:has-text("Next"), div[role="button"]:has-text("Next")')
            if next_btn:
                await next_btn.click()
            
            await asyncio.sleep(3)
            
            # Enter password
            pw_input = await page.query_selector('input[type="password"], input[name="password"]')
            if pw_input:
                await pw_input.fill('ttskying007')
                print("Entered password")
                
                # Click Login
                login_btn = await page.query_selector('button[role="button"]:has-text("Log in"), div[role="button"]:has-text("Log in")')
                if login_btn:
                    await login_btn.click()
                
                await asyncio.sleep(5)
        
        # Check login result
        print(f"After login URL: {page.url}")
        
        # Get fresh cookies
        fresh_cookies = await context.cookies()
        print(f"Cookies after login: {len(fresh_cookies)}")
        
        # Save cookies
        import json
        cookies_dict = {c['name']: c['value'] for c in fresh_cookies}
        with open('/root/.hermes/x_cookies_fresh_playwright.json', 'w') as f:
            json.dump(cookies_dict, f, indent=2)
        print(f"Saved fresh cookies")
        
        # Now try search
        if 'login' not in page.url.lower():
            print("\nLogged in! Trying search...")
            await page.goto('https://x.com/search?q=AI+agent&src=typed_query&f=live', wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(5)
            
            tweets = await page.evaluate('''
                () => {
                    const articles = document.querySelectorAll('article[data-testid="tweet"]');
                    return Array.from(articles).slice(0, 5).map(a => {
                        const textEl = a.querySelector('[data-testid="tweetText"]');
                        const userLinks = a.querySelectorAll('[data-testid="User-Name"] a');
                        let screenName = '';
                        userLinks.forEach(el => {
                            const href = el.getAttribute('href') || '';
                            if (href.startsWith('/') && !href.includes('/status/')) {
                                screenName = href.replace('/', '');
                            }
                        });
                        return {
                            text: textEl ? textEl.textContent : '',
                            screen_name: screenName,
                        };
                    });
                }
            ''')
            print(f"Found {len(tweets)} tweets")
            for t in tweets:
                print(f"  @{t['screen_name']}: {t['text'][:80]}")
        else:
            print("Still on login page - auth failed")
            await page.screenshot(path='/tmp/x_login_fail.png')
        
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
