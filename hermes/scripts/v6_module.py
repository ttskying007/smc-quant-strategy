#!/usr/bin/env python3
"""V6 Module — V465/V466/V467 Unified Analytics Dashboard"""
import json
from pathlib import Path
from collections import Counter

DIRS = {
    'V465': '/root/.hermes/smc_opt_v465',
    'V466': '/root/.hermes/smc_opt_v466',
    'V467': '/root/.hermes/smc_opt_v467',
}

def _load(v):
    d = DIRS[v]
    sf = Path(f'{d}/{v.lower()}_full_stocks.json')
    tf = Path(f'{d}/{v.lower()}_full_trades.json')
    smf = Path(f'{d}/{v.lower()}_full_summary.json')
    stocks = json.loads(sf.read_bytes()) if sf.exists() else None
    trades = json.loads(tf.read_bytes()) if tf.exists() else None
    summary = json.loads(smf.read_bytes()) if smf.exists() else None
    return stocks, trades, summary

def _fmt(d):
    if isinstance(d, str):
        s = d.strip()
        if len(s) >= 10 and s[4]=='-' and s[7]=='-': return s[:10]
        if len(s)==8 and s.isdigit(): return f'{s[:4]}-{s[4:6]}-{s[6:8]}'
    return str(d)

def build_v6(nav=''):
    parts = [nav, '<div style="padding:20px;max-width:1400px;margin:0 auto;">']
    parts.append('<h2 style="color:#f0f6fc;margin:0 0 16px 0;">统一分析面板 V6</h2>')
    
    # ── Version comparison table ──
    parts.append('<table style="width:100%;border-collapse:collapse;background:#161b22;border:1px solid #30363d;border-radius:8px;margin-bottom:20px;font-size:13px;">')
    parts.append('<tr style="background:#1f242f;border-bottom:2px solid #30363d;">')
    for h in ['版本', '时间', 'WR', 'RR', 'PF', 'P&L', '股票', '交易', '描述']:
        align = 'left' if h in ['版本','时间','描述'] else 'right'
        parts.append(f'<th style="padding:10px 12px;color:#8b949e;text-align:{align};">{h}</th>')
    parts.append('</tr>')
    
    versions = [
        ('V465', '60min', '#58a6ff', 'MIN_RR=8.0 + hard BE-lock(hold>=2)'),
        ('V466', '日线', '#3fb950', 'MIN_RR=8.0 + hard BE-lock(hold>=2), daily data'),
        ('V467', '60min', '#f0883e', 'MIN_RR=8.0 + progressive BE + TP-distance-aware trailing'),
    ]
    
    for vkey, tf, color, desc in versions:
        stocks, trades, summary = _load(vkey)
        if not summary:
            continue
        s = summary
        ns = len(stocks) if stocks else 0
        nt = len(trades) if trades else 0
        parts.append(f'<tr style="border-bottom:1px solid #21262d;">')
        parts.append(f'<td style="padding:8px 12px;color:{color};font-weight:bold;text-align:left;">{vkey}</td>')
        parts.append(f'<td style="padding:8px 12px;color:#8b949e;text-align:left;">{tf}</td>')
        parts.append(f'<td style="padding:8px 12px;color:#fff;text-align:right;">{s["win_rate"]:.1f}%</td>')
        parts.append(f'<td style="padding:8px 12px;color:#d2a8ff;text-align:right;font-weight:bold;">{s["avg_rr"]:.2f}x</td>')
        parts.append(f'<td style="padding:8px 12px;color:#fff;text-align:right;">{s["profit_factor"]:.0f}</td>')
        parts.append(f'<td style="padding:8px 12px;color:#3fb950;text-align:right;">{s["avg_pnl"]:+.2f}%</td>')
        parts.append(f'<td style="padding:8px 12px;color:#8b949e;text-align:right;">{ns}</td>')
        parts.append(f'<td style="padding:8px 12px;color:#8b949e;text-align:right;">{nt}</td>')
        parts.append(f'<td style="padding:8px 12px;color:#8b949e;text-align:left;font-size:11px;">{desc}</td>')
        parts.append('</tr>')
    parts.append('</table>')
    
    # Load V467 for detailed analysis
    stocks, trades, summary = _load('V467')
    if not trades:
        parts.append('<p style="color:#8b949e;">等待V467数据加载...</p></div>')
        return ''.join(parts)
    
    n = len(trades)
    wins = sum(1 for t in trades if t['won'])
    rr_avg = sum(t['rr'] for t in trades)/n
    pnl_avg = sum(t['pnl_pct'] for t in trades)/n
    
    # KPI cards
    kpis = [
        ('总交易', str(n), '#f0f6fc'),
        ('可交易股票', str(len(stocks)), '#58a6ff'),
        ('WR', f'{wins/n*100:.1f}%', '#3fb950'),
        ('RR', f'{rr_avg:.2f}x', '#d2a8ff'),
        ('PF', f'{summary.get("profit_factor",0):.0f}', '#f0883e'),
        ('P&L', f'{pnl_avg:+.2f}%', '#3fb950'),
    ]
    parts.append('<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:20px;">')
    for label, val, color in kpis:
        parts.append(f'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;text-align:center;">')
        parts.append(f'<div style="color:#8b949e;font-size:12px;margin-bottom:4px;">{label}</div>')
        parts.append(f'<div style="color:{color};font-size:22px;font-weight:bold;">{val}</div></div>')
    parts.append('</div>')
    
    # Two column layout
    parts.append('<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px;">')
    
    # RR Distribution
    parts.append('<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;">')
    parts.append('<h3 style="color:#f0f6fc;font-size:14px;margin:0 0 12px 0;">RR Distribution</h3>')
    parts.append('<table style="width:100%;border-collapse:collapse;font-size:12px;">')
    for thresh in [0, 3, 5, 8, 10, 15, 20, 30, 50]:
        sub = [t for t in trades if t['rr'] >= thresh]
        if not sub: continue
        wr_s = sum(1 for t in sub if t['won'])/len(sub)*100
        rr_s = sum(t['rr'] for t in sub)/len(sub)
        parts.append(f'<tr style="border-bottom:1px solid #21262d;">')
        parts.append(f'<td style="padding:6px 8px;color:#8b949e;">RR&gt;={thresh}x</td>')
        parts.append(f'<td style="padding:6px 8px;color:#f0f6fc;text-align:right;">{len(sub)}</td>')
        parts.append(f'<td style="padding:6px 8px;color:#8b949e;text-align:right;">{len(sub)/n*100:.1f}%</td>')
        parts.append(f'<td style="padding:6px 8px;color:#3fb950;text-align:right;">{wr_s:.1f}%</td>')
        parts.append(f'<td style="padding:6px 8px;color:#d2a8ff;text-align:right;font-weight:bold;">{rr_s:.1f}x</td></tr>')
    parts.append('</table></div>')
    
    # Hold Bars
    parts.append('<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;">')
    parts.append('<h3 style="color:#f0f6fc;font-size:14px;margin:0 0 12px 0;">Hold Bars Distribution</h3>')
    parts.append('<table style="width:100%;border-collapse:collapse;font-size:12px;">')
    for hb in [1, 2, 3, 4, 5, 7, 10, 15, 20]:
        sub = [t for t in trades if t['hold_bars'] == hb]
        if not sub: continue
        w = sum(1 for t in sub if t['won'])/len(sub)*100
        r = sum(t['rr'] for t in sub)/len(sub)
        p = sum(t['pnl_pct'] for t in sub)/len(sub)
        parts.append(f'<tr style="border-bottom:1px solid #21262d;">')
        parts.append(f'<td style="padding:6px 8px;color:#8b949e;">hold={hb}</td>')
        parts.append(f'<td style="padding:6px 8px;color:#f0f6fc;text-align:right;">{len(sub)}</td>')
        parts.append(f'<td style="padding:6px 8px;color:#8b949e;text-align:right;">{len(sub)/n*100:.1f}%</td>')
        parts.append(f'<td style="padding:6px 8px;color:#3fb950;text-align:right;">{w:.1f}%</td>')
        parts.append(f'<td style="padding:6px 8px;color:#d2a8ff;text-align:right;">{r:.2f}x</td>')
        parts.append(f'<td style="padding:6px 8px;color:#58a6ff;text-align:right;">{p:+.2f}%</td></tr>')
    parts.append('</table></div>')
    parts.append('</div>')
    
    # SL tightness + TP distance
    parts.append('<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px;">')
    
    parts.append('<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;">')
    parts.append('<h3 style="color:#f0f6fc;font-size:14px;margin:0 0 12px 0;">SL Tightness Analysis</h3>')
    parts.append('<table style="width:100%;border-collapse:collapse;font-size:12px;">')
    for sl_th in [0.2, 0.3, 0.5, 0.7, 1.0]:
        tight = [t for t in trades if t['sl_pct'] <= sl_th]
        wide = [t for t in trades if t['sl_pct'] > sl_th]
        if not tight: continue
        tw = sum(1 for t in tight if t['won'])/len(tight)*100
        tr = sum(t['rr'] for t in tight)/len(tight)
        ww = sum(1 for t in wide if t['won'])/len(wide)*100 if wide else 0
        wr = sum(t['rr'] for t in wide)/len(wide) if wide else 0
        parts.append(f'<tr style="border-bottom:1px solid #21262d;">')
        parts.append(f'<td style="padding:6px 8px;color:#8b949e;">SL&lt;={sl_th:.0%}</td>')
        parts.append(f'<td style="padding:6px 8px;color:#f0f6fc;text-align:right;">{len(tight)}</td>')
        parts.append(f'<td style="padding:6px 8px;color:#3fb950;text-align:right;">{tw:.1f}%</td>')
        parts.append(f'<td style="padding:6px 8px;color:#d2a8ff;text-align:right;font-weight:bold;">{tr:.1f}x</td>')
        parts.append(f'<td style="padding:6px 8px;color:#8b949e;text-align:right;">| &gt;{sl_th:.0%}</td>')
        parts.append(f'<td style="padding:6px 8px;color:#3fb950;text-align:right;">{ww:.1f}%</td>')
        parts.append(f'<td style="padding:6px 8px;color:#d2a8ff;text-align:right;font-weight:bold;">{wr:.1f}x</td></tr>')
    parts.append('</table></div>')
    
    parts.append('<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;">')
    parts.append('<h3 style="color:#f0f6fc;font-size:14px;margin:0 0 12px 0;">TP Distance vs Performance</h3>')
    parts.append('<table style="width:100%;border-collapse:collapse;font-size:12px;">')
    for lo, hi in [(0,3),(3,5),(5,8),(8,12),(12,20),(20,100)]:
        sub = [t for t in trades if t['tp_pct'] and lo <= t['tp_pct'] < hi]
        if not sub: continue
        w = sum(1 for t in sub if t['won'])/len(sub)*100
        r = sum(t['rr'] for t in sub)/len(sub)
        p = sum(t['pnl_pct'] for t in sub)/len(sub)
        h = sum(t['hold_bars'] for t in sub)/len(sub)
        parts.append(f'<tr style="border-bottom:1px solid #21262d;">')
        parts.append(f'<td style="padding:6px 8px;color:#8b949e;">{lo}-{hi}%</td>')
        parts.append(f'<td style="padding:6px 8px;color:#f0f6fc;text-align:right;">{len(sub)}</td>')
        parts.append(f'<td style="padding:6px 8px;color:#3fb950;text-align:right;">{w:.1f}%</td>')
        parts.append(f'<td style="padding:6px 8px;color:#d2a8ff;text-align:right;font-weight:bold;">{r:.1f}x</td>')
        parts.append(f'<td style="padding:6px 8px;color:#58a6ff;text-align:right;">{p:+.2f}%</td>')
        parts.append(f'<td style="padding:6px 8px;color:#8b949e;text-align:right;">{h:.1f}b</td></tr>')
    parts.append('</table></div>')
    parts.append('</div>')
    
    # Entry type + SL type
    parts.append('<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px;">')
    
    parts.append('<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;">')
    parts.append('<h3 style="color:#f0f6fc;font-size:14px;margin:0 0 12px 0;">Entry Type</h3>')
    parts.append('<table style="width:100%;border-collapse:collapse;font-size:12px;">')
    for et in sorted(set(t.get('entry_type','?') for t in trades)):
        sub = [t for t in trades if t.get('entry_type') == et]
        w = sum(1 for t in sub if t['won'])/len(sub)*100
        r = sum(t['rr'] for t in sub)/len(sub)
        h = sum(t['hold_bars'] for t in sub)/len(sub)
        parts.append(f'<tr style="border-bottom:1px solid #21262d;">')
        parts.append(f'<td style="padding:6px 8px;color:#8b949e;">{et}</td>')
        parts.append(f'<td style="padding:6px 8px;color:#f0f6fc;text-align:right;">{len(sub)}</td>')
        parts.append(f'<td style="padding:6px 8px;color:#3fb950;text-align:right;">{w:.1f}%</td>')
        parts.append(f'<td style="padding:6px 8px;color:#d2a8ff;text-align:right;">{r:.2f}x</td>')
        parts.append(f'<td style="padding:6px 8px;color:#8b949e;text-align:right;">{h:.1f}b</td></tr>')
    parts.append('</table></div>')
    
    parts.append('<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;">')
    parts.append('<h3 style="color:#f0f6fc;font-size:14px;margin:0 0 12px 0;">SL Type Breakdown</h3>')
    parts.append('<table style="width:100%;border-collapse:collapse;font-size:12px;">')
    for sl_type in sorted(set(t['sl_type'] for t in trades)):
        sub = [t for t in trades if t['sl_type'] == sl_type]
        w = sum(1 for t in sub if t['won'])/len(sub)*100
        r = sum(t['rr'] for t in sub)/len(sub)
        asl = sum(t['sl_pct'] for t in sub)/len(sub)
        h = sum(t['hold_bars'] for t in sub)/len(sub)
        p = sum(t['pnl_pct'] for t in sub)/len(sub)
        parts.append(f'<tr style="border-bottom:1px solid #21262d;">')
        parts.append(f'<td style="padding:6px 8px;color:#8b949e;">{sl_type}</td>')
        parts.append(f'<td style="padding:6px 8px;color:#f0f6fc;text-align:right;">{len(sub)}</td>')
        parts.append(f'<td style="padding:6px 8px;color:#3fb950;text-align:right;">{w:.1f}%</td>')
        parts.append(f'<td style="padding:6px 8px;color:#d2a8ff;text-align:right;">{r:.2f}x</td>')
        parts.append(f'<td style="padding:6px 8px;color:#58a6ff;text-align:right;">{p:+.2f}%</td>')
        parts.append(f'<td style="padding:6px 8px;color:#8b949e;text-align:right;">{h:.1f}b</td></tr>')
    parts.append('</table></div>')
    parts.append('</div>')
    
    # Stock list
    parts.append('<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;margin-bottom:20px;">')
    parts.append('<h3 style="color:#f0f6fc;font-size:14px;margin:0 0 12px 0;">Top Stocks by Trades</h3>')
    parts.append('<table style="width:100%;border-collapse:collapse;font-size:11px;">')
    parts.append('<tr style="background:#1f242f;">')
    for h in ['Symbol', 'Trades', 'WR', 'RR', 'PF', 'P&L', 'Vol Class']:
        parts.append(f'<th style="padding:6px 8px;color:#8b949e;text-align:right;">{h}</th>' if h not in ['Symbol','Vol Class'] else f'<th style="padding:6px 8px;color:#8b949e;text-align:left;">{h}</th>')
    parts.append('</tr>')
    
    top_stocks = sorted(stocks, key=lambda s: s['n_trades'], reverse=True)[:50]
    for s in top_stocks:
        color = '#3fb950' if s.get('win_rate', 0) >= 80 else '#d29922'
        parts.append(f'<tr style="border-bottom:1px solid #21262d;">')
        parts.append(f'<td style="padding:4px 8px;color:#58a6ff;"><a href="/v6?s={s["symbol"]}" style="color:#58a6ff;text-decoration:none;">{s["symbol"]}</a></td>')
        parts.append(f'<td style="padding:4px 8px;color:#f0f6fc;text-align:right;">{s["n_trades"]}</td>')
        parts.append(f'<td style="padding:4px 8px;color:{color};text-align:right;">{s["win_rate"]:.1f}%</td>')
        parts.append(f'<td style="padding:4px 8px;color:#d2a8ff;text-align:right;">{s["avg_rr"]:.1f}x</td>')
        parts.append(f'<td style="padding:4px 8px;color:#f0f6fc;text-align:right;">{s.get("profit_factor",0):.0f}</td>')
        parts.append(f'<td style="padding:4px 8px;color:#58a6ff;text-align:right;">{s.get("avg_pnl",0):+.2f}%</td>')
        parts.append(f'<td style="padding:4px 8px;color:#8b949e;text-align:left;">{s.get("vol_class","?")}</td></tr>')
    parts.append('</table></div>')
    
    parts.append('</div>')
    return ''.join(parts)

def build_v6_stock(symbol, nav=''):
    """V6 Stock viewer - redirects back to dashboard with note"""
    parts = [nav, '<div style="padding:20px;">']
    parts.append(f'<h2 style="color:#f0f6fc;">{symbol}</h2>')
    parts.append('<p style="color:#8b949e;">个股K线查看请使用 V1 或 V5 功能。</p>')
    parts.append(f'<p><a href="/v1?s={symbol}" style="color:#58a6ff;">V1 K线查看器</a>')
    parts.append(f' <a href="/v5_stock?s={symbol}" style="color:#58a6ff;margin-left:16px;">V5 个股查看</a></p>')
    
    # Show V467 stats for this stock
    stocks, trades, _ = _load('V467')
    if stocks:
        for s in stocks:
            if s.get('symbol') == symbol:
                parts.append(f'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;margin-top:16px;">')
                parts.append(f'<p style="color:#f0f6fc;">V467 交易统计: {s["n_trades"]}笔 | WR={s["win_rate"]:.1f}% | RR={s["avg_rr"]:.2f}x | P&L={s["avg_pnl"]:+.2f}%</p>')
                parts.append(f'<p style="color:#8b949e;font-size:12px;">波动率: {s.get("vol_class","?")} | SL类型: {", ".join(f"{k}:{v}" for k,v in s.get("sl_types",{}).items())}</p>')
                parts.append('</div>')
                break
    
    parts.append('</div>')
    return ''.join(parts)

if __name__ == '__main__':
    print(f"V6 module: test OK ({len(build_v6())} chars)")
