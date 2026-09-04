#!/usr/bin/env python3
"""V12 200-stock backtest — V467 trailing logic + V12 signals."""
import sys, json, os, time, math
sys.path.insert(0, '/root/.hermes/scripts/v11')
from signals_v12 import detect_all_signals_v12, calc_adaptive_thresholds

CACHE = '/root/.hermes/kline_cache_60min'
OUT = '/root/.hermes/smc_opt_v12'
ENABLE_BEAR = False
MIN_PROJ_RR = 6.0
OB_DISP = 1.0
PROGRESSIVE_BE = [(3, 0.0), (5, 0.3), (8, 0.5), (12, 1.0)]

os.makedirs(OUT, exist_ok=True)

def load_kline(code):
    p = os.path.join(CACHE, f'{code}_60min_200.json')
    with open(p) as f:
        raw = json.load(f)
    return raw if isinstance(raw, list) else raw.get('data', raw.get('klines', raw))

def backtest_stock(ohlcv, code, adaptive):
    """V12 signals + V467 trailing = clean exit with correct signal entry."""
    n = len(ohlcv)
    sigs = detect_all_signals_v12(ohlcv, {
        'adaptive': adaptive, 'ob_displacement_mult': OB_DISP,
        'require_volume': True,
    })
    ob_bull = sigs.get('OB_Bull', [])
    fvg_bull = sigs.get('FVG_Bull', [])
    sw_high = sigs.get('swing_highs', [])

    entries = []
    for sig in ob_bull:
        entries.append({'idx': sig['idx'], 'price': sig['price'], 'type': 'OB',
                        'upper': sig.get('upper', 0), 'lower': sig.get('lower', 0),
                        'strength': sig.get('strength', 0)})
    for sig in fvg_bull:
        entries.append({'idx': sig['idx'], 'price': (sig.get('upper',0) + sig.get('lower',0))/2,
                        'type': 'FVG', 'upper': sig.get('upper', 0), 'lower': sig.get('lower', 0),
                        'strength': sig.get('strength', 0)})
    entries.sort(key=lambda e: e['idx'])

    trades = []
    last_entry = -999
    cooldown = 8

    for e in entries:
        i = e['idx']
        if i - last_entry < cooldown:
            continue
        if i + 2 >= n:
            continue

        # Entry at confirmed bar close
        entry_bar = i + 1
        if entry_bar >= n:
            continue
        entry_price = ohlcv[entry_bar]['c']

        # Projected RR using nearest swing high
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

        # SL = 0.3% (V467 tight)
        sl_price = entry_price * 0.997
        sl_hit = False
        tp_hit = False
        won = False

        # Progressive trailing (V467)
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

            # Structure TP
            if proj_tp and high >= proj_tp and j > entry_bar:
                tp_hit = True
                exit_price = proj_tp
                won = True
                break

            # Progressive BE lock
            hold_bars = j - entry_bar
            for hb, lock_pct in PROGRESSIVE_BE:
                if hold_bars >= hb and not be_locked:
                    gain_pct = (best_price - entry_price) / entry_price * 100
                    if gain_pct >= lock_pct:
                        sl_adj = max(sl_adj, entry_price + lock_pct / 100 * entry_price)
                        be_locked = True

            # ATR-based trailing
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

        pnl_pct = (exit_price - entry_price) / entry_price * 100 if not sl_hit else (exit_price - entry_price) / entry_price * 100
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
        'total_pnl': round(pnl, 2), 'avg_hold': round(sum(t['hold'] for t in trades) / max(total, 1), 1),
        'pf': round(pf, 1),
        'entry_types': {},  # Simplified
    }

def main():
    stocks = sorted([f.split('_60min_200.json')[0] for f in os.listdir(CACHE) if f.endswith('_60min_200.json')])[:200]
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

    with open(f'{OUT}/v12_200_results.json', 'w') as f:
        json.dump({'results': results, 'config': {
            'displacement_mult': OB_DISP, 'min_proj_rr': MIN_PROJ_RR,
            'progressive_be': PROGRESSIVE_BE, 'stocks': len(results),
            'time': time.time() - start,
        }}, f, indent=2)

    tradable = [r for r in results if r['trades'] > 0]
    t = sum(r['trades'] for r in tradable); w = sum(r['wins'] for r in tradable)
    gain_t = sum(r['total_pnl'] for r in tradable if r['total_pnl'] > 0)
    loss_t = abs(sum(r['total_pnl'] for r in tradable if r['total_pnl'] < 0))
    print(f"\n=== V12 200-stock results ===")
    print(f"Stocks: {len(tradable)}/{len(results)} tradable, {t} trades")
    print(f"WR: {w/max(t,1)*100:.1f}%, P&L: {gain_t-loss_t:.2f}% ({gain_t}/{loss_t})")
    print(f"Avg trade/stock: {t/max(len(tradable),1):.1f}")
    print(f"Time: {time.time()-start:.0f}s")

if __name__ == '__main__':
    main()
