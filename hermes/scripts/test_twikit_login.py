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
        # SECURITY FIX(2026-09-08, 审计 P0-8): 凭据从环境变量读取，禁止明文密码入仓库。
        # 历史提交中曾出现明文密码 —— 该密码已按审计要求轮换，历史记录见安全报告。
        import os as _os
        _user = _os.environ.get("TWIKIT_USERNAME", "")
        _pwd = _os.environ.get("TWIKIT_PASSWORD", "")
        if not (_user and _pwd):
            print("缺少 TWIKIT_USERNAME / TWIKIT_PASSWORD 环境变量，跳过登录测试")
            return
        await client.login(
            auth_info_1=_user,
            auth_info_2=_pwd,
            password=_pwd,
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
