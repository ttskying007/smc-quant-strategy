#!/root/scraper_env/bin/python3
"""
Multi-Source Data Crawler v4.3 — 配置驱动 + 自适应精调
架构: 配置文件(topic_config_v2.json)驱动, 查询自带方向标签, 跑完自动出精调建议
"""
import json, requests, re, urllib.parse, time, os, asyncio, ssl, subprocess
from datetime import datetime
from pathlib import Path

HERMES_DIR = Path(__file__).parent.parent
CRAWL_DIR = HERMES_DIR / "crawl_data"
CONFIG_FILE = HERMES_DIR / "topic_config_v2.json"
CRAWL_DIR.mkdir(exist_ok=True)

PROXIES = {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}
NO_PROXY = {'http': '', 'https': ''}
HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/148.0.0.0 Safari/537.36'}

# ============================================================
# 多层重试机制
# ============================================================
MAX_GLOBAL_RETRIES = 0          # Layer 3: 整个爬虫重试 (disabled for cron)
MIN_ACCEPTABLE_ITEMS = 0        # 低于此值触发全局重试 (accept any result)
SOURCE_RETRY_CUTOFF = 0.5       # Layer 2: 源失败率 > 50% 触发源级重试

def retry_request(url, params=None, json_fmt=False, timeout=20, max_tries=3):
    """增强版请求重试: 先走代理, 失败后直连, 每次换策略"""
    strategies = [
        {'proxies': PROXIES, 'msg': 'proxy'},
        {'proxies': NO_PROXY, 'msg': 'direct'},
    ]
    for strat in strategies:
        for attempt in range(max_tries):
            try:
                r = requests.get(url, params=params, headers=HEADERS,
                                 proxies=strat['proxies'], timeout=timeout)
                if r.status_code == 200:
                    return r.json() if json_fmt else r.text
                time.sleep(1 + attempt)
            except Exception as e:
                if attempt == max_tries - 1:
                    break
                time.sleep(2)
    return None

def retry_urllib(url, headers=None, timeout=20, max_tries=3):
    """urllib 请求重试: 先直连, 后代理(用requests, 修复urllib ProxyHandler context兼容问题)"""
    hdrs = headers or HEADERS
    strategies = [
        {'proxy': None, 'use_requests': False, 'msg': 'direct'},
        {'proxy': PROXIES, 'use_requests': True, 'msg': 'via proxy'},
    ]
    ctx = ssl._create_unverified_context()
    for strat in strategies:
        for attempt in range(max_tries):
            try:
                if strat['use_requests']:
                    r = requests.get(url, headers=hdrs, proxies=strat['proxy'], timeout=timeout)
                    if r.status_code == 200:
                        return r.text
                else:
                    req = urllib.request.Request(url, headers=hdrs)
                    r = urllib.request.urlopen(req, context=ctx, timeout=timeout)
                    return r.read().decode("utf-8", errors="replace")
            except Exception as e:
                if attempt == max_tries - 1:
                    break
                time.sleep(2)
    return None

X_COOKIES_FILE = HERMES_DIR / "x_cookies_fresh_playwright.json"
X_DEFAULT_COOKIES = [
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


# ============================================================
# 加载配置
# ============================================================
def load_config():
    with open(CONFIG_FILE) as f:
        cfg = json.load(f)
    return cfg


def save_config(cfg):
    """写回配置（更新查询统计）"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ============================================================
# 验证引擎（verify/exclude）
# ============================================================
def verify_text(text, direction_cfg):
    """
    返回: ('precise', matched_word) | ('false', matched_exclude) | ('uncertain', None)
    """
    text_lower = text.lower()
    for ex in direction_cfg.get("exclude", []):
        if ex.lower() in text_lower:
            return ('false', ex)
    for vw in direction_cfg.get("verify", []):
        if vw.lower() in text_lower:
            return ('precise', vw)
    return ('uncertain', None)


# ============================================================
# 来源处理函数 — 每个返回 pre-tagged results
# ============================================================
def load_x_cookies():
    if X_COOKIES_FILE.exists():
        try:
            with open(X_COOKIES_FILE) as f:
                data = json.load(f)
            if isinstance(data, dict) and 'auth_token' in data:
                return [{"name": n, "value": v, "domain": ".x.com", "path": "/"} for n, v in data.items()]
        except:
            pass
    return X_DEFAULT_COOKIES


async def fetch_google_for_query(direction_id, query_obj, page, site_prefix=None):
    """Fetch Google Search results via Playwright. If site_prefix='site:reddit.com', gets Reddit results.
    带自动重试: 0结果时刷新页面重试。"""
    q = query_obj["q"]
    qid = query_obj["id"]
    src_label = "Reddit" if site_prefix else "Google"

    if site_prefix:
        search_q = f"{site_prefix} ({q})"
    else:
        search_q = q

    url = f'https://www.google.com/search?q={urllib.parse.quote(search_q)}&hl=en&num=10'

    for attempt in range(1):  # reduced from 3 — Google blocks automation
        results = []
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=15000)
            await asyncio.sleep(2)

            items = await page.evaluate("""(maxResults) => {
                const items = [];
                const seen = new Set();
                const containers = document.querySelectorAll('.g, .MjjYud');
                for (const c of containers) {
                    if (items.length >= maxResults) break;
                    const h3 = c.querySelector('h3');
                    const a = c.querySelector('a[href^="http"]');
                    if (!a || !h3) continue;
                    const href = a.href;
                    if (seen.has(href)) continue;
                    seen.add(href);
                    const snippet = c.querySelector('.VwiC3b, .lEBKkf, [data-sncf]');
                    items.push({
                        url: href,
                        title: h3.textContent || '',
                        snippet: snippet ? snippet.textContent.slice(0, 300) : '',
                    });
                }
                if (items.length === 0) {
                    document.querySelectorAll('a[href^="http"] > h3, a > h3').forEach(el => {
                        if (items.length >= maxResults) return;
                        const parent = el.closest('a');
                        if (!parent || seen.has(parent.href)) return;
                        seen.add(parent.href);
                        items.push({
                            url: parent.href,
                            title: el.textContent || '',
                            snippet: '',
                        });
                    });
                }
                return items;
            }""", 10)

            for item in items:
                title = item.get('title', '').strip()
                url_item = item.get('url', '').strip()
                snippet = item.get('snippet', '').strip()
                if not title or not url_item:
                    continue
                combined = f"{title} {snippet}"
                results.append({
                    'direction': direction_id,
                    'query_id': qid,
                    'query': q[:30],
                    'source': 'reddit' if site_prefix else 'google',
                    'title': title,
                    'description': snippet,
                    'url': url_item,
                    '_text_for_verify': combined,
                })

            if results:
                print(f"    {src_label}/{direction_id} '{qid}': {len(results)} results")
                return results, {'hits': len(results), 'precise': 0, 'false': 0}

            print(f"    {src_label}/{direction_id} '{qid}': 0 results, retrying... (attempt {attempt+1})")
            await asyncio.sleep(5 * (attempt + 1))

        except Exception as e:
            err = str(e)[:40]
            if attempt < 2:
                print(f"    {src_label}/{direction_id} '{qid}': {err}, retrying... (attempt {attempt+1})")
                await asyncio.sleep(5 * (attempt + 1))
            else:
                print(f"    {src_label}/{direction_id} '{qid}': {err} (failed after 3 attempts)")
                return results, {'hits': 0, 'precise': 0, 'false': 0}

    print(f"    {src_label}/{direction_id} '{qid}': 0 results (failed after 3 attempts)")
    return results, {'hits': 0, 'precise': 0, 'false': 0}


async def fetch_reddit_for_query(direction_id, query_obj, page):
    """Fetch Reddit results via Google site:reddit.com search."""
    return await fetch_google_for_query(direction_id, query_obj, page, site_prefix='site:reddit.com')


async def fetch_x_for_query(direction_id, query_obj, page):
    """在同一个page中执行一个X查询（复用页面）"""
    q = query_obj["q"]
    qid = query_obj["id"]
    max_per = 10
    results = []

    try:
        encoded_q = urllib.parse.quote(q)
        search_url = f'https://x.com/search?q={encoded_q}&src=typed_query&f=live'
        await page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)

        if 'login' in page.url.lower():
            print(f"    X/{direction_id} '{qid}': login redirect")
            return results, {'hits': 0, 'precise': 0, 'false': 0}

        for _ in range(3):
            await page.evaluate('window.scrollBy(0, 800)')
            await asyncio.sleep(1)

        tweets = await page.evaluate(f'''(max) => {{
            const articles = document.querySelectorAll('article[data-testid="tweet"]');
            const results = [];
            for (const a of articles) {{
                if (results.length >= max) break;
                const textEl = a.querySelector('[data-testid="tweetText"]');
                const timeEl = a.querySelector('time');
                const userLinks = a.querySelectorAll('[data-testid="User-Name"] a');
                let screenName = '', displayName = '';
                for (const link of userLinks) {{
                    const href = link.getAttribute('href') || '';
                    if (href.startsWith('/') && !href.includes('/status/')) {{
                        screenName = href.replace('/', '');
                        displayName = link.textContent || '';
                    }}
                }}
                const linkEl = a.querySelector('a[href*="/status/"]');
                const tweetUrl = linkEl ? 'https://x.com' + linkEl.getAttribute('href') : '';
                const tweetId = tweetUrl ? tweetUrl.split('/status/')[1]?.split('?')[0] : '';
                results.push({{
                    id: tweetId, url: tweetUrl,
                    screen_name: screenName, display_name: displayName,
                    text: textEl ? textEl.textContent?.substring(0, 400) : '',
                    timestamp: timeEl ? timeEl.getAttribute('datetime') : '',
                }});
            }}
            return results;
        }}''', max_per)

        for t in tweets:
            if t.get('text'):
                results.append({
                    'direction': direction_id,
                    'query_id': qid,
                    'query': q[:30],
                    'source': 'x_twitter',
                    'text': t['text'],
                    'author': t.get('screen_name', ''),
                    'author_name': t.get('display_name', ''),
                    'url': t.get('url', ''),
                    'created_at': t.get('timestamp', ''),
                })

        print(f"    X/{direction_id} '{qid}': {len(tweets)} tweets")
        return results, {'hits': len(tweets), 'precise': 0, 'false': 0}

    except Exception as e:
        print(f"    X/{direction_id} '{qid}': error {str(e)[:40]}")
        return results, {'hits': 0, 'precise': 0, 'false': 0}


def fetch_bing_for_query(direction_id, query_obj):
    q = query_obj["q"]
    qid = query_obj["id"]
    results = []

    try:
        r = requests.get(f'https://www.bing.com/search?q={urllib.parse.quote(q)}&count=10',
                         headers=HEADERS, proxies=PROXIES, timeout=10)
        if r.status_code != 200:
            print(f"    Bing/{direction_id} '{qid}': HTTP {r.status_code}")
            return results, {'hits': 0, 'precise': 0, 'false': 0}

        count = 0
        for m in re.finditer(
            r'<h2 class="">.*?<a[^>]*?href="(https?://[^"]+)"[^>]*?>(.*?)</a>.*?<p class="b_lineclamp2">(.*?)</p>',
            r.text, re.DOTALL):
            if count >= 10:
                break
            url = m.group(1).split('?')[0] if '?' in m.group(1) else m.group(1)
            title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            desc = re.sub(r'<[^>]+>', '', m.group(3)).strip()[:200]
            combined = f"{title} {desc}"
            results.append({
                'direction': direction_id,
                'query_id': qid,
                'query': q[:25],
                'source': 'bing',
                'title': title,
                'description': desc,
                'url': url,
                '_text_for_verify': combined,
            })
            count += 1

        print(f"    Bing/{direction_id} '{qid}': {count} results")
        return results, {'hits': count, 'precise': 0, 'false': 0}

    except Exception as e:
        print(f"    Bing/{direction_id} '{qid}': error {str(e)[:40]}")
        return results, {'hits': 0, 'precise': 0, 'false': 0}


def fetch_github_for_query(direction_id, query_obj):
    q = query_obj["q"]
    qid = query_obj["id"]
    results = []

    try:
        data = fetch_url('https://api.github.com/search/repositories',
                         {'q': q, 'per_page': 10, 'sort': 'stars'}, json_fmt=True)
        if not data or 'items' not in data:
            print(f"    GitHub/{direction_id} '{qid}': no data")
            return results, {'hits': 0, 'precise': 0, 'false': 0}

        count = 0
        for item in data['items']:
            name = item['full_name']
            desc = (item.get('description') or '')[:300]
            combined = f"{name} {desc}"
            results.append({
                'direction': direction_id,
                'query_id': qid,
                'query': q[:30],
                'source': 'github',
                'name': name,
                'description': desc,
                'stars': item.get('stargazers_count', 0),
                'language': item.get('language') or '',
                'url': item.get('html_url', ''),
                '_text_for_verify': combined,
            })
            count += 1

        print(f"    GitHub/{direction_id} '{qid}': {count} repos")
        return results, {'hits': count, 'precise': 0, 'false': 0}

    except Exception as e:
        print(f"    GitHub/{direction_id} '{qid}': error {str(e)[:40]}")
        return results, {'hits': 0, 'precise': 0, 'false': 0}


def fetch_hn_for_query(direction_id, query_obj):
    q = query_obj["q"]
    qid = query_obj["id"]
    results = []

    try:
        data = fetch_url('https://hn.algolia.com/api/v1/search',
                         {'query': q, 'hitsPerPage': 20}, json_fmt=True)
        if not data or 'hits' not in data:
            print(f"    HN/{direction_id} '{qid}': no data")
            return results, {'hits': 0, 'precise': 0, 'false': 0}

        count = 0
        for h in data['hits']:
            title = h.get('title', '')
            url = h.get('url', '') or f"https://news.ycombinator.com/item?id={h.get('objectID', '')}"
            combined = title + " " + (h.get('story_text', '') or '')[:200]
            results.append({
                'direction': direction_id,
                'query_id': qid,
                'query': q[:30],
                'source': 'hackernews',
                'title': title,
                'url': url,
                'author': h.get('author', ''),
                'points': h.get('points', 0),
                '_text_for_verify': combined,
            })
            count += 1

        print(f"    HN/{direction_id} '{qid}': {count} items")
        return results, {'hits': count, 'precise': 0, 'false': 0}

    except Exception as e:
        print(f"    HN/{direction_id} '{qid}': error {str(e)[:40]}")
        return results, {'hits': 0, 'precise': 0, 'false': 0}


def fetch_brave_for_query(direction_id, query_obj):
    """Fetch Brave Search results (stands in for Google). Reddit content appears naturally in results."""
    q = query_obj["q"]
    qid = query_obj["id"]
    results = []
    ua = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/148.0.0.0 Safari/537.36'

    try:
        html = retry_urllib(
            f'https://search.brave.com/search?q={urllib.parse.quote(q)}&source=web',
            headers={"User-Agent": ua}, timeout=20, max_tries=3)

        all_links = re.findall(r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL)
        external = [(u, t.strip()) for u, t in all_links
                    if u.startswith('http')
                    and 'brave.com' not in u
                    and 'search.brave' not in u
                    and 'google-analytics' not in u
                    and 'googlesyndication' not in u]

        count = 0
        seen = set()
        for url_text, title_text in external:
            if count >= 10:
                break
            clean_url = url_text.split('?')[0].split('#')[0]
            if clean_url in seen:
                continue
            seen.add(clean_url)
            title_clean = re.sub(r'<[^>]+>', '', title_text).strip()
            title_clean = re.sub(r'\s+', ' ', title_clean)
            if title_clean and len(title_clean) > 5:
                results.append({
                    'direction': direction_id,
                    'query_id': qid,
                    'query': q[:30],
                    'source': 'brave',
                    'title': title_clean,
                    'url': clean_url,
                    '_text_for_verify': title_clean,
                })
                count += 1

        print(f"    Brave/{direction_id} '{qid}': {count} results")
        return results, {'hits': count, 'precise': 0, 'false': 0}
    except Exception as e:
        print(f"    Brave/{direction_id} '{qid}': error {str(e)[:40]}")
        return results, {'hits': 0, 'precise': 0, 'false': 0}


def fetch_google_news_for_query(direction_id, query_obj):
    """Fetch Google News RSS (English query only, returns 60-100+ items per query)."""
    q = query_obj["q"]
    qid = query_obj["id"]
    results = []
    ua = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'

    try:
        rss_url = f'https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl=en-US&gl=US&ceid=US:en'
        data = retry_urllib(rss_url, headers={"User-Agent": ua}, timeout=15, max_tries=3)

        titles = re.findall(r'<title>(.*?)</title>', data)
        links = re.findall(r'<link>([^<]+)</link>', data)
        sources = re.findall(r'<source[^>]*?>(.*?)</source>', data)

        count = 0
        # titles[0] is feed title, skip it; links[0] is feed link
        for i in range(1, min(len(titles), len(links))):
            if count >= 10:
                break
            t = titles[i].strip()
            l = links[i].strip()
            src = sources[i - 1].strip() if (i - 1) < len(sources) else ''
            combined = f"{t} {src}"
            results.append({
                'direction': direction_id,
                'query_id': qid,
                'query': q[:30],
                'source': 'google_news_rss',
                'title': t,
                'url': l,
                'source_site': src,
                '_text_for_verify': combined,
            })
            count += 1

        print(f"    GNews/{direction_id} '{qid}': {count} items")
        return results, {'hits': count, 'precise': 0, 'false': 0}
    except Exception as e:
        print(f"    GNews/{direction_id} '{qid}': error {str(e)[:40]}")
        return results, {'hits': 0, 'precise': 0, 'false': 0}


# ============================================================
# 通用HTTP请求
# ============================================================
def fetch_url(url, params=None, json_fmt=False, timeout=20, use_proxy=True):
    """通用HTTP请求: 3次重试 + proxy/direct fallback。"""

    # Read current proxy status
    retry = retry_request(url, params=params, json_fmt=json_fmt, timeout=timeout, max_tries=3)
    if retry is not None:
        return retry
    
    # Fallback: no proxy
    if use_proxy:
        try:
            r = requests.get(url, params=params, headers=HEADERS, proxies=NO_PROXY, timeout=timeout)
            if r.status_code == 200:
                return r.json() if json_fmt else r.text
        except:
            pass
    
    return None


# ============================================================
# NewsNow — 全源热帖聚合 (Playwright)
# ============================================================
async def fetch_newsnow(page, direction_id, query_obj):
    """抓取 newsnow.busiyi.world 全部源的热帖。带自动重试。"""
    qid = query_obj["id"]
    results = []
    
    for attempt in range(1):  # reduced retries
        try:
            await page.goto('https://newsnow.busiyi.world/', wait_until='domcontentloaded', timeout=15000)
            await asyncio.sleep(2)
            
            # 滚动到底部触发懒加载
            for _ in range(5):
                await page.evaluate('window.scrollBy(0, 2000)')
                await asyncio.sleep(0.5)
            
            # 提取所有 li a 元素
            items = await page.evaluate('''() => {
                const items = [];
                const seen = new Set();
                const links = document.querySelectorAll('li a[href]');
                
                for (const a of links) {
                    const href = a.getAttribute('href') || '';
                    const text = a.textContent ? a.textContent.trim() : '';
                    if (!text || text.length < 5 || seen.has(href)) continue;
                    seen.add(href);
                    
                    let source = '';
                    try {
                        const url = new URL(href);
                        source = url.hostname.replace('www.', '');
                    } catch(e) {
                        source = 'unknown';
                    }
                    
                    let title = text;
                    title = title.replace(/^\\\\d+/, '').trim();
                    
                    items.push({
                        url: href,
                        title: text.substring(0, 200),
                        source: source,
                    });
                }
                return items;
            }''')
            
            for item in items:
                url = item.get('url', '')
                title = item.get('title', '')
                src_domain = item.get('source', '')
                
                if not title or not url:
                    continue
                
                combined = title
                assigned_direction = direction_id
                
                results.append({
                    'direction': assigned_direction,
                    'query_id': qid,
                    'query': 'newsnow',
                    'source': f'newsnow:{src_domain}',
                    'title': title,
                    'url': url,
                    'domain': src_domain,
                    '_text_for_verify': combined,
                })
            
            # 如果成功获取到内容，返回结果（不再重试）
            if results:
                print(f"    NewsNow/{direction_id} '{qid}': {len(results)} items from {len(set(i['domain'] for i in results))} domains (attempt {attempt+1})")
                return results, {'hits': len(results), 'precise': 0, 'false': 0}
            
            print(f"    NewsNow/{direction_id} '{qid}': 0 items, retrying... (attempt {attempt+1})")
            await asyncio.sleep(3 * (attempt + 1))
            
        except Exception as e:
            err_msg = str(e)[:60]
            if attempt < 2:
                print(f"    NewsNow/{direction_id} '{qid}': {err_msg}, retrying... (attempt {attempt+1})")
                await asyncio.sleep(5 * (attempt + 1))
            else:
                print(f"    NewsNow/{direction_id} '{qid}': {err_msg} (failed after 3 attempts)")
    
    return results, {'hits': len(results), 'precise': 0, 'false': 0}


# ============================================================
# 精调建议引擎
# ============================================================
# ============================================================
# last30days 集成 — 调用外部研究引擎
# ============================================================
LAST30DAYS_SCRIPT = "/root/last30days-skill/skills/last30days/scripts/last30days.py"
LAST30DAYS_ENGINE = "/root/scraper_env/bin/python3"

# last30days: only run for broad-enough directions that might hit HN/Reddit
# niche topics (SMC forex, A-stock quant, fortune) skip to save ~55s per run
L30D_ENABLED_DIRS = {
    "programming", "general-ai", "best-models",
    "ai-video", "skills", "free-api", "management",
}

# Load ScrapeCreators API key for Reddit access via last30days
def ensure_l30d_env():
    """Load SCRAPECREATORS_API_KEY from env file if not already set."""
    if os.environ.get("SCRAPECREATORS_API_KEY"):
        return
    env_file = Path(__file__).parent / "l30d_env.sh"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if line.startswith("export SCRAPECREATORS"):
                    key = line.strip().split("=", 1)[1]
                    os.environ["SCRAPECREATORS_API_KEY"] = key
                    break

def fetch_via_last30days(direction_id, query_obj):
    """调用 last30days 引擎研究一个话题，返回 crawler 格式的 items.
    带自动重试 (首次失败重试一次)。"""
    topic = query_obj["q"]
    qid = query_obj["id"]
    search = query_obj.get("search", "hackernews,polymarket")
    
    for attempt in range(2):
        try:
            cmd = [
                LAST30DAYS_ENGINE, LAST30DAYS_SCRIPT,
                topic, "--emit=json", f"--search={search}", "--quick",
            ]
            env = os.environ.copy()
            env['http_proxy'] = 'http://127.0.0.1:7890'
            env['https_proxy'] = 'http://127.0.0.1:7890'
            
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
                cwd=os.path.dirname(os.path.dirname(LAST30DAYS_SCRIPT)),
                env=env,
            )
            
            if result.returncode != 0:
                if attempt == 0:
                    print(f"    last30days/{direction_id} '{qid}': exit {result.returncode}, retrying...")
                    time.sleep(3)
                    continue
                print(f"    last30days/{direction_id} '{qid}': exit {result.returncode}")
                return [], {'hits': 0, 'precise': 0, 'false': 0}
            
            data = json.loads(result.stdout)
            items = []
            for src, src_items in data.get("items_by_source", {}).items():
                src_map = {"hackernews": "l30d_hn", "polymarket": "l30d_polymarket", "reddit": "l30d_reddit"}
                mapped_src = src_map.get(src, f"l30d_{src}")
                
                for item in src_items:
                    text = item.get("body") or item.get("snippet") or item.get("title", "")
                    items.append({
                        'direction': direction_id,
                        'query_id': qid,
                        'query': topic[:30],
                        'source': mapped_src,
                        'title': item.get("title", ""),
                        'text': text,
                        'url': item.get("url", ""),
                        'author': item.get("author", ""),
                        'created_at': item.get("published_at", ""),
                        'engagement': item.get("engagement", {}).get("comments", 0),
                        '_last30days': True,
                    })
            
            total = len(items)
            print(f"    last30days/{direction_id} '{qid}': {total} items ({', '.join([f'{s}:{len(v)}' for s,v in data.get('items_by_source',{}).items()])})")
            return items, {'hits': total, 'precise': 0, 'false': 0}
            
        except subprocess.TimeoutExpired:
            if attempt == 0:
                print(f"    last30days/{direction_id} '{qid}': timeout (120s), retrying...")
                time.sleep(5)
                continue
            print(f"    last30days/{direction_id} '{qid}': timeout (120s)")
            return [], {'hits': 0, 'precise': 0, 'false': 0}
        except json.JSONDecodeError as e:
            if attempt == 0:
                print(f"    last30days/{direction_id} '{qid}': JSON error {str(e)[:40]}, retrying...")
                time.sleep(3)
                continue
            print(f"    last30days/{direction_id} '{qid}': JSON error {str(e)[:40]}")
            return [], {'hits': 0, 'precise': 0, 'false': 0}
        except Exception as e:
            if attempt == 0:
                print(f"    last30days/{direction_id} '{qid}': error {str(e)[:60]}, retrying...")
                time.sleep(3)
                continue
            print(f"    last30days/{direction_id} '{qid}': error {str(e)[:60]}")
            return [], {'hits': 0, 'precise': 0, 'false': 0}
    
    return [], {'hits': 0, 'precise': 0, 'false': 0}


def fetch_via_hn_algolia(direction_id, query_obj):
    """Fetch Hacker News stories via Algolia API. Free, no API key needed, works from GFW."""
    topic = query_obj["q"]
    qid = query_obj["id"]
    
    params = {
        "query": topic,
        "tags": "story",
        "numericFilters": "points>2",
        "hitsPerPage": "15",
    }
    from urllib.parse import urlencode
    url = f"https://hn.algolia.com/api/v1/search?{urlencode(params)}"
    
    try:
        resp = retry_request(url, timeout=30)
        if not resp:
            print(f"    hn/{direction_id} '{qid}': no response after retries")
            return [], {'hits': 0, 'precise': 0, 'false': 0}
        data = json.loads(resp) if isinstance(resp, str) else resp
        hits = data.get("hits", [])
        items = []
        for hit in hits:
            items.append({
                'direction': direction_id,
                'query_id': qid,
                'query': topic[:30],
                'source': 'hn_algolia',
                'title': hit.get("title", ""),
                'text': hit.get("title", ""),
                'url': hit.get("url", "") or f"https://news.ycombinator.com/item?id={hit.get('objectID','')}",
                'author': hit.get("author", ""),
                'created_at': hit.get("created_at", ""),
                'engagement': hit.get("points", 0),
            })
        print(f"    hn/{direction_id} '{qid}': {len(items)} stories")
        return items, {'hits': len(items), 'precise': 0, 'false': 0}
    except Exception as e:
        print(f"    hn/{direction_id} '{qid}': error {str(e)[:60]}")
        return [], {'hits': 0, 'precise': 0, 'false': 0}


def analyze_query(query_id, direction_cfg, stats):
    """返回建议文本字符串"""
    qname = query_id
    hits = stats['hits']
    precise = stats['precise']
    false_count = stats['false']
    uncertain = hits - precise - false_count

    lines = []

    if hits == 0:
        lines.append(f"    [{qname}] 零命中")
        lines.append(f"      建议A: 换词（当前词无结果）")
        lines.append(f"      建议B: 放宽条件（加同义词）")
        return '\n'.join(lines)

    precision_rate = precise / hits if hits > 0 else 0

    lines.append(f"    [{qname}] {hits}条 | 精准{precise}/{precision_rate:.0%} | 误报{false_count} | 未确认{uncertain}")

    if precision_rate < 0.5:
        lines.append(f"      误报率高({precision_rate:.0%}) → 建议加exclude词")
    elif precision_rate < 0.7:
        lines.append(f"      精度一般({precision_rate:.0%}) → 可加verify词收窄")
    elif precision_rate > 0.9 and hits < 5:
        lines.append(f"      精度高但量少({precision_rate:.0%}, {hits}条) → 可放宽查询扩大召回")
    elif precision_rate > 0.9:
        lines.append(f"      精度高({precision_rate:.0%}) → 维持")

    if false_count > 0:
        lines.append(f"      误报{false_count}条 → 当前exclude: {direction_cfg.get('exclude',[])}")
        if false_count >= 3:
            lines.append(f"      建议: 加更多exclude词过滤")

    return '\n'.join(lines)


# ============================================================
# Main
# ============================================================
async def run_crawl_once():
    """执行单次爬取，返回 total_items。异常时返回负数。"""
    cfg = load_config()
    all_results = []
    direction_stats = {}
    query_stats_all = {}

    ascore = 0
    bscore = 0
    cscore = 0

    # 对每个方向，对每个有查询的源，执行查询
    print("\n\n[按源收集]")
    print(f"Playwright sources: X, Google, Reddit | Sync sources: Bing, GitHub, HN, Brave, GNews")

    # === 按源收集（所有非Playwright源用同步） ===
    non_x_sources = {}

    for dir_id, dcfg in cfg["directions"].items():
        for src in ["bing", "github", "hn", "brave", "google_news_rss"]:
            if src in dcfg.get("queries", {}):
                for qobj in dcfg["queries"][src]:
                    non_x_sources.setdefault(src, []).append((dir_id, dcfg, qobj))

    # === Playwright Sources (X, Google, Reddit) — 共享一个browser ===
    pw_queries = {"x": [], "google": [], "reddit": []}
    for dir_id, dcfg in cfg["directions"].items():
        for src in ["x", "google", "reddit"]:
            if src in dcfg.get("queries", {}):
                for qobj in dcfg["queries"][src]:
                    pw_queries.setdefault(src, []).append((dir_id, dcfg, qobj))

    if any(pw_queries.values()):
        sources_done = 0
        print(f"[1/10] X, Google, Reddit (via Playwright)...")
        from playwright.async_api import async_playwright

        cookies = load_x_cookies()
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    proxy={"server": "http://127.0.0.1:7890"},
                    args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
                )
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/148.0.0.0 Safari/537.36',
                    viewport={'width': 1280, 'height': 720},
                    locale='en',
                )
                await context.add_cookies(cookies)

                # === Process X queries ===
                if pw_queries["x"]:
                    print(f"  [X] {len(pw_queries['x'])} queries...")
                    x_total = 0
                    page_x = await context.new_page()
                    try:
                        await page_x.goto('https://x.com/home', wait_until='domcontentloaded', timeout=30000)
                        await asyncio.sleep(2)
                        title = await page_x.title()
                        print(f"    Session: {'OK' if title else 'loaded'} ({title[:30]})" if title else "    Session: OK")
                    except Exception as e:
                        print(f"    Session error: {str(e)[:50]}")

                    for dir_id, dcfg, qobj in pw_queries["x"]:
                        results, stats = await fetch_x_for_query(dir_id, qobj, page_x)
                        for r in results:
                            all_results.append(r)
                        direction_stats.setdefault(dir_id, {"name": dcfg["name"], "weight": dcfg["weight"],
                                                             "hits": 0, "precise": 0, "false": 0})
                        direction_stats[dir_id]["hits"] += stats["hits"]
                        x_total += stats["hits"]
                        qkey = f"x:{qobj['id']}"
                        query_stats_all[qkey] = {"hits": stats["hits"], "precise": stats["precise"],
                                                  "false": stats["false"]}
                    await page_x.close()
                    print(f"    X total: {x_total} tweets")
                    sources_done += 1

                # === Process Google queries ===
                if pw_queries["google"]:
                    print(f"  [Google] {len(pw_queries['google'])} queries...")
                    gw_total = 0
                    page_g = await context.new_page()
                    for dir_id, dcfg, qobj in pw_queries["google"]:
                        results, stats = await fetch_google_for_query(dir_id, qobj, page_g)
                        for r in results:
                            all_results.append(r)
                        direction_stats.setdefault(dir_id, {"name": dcfg["name"], "weight": dcfg["weight"],
                                                             "hits": 0, "precise": 0, "false": 0})
                        direction_stats[dir_id]["hits"] += stats["hits"]
                        gw_total += stats["hits"]
                        qkey = f"google:{qobj['id']}"
                        query_stats_all[qkey] = {"hits": stats["hits"], "precise": stats["precise"],
                                                  "false": stats["false"]}
                    await page_g.close()
                    print(f"    Google total: {gw_total} items")
                    sources_done += 1

                # === Process Reddit queries (Google site:reddit.com) ===
                if pw_queries["reddit"]:
                    print(f"  [Reddit via Google] {len(pw_queries['reddit'])} queries...")
                    rd_total = 0
                    page_r = await context.new_page()
                    for dir_id, dcfg, qobj in pw_queries["reddit"]:
                        results, stats = await fetch_reddit_for_query(dir_id, qobj, page_r)
                        for r in results:
                            all_results.append(r)
                        direction_stats.setdefault(dir_id, {"name": dcfg["name"], "weight": dcfg["weight"],
                                                             "hits": 0, "precise": 0, "false": 0})
                        direction_stats[dir_id]["hits"] += stats["hits"]
                        rd_total += stats["hits"]
                        qkey = f"reddit:{qobj['id']}"
                        query_stats_all[qkey] = {"hits": stats["hits"], "precise": stats["precise"],
                                                  "false": stats["false"]}
                    await page_r.close()
                    print(f"    Reddit total: {rd_total} items")
                    sources_done += 1

                await context.close()
                await browser.close()
        except Exception as e:
            print(f"  X error: {str(e)[:60]}")

    # === Bing ===
    if "bing" in non_x_sources:
        print(f"[2/10] Bing Search...")
        bing_total = 0
        for dir_id, dcfg, qobj in non_x_sources["bing"]:
            results, stats = fetch_bing_for_query(dir_id, qobj)
            for r in results:
                all_results.append(r)
            direction_stats.setdefault(dir_id, {"name": dcfg["name"], "weight": dcfg["weight"],
                                                 "hits": 0, "precise": 0, "false": 0})
            direction_stats[dir_id]["hits"] += stats["hits"]
            direction_stats[dir_id]["_hits_bing"] = direction_stats[dir_id].get("_hits_bing", 0) + stats["hits"]
            bing_total += stats["hits"]

            qkey = f"bing:{qobj['id']}"
            query_stats_all[qkey] = {"hits": stats["hits"], "precise": stats["precise"],
                                      "false": stats["false"]}
        print(f"  Bing total: {bing_total} items")

    # === GitHub ===
    if "github" in non_x_sources:
        print(f"[3/10] GitHub...")
        gh_total = 0
        seen_names = set()
        for dir_id, dcfg, qobj in non_x_sources["github"]:
            results, stats = fetch_github_for_query(dir_id, qobj)
            # Dedup by name
            deduped = []
            for r in results:
                nm = r.get('name', '')
                if nm not in seen_names:
                    seen_names.add(nm)
                    deduped.append(r)
            for r in deduped:
                all_results.append(r)
            direction_stats.setdefault(dir_id, {"name": dcfg["name"], "weight": dcfg["weight"],
                                                 "hits": 0, "precise": 0, "false": 0})
            direction_stats[dir_id]["hits"] += len(deduped)
            gh_total += len(deduped)

            qkey = f"github:{qobj['id']}"
            query_stats_all[qkey] = {"hits": len(deduped), "precise": stats.get("precise", 0),
                                      "false": stats.get("false", 0)}
        print(f"  GitHub total: {gh_total} repos")

    # === HN ===
    if "hn" in non_x_sources:
        print(f"[4/10] HackerNews...")
        hn_total = 0
        seen_titles = set()
        for dir_id, dcfg, qobj in non_x_sources["hn"]:
            results, stats = fetch_hn_for_query(dir_id, qobj)
            deduped = []
            for r in results:
                t = r.get('title', '')
                if t and t not in seen_titles:
                    seen_titles.add(t)
                    deduped.append(r)
            for r in deduped:
                all_results.append(r)
            direction_stats.setdefault(dir_id, {"name": dcfg["name"], "weight": dcfg["weight"],
                                                 "hits": 0, "precise": 0, "false": 0})
            direction_stats[dir_id]["hits"] += len(deduped)
            hn_total += len(deduped)

            qkey = f"hn:{qobj['id']}"
            query_stats_all[qkey] = {"hits": len(deduped), "precise": stats.get("precise", 0),
                                      "false": stats.get("false", 0)}
        print(f"  HN total: {hn_total} items")

    # === Brave Search (Google + Reddit replacement) ===
    if "brave" in non_x_sources:
        print(f"\n[5/10] Brave Search...")
        br_total = 0
        seen_urls = set()
        for dir_id, dcfg, qobj in non_x_sources["brave"]:
            results, stats = fetch_brave_for_query(dir_id, qobj)
            deduped = []
            for r in results:
                u = r.get('url', '')
                if u and u not in seen_urls:
                    seen_urls.add(u)
                    deduped.append(r)
            for r in deduped:
                all_results.append(r)
            direction_stats.setdefault(dir_id, {"name": dcfg["name"], "weight": dcfg["weight"],
                                                 "hits": 0, "precise": 0, "false": 0})
            direction_stats[dir_id]["hits"] += len(deduped)
            br_total += len(deduped)

            qkey = f"brave:{qobj['id']}"
            query_stats_all[qkey] = {"hits": len(deduped), "precise": stats.get("precise", 0),
                                      "false": stats.get("false", 0)}
        print(f"  Brave total: {br_total} items")

    # === Google News RSS ===
    if "google_news_rss" in non_x_sources:
        print(f"\n[6/10] Google News RSS...")
        gn_total = 0
        seen_urls_gn = set()
        for dir_id, dcfg, qobj in non_x_sources["google_news_rss"]:
            results, stats = fetch_google_news_for_query(dir_id, qobj)
            deduped = []
            for r in results:
                u = r.get('url', '')
                if u and u not in seen_urls_gn:
                    seen_urls_gn.add(u)
                    deduped.append(r)
            for r in deduped:
                all_results.append(r)
            direction_stats.setdefault(dir_id, {"name": dcfg["name"], "weight": dcfg["weight"],
                                                 "hits": 0, "precise": 0, "false": 0})
            direction_stats[dir_id]["hits"] += len(deduped)
            gn_total += len(deduped)

            qkey = f"google_news_rss:{qobj['id']}"
            query_stats_all[qkey] = {"hits": len(deduped), "precise": stats.get("precise", 0),
                                      "false": stats.get("false", 0)}
        print(f"  GNews total: {gn_total} items")

    # === NewsNow (uses Playwright — need browser context) ===
    newsnow_queries = []
    for dir_id, dcfg in cfg["directions"].items():
        if "newsnow" in dcfg.get("queries", {}):
            for qobj in dcfg["queries"]["newsnow"]:
                newsnow_queries.append((dir_id, dcfg, qobj))
    
    if newsnow_queries:
        print(f"\n[7/10] NewsNow (44 sources via Playwright)...")
        nn_total = 0
        seen_urls_nn = set()
        
        # Launch fresh browser for NewsNow
        from playwright.async_api import async_playwright
        async with async_playwright() as nn_p:
            cookies = load_x_cookies()
            nn_browser = await nn_p.chromium.launch(
                headless=True,
                proxy={"server": "http://127.0.0.1:7890"},
                args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
            )
            nn_ctx = await nn_browser.new_context(
                user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/148.0.0.0 Safari/537.36',
                viewport={'width': 1280, 'height': 720},
            )
            nn_page = await nn_ctx.new_page()
            
            try:
                for dir_id, dcfg, qobj in newsnow_queries:
                    results, stats = await fetch_newsnow(nn_page, dir_id, qobj)
                    deduped = []
                    for r in results:
                        u = r.get('url', '')
                        if u and u not in seen_urls_nn:
                            seen_urls_nn.add(u)
                            deduped.append(r)
                    for r in deduped:
                        all_results.append(r)
                    direction_stats.setdefault(dir_id, {"name": dcfg["name"], "weight": dcfg["weight"],
                                                         "hits": 0, "precise": 0, "false": 0})
                    direction_stats[dir_id]["hits"] += len(deduped)
                    nn_total += len(deduped)
    
                    qkey = f"newsnow:{qobj['id']}"
                    query_stats_all[qkey] = {"hits": len(deduped), "precise": stats.get("precise", 0),
                                              "false": stats.get("false", 0)}
                print(f"  NewsNow total: {nn_total} items (deduped)")
            except Exception as e:
                print(f"  NewsNow error: {str(e)[:60]}")

    # === HN Algolia 直接搜索 (替代 last30days — SC key 已过期, HTTP 402) ===
    hn_queries = []
    for dir_id, dcfg in cfg["directions"].items():
        if "hn" in dcfg.get("queries", {}):
            for qobj in dcfg["queries"]["hn"]:
                hn_queries.append((dir_id, dcfg, qobj))
    if hn_queries:
        print(f"\n[8/10] HN Algolia Direct API...")
        hn_total = 0
        seen_urls_hn = set()
        for dir_id, dcfg, qobj in hn_queries:
            results, stats = fetch_via_hn_algolia(dir_id, qobj)
            for r in results:
                u = r.get('url', '')
                if u and u not in seen_urls_hn:
                    seen_urls_hn.add(u)
                    all_results.append(r)
            direction_stats.setdefault(dir_id, {"name": dcfg["name"], "weight": dcfg["weight"],
                                                 "hits": 0, "precise": 0, "false": 0})
            direction_stats[dir_id]["hits"] += len(results)
            hn_total += len(results)
            qkey = f"hn_direct:{qobj['id']}"
            query_stats_all[qkey] = {"hits": len(results), "precise": stats.get("precise", 0),
                                      "false": stats.get("false", 0)}
        print(f"  HN Algolia total: {hn_total} items")

    # ============================================================
    # 验证阶段：对每条结果跑 verify/exclude
    # ============================================================
    print("\n%s" % ("=" * 80))
    print("=== 验证 & 统计 ===")
    verified_total = 0

    # 重置方向统计（用验证后的值覆盖）
    for dir_id, dcfg in cfg["directions"].items():
        direction_stats[dir_id] = {"name": dcfg["name"], "weight": dcfg["weight"],
                                    "hits": 0, "precise": 0, "false": 0}

    for item in all_results:
        dir_id = item['direction']
        dcfg = cfg["directions"].get(dir_id, {})
        text = item.get('_text_for_verify', '') or item.get('text', '') or item.get('title', '') or item.get('name', '') or ''
        verdict, matched = verify_text(text, dcfg)

        item['_verify'] = verdict
        item['_verify_match'] = matched

        ds = direction_stats.setdefault(dir_id, {"name": dcfg.get("name", dir_id), "weight": dcfg.get("weight", 1.0),
                                                   "hits": 0, "precise": 0, "false": 0})
        ds["hits"] += 1
        if verdict == 'precise':
            ds["precise"] += 1
        elif verdict == 'false':
            ds["false"] += 1

        # 也更新查询级别的验证统计
        qkey = f"{item['source'].replace('x_twitter','x').replace('hackernews','hn')}:{item['query_id']}"
        if qkey in query_stats_all:
            if verdict == 'precise':
                query_stats_all[qkey]["precise"] += 1
            elif verdict == 'false':
                query_stats_all[qkey]["false"] += 1

        if verdict == 'precise':
            verified_total += 1

    # ============================================================
    # 输出报告 (改进版)
    # ============================================================
    print(f"\n{'='*80}")
    print(f"HERMES v4.3 — 爬取报告")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"总条目: {len(all_results)} | 验证通过(精准): {verified_total}")
    print(f"{'='*80}")

    src_map = {'x_twitter': 'X', 'google': 'Google', 'reddit': 'Reddit', 'bing': 'Bing', 'github': 'GitHub', 'hackernews': 'HN', 'brave': 'Brave', 'google_news_rss': 'GNews', 'newsnow': 'NewsNow',
               'l30d_hn': 'last30d-HN', 'l30d_reddit': 'last30d-Reddit', 'l30d_polymarket': 'last30d-Polymarket'}
    src_db_map = {'x': 'X', 'google': 'Google', 'reddit': 'Reddit', 'bing': 'Bing', 'github': 'GitHub', 'hn': 'HN', 'brave': 'Brave', 'google_news_rss': 'GNews', 'newsnow': 'NewsNow',
                  'l30d_hn': 'last30d-HN', 'l30d_reddit': 'last30d-Reddit', 'l30d_polymarket': 'last30d-Polymarket'}

    # 方向覆盖
    print(f"\n── 方向覆盖（验证精度）──")
    sorted_dirs = sorted(direction_stats.items(), key=lambda x: -x[1]["hits"])
    for dir_id, ds in sorted_dirs:
        if ds["hits"] == 0:
            continue
        pct = ds["precise"] / ds["hits"] * 100 if ds["hits"] > 0 else 0
        quality = "  ✓" if pct >= 50 else ("  ⚠" if pct >= 30 else "  ✗")
        print(f"{quality} {ds['name']:16s} | {ds['hits']:3d}条 | 精准{ds['precise']}/{pct:3.0f}% | 误报{ds['false']}")

    # 查询级精调建议（只显示有命中的）
    print(f"\n── 查询精调 ──")
    for qkey, stats in sorted(query_stats_all.items(), key=lambda x: -x[1]["hits"]):
        if stats["hits"] == 0:
            continue
        src_part = qkey.split(':')[0]
        src_label = src_db_map.get(src_part, src_part)
        pct = stats["precise"] / stats["hits"] * 100 if stats["hits"] > 0 else 0
        if pct >= 70:
            flag = "  ✓"
        elif pct >= 30:
            flag = "  ⚠"
        else:
            flag = "  ✗"
        print(f"  [{src_label}] {qkey.split(':')[-1]:20s} | {stats['hits']:2d}条 | 精准{pct:3.0f}%{flag}")

    # 零命中查询
    zero_hit = [k for k, v in query_stats_all.items() if v["hits"] == 0]
    low_precision = [(k, v) for k, v in query_stats_all.items() if v["hits"] > 0 and v["precise"] / v["hits"] < 0.5]

    print(f"\n── 精调建议 ──")

    if zero_hit:
        print(f"  零命中 ({len(zero_hit)}个查询):")
        for k in zero_hit:
            src = k.split(':')[0]
            qid = k.split(':')[-1]
            label = src_db_map.get(src, src)
            print(f"    {label}/{qid}  → 无结果，建议换词或放宽")
    else:
        print(f"  所有查询均有命中")

    if low_precision:
        print(f"  低精度 ({len(low_precision)}个查询):")
        for k, v in low_precision[:5]:
            src = k.split(':')[0]
            qid = k.split(':')[-1]
            label = src_db_map.get(src, src)
            pct = v["precise"] / v["hits"] * 100
            print(f"    {label}/{qid} | {v['hits']}条 精准{pct:.0f}%  → 加exclude/收窄")
        if len(low_precision) > 5:
            print(f"    ... 还有{len(low_precision)-5}个")

    # 保存
    for item in all_results:
        item.pop('_text_for_verify', None)
        item.pop('_verify', None)
        item.pop('_verify_match', None)

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_file = CRAWL_DIR / f'multi_source_{ts}.json'

    output = {
        'timestamp': datetime.now().isoformat(),
        'v': '4.5',
        'total_items': len(all_results),
        'verified_precise': verified_total,
        'topic_coverage': {did: {"name": ds["name"], "count": ds["hits"],
                                  "precise": ds["precise"], "false": ds["false"]}
                            for did, ds in direction_stats.items() if ds["hits"] > 0},
        'query_stats': query_stats_all,
        'results': all_results
    }

    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    latest = CRAWL_DIR / 'multi_source_latest.json'
    with open(latest, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*80}")
    print(f"保存: {out_file}")
    print(f"{'='*80}")

    return len(all_results)


async def main():
    """主入口: 带多层重试的爬虫。"""
    for attempt in range(1, MAX_GLOBAL_RETRIES + 2):  # 最多 MAX_GLOBAL_RETRIES+1 次
        if attempt > 1:
            print(f"\n{'#'*80}")
            print(f"# 全局重试 #{attempt-1}/{MAX_GLOBAL_RETRIES} — 开始...")
            print(f"{'#'*80}\n")
        
        print("=" * 80)
        print(f"HERMES Multi-Source Crawler v4.5 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (attempt {attempt})")
        print(f"Target: 11 Interest Categories | Sources: X, Google, Reddit, Bing, GitHub, HN, Brave, GNews, NewsNow, last30days")
        print("=" * 80)
        
        try:
            total = await run_crawl_once()
        except Exception as e:
            total = -1
            print(f"\n!!! 爬虫异常终止: {str(e)[:100]}")
            import traceback
            traceback.print_exc()
        
        if total >= MIN_ACCEPTABLE_ITEMS:
            if attempt > 1:
                print(f"\n全局重试成功: 第 {attempt} 次运行产出 {total} 条 (>= {MIN_ACCEPTABLE_ITEMS})")
            return  # 正常退出
        
        if attempt <= MAX_GLOBAL_RETRIES:
            wait = 30 * attempt
            print(f"\n⚠ 结果不足 ({total} < {MIN_ACCEPTABLE_ITEMS}), {wait}s 后重试...")
            await asyncio.sleep(wait)
        else:
            print(f"\n✗ 重试耗尽: 最终产出 {total} 条 (目标 {MIN_ACCEPTABLE_ITEMS}+)")
            # 即使结果不足也保存了输出，不需要额外动作


if __name__ == '__main__':
    asyncio.run(main())
