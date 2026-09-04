# -*- coding: utf-8 -*-
"""解析同花顺 K 线 JSON 格式 + 写入 kline_cache_tencent 兼容格式"""
import io, json, re, sys, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "http://www.10jqka.com.cn/"}

def fetch_ths_kline(code, days=140):
    """拉取同花顺日 K（最近 days 条）"""
    url = f"http://d.10jqka.com.cn/v6/line/hs_{code}/01/last.js"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=12) as r:
        txt = r.read().decode("utf-8", errors="replace")
    # 格式: quotebridge_v6_line_hs_000001_01_last({...})
    m = re.search(r"\((\{.*\})\)\s*$", txt, re.S)
    if not m:
        return None
    data = json.loads(m.group(1))
    return data


def parse_ths_kline(data):
    """解析同花顺 K 线 JSON → [{t,o,h,l,c,v}]"""
    # data: {"num":140,"year":{...},"data":"19910403,58.52,58.72,58.00,58.00,0,...;..."}
    raw = data.get("data", "")
    out = []
    for line in raw.split(";"):
        parts = line.split(",")
        if len(parts) >= 7:
            t = parts[0]
            try:
                o, h, l, c = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                v = float(parts[6]) if len(parts) > 6 else 0
                out.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v})
            except Exception:
                continue
    return out


if __name__ == "__main__":
    code = "000001"
    data = fetch_ths_kline(code)
    if data:
        bars = parse_ths_kline(data)
        print(f"同花顺 K 线: {len(bars)} 条 (000001)")
        if bars:
            print(f"  最新: {bars[-1]}")
            print(f"  最旧: {bars[0]}")
    else:
        print("解析失败")
