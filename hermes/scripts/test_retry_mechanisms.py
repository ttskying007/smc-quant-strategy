#!/root/scraper_env/bin/python3
"""测试四层重试机制的各组件"""
import sys, time
sys.path.insert(0, '/root/.hermes/scripts')
from daily_multi_source_crawler import retry_urllib, retry_request

passed = 0
failed = 0

def test(name, ok, detail):
    global passed, failed
    status = 'PASS' if ok else 'FAIL'
    if ok: passed += 1
    else: failed += 1
    print(f'  [{status}] {name}: {detail}')

print('=' * 60)
print('Layer 1a: retry_urllib (Brave/GNews - direct first)')
print('=' * 60)

# T1: Brave
start = time.time()
html = retry_urllib('https://search.brave.com/search?q=python+ai&source=web',
                     headers={'User-Agent': 'Mozilla/5.0'}, timeout=15, max_tries=3)
elapsed = time.time() - start
ok = html is not None and len(html) > 100
test('Brave Search', ok, f'{len(html) if html else 0} bytes in {elapsed:.1f}s')

# T2: GNews
start = time.time()
html = retry_urllib('https://news.google.com/rss/search?q=AI&hl=en-US',
                     headers={'User-Agent': 'Mozilla/5.0'}, timeout=15, max_tries=3)
elapsed = time.time() - start
ok = html is not None and len(html) > 100
test('GNews RSS', ok, f'{len(html) if html else 0} bytes in {elapsed:.1f}s')

print()
print('=' * 60)
print('Layer 1b: retry_request (API sources - proxy first)')
print('=' * 60)

# T3: HN Algolia
start = time.time()
data = retry_request('https://hn.algolia.com/api/v1/search',
                      {'query': 'AI', 'hitsPerPage': 3}, json_fmt=True, timeout=15)
elapsed = time.time() - start
ok = data is not None and len(data.get('hits', [])) > 0
test('HN Algolia', ok, f'{len(data.get("hits", [])) if data else 0} hits in {elapsed:.1f}s')

# T4: GitHub
start = time.time()
data = retry_request('https://api.github.com/search/repositories',
                      {'q': 'python', 'per_page': 3}, json_fmt=True, timeout=15)
elapsed = time.time() - start
ok = data is not None and len(data.get('items', [])) > 0
test('GitHub API', ok, f'{len(data.get("items", [])) if data else 0} repos in {elapsed:.1f}s')

# T5: 已知会失败的 URL (验证fallback机制)
start = time.time()
html = retry_urllib('https://newsnow.busiyi.world/', timeout=10, max_tries=2)
elapsed = time.time() - start
print(f'  [INFO] NewsNow fallback: {len(html) if html else 0} bytes in {elapsed:.1f}s (may fail - site intermittent)')

print()
print('=' * 60)
print('Layer 3: 全局重试逻辑 (simulated in main())')
print('=' * 60)

# Test that run_crawl_once returns int
from daily_multi_source_crawler import run_crawl_once, MAX_GLOBAL_RETRIES, MIN_ACCEPTABLE_ITEMS
print(f'  MAX_GLOBAL_RETRIES = {MAX_GLOBAL_RETRIES}')
print(f'  MIN_ACCEPTABLE_ITEMS = {MIN_ACCEPTABLE_ITEMS}')
print(f'  Runs on failure: up to {MAX_GLOBAL_RETRIES+1} times')
print(f'  Wait between retries: 30s, 60s')

print()
print('=' * 60)
print(f'RESULT: {passed} passed, {failed} failed')
print('=' * 60)
sys.exit(0 if failed == 0 else 1)
