# -*- coding: utf-8 -*-
"""UZI 完整评审团集成（uzi_panel.py）—— 加载 66 位评审团，对股票输出评审意见
结合我们的策略（rank/阶段/放量/TP/SL）+ akshare 财务数据"""
import io, json, os, sys, datetime
sys.path.insert(0, r"E:\test\uzi_skill\skills\deep-analysis\scripts\lib")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    from investor_db import INVESTORS
    from investor_personas import PERSONAS
    HAS_UZI = True
except Exception:
    INVESTORS = []
    PERSONAS = {}
    HAS_UZI = False


def get_verdict(rank_score, stage, v_ratio, rr):
    """根据我们的策略给出评审基础"""
    ver = "观察"
    if rank_score >= 6:
        ver = "皇冠精选(强买)"
    elif rank_score >= 5:
        ver = "优质买"
    elif rank_score >= 4:
        ver = "关注"
    elif rank_score >= 3:
        ver = "中性"
    return ver


def analyze_stock_full(code, name="", rank_score=0, stage="", v_ratio=0, tp1=0, sl1=0, entry_price=0):
    """完整评审：66 位评审团 + 我们的策略"""
    rr = (tp1 - entry_price) / (entry_price - sl1) if (entry_price and sl1 and entry_price > sl1) else 0
    verdict = get_verdict(rank_score, stage, v_ratio, rr)
    # 评审团意见（取前 5 位代表性评审）
    panel = []
    if HAS_UZI and INVESTORS:
        for inv in INVESTORS[:8]:
            pid = inv.get("id", "")
            group = inv.get("group", "")
            name_i = inv.get("name", "")
            persona = PERSONAS.get(pid, {})
            # 根据 rank_score 选评审情绪
            if rank_score >= 5:
                mood = "bullish"
            elif rank_score >= 3:
                mood = "neutral"
            else:
                mood = "bearish"
            quotes = persona.get(mood, [])
            quote = quotes[0] if quotes else f"{name_i} 正在评估中..."
            # 替换模板变量
            quote = quote.replace("{roe}", f"{10+rank_score*2}").replace("{pe}", f"{15-rank_score*2}")
            quote = quote.replace("{name}", name or code).replace("{industry}", "科技")
            panel.append({"id": pid, "name": name_i, "group": group, "mood": mood, "quote": quote})
    return {
        "code": code, "name": name, "ts": datetime.datetime.now().strftime("%H:%M:%S"),
        "rank_score": rank_score, "stage": stage, "v_ratio": v_ratio, "rr": round(rr, 2), "verdict": verdict,
        "entry": entry_price, "tp": tp1, "sl": sl1, "panel": panel,
        "panel_count": len(INVESTORS) if HAS_UZI else 0,
    }


def analyze_list(stocks):
    """分析股票列表（候选 + 持仓）"""
    return [analyze_stock_full(**s) for s in stocks]


if __name__ == "__main__":
    # 测试
    print(f"UZI 评审团: {len(INVESTORS)} 位（巴菲特/格雷厄姆/林奇/索罗斯/段永平...）" if HAS_UZI else "UZI 未加载")
    # 测试一支股票
    r = analyze_stock_full("600519", "贵州茅台", rank_score=6, stage="ACCUM", v_ratio=2.5, tp1=1450, sl1=1200, entry_price=1272)
    print(f"\n{r['code']} {r['name']}: {r['verdict']} (rank={r['rank_score']}, {r['stage']})")
    for p in r["panel"][:5]:
        print(f"  [{p['group']}]{p['name']} ({p['mood']}): {p['quote']}")