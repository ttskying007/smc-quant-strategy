#!/usr/bin/env python3
"""
Compare V11 vs V12 signal engines with V467 trailing logic.
SWITCH = 'v11' or 'v12' at line 13 to toggle.
"""
import sys, json, os, time, math
sys.path.insert(0, '/root/.hermes/scripts/v11')

# ── ENGINE SELECT ──────────────────────────────────────────────────
SWITCH = 'v12'  # Current engine
# ───────────────────────────────────────────────────────────────────

CACHE = '/root/.hermes/kline_cache_60min'
OUT = '/root/.hermes/smc_opt_v12'
ENABLE_BEAR = False
MIN_PROJ_RR = 6.0
OB_DISP = 1.0
PROGRESSIVE_BE = [(3, 0.0), (5, 0.3), (8, 0.5), (12, 1.0)]

os.makedirs(OUT, exist_ok=True)

if SWITCH == 'v12':
    from signals_v12 import detect_all_signals_v12 as detect_signals, calc_adaptive_thresholds
else:
    from signals_v11 import detect_all_signals_v11 as detect_signals, calc_adaptive_thresholds


def load_kline(code):
    p = os.path.join(CACHE, f'{code}_60min_200.json')
    with open(p) as f:
        raw = json.load(f)
    return raw if isinstance(raw, list) else raw.get('data', raw.get('klines', raw))


def _quick_swing_highs(ohlcv, lookback=12):
    n = len(ohlcv)
    return [(i, ohlcv[i]['h']) for i in range(lookback, n - lookback)
            if all(ohlcv[i]['h'] >= ohlcv[j]['h']
                   for j in range(i - lookback, i + lookback + 1) if 0 <= j < n)]

def extract_entries(sigs, ohlcv):
    """Get bull signal entries from either V11 or V12 signal format."""
    n = len(ohlcv)
    entries = []
    sw_high = []

    # V12 format: {'OB_Bull': [...], 'swing_highs': [{'idx':i,'price':p}, ...]}
    if 'OB_Bull' in sigs:
        for s in sigs.get('OB_Bull', []):
            entries.append({'idx': s['idx'], 'price': s['price'], 'type': 'OB',
                            'upper': s.get('upper', 0), 'lower': s.get('lower', 0),
                            'strength': s.get('strength', 0)})
        for s in sigs.get('FVG_Bull', []):
            entries.append({'idx': s['idx'], 'price': (s.get('upper', 0) + s.get('lower', 0)) / 2,
                            'type': 'FVG', 'upper': s.get('upper', 0), 'lower': s.get('lower', 0),
                            'strength': s.get('strength', 0)})
        sw_high = sigs.get('swing_highs', [])

    # V11 format: {'ob': [{'type':'OB_Bull','idx':i,...}], 'fvg': [...], 'fvg_bull': [...]}
    elif 'ob' in sigs:
        for s in sigs.get('ob', []):
            if 'Bull' in s.get('type', ''):
                entries.append({'idx': s['idx'], 'price': s['price'], 'type': 'OB',
                                'upper': s.get('upper', 0), 'lower': s.get('lower', 0),
                                'strength': s.get('strength', 0)})
        for s in sigs.get('fvg', []):
            if 'Bull' in s.get('type', ''):
                entries.append({'idx': s['idx'], 'price': (s.get('upper', 0) + s.get('lower', 0)) / 2,
                                'type': 'FVG', 'upper': s.get('upper', 0), 'lower': s.get('lower', 0),
                                'strength': s.get('strength', 0)})
        # V11 doesn't return swing_highs — compute locally
        raw_sh = _quick_swing_highs(ohlcv)
        sw_high = [{'idx': i, 'price': p} for i, p in raw_sh]

    entries.sort(key=lambda e: e['idx'])
    return entries, sw_high


def backtest_stock(ohlcv, code, adaptive):
    n = len(ohlcv)
    sigs = detect_signals(ohlcv, {
        'adaptive': adaptive, 'require_volume': True,
    })

    entries, sw_high = extract_entries(sigs, ohlcv)

    trades = []
    last_entry = -999
    cooldown = 8

    for e in entries:
        i = e['idx']
        if i - last_entry < cooldown:
            continue
        if i + 2 >= n:
            continue

        entry_bar = i + 1
        if entry_bar >= n:
            continue
        entry_price = ohlcv[entry_bar]['c']

        # Projected RR
        proj_tp = None
        for sh in sw_high:
            if sh['idx'] > i:
                proj_tp = sh['price']
                break
        if proj_tp is None or proj_tp <= entry_price:
            continue
        proj_rr = (proj_tp - entry_price) / max(entry_price * 0.003, 0.001)
        if proj_rr < MIN_PROJ_RR:
            continue

        sl_price = entry_price * 0.997
        sl_hit = False
        tp_hit = False
        won = False

        best_price = entry_price
        be_locked = False
        sl_adj = sl_price

        for j in range(entry_bar + 1, n):
            bar = ohlcv[j]
            low, high = bar['l'], bar['h']

            if low <= sl_adj:
                sl_hit = True
                exit_price = sl_adj
                won = False
                break

            if high > best_price:
                best_price = high

            if proj_tp and high >= proj_tp and j > entry_bar:
                tp_hit = True
                exit_price = proj_tp
                won = True
                break

            hold_bars = j - entry_bar
            for hb, lock_pct in PROGRESSIVE_BE:
                if hold_bars >= hb and not be_locked:
                    gain_pct = (best_price - entry_price) / entry_price * 100
                    if gain_pct >= lock_pct:
                        sl_adj = max(sl_adj, entry_price + lock_pct / 100 * entry_price)
                        be_locked = True

            gain_pct = (best_price - entry_price) / entry_price * 100
            if gain_pct >= 0.5:
                sl_adj = max(sl_adj, entry_price + 0.001 * entry_price)
            if gain_pct >= 1.0:
                sl_adj = max(sl_adj, entry_price + 0.003 * entry_price)
            if gain_pct >= 2.0:
                sl_adj = max(sl_adj, entry_price + 0.01 * entry_price)
            if gain_pct >= 4.0:
                sl_adj = max(sl_adj, best_price * 0.99)

            if j == n - 1:
                exit_price = ohlcv[j]['c']
                won = ohlcv[j]['c'] > entry_price
                break

        pnl_pct = (exit_price - entry_price) / entry_price * 100
        trades.append({
            'entry_bar': entry_bar, 'entry_price': round(entry_price, 2),
            'exit_bar': j, 'exit_price': round(exit_price, 2),
            'pnl_pct': round(pnl_pct, 2), 'won': won,
            'entry_type': e['type'], 'proj_rr': round(proj_rr, 1),
            'hold': j - entry_bar,
            'exit_method': 'tp' if tp_hit else 'sl' if sl_hit else 'trailing',
        })
        last_entry = i

    wins = sum(1 for t in trades if t['won'])
    total = len(trades)
    pnl = sum(t['pnl_pct'] for t in trades)
    gain = sum(t['pnl_pct'] for t in trades if t['won'])
    loss = sum(abs(t['pnl_pct']) for t in trades if not t['won'])
    rr = (gain / max(wins, 1)) / (loss / max(total - wins, 1)) if loss > 0 else 0
    pf = gain / max(loss, 0.001)

    return {
        'code': code, 'trades': total, 'wins': wins,
        'win_rate': round(wins / max(total, 1) * 100, 1),
        'avg_rr': round(rr, 2), 'avg_pnl': round(pnl / max(total, 1), 2),
        'total_pnl': round(pnl, 2),
        'avg_hold': round(sum(t['hold'] for t in trades) / max(total, 1), 1),
        'pf': round(pf, 1),
    }


def main():
    stocks = sorted([f.split('_60min_200.json')[0]
                     for f in os.listdir(CACHE) if f.endswith('_60min_200.json')])[:200]
    results = []
    start = time.time()

    for idx, code in enumerate(stocks):
        t0 = time.time()
        try:
            ohlcv = load_kline(code)
            adaptive = calc_adaptive_thresholds(ohlcv)
            r = backtest_stock(ohlcv, code, adaptive)
            results.append(r)
            print(f"[{idx+1}/200] {code}: {r['trades']} trades, WR={r['win_rate']}%, RR={r['avg_rr']}x P&L={r['total_pnl']}% ({time.time()-t0:.1f}s)", flush=True)
        except Exception as ex:
            print(f"[{idx+1}/200] {code}: ERROR - {ex}", flush=True)

    tag = f"v{SWITCH}"
    with open(f'{OUT}/{tag}_200_results.json', 'w') as f:
        json.dump({'results': results, 'config': {
            'engine': SWITCH, 'min_proj_rr': MIN_PROJ_RR,
            'progressive_be': PROGRESSIVE_BE, 'stocks': len(results),
            'time': time.time() - start,
        }}, f, indent=2)

    tradable = [r for r in results if r['trades'] > 0]
    t = sum(r['trades'] for r in tradable)
    w = sum(r['wins'] for r in tradable)
    gain_t = sum(r['total_pnl'] for r in tradable if r['total_pnl'] > 0)
    loss_t = abs(sum(r['total_pnl'] for r in tradable if r['total_pnl'] < 0))
    print(f"\n=== V{SWITCH.upper()} 200-stock results ===")
    print(f"Stocks: {len(tradable)}/{len(results)} tradable, {t} trades")
    print(f"WR: {w/max(t,1)*100:.1f}%, P&L: {gain_t-loss_t:.2f}% ({gain_t}/{loss_t})")
    print(f"Avg trade/stock: {t/max(len(tradable),1):.1f}")
    print(f"Time: {time.time()-start:.0f}s")


if __name__ == '__main__':
    main()
