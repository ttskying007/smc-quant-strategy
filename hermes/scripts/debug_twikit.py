#!/usr/bin/env python3
"""Debug twikit v2.3.3 x_client_transaction issue"""
import asyncio
import httpx
import json
import os

async def debug_x_transaction():
    """Manually reproduce what x_client_transaction does"""
    
    # Same cookies as before
    COOKIES_STR = 'guest_id=v1%3A174833691628213588; __cuid=238c4ca7dbd2487da438d9f43b539179; guest_id_marketing=v1%3A174833691628213588; guest_id_ads=v1%3A174833691628213588; d_prefs=MToxLGNvbnNlbnRfdmVyc2lvbjoyLHRleHRfdmVyc2lvbjoxMDAw; personalization_id="v1_gfF9OeWywzuDvVem2OwXzQ=="; ct0=790a25b8f1c87e65d32810b3327d1df29386657f911837ff759b56645f77f09b6eaa6e6c39921616d970e3ed1cdba584c8fc6e9b51d60bed6dbe694eca4cefa017a72ba3592460e9e8ab812b22088d1f; twid=u%3D488154571; lang=zh-CN'
    
    cookies = {}
    for item in COOKIES_STR.split('; '):
        if '=' in item:
            k, v = item.split('=', 1)
            cookies[k.strip()] = v.strip()
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15',
        'Cookie': COOKIES_STR,
        'x-csrf-token': cookies.get('ct0', ''),
    }
    
    print("=" * 60)
    print("Step 1: Fetch https://x.com (no proxy)")
    print("=" * 60)
    
    # Try WITHOUT proxy first
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get('https://x.com', headers=headers, follow_redirects=True)
            print(f"Status: {resp.status_code}")
            print(f"Content length: {len(resp.content)}")
            print(f"Final URL: {resp.url}")
            
            # Check key elements
            text = resp.text
            has_twitter_site = 'twitter-site-verification' in text
            has_ondemand = 'ondemand.s' in text
            has_migrate = 'migrate' in text.lower()
            print(f"Has twitter-site-verification: {has_twitter_site}")
            print(f"Has ondemand: {has_ondemand}")
            print(f"Has migrate: {has_migrate}")
            
            if has_twitter_site:
                import re
                match = re.search(r'name=["\']twitter-site-verification["\'].*?content=["\']([^"\']+)["\']', text)
                if match:
                    print(f"Key found: {match.group(1)[:30]}...")
            
            if has_ondemand:
                match = re.search(r"""['"]ondemand\.s['"]\s*:\s*['"]([\w]*)['"]""", text)
                if match:
                    print(f"On-demand file hash: {match.group(1)}")
            
            print(f"\nFirst 1000 chars of response:")
            print(text[:1000])
            
        except Exception as e:
            print(f"Error (no proxy): {e}")
    
    print("\n" + "=" * 60)
    print("Step 2: Fetch https://x.com (WITH proxy)")
    print("=" * 60)
    
    proxies = {'http://': 'http://127.0.0.1:7890', 'https://': 'http://127.0.0.1:7890'}
    async with httpx.AsyncClient(timeout=30.0, proxy='http://127.0.0.1:7890') as client:
        try:
            resp = await client.get('https://x.com', headers=headers, follow_redirects=True)
            print(f"Status: {resp.status_code}")
            print(f"Content length: {len(resp.content)}")
            print(f"Final URL: {resp.url}")
            
            text = resp.text
            has_twitter_site = 'twitter-site-verification' in text
            has_ondemand = 'ondemand.s' in text
            has_migrate = 'migrate' in text.lower()
            print(f"Has twitter-site-verification: {has_twitter_site}")
            print(f"Has ondemand: {has_ondemand}")
            print(f"Has migrate: {has_migrate}")
            
            print(f"\nFirst 800 chars of response:")
            print(text[:800])
            
        except Exception as e:
            print(f"Error (with proxy): {e}")

if __name__ == '__main__':
    asyncio.run(debug_x_transaction())
