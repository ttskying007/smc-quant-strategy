#!/usr/bin/env python3
"""
SMC L→D 序列扫描器 — 仅bullish周线趋势 + 做多序列
输出: L→D picks JSON (用于实时监控)
检测: 周线SMC趋势 → 日线L→D序列(LIQ→ZONE) → 入场信号
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20

KLINE = Path('/root/.hermes/kline_cache')
KLINE_60 = Path('/root/.hermes/kline_cache_60min')
OUT = Path('/root/.hermes/smc_opt_v21')
OUT.mkdir(exist_ok=True)

# ═══ 配置 ═══
CATEGORIES = {
    'LIQ_LONG':  ['Sweep_SSL', 'EQL'],
    'ZONE_LONG': ['OB_Bull', 'FVG_Bull'],
    'STRUCT_LONG': ['CHOCH_Bull','BOS_Bull','MSS_Bull'],
}
# L→D = LIQ + ZONE; S→D = STRUCT + ZONE (保留兼容)
PATTERNS = {
    'L→D':  (['LIQ_LONG','ZONE_LONG'],[25]),
    'S→D':  (['STRUCT_LONG','ZONE_LONG'],[20]),
    'L→S→D':(['LIQ_LONG','STRUCT_LONG','ZONE_LONG'],[30,15]),
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

def detect_sequences(signals, direction='long'):
    sbb = defaultdict(list)
    for s in signals: sbb[s.idx].append(s)
    seqs = []
    for pn, (stages, gaps) in PATTERNS.items():
        ss = [CATEGORIES[s] for s in stages]
        for sb in sorted(sbb):
            for sig in [s for s in sbb[sb] if s.type in ss[0]]:
                chain = [sig]; c = sig.idx; ok = True
                for si in range(1, len(stages)):
                    gap = gaps[si-1] if si-1 < len(gaps) else 25
                    fnd = False
                    for bi in range(c+1, c+gap+1):
                        if bi in sbb:
                            for cand in sbb[bi]:
                                if cand.type in ss[si] and cand not in chain:
                                    chain.append(cand); c = bi; fnd = True; break
                        if fnd: break
                    if not fnd: ok = False; break
                if ok and len(chain) == len(stages):
                    zone = chain[-1]  # last = demand zone
                    liq = chain[0]    # first = liquidity
                    seqs.append({
                        'pattern': pn,
                        'bar': zone.idx,
                        'zone_type': zone.type,
                        'zone_price': zone.price,
                        'zone_low': zone.lower,
                        'zone_up': zone.upper,
                        'liq_type': liq.type,
                        'liq_bar': liq.idx,
                        'liq_price': liq.price,
                        'chain_types': [s.type for s in chain],
                        'n_chain': len(chain),
                    })
    seen = set(); unique = []
    for s in sorted(seqs, key=lambda x: x['bar']):
        if s['bar'] not in seen:
            seen.add(s['bar'])
            unique.append(s)
    return unique

# ═══ MAIN ═══
t0 = time.time()
daily_files = sorted(KLINE.glob('*_daily_300.json'))
picks = []
stats = defaultdict(lambda: {'count': 0, 'stocks': set()})

for fi, df in enumerate(daily_files):
    sym = df.stem.replace('_daily_300', '')
    try:
        daily = json.loads(df.read_bytes())
        if len(daily) < 50: continue
    except: continue
    
    # Weekly trend (synthesize if needed)
    weekly_path = KLINE / f'{sym}_weekly_200.json'
    weekly = None
    if weekly_path.exists():
        try:
            weekly = json.loads(weekly_path.read_bytes())
        except: pass
    if weekly is None or len(weekly) < 20:
        weekly = daily_to_weekly(daily)
    
    w_trend, w_tc = weekly_smc_trend(weekly)
    if w_trend != 'bullish':
        continue  # Only bullish for monitoring
    
    # Daily signals + L→D sequences
    sigs, st, _, _ = detect_all_signals_v20(daily)
    sequences = detect_sequences(sigs)
    if not sequences: continue
    
    # Get recent valid sequences (last 30 days, need room for T+1 entry)
    n = len(daily)
    from datetime import datetime, timedelta
    last_date = datetime.strptime(str(daily[-1].get('t', daily[-1].get('date', '')))[:8], '%Y%m%d')
    cutoff = last_date - timedelta(days=3)
    
    recent_seqs = []
    for seq in reversed(sequences):
        sig_date_str = str(daily[seq['bar']].get('t', daily[seq['bar']].get('date', '')))[:8]
        try:
            sig_date = datetime.strptime(sig_date_str, '%Y%m%d')
            if sig_date < cutoff:
                continue
        except: pass
        if seq['bar'] < n - 3:  # need at least 3 bars ahead for T+1+forward
            recent_seqs.append(seq)
    
    if not recent_seqs: continue
    
    for last_seq in recent_seqs:
        # Entry: T+1 = next bar open
        entry_bar = last_seq['bar'] + 1
        if entry_bar >= n: continue
        entry_price = daily[entry_bar]['o']
        signal_date = str(daily[last_seq['bar']].get('t', daily[last_seq['bar']].get('date', '')))[:8]
        
        # SL = zone lower boundary (not too far: max 3% below entry)
        zone_sl = last_seq['zone_low'] if last_seq['zone_low'] > 0 else entry_price * 0.97
        sl_distance = (entry_price - zone_sl) / entry_price
        if sl_distance > 0.03:
            zone_sl = entry_price * 0.97  # cap at 3% below entry
        elif sl_distance < 0.005:
            zone_sl = entry_price * 0.995  # floor at 0.5%
        sl_price = round(zone_sl, 2)
        tp_price = round(entry_price * 1.03, 2)
        
        sd = dna.get(sym, {})
        has_60min = (KLINE_60 / f'{sym}_60min_200.json').exists()
        
        picks.append({
            'symbol': sym,
            'pattern': last_seq['pattern'],
            'chain': '→'.join(last_seq['chain_types']),
            'signal_date': signal_date,
            'entry_date': signal_date,
            'entry_price': entry_price,
            'signal_price': last_seq['zone_price'],
            'sl': sl_price,
            'tp': tp_price,
            'zone_bar': last_seq['bar'],
            'hist_wr': sd.get('v11_wr', 0),
            'ob_wr': sd.get('ob_wr', 0),
            'hist_trades': sd.get('v11_trades', 0),
            'trend': w_trend,
            'has_60min': has_60min,
            'type': 'combo',
        })
        
        stats[last_seq['pattern']]['count'] += 1
        stats[last_seq['pattern']]['stocks'].add(sym)
    
    if (fi+1) % 1000 == 0:
        print(f"  [{fi+1}/{len(daily_files)}] {time.time()-t0:.0f}s picks={len(picks)}")

elapsed = time.time() - t0

# ═══ SAVE ═══
output = {
    'meta': {
        'version': 'L→D v1.0',
        'date': time.strftime('%Y-%m-%d %H:%M'),
        'total_picks': len(picks),
        'elapsed': round(elapsed, 1),
    },
    'stats': {p: {'count': s['count'], 'stocks': len(s['stocks'])} for p, s in stats.items()},
    'picks': picks,
}

pick_path = OUT / 'LD_picks.json'
json.dump(output, open(pick_path, 'w'), ensure_ascii=False)

print(f"\n{'='*60}")
print(f"  L→D 信号扫描完成 — {elapsed:.0f}s")
print(f"  Total picks: {len(picks)}")
for p, s in sorted(stats.items(), key=lambda x: -x[1]['count']):
    print(f"  {p:8s}: {s['count']:>4d}个信号, {len(s['stocks']):>4d}只股票")
print(f"\n  保存: {pick_path}")
