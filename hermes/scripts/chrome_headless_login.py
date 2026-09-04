#!/usr/bin/env python3
"""
Launch system Chrome (channel: chrome) with fresh profile and login to X.
This avoids Playwright's bundled Chromium which Cloudflare blocks more aggressively.
"""
import asyncio
import os
import tempfile
import json
import shutil
from playwright.async_api import async_playwright

async def main():
    # Create fresh temp profile
    profile_dir = tempfile.mkdtemp(prefix='chrome_x_profile_')
    print(f"Fresh profile: {profile_dir}")
    
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            channel='chrome',
            headless=True,
            proxy={"server": "http://127.0.0.1:7890"},
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--window-size=1280,1024',
            ],
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36',
        )
        
        page = context.pages[0] if context.pages else await context.new_page()
        
        print("Navigating to x.com login...")
        try:
            await page.goto('https://x.com/i/flow/login', wait_until='domcontentloaded', timeout=60000)
        except Exception as e:
            print(f"Navigation timeout/error: {e}")
        
        await asyncio.sleep(5)
        
        title = await page.title()
        print(f"Title: {title}")
        print(f"URL: {page.url}")
        
        # Check for Cloudflare
        content = await page.content()
        
        # Take screenshot
        await page.screenshot(path='/tmp/x_headless_chrome.png')
        
        if 'challenge' in page.url.lower() or 'cf-challenge' in content[:5000].lower():
            print("CLOUDFLARE CHALLENGE - headless Chrome blocked")
            await context.close()
            shutil.rmtree(profile_dir, ignore_errors=True)
            return
        
        # Check for login form
        has_username_input = await page.query_selector('input[autocomplete="username"], input[name="text"]')
        if has_username_input:
            print("Found username input - trying login...")
            await has_username_input.fill('ttskying')
            print("Entered username")
            
            # Click Next
            next_btn = await page.query_selector('button[role="button"]:has-text("Next"), div[role="button"]:has-text("Next")')
            if next_btn:
                await next_btn.click()
                print("Clicked Next")
            await asyncio.sleep(3)
            
            # Enter password
            pw_input = await page.query_selector('input[type="password"], input[name="password"]')
            if pw_input:
                await pw_input.fill('ttskying007')
                print("Entered password")
                
                login_btn = await page.query_selector('button[role="button"]:has-text("Log in"), div[role="button"]:has-text("Log in")')
                if login_btn:
                    await login_btn.click()
                    print("Clicked Log in")
                await asyncio.sleep(5)
        
        print(f"After login URL: {page.url}")
        
        if 'login' not in page.url.lower():
            print("LOGGED IN! Extracting cookies...")
            
            # Get cookies from context
            cookies = await context.cookies()
            x_cookies = {}
            for c in cookies:
                domain = c.get('domain', '')
                if 'x.com' in domain or 'twitter.com' in domain:
                    x_cookies[c['name']] = c['value']
                    print(f"  {c['name']} = {c['value'][:40]}...")
            
            # Save cookies
            output_path = '/root/.hermes/x_cookies_fresh_playwright.json'
            with open(output_path, 'w') as f:
                json.dump(x_cookies, f, indent=2)
            print(f"\nSaved {len(x_cookies)} cookies to {output_path}")
            
            # Generate cookie header
            cookie_parts = []
            for name in ('auth_token', 'ct0', 'twid'):
                if name in x_cookies:
                    cookie_parts.append(f"{name}={x_cookies[name]}")
            if cookie_parts:
                cookie_str = '; '.join(cookie_parts)
                with open('/root/.hermes/x_cookie_header.txt', 'w') as f:
                    f.write(cookie_str)
                print(f"\nCookie header: {cookie_str[:80]}...")
        else:
            print("Login failed")
            # Show what's on the page
            visible_text = await page.evaluate('() => document.body.innerText.substring(0, 1000)')
            print(f"Page text: {visible_text[:500]}")
        
        await context.close()
        shutil.rmtree(profile_dir, ignore_errors=True)

asyncio.run(main())
