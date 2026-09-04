#!/usr/bin/env python3
"""
V500 结构TP/SL回测引擎
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
纯SMC结构止盈止损 — 不用任何固定百分比/ATR自适应

TP (止盈) — 入场后的前方结构阻力位:
  1. 前方摆动高点 (swing_high)
  2. 前方OB区域上沿 (OB.upper)
  3. 前方FVG区域上沿 (FVG.upper)
  4. BSL (buy-side liquidity = 历史摆动高点)
  5. BOS/CHOCH突破位
  → 所有 > entry * 1.01 的距离才有效
  → 从最近到最远排序, 形成TP1/TP2/TP3/...级联

SL (止损) — 入场处/后的结构支撑位:
  1. 最近摆动低点 (swing_low, 在entry下方)
  2. 最近OB下沿 (OB.lower, 在entry下方)
  3. 最近FVG下沿 (FVG.lower, 在entry下方)
  4. SSL (sell-side liquidity = 历史摆动低点)
  → 必须 < entry
  → 取最近的有效支撑

核心测试:
  1. 入场位置是否准确? (有多少结构SL可用?)
  2. 信号检测是否准确? (结构TP够不够密集?)
  3. 假信号会暴露: 没有有效结构SL/TP → 入场位置在空区
"""

import json, sys, math, time, os
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v16 import (
    detect_all_signals_v16,
    detect_swings_v16,
    calc_adaptive_thresholds,
)

# ── 配置 ──
CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v501')
OUTPUT_DIR.mkdir(exist_ok=True)

MIN_BARS = 60
MAX_HOLD = 40  # 日线最多持有40天
MIN_TP_DIST_PCT = 1.0  # TP必须至少1%利润
MAX_SL_DIST_PCT = 8.0  # SL不能超过8% (太远无意义)

# 入场信号类型
ENTRY_SIGNAL_TYPES = {'FVG_Bull', 'OB_Bull'}

# ── 摆动检测参数 (结构分析用) ──
SWING_LEFT = 5
SWING_RIGHT = 2


def load_kline(symbol, cache_dir=CACHE_DIR):
    """加载日线K线"""
    pat = f"{symbol}_daily_300.json"
    for f in cache_dir.glob(pat):
        try:
            with open(f) as fh:
                data = json.load(fh)
            if isinstance(data, list) and len(data) >= MIN_BARS:
                return data
        except:
            pass
    return None


def collect_structural_tps(ohlcv, entry_idx, entry_price, swings, all_signals):
    """
    收集入场后所有结构阻力位作为TP候选
    
    返回: [(bar_idx, price, source, distance_pct), ...] 按距离排序
    """
    n = len(ohlcv)
    candidates = []
    
    # 1. 前方摆动高点
    for sh in swings.get('highs', []):
        if sh['idx'] > entry_idx and sh['price'] > entry_price * (1 + MIN_TP_DIST_PCT / 100):
            dist = (sh['price'] - entry_price) / entry_price * 100
            candidates.append((sh['idx'], sh['price'], 'swing_high', round(dist, 2)))
    
    # 2. OB区域上沿 (bull OB在支撑, 但前方OB可以做阻力参考)
    for s in all_signals:
        if s.get('type') in ('OB_Bull', 'OB_Bear'):
            ob_upper = s.get('upper', 0)
            if ob_upper > entry_price * (1 + MIN_TP_DIST_PCT / 100):
                # OB位置在信号idx处, 用confirmed_at作为bar位置
                ob_idx = s.get('confirmed_at', s.get('idx', entry_idx))
                if ob_idx > entry_idx:
                    dist = (ob_upper - entry_price) / entry_price * 100
                    candidates.append((ob_idx, ob_upper, 'ob_zone', round(dist, 2)))
    
    # 3. FVG区域上沿
    for s in all_signals:
        if s.get('type') in ('FVG_Bull', 'FVG_Bear'):
            fvg_upper = s.get('upper', 0)
            if fvg_upper > entry_price * (1 + MIN_TP_DIST_PCT / 100):
                fvg_idx = s.get('confirmed_at', s.get('idx', entry_idx))
                if fvg_idx > entry_idx:
                    dist = (fvg_upper - entry_price) / entry_price * 100
                    candidates.append((fvg_idx, fvg_upper, 'fvg_zone', round(dist, 2)))
    
    # 4. CHOCH/BOS突破价格
    for s in all_signals:
        if s.get('type') in ('CHOCH_Bull', 'BOS_Bull'):
            tp = s.get('price', 0) or s.get('upper', 0)
            if tp > entry_price * (1 + MIN_TP_DIST_PCT / 100):
                ch_idx = s.get('confirmed_at', s.get('idx', entry_idx))
                if ch_idx > entry_idx:
                    dist = (tp - entry_price) / entry_price * 100
                    candidates.append((ch_idx, tp, 'choch_bos', round(dist, 2)))
    
    # 去重: 按价格聚合同一位置(0.3%内合并)
    candidates.sort(key=lambda x: x[1])  # 按价格排序
    deduped = []
    for c in candidates:
        if not deduped or abs(c[1] - deduped[-1][1]) / entry_price > 0.003:
            deduped.append(c)
    
    # 按bar顺序排
    deduped.sort(key=lambda x: (x[0], x[1]))
    
    # 去重: 同一bar只保留最近的一个
    final = []
    for c in deduped:
        if final and c[0] == final[-1][0]:
            # 同一bar, 保留source优先级高的
            source_order = {'swing_high': 0, 'choch_bos': 1, 'ob_zone': 2, 'fvg_zone': 3}
            if source_order.get(c[3], 99) < source_order.get(final[-1][3], 99):
                final[-1] = c
        else:
            final.append(c)
    
    # 按距离排序
    final.sort(key=lambda x: x[2])
    
    return final


def find_structural_sl(ohlcv, entry_idx, entry_price, swings, all_signals):
    """
    V501修复: 仅用入场前(≤entry_idx)的结构支撑位
    需满足: min_distance_pct ≤ distance ≤ max_distance_pct
    """
    n = len(ohlcv)
    MIN_SL_PCT = 2.0  # SL至少2%距离(太近不可靠)
    candidates = []
    
    # 1. 入场前最近摆动低点
    for slo in sorted(swings.get('lows', []), key=lambda x: x['idx'], reverse=True):
        if slo['idx'] <= entry_idx and slo['price'] < entry_price:
            dist = (entry_price - slo['price']) / entry_price * 100
            if MIN_SL_PCT <= dist <= MAX_SL_DIST_PCT:
                candidates.append((slo['idx'], slo['price'], 'swing_low', round(dist, 2)))
                break  # 取最近的一个
    
    # 2. 入场前OB_Bull下沿
    for s in sorted(all_signals, key=lambda x: x.get('confirmed_at', x.get('idx', 0)), reverse=True):
        if s.get('type') == 'OB_Bull' and s.get('confirmed_at', s.get('idx', 0)) <= entry_idx:
            ob_lower = s.get('lower', 0)
            if 0 < ob_lower < entry_price:
                dist = (entry_price - ob_lower) / entry_price * 100
                if MIN_SL_PCT <= dist <= MAX_SL_DIST_PCT:
                    candidates.append((s.get('confirmed_at', s['idx']), ob_lower, 'ob_lower', round(dist, 2)))
                    break
    
    # 3. 入场前FVG_Bull下沿
    for s in sorted(all_signals, key=lambda x: x.get('confirmed_at', x.get('idx', 0)), reverse=True):
        if s.get('type') == 'FVG_Bull' and s.get('confirmed_at', s.get('idx', 0)) <= entry_idx:
            fvg_lower = s.get('lower', 0)
            if 0 < fvg_lower < entry_price:
                dist = (entry_price - fvg_lower) / entry_price * 100
                if MIN_SL_PCT <= dist <= MAX_SL_DIST_PCT:
                    candidates.append((s.get('confirmed_at', s['idx']), fvg_lower, 'fvg_lower', round(dist, 2)))
                    break
    
    if not candidates:
        return None
    
    candidates.sort(key=lambda x: x[3])  # 按距离排序, 最近优先
    return candidates[0]


def simulate_trade(ohlcv, entry_idx, entry_price, tp_levels, sl_info):
    """
    前向模拟: 逐bar检查是先触TP还是先触SL
    
    tp_levels: [(bar_idx, price, source, distance), ...] 按距离排序
    sl_info: (bar_idx, price, source, distance) or None
    
    返回: {
        'exit_bar': int, 'exit_price': float, 'won': bool,
        'exit_reason': 'tp1'|'tp2'|...|'sl'|'max_hold',
        'tp_hit': int (1-based TP索引),
        'hold_bars': int
    }
    """
    n = len(ohlcv)
    sl_price = sl_info[1] if sl_info else entry_price * 0.92  # fallback -8%
    
    for j in range(entry_idx + 1, min(entry_idx + MAX_HOLD + 1, n)):
        bar = ohlcv[j]
        bar_high = bar['h']
        bar_low = bar['l']
        
        # 检查SL
        if bar_low <= sl_price:
            return {
                'exit_bar': j, 'exit_price': sl_price, 'won': False,
                'exit_reason': 'sl', 'tp_hit': 0,
                'hold_bars': j - entry_idx,
                'sl_source': sl_info[2] if sl_info else 'fallback',
                'sl_distance': sl_info[3] if sl_info else 8.0,
            }
        
        # 检查TP (按优先级: tp1, tp2, ...)
        # 价格需要穿透TP线
        for i, (tp_bar, tp_price, tp_src, tp_dist) in enumerate(tp_levels):
            if bar_high >= tp_price:
                return {
                    'exit_bar': j, 'exit_price': tp_price, 'won': True,
                    'exit_reason': f'tp{i+1}', 'tp_hit': i + 1,
                    'hold_bars': j - entry_idx,
                    'tp_source': tp_src,
                    'tp_distance': tp_dist,
                    'tp_total_count': len(tp_levels),
                }
    
    # max_hold
    j = min(entry_idx + MAX_HOLD, n - 1)
    last_close = ohlcv[j]['c']
    won = last_close > entry_price
    return {
        'exit_bar': j, 'exit_price': last_close, 'won': won,
        'exit_reason': 'max_hold', 'tp_hit': 0,
        'hold_bars': j - entry_idx,
    }


def backtest_stock(symbol):
    """对一只股票做结构TP/SL回测"""
    ohlcv = load_kline(symbol)
    if ohlcv is None:
        return None
    
    n = len(ohlcv)
    
    # 检测信号 (V16 returns dict with 'all', 'fvg', 'ob', etc.)
    adaptive = calc_adaptive_thresholds(ohlcv)
    sig_result = detect_all_signals_v16(ohlcv, adaptive=adaptive)
    
    # 单独检测结构摆动 (用于TP/SL分析, 获取完整摆动数据含价格)
    swings = detect_swings_v16(ohlcv, left=SWING_LEFT, right=SWING_RIGHT)
    
    # 扁平化所有信号
    flat_signals = list(sig_result.get('all', []))
    if not flat_signals:
        # fallback: 手动收集
        for key in ('fvg', 'ob', 'sweep', 'choch', 'bos', 'mss', 'eql', 'bpr', 'ifvg'):
            sigs = sig_result.get(key, [])
            if isinstance(sigs, list):
                flat_signals.extend(sigs)
    
    trades = []
    
    for sig in flat_signals:
        if sig.get('type') not in ENTRY_SIGNAL_TYPES:
            continue
        
        entry_idx = sig.get('confirmed_at', sig.get('idx', 0))
        if entry_idx >= n - 5:
            continue
        
        entry_price = ohlcv[entry_idx]['c']
        if entry_price <= 0:
            continue
        
        # 收集结构TP (入场后前方所有阻力)
        tp_levels = collect_structural_tps(ohlcv, entry_idx, entry_price, swings, flat_signals)
        
        if not tp_levels:
            continue  # 没有有效结构TP, 跳过
        
        # 找结构SL
        sl_info = find_structural_sl(ohlcv, entry_idx, entry_price, swings, flat_signals)
        
        # 模拟
        result = simulate_trade(ohlcv, entry_idx, entry_price, tp_levels, sl_info)
        
        result['symbol'] = symbol
        result['entry_idx'] = entry_idx
        result['entry_price'] = round(entry_price, 2)
        result['signal_type'] = sig['type']
        result['signal_strength'] = round(sig.get('strength', 0), 2)
        result['signal_confidence'] = round(sig.get('confidence', 0), 3)
        result['tp_count'] = len(tp_levels)
        
        # TP详情
        result['tp_details'] = [
            {'idx': t[0], 'price': round(t[1], 2), 'source': t[2], 'dist_pct': t[3]}
            for t in tp_levels[:5]  # 前5个
        ]
        
        if sl_info:
            result['sl_source'] = sl_info[2]
            result['sl_price'] = round(sl_info[1], 2)
            result['sl_distance'] = sl_info[3]
        else:
            result['sl_source'] = 'none_fallback'
            result['sl_price'] = round(entry_price * 0.92, 2)
            result['sl_distance'] = 8.0
        
        # PnL
        if result['won']:
            result['pnl_pct'] = round((result['exit_price'] - entry_price) / entry_price * 100, 2)
        else:
            result['pnl_pct'] = round(-sl_info[3] if sl_info else -8.0, 2)
        
        trades.append(result)
    
    return {
        'symbol': symbol,
        'bars': n,
        'signal_count': len(flat_signals),
        'entry_signals': sum(1 for s in flat_signals if s.get('type') in ENTRY_SIGNAL_TYPES),
        'trade_count': len(trades),
        'trades': trades,
    }


def aggregate_results(results):
    """汇总所有股票的回测结果"""
    all_trades = []
    stats = {
        'total_stocks': 0,
        'tradable_stocks': 0,
        'total_trades': 0,
        'won': 0,
        'lost': 0,
        'total_pnl': 0.0,
        'total_rr': 0.0,
        # TP分析
        'tp_hit_distribution': Counter(),  # tp1, tp2, tp3...
        'tp_source_distribution': Counter(),  # swing_high, ob_zone, fvg_zone, choch_bos
        # SL分析
        'sl_source_distribution': Counter(),
        'sl_available_count': 0,  # 有结构SL的交易数
        'sl_unavailable_count': 0,  # 无结构SL(用fallback)
        # 信号分析
        'signal_type_distribution': Counter(),
        'avg_tp_per_trade': 0.0,
        'tp_count_distribution': Counter(),  # 每笔交易有几个TP可选
        # 按信号类型统计
        'by_signal_type': defaultdict(lambda: {'trades': 0, 'won': 0, 'pnl': 0.0, 'rr': 0.0}),
        # 按TP来源统计
        'by_tp_source': defaultdict(lambda: {'trades': 0, 'won': 0, 'pnl': 0.0}),
    }
    
    for r in results:
        if r is None:
            continue
        stats['total_stocks'] += 1
        if r['trade_count'] > 0:
            stats['tradable_stocks'] += 1
        
        stats['total_trades'] += r['trade_count']
        all_trades.extend(r['trades'])
    
    for t in all_trades:
        stats['won' if t['won'] else 'lost'] += 1
        stats['total_pnl'] += t['pnl_pct']
        
        if not t['won']:
            # SL损失用负数
            avg_loss = abs(t['pnl_pct'])
            stats['total_rr'] += 0  # loss contributes 0 to RR numerator
        else:
            stats['total_rr'] += t['pnl_pct']
        
        # TP分布
        if t.get('exit_reason', '').startswith('tp'):
            stats['tp_hit_distribution'][t['exit_reason']] += 1
        if t.get('tp_source'):
            stats['tp_source_distribution'][t['tp_source']] += 1
        
        # SL分布
        sl_src = t.get('sl_source', 'unknown')
        stats['sl_source_distribution'][sl_src] += 1
        if sl_src == 'none_fallback':
            stats['sl_unavailable_count'] += 1
        else:
            stats['sl_available_count'] += 1
        
        # 信号类型
        stats['signal_type_distribution'][t['signal_type']] += 1
        
        # TP数量
        tp_cnt = t.get('tp_count', 0)
        stats['tp_count_distribution'][tp_cnt] += 1
        stats['avg_tp_per_trade'] += tp_cnt
        
        # 按信号类型
        st = t['signal_type']
        stats['by_signal_type'][st]['trades'] += 1
        if t['won']:
            stats['by_signal_type'][st]['won'] += 1
        stats['by_signal_type'][st]['pnl'] += t['pnl_pct']
        
        # 按TP来源
        tp_src = t.get('tp_source', 'none')
        stats['by_tp_source'][tp_src]['trades'] += 1
        if t['won']:
            stats['by_tp_source'][tp_src]['won'] += 1
        stats['by_tp_source'][tp_src]['pnl'] += t['pnl_pct']
    
    if stats['total_trades'] > 0:
        stats['wr'] = round(stats['won'] / stats['total_trades'] * 100, 1)
        stats['avg_pnl'] = round(stats['total_pnl'] / stats['total_trades'], 2)
        stats['avg_rr'] = round(stats['total_rr'] / max(1, stats['lost']), 2) if stats['lost'] > 0 else float('inf')
        stats['avg_tp_per_trade'] = round(stats['avg_tp_per_trade'] / stats['total_trades'], 1)
        stats['avg_won_pnl'] = round(sum(t['pnl_pct'] for t in all_trades if t['won']) / max(1, stats['won']), 2)
        stats['avg_lost_pnl'] = round(sum(t['pnl_pct'] for t in all_trades if not t['won']) / max(1, stats['lost']), 2)
        
        # 按信号类型计算WR/RR
        for st, data in stats['by_signal_type'].items():
            if data['trades'] > 0:
                data['wr'] = round(data['won'] / data['trades'] * 100, 1)
                data['avg_pnl'] = round(data['pnl'] / data['trades'], 2)
                losses = data['trades'] - data['won']
                if losses > 0:
                    data['rr'] = round(sum(t['pnl_pct'] for t in all_trades if t['signal_type'] == st and t['won']) / losses, 2)
        
        # 按TP来源计算WR
        for src, data in stats['by_tp_source'].items():
            if data['trades'] > 0:
                data['wr'] = round(data['won'] / data['trades'] * 100, 1)
                data['avg_pnl'] = round(data['pnl'] / data['trades'], 2)
    
    stats['all_trades'] = all_trades
    return stats


def print_report(stats):
    """打印详细报告"""
    print()
    print("=" * 72)
    print("  V500 结构TP/SL回测报告")
    print("=" * 72)
    print(f"  股票: 总{stats['total_stocks']} | 有交易{stats['tradable_stocks']}")
    print(f"  交易: {stats['total_trades']}笔")
    print(f"  胜率: {stats['wr']}%  (赢{stats['won']}/输{stats['lost']})")
    print(f"  平均盈亏: {stats['avg_pnl']}%/笔")
    print(f"  平均赢: {stats['avg_won_pnl']}% | 平均输: {stats['avg_lost_pnl']}%")
    print(f"  RR: {stats['avg_rr']}")
    print(f"  平均TP候选: {stats['avg_tp_per_trade']}个/笔")
    print()
    
    print("── TP命中分布 ──")
    total_won = sum(stats['tp_hit_distribution'].values())
    for tp, cnt in sorted(stats['tp_hit_distribution'].items()):
        pct = cnt / max(1, total_won) * 100
        print(f"  {tp}: {cnt}笔 ({pct:.0f}%)")
    
    print()
    print("── TP来源分布 ──")
    for src, cnt in sorted(stats['tp_source_distribution'].items(), key=lambda x: -x[1]):
        data = stats['by_tp_source'].get(src, {})
        print(f"  {src}: {cnt}笔 | WR={data.get('wr', '-')}% | 均P&L={data.get('avg_pnl', '-')}%")
    
    print()
    print("── SL来源分布 ──")
    for src, cnt in sorted(stats['sl_source_distribution'].items(), key=lambda x: -x[1]):
        pct = cnt / max(1, stats['total_trades']) * 100
        print(f"  {src}: {cnt}笔 ({pct:.0f}%)")
    print(f"  有结构SL: {stats['sl_available_count']}笔 | 无结构SL(fallback): {stats['sl_unavailable_count']}笔")
    
    print()
    print("── 按信号类型 ──")
    for st, data in sorted(stats['by_signal_type'].items()):
        print(f"  {st}: {data['trades']}笔 | WR={data.get('wr', '-')}% | 均P&L={data.get('avg_pnl', '-')}% | RR={data.get('rr', '-')}")
    
    print()
    print("── TP候选数量分布 ──")
    for tp_cnt in sorted(stats['tp_count_distribution'].keys()):
        cnt = stats['tp_count_distribution'][tp_cnt]
        pct = cnt / max(1, stats['total_trades']) * 100
        bar = '█' * int(pct / 2)
        print(f"  {tp_cnt}个TP: {cnt}笔 ({pct:.0f}%) {bar}")
    
    print()
    print("── 关键发现 ──")
    tp1_hits = stats['tp_hit_distribution'].get('tp1', 0)
    print(f"  最近TP(tp1)命中: {tp1_hits}/{stats['won']}赢 ({tp1_hits/max(1,stats['won'])*100:.0f}%)")
    print(f"  SL不可用率: {stats['sl_unavailable_count']}/{stats['total_trades']} ({stats['sl_unavailable_count']/max(1,stats['total_trades'])*100:.0f}%)")
    print("=" * 72)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--stocks', type=int, default=200, help='测试股票数')
    ap.add_argument('--symbol', type=str, help='单只股票')
    ap.add_argument('--full', action='store_true', help='全量')
    ap.add_argument('--output', type=str, help='输出JSON')
    args = ap.parse_args()
    
    # 获取股票列表
    if args.symbol:
        symbols = [args.symbol]
    else:
        # 从kline缓存获取有数据的股票
        symbols = []
        for f in sorted(CACHE_DIR.glob('*_daily_300.json')):
            sym = f.name.split('_daily_300')[0]
            symbols.append(sym)
        
        if args.stocks and not args.full:
            # 均匀采样
            step = max(1, len(symbols) // args.stocks)
            symbols = symbols[::step][:args.stocks]
    
    print(f"V500 结构TP/SL回测 — {len(symbols)}只股票")
    
    results = []
    t0 = time.time()
    for i, sym in enumerate(symbols):
        r = backtest_stock(sym)
        results.append(r)
        if (i + 1) % 50 == 0 or i == len(symbols) - 1:
            elapsed = time.time() - t0
            trades_done = sum(r['trade_count'] for r in results if r)
            print(f"  [{i+1}/{len(symbols)}] {trades_done}笔交易 | {elapsed:.0f}s", flush=True)
    
    stats = aggregate_results(results)
    print_report(stats)
    
    # 保存
    out_path = args.output or str(OUTPUT_DIR / 'v500_results.json')
    # 去掉all_trades减小文件
    trades_out = stats.pop('all_trades', [])
    with open(out_path, 'w') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False, default=str)
    stats['all_trades'] = trades_out
    
    # 详细交易数据 (用于分析)
    detail_path = str(OUTPUT_DIR / 'v500_trades.json')
    with open(detail_path, 'w') as f:
        json.dump(trades_out, f, indent=1, ensure_ascii=False, default=str)
    
    print(f"\n结果: {out_path}")
    print(f"交易明细: {detail_path}")


if __name__ == '__main__':
    main()
