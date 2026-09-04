#!/usr/bin/env python3
"""
V26 SMC Signal Detector — focused on accurate core SMC signals only
Filters noise (FVG/Pinbar/OTE/IFVG/BreakerBlock) and enhances BOS/CHOCH/Sweep
"""
import json
from pathlib import Path
from collections import defaultdict, Counter


class Signal:
    __slots__ = ('type','bar','dir','price','strength','confidence','meta')
    def __init__(self, type_, bar, dir_, price=0, strength=0, confidence=0.5, meta=None):
        self.type = type_; self.bar = bar; self.dir = dir_
        self.price = price; self.strength = strength
        self.confidence = confidence; self.meta = meta or {}
    def __repr__(self):
        return f"Signal({self.type}@{self.bar} {self.dir} p={self.price})"


def atr(klines, idx, period=14):
    trs = []
    for i in range(max(period, idx-period), idx+1):
        if i<1 or i>=len(klines): continue
        b, pb = klines[i], klines[i-1]
        h, l = float(b.get('h',0)), float(b.get('l',0))
        pc = float(pb.get('c',0))
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return sum(trs)/len(trs) if trs else 0.02


def find_swings(klines, min_bars=3):
    """Find swing highs and lows — more sensitive than LuxAlgo"""
    n = len(klines)
    highs, lows = [], []
    
    for i in range(min_bars, n - min_bars):
        b = klines[i]
        h, l = float(b.get('h',0)), float(b.get('l',0))
        
        # Swing high: higher than min_bars bars on each side
        is_high = True
        for j in range(i-min_bars, i+min_bars+1):
            if j == i: continue
            if float(klines[j].get('h',0)) >= h:
                is_high = False; break
        if is_high:
            highs.append({'bar': i, 'price': h, 'label': 'HH', 'date': klines[i].get('t','?')})
        
        # Swing low
        is_low = True
        for j in range(i-min_bars, i+min_bars+1):
            if j == i: continue
            if float(klines[j].get('l',0)) <= l:
                is_low = False; break
        if is_low:
            lows.append({'bar': i, 'price': l, 'label': 'LL', 'date': klines[i].get('t','?')})
    
    # Label HH/HL/LH/LL
    for i, h in enumerate(highs):
        if i > 0: 
            h['label'] = 'HH' if h['price'] > highs[i-1]['price'] else 'LH'
    for i, l in enumerate(lows):
        if i > 0:
            l['label'] = 'HL' if l['price'] > lows[i-1]['price'] else 'LL'
    
    return highs, lows


def detect_smc_signals(klines):
    """
    Detects ONLY core SMC signals:
    1. BOS (Break of Structure) — price breaks prior swing point
    2. CHOCH (Change of Character) — LH broken up or HL broken down
    3. Sweep (Liquidity Sweep) — price briefly breaks swing point then reverses
    4. OB (Order Block) — last opposing candle before a strong move
    5. MSS (Market Structure Shift) — CHOCH confirmed by follow-through
    """
    n = len(klines)
    signals = []
    atr14 = atr(klines, n-1)
    highs, lows = find_swings(klines, min_bars=3)
    
    if not highs or not lows:
        return signals
    
    # ═══ 1. BOS/CHOCH Detection ═══
    for h in highs:
        h_bar, h_price = h['bar'], h['price']
        # Check if price subsequently broke above this high
        for i in range(h_bar + 2, min(h_bar + 40, n)):
            cl = float(klines[i].get('c', 0))
            if cl > h_price:
                penetration = (cl - h_price) / h_price * 100
                if penetration < 0.1:  # Too small, keep scanning
                    continue
                
                tag = 'CHOCH_Bull' if h['label'] == 'LH' else 'BOS_Bull'
                signals.append(Signal(tag, i, 'bull', price=round(cl, 2),
                    strength=round(penetration, 2),
                    confidence=0.85 if 'CHOCH' in tag else 0.70,
                    meta={'swing_bar': h_bar, 'swing_price': h_price, 'swing_label': h['label']}))
                break
    
    for l in lows:
        l_bar, l_price = l['bar'], l['price']
        for i in range(l_bar + 2, min(l_bar + 40, n)):
            cl = float(klines[i].get('c', 0))
            if cl < l_price:
                penetration = (l_price - cl) / l_price * 100
                if penetration < 0.1: continue
                
                tag = 'CHOCH_Bear' if l['label'] == 'HL' else 'BOS_Bear'
                signals.append(Signal(tag, i, 'bear', price=round(cl, 2),
                    strength=round(penetration, 2),
                    confidence=0.85 if 'CHOCH' in tag else 0.70,
                    meta={'swing_bar': l_bar, 'swing_price': l_price, 'swing_label': l['label']}))
                break
    
    # ═══ 2. Liquidity Sweep ═══
    for h in highs:
        h_bar, h_price = h['bar'], h['price']
        for i in range(h_bar + 1, min(h_bar + 15, n)):
            hi = float(klines[i].get('h', 0))
            cl = float(klines[i].get('c', 0))
            # Briefly broke above swing high then closed below
            if hi > h_price * 1.002 and cl < h_price * 0.998:
                signals.append(Signal('Sweep_SSL', i, 'bear', price=round(cl, 2),
                    strength=round((hi - h_price)/h_price*100, 2),
                    confidence=0.70,
                    meta={'swing_bar': h_bar, 'swing_price': h_price}))
                break
    
    for l in lows:
        l_bar, l_price = l['bar'], l['price']
        for i in range(l_bar + 1, min(l_bar + 15, n)):
            lo = float(klines[i].get('l', 0))
            cl = float(klines[i].get('c', 0))
            if lo < l_price * 0.998 and cl > l_price * 1.002:
                signals.append(Signal('Sweep_BSL', i, 'bull', price=round(cl, 2),
                    strength=round((l_price - lo)/l_price*100, 2),
                    confidence=0.70,
                    meta={'swing_bar': l_bar, 'swing_price': l_price}))
                break
    
    # ═══ 3. OB (Order Block) — last opposing candle before displacement ═══
    for i in range(5, n - 2):
        b0, b1, b2 = klines[i-1], klines[i], klines[i+1]
        c0, c1, c2 = float(b0.get('c',0)), float(b1.get('c',0)), float(b2.get('c',0))
        h0, h1 = float(b0.get('h',0)), float(b1.get('h',0))
        l0, l1 = float(b0.get('l',0)), float(b1.get('l',0))
        
        # Bullish OB: down candle then strong up move
        displacement = c2 - c1
        if c0 > c1 and displacement > atr14 * 1.0:  # Require 1.0x ATR displacement (was 0.5)
            # OB = the down candle (b1)
            signals.append(Signal('OB_Bull', i, 'bull', price=round(c1, 2),
                strength=round(displacement/atr14, 1),
                confidence=0.65,
                meta={'ob_bar': i, 'ob_high': max(h1, h0), 'ob_low': l1, 'disp': round(displacement, 2)}))
        
        # Bearish OB: up candle then strong down move
        if c0 < c1 and -displacement > atr14 * 1.0:
            signals.append(Signal('OB_Bear', i, 'bear', price=round(c1, 2),
                strength=round(-displacement/atr14, 1),
                confidence=0.65,
                meta={'ob_bar': i, 'ob_high': h1, 'ob_low': min(l1, l0), 'disp': round(displacement, 2)}))
    
    # ═══ 4. MSS — CHOCH with follow-through (only first confirm) ═══
    choch_signals = [s for s in signals if 'CHOCH' in s.type]
    used_choch = set()
    for ch_sig in choch_signals:
        if ch_sig.bar in used_choch: continue
        ch_bar = ch_sig.bar
        # Find first bar within 5 bars after CHOCH that continues in same direction
        for i in range(ch_bar + 1, min(ch_bar + 6, n)):
            cl = float(klines[i].get('c', 0))
            ch_close = float(klines[ch_bar].get('c', 0))
            if ch_sig.dir == 'bull' and cl > ch_close:
                signals.append(Signal('MSS_Bull', i, 'bull', price=round(cl, 2),
                    strength=1, confidence=0.75, meta={'choch_bar': ch_bar}))
                used_choch.add(ch_bar)
                break
            elif ch_sig.dir == 'bear' and cl < ch_close:
                signals.append(Signal('MSS_Bear', i, 'bear', price=round(cl, 2),
                    strength=1, confidence=0.75, meta={'choch_bar': ch_bar}))
                used_choch.add(ch_bar)
                break
    
    # ═══ 5. Dedup — keep strongest signal per bar ═══
    signals.sort(key=lambda s: (s.bar, -s.strength))
    deduped = []
    last_bar = -1
    for s in signals:
        if s.bar != last_bar:
            deduped.append(s)
            last_bar = s.bar
    
    return deduped


# ── Test ──
if __name__ == '__main__':
    KLINE_DIR = Path('/root/.hermes/kline_cache')
    
    import random
    random.seed(42)
    files = random.sample(list(KLINE_DIR.glob('*_daily_750.json')), 5)
    
    all_types = Counter()
    total = 0
    
    for f in files:
        klines = json.loads(f.read_text())
        for b in klines:
            for k in ('o','h','l','c'):
                if k in b: b[k] = float(b[k])
        
        sigs = detect_smc_signals(klines)
        total += len(klines)
        for s in sigs:
            all_types[s.type] += 1
        
        sym = f.stem.replace('_daily_750','').replace('_SH','.SH').replace('_SZ','.SZ')
        print(f"{sym}: {len(sigs)} signals in {len(klines)} bars")
    
    print(f"\n=== Signal Distribution ({len(files)} stocks, {total} bars) ===")
    for st, n in all_types.most_common():
        print(f"  {st:20s}: {n:4d} ({n/total*100:.2f}% of bars)")
