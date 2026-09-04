#!/usr/bin/env python3
"""
V19 SMC信号引擎 — LuxAlgo + SMC 2026 混合架构

核心架构变革：
1. 摆动检测: LuxAlgo leg() — break N-bar high/low 确认真结构点
2. HH/HL/LL/LH: 内部标注 — 每个摆动点比较前一摆动标记结构类型
3. CHOCH/BOS: LuxAlgo crossover/crossunder close vs pivot price
4. OB: LuxAlgo — 在CHOCH/BOS时从pivot回溯到当前bar找OB（不在预设时扫描）
5. Sweep: ICT标准 — 突破摆动点+反转
6. MSS: LuxAlgo内部结构 — 小leg size的crossover
7. FVG: SMC 2026纯gap
8. EQL/EQH: LuxAlgo相邻pivot比较
9. BPR: SMC 2026多区域重叠
"""
import math, logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

log = logging.getLogger('smc_v19')

@dataclass
class Signal:
    type: str; idx: int; direction: str; price: float
    upper: float = 0.0; lower: float = 0.0
    strength: float = 0.0; confidence: float = 0.0
    timeframe: str = 'daily'; confirmed_at: int = 0
    volume_ratio: float = 1.0; grade: int = 1
    trend_aligned: bool = False
    metadata: Dict = field(default_factory=dict)
    def to_dict(self) -> Dict:
        return {'type':self.type,'idx':self.idx,'direction':self.direction,
                'price':round(self.price,4),'upper':round(self.upper,4),
                'lower':round(self.lower,4),'strength':round(self.strength,2),
                'confidence':round(self.confidence,3),'timeframe':self.timeframe,
                'confirmed_at':self.confirmed_at,'volume_ratio':round(self.volume_ratio,2),
                'grade':self.grade,'trend_aligned':self.trend_aligned,'metadata':self.metadata}

# ════════════════════════════════════════════
# 0. UTILITY: ATR calculation
# ════════════════════════════════════════════

def _calc_atr(ohlcv, length=14):
    n = min(length, len(ohlcv))
    trs = []
    for i in range(max(1,len(ohlcv)-n), len(ohlcv)):
        h,l,pc = ohlcv[i]['h'],ohlcv[i]['l'],ohlcv[i-1]['c']
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return sum(trs)/len(trs) if trs else 1.0

# ════════════════════════════════════════════
# 1. LUXALGO LEG DETECTION — TRUE SWING POINTS
# ════════════════════════════════════════════

class SwingPoint:
    def __init__(self, bar_idx, price, ptype, label=''):
        self.bar_idx = bar_idx
        self.price = price
        self.type = ptype  # 'H' or 'L'
        self.label = label  # 'HH','HL','LH','LL'
        self.crossed = False

def detect_leg_swings(ohlcv, leg_size=20) -> Tuple[List[SwingPoint], Dict]:
    """
    LuxAlgo leg(): high[leg_size] > ta.highest(leg_size) → new bearish leg (swing high)
                   low[leg_size] < ta.lowest(leg_size) → new bullish leg (swing low)
    
    Returns list of confirmed SwingPoint objects with HH/HL/LL/LH labels.
    """
    n = len(ohlcv)
    if n < leg_size * 2:
        return [], {'highs': [], 'lows': []}
    
    # Track leg state
    leg = 0  # 0=neutral, 1=bullish leg, -1=bearish leg
    prev_leg = 0
    swings = []
    last_high = None
    last_low = None
    
    for i in range(leg_size, n):
        bar = ohlcv[i]
        # LuxAlgo: high[size] > ta.highest(size)
        # high[leg_size] = bar at i-leg_size
        # ta.highest(leg_size) = max of last leg_size bars (i-leg_size+1 to i)
        pivot_bar = i - leg_size
        pivot_high = ohlcv[pivot_bar]['h']
        pivot_low = ohlcv[pivot_bar]['l']
        
        recent_highs = [ohlcv[j]['h'] for j in range(pivot_bar+1, i+1)]
        recent_lows = [ohlcv[j]['l'] for j in range(pivot_bar+1, i+1)]
        
        if pivot_high > max(recent_highs):
            leg = -1  # bearish leg → swing high confirmed
        elif pivot_low < min(recent_lows):
            leg = 1   # bullish leg → swing low confirmed
        
        # New leg detected   
        if leg != 0 and leg != prev_leg:
            if leg == -1:  # New swing high at pivot_bar
                price = ohlcv[pivot_bar]['h']
                label = ''
                if last_high is not None:
                    label = 'HH' if price > last_high.price else 'LH'
                else:
                    label = 'HH'
                sp = SwingPoint(pivot_bar, price, 'H', label)
                sp.last_price = last_high.price if last_high else None
                last_high = sp
                swings.append(sp)
            else:  # New swing low
                price = ohlcv[pivot_bar]['l']
                label = ''
                if last_low is not None:
                    label = 'LL' if price < last_low.price else 'HL'
                else:
                    label = 'LL'
                sp = SwingPoint(pivot_bar, price, 'L', label)
                sp.last_price = last_low.price if last_low else None
                last_low = sp
                swings.append(sp)
        
        prev_leg = leg
    
    highs = [{'bar_idx': s.bar_idx, 'price': s.price, 'label': s.label} for s in swings if s.type == 'H']
    lows = [{'bar_idx': s.bar_idx, 'price': s.price, 'label': s.label} for s in swings if s.type == 'L']
    
    return swings, {'highs': highs, 'lows': lows}

# ════════════════════════════════════════════
# 2. CHOCH/BOS — LuxAlgo crossover/crossunder
# ════════════════════════════════════════════

def detect_choch_bos_v19(ohlcv, swings, trend_bias=0):
    """
    LuxAlgo displayStructure():
    For EACH uncrossed pivot, check crossover/crossunder.
    After detection: pivot.crossed = true, trend_bias updates.
    """
    n = len(ohlcv)
    signals = []
    
    for i in range(1, n):
        close = ohlcv[i]['c']
        prev_close = ohlcv[i-1]['c']
        
        # Check all uncrossed swing highs
        for sh in swings:
            if sh.type != 'H' or sh.crossed: continue
            if sh.bar_idx >= i: continue  # future swing
            
            if prev_close <= sh.price and close > sh.price:
                tag = 'CHOCH_Bull' if trend_bias == -1 else 'BOS_Bull'
                signals.append(Signal(
                    type=tag, idx=i, direction='bull',
                    price=sh.price, upper=close,
                    strength=7.0 if 'CHOCH' in tag else 5.0,
                    confidence=0.85 if 'CHOCH' in tag else 0.7,
                    metadata={'swing_bar': sh.bar_idx, 'swing_price': sh.price,
                              'swing_label': sh.label, 'trend_before': trend_bias}
                ))
                sh.crossed = True
                trend_bias = 1
                break  # one signal per bar
        
        if any(s.type in ('CHOCH_Bull','BOS_Bull') and s.idx == i for s in signals):
            continue  # already labeled this bar
        
        # Check all uncrossed swing lows
        for sl in swings:
            if sl.type != 'L' or sl.crossed: continue
            if sl.bar_idx >= i: continue
            
            if prev_close >= sl.price and close < sl.price:
                tag = 'CHOCH_Bear' if trend_bias == 1 else 'BOS_Bear'
                signals.append(Signal(
                    type=tag, idx=i, direction='bear',
                    price=sl.price, lower=close,
                    strength=7.0 if 'CHOCH' in tag else 5.0,
                    confidence=0.85 if 'CHOCH' in tag else 0.7,
                    metadata={'swing_bar': sl.bar_idx, 'swing_price': sl.price,
                              'swing_label': sl.label, 'trend_before': trend_bias}
                ))
                sl.crossed = True
                trend_bias = -1
                break
    
    return signals, trend_bias

# ════════════════════════════════════════════
# 3. OB — LuxAlgo: store at CHOCH/BOS moment
# ════════════════════════════════════════════

def detect_ob_luxalgo(ohlcv, swings, choch_bos_signals):
    """
    LuxAlgo storeOrdeBlock():
    - On CHOCH/BOS bullish: find MIN low between pivot.barIndex and current bar_index
    - On CHOCH/BOS bearish: find MAX high between pivot.barIndex and current bar_index
    - That bar is the Order Block
    
    Also locate OBs at swing points (SMC 2026 approach for standalone detection).
    """
    signals = []
    
    for cs in choch_bos_signals:
        meta = cs.metadata
        pivot_bar = meta.get('swing_bar', cs.idx - 10)
        current_bar = cs.idx
        
        if 'Bull' in cs.type:
            # Bullish CHOCH/BOS: find lowest low between pivot and current bar
            best_bar = pivot_bar
            best_low = float('inf')
            for i in range(pivot_bar, min(current_bar + 1, len(ohlcv))):
                if ohlcv[i]['l'] < best_low:
                    best_low = ohlcv[i]['l']
                    best_bar = i
            if best_bar < len(ohlcv) and best_low < float('inf'):
                bar = ohlcv[best_bar]
                signals.append(Signal(
                    type='OB_Bull', idx=best_bar, direction='bull',
                    price=best_low, upper=bar['h'], lower=bar['l'],
                    strength=6.0, confidence=0.75,
                    confirmed_at=cs.idx,
                    metadata={'pivot_bar': pivot_bar, 'choch_bar': current_bar,
                              'method': 'luxalgo'}
                ))
        else:
            # Bearish CHOCH/BOS: find highest high between pivot and current bar
            best_bar = pivot_bar
            best_high = -float('inf')
            for i in range(pivot_bar, min(current_bar + 1, len(ohlcv))):
                if ohlcv[i]['h'] > best_high:
                    best_high = ohlcv[i]['h']
                    best_bar = i
            if best_bar < len(ohlcv):
                bar = ohlcv[best_bar]
                signals.append(Signal(
                    type='OB_Bear', idx=best_bar, direction='bear',
                    price=best_high, upper=bar['h'], lower=bar['l'],
                    strength=6.0, confidence=0.75,
                    confirmed_at=cs.idx,
                    metadata={'pivot_bar': pivot_bar, 'choch_bar': current_bar,
                              'method': 'luxalgo'}
                ))
    
    # Also do SMC 2026 standalone OB for swing points (without CHOCH/BOS)
    smc_obs = detect_ob_smc2026(ohlcv, swings)
    # Merge, dedup by bar index
    used_idx = set()
    for s in signals:
        used_idx.add((s.type, s.idx))
    for s in smc_obs:
        if (s.type, s.idx) not in used_idx:
            signals.append(s)
    
    return signals

def detect_ob_smc2026(ohlcv, swings):
    """SMC 2026 OB: from swing, scan backward for first opposite candle with displacement."""
    signals = []
    atr = _calc_atr(ohlcv, 14)
    avg_price = sum(b['c'] for b in ohlcv[-50:]) / 50 if len(ohlcv) >= 50 else 100
    
    for sp in swings:
        if sp.type == 'L':  # Swing low → Bullish OB
            sl_bar = sp.bar_idx
            sl_price = sp.price
            found = False
            for i in range(7, 18):
                idx = sl_bar - i
                if idx < 0: break
                bar = ohlcv[idx]
                if bar['c'] < bar['o']:  # Bearish candle before bullish impulse
                    disp = sl_price - bar['l']
                    rng = bar['h'] - bar['l']
                    if rng > 0 and disp > rng * 0.6:  # A-share adapted
                        strength = min(10.0, disp/atr*2 + rng/atr*1.5)
                        if strength >= 2.0:
                            signals.append(Signal(
                                type='OB_Bull', idx=idx, direction='bull',
                                price=bar['l'], upper=bar['h'], lower=bar['l'],
                                strength=round(strength,1), confidence=0.7,
                                confirmed_at=sl_bar,
                                metadata={'swing_bar': sl_bar, 'swing_price': sl_price,
                                          'swing_label': sp.label, 'displacement': round(disp,4)}
                            ))
                            found = True
                            break
        elif sp.type == 'H':  # Swing high → Bearish OB
            sh_bar = sp.bar_idx
            sh_price = sp.price
            found = False
            for i in range(7, 18):
                idx = sh_bar - i
                if idx < 0: break
                bar = ohlcv[idx]
                if bar['c'] > bar['o']:  # Bullish candle before bearish impulse
                    disp = bar['h'] - sh_price
                    rng = bar['h'] - bar['l']
                    if rng > 0 and disp > rng * 0.6:
                        strength = min(10.0, disp/atr*2 + rng/atr*1.5)
                        if strength >= 2.0:
                            signals.append(Signal(
                                type='OB_Bear', idx=idx, direction='bear',
                                price=bar['h'], upper=bar['h'], lower=bar['l'],
                                strength=round(strength,1), confidence=0.7,
                                confirmed_at=sh_bar,
                                metadata={'swing_bar': sh_bar, 'swing_price': sh_price,
                                          'swing_label': sp.label, 'displacement': round(disp,4)}
                            ))
                            found = True
                            break
    return signals

# ════════════════════════════════════════════
# 4. FVG — SMC 2026 pure gap
# ════════════════════════════════════════════

def detect_fvg_v19(ohlcv, atr_mult=0.5, min_strength=2.5):
    n = len(ohlcv)
    if n < 3: return []
    atr = _calc_atr(ohlcv, 14)
    signals = []
    for i in range(2, n):
        if ohlcv[i]['l'] > ohlcv[i-2]['h']:
            gap_top, gap_bot = ohlcv[i]['l'], ohlcv[i-2]['h']
            gap = gap_top - gap_bot
            if gap >= atr * atr_mult:
                strength = min(10.0, gap/atr*3)
                if strength >= min_strength:
                    signals.append(Signal(type='FVG_Bull', idx=i-1, direction='bull',
                        price=gap_bot, upper=gap_top, lower=gap_bot,
                        strength=round(strength,2), confidence=0.75, confirmed_at=i,
                        metadata={'gap_size': round(gap,4)}))
        if ohlcv[i]['h'] < ohlcv[i-2]['l']:
            gap_top, gap_bot = ohlcv[i-2]['l'], ohlcv[i]['h']
            gap = gap_top - gap_bot
            if gap >= atr * atr_mult:
                strength = min(10.0, gap/atr*3)
                if strength >= min_strength:
                    signals.append(Signal(type='FVG_Bear', idx=i-1, direction='bear',
                        price=gap_top, upper=gap_top, lower=gap_bot,
                        strength=round(strength,2), confidence=0.75, confirmed_at=i,
                        metadata={'gap_size': round(gap,4)}))
    return signals

# ════════════════════════════════════════════
# 5. SWEEP — ICT: break swing + reverse
# ════════════════════════════════════════════

def detect_sweep_v19(ohlcv, swings):
    """Sweep: bar pierces a prior swing point then closes back inside."""
    n = len(ohlcv)
    if n < 10: return []
    avg_price = sum(b['c'] for b in ohlcv[-50:])/50 if len(ohlcv)>=50 else 100
    
    signals = []
    swing_highs = [(s.bar_idx, s.price) for s in swings if s.type == 'H']
    swing_lows = [(s.bar_idx, s.price) for s in swings if s.type == 'L']
    
    for i in range(5, n):
        bar = ohlcv[i]
        min_pen = max(_calc_atr(ohlcv,14)*0.15, avg_price*0.001)
        
        # BSL sweep: pierces prior high then closes below
        for sh_idx, sh_price in swing_highs:
            if sh_idx >= i-30 and sh_idx < i and bar['h'] > sh_price + min_pen:
                if bar['c'] < sh_price:
                    signals.append(Signal(type='Sweep_BSL', idx=i, direction='bear',
                        price=sh_price, strength=6.0, confidence=0.7,
                        metadata={'swept_level': sh_price, 'level_bar': sh_idx}))
                    break
        
        # SSL sweep: pierces prior low then closes above
        for sl_idx, sl_price in swing_lows:
            if sl_idx >= i-30 and sl_idx < i and bar['l'] < sl_price - min_pen:
                if bar['c'] > sl_price:
                    signals.append(Signal(type='Sweep_SSL', idx=i, direction='bull',
                        price=sl_price, strength=6.0, confidence=0.7,
                        metadata={'swept_level': sl_price, 'level_bar': sl_idx}))
                    break
    return signals

# ════════════════════════════════════════════
# 6. MSS — LuxAlgo internal structure
# ════════════════════════════════════════════

def detect_mss_v19(ohlcv, swings):
    """
    LuxAlgo internal structure: smaller leg size crossover events.
    Simple: check close crossing above/below prior internal swing levels.
    """
    n = len(ohlcv)
    if n < 10: return []
    
    signals = []
    # Use existing swings as reference
    highs = [(s.bar_idx, s.price) for s in swings if s.type == 'H']
    lows = [(s.bar_idx, s.price) for s in swings if s.type == 'L']
    last_mss = -999
    
    for i in range(5, n):
        if i - last_mss < 12: continue
        close = ohlcv[i]['c']
        prev_close = ohlcv[i-1]['c']
        
        # Check crossover above prior high (bullish MSS)
        for sh_idx, sh_price in highs:
            if sh_idx < i-3 and sh_idx >= i-40:
                if prev_close <= sh_price and close > sh_price:
                    signals.append(Signal(type='MSS_Bull', idx=i, direction='bull',
                        price=sh_price, strength=4.0, confidence=0.6,
                        metadata={'pivot_bar': sh_idx, 'pivot_price': sh_price}))
                    last_mss = i
                    break
        
        # Check crossunder below prior low (bearish MSS)
        for sl_idx, sl_price in lows:
            if sl_idx < i-3 and sl_idx >= i-40:
                if prev_close >= sl_price and close < sl_price:
                    signals.append(Signal(type='MSS_Bear', idx=i, direction='bear',
                        price=sl_price, strength=4.0, confidence=0.6,
                        metadata={'pivot_bar': sl_idx, 'pivot_price': sl_price}))
                    last_mss = i
                    break
    return signals

# ════════════════════════════════════════════
# 7. EQL/EQH — LuxAlgo adjacent pivot comparison
# ════════════════════════════════════════════

def detect_eql_v19(ohlcv, swings, atr_val=None, avg_price=None):
    """LuxAlgo style + A-share percentage adaptation: compare adjacent pivots with 0.5% price tolerance."""
    if avg_price is None:
        avg_price = sum(b['c'] for b in ohlcv[-100:]) / min(100, len(ohlcv)) if len(ohlcv) >= 20 else 100
    threshold = avg_price * 0.005  # 0.5% of average price (for A-share high-price stocks)
    
    signals = []
    highs = [s for s in swings if s.type == 'H']
    lows = [s for s in swings if s.type == 'L']
    
    for i in range(1, len(highs)):
        prev, curr = highs[i-1], highs[i]
        if abs(curr.price - prev.price) <= threshold:
            signals.append(Signal(type='EQH', idx=curr.bar_idx, direction='neutral',
                price=curr.price, upper=max(curr.price,prev.price),
                lower=min(curr.price,prev.price), strength=3.0, confidence=0.5))
    
    for i in range(1, len(lows)):
        prev, curr = lows[i-1], lows[i]
        if abs(curr.price - prev.price) <= threshold:
            signals.append(Signal(type='EQL', idx=curr.bar_idx, direction='neutral',
                price=curr.price, upper=max(curr.price,prev.price),
                lower=min(curr.price,prev.price), strength=3.0, confidence=0.5))
    return signals

# ════════════════════════════════════════════
# 8. BPR — Multi-zone overlap
# ════════════════════════════════════════════

def detect_bpr_v19(fvg_signals, ob_signals):
    signals = []
    bull_zones = [(s.lower, s.upper, s.idx) for s in fvg_signals+ob_signals if s.direction=='bull']
    bear_zones = [(s.lower, s.upper, s.idx) for s in fvg_signals+ob_signals if s.direction=='bear']
    
    added = set()
    all_bpr = []
    for bl, bu, bidx in bull_zones:
        for rl, ru, ridx in bear_zones:
            ol = max(bl, rl); oh = min(bu, ru)
            key = (round(ol,2), round(oh,2))
            if ol < oh and key not in added:
                added.add(key)
                all_bpr.append((max(bidx,ridx), ol, oh, (ol+oh)/2))
    
    # Limit to top-15 most recent (highest bar index) BPRs
    all_bpr.sort(key=lambda x: -x[0])
    for bidx, ol, oh, mid in all_bpr[:15]:
        signals.append(Signal(type='BPR', idx=bidx, direction='neutral',
            price=mid, upper=oh, lower=ol, strength=5.0, confidence=0.65))
    return signals

# ════════════════════════════════════════════
# 9. MAIN DETECTION
# ════════════════════════════════════════════

def detect_all_signals_v19(ohlcv: List[Dict], params: Dict = None) -> tuple:
    if params is None: params = {}
    
    leg_size = params.get('leg_size', 20)  # A-share daily: 20 for true structure swings
    fvg_atr_mult = params.get('fvg_atr_mult', 0.5)
    min_strength = params.get('min_strength', 2.5)
    
    # 1. Detect swing points (LuxAlgo leg method)
    swings, swings_dict = detect_leg_swings(ohlcv, leg_size=leg_size)
    
    # 2. CHOCH/BOS
    choch_bos, trend_bias = detect_choch_bos_v19(ohlcv, swings)
    
    # 3. OB (LuxAlgo + SMC 2026)
    ob = detect_ob_luxalgo(ohlcv, swings, choch_bos)
    
    # 4. FVG
    fvg = detect_fvg_v19(ohlcv, atr_mult=fvg_atr_mult, min_strength=min_strength)
    
    # 5. Sweep
    sweep = detect_sweep_v19(ohlcv, swings)
    
    # 6. MSS
    mss = detect_mss_v19(ohlcv, swings)
    
    # 7. EQL/EQH
    atr_val = _calc_atr(ohlcv, 200)
    avg_price = sum(b['c'] for b in ohlcv[-100:]) / min(100, len(ohlcv))
    eql = detect_eql_v19(ohlcv, swings, avg_price=avg_price)
    
    # 8. BPR
    bpr = detect_bpr_v19(fvg, ob)
    
    all_sigs = fvg + ob + choch_bos + sweep + mss + eql + bpr
    all_sigs.sort(key=lambda s: s.idx)
    
    type_counts = {}
    for s in all_sigs:
        type_counts[s.type] = type_counts.get(s.type, 0) + 1
    
    stats = {
        'total_signals': len(all_sigs),
        'type_counts': type_counts,
        'swing_highs': len(swings_dict['highs']),
        'swing_lows': len(swings_dict['lows']),
        'swings': [
            {'bar': s.bar_idx, 'price': round(s.price,2), 'type': s.type, 'label': s.label}
            for s in swings
        ],
        'params': params,
    }
    
    return all_sigs, stats, swings, swings_dict

# ════════════════════════════════════════════
# 10. SELF-TEST
# ════════════════════════════════════════════

if __name__ == '__main__':
    import json, sys
    sys.path.insert(0, '/root/.hermes/scripts')
    from pathlib import Path
    
    fpath = Path('/root/.hermes/kline_cache/600519_SH_daily_300.json')
    if not fpath.exists():
        print("No data"); sys.exit(1)
    
    ohlcv = json.loads(fpath.read_bytes())
    signals, stats, swings, _ = detect_all_signals_v19(ohlcv)
    
    print(f"=== V19: 600519.SH ({len(ohlcv)} bars) ===")
    print(f"Swing points: {stats['swing_highs']}H + {stats['swing_lows']}L = {stats['swing_highs']+stats['swing_lows']}")
    print(f"\nSwing labels:")
    for s in stats['swings']:
        print(f"  bar={s['bar']:3d} {s['type']}@{s['price']:>8.2f} [{s['label']}]")
    
    print(f"\nSignal counts:")
    for t, c in sorted(stats['type_counts'].items()):
        print(f"  {t}: {c}")
    print(f"  TOTAL: {stats['total_signals']}")
    
    # Sample signals
    print(f"\nSample signal indices:")
    shown = {}
    for s in signals:
        if s.type not in shown: shown[s.type] = []
        if len(shown[s.type]) < 3: shown[s.type].append(f"bar={s.idx} price={s.price:.2f}")
    for t, items in sorted(shown.items()):
        print(f"  {t}: {', '.join(items)}")


# ════════════════════════════════════════════
# 11. SIGNAL SEQUENCE DETECTION
# ════════════════════════════════════════════

SEQUENCE_PATTERNS = [
    # Bullish reversal
    {'name': 'Sweep→CHOCH→FVG→OB', 'types': ['Sweep_SSL','CHOCH_Bull','FVG_Bull','OB_Bull'], 'bars': [3,4,4]},
    {'name': 'CHOCH→FVG→OB', 'types': ['CHOCH_Bull','FVG_Bull','OB_Bull'], 'bars': [4,3]},
    {'name': 'Sweep→CHOCH→FVG', 'types': ['Sweep_SSL','CHOCH_Bull','FVG_Bull'], 'bars': [3,4]},
    {'name': 'Sweep→FVG→OB', 'types': ['Sweep_SSL','FVG_Bull','OB_Bull'], 'bars': [5,4]},
    # Bearish reversal
    {'name': 'Sweep→CHOCH→FVG→OB', 'types': ['Sweep_BSL','CHOCH_Bear','FVG_Bear','OB_Bear'], 'bars': [3,4,4]},
    {'name': 'CHOCH→FVG→OB', 'types': ['CHOCH_Bear','FVG_Bear','OB_Bear'], 'bars': [4,3]},
    {'name': 'Sweep→CHOCH→FVG', 'types': ['Sweep_BSL','CHOCH_Bear','FVG_Bear'], 'bars': [3,4]},
    {'name': 'Sweep→FVG→OB', 'types': ['Sweep_BSL','FVG_Bear','OB_Bear'], 'bars': [5,4]},
    # Trend continuation
    {'name': 'BOS→FVG', 'types': ['BOS_Bull','FVG_Bull'], 'bars': [3]},
    {'name': 'BOS→FVG', 'types': ['BOS_Bear','FVG_Bear'], 'bars': [3]},
    {'name': 'MSS→CHOCH', 'types': ['MSS_Bull','CHOCH_Bull'], 'bars': [3]},
    {'name': 'MSS→CHOCH', 'types': ['MSS_Bear','CHOCH_Bear'], 'bars': [3]},
    # Simple combos
    {'name': 'FVG+OB', 'types': ['FVG_Bull','OB_Bull'], 'bars': [2]},
    {'name': 'FVG+OB', 'types': ['FVG_Bear','OB_Bear'], 'bars': [2]},
    {'name': 'Sweep→FVG', 'types': ['Sweep_SSL','FVG_Bull'], 'bars': [5]},
    {'name': 'Sweep→FVG', 'types': ['Sweep_BSL','FVG_Bear'], 'bars': [5]},
]

def detect_signal_sequences(signals):
    """Find SMC signal sequences in chronological order."""
    sequences = []
    sigs = sorted(signals, key=lambda s: s.idx)
    
    for pat in SEQUENCE_PATTERNS:
        types = pat['types']
        windows = pat['bars']
        # Sliding window through all signals
        for i in range(len(sigs) - len(types) + 1):
            match = True
            bars = [sigs[i].idx]
            for j in range(len(types)):
                s = sigs[i+j]
                if s.type != types[j]:
                    match = False
                    break
                if j > 0 and s.idx - sigs[i+j-1].idx > windows[j-1]:
                    match = False
                    break
                bars.append(s.idx)
            if match:
                sequences.append({
                    'pattern': pat['name'],
                    'direction': 'bull' if 'Bull' in types[0] or 'SSL' in types[0] else 'bear',
                    'start_bar': sigs[i].idx,
                    'end_bar': sigs[i+len(types)-1].idx,
                    'signals': [{'type': sigs[i+k].type, 'bar': sigs[i+k].idx, 'price': round(sigs[i+k].price, 2)} for k in range(len(types))],
                    'has_entry': types[-1] in ('FVG_Bull','OB_Bull','FVG_Bear','OB_Bear')
                })
                break  # One match per pattern per start position
    
    return sequences
