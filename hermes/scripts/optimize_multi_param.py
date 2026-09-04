#!/usr/bin/env python3
"""
每股多参数优化器 — 搜索最优参数组合(入场阈值/趋势阈值/信号质量阈值/FVG gap)
基于V13/V14快速引擎架构

参数空间:
  - entry_threshold: [0.55, 0.60, 0.65, 0.70]  (共振入场阈值)
  - trend_threshold: [0.5, 0.8, 1.0, 1.5]       (趋势强度%)
  - vol_multiplier:  [0.6, 0.8, 1.0]             (成交量>均量的倍数)
  - fvg_gap_min:     [0.2, 0.3, 0.5]             (FVG最小gap%)
  - 共: 4 x 4 x 3 x 3 = 144组合
  
优化策略: 随机采样+精英选择(类似V8.4)
每次只随机采样30组合, 选TOP5扩精, 迭代6轮
"""
import json, sys, time, random
from pathlib import Path
from collections import Counter
from datetime import datetime
sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v14')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SL_OPTIONS = [0.3, 0.5, 0.7, 1.0]
TP_OPTIONS = [3.0, 4.0, 5.0]
ENTRY_THRESH = [0.55, 0.60, 0.65, 0.70]
TREND_THRESH = [0.5, 0.8, 1.0, 1.5]
VOL_MULT = [0.6, 0.8, 1.0]
FVG_GAP = [0.2, 0.3, 0.5]

# 固定参数
MIN_BARS = 120
ROLL_START = 80
ROLL_END_OFFSET = 10
MAX_HOLD = 40
COOLDOWN = 15


def load_ohlcv(symbol):
    fname = f"{symbol.replace('.', '_')}_daily_300.json"
    fpath = CACHE_DIR / fname
    if not fpath.exists():
        return None
    data = json.loads(fpath.read_text())
    if not data or len(data) < MIN_BARS:
        return None
    for bar in data:
        if 'date' not in bar and 't' in bar:
            bar['date'] = str(bar['t'])
    return data


def short_trend(ohlcv, idx, lookback=10):
    if idx < lookback:
        return 'neutral', 0.0
    segment = ohlcv[idx-lookback:idx+1]
    start, end = segment[0]['c'], segment[-1]['c']
    change = (end - start) / start * 100
    ema = sum(ohlcv[i]['c'] for i in range(idx-min(5,idx), idx+1)) / min(6, idx+1)
    ema_dist = (ohlcv[idx]['c'] - ema) / ema * 100
    if change > 0 and ema_dist > 0:
        return 'up', change
    elif change < 0 and ema_dist < 0:
        return 'down', abs(change)
    return 'neutral', 0


def run_single_param(ohlcv, all_signals, symbol, params_dict):
    """用一组参数运行回测"""
    entry_thresh = params_dict.get('entry_threshold', 0.65)
    trend_thresh = params_dict.get('trend_threshold', 0.8)
    vol_mult = params_dict.get('vol_multiplier', 0.8)
    fvg_gap = params_dict.get('fvg_gap_min', 0.3)
    sl_pct = params_dict.get('sl_pct', 0.5)
    tp_pct = params_dict.get('tp_pct', 5.0)
    
    n = len(ohlcv)
    roll_end = n - ROLL_END_OFFSET
    trades = []
    entered_bar = -999
    
    base_params = calc_stock_params(ohlcv, symbol, tf='daily')
    params = {**base_params, 'sl_pct': sl_pct, 'tp_pct': tp_pct}
    
    for i in range(ROLL_START, roll_end):
        if i - entered_bar < COOLDOWN:
            continue
        
        sigs_before = [s for s in all_signals if s.get('idx', 0) <= i]
        if len(sigs_before) < 5:
            continue
        
        seq_result = analyze_sequence_v11(sigs_before, params=params)
        best_seq = seq_result.get('best_sequence')
        if not best_seq:
            continue
        
        seq_name = best_seq.get('name', '')
        is_scout = 'SCOUT' in seq_name
        seq_dir = 'bull' if 'LONG' in seq_name else 'bear'
        
        if seq_dir != 'bull':
            continue
        if not is_scout:
            continue
        
        # 信号质量检查 (用参数化的阈值)
        entry_sig = seq_result.get('entry_signal', {})
        fvg_entry = seq_result.get('fvg_entry')
        sig = fvg_entry if fvg_entry else entry_sig
        sig_idx = sig.get('idx', i)
        sig_type = sig.get('type', '')
        
        if sig_idx > 30 and sig_idx < n:
            bar_vol = ohlcv[sig_idx].get('v', ohlcv[sig_idx].get('vol', 0))
            avg_vol = sum(ohlcv[k].get('v', ohlcv[k].get('vol', 0))
                           for k in range(max(0, sig_idx-30), sig_idx)) / 30
            if bar_vol < avg_vol * vol_mult:
                continue
        
        if 'FVG' in sig_type and sig_idx > 0 and sig_idx < n:
            bar = ohlcv[sig_idx]
            if bar['c'] <= bar['o']:
                continue
        
        if 'FVG' in sig_type:
            upper = sig.get('upper', 0)
            lower = sig.get('lower', 0)
            if upper > 0 and lower > 0:
                gap_pct = (upper - lower) / lower * 100
                if gap_pct < fvg_gap:
                    continue
        
        # 趋势检查
        trend_dir, trend_str = short_trend(ohlcv, i)
        if trend_dir != 'neutral' and trend_dir != 'up':
            continue
        if trend_dir == 'up' and trend_str < trend_thresh:
            continue
        
        # 共振检查
        window = ohlcv[:i+1]
        tf_sequences = {'daily': seq_result}
        resonance = evaluate_full_resonance_v11(
            all_signals=sigs_before, tf_sequences=tf_sequences, ohlcv=window,
        )
        
        if resonance.total < entry_thresh:
            continue
        
        entry_price = sig.get('price', ohlcv[i]['c'])
        if not entry_price:
            continue
        
        sl_price = entry_price * (1 - sl_pct / 100)
        tp_price = entry_price * (1 + tp_pct / 100)
        
        exit_idx, exit_price, won = -1, None, False
        for j in range(i + 1, min(i + MAX_HOLD + 1, n)):
            bar = ohlcv[j]
            if bar['h'] >= tp_price: exit_idx, exit_price, won = j, tp_price, True; break
            if bar['l'] <= sl_price: exit_idx, exit_price, won = j, sl_price, False; break
        
        if exit_idx == -1:
            exit_idx = min(i + MAX_HOLD, n - 1)
            exit_price = ohlcv[exit_idx]['c']
            won = exit_price > entry_price
        
        pnl_pct = (exit_price - entry_price) / entry_price * 100
        actual_rr = abs(exit_price - entry_price) / abs(entry_price - sl_price + 0.001)
        
        trades.append({
            'entry_idx': i, 'exit_idx': exit_idx,
            'pnl_pct': round(pnl_pct, 2), 'won': won, 'rr': round(actual_rr, 2),
        })
        entered_bar = i
    
    if len(trades) < 2:
        return None
    
    wins = sum(1 for t in trades if t['won'])
    wr = wins / len(trades) * 100
    win_pnl = sum(t['pnl_pct'] for t in trades if t['won'])
    loss_pnl = abs(sum(t['pnl_pct'] for t in trades if not t['won']))
    pf = win_pnl / loss_pnl if loss_pnl > 0 else 99.9
    avg_pnl = sum(t['pnl_pct'] for t in trades) / len(trades)
    avg_rr = sum(t['rr'] for t in trades) / len(trades)
    
    # 评分: WR^2 * sqrt(n) * min(3, PF) * min(3, avg_rr)
    score = (wr/100)**2 * (len(trades)**0.5) * min(3, pf) * min(3, avg_rr)
    
    return {
        'n_trades': len(trades), 'wr': round(wr, 1),
        'rr': round(avg_rr, 2), 'pf': round(pf, 2),
        'pnl': round(avg_pnl, 2), 'score': round(score, 2),
    }


def optimize_stock(ohlcv, all_signals, symbol, n_iterations=6, n_samples=30, n_elite=5):
    """多参数迭代优化"""
    if not all_signals or len(all_signals) < 5:
        return None
    
    # 生成所有SL/TP组合
    sl_tp_combos = [(s, t) for s in SL_OPTIONS for t in TP_OPTIONS]
    
    best_overall = None
    best_params = None
    
    for sl_pct, tp_pct in sl_tp_combos:
        # 每对SL/TP独立优化其他参数
        candidates = []
        
        for iteration in range(n_iterations):
            # 采样/精英
            if iteration == 0:
                param_set = [
                    {'entry_threshold': random.choice(ENTRY_THRESH),
                     'trend_threshold': random.choice(TREND_THRESH),
                     'vol_multiplier': random.choice(VOL_MULT),
                     'fvg_gap_min': random.choice(FVG_GAP),
                     'sl_pct': sl_pct, 'tp_pct': tp_pct}
                    for _ in range(n_samples)
                ]
            else:
                # 精英周围变异
                elite = sorted(candidates, key=lambda x: x['score'], reverse=True)[:n_elite]
                param_set = []
                for e in elite:
                    base = e['params']
                    for _ in range(n_samples // n_elite):
                        noisy = {
                            'entry_threshold': min(0.75, max(0.50, base['entry_threshold'] + random.uniform(-0.05, 0.05))),
                            'trend_threshold': min(2.0, max(0.3, base['trend_threshold'] + random.uniform(-0.3, 0.3))),
                            'vol_multiplier': min(1.2, max(0.5, base['vol_multiplier'] + random.uniform(-0.2, 0.2))),
                            'fvg_gap_min': min(0.6, max(0.15, base['fvg_gap_min'] + random.uniform(-0.1, 0.1))),
                            'sl_pct': sl_pct, 'tp_pct': tp_pct,
                        }
                        # 四舍五入到标准值
                        noisy['entry_threshold'] = round(noisy['entry_threshold'] * 20) / 20
                        noisy['trend_threshold'] = round(noisy['trend_threshold'] * 10) / 10
                        noisy['vol_multiplier'] = round(noisy['vol_multiplier'] * 10) / 10
                        noisy['fvg_gap_min'] = round(noisy['fvg_gap_min'] * 10) / 10
                        param_set.append(noisy)
            
            for p in param_set:
                result = run_single_param(ohlcv, all_signals, symbol, p)
                if result:
                    candidates.append({'params': p, **result})
        
        if candidates:
            best = max(candidates, key=lambda x: x['score'])
            if best_overall is None or best['score'] > best_overall['score']:
                best_overall = best
                best_params = best['params']
    
    return best_overall, best_params


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--batch', type=int, default=200)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--output', default='v14_multiopt.json')
    args = parser.parse_args()
    
    symbols = sorted([f.stem.replace('_daily_300', '').replace('_', '.')
                      for f in CACHE_DIR.glob('*_daily_300.json')])
    symbols = symbols[args.start:args.start + args.batch]
    
    print(f"{'='*80}")
    print(f"每股多参数优化器")
    print(f"  参数: 入场阈/趋势阈/成交量/FVGgap x SL/TP")
    print(f"  迭代: 6轮 x 30采样 x {len(SL_OPTIONS)*len(TP_OPTIONS)}SL/TP组合")
    print(f"  股票: {len(symbols)} (idx {args.start}-{args.start+len(symbols)-1})")
    print(f"{'='*80}")
    
    results = []
    t_start = time.time()
    
    for idx, sym in enumerate(symbols):
        t0 = time.time()
        ohlcv = load_ohlcv(sym)
        if not ohlcv:
            print(f"  [{idx+1:3d}/{len(symbols)}] {sym:12s} CACHE MISS")
            continue
        
        base_params = calc_stock_params(ohlcv, sym, tf='daily')
        all_signals = detect_all_signals_v11(ohlcv, params=base_params, tf='daily')['all']
        
        if not all_signals or len(all_signals) < 5:
            print(f"  [{idx+1:3d}/{len(symbols)}] {sym:12s} NO SIGNALS ({len(all_signals) if all_signals else 0})")
            continue
        
        best, params = optimize_stock(ohlcv, all_signals, sym, n_iterations=6, n_samples=30)
        
        if best and params:
            results.append({
                'symbol': sym, 'n_signals': len(all_signals),
                **best,
                'params': {k: v for k, v in params.items() if k != 'sl_pct' and k != 'tp_pct'},
                'sl_pct': params['sl_pct'], 'tp_pct': params['tp_pct'],
                'elapsed': round(time.time() - t0, 1),
            })
            print(f"  [{idx+1:3d}/{len(symbols)}] {sym:12s} "
                  f"trades={best['n_trades']:2d} WR={best['wr']:.0f}% "
                  f"RR={best['rr']:.1f}x PF={best['pf']:.1f} "
                  f"score={best['score']:.1f} | "
                  f"entry={params['entry_threshold']:.2f} "
                  f"trend={params['trend_threshold']:.1f}% "
                  f"vol={params['vol_multiplier']:.1f}x "
                  f"gap={params['fvg_gap_min']:.1f}% "
                  f"SL={params['sl_pct']}%/TP={params['tp_pct']}% | "
                  f"{best.get('elapsed',0):.1f}s")
        else:
            print(f"  [{idx+1:3d}/{len(symbols)}] {sym:12s} NO TRADES")
        
        if (idx + 1) % 10 == 0:
            time.sleep(0.2)
    
    total_time = time.time() - t_start
    print(f"\n{'='*80}")
    print(f"每股多参数优化完成: {len(results)}/{len(symbols)}")
    print(f"  耗时: {total_time:.1f}s")
    
    if results:
        # 汇总
        avg_wr = sum(r['wr'] for r in results) / len(results)
        avg_rr = sum(r['rr'] for r in results) / len(results)
        avg_pf = sum(r['pf'] for r in results) / len(results)
        total_trades = sum(r['n_trades'] for r in results)
        print(f"  平均WR: {avg_wr:.1f}% | RR: {avg_rr:.2f}x | PF: {avg_pf:.1f}")
        print(f"  总交易: {total_trades}")
        print(f"  WR>=80%: {sum(1 for r in results if r['wr']>=80)} stocks")
        print(f"  WR>=70%: {sum(1 for r in results if r['wr']>=70)} stocks")
        
        # 参数分布
        entry_dist = Counter(r['params']['entry_threshold'] for r in results)
        trend_dist = Counter(r['params']['trend_threshold'] for r in results)
        vol_dist = Counter(r['params']['vol_multiplier'] for r in results)
        gap_dist = Counter(r['params']['fvg_gap_min'] for r in results)
        sl_dist = Counter(r['sl_pct'] for r in results)
        tp_dist = Counter(r['tp_pct'] for r in results)
        
        print(f"\n  参数分布:")
        print(f"    入场阈: {dict(entry_dist.most_common(5))}")
        print(f"    趋势阈: {dict(trend_dist.most_common(5))}")
        print(f"    成交量: {dict(vol_dist.most_common(5))}")
        print(f"    FVGgap: {dict(gap_dist.most_common(5))}")
        print(f"    SL: {dict(sl_dist.most_common(5))}")
        print(f"    TP: {dict(tp_dist.most_common(5))}")
        
        print(f"\n  TOP 10 (by score):")
        for r in sorted(results, key=lambda x: x['score'], reverse=True)[:10]:
            p = r['params']
            print(f"    {r['symbol']:12s} WR={r['wr']:.0f}% RR={r['rr']:.1f}x "
                  f"PF={r['pf']:.1f} n={r['n_trades']} "
                  f"entry={p['entry_threshold']:.2f} trend={p['trend_threshold']:.1f}% "
                  f"SL={r['sl_pct']}%/TP={r['tp_pct']}%")
    
    outpath = OUTPUT_DIR / args.output
    out = {
        'timestamp': datetime.now().isoformat(),
        'config': {
            'stocks': f'{args.start}-{args.start+len(symbols)-1}',
            'sl_options': SL_OPTIONS, 'tp_options': TP_OPTIONS,
            'entry_thresh': ENTRY_THRESH, 'trend_thresh': TREND_THRESH,
            'vol_mult': VOL_MULT, 'fvg_gap': FVG_GAP,
            'n_iterations': 6, 'n_samples': 30,
        },
        'summary': {
            'total_stocks': len(symbols), 'optimized': len(results),
            'total_trades': total_trades,
            'avg_wr': round(avg_wr, 1) if results else 0,
            'avg_rr': round(avg_rr, 2) if results else 0,
            'avg_pf': round(avg_pf, 1) if results else 0,
        } if results else {},
        'results': results,
    }
    outpath.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    print(f"\n  保存: {outpath}")


if __name__ == '__main__':
    main()
