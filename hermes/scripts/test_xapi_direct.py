#!/usr/bin/env python3
"""Test if X API works WITHOUT x-client-transaction-id"""
import asyncio
import httpx
import json
import re
import os

COOKIES_STR = 'guest_id=v1%3A174833691628213588; __cuid=238c4ca7dbd2487da438d9f43b539179; guest_id_marketing=v1%3A174833691628213588; guest_id_ads=v1%3A174833691628213588; d_prefs=MToxLGNvbnNlbnRfdmVyc2lvbjoyLHRleHRfdmVyc2lvbjoxMDAw; personalization_id="v1_gfF9OeWywzuDvVem2OwXzQ=="; ct0=790a25b8f1c87e65d32810b3327d1df29386657f911837ff759b56645f77f09b6eaa6e6c39921616d970e3ed1cdba584c8fc6e9b51d60bed6dbe694eca4cefa017a72ba3592460e9e8ab812b22088d1f; twid=u%3D488154571; lang=zh-CN'

async def main():
    # Parse cookies
    cookies = {}
    for item in COOKIES_STR.split('; '):
        if '=' in item:
            k, v = item.split('=', 1)
            cookies[k.strip()] = v.strip()
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15',
        'Authorization': 'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
        'x-csrf-token': cookies.get('ct0', ''),
        'Cookie': COOKIES_STR,
        'Content-Type': 'application/json',
        'Origin': 'https://x.com',
        'Referer': 'https://x.com/',
    }
    
    print("=" * 60)
    print("Test: X API without x-client-transaction-id")
    print("=" * 60)
    
    async with httpx.AsyncClient(timeout=30.0, proxy='http://127.0.0.1:7890') as client:
        # Test 1: Get user by screen name (GraphQL)
        print("\n[Test 1] Get user @ttskying via GraphQL API...")
        
        # This uses the UserByScreenName endpoint
        url = "https://api.x.com/graphql/7mjxD3-C6BxitPMVQ6w0-Q/UserByScreenName"
        variables = {"screen_name": "ttskying", "withSafetyModeUserFields": True}
        features = {"hidden_profile_subscriptions_enabled": True, "rweb_tipjar_consumption_enabled": True, "responsive_web_graphql_exclude_directive_enabled": True, "verified_phone_label_enabled": False, "subscriptions_verification_info_is_identity_verified_enabled": True, "subscriptions_verification_info_verified_since_enabled": True, "highlights_tweets_tab_ui_enabled": True, "responsive_web_twitter_article_notes_tab_enabled": True, "subscriptions_feature_can_gift_premium": True, "creator_subscriptions_tweet_preview_api_enabled": True, "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False, "responsive_web_graphql_timeline_navigation_enabled": True}
        
        params = {"variables": json.dumps(variables), "features": json.dumps(features)}
        
        try:
            resp = await client.get(url, params=params, headers=headers)
            print(f"  Status: {resp.status_code}")
            data = resp.json()
            if resp.status_code == 200:
                user_data = data.get('data', {}).get('user', {}).get('result', {})
                print(f"  User: {user_data.get('legacy', {}).get('name', 'N/A')}")
                print(f"  Handle: @{user_data.get('legacy', {}).get('screen_name', 'N/A')}")
                print(f"  ✅ API works without x-client-transaction-id!")
            else:
                print(f"  Error: {json.dumps(data, indent=2)[:500]}")
        except Exception as e:
            print(f"  Exception: {e}")
        
        # Test 2: Search tweets
        print("\n[Test 2] Search tweets...")
        search_url = "https://api.x.com/graphql/gkjsKepM6gl_HFWGgVWYIg/SearchTimeline"
        search_vars = {"rawQuery": "AI agent", "count": 5, "querySource": "typed_query", "product": "Top"}
        
        params2 = {"variables": json.dumps(search_vars), "features": json.dumps(features)}
        
        try:
            resp2 = await client.get(search_url, params=params2, headers=headers)
            print(f"  Status: {resp2.status_code}")
            if resp2.status_code == 200:
                print(f"  ✅ Search works without x-client-transaction-id!")
                data2 = resp2.json()
                instructions = data2.get('data', {}).get('search_by_raw_query', {}).get('search_timeline', {}).get('timeline', {}).get('instructions', [])
                entries = []
                for inst in instructions:
                    if inst.get('type') == 'TimelineAddEntries':
                        entries = inst.get('entries', [])
                print(f"  Found {len(entries)} tweet entries")
            else:
                print(f"  Error: {resp2.text[:300]}")
        except Exception as e:
            print(f"  Exception: {e}")

if __name__ == '__main__':
    asyncio.run(main())
