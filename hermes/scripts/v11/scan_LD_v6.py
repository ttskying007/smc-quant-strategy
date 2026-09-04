#!/usr/bin/env python3
"""
SMC V6 — OB上下文矩阵 + 全信号组合 + Pinbar POI
================================================
核心改进:
  1. 修复break bug: 扫描全窗口不提前break
  2. OB上下文增强: 每个OB标注前序LIQ/STRUCT(1-10bar)
  3. 新增Pinbar_Bull作为POI
  4. L2组合: START→ZONE (ZONE含OB/FVG/Pinbar), 与L1各自独立去重
  5. OB→Forward追踪: OB后1-5bar出现的信号

架构: 
  POI: OB_Bull / FVG_Bull / Pinbar_Bull
  CTX: LIQ(Sweep_SSL,EQL) / STRUCT(CHOCH,BOS,MSS)
  矩阵: CTX × POI 全部组合 + OB单信号(+上下文标签)
"""
import json, sys, time, math
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20, SwingPoint, Signal
from v11.v19_backtest_engine import find_tps, find_sls

KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v21')
OUT.mkdir(exist_ok=True)

# ═══ 信号定义 ═══
LIQ_TYPES = ['Sweep_SSL', 'Sweep_BSL', 'EQL']
STRUCT_TYPES = ['CHOCH_Bull','BOS_Bull','MSS_Bull']
ZONE_TYPES = ['OB_Bull', 'FVG_Bull']  # Pinbar is entry confirmation at PD Array, not standalone zone  # Engulf/Harami/Pierce are entry confirmations, not standalone zones
ALL_START = LIQ_TYPES + STRUCT_TYPES
# Zone-type adaptive gap windows (backtest-optimized)
ZONE_GAP_MAX = {'OB_Bull': 10, 'FVG_Bull': 7}
TP_CAP = 1.05

# ═══ Pinbar Detection (V8: Fixed 4 bugs, SMC-standard) ═══
def detect_pinbars(daily):
    """SMC Pinbar: entry confirmation at PD Arrays (OB/FVG), NOT standalone zone.
    
    Fixes from V7.5:
    1. Removed c<=o filter — valid hammers can have bearish body (close < open)
    2. Close position check: must be near HIGH (top 30% of range), not just above midpoint
    3. Added Shooting Star (bearish pinbar) detection
    4. Note: PD Array context check is done by caller (scan_LD_v6), not here —
       isolated pinbars without OB/FVG nearby are unreliable
    
    SMC Pinbar criteria:
    - Bull (Hammer): long lower wick > body×2.5, wick > range×0.6, tiny upper wick < range×0.15
    - Bear (Shooting Star): long upper wick > body×2.5, wick > range×0.6, tiny lower wick < range×0.15
    """
    results = []
    for i in range(20, len(daily)):
        b = daily[i]; o, h, l, c = b['o'], b['h'], b['l'], b['c']
        if h == l: continue
        range_hl = h - l
        if range_hl == 0: continue
        
        body_abs = abs(c - o)
        lower_wick = min(o, c) - l
        upper_wick = h - max(o, c)
        
        # --- Bullish Pinbar (Hammer) ---
        # Long lower wick, tiny upper wick, close near HIGH
        if lower_wick > body_abs * 2.5 and lower_wick > range_hl * 0.6 and upper_wick < range_hl * 0.15:
            close_in_upper = c > (h - range_hl * 0.3)  # close in top 30% of range
            if close_in_upper:
                results.append(Signal('Pinbar_Bull', i, 'bull', lower=l, upper=h, price=c,
                                      strength=lower_wick/range_hl, confidence=0.6))
        
        # --- Bearish Pinbar (Shooting Star) ---
        # Long upper wick, tiny lower wick, close near LOW
        elif upper_wick > body_abs * 2.5 and upper_wick > range_hl * 0.6 and lower_wick < range_hl * 0.15:
            close_in_lower = c < (l + range_hl * 0.3)  # close in bottom 30% of range
            if close_in_lower:
                results.append(Signal('Pinbar_Bear', i, 'bear', lower=l, upper=h, price=c,
                                      strength=upper_wick/range_hl, confidence=0.6))
    return results

# ═══ FVG回补率 ═══
def detect_fvg_fills(daily):
    sigs, _, _, _ = detect_all_signals_v20(daily)
    fvgs = [s for s in sigs if 'FVG' in s.type]
    if len(fvgs) < 5: return 0, 0
    filled = 0
    for fvg in fvgs:
        if not hasattr(fvg,'lower') or not hasattr(fvg,'upper'): continue
        gap_low, gap_high = fvg.lower, fvg.upper
        if gap_low >= gap_high: continue
        for k in range(fvg.idx+2, min(fvg.idx+22, len(daily))):
            c = daily[k]['c']
            if gap_low < c < gap_high: filled += 1; break
    return filled, len(fvgs)

def market_state(fill_c, fvg_c):
    if fvg_c < 5: return 'transition'
    rate = fill_c / fvg_c
    if rate >= 0.6: return 'mean_reversion'
    if rate <= 0.4: return 'expansion'
    return 'transition'

# ═══ Score ═══
def calc_score(sym, signal_type, ms, ctx_count=0, gap=0):
    """SignalScore [0, 1]"""
    s = 0.0
    trend = dna.get(sym, {}).get('trend','?')
    if trend == 'bullish': s += 0.15
    
    if signal_type == 'OB_Bull':
        s += 0.25  # Base OB
        if ctx_count >= 2: s += 0.20  # Multiple context
        elif ctx_count == 1: s += 0.10  # Single context
    elif 'FVG' in signal_type:
        s += 0.10
        if gap <= 5: s += 0.15
        if ms == 'mean_reversion': s += 0.25
        elif ms == 'transition': s += 0.10
    elif 'Pinbar' in signal_type:
        s += 0.15
    
    if ms == 'mean_reversion': s += 0.05
    if gap <= 3: s += 0.10
    
    return round(min(1.0, s), 2)

# ═══ Weekly trend ═══
def weekly_trend(weekly):
    if len(weekly) < 20: return 'neutral'
    sigs, st, _, _ = detect_all_signals_v20(weekly)
    tc = st['type_counts']
    cb = tc.get('CHOCH_Bull',0); cbr = tc.get('CHOCH_Bear',0)
    bb = tc.get('BOS_Bull',0); bbr = tc.get('BOS_Bear',0)
    last_ch = [s for s in sigs if 'CHOCH' in s.type]
    ld = 'bull' if last_ch and 'Bull' in last_ch[-1].type else ('bear' if last_ch and 'Bear' in last_ch[-1].type else None)
    if ld == 'bull' and cb+bb >= cbr+bbr: return 'bullish'
    if ld == 'bear' and cbr+bbr > cb+bb: return 'bearish'
    if cb+bb > (cbr+bbr)*1.5: return 'bullish'
    if cbr+bbr > (cb+bb)*1.5: return 'bearish'
    return 'neutral'

def daily_to_weekly(daily):
    w = []
    for i in range(0, len(daily), 5):
        chunk = daily[i:i+5]
        if len(chunk) >= 3:
            w.append({'o':chunk[0]['o'],'h':max(b['h'] for b in chunk),
                      'l':min(b['l'] for b in chunk),'c':chunk[-1]['c']})
    return w

# ═══ Load DNA ═══
DNA = OUT / 'stock_dna_v11.json'
dna = json.loads(DNA.read_bytes()) if DNA.exists() else {}

# ═══ MAIN ═══
t0 = time.time()
files = sorted(KLINE.glob('*_daily_300.json'))
picks = []
market_states = {}
combo_stats = Counter()

for fi, f in enumerate(files):
    sym = f.stem.replace('_daily_300', '')
    try:
        daily = json.loads(f.read_bytes())
        if len(daily) < 50: continue
    except: continue
    
    weekly_path = KLINE / f'{sym}_weekly_200.json'
    weekly = None
    if weekly_path.exists():
        try: weekly = json.loads(weekly_path.read_bytes())
        except: pass
    if weekly is None or len(weekly) < 20:
        weekly = daily_to_weekly(daily)
    w_trend = weekly_trend(weekly)
    if w_trend != 'bullish': continue
    
    sigs, st, _, swings_dict = detect_all_signals_v20(daily)
    n = len(daily)
    
    # 加Pinbar
    pinbars = detect_pinbars(daily)
    all_sigs = list(sigs) + pinbars
    
    sbb = defaultdict(list)
    for s in all_sigs: sbb[s.idx].append(s)
    
    fill_c, fvg_c = detect_fvg_fills(daily)
    ms = market_state(fill_c, fvg_c)
    market_states[sym] = {'state': ms, 'fill_rate': round(fill_c/fvg_c,2) if fvg_c>0 else 0}
    
    candidates = []
    
    # ── 逐bar扫描 ──
    for i in sorted(sbb.keys()):
        types_i = [s.type for s in sbb[i]]
        
        # ═══ OB_Bull: L1 + 上下文 (回调入场) ═══
        if 'OB_Bull' in types_i:
            ob_sig = next(s for s in sbb[i] if s.type == 'OB_Bull')
            entry_bar = i + 1
            if entry_bar >= n - 2: continue
            # 回调入场: 目标价=zone_low, 等价格回落才买入
            zone_low_ob = ob_sig.lower if hasattr(ob_sig,'lower') and ob_sig.lower > 0 else ob_sig.price * 0.99
            ep = zone_low_ob
            if ep == 0: continue
            
            # 前序上下文: 1-10 bar前的LIQ/STRUCT
            ctx_signals = []
            for prev in range(max(0, i-10), i):
                if prev in sbb:
                    for s in sbb[prev]:
                        if s.type in ALL_START:
                            ctx_signals.append({'type': s.type, 'gap': i-prev})
            
            ctx_types = set(c['type'] for c in ctx_signals)
            ctx_count = len(ctx_signals)
            
            # OB→Forward: 1-5 bar后信号
            fw_signals = []
            for fw in range(i+1, min(i+6, n)):
                if fw in sbb:
                    for s in sbb[fw]:
                        if s.type in ALL_START + ['FVG_Bull','Pinbar_Bull']:
                            fw_signals.append({'type': s.type, 'gap': fw-i})
            
            tp, _, _ = find_tps(ep, sigs, swings_dict, daily)
            sl, _, _ = find_sls(ep, sigs, swings_dict, daily)
            if tp is None: tp = ep * TP_CAP
            if tp > ep * TP_CAP: tp = ep * TP_CAP
            if sl is None: sl = ep * 0.97
            
            score = calc_score(sym, 'OB_Bull', ms, ctx_count)
            candidates.append({
                'tier': 'L1', 'signal': 'OB_Bull',
                'ctx': [{'type': t['type'], 'gap': t['gap']} for t in ctx_signals],
                'ctx_count': ctx_count,
                'ctx_types': sorted(ctx_types),
                'fw': [{'type': t['type'], 'gap': t['gap']} for t in fw_signals],
                'score': score,
                'ep': ep, 'sl': round(sl,2), 'tp': round(tp,2),
                'entry_bar': entry_bar, 'zone_bar': i, 'zone_type': 'OB_Bull',
                'zone_low': zone_low_ob, 'entry_mode': 'retrace',
                'gap': 0, 'state': ms, 'trend': w_trend,
                'fill_rate': round(fill_c/fvg_c,2) if fvg_c>0 else 0,
                'confirmed_at': ob_sig.confirmed_at if hasattr(ob_sig,'confirmed_at') else entry_bar,
            })
        
        # ═══ L2: START→ZONE 全组合(不限OB) ═══
        start_sigs = [s for s in sbb[i] if s.type in ALL_START]
        for start_s in start_sigs:
            best_zone = None; best_gap = 99; best_score = -99
            # Scan full 1-10 window, but filter per zone type
            for j in range(i+1, min(i+11, n)):
                if j not in sbb: continue
                zone_cands = [s for s in sbb[j] if s.type in ZONE_TYPES]
                if not zone_cands: continue
                for z in zone_cands:
                    gap = j - i
                    max_gap = ZONE_GAP_MAX.get(z.type, 10)
                    if gap > max_gap: continue  # 超出此zone类型的gap上限
                    z_score = (gap * -1.5) + (3 if z.type=='OB_Bull' else 1)
                    if z_score > best_score:
                        best_score = z_score; best_zone = (z, j)
                # 不break — 继续扫描后续bar
            
            if not best_zone: continue
            zone, j = best_zone
            gap = j - i
            entry_bar = j + 1
            if entry_bar >= n - 2: continue
            
            # Entry mode: retrace for OB/Pinbar, immediate for FVG
            if zone.type == 'OB_Bull':
                zone_low_l2 = zone.lower if hasattr(zone,'lower') and zone.lower > 0 else zone.price * 0.99
                ep = zone_low_l2
                entry_mode = 'retrace'
            else:
                ep = daily[entry_bar]['o']
                zone_low_l2 = ep  # FVG: zone_low = entry for reference
                entry_mode = 'immediate'
            if ep == 0: continue
            
            tp, _, _ = find_tps(ep, sigs, swings_dict, daily)
            sl, _, _ = find_sls(ep, sigs, swings_dict, daily)
            if tp is None: tp = ep * TP_CAP
            if tp > ep * TP_CAP: tp = ep * TP_CAP
            if sl is None: sl = ep * 0.97
            
            tpd = abs(tp-ep)/ep*100; sld = abs(sl-ep)/ep*100
            if sld == 0 or tpd/sld < 1.0: continue
            
            sig_name = f'{start_s.type}→{zone.type}'
            
            # Market state gate: non-OB combos only in MR
            is_ob_zone = (zone.type == 'OB_Bull')
            l2_ok = is_ob_zone or (ms == 'mean_reversion')
            if not l2_ok: continue
            
            score = calc_score(sym, sig_name, ms, gap=gap)
            candidates.append({
                'tier': 'L2', 'signal': sig_name,
                'score': score,
                'ep': ep, 'sl': round(sl,2), 'tp': round(tp,2),
                'entry_bar': entry_bar, 'zone_bar': j, 'zone_type': zone.type,
                'zone_low': zone_low_l2, 'entry_mode': entry_mode,
                'gap': gap, 'state': ms, 'trend': w_trend,
                'fill_rate': round(fill_c/fvg_c,2) if fvg_c>0 else 0,
                'start_type': start_s.type, 'start_bar': i,
            })
    
    # ═══ Dedup: 同一entry_bar, L1优先, 同tier选高score ═══
    candidates.sort(key=lambda x: (x['entry_bar'], 0 if x['tier']=='L1' else 1, -x['score']))
    seen = set()
    for c in candidates:
        key = (sym, c['entry_bar'])
        if key in seen: continue
        seen.add(key)
        
        sig_date = str(daily[c['entry_bar']].get('t',''))[:8]
        
        pick = {
            'symbol': sym,
            'tier': c['tier'],
            'signal': c['signal'],
            'score': c['score'],
            'state': c['state'],
            'fill_rate': c['fill_rate'],
            'signal_date': sig_date,
            'entry_date': sig_date,
            'entry_price': c['ep'],
            'sl': c['sl'],
            'tp': c['tp'],
            'zone_bar': c['zone_bar'],
            'zone_type': c['zone_type'],
            'zone_low': c.get('zone_low', c['ep']),
            'entry_mode': c.get('entry_mode', 'immediate'),
            'gap': c['gap'],
            'trend': c['trend'],
            'confirmed_at': c.get('confirmed_at', c['entry_bar']),
        }
        
        if c['tier'] == 'L1':
            pick['ctx_count'] = c['ctx_count']
            pick['ctx_types'] = c['ctx_types']
            if c['fw']:
                pick['fw_signals'] = [f"{x['type']}(+{x['gap']})" for x in c['fw'][:3]]
        else:
            pick['start_type'] = c['start_type']
            pick['start_bar'] = c['start_bar']
        
        picks.append(pick)
        combo_stats[c['signal']] += 1
    
    if (fi+1) % 1000 == 0:
        print(f"  [{fi+1}/{len(files)}] {time.time()-t0:.0f}s picks={len(picks)}")

# ═══ OUTPUT ═══
elapsed = time.time() - t0
l1_count = sum(1 for p in picks if p['tier'] == 'L1')
l2_count = sum(1 for p in picks if p['tier'] == 'L2')
with_ctx = sum(1 for p in picks if p['tier']=='L1' and p.get('ctx_count',0) > 0)
with_fw = sum(1 for p in picks if p['tier']=='L1' and p.get('fw_signals'))

print(f"\n{'='*70}")
print(f"  SMC V6 — OB上下文矩阵 + 全信号组合 — {elapsed:.0f}s")
print(f"{'='*70}")
print(f"  Total picks: {len(picks)} (L1={l1_count}, L2={l2_count})")
print(f"  L1 with context: {with_ctx} ({with_ctx/l1_count*100:.0f}%)" if l1_count else "")
print(f"  L1 with forward: {with_fw} ({with_fw/l1_count*100:.0f}%)" if l1_count else "")

print(f"\n  Signal Matrix:")
for sig, n in combo_stats.most_common():
    marker = "⭐" if 'OB_Bull' in sig else ("📊" if 'FVG' in sig else "📌")
    print(f"    {marker} {sig:<35s} {n:>5d}")

# By state
state_counts = Counter(p['state'] for p in picks)
print(f"\n  By State: {dict(state_counts)}")

# By trend
trend_counts = Counter(p['trend'] for p in picks)
print(f"  By Trend: {dict(trend_counts)}")

# Data file
output = {
    'meta': {
        'version': 'V6 Context-Matrix',
        'date': time.strftime('%Y-%m-%d %H:%M'),
        'elapsed': round(elapsed, 1),
        'l1': l1_count, 'l2': l2_count, 'total': len(picks),
        'l1_with_ctx': with_ctx, 'l1_with_fw': with_fw,
    },
    'market_states': market_states,
    'combo_summary': dict(combo_stats),
    'picks': picks,
}

out_file = OUT / 'LD_picks_v6.json'
json.dump(output, open(out_file, 'w'), ensure_ascii=False)
print(f"\n  保存: {out_file} ({out_file.stat().st_size//1024}KB)")
