#!/usr/bin/env python3
"""Phase 2 Quality Backtest: validate each filter dimension on full market.
For every POI-retrace trade record features:
  zone_type, entry_in_zone, sl_pct bin, retrace_depth, sweep_tag, market_state
Then report WR / avg PnL per bucket so filters are data-driven, not guessed.
"""
import json, sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
sys.path.insert(0, '/root/.hermes/scripts/v11')
sys.path.insert(0, '/root/.hermes/scripts/v25')

KLINE_DIR = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v25/phase2_quality_backtest.json')

from signals_v22 import detect_all_signals_v22

N_STOCKS = int(sys.argv[1]) if len(sys.argv) > 1 else 0  # 0 = all


def compute_atr(klines, bar, n=14):
    start = max(1, bar - n)
    trs = []
    for i in range(start, bar + 1):
        hi = klines[i].get('h', 0); lo = klines[i].get('l', 0)
        pc = klines[i - 1].get('c', lo)
        trs.append(max(hi - lo, abs(hi - pc), abs(lo - pc)))
    return sum(trs) / max(1, len(trs))


def ma(klines, idx, p=20):
    cs = [klines[i].get('c', 0) for i in range(max(0, idx - p + 1), idx + 1)]
    return sum(cs) / len(cs) if cs else 0


def market_state(klines, idx):
    if idx < 30: return 'UNDEFINED'
    ep = klines[idx].get('c', 0)
    a = compute_atr(klines, idx)
    ap = a / ep * 100 if ep > 0 else 0
    m20 = ma(klines, idx); m20p = ma(klines, max(14, idx - 10))
    slope = (m20 - m20p) / m20p * 100 if m20p > 0 else 0
    if ap > 5: return 'HIGH_VOL'
    if ap < 1.5: return 'LOW_VOL'
    if slope > 1: return 'TREND_UP'
    if slope < -1: return 'TREND_DOWN'
    return 'RANGE'


def simulate(klines, entry_bar, entry_price, sl, tp1):
    n = len(klines); max_hold = 60
    for i in range(entry_bar + 1, min(entry_bar + max_hold, n)):
        lo = klines[i].get('l', 0); hi = klines[i].get('h', 0)
        if lo <= sl:
            return {'pnl_pct': (sl / entry_price - 1) * 100, 'exit': 'SL_HIT', 'hold': i - entry_bar}
        if hi >= tp1:
            return {'pnl_pct': (tp1 / entry_price - 1) * 100, 'exit': 'TP1_HIT', 'hold': i - entry_bar}
    if entry_bar + max_hold < n:
        ep2 = klines[entry_bar + max_hold].get('c', 0)
        return {'pnl_pct': (ep2 / entry_price - 1) * 100, 'exit': 'TIME_STOP', 'hold': max_hold}
    return None


def main():
    kfiles = sorted(KLINE_DIR.glob('*_daily_750.json'))
    if N_STOCKS > 0:
        kfiles = kfiles[:N_STOCKS]
    print(f"Quality backtest on {len(kfiles)} stocks at {datetime.now():%H:%M:%S}")
    trades = []
    for ki, kf in enumerate(kfiles):
        if ki % 500 == 0 and ki > 0:
            print(f"  {ki}/{len(kfiles)} ({len(trades)} trades)...", flush=True)
        sym = kf.stem.replace('_daily_750', '')
        symbol = sym.replace('_SH', '.SH').replace('_SZ', '.SZ').replace('_BJ', '.BJ')
        try:
            klines = json.loads(kf.read_text())
        except Exception:
            continue
        if len(klines) < 100: continue
        for b in klines:
            for k in ('o', 'h', 'l', 'c', 'v'):
                if k in b: b[k] = float(b[k])
        try:
            sigs, summary, swings, sig_dict = detect_all_signals_v22(klines)
        except Exception:
            continue
        if not sigs: continue
        sweeps = [s for s in sigs if 'Sweep' in getattr(s, 'type', '')]
        confirms = [s for s in sigs if getattr(s, 'type', '') in ('BOS_Bull', 'CHOCH_Bull')]
        seen = set()
        for sig in sigs:
            st = getattr(sig, 'type', '')
            if st not in ('OB_Bull', 'FVG_Bull'): continue
            zbar = getattr(sig, 'bar', getattr(sig, 'idx', 0))
            if zbar < 30 or zbar >= len(klines) - 65: continue
            key = (zbar, st)
            if key in seen: continue
            seen.add(key)
            if hasattr(sig, 'meta') and sig.meta:
                zlow = sig.meta.get('ob_low', klines[zbar].get('l', 0))
                zhigh = sig.meta.get('ob_high', klines[zbar].get('h', 0))
            else:
                zlow = klines[zbar].get('l', 0); zhigh = klines[zbar].get('h', 0)
            if zlow <= 0 or zhigh <= zlow: continue
            # require structure confirm after zone (mirror daily_scan)
            def sbar(x):
                return getattr(x, 'bar', getattr(x, 'idx', 0))
            conf = next((c for c in confirms if zbar < sbar(c) <= zbar + 30), None)
            if conf is None: continue
            atr = compute_atr(klines, zbar)
            sl = min(zlow - atr * 0.5, zlow * 0.995)
            risk = abs(zlow - sl) / zlow * 100
            if risk < 0.5: risk = 1.5
            tp1 = zhigh * (1 + risk * 1.5 / 100)
            # POI retrace entry
            for eb in range(zbar + 3, min(zbar + 31, len(klines) - 5)):
                lo = klines[eb].get('l', 0); hi = klines[eb].get('h', 0)
                if lo > zhigh: continue
                if lo < zlow * 0.95: break
                if lo <= zhigh and hi >= zlow:
                    ep = klines[eb].get('c', 0)
                    if ep <= 0: break
                    r = simulate(klines, eb, ep, sl, tp1)
                    if r:
                        sl_pct = abs(ep - sl) / ep * 100
                        in_zone = ep <= zhigh
                        above_pct = (ep / zhigh - 1) * 100
                        retr = max(0.0, min(100.0, (zhigh - lo) / max(zhigh - zlow, 1e-9) * 100))
                        conf_bar = sbar(conf)
                        has_sweep = any(s for s in sweeps if conf_bar - 15 <= sbar(s) < conf_bar)
                        ms = market_state(klines, eb)
                        trades.append({
                            'symbol': symbol, 'zone_type': st,
                            'sl_pct': round(sl_pct, 2), 'in_zone': in_zone,
                            'above_pct': round(above_pct, 2),
                            'retrace_pct': round(retr, 1),
                            'sweep': has_sweep, 'state': ms,
                            'conf_conf': round(getattr(conf, 'confidence', 0), 3),
                            **r,
                        })
                    break
    print(f"\nTotal trades: {len(trades)}")

    def bucket_report(name, keyfn):
        groups = defaultdict(list)
        for t in trades:
            groups[keyfn(t)].append(t)
        rows = []
        for k in sorted(groups, key=lambda x: str(x)):
            g = groups[k]
            wins = sum(1 for t in g if t['pnl_pct'] > 0)
            wr = wins / len(g) * 100
            avg = sum(t['pnl_pct'] for t in g) / len(g)
            rows.append({'bucket': str(k), 'n': len(g), 'wr': round(wr, 1), 'avg_pnl': round(avg, 3)})
            print(f"  {name}={k}: n={len(g)} WR={wr:.1f}% avg={avg:+.3f}%")
        return rows

    print("\n=== Bucket Analysis ===")
    report = {}
    print("\n[zone_type]"); report['zone_type'] = bucket_report('zone', lambda t: t['zone_type'])
    print("\n[in_zone]"); report['in_zone'] = bucket_report('in_zone', lambda t: t['in_zone'])
    def slbin(t):
        s = t['sl_pct']
        if s < 1: return 'a_<1%'
        if s < 2: return 'b_1-2%'
        if s < 3: return 'c_2-3%'
        if s < 5: return 'd_3-5%'
        return 'e_>5%'
    print("\n[sl_pct]"); report['sl_pct'] = bucket_report('sl', slbin)
    def rbin(t):
        r = t['retrace_pct']
        if r < 30: return 'a_<30'
        if r < 60: return 'b_30-60'
        if r < 90: return 'c_60-90'
        return 'd_90-100'
    print("\n[retrace]"); report['retrace'] = bucket_report('retr', rbin)
    print("\n[sweep]"); report['sweep'] = bucket_report('sweep', lambda t: t['sweep'])
    print("\n[state]"); report['state'] = bucket_report('state', lambda t: t['state'])
    def cbin(t):
        c = t['conf_conf']
        if c < 0.5: return 'a_<0.5'
        if c < 0.7: return 'b_0.5-0.7'
        return 'c_>=0.7'
    print("\n[conf_confidence]"); report['conf_confidence'] = bucket_report('conf', cbin)

    # Combined filter test: in_zone + sl>=1% + various combos
    def combo(label, fn):
        g = [t for t in trades if fn(t)]
        if not g:
            print(f"  {label}: n=0"); return {'label': label, 'n': 0}
        wins = sum(1 for t in g if t['pnl_pct'] > 0)
        wr = wins / len(g) * 100
        avg = sum(t['pnl_pct'] for t in g) / len(g)
        cum = sum(t['pnl_pct'] for t in g)
        print(f"  {label}: n={len(g)} WR={wr:.1f}% avg={avg:+.3f}% cum={cum:+.1f}%")
        return {'label': label, 'n': len(g), 'wr': round(wr, 1), 'avg_pnl': round(avg, 3), 'cum': round(cum, 1)}

    print("\n=== Combined Filters ===")
    combos = []
    combos.append(combo('BASELINE(all)', lambda t: True))
    combos.append(combo('in_zone', lambda t: t['in_zone']))
    combos.append(combo('sl>=1%', lambda t: t['sl_pct'] >= 1))
    combos.append(combo('in_zone+sl>=1%', lambda t: t['in_zone'] and t['sl_pct'] >= 1))
    combos.append(combo('in_zone+sl1-5%', lambda t: t['in_zone'] and 1 <= t['sl_pct'] <= 5))
    combos.append(combo('OB_only', lambda t: t['zone_type'] == 'OB_Bull'))
    combos.append(combo('in_zone+sl1-5%+OB', lambda t: t['in_zone'] and 1 <= t['sl_pct'] <= 5 and t['zone_type'] == 'OB_Bull'))
    combos.append(combo('in_zone+sl1-5%+sweep', lambda t: t['in_zone'] and 1 <= t['sl_pct'] <= 5 and t['sweep']))
    combos.append(combo('in_zone+sl1-5%+!TREND_DOWN', lambda t: t['in_zone'] and 1 <= t['sl_pct'] <= 5 and t['state'] != 'TREND_DOWN'))
    combos.append(combo('PRODUCTION_GATE(in_zone+sl>=1%+retr<60)', lambda t: t['in_zone'] and t['sl_pct'] >= 1 and t['retrace_pct'] < 60))
    combos.append(combo('PRODUCTION_GATE_FVG', lambda t: t['in_zone'] and t['sl_pct'] >= 1 and t['retrace_pct'] < 60 and t['zone_type'] == 'FVG_Bull'))
    combos.append(combo('PRODUCTION_GATE_OB', lambda t: t['in_zone'] and t['sl_pct'] >= 1 and t['retrace_pct'] < 60 and t['zone_type'] == 'OB_Bull'))
    combos.append(combo('in_zone+sl1-5%+retr<60', lambda t: t['in_zone'] and 1 <= t['sl_pct'] <= 5 and t['retrace_pct'] < 60))
    combos.append(combo('in_zone+sl1-5%+retr30-90', lambda t: t['in_zone'] and 1 <= t['sl_pct'] <= 5 and 30 <= t['retrace_pct'] < 90))
    report['combos'] = combos

    OUT.write_text(json.dumps({
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'n_stocks': len(kfiles), 'n_trades': len(trades),
        'buckets': report,
    }, ensure_ascii=False, indent=2))
    print(f"\nSaved: {OUT}")


if __name__ == '__main__':
    main()
