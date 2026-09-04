#!/usr/bin/env python3
"""
SMC V4 — 信号详情生成 v2
==========================
修复缓存读取问题，从本地缓存读取K线数据
"""
import sys, os, json, math, time, concurrent.futures
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = os.path.expanduser('~/.hermes/scripts')
sys.path.insert(0, SCRIPT_DIR)

# 在导入smc_engine_v4之前先清除代理
for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
    os.environ.pop(k, None)

# 本地缓存路径
KLINE_CACHE = Path.home() / '.hermes' / 'kline_cache'
OPT_DIR = Path.home() / '.hermes' / 'smc_opt_v4'
MAX_WORKERS = 16

# 从smc_engine_v4导入检测函数(不导入get_klines以使用缓存)
from smc_engine_v4 import (
    detect_entries_v4, backtest_v4,
    get_volatility_profile, get_adaptive_params,
    calc_atr
)


def load_bars_from_cache(symbol, limit=300):
    """从本地缓存读取K线"""
    cache_key = f"{symbol}_daily_{limit}".replace('.','_').replace('-','_')
    cache_path = KLINE_CACHE / f"{cache_key}.json"
    
    if cache_path.exists() and os.path.getsize(cache_path) > 100:
        try:
            with open(cache_path) as f:
                return json.load(f)
        except:
            pass
    
    # 不在缓存中，通过API获取
    from smc_engine_v4 import get_klines
    bars = get_klines(symbol, 'daily', limit)
    if bars and len(bars) >= 100:
        # 存入缓存
        KLINE_CACHE.mkdir(parents=True, exist_ok=True)
        simple = [{'o':b['o'],'h':b['h'],'l':b['l'],'c':b['c'],'v':b['v'],'t':b['t']} for b in bars]
        with open(cache_path, 'w') as f:
            json.dump(simple, f, ensure_ascii=False)
    return bars


def extract_signal_details(code, name):
    """提取信号详情 (从本地缓存)"""
    try:
        bars = load_bars_from_cache(code, 300)
        if not bars or len(bars) < 120:
            return None
        
        vol = get_volatility_profile(bars)
        
        params = {
            'fvg_threshold': 0.26,
            'score_threshold': 1.7,
            'sl_mult': 2.5,
            'tp_mult': 2.1,
        }
        
        entries = detect_entries_v4(bars, params)
        
        strict_entries = entries.get('strict', [])
        total_entries = entries.get('total', [])
        loose_entries = entries.get('loose', [])
        
        if not strict_entries and not total_entries:
            return None
        
        def fmt_time(idx):
            if 0 <= idx < len(bars):
                t = bars[idx].get('t', '')
                if t and len(t) >= 8:
                    return f"{t[:4]}-{t[4:6]}-{t[6:8]}"
                return str(t)
            return str(idx)
        
        signals_list = []
        
        for mode_name, mode_entries in [('strict', strict_entries), ('total', total_entries)]:
            for e in mode_entries:
                idx = e.get('idx', 0)
                dir_label = 'LONG' if e.get('dir') == 'L' else 'SHORT'
                sigs = e.get('sigs', [])
                sc = e.get('sc', 0)
                n_sig = e.get('n_sig', 0)
                
                entry_time = fmt_time(idx - 1)
                fvg_time = fmt_time(e.get('fvg_idx', idx - 1))
                
                ep = e.get('ep', 0)
                sl = e.get('sl', 0)
                tp = e.get('tp', 0)
                
                if ep and sl and tp:
                    if dir_label == 'LONG':
                        risk = abs(ep - sl) / ep * 100
                        reward = abs(tp - ep) / ep * 100
                    else:
                        risk = abs(sl - ep) / ep * 100
                        reward = abs(ep - tp) / ep * 100
                    rr = round(reward / risk, 2) if risk > 0 else 0
                else:
                    risk = reward = rr = 0
                
                signal_types = []
                for s in sigs:
                    if 'FVG' in s: signal_types.append('FVG')
                    if 'SW(' in s or 'SW' in s: signal_types.append('Sweep')
                    if 'OB' in s: signal_types.append('OB')
                    if 'CH(' in s or 'CH' in sigs: signal_types.append('CHOCH')
                    if 'BPR' in s: signal_types.append('BPR')
                    if 'MS' in s: signal_types.append('MS')
                    if 'MG' in s: signal_types.append('MergeFVG')
                    if 'CF' in s: signal_types.append('ConfirmBar')
                
                # 去重
                signal_types = list(dict.fromkeys(signal_types))
                
                signals_list.append({
                    'mode': mode_name,
                    'direction': dir_label,
                    'entry_bar_idx': idx,
                    'fvg_bar_idx': e.get('fvg_idx', idx - 1),
                    'fvg_time': fvg_time,
                    'entry_time': entry_time,
                    'entry_price': round(ep, 4),
                    'stop_loss': round(sl, 4),
                    'take_profit': round(tp, 4),
                    'risk_pct': round(risk, 2),
                    'reward_pct': round(reward, 2),
                    'rr_ratio': rr,
                    'score': sc,
                    'signal_types': signal_types,
                    'raw_signals': sigs,
                    'signal_count': n_sig,
                })
        
        # 回测性能
        strict_trades = backtest_v4(bars, 'strict', params)
        total_trades = backtest_v4(bars, 'total', params)
        
        perf = {}
        for mode_name, trades in [('strict', strict_trades), ('total', total_trades)]:
            if trades and len(trades) > 0:
                wins = sum(1 for t in trades if t['pnl'] > 0)
                losses = [t for t in trades if t['pnl'] <= 0]
                wr = len(wins)/len(trades)*100
                pf = abs(sum(t['pnl'] for t in trades if t['pnl']>0) / sum(t['pnl'] for t in losses)) if losses and sum(t['pnl'] for t in losses)!=0 else 999
                perf[mode_name] = {
                    'n': len(trades),
                    'wins': len(wins),
                    'wr': round(wr, 1),
                    'pf': round(pf, 2),
                }
        
        return {
            'code': code,
            'name': name,
            'vol_level': vol.get('vol_level', '?'),
            'atr_pct': vol.get('atr_pct', 0),
            'current_price': round(bars[-1]['c'], 2),
            'signals': signals_list,
            'performance': perf,
        }
    
    except Exception as e:
        import traceback
        return {'code': code, 'name': name, 'error': str(e)[:50]}


def process_batch(stock_list, start_idx=0, batch_size=500):
    """分批处理"""
    batch = stock_list[start_idx:start_idx + batch_size]
    results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(extract_signal_details, s['code'], s['name']): i 
            for i, s in enumerate(batch)
        }
        
        for f in concurrent.futures.as_completed(futures):
            try:
                r = f.result()
                if r and not r.get('error') and r.get('signals'):
                    results.append(r)
            except:
                pass
    
    return results


def main():
    # 加载有信号的股票列表
    results_path = OPT_DIR / 'scan_v4_results.json'
    if not results_path.exists():
        print(f"❌ 文件不存在: {results_path}")
        sys.exit(1)
    
    with open(results_path) as f:
        all_stocks = json.load(f)
    
    # 只处理 WR>=80% 的高质量信号
    quality = [s for s in all_stocks if s.get('wr_s', 0) >= 80]
    
    print(f"{'='*70}")
    print(f"  SMC V4 — 信号详情生成 v2")
    print(f"  总股票: {len(all_stocks)}")
    print(f"  高质量(WR>=80%): {len(quality)}")
    print(f"  缓存目录: {KLINE_CACHE}")
    print(f"  Workers: {MAX_WORKERS}")
    print(f"{'='*70}")
    
    all_results = []
    batch_size = 500
    total_batches = (len(quality) + batch_size - 1) // batch_size
    
    for batch_idx in range(total_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(quality))
        
        print(f"\n  Batch {batch_idx + 1}/{total_batches} ({start}-{end})...")
        
        batch_results = process_batch(quality, start, batch_size)
        all_results.extend(batch_results)
        
        print(f"    Found {len(batch_results)} stocks with signals in this batch")
        print(f"    Total so far: {len(all_results)}")
    
    # ═════ 保存 ═════
    print(f"\n{'='*70}")
    print(f"  Savings results...")
    
    # JSON
    with open(OPT_DIR / 'signal_details_full.json', 'w') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"  ✅ JSON: {OPT_DIR / 'signal_details_full.json'} ({len(all_results)} stocks)")
    
    # COMPACT TABLE
    lines = []
    lines.append('=' * 70)
    lines.append(f'  SMC V4 — 有信号股票详情')
    lines.append(f'  生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    lines.append(f'  总股票: {len(all_results)}')
    lines.append(f'=' * 70)
    lines.append('')
    lines.append(f'  {"代码":>10} {"名称":<10} {"方向":>6} {"时间":>12} {"入场":>8} {"止损":>8} {"止盈":>8} {"R:R":>5} {"评分":>5} {"触发条件":<30}')
    lines.append(f'  {"-"*10} {"-"*10} {"-"*6} {"-"*12} {"-"*8} {"-"*8} {"-"*8} {"-"*5} {"-"*5} {"-"*30}')
    
    for r in all_results[:3000]:
        for s in r.get('signals', [])[:3]:
            code = r['code']
            name = r['name'][:8]
            dir_ = s['direction'][:4]
            t = s['entry_time'][:10]
            ep = f"{s['entry_price']:>7.2f}"
            sl = f"{s['stop_loss']:>7.2f}"
            tp = f"{s['take_profit']:>7.2f}"
            rr = f"{s['rr_ratio']:>4.1f}"
            sc = f"{s['score']:>4.1f}"
            trig = '+'.join(s['signal_types'][:4])
            lines.append(f"  {code:>10} {name:<10} {dir_:>6} {t:>12} {ep:>8} {sl:>8} {tp:>8} {rr:>5} {sc:>5} {trig:<30}")
    
    compact_path = OPT_DIR / 'signal_details_compact.txt'
    with open(compact_path, 'w') as f:
        f.write('\n'.join(lines))
    print(f"  ✅ 简洁表: {compact_path} ({len([l for l in lines if '->' not in l and '---' not in l])} rows)")
    
    # FULL DETAIL REPORT
    detail_lines = []
    for r in all_results:
        code = r['code']
        name = r['name']
        vol = r.get('vol_level', '?')
        atr = r.get('atr_pct', 0)
        price = r.get('current_price', 0)
        
        detail_lines.append(f"{'═' * 70}")
        detail_lines.append(f"  {code} | {name} | 当前价: {price:.2f} | ATR%: {atr:.2f}% | 波动: {vol}")
        
        perf = r.get('performance', {})
        for m in ['strict', 'total']:
            if m in perf:
                p = perf[m]
                detail_lines.append(f"  {m}: {p['n']}笔 WR={p['wr']}% PF={p['pf']}")
        
        for i, s in enumerate(r.get('signals', []), 1):
            detail_lines.append(f"  {'─' * 60}")
            detail_lines.append(f"  信号 #{i} [{s['mode']}] {s['direction']}:")
            detail_lines.append(f"    FVG位置: {s['fvg_time']} → 入场: {s['entry_time']}")
            detail_lines.append(f"    入场: {s['entry_price']:.2f} 止损: {s['stop_loss']:.2f} 止盈: {s['take_profit']:.2f}")
            detail_lines.append(f"    风险: {s['risk_pct']:.1f}% 回报: {s['reward_pct']:.1f}% R:R={s['rr_ratio']}")
            detail_lines.append(f"    评分: {s['score']} 触发: {'+'.join(s['signal_types'])}")
            detail_lines.append(f"    原始信号: {' '.join(s['raw_signals'])}")
    
    detail_lines.append(f"{'═' * 70}")
    
    detail_path = OPT_DIR / 'signal_details_report.txt'
    with open(detail_path, 'w') as f:
        f.write('\n'.join(detail_lines))
    print(f"  ✅ 详细报告: {detail_path}")
    
    # 展示前5
    print(f"\n{'='*70}")
    print(f"  前5只样例:")
    print(f"{'='*70}")
    for r in all_results[:5]:
        print(f"\n  {r['code']} | {r['name']} | price={r['current_price']:.2f} | WR>=80% signal")
        for s in r.get('signals', [])[:2]:
            print(f"    {s['direction']:>6} @ {s['entry_time']}: "
                  f"ep={s['entry_price']:.2f} sl={s['stop_loss']:.2f} tp={s['take_profit']:.2f} "
                  f"RR={s['rr_ratio']} sc={s['score']} |{'+'.join(s['signal_types'][:4])}|")
    
    print(f"\n{'='*70}")
    print(f"  ✅ 全部完成!")
    print(f"  文件:")
    print(f"    -> {OPT_DIR / 'signal_details_full.json'}")
    print(f"    -> {OPT_DIR / 'signal_details_compact.txt'}")
    print(f"    -> {OPT_DIR / 'signal_details_report.txt'}")
    print(f"{'='*70}")


if __name__ == '__main__':
    main()