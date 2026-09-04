#!/usr/bin/env python3
"""Test Playwright + X with cookies - bypass twikit issues"""
import asyncio, json, re, os
from playwright.async_api import async_playwright

COOKIES_STR = 'guest_id=v1%3A174833691628213588; __cuid=238c4ca7dbd2487da438d9f43b539179; guest_id_marketing=v1%3A174833691628213588; guest_id_ads=v1%3A174833691628213588; d_prefs=MToxLGNvbnNlbnRfdmVyc2lvbjoyLHRleHRfdmVyc2lvbjoxMDAw; personalization_id="v1_gfF9OeWywzuDvVem2OwXzQ=="; ct0=790a25b8f1c87e65d32810b3327d1df29386657f911837ff759b56645f77f09b6eaa6e6c39921616d970e3ed1cdba584c8fc6e9b51d60bed6dbe694eca4cefa017a72ba3592460e9e8ab812b22088d1f; twid=u%3D488154571; lang=zh-CN'

async def main():
    print("=" * 60)
    print("Playwright + X Cookie Scraper Test")
    print("=" * 60)
    
    cookie_list = []
    for item in COOKIES_STR.split('; '):
        if '=' in item:
            k, v = item.split('=', 1)
            cookie_list.append({"name": k, "value": v, "domain": ".x.com", "path": "/"})
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy={"server": "http://127.0.0.1:7890"},
            args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15',
            viewport={'width': 1280, 'height': 720}
        )
        await context.add_cookies(cookie_list)
        
        page = await context.new_page()
        
        # Step 1: Go to x.com main page
        print("\n[1/3] Loading x.com...")
        try:
            await page.goto('https://x.com', wait_until='domcontentloaded', timeout=45000)
            await asyncio.sleep(4)
            print(f"  Title: {await page.title()}")
            print(f"  URL: {page.url[:80]}")
            
            content = await page.content()
            if 'cloudflare' in content.lower()[:3000]:
                print("  ❌ Cloudflare blocked!")
                await browser.close()
                return
            print("  ✅ Page loaded!")
            
            # Check if logged in
            logged_in = await page.evaluate('() => document.cookie.includes("twid")')
            print(f"  Logged in (cookie check): {logged_in}")
            
        except Exception as e:
            print(f"  Error: {e}")
            await browser.close()
            return
        
        # Step 2: Search for tweets
        print("\n[2/3] Searching for 'AI agent'...")
        try:
            await page.goto(
                'https://x.com/search?q=AI+agent&src=typed_query&f=live',
                wait_until='domcontentloaded', timeout=45000
            )
            await asyncio.sleep(5)
            print(f"  Search URL: {page.url[:80]}")
            
            # Wait a bit more for tweets to load
            await page.wait_for_timeout(3000)
            
            # Try scrolling to trigger loading
            await page.evaluate('window.scrollTo(0, 500)')
            await page.wait_for_timeout(2000)
            
            # Extract tweets
            tweets = await page.evaluate('''
                () => {
                    const articles = document.querySelectorAll('article[data-testid="tweet"]');
                    return Array.from(articles).slice(0, 10).map(a => {
                        const textEl = a.querySelector('[data-testid="tweetText"]');
                        const userLinks = a.querySelectorAll('[data-testid="User-Name"] a, [data-testid="User-Name"] span');
                        const timeEl = a.querySelector('time');
                        const likeBtn = a.querySelector('[data-testid="like"]');
                        const retweetBtn = a.querySelector('[data-testid="retweet"]');
                        const replyBtn = a.querySelector('[data-testid="reply"]');
                        
                        // Extract username from href
                        let screenName = '';
                        let displayName = '';
                        userLinks.forEach(el => {
                            const href = el.getAttribute('href') || '';
                            if (href.startsWith('/') && !href.includes('/status/')) {
                                screenName = href.replace('/', '');
                            }
                        });
                        
                        return {
                            text: textEl ? textEl.textContent : '',
                            screen_name: screenName,
                            time: timeEl ? timeEl.getAttribute('datetime') : '',
                            likes: likeBtn ? (likeBtn.getAttribute('aria-label') || '') : '',
                            retweets: retweetBtn ? (retweetBtn.getAttribute('aria-label') || '') : '',
                            replies: replyBtn ? (replyBtn.getAttribute('aria-label') || '') : '',
                        };
                    });
                }
            ''')
            print(f"  Found {len(tweets)} tweets")
            for t in tweets:
                print(f"  @{t['screen_name']}: {t['text'][:80]}")
                print(f"    ❤{t['likes']} 🔁{t['retweets']}")
                print(f"    ---")
            
        except Exception as e:
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()
        
        # Step 3: Get user timeline
        print("\n[3/3] Getting @ttskying timeline...")
        try:
            await page.goto(
                'https://x.com/ttskying',
                wait_until='domcontentloaded', timeout=45000
            )
            await asyncio.sleep(5)
            await page.evaluate('window.scrollTo(0, 500)')
            await page.wait_for_timeout(2000)
            
            tweets = await page.evaluate('''
                () => {
                    const articles = document.querySelectorAll('article[data-testid="tweet"]');
                    return Array.from(articles).slice(0, 5).map(a => {
                        const textEl = a.querySelector('[data-testid="tweetText"]');
                        const timeEl = a.querySelector('time');
                        return {
                            text: textEl ? textEl.textContent : '',
                            time: timeEl ? timeEl.getAttribute('datetime') : '',
                        };
                    });
                }
            ''')
            print(f"  Found {len(tweets)} tweets")
            for t in tweets:
                print(f"  {t['text'][:100]}")
                print(f"    {t['time']}")
            
        except Exception as e:
            print(f"  Error: {e}")
        
        await browser.close()
        print("\n=== Done ===")

if __name__ == '__main__':
    asyncio.run(main())
