#!/usr/bin/env python3
"""
X/twitter scraper using browser cookies + direct GraphQL API
Bypasses twikit's broken x_client_transaction and Cloudflare issues
by using the same cookie the user provided.
"""
import asyncio, httpx, json, re, os, time
from datetime import datetime

COOKIES_STR = 'guest_id=v1%3A174833691628213588; __cuid=238c4ca7dbd2487da438d9f43b539179; guest_id_marketing=v1%3A174833691628213588; guest_id_ads=v1%3A174833691628213588; d_prefs=MToxLGNvbnNlbnRfdmVyc2lvbjoyLHRleHRfdmVyc2lvbjoxMDAw; personalization_id="v1_gfF9OeWywzuDvVem2OwXzQ=="; ct0=790a25b8f1c87e65d32810b3327d1df29386657f911837ff759b56645f77f09b6eaa6e6c39921616d970e3ed1cdba584c8fc6e9b51d60bed6dbe694eca4cefa017a72ba3592460e9e8ab812b22088d1f; twid=u%3D488154571; lang=zh-CN'

X_BEARER_TOKEN = 'AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA'

def parse_cookies(s):
    c = {}
    for item in s.split('; '):
        if '=' in item:
            k, v = item.split('=', 1)
            c[k.strip()] = v.strip()
    return c

cookies = parse_cookies(COOKIES_STR)
ct0 = cookies.get('ct0', '')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15',
    'Authorization': f'Bearer {X_BEARER_TOKEN}',
    'x-csrf-token': ct0,
    'Cookie': COOKIES_STR,
    'Content-Type': 'application/json',
    'Origin': 'https://x.com',
    'Referer': 'https://x.com/',
}

# Known working GraphQL query IDs (as of 2025)
# Search timeline uses SearchTimeline query
SEARCH_TIMELINE_ID = "gkjsKepM6gl_HFWGgVWYIg"  # This might be stale

FEATURES = {
    "hidden_profile_subscriptions_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "subscriptions_verification_info_is_identity_verified_enabled": True,
    "subscriptions_verification_info_verified_since_enabled": True,
    "highlights_tweets_tab_ui_enabled": True,
    "responsive_web_twitter_article_notes_tab_enabled": True,
    "subscriptions_feature_can_gift_premium": True,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
}

# Try multiple known search endpoint IDs
SEARCH_IDS = [
    "gkjsKepM6gl_HFWGgVWYIg",
    "7Pq1sT0NhJxuZ4Z3e2yXiQ",
    "nK1f4q5z6Yx8Rv0Lm3AsBw",
]

async def try_search(client, search_id, keyword, count=10):
    url = f"https://api.x.com/graphql/{search_id}/SearchTimeline"
    variables = {
        "rawQuery": keyword,
        "count": count,
        "querySource": "typed_query",
        "product": "Top"
    }
    params = {"variables": json.dumps(variables), "features": json.dumps(FEATURES)}
    
    try:
        resp = await client.get(url, params=params, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            return resp.json(), True
        return {"error": resp.status_code, "body": resp.text[:300]}, False
    except Exception as e:
        return {"error": str(e)}, False

async def search_tweets(keyword, count=10):
    async with httpx.AsyncClient(timeout=30.0, proxy='http://127.0.0.1:7890') as client:
        # Try different search IDs
        for sid in SEARCH_IDS:
            data, ok = await try_search(client, sid, keyword, count)
            if ok:
                return data
        return None

async def extract_tweets_from_response(data):
    """Extract tweet data from X API response"""
    tweets = []
    try:
        instructions = data['data']['search_by_raw_query']['search_timeline']['timeline']['instructions']
        entries = []
        for inst in instructions:
            if inst.get('type') == 'TimelineAddEntries':
                entries = inst.get('entries', [])
        
        for entry in entries:
            if entry.get('content', {}).get('entryType') == 'TimelineTimelineItem':
                result = entry.get('content', {}).get('itemContent', {}).get('tweet_results', {}).get('result', {})
                if not result:
                    continue
                
                legacy = result.get('legacy', {})
                core = result.get('core', {}).get('user_results', {}).get('result', {}).get('legacy', {})
                
                tweets.append({
                    'id': result.get('rest_id', ''),
                    'text': legacy.get('full_text', legacy.get('text', '')),
                    'created_at': legacy.get('created_at', ''),
                    'author': core.get('screen_name', ''),
                    'author_name': core.get('name', ''),
                    'author_followers': core.get('followers_count', 0),
                    'author_verified': core.get('verified', False),
                    'likes': legacy.get('favorite_count', 0),
                    'retweets': legacy.get('retweet_count', 0),
                    'replies': legacy.get('reply_count', 0),
                    'views': legacy.get('ext_views', {}).get('count', 0) if legacy.get('ext_views') else 0,
                    'url': f"https://x.com/{core.get('screen_name', '')}/status/{result.get('rest_id', '')}",
                    'source': 'x_direct',
                })
    except Exception as e:
        print(f"  Parse error: {e}")
    
    return tweets

async def main():
    print("=" * 60)
    print(f"X Direct API Scraper — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    keywords = ['AI agent', 'hermes', 'LLM', 'open source AI']
    
    for kw in keywords:
        print(f"\nSearching: '{kw}'")
        data = await search_tweets(kw, count=5)
        if data:
            tweets = await extract_tweets_from_response(data)
            print(f"  Found: {len(tweets)} tweets")
            for t in tweets[:3]:
                print(f"  @{t['author']}: {t['text'][:80]}...")
                print(f"    ❤{t['likes']} 🔁{t['retweets']} 👁{t['views']}")
        else:
            print(f"  ❌ No results from any endpoint")
    
    print("\n=== Done ===")

if __name__ == '__main__':
    asyncio.run(main())
