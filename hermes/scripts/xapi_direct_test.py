#!/usr/bin/env python3
"""Test X API directly with fresh cookies from Chrome"""
import httpx
import json
import time

PROXY = "http://127.0.0.1:7890"
BEARER = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"

COOKIES = {
    "auth_token": "94c33a4433814a44ae685c46c0611d8eeef8c363",
    "ct0": "7125be269b3185ac33e8e90cc0c924f24d9fb77d5a45318d5974ff3e86f4c386a6d40072dd1179589f00f2d8dd05b45418ade6de9c24bc5f2a5ec8f5748b826305e117cdf5a387b0933ff69f27b9867c",
    "twid": "u%3D488154571",
    "guest_id": "v1%3A177297400447928763",
    "guest_id_ads": "v1%3A177297400447928763",
    "guest_id_marketing": "v1%3A177297400447928763",
    "personalization_id": '"v1_6x8rnY8gxq97e7Gwb5/aqw=="',
    "lang": "zh-CN",
}

HEADERS = {
    "authorization": f"Bearer {BEARER}",
    "x-csrf-token": COOKIES["ct0"],
    "content-type": "application/json",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "origin": "https://x.com",
    "referer": "https://x.com/",
}

# Known GraphQL query IDs - these are the ones that work with the current X API
# Search timeline: recent tweets
SEARCH_TIMELINE_QUERY = "qGJYUWzp-OjO2yAfIyaA-A"  # SearchTimeline
USER_TIMELINE_QUERY = "xIiJoGH-2tCqQSD-FkEKVQ"  # UserByScreenName + UserTweets

# Step 1: Test basic connectivity
with httpx.Client(proxy=PROXY, headers=HEADERS, cookies=COOKIES) as client:
    print("=== Test 1: Search recent tweets ===")
    variables = {
        "rawQuery": "AI agent",
        "count": 5,
        "querySource": "typed_query",
        "product": "Latest",
    }
    features = {
        "rweb_tipjar_consumption_enabled": True,
        "responsive_web_graphql_exclude_directive_enabled": True,
        "verified_phone_label_enabled": False,
        "creator_subscriptions_tweet_preview_api_enabled": True,
        "responsive_web_graphql_timeline_navigation_enabled": True,
        "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
        "communities_web_enable_tweet_community_results_fetch": True,
        "c9s_tweet_anatomy_moderator_badge_enabled": True,
        "articles_preview_enabled": True,
        "tweetypie_unmention_optimization_enabled": True,
        "responsive_web_edit_tweet_api_enabled": True,
        "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
        "view_counts_everywhere_api_enabled": True,
        "longform_notetweets_consumption_enabled": True,
        "responsive_web_twitter_article_tweet_consumption_enabled": True,
        "tweet_awards_web_tipping_enabled": False,
        "creator_subscriptions_quote_tweet_preview_enabled": False,
        "freedom_of_speech_not_reach_fetch_enabled": True,
        "standardized_nudges_misinfo": True,
        "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
        "rweb_video_timestamps_enabled": True,
        "longform_notetweets_rich_text_read_enabled": True,
        "longform_notetweets_inline_media_enabled": True,
        "responsive_web_enhance_cards_enabled": False,
    }
    
    url = f"https://api.x.com/graphql/{SEARCH_TIMELINE_QUERY}/SearchTimeline"
    params = {
        "variables": json.dumps(variables),
        "features": json.dumps(features),
    }
    
    resp = client.get(url, params=params)
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        if "data" in data:
            print("  Got data!")
            # Extract tweets
            try:
                instructions = data["data"]["search_by_raw_query"]["search_timeline"]["timeline"]["instructions"]
                for inst in instructions:
                    if inst.get("type") == "TimelineAddEntries":
                        entries = inst.get("entries", [])
                        print(f"  Found {len(entries)} entries")
                        for e in entries[:5]:
                            content = e.get("content", {})
                            item = content.get("itemContent", {})
                            tweet = item.get("tweet_results", {}).get("result", {})
                            legacy = tweet.get("legacy", {})
                            if legacy and legacy.get("full_text"):
                                user = legacy.get("user_id_str", "?")
                                print(f"  Tweet: {legacy['full_text'][:80]}")
            except (KeyError, TypeError) as e:
                print(f"  Parse error: {e}")
                print(f"  Response preview: {json.dumps(data, indent=2)[:2000]}")
        else:
            print(f"  No data key: {json.dumps(data, indent=2)[:1000]}")
    else:
        print(f"  Error: {resp.text[:500]}")
    
    # Step 2: Get user timeline
    print("\n=== Test 2: Get @ttskying profile ===")
    
    # First get user by screen name
    user_vars = {"screen_name": "ttskying", "withSafetyModeUserFields": True}
    user_params = {
        "variables": json.dumps(user_vars),
    }
    
    # Use a simpler endpoint - UserByScreenName
    user_resp = client.get(
        "https://api.x.com/graphql/7emiR1KvHDAoxWF4SWs4Tg/UserByScreenName",
        params=user_params
    )
    print(f"  Status: {user_resp.status_code}")
    if user_resp.status_code == 200:
        print(f"  Response: {json.dumps(user_resp.json(), indent=2)[:1500]}")
    else:
        print(f"  Error: {user_resp.text[:500]}")

print("\n=== Done ===")
