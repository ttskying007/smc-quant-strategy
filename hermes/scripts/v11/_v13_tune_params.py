#!/usr/bin/env python3
"""Tune V13 fallback params side-by-side on 200 stocks.
Creates parameterized fallback OB functions to compare coverage vs WR."""
import sys, json, time
from pathlib import Path
from collections import Counter

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v12 import (
    detect_swings_v13_60min, calc_adaptive_thresholds, Signal,
    _quick_sh, _quick_sl
)
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.v474_engine import (
    load_ohlcv, calc_stock_params_v45, evaluate_v45_entry,
    TRADE_SIGNAL_TYPES
)

SYMBOLS = [
    '600519.SH','000858.SZ','002415.SZ','000001.SZ','300750.SZ',
    '600036.SH','000333.SZ','601318.SH','600276.SH','002475.SZ',
    '688981.SH','300059.SZ','002594.SZ','300760.SZ','600809.SH',
    '000568.SZ','002304.SZ','600887.SH','600690.SH','600585.SH',
    '601166.SH','000002.SZ','002714.SZ','300015.SZ','002230.SZ',
    '603259.SH','601012.SH','600030.SH','002142.SZ','600900.SH',
    '688036.SH','002352.SZ','601899.SH','600438.SH','300124.SZ',
    '603288.SH','000725.SZ','002460.SZ','600309.SH','601088.SH',
    '002466.SZ','300274.SZ','002812.SZ','300896.SZ','000661.SZ',
    '600031.SH','600436.SH','002371.SZ','300413.SZ','688111.SH',
    '601995.SH','688012.SH','002049.SZ','300347.SZ','002920.SZ',
    '300450.SZ','002821.SZ','603986.SH','688396.SH','300661.SZ',
    '688981.SH','300782.SZ','688169.SH','688256.SH','688008.SH',
    '300751.SZ','688599.SH','688005.SH','688390.SH','300502.SZ',
    '688561.SH','300957.SZ','601633.SH','002920.SZ','603501.SH',
    '300122.SZ','688126.SH','688187.SH','601225.SH','601728.SH',
    '600941.SH','688981.SH','688303.SH','688686.SH','688772.SH',
    '688819.SH','688536.SH','688200.SH','688029.SH','688301.SH',
    '688095.SH','688139.SH','688188.SH','688036.SH','688777.SH',
    '688520.SH','688065.SH','688122.SH','688289.SH','688533.SH',
    '688385.SH','688609.SH','688330.SH','688698.SH','688018.SH',
    '688526.SH','688516.SH','688568.SH','688185.SH','688778.SH',
    '688186.SH','688180.SH','688100.SH','688208.SH','688488.SH',
    '688608.SH','688028.SH','688466.SH','688131.SH','688202.SH',
    '688800.SH','688383.SH','688981.SH','688116.SH','688363.SH',
    '688016.SH','688981.SH','688639.SH','688087.SH','688981.SH',
    '688981.SH','688981.SH','688981.SH','688981.SH','688981.SH',
]

# ── Parameter combos ──
COMBOS = {
    'A_current':  {'body': 0.10, 'dis': 0.7,  'near_w': 5, 'vol': 0.3},
    'B_medium':   {'body': 0.12, 'dis': 0.8,  'near_w': 4, 'vol': 0.4},
    'C_tighter':  {'body': 0.15, 'dis': 0.8,  'near_w': 4, 'vol': 0.5},
    'D_strict':   {'body': 0.15, 'dis': 1.0,  'near_w': 3, 'vol': 0.5},
    'E_light':    {'body': 0.10, 'dis': 0.8,  'near_w': 5, 'vol': 0.3},
    'F_balanced': {'body': 0.12, 'dis': 0.7,  'near_w': 4, 'vol': 0.5},
}


def make_param_fallback(body_min, dis_min, near_w, vol_min):
    """Create a parameterized V13 OB detection with custom fallback params."""
    def _run(ohlcv, adaptive=None, swings=None, tf='60min'):
        n = len(ohlcv)
        if n < 30:
            return []
        if adaptive is None:
            adaptive = calc_adaptive_thresholds(ohlcv)
        vol_median = adaptive['vol_median']

        # Step 1: swing-backward with relaxed primary
        primary_obs = []
        try:
            from v11.signals_v12 import detect_ob_v12
            primary_obs = detect_ob_v12(
                ohlcv, adaptive=adaptive, require_volume=True,
                displacement_mult=1.0, swings=swings, tf=tf,
                body_pct_min=0.08,
            )
        except:
            pass

        # Step 2: Fallback with our custom params
        sh = _quick_sh(ohlcv, 8)
        sl = _quick_sl(ohlcv, 8)
        swing_near_idxs = set(i for i, _ in sh + sl)
        processed = set(s.get('idx', -1) for s in primary_obs)

        fallback = []
        for i in range(5, n - 3):
            if i in processed:
                continue
            bar = ohlcv[i]
            body = abs(bar['c'] - bar['o'])
            if body == 0:
                continue
            body_pct = body / max(bar['o'], 0.01) * 100
            if body_pct < body_min:
                continue
            bar_range = bar['h'] - bar['l']
            if bar_range <= 0:
                continue

            near_sw = any(abs(i - si) <= near_w for si in swing_near_idxs)
            if not near_sw:
                continue

            # Bullish OB
            if bar['c'] < bar['o']:
                max_fwd = max(b['h'] for b in ohlcv[i+1:min(i+12, n)])
                displacement = max_fwd - bar['l']
                dis_ratio = displacement / max(bar_range, 0.001)
                if dis_ratio >= dis_min:
                    if ohlcv[i+1]['c'] <= ohlcv[i+1]['o']:
                        continue
                    imp = 0
                    for j in range(i+1, min(i+6, n)):
                        if ohlcv[j]['c'] > ohlcv[j]['o']:
                            imp += 1
                        else:
                            break
                    if imp >= 1:
                        vol_ok = bar['v'] > vol_median * vol_min
                        if not vol_ok:
                            continue
                        sig = Signal(type='OB_Bull', idx=i, direction='bull',
                            price=bar['l'], upper=bar['h'], lower=bar['l'],
                            timeframe=tf, confirmed_at=i+1,
                            volume_ratio=round(bar['v']/max(vol_median,1),2))
                        sig.strength = min(6, 1.5 + dis_ratio*1.0 + min(1, imp*0.3))
                        sig.confidence = min(0.60, 0.20 + dis_ratio*0.04 + (0.05 if vol_ok else 0))
                        sig.metadata = {'body_pct': round(body_pct,2), 'impulse_bars': imp,
                            'displacement_ratio': round(dis_ratio,2), 'ob_method': 'v13_param_tune',
                            'params': f'b={body_min:.2f}_d={dis_min:.1f}_n={near_w}_v={vol_min:.1f}'}
                        fallback.append(sig)
                        processed.add(i)

            # Bearish OB
            elif bar['c'] > bar['o']:
                min_fwd = min(b['l'] for b in ohlcv[i+1:min(i+12, n)])
                displacement = bar['h'] - min_fwd
                dis_ratio = displacement / max(bar_range, 0.001)
                if dis_ratio >= dis_min:
                    if ohlcv[i+1]['c'] >= ohlcv[i+1]['o']:
                        continue
                    imp = 0
                    for j in range(i+1, min(i+6, n)):
                        if ohlcv[j]['c'] < ohlcv[j]['o']:
                            imp += 1
                        else:
                            break
                    if imp >= 1:
                        vol_ok = bar['v'] > vol_median * vol_min
                        if not vol_ok:
                            continue
                        sig = Signal(type='OB_Bear', idx=i, direction='bear',
                            price=bar['h'], upper=bar['h'], lower=bar['l'],
                            timeframe=tf, confirmed_at=i+1,
                            volume_ratio=round(bar['v']/max(vol_median,1),2))
                        sig.strength = min(6, 1.5 + dis_ratio*1.0 + min(1, imp*0.3))
                        sig.confidence = min(0.60, 0.20 + dis_ratio*0.04 + (0.05 if vol_ok else 0))
                        sig.metadata = {'body_pct': round(body_pct,2), 'impulse_bars': imp,
                            'displacement_ratio': round(dis_ratio,2), 'ob_method': 'v13_param_tune'}
                        fallback.append(sig)
                        processed.add(i)

        return primary_obs + fallback
    return _run


def make_full_detector(ob_fn):
    """Wrap OB function into full signal detection."""
    def detect_all(ohlcv, params=None, tf='60min'):
        if params is None:
            params = {}
        adaptive = calc_adaptive_thresholds(ohlcv)
        swings = detect_swings_v13_60min(ohlcv)
        obs = ob_fn(ohlcv, adaptive=adaptive, swings=swings, tf=tf)

        from v11.signals_v12 import (
            detect_fvg_v11, detect_ifvg_v11, detect_sweep_v11, detect_cho_ch_v11,
            detect_mss_v11, detect_bpr_v11, detect_po3_v11, detect_ote_v11,
            detect_eql_v11, detect_rj_v11, detect_lv_v11, detect_mfvg_v11,
            detect_breaker_block_v11
        )
        all_signals = list(obs)
        all_signals.extend(detect_fvg_v11(ohlcv, adaptive=adaptive, tf=tf))
        all_signals.extend(detect_ifvg_v11(ohlcv, tf=tf))
        all_signals.extend(detect_sweep_v11(ohlcv, swings=swings, tf=tf))
        all_signals.extend(detect_cho_ch_v11(ohlcv, swings=swings, adaptive=adaptive, tf=tf))
        all_signals.extend(detect_mss_v11(ohlcv, swings=swings, adaptive=adaptive, tf=tf))
        all_signals.extend(detect_bpr_v11(ohlcv, tf=tf))
        all_signals.extend(detect_po3_v11(ohlcv, tf=tf))
        all_signals.extend(detect_ote_v11(ohlcv, adaptive=adaptive, tf=tf))
        all_signals.extend(detect_eql_v11(ohlcv, swings=swings, tf=tf))
        all_signals.extend(detect_rj_v11(ohlcv, tf=tf))
        all_signals.extend(detect_lv_v11(ohlcv, tf=tf))
        all_signals.extend(detect_mfvg_v11(ohlcv, tf=tf))
        all_signals.extend(detect_breaker_block_v11(ohlcv, swings=swings, tf=tf))

        # Dedup by (idx, type)
        seen = set()
        deduped = []
        for s in all_signals:
            k = (s.idx, s.type)  # Signal may be dict or object
            if isinstance(s, dict):
                k = (s.get('idx',0), s.get('type',''))
            else:
                k = (s.idx, s.type)
            if k not in seen:
                seen.add(k)
                deduped.append(s)

        # Sort by idx
        if deduped and hasattr(deduped[0], 'id'):
            deduped.sort(key=lambda s: s.idx)
        else:
            deduped.sort(key=lambda s: s.get('idx',0) if isinstance(s, dict) else s.idx)

        return {'all': deduped, 'obs': obs, 'signals': deduped}
    return detect_all


# ── Run all combos ──
unique_symbols = list(dict.fromkeys(SYMBOLS))  # dedup preserving order
print(f"Testing {len(unique_symbols)} unique symbols across {len(COMBOS)} parameter combos")
print()

results = {}
t_total = time.time()

for combo_name, params in COMBOS.items():
    print(f"\n{'='*60}")
    print(f"  Combo {combo_name}: body>={params['body']:.0%} dis>={params['dis']:.1f}x near_w={params['near_w']} vol>{params['vol']:.1f}x")
    print(f"{'='*60}")

    ob_fn = make_param_fallback(params['body'], params['dis'], params['near_w'], params['vol'])
    detect_all = make_full_detector(ob_fn)

    all_trades, tradeable_stocks = [], 0
    used_stock_ids = set()
    t0 = time.time()

    for idx, sym in enumerate(unique_symbols):
        ohlcv = load_ohlcv(sym)
        if not ohlcv or len(ohlcv) < 60:
            continue
        n = len(ohlcv)
        stock_params = calc_stock_params_v45(ohlcv, sym)
        base_params = {'fvg_min_width': None, 'sweep_lookback': 12}

        signals_result = detect_all(ohlcv, params=base_params, tf='60min')
        all_signals = signals_result.get('all', [])

        if not all_signals or len(all_signals) < 3:
            continue

        # Count how many of the signals are OBs for coverage tracking
        ob_count = sum(1 for s in all_signals if isinstance(s, dict) and 'OB' in s.get('type','') or hasattr(s, 'type') and 'OB' in s.type)

        trades, used_bars = [], set()
        for sig in all_signals:
            sig_idx = sig.get('idx', 0) if isinstance(sig, dict) else getattr(sig, 'idx', 0)
            sig_type = sig.get('type', '') if isinstance(sig, dict) else getattr(sig, 'type', '')
            direction = sig.get('direction', '') if isinstance(sig, dict) else getattr(sig, 'direction', '')

            if sig_type not in TRADE_SIGNAL_TYPES:
                continue
            if 'OB' not in sig_type:
                continue
            if sig_idx < 40 or sig_idx >= n - 10:
                continue

            sigs_up_to = [s for s in all_signals if (s.get('idx',0) if isinstance(s,dict) else s.idx) <= sig_idx]
            result = evaluate_v45_entry(all_signals, sigs_up_to, sig, ohlcv, n,
                                         direction, base_params, stock_params)
            if result:
                if result['entry_idx'] in used_bars:
                    continue
                used_bars.add(result['entry_idx'])
                trades.append(result)

        if len(trades) >= 2:
            tradeable_stocks += 1
            all_trades.extend(trades)

    elapsed = time.time() - t0
    if all_trades:
        n = len(all_trades)
        wins = sum(1 for t in all_trades if t['won'])
        wr = wins / n * 100
        wp = sum(t['pnl_pct'] for t in all_trades if t['won'])
        lp = abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
        pf = wp / lp if lp > 0 else 999
        rr = sum(t['rr'] for t in all_trades) / n
        pnl = sum(t['pnl_pct'] for t in all_trades) / n

        results[combo_name] = {
            'stocks': tradeable_stocks,
            'trades': n,
            'WR': round(wr, 1),
            'RR': round(rr, 2),
            'PF': round(pf, 1),
            'P&L': round(pnl, 2),
            'time': round(elapsed, 0),
            'params': params,
        }
        print(f"  => {tradeable_stocks} stocks, {n} trades, WR={wr:.1f}%, RR={rr:.2f}x, PF={pf:.0f}, P&L={pnl:+.2f}% [{elapsed:.0f}s]")
    else:
        results[combo_name] = {'stocks': 0, 'trades': 0, 'WR': 0, 'RR': 0, 'PF': 0, 'P&L': 0, 'time': round(elapsed,0), 'params': params}
        print(f"  => 0 trades")

# ── Summary ──
print(f"\n\n{'='*70}")
print(f"  PARAM TUNE SUMMARY — {len(unique_symbols)} stocks")
print(f"{'='*70}")
print(f"  {'Combo':12s} {'body':>5s} {'dis':>4s} {'near':>4s} {'vol':>4s} {'Stocks':>6s} {'Trades':>6s} {'WR%':>6s} {'RR':>6s} {'PF':>6s}")
print(f"  {'-'*70}")
for cname, r in sorted(results.items(), key=lambda x: -x[1].get('WR', 0)):
    p = r['params']
    print(f"  {cname:12s} {p['body']:5.2f} {p['dis']:4.1f} {p['near_w']:4d} {p['vol']:4.1f} {r['stocks']:6d} {r['trades']:6d} {r['WR']:6.1f} {r['RR']:6.2f} {r['PF']:>6.0f}")
print(f"{'='*70}")

total_elapsed = time.time() - t_total
print(f"\nTotal time: {total_elapsed:.0f}s")

out = Path('/root/.hermes/smc_opt_v474/v13_param_tune.json')
out.write_text(json.dumps(results, indent=2))
print(f"Saved to {out}")
