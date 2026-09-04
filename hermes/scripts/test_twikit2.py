#!/usr/bin/env python3
"""Test twikit with proxy"""
import asyncio, json
from twikit import Client

COOKIES_STR = 'guest_id=v1%3A174833691628213588; __cuid=238c4ca7dbd2487da438d9f43b539179; guest_id_marketing=v1%3A174833691628213588; guest_id_ads=v1%3A174833691628213588; d_prefs=MToxLGNvbnNlbnRfdmVyc2lvbjoyLHRleHRfdmVyc2lvbjoxMDAw; personalization_id="v1_gfF9OeWywzuDvVem2OwXzQ=="; g_state={"i_l":0,"i_ll":1775035533144,"i_e":{"enable_itp_optimization":0}}; ct0=790a25b8f1c87e65d32810b3327d1df29386657f911837ff759b56645f77f09b6eaa6e6c39921616d970e3ed1cdba584c8fc6e9b51d60bed6dbe694eca4cefa017a72ba3592460e9e8ab812b22088d1f; twid=u%3D488154571; lang=zh-CN'

def parse_cookies(cookie_str):
    cookies = {}
    for part in cookie_str.split('; '):
        if '=' in part:
            k, v = part.split('=', 1)
            cookies[k.strip()] = v.strip()
    return cookies

async def main():
    cookies = parse_cookies(COOKIES_STR)
    
    # Use proxy
    client = Client(language='en-US', proxy='http://127.0.0.1:7890')
    client.set_cookies(cookies)
    
    print("Testing twikit with proxy...")
    
    try:
        tweets = await client.search_tweet('AI agent open source', 'Latest', count=5)
        print(f"SUCCESS! Got {len(tweets)} tweets")
        for t in tweets[:3]:
            user = t.user
            print(f"\n@{user.screen_name}: {t.text[:120]}")
            print(f"   ♥{t.favorite_count} 🔁{t.retweet_count} 💬{t.reply_count}")
    except Exception as e:
        print(f"Failed: {type(e).__name__}: {e}")
    
    # Try without proxy
    print("\n\nTrying without proxy...")
    client2 = Client(language='en-US')
    client2.set_cookies(cookies)
    
    try:
        tweets2 = await client2.search_tweet('AI', 'Latest', count=3)
        print(f"SUCCESS! Got {len(tweets2)} tweets")
        for t in tweets2[:2]:
            print(f"\n@{t.user.screen_name}: {t.text[:120]}")
    except Exception as e:
        print(f"Failed: {type(e).__name__}: {e}")

if __name__ == '__main__':
    asyncio.run(main())
