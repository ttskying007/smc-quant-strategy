#!/usr/bin/env python3
"""
Copy Chrome profile and launch via Playwright to extract X cookies.
Chrome itself decrypts the cookies, we just read them via JS.
"""
import asyncio
import shutil
import os
import tempfile
import json
from playwright.async_api import async_playwright

PROFILE_SRC = '/home/lei/.config/google-chrome'
PROFILE_DST = '/tmp/chrome_profile_copy'

async def main():
    # Step 1: Copy profile (just the essential files)
    print("Copying Chrome profile...")
    if os.path.exists(PROFILE_DST):
        shutil.rmtree(PROFILE_DST)
    
    # Copy the key files - we need Cookies, but also Local State which may have key
    os.makedirs(os.path.join(PROFILE_DST, 'Default'), exist_ok=True)
    
    # Copy Local State
    shutil.copy2(os.path.join(PROFILE_SRC, 'Local State'), 
                 os.path.join(PROFILE_DST, 'Local State'))
    
    # Copy Cookies DB
    shutil.copy2(os.path.join(PROFILE_SRC, 'Default', 'Cookies'),
                 os.path.join(PROFILE_DST, 'Default', 'Cookies'))
    print("Profile copied")
    
    # Step 2: Launch Chrome with copied profile
    async with async_playwright() as p:
        print("Launching Chrome with copied profile...")
        context = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DST,
            channel='chrome',  # Use system Chrome
            headless=True,
            proxy={"server": "http://127.0.0.1:7890"},
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
            ]
        )
        
        page = context.pages[0] if context.pages else await context.new_page()
        
        print("Navigating to x.com...")
        await page.goto('https://x.com', wait_until='domcontentloaded', timeout=60000)
        await asyncio.sleep(3)
        
        title = await page.title()
        print(f"Title: {title}")
        print(f"URL: {page.url}")
        
        # Check if logged in
        is_login_page = 'login' in page.url.lower()
        print(f"On login page: {is_login_page}")
        
        if not is_login_page:
            # Extract cookies from browser context
            cookies = await context.cookies()
            x_cookies = {}
            for c in cookies:
                if 'x.com' in c.get('domain', '') or 'twitter.com' in c.get('domain', ''):
                    x_cookies[c['name']] = c['value']
                    print(f"  {c['name']} = {c['value'][:40]}...")
            
            # Save cookies
            output_path = '/root/.hermes/x_cookies_fresh_playwright.json'
            with open(output_path, 'w') as f:
                json.dump(x_cookies, f, indent=2)
            print(f"\nSaved {len(x_cookies)} cookies to {output_path}")
            
            # Also save as Netscape/curl format for httpx
            cookie_header = '; '.join([f"{k}={v}" for k, v in x_cookies.items() if k in ('auth_token', 'ct0', 'twid')])
            print(f"\nCookie header for httpx:")
            print(f"  {cookie_header[:100]}...")
            
            # Save as text
            with open('/root/.hermes/x_cookie_header.txt', 'w') as f:
                f.write(cookie_header)
        else:
            print("Still on login page - checking page content...")
            await page.screenshot(path='/tmp/x_copy_profile.png')
            content = await page.content()
            if 'cf-challenge' in content or 'cloudflare' in content.lower()[:5000]:
                print("Cloudflare blocking")
        
        await context.close()

asyncio.run(main())
