#!/usr/bin/env python3
"""Patch: Fix Playwright browser args in crawler"""
import re

path = "/root/.hermes/scripts/daily_multi_source_crawler.py"
with open(path) as f:
    content = f.read()

# Add --disable-blink-features=AutomationControlled to browser launch args
old = '"--no-sandbox", "--disable-dev-shm-usage"'
new = '"--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"'
content = content.replace(old, new)

# Fix: wait longer for JS to render on search page
old2 = 'await asyncio.sleep(4)\n                    page_title'
new2 = 'await asyncio.sleep(6)\n                    page_title'
content = content.replace(old2, new2)

# Fix: also increase initial sleep after homepage visit
old3 = 'await asyncio.sleep(3)\n                    print(f"  Session established'
new3 = 'await asyncio.sleep(5)\n                    print(f"  Session established'
content = content.replace(old3, new3)

with open(path, 'w') as f:
    f.write(content)
print("Patched successfully")
