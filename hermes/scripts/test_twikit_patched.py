#!/usr/bin/env python3
"""Test twikit with monkey patch"""
import asyncio, sys, os
os.chdir('/root/.hermes')

sys.path.insert(0, '/root/.hermes/scripts')
import monkey_patch_twikit
monkey_patch_twikit.apply_patch()

async def main():
    from twikit import Client
    
    client = Client(language='zh-CN', proxy='http://127.0.0.1:7890')
    
    print("=== Twikit v2.3.3 + Patch Test ===")
    
    # Test 1: Login with credentials
    print("\n[1/3] Login with credentials...")
    try:
        await client.login(
            auth_info_1='ttskying',
            auth_info_2='ttskying007',
            password='ttskying007',
            cookies_file='/root/.hermes/x_cookies_fresh.json'
        )
        print("  ✅ Login successful!")
        
        # Get user info
        user = await client.user()
        print(f"  User: @{user.screen_name} (ID: {user.id})")
        print(f"  Name: {user.name}")
        print(f"  Followers: {user.followers_count}")
        
        USER_ID = user.id
    except Exception as e:
        print(f"  ❌ Login failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Test 2: Search tweets
    print("\n[2/3] Search 'AI agent' tweets...")
    try:
        tweets = await client.search_tweet('AI agent', 'Latest', count=5)
        print(f"  ✅ Found {len(tweets)} tweets")
        for t in tweets[:5]:
            print(f"  @{t.user.screen_name}: {t.text[:100]}")
    except Exception as e:
        print(f"  ❌ Search failed: {e}")
    
    # Test 3: Get user tweets
    print("\n[3/3] Get user tweets...")
    try:
        ut = await client.get_user_tweets(str(USER_ID), 'Tweets', count=5)
        print(f"  ✅ Found {len(ut)} tweets")
        for t in ut[:3]:
            print(f"  {t.text[:120]}")
    except Exception as e:
        print(f"  ❌ Get tweets failed: {e}")
    
    print("\n=== Done ===")

if __name__ == '__main__':
    asyncio.run(main())
