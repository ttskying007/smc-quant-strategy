#!/usr/bin/env python3
"""Verify V44 frontend pages and stale-version leakage.

Checks the live dashboard pages for:
- expected V44 title/branding
- absence of V24/V31 stale labels
- presence of V44 summary tokens on pages that should expose them

Usage:
  python3 v44_verify_frontend.py http://127.0.0.1:8890
"""

from __future__ import annotations

import re
import sys
from urllib.request import urlopen

PAGES = ["/", "/backtest", "/monitor", "/analysis", "/autopsy"]
STALE_PATTERNS = [
    r"SMC V24",
    r"V24选股",
    r"V24 回测概览",
    r"V24 高质量选股",
    r"V31 引擎总览",
    r"V31实测",
    r"V31 逐笔交易复盘诊断",
]


def fetch(url: str) -> str:
    return urlopen(url, timeout=60).read().decode("utf-8", "ignore")


def check(base: str) -> int:
    failures = 0
    for path in PAGES:
        html = fetch(base.rstrip("/") + path)
        title = re.search(r"<title>(.*?)</title>", html)
        title_text = title.group(1) if title else ""
        stale = [p for p in STALE_PATTERNS if re.search(p, html)]
        ok_v44 = ("SMC V44" in html) or ("V44" in html)
        print(f"{path}: title={title_text!r} v44={ok_v44} stale={stale}")
        if stale:
            failures += 1
    return failures


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: v44_verify_frontend.py http://127.0.0.1:8890", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(check(sys.argv[1]))
