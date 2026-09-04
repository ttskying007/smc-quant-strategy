#!/usr/bin/env python3
"""Playwright X scraper - inject cookies then scrape search results"""
import asyncio
import json
import re
from playwright.async_api import async_playwright

PROXY = "http://127.0.0.1:7890"

# Fresh cookies from Chrome (including auth_token!)
COOKIES_DATA = [
    {"name": "auth_token", "value": "94c33a4433814a44ae685c46c0611d8eeef8c363", "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": "7125be269b3185ac33e8e90cc0c924f24d9fb77d5a45318d5974ff3e86f4c386a6d40072dd1179589f00f2d8dd05b45418ade6de9c24bc5f2a5ec8f5748b826305e117cdf5a387b0933ff69f27b9867c", "domain": ".x.com", "path": "/"},
    {"name": "twid", "value": "u%3D488154571", "domain": ".x.com", "path": "/"},
    {"name": "guest_id", "value": "v1%3A177297400447928763", "domain": ".x.com", "path": "/"},
    {"name": "guest_id_ads", "value": "v1%3A177297400447928763", "domain": ".x.com", "path": "/"},
    {"name": "guest_id_marketing", "value": "v1%3A177297400447928763", "domain": ".x.com", "path": "/"},
    {"name": "personalization_id", "value": '"v1_6x8rnY8gxq97e7Gwb5/aqw=="', "domain": ".x.com", "path": "/"},
    {"name": "kdt", "value": "Sh9VZg6jwEQxNrG9uIpnYklHjR5EHDl6sgfmSZt5", "domain": ".x.com", "path": "/"},
    {"name": "lang", "value": "zh-CN", "domain": ".x.com", "path": "/"},
    {"name": "__cuid", "value": "6a5d224c81f14049b68dab86be6d596c", "domain": ".x.com", "path": "/"},
    {"name": "d_prefs", "value": "MToxLGNvbnNlbnRfdmVyc2lvbjoyLHRleHRfdmVyc2lvbjoxMDAw", "domain": ".x.com", "path": "/"},
]

async def scrape_search(browser, query, max_tweets=10):
    """Search X and extract tweets"""
    context = await browser.new_context(
        user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36',
        viewport={'width': 1280, 'height': 720},
        proxy={"server": PROXY},
    )
    await context.add_cookies(COOKIES_DATA)
    page = await context.new_page()
    
    # Navigate to search with latest tab
    encoded_q = query.replace(' ', '+')
    search_url = f'https://x.com/search?q={encoded_q}&src=typed_query&f=live'
    print(f"Navigating to: {search_url}")
    await page.goto(search_url, wait_until='domcontentloaded', timeout=60000)
    await asyncio.sleep(5)
    
    # Check if we're logged in
    title = await page.title()
    current_url = page.url
    print(f"Title: {title}")
    print(f"URL: {current_url}")
    
    if 'login' in current_url.lower():
        print("Redirected to login! Cookies may be expired.")
        text = await page.inner_text('body')
        print(f"Page text: {text[:500]}")
        await context.close()
        return []
    
    # Scroll to load more tweets
    for _ in range(3):
        await page.evaluate('window.scrollBy(0, 1000)')
        await asyncio.sleep(2)
    
    # Extract tweets
    tweets = await page.evaluate('''(max) => {
        const articles = document.querySelectorAll('article[data-testid="tweet"]');
        const results = [];
        for (const a of articles) {
            if (results.length >= max) break;
            
            const textEl = a.querySelector('[data-testid="tweetText"]');
            const timeEl = a.querySelector('time');
            const userLinks = a.querySelectorAll('[data-testid="User-Name"] a');
            let screenName = '', displayName = '';
            for (const link of userLinks) {
                const href = link.getAttribute('href') || '';
                if (href.startsWith('/') && !href.includes('/status/') && !href.includes('/search')) {
                    screenName = href.replace('/', '');
                    displayName = link.textContent || '';
                }
            }
            
            const linkEl = a.querySelector('a[href*="/status/"]');
            const tweetUrl = linkEl ? 'https://x.com' + linkEl.getAttribute('href') : '';
            const tweetId = tweetUrl ? tweetUrl.split('/status/')[1]?.split('?')[0] : '';
            
            const stats = {};
            a.querySelectorAll('[data-testid$="count"]').forEach(el => {
                const key = el.getAttribute('data-testid') || '';
                stats[key] = el.textContent || '0';
            });
            
            results.push({
                id: tweetId,
                url: tweetUrl,
                screen_name: screenName,
                display_name: displayName,
                text: textEl ? textEl.textContent : '',
                timestamp: timeEl ? timeEl.getAttribute('datetime') : '',
                reply_count: stats.reply || '0',
                retweet_count: stats.retweet || '0',
                like_count: stats.like || '0',
            });
        }
        return results;
    }''', max_tweets)
    
    print(f"Found {len(tweets)} tweets")
    for t in tweets[:5]:
        print(f"  @{t['screen_name']}: {t['text'][:80]}")
    
    await context.close()
    return tweets

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy={"server": PROXY},
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        
        # Test with multiple queries
        queries = ["AI agent", "hermes", "SMC trading"]
        
        for q in queries:
            print(f"\n{'='*60}")
            print(f"Searching: '{q}'")
            print('='*60)
            tweets = await scrape_search(browser, q, max_tweets=5)
            if not tweets:
                print("No results, trying to debug...")
                # Quick debug: load homepage
                ctx = await browser.new_context(proxy={"server": PROXY})
                await ctx.add_cookies(COOKIES_DATA)
                pg = await ctx.new_page()
                await pg.goto('https://x.com/home', wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(5)
                print(f"Home URL: {pg.url}")
                await ctx.close()
                break  # Stop if cookies don't work
        
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
