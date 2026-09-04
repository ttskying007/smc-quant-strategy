# -*- coding: utf-8 -*-
"""Try Eastmoney announcement text-content endpoints (non-PDF)."""
import io, json, sys, urllib.request, urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://data.eastmoney.com/notices/"}


def get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except Exception as e:
        return None, str(e)[:120]


# art_code from the known announcement
art = "AN202608141827994407"
# attempt text-content endpoints
for ep in [f"https://np-cnotice-stock.eastmoney.com/api/content/ann?art_code={art}&client_source=web&page_index=1",
           f"https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size=1&page_index=1&ann_type=A&client_source=web&art_code={art}",
           f"https://np-cnotice-stock.eastmoney.com/api/content/ann?art_code={art}&client_source=web"]:
    st, b = get(ep)
    print("=== ", ep[:70], "===")
    if st == 200:
        try:
            d = json.loads(b)
            s = json.dumps(d, ensure_ascii=False)
            # look for text fields
            has_text = any(k in s for k in ("content", "summary", "text"))
            print("  keys:", list(d.keys())[:8] if isinstance(d, dict) else type(d))
            print("  has text:", has_text)
            print("  sample:", s[:300])
        except Exception as e:
            print("  parse:", e, b[:200])
    else:
        print("  FAIL:", b)
