#!/usr/bin/env python3
"""Test twikit with browser cookies and verify data completeness"""
import asyncio
import json
from datetime import datetime

COOKIES_STR = 'guest_id=v1%3A174833691628213588; __cuid=238c4ca7dbd2487da438d9f43b539179; guest_id_marketing=v1%3A174833691628213588; guest_id_ads=v1%3A174833691628213588; d_prefs=MToxLGNvbnNlbnRfdmVyc2lvbjoyLHRleHRfdmVyc2lvbjoxMDAw; personalization_id="v1_gfF9OeWywzuDvVem2OwXzQ=="; g_state={"i_l":0,"i_ll":1775035533144,"i_e":{"enable_itp_optimization":0}}; ct0=790a25b8f1c87e65d32810b3327d1df29386657f911837ff759b56645f77f09b6eaa6e6c39921616d970e3ed1cdba584c8fc6e9b51d60bed6dbe694eca4cefa017a72ba3592460e9e8ab812b22088d1f; twid=u%3D488154571; lang=zh-CN'

def parse_cookies(cookie_str):
    cookies = {}
    for item in cookie_str.split('; '):
        if '=' in item:
            key, value = item.split('=', 1)
            cookies[key.strip()] = value.strip()
    return cookies

async def main():
    from twikit import Client

    client = Client(language='zh-CN', proxy='http://127.0.0.1:7890')
    cookies = parse_cookies(COOKIES_STR)

    print("=" * 60)
    print(f"twikit v2.3.3 - X/Twitter Data Scraper Test")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Step 1: Set cookies
    print("\n[1/4] Setting cookies from browser...")
    client.set_cookies(cookies)
    print(f"  Cookie count: {len(cookies)}")
    print(f"  ct0: {'ct0' in cookies}, twid: {'twid' in cookies}")
    client.save_cookies('/root/.hermes/x_cookies.json')
    print("  Cookies saved")

    # Step 2: Auth test
    print("\n[2/4] Testing authentication...")
    try:
        user = await client.get_user_by_screen_name('ttskying')
        print(f"  Logged in as: @{user.screen_name}")
        print(f"  User ID: {user.id}")
        print(f"  Name: {user.name}")
        print(f"  Followers: {user.followers_count}")
        print(f"  Verified: {user.verified}")
        USER_ID = user.id
    except Exception as e:
        print(f"  Auth test failed: {e}")
        import traceback
        traceback.print_exc()
        USER_ID = None

    # Step 3: Search tweets
    print("\n[3/4] Testing tweet search (AI agent)...")
    try:
        tweets = await client.search_tweet('AI agent', 'Latest', count=5)
        print(f"  Found {len(tweets)} tweets")
        for i, tweet in enumerate(tweets[:3]):
            print(f"\n  [{i+1}] @{tweet.user.screen_name}")
            print(f"      Text: {tweet.text[:150]}")
            print(f"      Likes: {tweet.favorite_count}, RTs: {tweet.retweet_count}")
            print(f"      Time: {tweet.created_at}")
            print(f"      URL: https://x.com/{tweet.user.screen_name}/status/{tweet.id}")
    except Exception as e:
        print(f"  Search failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)

if __name__ == '__main__':
    asyncio.run(main())
