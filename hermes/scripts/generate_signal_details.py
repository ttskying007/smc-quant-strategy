#!/usr/bin/env python3
"""
SMC V4 — 有信号股票完整详情报告生成器
=========================================
对scan_v4_results.json中有信号的股票，重新获取K线并提取完整的信号详情。
包括:
  - 信号位置 (入口K线索引/时间)
  - 触发条件 (FVG/Sweep/OB/CHOCH/BPR共振组合)
  - 时间 (K线日期)
  - 价格区间 (入场/SL/TP)
  - 信号强度评分
  - V4检测引擎原始输出

输出:
  ~/.hermes/smc_opt_v4/signal_details_full.json  (完整结构化数据)
  ~/.hermes/smc_opt_v4/signal_details_report.txt  (人类可读报告)

用法:
  python3 generate_signal_details.py              # 处理所有有信号的股票 (~2691只)
  python3 generate_signal_details.py --top 100    # 只处理Top 100
"""

import sys, os, json, math, time, concurrent.futures
from pathlib import Path
from collections import Counter
from datetime import datetime

SCRIPT_DIR = os.path.expanduser('~/.hermes/scripts')
sys.path.insert(0, SCRIPT_DIR)

for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
    os.environ.pop(k, None)

from smc_engine_v4 import (
    get_klines, get_stock_list,
    get_volatility_profile, get_adaptive_params,
    detect_entries_v4, backtest_v4, evaluate,
    detect_fvg_standard, detect_sweep_precise, detect_ob_v4,
    detect_choch_v4, calc_bpr_v4, calc_atr
)

OPT_DIR = Path.home() / '.hermes' / 'smc_opt_v4'
MAX_WORKERS = 16

# 最佳参数 (继承200轮优化结果)
BEST_PARAMS = {
    'fvg_threshold': 0.26,
    'score_threshold': 1.7,
    'sl_mult': 2.5,
    'tp_mult': 2.1,
}


def get_klines_detailed(symbol, limit=300):
    """获取K线，返回带时间格式的数据"""
    bars = get_klines(symbol, 'daily', limit)
    if not bars or len(bars) < 120:
        return []
    return bars


def extract_signal_details(code, name):
    """对单只股票提取所有信号详情"""
    try:
        bars = get_klines_detailed(code, 300)
        if not bars or len(bars) < 120:
            return None
        
        vol = get_volatility_profile(bars)
        v4_params = BEST_PARAMS.copy()
        
        # 获取V4入口检测详情
        entries = detect_entries_v4(bars, v4_params)
        strict_entries = entries.get('strict', [])
        total_entries = entries.get('total', [])
        loose_entries = entries.get('loose', [])
        
        if not strict_entries and not total_entries:
            return None
        
        # 格式化时间
        def fmt_time(idx):
            if 0 <= idx < len(bars):
                t = bars[idx].get('t', '')
                if t and len(t) >= 8:
                    return f"{t[:4]}-{t[4:6]}-{t[6:8]}"
            return str(idx)
        
        def fmt_price(p):
            return round(p, 2)
        
        # 构建信号详情
        signals_list = []
        
        for mode_name, mode_entries in [('strict', strict_entries), ('total', total_entries)]:
            for e in mode_entries:
                idx = e.get('idx', 0)
                dir_label = 'LONG' if e.get('dir') == 'L' else 'SHORT'
                sigs = e.get('sigs', [])
                sc = e.get('sc', 0)
                
                entry_time = fmt_time(idx - 1)  # entry前一根K线是FVG位置
                entry_price = fmt_price(e.get('ep', 0))
                sl = fmt_price(e.get('sl', 0))
                tp = fmt_price(e.get('tp', 0))
                
                # 计算盈亏比
                if entry_price and sl and tp:
                    if dir_label == 'LONG':
                        risk = abs(entry_price - sl) / entry_price * 100
                        reward = abs(tp - entry_price) / entry_price * 100
                    else:
                        risk = abs(sl - entry_price) / entry_price * 100
                        reward = abs(entry_price - tp) / entry_price * 100
                    rr = round(reward / risk, 2) if risk > 0 else 0
                else:
                    risk = reward = rr = 0
                
                # 解析信号类型
                signal_types = []
                for s in sigs:
                    if 'FVG' in s: signal_types.append('FVG')
                    if 'SW' in s: signal_types.append('Sweep')
                    if 'OB' in s: signal_types.append('OB')
                    if 'CH' in s: signal_types.append('CHOCH')
                    if 'BPR' in s: signal_types.append('BPR')
                    if 'MS' in s: signal_types.append('MS')
                    if 'MG' in s: signal_types.append('MergeFVG')
                    if 'CF' in s: signal_types.append('ConfirmBar')
                
                signals_list.append({
                    'mode': mode_name,
                    'direction': dir_label,
                    'entry_bar_idx': idx,
                    'fvg_bar_idx': idx - 1,
                    'entry_time': entry_time,
                    'entry_price': entry_price,
                    'stop_loss': sl,
                    'take_profit': tp,
                    'risk_pct': round(risk, 2),
                    'reward_pct': round(reward, 2),
                    'rr_ratio': rr,
                    'score': sc,
                    'signal_types': signal_types,
                    'raw_signals': sigs,
                    'signal_count': len(signal_types),
                })
        
        # 回测性能
        strict_trades = backtest_v4(bars, 'strict', v4_params)
        total_trades = backtest_v4(bars, 'total', v4_params)
        
        perf = {}
        for mode_name, trades in [('strict', strict_trades), ('total', total_trades)]:
            if trades:
                wins = sum(1 for t in trades if t['pnl']>0)
                losses = [t for t in trades if t['pnl']<=0]
                wr = len(wins)/len(trades)*100
                pf = abs(sum(t['pnl'] for t in trades if t['pnl']>0)/sum(t['pnl'] for t in losses)) if losses and sum(t['pnl'] for t in losses)!=0 else 999
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
            'current_price': round(bars[-1]['c'], 2) if bars else 0,
            'signals': signals_list,
            'performance': perf,
        }
    
    except Exception as e:
        return {'code': code, 'name': name, 'error': str(e)[:50]}


def format_signal_report(detail):
    """格式化单只股票的信号报告文本"""
    lines = []
    code = detail['code']
    name = detail['name']
    vol = detail.get('vol_level', '?')
    atr = detail.get('atr_pct', 0)
    price = detail.get('current_price', 0)
    
    lines.append(f"{'═' * 70}")
    lines.append(f"  {code} | {name}")
    lines.append(f"  价格: {price:.2f} | 波动: {vol} (ATR%={atr:.2f}%)")
    
    # 性能
    perf = detail.get('performance', {})
    if perf.get('strict'):
        p = perf['strict']
        lines.append(f"  V4 Strict: {p['n']}笔 WR={p['wr']}% PF={p['pf']}")
    if perf.get('total'):
        p = perf['total']
        lines.append(f"  V4 Total:  {p['n']}笔 WR={p['wr']}% PF={p['pf']}")
    
    # 信号列表
    sigs = detail.get('signals', [])
    if not sigs:
        lines.append(f"  (无详细信号)")
        lines.append('')
        return '\n'.join(lines)
    
    lines.append(f"{'─' * 70}")
    lines.append(f"  {'#':>3} {'模式':>6} {'方向':>6} {'时间':>12} {'入场':>8} {'止损':>8} {'止盈':>8} {'风险%':>6} {'回报%':>6} {'R:R':>5} {'评分':>5} {'触发':<30}")
    lines.append(f"{'─' * 70}")
    
    for i, s in enumerate(sigs, 1):
        mode = s.get('mode', '?')[:6]
        dir_ = s.get('direction', '?')[:6]
        t = s.get('entry_time', '?')[:10]
        ep = f"{s.get('entry_price', 0):>8.2f}"
        sl = f"{s.get('stop_loss', 0):>8.2f}"
        tp = f"{s.get('take_profit', 0):>8.2f}"
        rp = f"{s.get('risk_pct', 0):>5.1f}"
        rw = f"{s.get('reward_pct', 0):>5.1f}"
        rr = f"{s.get('rr_ratio', 0):>4.1f}"
        sc = f"{s.get('score', 0):>4.1f}"
        trig = '+'.join(s.get('signal_types', [])[:5])
        
        lines.append(f"  {i:>3} {mode:>6} {dir_:>6} {t:>12} {ep:>8} {sl:>8} {tp:>8} {rp:>6} {rw:>6} {rr:>5} {sc:>5} {trig:<30}")
    
    lines.append(f"{'═' * 70}")
    lines.append('')
    
    return '\n'.join(lines)


def generate_reports(signal_stocks, top_n=None):
    """生成所有信号的详情"""
    total = len(signal_stocks)
    if top_n:
        signal_stocks = signal_stocks[:top_n]
        print(f"\n  Processing: {top_n}/{total} top stocks")
    else:
        print(f"\n  Processing all {total} stocks...")
    
    results = []
    report_lines = []
    done = 0
    errors = 0
    
    start = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(extract_signal_details, s['code'], s['name']): s for s in signal_stocks}
        
        for f in concurrent.futures.as_completed(futures):
            done += 1
            try:
                r = f.result()
                if r and not r.get('error') and r.get('signals'):
                    results.append(r)
                    report_text = format_signal_report(r)
                    report_lines.append(report_text)
                elif r and r.get('error'):
                    errors += 1
                else:
                    # 无信号 (缓存可能过期)
                    errors += 1
            except:
                errors += 1
            
            if done % 100 == 0:
                elapsed = time.time() - start
                rate = done / elapsed if elapsed > 0 else 0
                eta = (total - done) / rate if rate > 0 else 0
                print(f"  [{done}/{total}] err={errors} rate={rate:.1f}stk/s ETA={eta:.0f}s")
    
    total_time = time.time() - start
    print(f"\n  Done! {len(results)}/{done} stocks with signals in {total_time:.0f}s")
    
    return results, report_lines


def main():
    # 加载有信号的股票列表 (按WR排序, 前2691只)
    results_path = OPT_DIR / 'scan_v4_results.json'
    if not results_path.exists():
        print(f"❌ File not found: {results_path}")
        print("   Run smc_optimizer_v4_5000_v2.py first!")
        sys.exit(1)
    
    with open(results_path) as f:
        signal_stocks = json.load(f)
    
    print(f"{'='*70}")
    print(f"  SMC V4 — 有信号股票详情生成")
    print(f"  总股票: {len(signal_stocks)}")
    print(f"  Workers: {MAX_WORKERS}")
    print(f"{'='*70}")
    
    # 检查命令行参数
    top_n = None
    if '--top' in sys.argv:
        idx = sys.argv.index('--top')
        if idx + 1 < len(sys.argv):
            top_n = int(sys.argv[idx + 1])
    
    # 过滤: 只处理WR>=80% 或 n_s>=2 的高质量信号
    quality_stocks = [s for s in signal_stocks if s.get('wr_s', 0) >= 80]
    
    print(f"  Quality stocks (WR>=80%): {len(quality_stocks)}")
    print(f"  Processing {'top ' + str(top_n) if top_n else 'all'}...")
    
    if top_n:
        quality_stocks = quality_stocks[:top_n]
    
    results, report_lines = generate_reports(quality_stocks, None)
    
    # ═════ 保存 ═════
    # 1. JSON完整详情
    json_path = OPT_DIR / 'signal_details_full.json'
    with open(json_path, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n✅ JSON详情: {json_path} ({len(results)} stocks)")
    
    # 2. 人类可读报告
    txt_path = OPT_DIR / 'signal_details_report.txt'
    
    header = []
    header.append('=' * 70)
    header.append(f'  SMC V4 — 有信号股票完整详情')
    header.append(f'  生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    header.append(f'  总股票: {len(results)}')
    header.append(f'  信号总数: {sum(len(r.get("signals",[])) for r in results)}')
    header.append(f'{":.70"}')
    header.append(f'')
    header.append(f'  信号说明:')
    header.append(f'    模式: strict=精选信号(高胜率), total=所有信号')
    header.append(f'    方向: LONG=做多, SHORT=做空')
    header.append(f'    时间: entry发生在FVG信号后1根K线')
    header.append(f'    R:R: 回报风险比 (>2:1 为高价值)')
    header.append(f'    评分: 基于FVG+Sweep+OB+CHOCH共振')
    header.append(f'    触发: 信号组件组合 (越多=越强)')
    header.append(f'')
    header.append(f'  {"#":>4} {"代码":>10} {"名称":<12} {"方向":>6} {"时间":>12} {"入场":>8} {"止损":>8} {"止盈":>8} {"R:R":>5} {"评分":>5} {"触发":<40}')
    header.append(f'')
    
    # 3. 简洁表格 (所有信号)
    table_lines = []
    for r in results[:2000]:  # 最多2000只
        code = r.get('code', '')
        name = r.get('name', '')[:10]
        for s in r.get('signals', [])[:3]:  # 每只最多3个信号
            dir_ = s.get('direction', '?')[:4]
            t = s.get('entry_time', '?')[:10]
            ep = f"{s.get('entry_price', 0):>7.2f}"
            sl = f"{s.get('stop_loss', 0):>7.2f}"
            tp = s.get('take_profit', 0)
            tp_s = f"{tp:>7.2f}"
            rr = f"{s.get('rr_ratio', 0):>4.1f}"
            sc = f"{s.get('score', 0):>4.1f}"
            trig = '+'.join(s.get('signal_types', [])[:5])
            mode = s.get('mode', '?')[:4]
            table_lines.append(f"  {code:>10} {name:<12} {dir_:>6} {t:>12} {ep:>8} {sl:>8} {tp_s:>8} {rr:>5} {sc:>5} {trig:<40}")
    
    compact_path = OPT_DIR / 'signal_details_compact.txt'
    with open(compact_path, 'w') as f:
        f.write('\n'.join(header + table_lines + ['' + '='*70]))
    print(f"✅ 简洁表: {compact_path} ({len(table_lines)} rows)")
    
    # 4. 完整详细报告
    with open(txt_path, 'w') as f:
        f.write('\n'.join(report_lines))
    print(f"✅ 详细报告: {txt_path}")
    
    # 5. 打印前10只
    print(f"\n{'='*70}")
    print(f"  前10只有信号股票:")
    print(f"{'='*70}")
    for r in results[:10]:
        print(f"\n  {r['code']} | {r['name']} | price={r.get('current_price',0):.2f}")
        for s in r.get('signals', [])[:2]:
            print(f"    {s['mode']:>6} {s['direction']:>6} @ {s['entry_time']} "
                  f"EP={s['entry_price']:.2f} SL={s['stop_loss']:.2f} TP={s['take_profit']:.2f} "
                  f"RR={s['rr_ratio']} score={s['score']} "
                  f"{'+'.join(s['signal_types'][:4])}")
    
    print(f"\n✅ 全部完成")


if __name__ == '__main__':
    main()