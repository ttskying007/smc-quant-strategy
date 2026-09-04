#!/usr/bin/env python3
"""
SMC 信号扫描器 V4 — SMC市场逻辑正解
=====================================
事件 → 确认 → 位置 → 入场

L1: OB_Bull独立 (完整事件产物, 自带机构逻辑)
L2: LIQ → FVG_Bull组合 (前序LIQ事件 + FVG回访, gap≤10)
丢弃: STRUCT起点(因果反转), gap>10(过期), FVG孤立(无前序事件)
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20
from v11.v19_backtest_engine import find_tps, find_sls

KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v21')
OUT.mkdir(exist_ok=True)

# ═══ 信号分类 (SMC修正版) ═══
LIQ_LONG = ['Sweep_SSL', 'EQL']          # 事件起点: 流动性被扫
STRUCT_LONG = ['CHOCH_Bull','BOS_Bull','MSS_Bull']  # 确认: displacement结果
ZONE_LONG = ['OB_Bull', 'FVG_Bull']       # 位置: 价格回访目标

MIN_GAP = 1
MAX_GAP = 10  # 机构快速回补, gap不过大

DNA_FILE = OUT / 'stock_dna_v11.json'
dna = {}
if DNA_FILE.exists():
    with open(DNA_FILE) as f:
        dna = json.load(f).get('dna', {})

def weekly_smc_trend(weekly):
    if len(weekly) < 20: return 'neutral', {}
    sigs, st, _, _ = detect_all_signals_v20(weekly)
    tc = st['type_counts']
    cb=tc.get('CHOCH_Bull',0); cbr=tc.get('CHOCH_Bear',0)
    bb=tc.get('BOS_Bull',0); bbr=tc.get('BOS_Bear',0)
    last_ch = [s for s in sigs if 'CHOCH' in s.type]
    last_dir = 'bull' if last_ch and 'Bull' in last_ch[-1].type else ('bear' if last_ch and 'Bear' in last_ch[-1].type else None)
    if last_dir=='bull' and cb+bb>=cbr+bbr: return 'bullish', tc
    if last_dir=='bear' and cbr+bbr>cb+bb: return 'bearish', tc
    if cb+bb>(cbr+bbr)*1.5: return 'bullish', tc
    if cbr+bbr>(cb+bb)*1.5: return 'bearish', tc
    return 'neutral', tc

def daily_to_weekly(daily):
    w = []
    for i in range(0, len(daily), 5):
        c = daily[i:i+5]
        if len(c) >= 3:
            w.append({'o':c[0]['o'],'h':max(b['h'] for b in c),'l':min(b['l'] for b in c),'c':c[-1]['c']})
    return w

def make_ob_pick(sym, ob_sig, entry_bar, entry_price, sl, tp, sig_date, sd, w_trend):
    return {
        'symbol': sym, 'tier': 'L1', 'signal': 'OB_Bull',
        'signal_date': sig_date, 'entry_date': sig_date,
        'entry_price': entry_price, 'sl': sl, 'tp': tp,
        'zone_bar': ob_sig.idx, 'zone_type': 'OB_Bull',
        'zone_low': ob_sig.lower if hasattr(ob_sig,'lower') else 0,
        'hist_wr': sd.get('v11_wr',0), 'ob_wr': sd.get('ob_wr',0),
        'hist_trades': sd.get('v11_trades',0), 'trend': w_trend,
    }

def make_combo_pick(sym, liq_sig, fvg_sig, gap, entry_bar, entry_price, sl, tp, sig_date, sd, w_trend):
    return {
        'symbol': sym, 'tier': 'L2', 'signal': f'{liq_sig.type}→FVG_Bull',
        'signal_date': sig_date, 'entry_date': sig_date,
        'entry_price': entry_price, 'sl': sl, 'tp': tp,
        'zone_bar': fvg_sig.idx, 'zone_type': 'FVG_Bull', 'gap': gap,
        'liq_type': liq_sig.type, 'liq_bar': liq_sig.idx,
        'zone_low': fvg_sig.lower if hasattr(fvg_sig,'lower') else 0,
        'hist_wr': sd.get('v11_wr',0), 'ob_wr': sd.get('ob_wr',0),
        'hist_trades': sd.get('v11_trades',0), 'trend': w_trend,
    }

# ═══ MAIN ═══
t0 = time.time()
daily_files = sorted(KLINE.glob('*_daily_300.json'))
picks = []

for fi, df in enumerate(daily_files):
    sym = df.stem.replace('_daily_300', '')
    try:
        daily = json.loads(df.read_bytes())
        if len(daily) < 50: continue
    except: continue
    
    # Weekly: only bullish
    weekly_path = KLINE / f'{sym}_weekly_200.json'
    weekly = None
    if weekly_path.exists():
        try: weekly = json.loads(weekly_path.read_bytes())
        except: pass
    if weekly is None or len(weekly) < 20:
        weekly = daily_to_weekly(daily)
    w_trend, _ = weekly_smc_trend(weekly)
    if w_trend != 'bullish': continue
    
    # Daily signals
    sigs, st, _, swings_dict = detect_all_signals_v20(daily)
    sbb = defaultdict(list)
    for s in sigs: sbb[s.idx].append(s)
    
    n = len(daily)
    last_date = datetime.strptime(str(daily[-1].get('t', daily[-1].get('date', '')))[:8], '%Y%m%d')
    cutoff = last_date - timedelta(days=30)  # 全量扫描
    sd = dna.get(sym, {})
    
    # Collect candidates within scan window (last 50 bars, within 3 days)
    l1_candidates = []  # OB_Bull standalone
    l2_candidates = []  # LIQ → FVG combo
    
    for i in range(max(0, n-50), n-3):
        if i not in sbb: continue
        types = [s.type for s in sbb[i]]
        sig_date = str(daily[i].get('t', daily[i].get('date', '')))[:8]
        try:
            if datetime.strptime(sig_date, '%Y%m%d') < cutoff: continue
        except: continue
        
        # ── L1: OB_Bull独立 ──
        for s in sbb[i]:
            if s.type != 'OB_Bull': continue
            entry_bar = i + 1
            if entry_bar >= n: continue
            ep = daily[entry_bar]['o']
            # V4-style TP/SL
            tp, tp_src, _ = find_tps(ep, sigs, swings_dict, daily)
            sl, sl_src, _ = find_sls(ep, sigs, swings_dict, daily)
            if tp is None: tp = ep * 1.05
            if tp > ep * 1.05: tp = ep * 1.05
            tp = round(tp, 2)
            sl = round(sl, 2) if sl else round(ep * 0.97, 2)
            l1_candidates.append(make_ob_pick(sym, s, entry_bar, ep, sl, tp, sig_date, sd, w_trend))
        
        # ── L2: LIQ(事件起点) → FVG(位置) ──
        liq_sigs = [s for s in sbb[i] if s.type in LIQ_LONG]
        if not liq_sigs: continue
        
        for liq in liq_sigs:
            for j in range(i+MIN_GAP, min(i+MAX_GAP+1, n)):
                if j not in sbb: continue
                fvg_sigs = [s for s in sbb[j] if s.type == 'FVG_Bull']
                if not fvg_sigs: continue
                
                fvg = fvg_sigs[0]
                gap = j - i
                entry_bar = j + 1
                if entry_bar >= n: continue
                ep = daily[entry_bar]['o']
                # V4-style TP/SL
                tp, tp_src, _ = find_tps(ep, sigs, swings_dict, daily)
                sl, sl_src, _ = find_sls(ep, sigs, swings_dict, daily)
                
                # Cap TP at 5%
                if tp is None: tp = ep * 1.05
                if tp > ep * 1.05: tp = ep * 1.05
                
                # RR filter (same as V4)
                tp_dist = abs(tp - ep) / ep * 100
                sl_dist = abs(sl - ep) / ep * 100
                if sl_dist == 0 or tp_dist / sl_dist < 1.0:
                    continue  # unfavorable RR
                
                sl = round(sl, 2)
                tp = round(tp, 2)
                l2_candidates.append(make_combo_pick(sym, liq, fvg, gap, entry_bar, ep, sl, tp, sig_date, sd, w_trend))
                break  # first FVG per LIQ
    
    # Dedup: per entry_bar, prefer OB over combo, prefer tighter gap
    all_candidates = []
    for c in l1_candidates:
        all_candidates.append((1, 0, c))  # L1 priority
    for c in l2_candidates:
        all_candidates.append((2, c['gap'], c))  # L2, prefer tighter gap
    
    all_candidates.sort(key=lambda x: (x[1] if isinstance(x[1], int) else x[1], x[0]))
    seen_entries = set()
    for _, _, c in all_candidates:
        key = (sym, c['entry_date'])
        if key in seen_entries: continue
        seen_entries.add(key)
        picks.append(c)
    
    if (fi+1) % 1000 == 0:
        print(f"  [{fi+1}/{len(daily_files)}] {time.time()-t0:.0f}s picks={len(picks)}")

elapsed = time.time() - t0

# Stats
l1_count = sum(1 for p in picks if p['tier']=='L1')
l2_count = sum(1 for p in picks if p['tier']=='L2')
chain_dist = defaultdict(int)
for p in picks:
    chain_dist[p['signal']] += 1

print(f"\n{'='*60}")
print(f"  SMC信号扫描 V4 (SMC正解) — {elapsed:.0f}s")
print(f"  🥇 L1 OB_Bull:    {l1_count}个")
print(f"  🥈 L2 LIQ→FVG:    {l2_count}个")
print(f"  总计:             {len(picks)}个")
print(f"\n  信号分布:")
for c, cnt in sorted(chain_dist.items(), key=lambda x:-x[1]):
    print(f"    {c}: {cnt}")

output = {
    'meta': {'version':'V4 SMC正解','date':time.strftime('%Y-%m-%d %H:%M'),
             'l1':l1_count,'l2':l2_count,'total':len(picks),'elapsed':round(elapsed,1)},
    'picks': picks,
}
json.dump(output, open(OUT/'LD_picks_v4.json','w'), ensure_ascii=False)
print(f"\n  保存: {OUT/'LD_picks_v4.json'}")
