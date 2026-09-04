# -*- coding: utf-8 -*-
"""build_uzi：/uzi 页面 —— UZI LLM 动态评审（66位评审团 + deepseek-v4-flash）"""
import io, json, sys, os
sys.path.insert(0, r"E:\test\smc_project\uzi")


def build_uzi():
    """UZI 评审分析页：持仓 + 候选股票（规则模板 + LLM 动态评审）"""
    import html
    from uzi_panel import analyze_stock_full, HAS_UZI, INVESTORS
    from uzi_review import batch_review
    # 1. 持仓股票
    try:
        led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
    except Exception:
        led = []
    active = [t for t in led if t.get("status") != "CLOSED"]

    # 2. 候选股票
    cands = []
    try:
        scan = json.load(open(r"E:\test\smc_project\research\current_scanner_result.json", encoding="utf-8"))
        for c in (scan.get("event_candidates") or [])[:10]:
            sym = str(c.get("symbol", "")).split(".")[0]
            cands.append({"code": sym, "name": str(c.get("title", ""))[:12] or sym, "rank_score": 3,
                          "stage": "候选", "v_ratio": 0, "tp1": 0, "sl1": 0, "entry_price": 0})
        for c in (scan.get("continuation_candidates") or [])[:10]:
            sym = str(c.get("symbol", "")).split(".")[0]
            cands.append({"code": sym, "name": "延续:" + sym, "rank_score": 4, "stage": "MARKUP",
                          "v_ratio": 0, "tp1": c.get("entry_price", 0) * 1.15, "sl1": c.get("support", 0) * 0.99,
                          "entry_price": c.get("entry_price", 0)})
    except Exception:
        pass

    # 3. 规则模板评审（快速）—— 显示全部（不过滤）
    pos_results = [analyze_stock_full(t.get("code"), t.get("name", ""), t.get("rank_score", 0), t.get("stage", ""),
                                      t.get("v_ratio", 0), t.get("tp1", 0), t.get("sl1", 0), t.get("entry_price", 0))
                   for t in active]
    cand_results = [analyze_stock_full(c["code"], c["name"], c["rank_score"], c["stage"], c["v_ratio"],
                                       c["tp1"], c["sl1"], c["entry_price"]) for c in cands]

    # 4. LLM 动态评审（批量 + 缓存）—— 只处理前 5 支避免页面超时
    llm_stocks = [{"code": r["code"], "name": r["name"], "rank_score": r["rank_score"],
                   "stage": r["stage"], "v_ratio": r["v_ratio"], "rr": r["rr"]}
                  for r in (pos_results + cand_results)[:5]]
    llm_results = {}
    try:
        for x in batch_review(llm_stocks):
            llm_results[x["code"]] = x.get("llm") or {}
    except Exception:
        pass

    def render(results):
        rows = ''
        for r in results:
            vd = f"阶段:{r['stage']} · 量比:{r['v_ratio']} · 盈亏比:{r['rr']}"
            color = '#3fb950' if r["rank_score"] >= 6 else ('#d29922' if r["rank_score"] >= 4 else '#8b949e')
            # LLM 评审（若有）
            llm = llm_results.get(r["code"], {})
            if llm:
                pn = '<br>'.join(f'<span style="color:#58a6ff">{html.escape(k)}</span>: {html.escape(str(v))[:60]}' for k, v in list(llm.items())[:4])
            else:
                pn = '<br>'.join(f'<span style="color:{("#3fb950" if p["mood"]=="bullish" else "#f85149")}">[{p["group"]}]{html.escape(p["name"])}</span>: {html.escape(p["quote"])[:40]}' for p in r["panel"][:3])
            rows += f'''<tr><td class="mono"><a href="/kline?symbol={r['code'] + ('.SH' if r['code'].startswith('6') else '.SZ')}">{r['code']}</a></td>
<td>{html.escape(str(r['name']))}</td>
<td style="color:{color}">{html.escape(str(r['verdict']))}</td>
<td class="mono">rank={r['rank_score']}</td>
<td class="mono">{html.escape(str(r['stage']))}</td>
<td style="font-size:10px;color:#8b949e">{html.escape(vd)}</td>
<td class="mono">{r['entry']}</td>
<td class="mono" style="color:#3fb950">{r['tp']}</td>
<td class="mono" style="color:#f85149">{r['sl']}</td>
<td style="font-size:10px">{pn}</td></tr>'''
        return rows

    n_panel = len(INVESTORS) if HAS_UZI else 0
    return f'''<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>UZI LLM 评审</title><style>{_CSS()}</style></head><body>{_NAV()}<div class="container">
<div class="card" style="border-left:3px solid #bc8cff"><h2>🎯 UZI 评审（{n_panel} 位评审团 + LLM 动态 deepseek-v4-flash）</h2>
<p style="color:#8b949e">持仓（{len(active)} 笔）+ 候选股票：规则模板（66 位评审）快速总评 + LLM 动态生成巴菲特/索罗斯/林奇意见。刷新页面触发 LLM 批量评审（缓存）。</p>
<p style="color:#d29922;background:#1c2128;padding:6px 10px;border-radius:4px;border:1px solid #d29922"><b>⚠️ 重要：本页评审<b>仅供参考</b>，<b>不改变选股结果</b>。选股由 rank_score（阶段/放量/跨度/周线等量化特征）自动决定，UZI 意见只作辅助参考，不构成过滤条件。全部股票均展示，无过滤。</p></div>
<div class="card"><h3>持仓股票评审（{len(pos_results)} 笔）</h3>
<table><thead><tr><th>代码</th><th>名称</th><th>总评</th><th>rank</th><th>阶段</th><th>量比/盈亏比</th><th>入场</th><th>TP1</th><th>SL1</th><th>评审意见（LLM/规则）</th></tr></thead>
<tbody>{render(pos_results) or '<tr><td colspan=10>无持仓</td></tr>'}</tbody></table></div>
<div class="card"><h3>候选股票评审（{len(cand_results)} 笔）</h3>
<table><thead><tr><th>代码</th><th>名称</th><th>总评</th><th>rank</th><th>阶段</th><th>量比/盈亏比</th><th>入场</th><th>TP1</th><th>SL1</th><th>评审意见（LLM/规则）</th></tr></thead>
<tbody>{render(cand_results) or '<tr><td colspan=10>暂无候选</td></tr>'}</tbody></table></div>
</div></body></html>'''


def _CSS():
    return "body{background:#0d1117;color:#e6edf3;font-family:Segoe UI,Arial;margin:0}.container{max-width:1400px;margin:0 auto;padding:16px}.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px;margin-bottom:12px}h2,h3{margin:4px 0}table{width:100%;border-collapse:collapse;font-size:12px}th,td{border:1px solid #30363d;padding:5px 7px;text-align:left;vertical-align:top}th{background:#21262d}.mono{font-family:Consolas,monospace}a{color:#58a6ff;text-decoration:none}nav{background:#161b22;padding:8px 16px;border-bottom:1px solid #30363d}nav a{color:#8b949e;margin-right:12px}nav a:hover{color:#58a6ff}"


def _NAV():
    return "<nav><a href='/'>仪表</a><a href='/monitor'>选股</a><a href='/kline'>K线</a><a href='/backtest'>回测</a><a href='/live'>实时</a><a href='/uzi'>UZI评审</a><a href='/analysis'>分析</a><a href='/autopsy'>复盘</a></nav>"
