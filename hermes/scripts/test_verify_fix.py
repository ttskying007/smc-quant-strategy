#!/root/scraper_env/bin/python3
"""Quick post-fix verification"""
import sys, time, os, py_compile
sys.path.insert(0, '/root/.hermes/scripts')
from daily_multi_source_crawler import retry_urllib, retry_request, PROXIES

print('=== Post-fix verification ===')
print()

# T1: retry_urllib proxy fallback
print('T1: retry_urllib proxy fallback (Brave)')
start = time.time()
html = retry_urllib('https://search.brave.com/search?q=test&source=web',
                     timeout=10, max_tries=1)
elapsed = time.time() - start
ok = len(html) > 100 if html else False
print(f'  {"PASS" if ok else "FAIL"}: {len(html) if html else 0} bytes in {elapsed:.1f}s')

# T2: retry_urllib direct path still works
print('T2: retry_urllib direct path (via proxy for speed)')
start = time.time()
html = retry_urllib('https://news.google.com/rss/search?q=AI&hl=en-US',
                     timeout=10, max_tries=1)
elapsed = time.time() - start
ok = len(html) > 100 if html else False
print(f'  {"PASS" if ok else "FAIL"}: {len(html) if html else 0} bytes in {elapsed:.1f}s')

# T3: retry_request proxy path
print('T3: retry_request (HN Algolia)')
start = time.time()
data = retry_request('https://hn.algolia.com/api/v1/search',
                      {'query': 'AI', 'hitsPerPage': 3}, json_fmt=True, timeout=15)
elapsed = time.time() - start
ok = data and len(data.get('hits', [])) > 0
print(f'  {"PASS" if ok else "FAIL"}: {len(data.get("hits",[])) if data else 0} hits in {elapsed:.1f}s')

# T4: retry_request direct fallback
print('T4: retry_request proxy->direct fallback (GitHub)')
start = time.time()
data = retry_request('https://api.github.com/search/repositories',
                      {'q': 'python', 'per_page': 3}, json_fmt=True, timeout=15)
elapsed = time.time() - start
ok = data and len(data.get('items', [])) > 0
print(f'  {"PASS" if ok else "FAIL"}: {len(data.get("items",[])) if data else 0} repos in {elapsed:.1f}s')

# T5: Script syntax
print('T5: Script syntax and integrity')
script = '/root/.hermes/scripts/daily_multi_source_crawler.py'
try:
    py_compile.compile(script, doraise=True)
    size = os.path.getsize(script)
    print(f'  PASS: {size} bytes, syntax OK')
except py_compile.PyCompileError as e:
    print(f'  FAIL: {e}')

print()
print('=== Done ===')
