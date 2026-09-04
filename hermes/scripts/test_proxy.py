#!/root/scraper_env/bin/python3
"""Test proxy fallback for Brave/GNews"""
import urllib.request, ssl, time, sys

# Test 1: retry_urllib direct approach
from daily_multi_source_crawler import retry_urllib

print('=== Test A: retry_urllib Brave (direct+proxy fallback) ===')
start = time.time()
html = retry_urllib('https://search.brave.com/search?q=python+ai&source=web',
                     headers={'User-Agent': 'Mozilla/5.0'}, timeout=15, max_tries=2)
elapsed = time.time() - start
print(f'  Result: {len(html) if html else 0} bytes in {elapsed:.1f}s')
if html:
    print(f'  First 200 chars: {html[:200]}')

print()
print('=== Test B: retry_urllib GNews (direct+proxy fallback) ===')
start = time.time()
html = retry_urllib('https://news.google.com/rss/search?q=AI&hl=en-US',
                     headers={'User-Agent': 'Mozilla/5.0'}, timeout=15, max_tries=2)
elapsed = time.time() - start
print(f'  Result: {len(html) if html else 0} bytes in {elapsed:.1f}s')
if html:
    print(f'  First 200 chars: {html[:200]}')

print()
print('=== Test C: Manual proxy via urllib ===')
import urllib.request
ctx = ssl._create_unverified_context()
proxy_h = urllib.request.ProxyHandler({'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'})
opener = urllib.request.build_opener(proxy_h)
for url, name in [
    ('https://search.brave.com/search?q=python+ai&source=web', 'Brave'),
    ('https://news.google.com/rss/search?q=AI&hl=en-US', 'GNews'),
]:
    try:
        start = time.time()
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        r = opener.open(req, context=ctx, timeout=15)
        html = r.read().decode('utf-8', errors='replace')
        elapsed = time.time() - start
        print(f'  [{name}] urllib+proxy: {len(html)} bytes in {elapsed:.1f}s')
        if len(html) < 100:
            print(f'    Content: {html[:200]}')
    except Exception as e:
        elapsed = time.time() - start
        print(f'  [{name}] FAIL: {str(e)[:80]} in {elapsed:.1f}s')

print()
print('=== Test D: Python requests via proxy ===')
import requests
proxies = {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}
for url, name in [
    ('https://search.brave.com/search?q=python+ai&source=web', 'Brave'),
    ('https://news.google.com/rss/search?q=AI&hl=en-US', 'GNews'),
]:
    try:
        start = time.time()
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'},
                         proxies=proxies, timeout=15)
        elapsed = time.time() - start
        print(f'  [{name}] requests+proxy: HTTP {r.status_code}, {len(r.text)} bytes in {elapsed:.1f}s')
    except Exception as e:
        elapsed = time.time() - start
        print(f'  [{name}] FAIL: {str(e)[:80]} in {elapsed:.1f}s')
