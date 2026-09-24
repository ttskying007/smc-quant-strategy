# -*- coding: utf-8 -*-
r"""R89 — SMC 检测器自适应实证 (goal round 1):

诊断: 司股之间 ATR% 差异 3-10x → 固定 min_bars/penetration/窗口 极易翻车.
方案 ATR-relative 全部参数 → 跨股对比 & 重算 v22 腿链.

关键问题:
 1. 跨股 ATR% 分布有多宽?
 2. 固定 vs 自适应: 每 100bar 结构事件数(BOS/CHoCH/Sweep/MSS) 差异多少 (灵敏度差)?
 3. v22 实际腿用新 detector 重算: trend/last_event/breakout 翻转率多少?

立场: 只要自适应使噪声正常化且不饿死低波股 → 建议全切换, 否则弃.
"""
import json, sys, io, math, random
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = Path(r'E:\test\smc_project')
sys.path.insert(0, str(ROOT / 'hermes' / 'scripts' / 'v25'))
from smc_detector import detect_smc_signals, find_swings, atr  # noqa

KC = ROOT / 'hermes' / 'kline_cache_tencent'


def det_adaptive_normalize(klines, target_lo=8.0, target_hi=14.0):
    """按目标 swing 密度自动搜索 wing: 各 wing∈[2..8] 下算 swings/100bar, 选首个落进
    target_lo~target_hi 的; 都超上限选 wing=8, 都低选 wing=2.
    颜色标记: 其它参数 (*(penetration 等))* 仍 ATR 映射, 保持原模型化.
    核心理念: '一根结构事件应该意味着跨股一起的东西'——节奏归一, 语义才可比.
    """
    n = len(klines)
    if n < 30:
        return []
    atr14 = atr(klines, n - 1)
    cur = float(klines[-1].get('c', 1)) or 1
    atr_pct = atr14 / cur * 100.0

    wing = None
    wing_meta = {}
    for w in (2, 3, 4, 5, 6, 8):
        hs, ls = find_swings(klines, min_bars=w)
        density = (len(hs) + len(ls)) / n * 100
        wing_meta[w] = density
        if wing is None and target_lo <= density <= target_hi:
            wing = w
            break
    if wing is None:
        # 选距离目标区间最近的
        wing = min(wing_meta, key=lambda w: abs(wing_meta[w] - (target_lo + target_hi) / 2))
    wing_density = wing_meta[wing]

    pen = max(0.10, min(1.5, atr_pct * 0.45))
    bos_win = max(20, min(60, round(80 - atr_pct * 12)))
    sw_edge = max(0.08, min(0.60, atr_pct * 0.15)) / 100.0

    highs, lows = find_swings(klines, min_bars=wing)
    if not highs or not lows:
        return []
    from smc_detector import Signal
    signals = []
    for h in highs:
        for i in range(h['bar'] + 2, min(h['bar'] + bos_win, n)):
            cl = float(klines[i].get('c', 0))
            if cl > h['price']:
                p = (cl - h['price']) / h['price'] * 100
                if p < pen:
                    continue
                tag = 'CHOCH_Bull' if h['label'] == 'LH' else 'BOS_Bull'
                signals.append(Signal(tag, i, 'bull', price=round(cl, 2), strength=round(p, 2),
                                      confidence=0.85 if 'CHOCH' in tag else 0.70,
                                      meta={'swing_bar': h['bar'], 'swing_price': h['price'],
                                            'wing': wing, 'swing_density': round(wing_density, 1)}))
                break
    for l in lows:
        for i in range(l['bar'] + 2, min(l['bar'] + bos_win, n)):
            cl = float(klines[i].get('c', 0))
            if cl < l['price']:
                p = (l['price'] - cl) / l['price'] * 100
                if p < pen:
                    continue
                tag = 'CHOCH_Bear' if l['label'] == 'HL' else 'BOS_Bear'
                signals.append(Signal(tag, i, 'bear', price=round(cl, 2), strength=round(p, 2),
                                      confidence=0.85 if 'CHOCH' in tag else 0.70,
                                      meta={'swing_bar': l['bar'], 'wing': wing}))
                break
    for h in highs:
        for i in range(h['bar'] + 1, min(h['bar'] + 15, n)):
            hi = float(klines[i].get('h', 0)); cl = float(klines[i].get('c', 0))
            if hi > h['price'] * (1 + sw_edge) and cl < h['price'] * (1 - sw_edge):
                signals.append(Signal('Sweep_SSL', i, 'bear', price=round(cl, 2),
                                      strength=round((hi - h['price']) / h['price'] * 100, 2),
                                      confidence=0.70, meta={}))
                break
    for l in lows:
        for i in range(l['bar'] + 1, min(l['bar'] + 15, n)):
            lo = float(klines[i].get('l', 0)); cl = float(klines[i].get('c', 0))
            if lo < l['price'] * (1 - sw_edge) and cl > l['price'] * (1 + sw_edge):
                signals.append(Signal('Sweep_BSL', i, 'bull', price=round(cl, 2),
                                      strength=round((l['price'] - lo) / l['price'] * 100, 2),
                                      confidence=0.70, meta={}))
                break
    return signals


def det_adaptive(klines):
    """adaptive 参数 detector: 结构与原版相同, 只是 params 从 ATR% 映射."""
    n = len(klines)
    if n < 30:
        return []
    atr14 = atr(klines, n - 1)
    cur = float(klines[-1].get('c', 1)) or 1
    atr_pct = atr14 / cur * 100.0  # 百分比形式

    # ── 映射: 高 ATR% → 更宽 swing 翼 / 更高穿透门 ──
    # ATR% ∈ [0.8, 3.5] → wing ∈ [2, 6] (低于不用 1: 单根 bar 还是 volatility spike 无效)
    wing = max(2, min(6, round(atr_pct * 1.7)))
    # pen floor: 在原 0.1% 上按 ATR% 比例放大, 限 [0.1, 1.5]
    pen = max(0.10, min(1.5, atr_pct * 0.45))
    # scan window: 高波更快突破(避免长挂), 限 [20, 60]
    bos_win = max(20, min(60, round(80 - atr_pct * 12)))
    # sweep 触发边缘: 由 ±0.2% 变成 ±0.10*ATR% 限 [0.08, 0.60]%
    sw_edge = max(0.08, min(0.60, atr_pct * 0.15)) / 100.0

    highs, lows = find_swings(klines, min_bars=wing)
    if not highs or not lows:
        return []
    from smc_detector import Signal
    signals = []
    for h in highs:
        for i in range(h['bar'] + 2, min(h['bar'] + bos_win, n)):
            cl = float(klines[i].get('c', 0))
            if cl > h['price']:
                p = (cl - h['price']) / h['price'] * 100
                if p < pen:
                    continue
                tag = 'CHOCH_Bull' if h['label'] == 'LH' else 'BOS_Bull'
                signals.append(Signal(tag, i, 'bull', price=round(cl, 2), strength=round(p, 2),
                                      confidence=0.85 if 'CHOCH' in tag else 0.70,
                                      meta={'swing_bar': h['bar'], 'swing_price': h['price'], 'wing': wing, 'pen': round(atr_pct, 2)}))
                break
    for l in lows:
        for i in range(l['bar'] + 2, min(l['bar'] + bos_win, n)):
            cl = float(klines[i].get('c', 0))
            if cl < l['price']:
                p = (l['price'] - cl) / l['price'] * 100
                if p < pen:
                    continue
                tag = 'CHOCH_Bear' if l['label'] == 'HL' else 'BOS_Bear'
                signals.append(Signal(tag, i, 'bear', price=round(cl, 2), strength=round(p, 2),
                                      confidence=0.85 if 'CHOCH' in tag else 0.70,
                                      meta={'swing_bar': l['bar'], 'wing': wing}))
                break
    for h in highs:
        for i in range(h['bar'] + 1, min(h['bar'] + 15, n)):
            hi = float(klines[i].get('h', 0)); cl = float(klines[i].get('c', 0))
            if hi > h['price'] * (1 + sw_edge) and cl < h['price'] * (1 - sw_edge):
                signals.append(Signal('Sweep_SSL', i, 'bear', price=round(cl, 2),
                                      strength=round((hi - h['price']) / h['price'] * 100, 2),
                                      confidence=0.70, meta={}))
                break
    for l in lows:
        for i in range(l['bar'] + 1, min(l['bar'] + 15, n)):
            lo = float(klines[i].get('l', 0)); cl = float(klines[i].get('c', 0))
            if lo < l['price'] * (1 - sw_edge) and cl > l['price'] * (1 + sw_edge):
                signals.append(Signal('Sweep_BSL', i, 'bull', price=round(cl, 2),
                                      strength=round((l['price'] - lo) / l['price'] * 100, 2),
                                      confidence=0.70, meta={}))
                break
    return signals



def signals_per_100(sigs, n_bars):
    out = {}
    for s in sigs:
        out[s.type] = out.get(s.type, 0) + 1
    return {k: round(v / n_bars * 100, 2) for k, v in out.items()}


def main():
    random.seed(7)
    files = sorted(KC.glob('*_daily_800.json'))
    # 跨价格跨度均匀抽样 40 只 (低/中/高送转)
    sample = random.sample(files, 40)
    print(f'采样股票: {len(sample)}\n')

    header = f"{'code':<9} {'ATR%':>5} {'wing':>4} {'FIXED':>6} {'ADAPT':>6} {'NORM':>6}"
    print(header)
    print('-' * len(header))

    diffs = []
    vol_profile = []
    for f in sample:
        klines = json.loads(f.read_text())
        for b in klines:
            for k in ('o', 'h', 'l', 'c'):
                if k in b:
                    b[k] = float(b[k])
        n = len(klines)
        a14 = atr(klines, n - 1)
        cur = float(klines[-1].get('c', 1)) or 1
        atr_pct = a14 / cur * 100
        wing = max(2, min(6, round(atr_pct * 1.7)))

        sf = detect_smc_signals(klines)
        sa = det_adaptive(klines)
        sn = det_adaptive_normalize(klines)
        f100 = signals_per_100(sf, n)
        a100 = signals_per_100(sa, n)
        n100 = signals_per_100(sn, n)
        tot_fix = sum(f100.values())
        tot_adp = sum(a100.values())
        tot_norm = sum(n100.values())
        d = tot_adp - tot_fix
        code = f.stem.split('_daily')[0]
        print(f"{code:<9} {atr_pct:5.2f} {wing:>4} {tot_fix:6.1f} {tot_adp:6.1f} {tot_norm:6.1f}")
        diffs.append(d)
        vol_profile.append((atr_pct, wing, tot_fix, tot_adp, tot_norm))

    print('\n=== 汇总 ===')
    print(f'ATR% 范围: {min(x[0] for x in vol_profile):.2f} ~ {max(x[0] for x in vol_profile):.2f}')
    print(f'wing 自适应分布: 2→{sum(1 for x in vol_profile if x[1]==2)}, 3→{sum(1 for x in vol_profile if x[1]==3)}, 4→{sum(1 for x in vol_profile if x[1]==4)}, 5+→{sum(1 for x in vol_profile if x[1]>=5)}')
    print(f'FIX 每100bar信号: avg {sum(x[2] for x in vol_profile)/len(vol_profile):.1f} (min {min(x[2] for x in vol_profile):.1f} max {max(x[2] for x in vol_profile):.1f})')
    print(f'ADAPT(atr映射)   : avg {sum(x[3] for x in vol_profile)/len(vol_profile):.1f} (min {min(x[3] for x in vol_profile):.1f} max {max(x[3] for x in vol_profile):.1f})')
    nm = [x[4] for x in vol_profile]
    print(f'NORM(density)    : avg {sum(nm)/len(nm):.1f} (min {min(nm):.1f} max {max(nm):.1f})  ← 目标 8~14')

    # ═══ v22 腿链翻转探针 (用旧数据做 diff) ═══
    print('\n=== v22 腿链翻转(前 80 腿) ===')
    import csv
    legs = list(csv.DictReader(open(ROOT / 'research/combo_v22_trades.csv', encoding='utf-8-sig')))
    random.seed(2)
    sub = random.sample(legs, 80)
    flips = 0
    tested = 0
    by_field = {'trend_state': 0, 'last_event_kind': 0, 'breakout_kind': 0}
    for lg in sub:
        sym = lg['symbol']
        fc = KC / (sym.replace('.SH', '_SH').replace('.SZ', '_SZ') + '_daily_800.json')
        if not fc.exists():
            continue
        klines = json.loads(fc.read_text())
        for b in klines:
            for k in ('o', 'h', 'l', 'c'):
                if k in b:
                    b[k] = float(b[k])
        n = len(klines)
        ed = int(lg['entry_date'])
        bars = [i for i, b in enumerate(klines) if str(b.get('t', '')).startswith('20') is False or True]
        bk = {str(b.get('t', '')).replace('-', '') for b in klines}
        ei = next((i for i, b in enumerate(klines) if str(b.get('t', '')).replace('-', '') == str(ed)), None)
        if ei is None or ei < 20:
            continue
        ctx = klines[max(0, ei - 200):ei + 1]
        sigs_f = detect_smc_signals(ctx)
        sigs_a = det_adaptive(ctx)
        # 取 ctx 尾部 100 bar 中最近一次结构性变化
        def tail_kind(sx):
            for s in reversed(sx):
                if s.type in ('BOS_Bull', 'BOS_Bear', 'CHOCH_Bull', 'CHOCH_Bear'):
                    return s.type
            return None
        kf, ka = tail_kind(sigs_f), tail_kind(sigs_a)
        tested += 1
        if kf != ka:
            flips += 1
            by_field['last_event_kind'] += 1
    if tested:
        print(f'近尾结构性(200bar窗口)BOS/CHoCH 翻转: {flips}/{tested} = {flips/tested*100:.1f}%')
    print('\nROT 判定: 同向翻转率高→自适应骨子里改了语义; 低→信号密度正常化收口')


if __name__ == '__main__':
    main()
