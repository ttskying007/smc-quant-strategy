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


# ═══ R90: 跨股票 swing 密度收归 — 把"一个结构事件"的语义跨股对齐 ═══
def pick_wing_by_density(klines, target_lo=8.0, target_hi=14.0):
    """按目标 swings/100bar 密度自动选 wing:
    依次试 2,3,4,5,6,8, 选首个落进 [target_lo, target_hi] 的;
    全超 → wing=8; 全低 → wing=2.
    返回 (wing, density). R89 实证: 跨股 ATR% 5.4x 跨度下,
    该法把信号量跨股跨度从固定版的 15.8~34.2 压到 4.3~13.2.
    """
    n = len(klines)
    if n < 30:
        return 3, 0.0
    meta = {}
    for w in (2, 3, 4, 5, 6, 8):
        hs, ls = find_swings(klines, min_bars=w)
        density = (len(hs) + len(ls)) / n * 100
        meta[w] = density
        if target_lo <= density <= target_hi:
            return w, density
    best = min(meta, key=lambda w: abs(meta[w] - (target_lo + target_hi) / 2))
    return best, meta[best]


def detect_smc_signals(klines, mode='fixed'):
    """
    Detects ONLY core SMC signals:
    1. BOS (Break of Structure) — price breaks prior swing point
    2. CHOCH (Change of Character) — LH broken up or HL broken down
    3. Sweep (Liquidity Sweep) — price briefly breaks swing point then reverses
    4. OB (Order Block) — last opposing candle before a strong move
    5. MSS (Market Structure Shift) — CHOCH confirmed by follow-through

    mode (R90):
      'fixed' — 旧版硬编参数 (默认, 向后兼容)
      'norm'  — 密度收归: wing 按 swings/100bar∈[8,14] 搜索 + ATR% 映射所有阈值
    """
    n = len(klines)
    signals = []
    atr14 = atr(klines, n-1)

    # ── 参数化(R90) ──
    _wing, _pen_floor, _bos_win, _sw_edge = 3, 0.1, 40, 0.2
    if mode == 'norm':
        _cur = float(klines[-1].get('c', 0)) or 1
        _atr_pct = atr14 / _cur * 100.0 if _cur else 1.0
        _wing, _wing_density = pick_wing_by_density(klines)
        _pen_floor = max(0.10, min(1.5, _atr_pct * 0.45))
        _bos_win = max(20, min(60, round(80 - _atr_pct * 12)))
        _sw_edge = max(0.08, min(0.60, _atr_pct * 0.15))

    atr14 = atr(klines, n-1)
    highs, lows = find_swings(klines, min_bars=_wing)

    if not highs or not lows:
        return signals

    # ═══ 1. BOS/CHOCH Detection ═══
    for h in highs:
        h_bar, h_price = h['bar'], h['price']
        # Check if price subsequently broke above this high
        for i in range(h_bar + 2, min(h_bar + _bos_win, n)):
            cl = float(klines[i].get('c', 0))
            if cl > h_price:
                penetration = (cl - h_price) / h_price * 100
                if penetration < _pen_floor:  # Too small, keep scanning
                    continue
                
                tag = 'CHOCH_Bull' if h['label'] == 'LH' else 'BOS_Bull'
                signals.append(Signal(tag, i, 'bull', price=round(cl, 2),
                    strength=round(penetration, 2),
                    confidence=0.85 if 'CHOCH' in tag else 0.70,
                    meta={'swing_bar': h_bar, 'swing_price': h_price, 'swing_label': h['label']}))
                break
    
    for l in lows:
        l_bar, l_price = l['bar'], l['price']
        for i in range(l_bar + 2, min(l_bar + _bos_win, n)):
            cl = float(klines[i].get('c', 0))
            if cl < l_price:
                penetration = (l_price - cl) / l_price * 100
                if penetration < _pen_floor: continue
                
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
            if hi > h_price * (1 + _sw_edge/100.0) and cl < h_price * (1 - _sw_edge/100.0):
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
            if lo < l_price * (1 - _sw_edge/100.0) and cl > l_price * (1 + _sw_edge/100.0):
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
    
    # ═══ 6. Reclaim_Reject — 二测拒绝 (池级, R125/R130 因果证据: 18/20 全胜) ═══
    # 注意: 类型名故意不含 'Sweep' 子串 — s8 因子用 "Sweep" in s.type 过滤,
    #       子串碰撞会把 RR 误计成扫 (additive 规则破坏), R131 修正。
    # EQH/EQL 池 (≥2 swing 点 0.8% 聚类, 近250 bar) 影线假扫 → 20 bar 内回池反弹
    # 且 close 未先破池位 → 信号 = 反弹 bar, 方向 = 反池侧 (EQH→bear 空拒绝, EQL→bull 多拒绝)
    # 因果: 两遍法 — Pass1 全序列找池+扫日; Pass2 以扫日为参考重聚类, 池价 1% 内一致才发信号
    # R131: 摆点源 = auto pivot (与 R125/R130 证据同源) — 自包含复制, 不动引擎 highs/lows
    def _rr_is_sh(j, p):
        if j < p or j + p >= n:
            return False
        hi = klines[j]["h"]
        return (hi > max(klines[k]["h"] for k in range(j - p, j))
                and hi >= max(klines[k]["h"] for k in range(j + 1, j + p + 1)))

    def _rr_is_sl(j, p):
        if j < p or j + p >= n:
            return False
        lo = klines[j]["l"]
        return (lo < min(klines[k]["l"] for k in range(j - p, j))
                and lo <= min(klines[k]["l"] for k in range(j + 1, j + p + 1)))

    def _rr_pick_pivot(ref_bar, lookback=250):
        n_ = min(ref_bar, n - 1)
        start = max(8, n_ - lookback)
        meta = {}
        for p in (2, 3, 4, 5, 6, 8):
            cnt = 0
            for j in range(max(p, start), max(p, n_ - p) + 1):
                if _rr_is_sh(j, p) or _rr_is_sl(j, p):
                    cnt += 1
            span = max(1, n_ - start)
            meta[p] = cnt / span * 100
            if 8.0 <= meta[p] <= 14.0:
                return p
        return min(meta, key=lambda w: abs(meta[w] - 11.0))

    def _rr_swings(ref_bar, side):
        p = _rr_pick_pivot(ref_bar)
        if side == 'EQH':
            return [{'bar': j, 'price': klines[j]['h']}
                    for j in range(p, min(ref_bar, n - p) - p + 1) if _rr_is_sh(j, p)]
        return [{'bar': j, 'price': klines[j]['l']}
                for j in range(p, min(ref_bar, n - p) - p + 1) if _rr_is_sl(j, p)]

    def _cluster_sw(sw_list, ref_bar, tol_ratio=0.008, lookback=250):
        cut = max(0, ref_bar - lookback)
        cand = sorted([(s['bar'], s['price']) for s in sw_list if s['bar'] >= cut and s['bar'] <= ref_bar],
                      key=lambda x: -x[0])
        used = [False] * len(cand)
        out = []
        for a in range(len(cand)):
            if used[a]:
                continue
            p1 = cand[a][1]
            members = [a]
            for b in range(a + 1, len(cand)):
                if abs(cand[b][1] - p1) / p1 <= tol_ratio:
                    members.append(b)
                    used[b] = True
            if len(members) >= 2:
                js = [cand[m][0] for m in members]
                out.append({'price': sum(cand[m][1] for m in members) / len(members),
                            'last_bar': max(js)})
        return out

    for _side, _sdir in (('EQH', 'bear'), ('EQL', 'bull')):
        # Pass1: 全序列参考找池 + 扫日/二测候选
        for q in _cluster_sw(_rr_swings(n, _side), n):
            pp = q['price']
            sweep_i = -1
            for i in range(q['last_bar'] + 1, n):
                _hi = float(klines[i].get('h', 0))
                _lo = float(klines[i].get('l', 0))
                _cl = float(klines[i].get('c', 0))
                _touched = (_hi > pp) if _side == 'EQH' else (_lo < pp)
                _broke = (_cl > pp) if _side == 'EQH' else (_cl < pp)
                if _touched and sweep_i < 0:
                    sweep_i = i
                if _broke:
                    break  # 实收穿越 → 池被吃, 不发信号
                if sweep_i >= 0 and i > sweep_i + 20:
                    break  # 20 bar 内无二测
                if _touched and sweep_i >= 0 and i > sweep_i:
                    # 二测反弹候选 → Pass2 因果验证 (以扫日为参考重聚类)
                    _causal = _cluster_sw(_rr_swings(sweep_i, _side), sweep_i)
                    _hit = next((c2 for c2 in _causal if abs(c2['price'] - pp) / pp <= 0.01), None)
                    if _hit is None:
                        break  # 池聚类前视 → 剔除 (R130 标准)
                    signals.append(Signal('Reclaim_Reject', i, _sdir, price=round(_cl, 2),
                        strength=round(abs(pp - _cl) / pp * 100, 2),
                        confidence=0.65,
                        meta={'pool_price': round(pp, 2), 'sweep_bar': sweep_i, 'side': _side}))
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
