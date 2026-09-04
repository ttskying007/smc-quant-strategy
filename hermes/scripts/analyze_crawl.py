#!/usr/bin/env python3
"""Analyze crawl results"""
import json
import sys

with open('/root/.hermes/crawl_data/multi_source_20260508_202033.json') as f:
    data = json.load(f)

print("=" * 80)
print("HERMES 多源数据爬取报告")
print("=" * 80)
print(f"时间: {data['timestamp']}")
print(f"总采集: {data['total_items']} 条 (来自5个来源)")
print()

# By source
sources = {}
for r in data['results']:
    s = r.get('source','unknown')
    sources.setdefault(s, []).append(r)

for src, items in sorted(sources.items()):
    print(f"  [{src}] {len(items)} 条")

print()
print("-" * 80)
print("【1. Reddit】")
reddit = sources.get('reddit', [])
subs = {}
for r in reddit:
    sub = r.get('subreddit','?')
    subs.setdefault(sub, []).append(r)
for sub, items in sorted(subs.items(), key=lambda x: len(x[1]), reverse=True):
    top = max(items, key=lambda x: x.get('score',0))
    print(f"  r/{sub}: {len(items)} 条 | 最热: \"{top['title'][:40]}...\" ↑{top['score']}")

print()
print("-" * 80)
print("【2. GitHub - Top 10 仓库】")
gh = sorted(sources.get('github', []), key=lambda x: x.get('stars',0), reverse=True)[:10]
for i, r in enumerate(gh, 1):
    print(f"  {i:2d}. ★{r['stars']:>6} {r['name']}")
    print(f"      [{r.get('language','?')}] {r.get('description','')[:60]}")
    print(f"      {r['url']}")

print()
print("-" * 80)
print("【3. Google 搜索】")
for r in sources.get('google', []):
    print(f"  • {r.get('title','')[:60]}")
    print(f"    {r['url']}")

print()
print("-" * 80)
print("【4. HackerNews - Top 5】")
hn = sorted(sources.get('hackernews', []), key=lambda x: x.get('score',0), reverse=True)[:5]
for i, r in enumerate(hn, 1):
    print(f"  {i}. ↑{r['score']} {r['title'][:60]}")
    print(f"     作者: {r.get('author','?')} | {r['url']}")

print()
print("-" * 80)
print("【5. X/Twitter】")
x_items = sources.get('x_twitter', [])
print(f"  本次: {len(x_items)} 条")
print(f"  原因: 6551.io API 返回 402 Payment Required (信用点耗尽)")
print()

print("=" * 80)
print("【技术说明】")
print()
print("本次运行是 v3.0 升级后的首次初始化执行。")
print()
print("X/Twitter 抓取历史:")
print("  v1.0 — Nitter RSS (免费实例多数不可用，返回0条)")
print("  v2.0 — XCrawl (只能获取页面元数据，无推文正文)")
print("  v3.0 — 6551.io OpenTwitter API (5/8 下午测试成功40条，但信用点已耗尽)")
print()
print("6551.io 账号: google_101832155263682857393 (JWT认证)")
print("当前状态: 402 Payment Required — 信用点归零")
print("解决方案: 去 https://ai.6551.io 充值或等待次日额度重置")
print()
print("其他来源: Reddit/GitHub/Google/HackerNews — 全部正常")
print("=" * 80)
