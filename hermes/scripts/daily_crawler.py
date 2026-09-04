#!/usr/bin/env python3
"""
HERMES Intelligent Crawler v5.0
Integrated Horizon architecture
"""

import json, requests, re
from datetime import datetime
from pathlib import Path

HERMES_DIR = Path(__file__).parent.parent
CRAWL_DIR = HERMES_DIR / "crawl_data"
CRAWL_DIR.mkdir(exist_ok=True)

PROXIES = {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}
HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}

def fetch(url, params=None, json_fmt=False, timeout=20):
    try:
        r = requests.get(url, params=params, headers=HEADERS, 
                        proxies=PROXIES, timeout=timeout)
        if json_fmt:
            return r.json() if r.status_code == 200 else None
        return r.text if r.status_code == 200 else None
    except: pass
    return None

all_data = {}

# 1. GITHUB
print("[BB] GitHub...")
github = []
for q in ['hermes-agent stars:>50', 'autonomous agents language:Python stars:>100']:
    data = fetch('https://api.github.com/search/repositories',
                {'q': q, 'per_page': 10, 'sort': 'stars'}, json_fmt=True)
    if data:
        for item in data.get('items', []):
            name = item['full_name']
            if not any(p['name'] == name for p in github):
                github.append({'name': name, 'description': item['description'] or '',
                              'stars': item['stargazers_count'], 'url': item['html_url'],
                              'language': item['language'] or '', 'source': 'github'})
all_data['github'] = github[:30]
print("  GitHub: %d" % len(github))

# 2. REDDIT
print("[BB] Reddit...")
reddit = []
for sub in ['artificial', 'MachineLearning', 'singularity']:
    data = fetch('https://www.reddit.com/r/%s/hot.json' % sub, 
                {'limit': 5}, json_fmt=True)
    if data:
        for c in data.get('data', {}).get('children', []):
            d = c['data']
            if not d.get('stickied'):
                reddit.append({'title': d['title'],
                              'url': 'https://reddit.com' + d['permalink'],
                              'score': d['score'], 'subreddit': sub, 'source': 'reddit'})
all_data['reddit'] = reddit[:25]
print("  Reddit: %d" % len(reddit))

# 3. V2EX
print("[BB] V2EX...")
v2ex = []
latest = fetch('https://www.v2ex.com/api/topics/latest.json', json_fmt=True)
if latest:
    for t in latest[:20]:
        if t.get('title'):
            v2ex.append({'title': t['title'],
                        'node': t.get('node', {}).get('title', ''),
                        'url': 'https://www.v2ex.com/t/' + str(t.get('id', '')),
                        'replies': t.get('replies', 0), 'source': 'v2ex'})
all_data['v2ex'] = v2ex
print("  V2EX: %d" % len(v2ex))

# 4. TWITTER
print("[BB] Twitter/X...")
twitter = []
instances = ['nitter.net', 'nitter.it', 'nitter.pussthecat.org']
for inst in instances:
    try:
        for user in ['karpathy', 'ylecun']:
            rss = fetch('https://%s/%s/rss' % (inst, user), timeout=15)
            if rss and len(rss) > 500:
                items = re.findall(r'<item>(.*?)</item>', rss, re.DOTALL)
                for item in items[:3]:
                    title_m = re.search(r'<title>(.*?)</title>', item)
                    link_m = re.search(r'<link>(.*?)</link>', item)
                    if title_m and link_m and 'twitter.com' in link_m.group(1):
                        title = title_m.group(1)
                        if not any(t.get('url') == link_m.group(1) for t in twitter):
                            twitter.append({'title': title, 'url': link_m.group(1),
                                          'source': 'twitter', 'via': inst})
                if twitter: break
        if twitter: break
    except: pass
all_data['twitter'] = twitter
print("  Twitter: %d" % len(twitter))

# 5. HACKERNEWS
print("[BB] HackerNews...")
hn = []
for q in ['AI', 'machine learning', 'GPT']:
    data = fetch('https://hn.algolia.com/api/v1/search',
                {'query': q, 'hitsPerPage': 20}, json_fmt=True)
    if data:
        for h in data.get('hits', []):
            oid = h.get('objectID')
            if oid and not any(i.get('url', '').endswith(oid) for i in hn):
                hn.append({'title': h.get('title', ''),
                          'url': h.get('url', 'https://news.ycombinator.com/item?id=' + str(oid)),
                          'author': h.get('author', ''), 'score': h.get('points', 0),
                          'source': 'hackernews'})
all_data['hackernews'] = hn[:30]
print("  HackerNews: %d" % len(hn))

# SAVE
ts = datetime.now().strftime('%Y%m%d_%H%M%S')
out = CRAWL_DIR / ('raw_' + ts + '.json')
with open(out, 'w') as f:
    json.dump({
        'timestamp': datetime.now().isoformat(),
        'total': sum(len(v) for v in all_data.values()),
        'results': [dict([('source', s)] + list(i.items())) for s, items in all_data.items() for i in items],
        'status': {s: {'status': 'working' if items else 'no_data', 'items': len(items)} for s, items in all_data.items()}
    }, f, indent=2, ensure_ascii=False)

print("\\nSaved: %d total" % sum(len(v) for v in all_data.values()))
print("=" * 80)
