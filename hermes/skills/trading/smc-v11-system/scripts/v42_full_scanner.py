#!/usr/bin/env python3
"""
V42 — ATR-Adaptive Trailing | Full 4800 Scanner
================================================
Run:  cd ~/.hermes/scripts && PYTHONUNBUFFERED=1 python3 <path>/v42_full_scanner.py

6 Improvements:
A) ATR-Adaptive thresholds: gain = mult × ATR%
B) Structure proximity: tighten near swing levels
C) Phase-aware multipliers: markup=1.2x, distribution=0.75x
D) Volume-confirmed exit: >1.2x avg = real, <0.6x = fake
E) Grid-optimized params: BE=0.20, LK=0.50
F) Bear differentiation: bear_mult=0.75

Output: /root/.hermes/smc_opt_v38/v42_full.json
"""
import sys, json, time
from pathlib import Path
from collections import Counter

sys.path.insert(0, '/root/.hermes/scripts')
from v11.structure_tree_v38 import StructureTree, calc_atr_v38
from v11.wyckoff_phases_v38 import detect_wyckoff_phases
import v11.rolling_backtest_v38 as rb38

# ── Config ──
V42_CFG = {
    'gain_breakeven_mult': 0.20, 'gain_lock01_mult': 0.30,
    'gain_lock03_mult': 0.30, 'gain_lock15_mult': 0.60, 'gain_lock30_mult': 1.20,
    'phase_mult_markup': 1.20, 'phase_mult_accumulation': 1.10,
    'phase_mult_reaccumulation': 1.00, 'phase_mult_distribution': 0.75,
    'phase_mult_unknown': 1.00, 'bear_mult': 0.75,
    'struct_prox_factor': 2.0, 'struct_prox_tighten': 0.75,
    'vol_confirm_thresh': 1.2, 'vol_deny_thresh': 0.6,
}

class _Ctx: config = V42_CFG; phase = 'unknown'; tree = None; ohlcv = None
_CTX = _Ctx()

def _pm(p): return _CTX.config.get(f'phase_mult_{p}', 1.0)

def _sp(ei, ep, bi, d):
    t = _CTX.tree
    if not t: return 1.0
    la = min(30, len(t.ohlcv) - bi - 1)
    if la < 3: return 1.0
    atr = calc_atr_v38(_CTX.ohlcv, bi)
    if atr <= 0: return 1.0
    cf = _CTX.config; fac, tgt = cf['struct_prox_factor'], cf['struct_prox_tighten']
    if d == 'bull':
        for lv in ['micro', 'meso']:
            nh = [h for h in t.structures[lv]['highs'] if h['idx'] > ei and h['idx'] <= bi + la]
            if not nh: continue
            nn = min(nh, key=lambda h: h['idx']); ds = (nn['price'] - ep) / ep * 100
            if 0 < ds < atr * fac: return 1.0 - ((1 - (ds / (atr * fac))) * (1 - tgt))
    else:
        for lv in ['micro', 'meso']:
            nl = [l for l in t.structures[lv]['lows'] if l['idx'] > ei and l['idx'] <= bi + la]
            if not nl: continue
            nn = min(nl, key=lambda l: l['idx']); ds = (ep - nn['price']) / ep * 100
            if 0 < ds < atr * fac: return 1.0 - ((1 - (ds / (atr * fac))) * (1 - tgt))
    return 1.0

def _vc(oh, bi):
    cfg = _CTX.config; lb = 20
    if bi < lb or bi >= len(oh): return True
    vs = [oh[i].get('v', oh[i].get('vol', 0)) for i in range(bi - lb, bi)]
    av = sum(vs) / lb; r = (oh[bi].get('v', oh[bi].get('vol', 0))) / av if av > 0 else 1.0
    if r >= cfg['vol_confirm_thresh']: return True
    if r <= cfg['vol_deny_thresh']: return False
    return r >= 0.8

def trailing_fn(ohlcv, ei, ep, sl, tp, n, mh, d):
    cfg = _CTX.config; ph = _CTX.phase
    atr = calc_atr_v38(ohlcv, ei); sa = max(0.3, atr)
    em = _pm(ph) * (cfg['bear_mult'] if d == 'bear' else 1.0)
    gb, g1, g3, g5, g0 = [cfg[k] * sa * em for k in
        ['gain_breakeven_mult', 'gain_lock01_mult', 'gain_lock03_mult',
         'gain_lock15_mult', 'gain_lock30_mult']]
    sl0, ex, tp_p, tp_pct = sl, ep, tp[0] if tp and tp[0] else None, tp[2] if tp and tp[2] else None
    ht, ib, pr = tp_p is not None, d == 'bear', 'tight' if not tp_p else ('bear' if d == 'bear' else 'loose')
    for j in range(ei + 1, min(ei + mh + 1, n)):
        br = ohlcv[j]; st = _sp(ei, ep, j, d)
        if ib:
            if br['l'] < ex: ex = br['l']
            g = (ep - ex) / ep * 100; tg = g * st
            if tp_p and ex <= tp_p * 1.05:
                sl0 = min(sl0, ep * (1 - max(0.8, tp_pct * 0.5) / 100))
                if ex <= tp_p * 1.02: return j, tp_p, True
            else:
                if tg >= g0: sl0 = min(sl0, ex * (1 + max(1.0, 3.0 * cfg['bear_mult']) / 100))
                elif tg >= g5: sl0 = min(sl0, ex * (1 + max(0.5, 1.5 * cfg['bear_mult']) / 100))
                elif tg >= g3: sl0 = min(sl0, ep * (1 + max(0.1, 0.3 * em) / 100))
                elif tg >= g1: sl0 = min(sl0, ep * (1 + max(0.05, 0.1 * em) / 100))
                elif tg >= gb: sl0 = min(sl0, ep * 1.0)
            if br['h'] >= sl0:
                xp = min(sl0, br['h'])
                if _vc(ohlcv, j) or pr == 'tight': return j, round(xp, 2), xp < ep
        else:
            if br['h'] > ex: ex = br['h']
            g = (ex - ep) / ep * 100; tg = g * st
            if tp_p and ex >= tp_p * 0.90:
                sl0 = max(sl0, ep * (1 + max(0.8, tp_pct * 0.5) / 100))
                if ex >= tp_p * 0.98: return j, tp_p, True
            else:
                if tg >= g0: sl0 = max(sl0, ex * (1 - 3.0 / 100))
                elif tg >= g5: sl0 = max(sl0, ex * (1 - 1.5 / 100))
                elif tg >= g3: sl0 = max(sl0, ep * (1 + max(0.1, 0.3 * em) / 100))
                elif tg >= g1: sl0 = max(sl0, ep * (1 + max(0.05, 0.1 * em) / 100))
                elif tg >= gb: sl0 = max(sl0, ep * 1.0)
            if br['l'] <= sl0:
                xp = max(sl0, br['l'])
                if _vc(ohlcv, j) or pr == 'tight': return j, round(xp, 2), xp > ep
    xi = min(ei + mh, n - 1); xp = ohlcv[xi]['c']
    return xi, round(xp, 2), (xp > ep) if not ib else (xp < ep)

# Monkey-patch
rb38.calc_v38_trailing = trailing_fn
_orig_bt = rb38.backtest_stock_v38
def _pbt(oh, sym):
    if oh and len(oh) >= 60:
        try:
            t = StructureTree(oh); w = detect_wyckoff_phases(oh, t)
            _CTX.phase = w.get('primary_phase', 'unknown'); _CTX.tree = t
        except: _CTX.phase = 'unknown'; _CTX.tree = None
        _CTX.ohlcv = oh
    return _orig_bt(oh, sym)
rb38.backtest_stock_v38 = _pbt
_CTX.config = V42_CFG

def main():
    cache = Path('/root/.hermes/kline_cache')
    out = Path('/root/.hermes/smc_opt_v38')
    syms = sorted([f.stem.replace('_daily_300', '').replace('_', '.') for f in cache.glob('*_daily_300.json')])
    print(f'V42 — {len(syms)} stocks | ATR-adaptive trailing'); t0 = time.time()
    all_t, sr = [], []
    for i, s in enumerate(syms):
        f = cache / f"{s.replace('.', '_')}_daily_300.json"
        if not f.exists(): continue
        d = json.loads(f.read_text())
        if not d or len(d) < 120: continue
        for b in d:
            if 'date' not in b and 't' in b: b['date'] = str(b['t'])
        r = rb38.backtest_stock_v38(d, s)
        if r:
            all_t.extend(r['trades']); sr.append({'symbol': s, **r['perf']})
        if (i + 1) % 500 == 0:
            wr = sum(1 for t in all_t if t['won']) / max(1, len(all_t)) * 100
            print(f'  [{i+1:>4d}/{len(syms)}] {len(all_t):>5d} tr | {len(sr):>4d} st | WR={wr:.1f}% | {time.time()-t0:.0f}s')
    e = time.time() - t0
    if all_t:
        n = len(all_t); w = sum(1 for t in all_t if t['won'])
        wr = w/n*100; wp = sum(t['pnl_pct'] for t in all_t if t['won'])
        lp = abs(sum(t['pnl_pct'] for t in all_t if not t['won']))
        pf = wp/lp if lp > 0 else 999; rr = sum(t['rr'] for t in all_t)/n
        pnl = sum(t['pnl_pct'] for t in all_t)/n
        print(f'\nV42 FULL — {len(sr)}/{len(syms)} stocks | {e:.0f}s')
        print(f'Trades: {n} | WR: {wr:.1f}% | RR: {rr:.2f}x | PF: {pf:.0f} | P&L: {pnl:+.2f}%')
        for d in ['bull', 'bear']:
            dt = [t for t in all_t if t.get('direction') == d]
            if dt: print(f'  {d}: {len(dt)} tr | WR={sum(1 for t in dt if t["won"])/len(dt)*100:.1f}% | RR={sum(t["rr"] for t in dt)/len(dt):.2f}x')
        out.write_text(json.dumps({
            'config': 'V42 ATR-Adaptive Trailing (BE=0.20 LK=0.50)',
            'summary': {'n_stocks': len(sr), 'n_trades': n, 'win_rate': round(wr,1),
                       'avg_rr': round(rr,2), 'profit_factor': round(pf,2), 'avg_pnl': round(pnl,2)},
            'stock_results': sr,
        }, ensure_ascii=False, indent=1))
        print(f'Saved: {out}/v42_full.json')
    print(f'Time: {e:.0f}s ({e/60:.1f}min)')

if __name__ == '__main__': main()
