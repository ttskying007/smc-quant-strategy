#!/usr/bin/env python3
"""
SMC 分层信号扫描器 V3
=====================
🥇 L1: OB_Bull单信号 (最高质量, WR=89.5%, 无需前序)
🥈 L2: LIQ/STRUCT → FVG_Bull组合, gap≤10 (组合有效, WR~78%)
🥉 L3: LIQ/STRUCT → FVG_Bull组合, gap>10 (次选, WR~72%)
过滤: FVG孤立信号(无前序, WR=64.5%)

机制说明:
  - V20引擎在每个bar检测LIQ/STRUCT/ZONE信号
  - L1: 直接找到OB_Bull, T+1入场
  - L2/L3: 从LIQ/STRUCT出发, 向后扫描找FVG_Bull, 按gap分级
  - 入场: ZONE bar+1的open价, SL=zone_low(cap 3%), TP=结构止盈
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

CATEGORIES = {
    'LIQ_LONG':  ['Sweep_SSL', 'EQL'],
    'STRUCT_LONG': ['CHOCH_Bull','BOS_Bull','MSS_Bull'],
}
PATTERNS = {
    'L→FVG':  (['LIQ_LONG','ZONE'],[25]),
    'S→FVG':  (['STRUCT_LONG','ZONE'],[20]),
}

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

def calc_sl_tp(entry_price, zone_signal, all_signals, swings_dict, daily):
    """计算SL/TP: SL=zone_low(cap 3%), TP=结构止盈or固定3%"""
    # SL
    zone_low = zone_signal.lower if hasattr(zone_signal,'lower') and zone_signal.lower else 0
    if zone_low > 0:
        sl_dist = (entry_price - zone_low) / entry_price
        if sl_dist > 0.03:
            sl_price = round(entry_price * 0.97, 2)
        elif sl_dist < 0.005:
            sl_price = round(entry_price * 0.995, 2)
        else:
            sl_price = round(zone_low, 2)
    else:
        sl_price = round(entry_price * 0.97, 2)
    
    # TP: structural or fixed
    tp_price, tp_src, _ = find_tps(entry_price, all_signals, swings_dict, daily)
    if tp_price is None or tp_price <= entry_price * 1.005:
        tp_price = round(entry_price * 1.03, 2)
    elif tp_price > entry_price * 1.05:
        tp_price = round(entry_price * 1.05, 2)
    else:
        tp_price = round(tp_price, 2)
    
    return sl_price, tp_price

# ═══ MAIN ═══
t0 = time.time()
daily_files = sorted(KLINE.glob('*_daily_300.json'))
picks_l1 = []   # OB_Bull
picks_l2 = []   # combo gap≤10
picks_l3 = []   # combo gap>10
stats = defaultdict(lambda: {'l1':0,'l2':0,'l3':0})

for fi, df in enumerate(daily_files):
    sym = df.stem.replace('_daily_300', '')
    try:
        daily = json.loads(df.read_bytes())
        if len(daily) < 50: continue
    except: continue
    
    # Weekly trend → only bullish
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
    cutoff = last_date - timedelta(days=30)  # 30天窗口捕获OB_Bull
    
    sd = dna.get(sym, {})
    
    # ═══ L1: OB_Bull单信号 (dedup by entry_bar) ═══
    l1_candidates = []
    for i in range(max(0, n-50), n-3):
        if i not in sbb: continue
        ob_signals = [s for s in sbb[i] if s.type == 'OB_Bull']
        if not ob_signals: continue
        
        sig_date = str(daily[i].get('t', daily[i].get('date', '')))[:8]
        try:
            if datetime.strptime(sig_date, '%Y%m%d') < cutoff: continue
        except: continue
        
        entry_bar = i + 1
        if entry_bar >= n: continue
        entry_price = daily[entry_bar]['o']
        sl_price, tp_price = calc_sl_tp(entry_price, ob_signals[0], sigs, swings_dict, daily)
        l1_candidates.append({
            'ob': ob_signals[0], 'entry_bar': entry_bar, 'entry_price': entry_price,
            'sl': sl_price, 'tp': tp_price, 'sig_date': sig_date,
        })
    
    seen_l1_entries = set()
    for c in l1_candidates:
        key = (sym, c['entry_bar'])
        if key in seen_l1_entries: continue
        seen_l1_entries.add(key)
        picks_l1.append({
            'symbol': sym, 'tier': 'L1', 'signal': 'OB_Bull',
            'signal_date': c['sig_date'], 'entry_date': c['sig_date'],
            'entry_price': c['entry_price'], 'sl': c['sl'], 'tp': c['tp'],
            'zone_bar': c['ob'].idx, 'zone_type': 'OB_Bull', 'gap': 0,
            'hist_wr': sd.get('v11_wr',0), 'ob_wr': sd.get('ob_wr',0),
            'hist_trades': sd.get('v11_trades',0), 'trend': w_trend,
        })
        stats[sym]['l1'] += 1
    
    # ═══ L2/L3: LIQ/STRUCT → FVG_Bull组合 (dedup by entry_bar) ═══
    used_entries = set()  # dedup key: (sym, entry_bar)
    
    # Collect all combo candidates first, then keep best per entry_bar
    combo_candidates = []
    for i in range(max(0, n-50), n-3):
        if i not in sbb: continue
        liq_struct = [s for s in sbb[i] if s.type in CATEGORIES['LIQ_LONG'] + CATEGORIES['STRUCT_LONG']]
        if not liq_struct: continue
        
        sig_date = str(daily[i].get('t', daily[i].get('date', '')))[:8]
        try:
            if datetime.strptime(sig_date, '%Y%m%d') < cutoff: continue
        except: continue
        
        for ls in liq_struct:
            search_end = min(i + 25, n)
            for j in range(i+1, search_end):
                if j not in sbb: continue
                fvg_signals = [s for s in sbb[j] if s.type == 'FVG_Bull']
                if not fvg_signals: continue
                fvg = fvg_signals[0]
                gap = j - i
                entry_bar = j + 1
                if entry_bar >= n: continue
                entry_price = daily[entry_bar]['o']
                sl_price, tp_price = calc_sl_tp(entry_price, fvg, sigs, swings_dict, daily)
                combo_candidates.append({
                    'liq': ls, 'fvg': fvg, 'gap': gap, 'entry_bar': entry_bar,
                    'entry_price': entry_price, 'sl': sl_price, 'tp': tp_price,
                    'sig_date': sig_date,
                })
    
    # Dedup: per entry_bar, keep the combo with the smallest gap (tightest)
    combo_candidates.sort(key=lambda x: (x['entry_bar'], x['gap']))
    seen_entries = set()
    for c in combo_candidates:
        key = (sym, c['entry_bar'])
        if key in seen_entries: continue
        seen_entries.add(key)
        
        tier = 'L2' if c['gap'] <= 10 else 'L3'
        chain = f'{c["liq"].type}→FVG_Bull'
        pick = {
            'symbol': sym, 'tier': tier, 'signal': chain,
            'signal_date': c['sig_date'], 'entry_date': c['sig_date'],
            'entry_price': c['entry_price'], 'sl': c['sl'], 'tp': c['tp'],
            'zone_bar': c['fvg'].idx, 'zone_type': 'FVG_Bull', 'gap': c['gap'],
            'liq_type': c['liq'].type, 'liq_bar': c['liq'].idx,
            'hist_wr': sd.get('v11_wr',0), 'ob_wr': sd.get('ob_wr',0),
            'hist_trades': sd.get('v11_trades',0), 'trend': w_trend,
        }
        if tier == 'L2':
            picks_l2.append(pick)
            stats[sym]['l2'] += 1
        else:
            picks_l3.append(pick)
            stats[sym]['l3'] += 1
    
    if (fi+1) % 1000 == 0:
        print(f"  [{fi+1}/{len(daily_files)}] {time.time()-t0:.0f}s L1={len(picks_l1)} L2={len(picks_l2)} L3={len(picks_l3)}")

elapsed = time.time() - t0

# ═══ Report ═══
print(f"\n{'='*60}")
print(f"  分层信号扫描 V3 — {elapsed:.0f}s")
print(f"{'='*60}")
print(f"  🥇 L1 OB_Bull:     {len(picks_l1)}个")
print(f"  🥈 L2 Combo≤10:    {len(picks_l2)}个")
print(f"  🥉 L3 Combo>10:    {len(picks_l3)}个")
print(f"  总计:              {len(picks_l1)+len(picks_l2)+len(picks_l3)}个")

# Chain distribution for L2+L3
chain_dist = defaultdict(int)
for p in picks_l2 + picks_l3:
    chain_dist[p['signal']] += 1
print(f"\n  组合链类型(L2+L3):")
for c, cnt in sorted(chain_dist.items(), key=lambda x:-x[1]):
    print(f"    {c}: {cnt}")

# Save
all_picks = picks_l1 + picks_l2 + picks_l3
output = {
    'meta': {
        'version': 'V3 layered',
        'date': time.strftime('%Y-%m-%d %H:%M'),
        'l1': len(picks_l1), 'l2': len(picks_l2), 'l3': len(picks_l3),
        'elapsed': round(elapsed, 1),
    },
    'picks': all_picks,
}
json.dump(output, open(OUT/'LD_picks_v3.json','w'), ensure_ascii=False)
print(f"\n  保存: {OUT/'LD_picks_v3.json'}")
