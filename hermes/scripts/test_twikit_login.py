#!/usr/bin/env python3
"""Fix twikit: Patch x_client_transaction to handle new X page format"""
import asyncio
import sys
import os

os.chdir('/root/.hermes')

async def main():
    from twikit import Client

    client = Client(language='zh-CN', proxy='http://127.0.0.1:7890')
    
    # Try login with credentials (handles auth flow properly)
    print("=== Twikit Login Test ===")
    print("Logging in with credentials...")
    
    try:
        await client.login(
            auth_info_1='ttskying',     # username
            auth_info_2='ttskying007',  # password  
            password='ttskying007',
            cookies_file='/root/.hermes/x_cookies_fresh.json'
        )
        print("Login successful!")
        
        # Get user info
        user = await client.user()
        print(f"User: @{user.screen_name} (ID: {user.id})")
        print(f"Name: {user.name}")
        print(f"Followers: {user.followers_count}")
        
        # Search for tweets
        print("\n=== Searching for 'AI agent' tweets ===")
        tweets = await client.search_tweet('AI agent', 'Latest', count=5)
        print(f"Found {len(tweets)} tweets")
        for t in tweets[:3]:
            print(f"  @{t.user.screen_name}: {t.text[:100]}")
        
        # Get my user tweets
        print(f"\n=== My recent tweets ===")
        tweets2 = await client.get_user_tweets(str(user.id), 'Tweets', count=5)
        print(f"Found {len(tweets2)} tweets")
        for t in tweets2[:3]:
            print(f"  {t.text[:100]}")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())
