#!/usr/bin/env python3
# SMC V11 — Backtest Engine
"""
V11回测引擎 — 全股票/全板块/全指数/全ETF验证

核心创新:
1. 真正的多周期回测 (daily+4H+1H)
2. V11自适应参数回测
3. 基于共振+序列的信号过滤
4. 每笔交易记录: 共振等级/序列评分/时间距离
5. 分阶段绩效分析 (trend/ranging/volatile)
6. 分品种分析 (股票/ETF/指数/板块)
7. 参数扫描: 找出每只股票的最佳参数
8. API限流保护
"""

import json, math, time, logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass, field

log = logging.getLogger('smc_v11.backtest')

# Paths
OUTPUT_DIR = Path.home() / '.hermes' / 'smc_opt_v11'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════
# Trade record
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class TradeRecord:
    """单笔交易记录"""
    symbol: str
    direction: str              # 'bull' | 'bear'
    signal_type: str            # 'Gold' | 'Silver' | 'Bronze' | 'Scout'
    entry_idx: int              # K线索引
    entry_price: float
    exit_idx: int
    exit_price: float
    sl: float
    tp: float
    rr: float                   # 实际盈亏比
    pnl_pct: float              # 盈亏百分比
    won: bool                   # 是否盈利
    resonance_grade: str = 'D'  # 共振等级
    confidence: float = 0.5     # 决策置信度
    avg_signal_dist: float = 0  # 信号平均距离
    phase: str = 'ranging'      # 市场阶段
    tf: str = 'daily'           # 时间框架
    
    @property
    def pnl(self) -> float:
        """盈亏点数"""
        if self.direction == 'bull':
            return self.exit_price - self.entry_price
        else:
            return self.entry_price - self.exit_price


# ═══════════════════════════════════════════════════════════════════════
# Core: Single-stock backtest
# ═══════════════════════════════════════════════════════════════════════

def backtest_single_stock_v11(
    ohlcv: List[Dict],
    symbol: str = '',
    params: Dict = None,
    tf: str = 'daily',
    min_resonance: float = 0.40,
    min_rr: float = 1.5,
    force_enter_all: bool = False,
) -> Dict:
    """单股票V11回测
    
    V11回测流程:
    1. 对每根K线前(滚动窗口), 检测信号
    2. 信号 → 序列分析 → 共振评分
    3. 入场决策: 共振分 >= min_resonance
    4. 计算SL/TP, 模拟交易
    5. 记录每笔交易
    
    Args:
        ohlcv: K线数据 (chronological)
        symbol: 股票代码
        params: 交易参数(自适应或固定)
        tf: 时间框架
        min_resonance: 最小共振门槛
        min_rr: 最小盈亏比
        force_enter_all: 是否强制入场所有信号(用于评估)
    
    Returns:
        {
            'trades': [TradeRecord, ...],
            'stats': {...},
            'params': {...},
            'win_rate': float,
            'avg_rr': float,
            'profit_factor': float,
            'total_return': float,
            'max_drawdown': float,
        }
    """
    from .signals_v11 import detect_all_signals_v11
    from .sequencer_v11 import analyze_sequence_v11
    from .resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
    from .adaptive_params import calc_stock_params, detect_market_phase, calc_sl_price, calc_tp_price
    
    if params is None:
        # 自适应参数
        from .adaptive_params import calc_stock_params
        phase = detect_market_phase(ohlcv)
        params = calc_stock_params(ohlcv, symbol=symbol, phase=phase, tf=tf)
    
    n = len(ohlcv)
    if n < 60:
        return {'trades': [], 'stats': {'error': 'insufficient data'}}
    
    trades = []
    
    # 滚动窗口: 每根K线作为一个潜在入场点
    # 用前300根(或全部)训练, 之后每根K线检测
    train_bars = min(300, n // 2)
    
    for i in range(train_bars, n - 3):
        window = ohlcv[max(0, i - 200):i + 1]  # 当前窗口
        if len(window) < 30:
            continue
        
        # 1. 检测信号
        signal_result = detect_all_signals_v11(window, params=params, tf=tf)
        all_signals = signal_result['all']
        
        if not all_signals:
            continue
        
        # 2. 序列分析
        seq_result = analyze_sequence_v11(all_signals, params=params)
        
        # 3. 共振评估
        tf_sequences = {tf: seq_result}
        resonance = evaluate_full_resonance_v11(
            all_signals=all_signals,
            tf_sequences=tf_sequences,
            ohlcv=window,
        )
        
        # 4. 入场决策
        decision = make_entry_decision_v11(resonance, seq_result, params, tf_sequences=tf_sequences)
        
        if decision['action'] != 'enter' and not force_enter_all:
            continue
        
        entry_price = decision.get('entry_price')
        direction = decision.get('direction')
        sl = decision.get('sl')
        tp = decision.get('tp')
        rr = decision.get('rr', 0)
        
        if not entry_price or not direction or not sl or not tp:
            continue
        
        if rr < min_rr and not force_enter_all:
            continue
        
        # 5. 模拟交易: 从i+1开始, 直到止损/止盈/收盘
        entry_idx = i
        exit_idx = -1
        exit_price = None
        won = False
        
        for j in range(i + 1, min(i + 60, n)):  # 最多持60根K线
            bar = ohlcv[j]
            
            if direction == 'bull':
                # 止盈
                if bar['h'] >= tp:
                    exit_idx = j
                    exit_price = tp
                    won = True
                    break
                # 止损
                if bar['l'] <= sl:
                    exit_idx = j
                    exit_price = sl
                    won = False
                    break
            else:
                # 止盈
                if bar['l'] <= tp:
                    exit_idx = j
                    exit_price = tp
                    won = True
                    break
                # 止损
                if bar['h'] >= sl:
                    exit_idx = j
                    exit_price = sl
                    won = False
                    break
        
        # 没有触发止盈止损: 以最后价格平仓
        if exit_idx == -1:
            exit_idx = min(i + 60, n - 1)
            exit_price = ohlcv[exit_idx]['c']
            if direction == 'bull':
                won = exit_price > entry_price
            else:
                won = exit_price < entry_price
        
        # 计算盈亏
        if direction == 'bull':
            pnl_pct = (exit_price - entry_price) / entry_price * 100
            actual_rr = abs(exit_price - entry_price) / abs(entry_price - sl) if sl != entry_price else 0
        else:
            pnl_pct = (entry_price - exit_price) / entry_price * 100
            actual_rr = abs(entry_price - exit_price) / abs(sl - entry_price) if sl != entry_price else 0
        
        # 序列信息
        best_seq = seq_result.get('best_sequence', {})
        seq_name = best_seq.get('name', 'Scout') if best_seq else 'Scout'
        avg_dist = best_seq.get('avg_distance', 0) if best_seq else 0
        
        # 市场阶段
        phase = detect_market_phase(window)
        
        trade = TradeRecord(
            symbol=symbol,
            direction=direction,
            signal_type=seq_name,
            entry_idx=entry_idx,
            entry_price=round(entry_price, 2),
            exit_idx=exit_idx,
            exit_price=round(exit_price, 2),
            sl=round(sl, 2),
            tp=round(tp, 2),
            rr=round(actual_rr, 2),
            pnl_pct=round(pnl_pct, 2),
            won=won,
            resonance_grade=decision.get('grade', 'D'),
            confidence=decision.get('confidence', 0.5),
            avg_signal_dist=round(avg_dist, 1),
            phase=phase,
            tf=tf,
        )
        trades.append(trade)
    
    if not trades:
        return {'trades': [], 'stats': {'no_trades': True}}
    
    # 计算统计
    stats = calc_trade_stats(trades)
    
    return {
        'trades': trades,
        'stats': stats,
        'params': params,
        'n_trades': len(trades),
    }


# ═══════════════════════════════════════════════════════════════════════
# Statistics
# ═══════════════════════════════════════════════════════════════════════

def calc_trade_stats(trades: List[TradeRecord]) -> Dict:
    """计算交易统计"""
    if not trades:
        return {}
    
    n = len(trades)
    wins = [t for t in trades if t.won]
    losses = [t for t in trades if not t.won]
    n_wins = len(wins)
    n_losses = len(losses)
    
    win_rate = n_wins / n * 100 if n > 0 else 0
    
    # 盈亏比
    avg_win = sum(t.rr for t in wins) / n_wins if n_wins > 0 else 0
    avg_loss = sum(abs(t.rr) for t in losses) / n_losses if n_losses > 0 else 0
    avg_rr = avg_win / avg_loss if avg_loss > 0 else avg_win
    
    # Profit Factor
    total_win_pnl = sum(max(t.pnl_pct, 0) for t in trades)
    total_loss_pnl = abs(sum(min(t.pnl_pct, 0) for t in trades))
    profit_factor = total_win_pnl / total_loss_pnl if total_loss_pnl > 0 else float('inf')
    
    # 总收益
    total_return = sum(t.pnl_pct for t in trades)
    
    # 最大回撤
    cumulative = 0
    peak = 0
    max_dd = 0
    for t in trades:
        cumulative += t.pnl_pct
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd
    
    # 按信号类型分
    by_signal = defaultdict(list)
    for t in trades:
        by_signal[t.signal_type].append(t)
    
    signal_stats = {}
    for sig_type, sig_trades in by_signal.items():
        sig_wins = [t for t in sig_trades if t.won]
        signal_stats[sig_type] = {
            'n': len(sig_trades),
            'wr': len(sig_wins) / len(sig_trades) * 100,
            'avg_rr': sum(t.rr for t in sig_trades) / len(sig_trades),
        }
    
    # 按阶段分
    by_phase = defaultdict(list)
    for t in trades:
        by_phase[t.phase].append(t)
    
    phase_stats = {}
    for phase, p_trades in by_phase.items():
        p_wins = [t for t in p_trades if t.won]
        phase_stats[phase] = {
            'n': len(p_trades),
            'wr': len(p_wins) / len(p_trades) * 100,
            'avg_rr': sum(t.rr for t in p_trades) / len(p_trades),
        }
    
    return {
        'n_trades': n,
        'n_wins': n_wins,
        'n_losses': n_losses,
        'win_rate': round(win_rate, 1),
        'avg_rr': round(avg_rr, 2),
        'profit_factor': round(profit_factor, 2),
        'total_return': round(total_return, 1),
        'max_drawdown': round(max_dd, 1),
        'avg_confidence': round(sum(t.confidence for t in trades) / n, 3),
        'by_signal_type': signal_stats,
        'by_phase': phase_stats,
    }


# ═══════════════════════════════════════════════════════════════════════
# Batch backtest across universe
# ═══════════════════════════════════════════════════════════════════════

def batch_backtest_v11(
    symbol_list: List[str],
    params: Dict = None,
    interval: str = 'daily',
    bars: int = 300,
    label: str = 'batch',
    max_concurrent: int = 3,
    batch_delay: float = 1.5,
    on_progress=None,
) -> Dict:
    """批量回测 — 全量验证
    
    Args:
        symbol_list: 代码列表
        params: 统一参数(每个股票会自适应)
        interval: 时间框架
        bars: K线数
        label: 标签
        max_concurrent: 并发数
        batch_delay: 批次延迟
        on_progress: 回调 fn(done, total, symbol, stats)
    
    Returns:
        {
            'overall': 整体统计,
            'per_symbol': {symbol: backtest_result},
            'top_performers': [...],
            'worst_performers': [...],
        }
    """
    from .rate_limiter import get_limiter
    from .tf_data import fetch_single_tf
    
    limiter = get_limiter(max_rps=3, max_concurrent=max_concurrent)
    
    results = {}
    total = len(symbol_list)
    
    for i, symbol in enumerate(symbol_list):
        # 获取数据
        ohlcv = fetch_single_tf(symbol, interval=interval, bars=bars, limiter=limiter)
        
        if not ohlcv or len(ohlcv) < 60:
            log.warning(f"{symbol}: insufficient data ({len(ohlcv) if ohlcv else 0} bars)")
            if on_progress:
                on_progress(i + 1, total, symbol, None)
            continue
        
        # 自适应的阶段感知参数
        from .adaptive_params import calc_stock_params, detect_market_phase
        if params is None:
            phase = detect_market_phase(ohlcv)
            stock_params = calc_stock_params(ohlcv, symbol=symbol, phase=phase, tf=interval)
        else:
            stock_params = dict(params)
        
        # 回测
        bt_result = backtest_single_stock_v11(ohlcv, symbol=symbol, params=stock_params, tf=interval)
        
        if bt_result and bt_result.get('n_trades', 0) > 0:
            results[symbol] = bt_result
            stats = bt_result['stats']
            log.info(f"  [{i+1}/{total}] {symbol}: WR={stats.get('win_rate','?')}% "
                     f"RR={stats.get('avg_rr','?')} N={stats.get('n_trades',0)} "
                     f"PF={stats.get('profit_factor','?')}")
        
        if on_progress:
            on_progress(i + 1, total, symbol, bt_result.get('stats') if bt_result else None)
        
        # 批次延迟控制
        if batch_delay > 0 and (i + 1) % max_concurrent == 0 and i + 1 < total:
            time.sleep(batch_delay)
        
        # 每20个请求长休息
        if (i + 1) % 20 == 0 and i + 1 < total:
            log.info(f"Batch pause: 2s after {i+1} stocks")
            time.sleep(2)
    
    # 汇总统计
    if not results:
        return {'overall': {'n_symbols': 0, 'n_trades': 0}, 'per_symbol': {}}
    
    all_stats = [r['stats'] for r in results.values() if r.get('stats')]
    
    total_trades = sum(s.get('n_trades', 0) for s in all_stats)
    total_wins = sum(s.get('n_wins', 0) for s in all_stats)
    
    if total_trades > 0:
        overall_wr = total_wins / total_trades * 100
    else:
        overall_wr = 0
    
    avg_rr = sum(s.get('avg_rr', 0) for s in all_stats) / len(all_stats) if all_stats else 0
    avg_pf = sum(s.get('profit_factor', 0) for s in all_stats) / len(all_stats) if all_stats else 0
    
    # 排序
    ranked = sorted(
        [(sym, r['stats'].get('win_rate', 0), r['stats'].get('avg_rr', 0), r['stats'].get('n_trades', 0))
         for sym, r in results.items()],
        key=lambda x: x[1], reverse=True
    )
    
    return {
        'overall': {
            'n_symbols': len(results),
            'n_attempted': total,
            'n_trades': total_trades,
            'n_wins': total_wins,
            'win_rate': round(overall_wr, 1),
            'avg_rr': round(avg_rr, 2),
            'avg_profit_factor': round(avg_pf, 2),
            'label': label,
        },
        'per_symbol': results,
        'top_performers': ranked[:10],
        'worst_performers': ranked[-5:] if len(ranked) > 5 else [],
    }


# ═══════════════════════════════════════════════════════════════════════
# Save / Load results
# ═══════════════════════════════════════════════════════════════════════

def save_backtest_results(results: Dict, name: str = 'backtest'):
    """保存回测结果"""
    # 精简输出
    output = {
        'overall': results.get('overall'),
        'top_performers': results.get('top_performers'),
        'worst_performers': results.get('worst_performers'),
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'per_symbol_summary': {
            sym: {
                'n_trades': r.get('n_trades', 0),
                'wr': r['stats'].get('win_rate', 0),
                'rr': r['stats'].get('avg_rr', 0),
                'pf': r['stats'].get('profit_factor', 0),
                'ret': r['stats'].get('total_return', 0),
            }
            for sym, r in results.get('per_symbol', {}).items()
        }
    }
    
    path = OUTPUT_DIR / f'{name}_results.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    log.info(f"Results saved to {path}")
    
    # 同时生成文本报告
    report_path = OUTPUT_DIR / f'{name}_report.txt'
    report = []
    report.append("=" * 60)
    report.append(f"SMC V11 Backtest Report: {name}")
    report.append(f"Time: {output['timestamp']}")
    report.append("=" * 60)
    report.append("")
    
    overall = output.get('overall', {})
    report.append(f"Symbols: {overall.get('n_symbols', 0)}/{overall.get('n_attempted', 0)}")
    report.append(f"Total Trades: {overall.get('n_trades', 0)}")
    report.append(f"Win Rate: {overall.get('win_rate', 0)}%")
    report.append(f"Avg RR: {overall.get('avg_rr', 0)}x")
    report.append(f"Avg PF: {overall.get('avg_profit_factor', 0)}x")
    report.append("")
    
    report.append("--- Top Performers ---")
    for sym, wr, rr, n in output.get('top_performers', []):
        report.append(f"  {sym}: WR={wr}% RR={rr} N={n}")
    
    report.append("")
    report.append("--- Worst Performers ---")
    for sym, wr, rr, n in output.get('worst_performers', []):
        report.append(f"  {sym}: WR={wr}% RR={rr} N={n}")
    
    report_path.write_text('\n'.join(report))
    log.info(f"Report saved to {report_path}")
    
    return str(path), str(report_path)


# ═══════════════════════════════════════════════════════════════════════
# Quick test
# ═══════════════════════════════════════════════════════════════════════

def test_single(symbol: str = '600519.SH', interval: str = 'daily'):
    """测试单股票回测"""
    from .tf_data import fetch_single_tf
    from .rate_limiter import get_limiter
    
    limiter = get_limiter(max_rps=3)
    ohlcv = fetch_single_tf(symbol, interval=interval, bars=300, limiter=limiter)
    
    if not ohlcv or len(ohlcv) < 60:
        print(f"Not enough data for {symbol}")
        return
    
    from .adaptive_params import calc_stock_params, detect_market_phase
    
    phase = detect_market_phase(ohlcv)
    params = calc_stock_params(ohlcv, symbol=symbol, phase=phase, tf=interval)
    
    print(f"\n=== Testing {symbol} ===")
    print(f"Bars: {len(ohlcv)}, Phase: {phase}")
    print(f"Params: SL={params['sl_pct']}% TP={params['tp_pct']}% "
          f"FVG={params['fvg_min_width']:.5f} SweepWick={params['sweep_wick_ratio']}")
    
    result = backtest_single_stock_v11(ohlcv, symbol=symbol, params=params, tf=interval)
    
    if result.get('n_trades', 0) > 0:
        stats = result['stats']
        print(f"\nResults:")
        print(f"  Trades: {stats.get('n_trades', 0)} ({stats.get('n_wins', 0)}W / {stats.get('n_losses', 0)}L)")
        print(f"  WR: {stats.get('win_rate', 0)}%")
        print(f"  Avg RR: {stats.get('avg_rr', 0)}x")
        print(f"  PF: {stats.get('profit_factor', 0)}x")
        print(f"  Return: {stats.get('total_return', 0)}%")
        print(f"  Max DD: {stats.get('max_drawdown', 0)}%")
        
        # 按信号类型
        by_sig = stats.get('by_signal_type', {})
        print(f"\n  By Signal Type:")
        for sig, s in sorted(by_sig.items(), key=lambda x: x[1]['n'], reverse=True):
            print(f"    {sig}: N={s['n']} WR={s['wr']:.0f}% RR={s['avg_rr']:.2f}x")
    else:
        print("  No trades generated")
    
    return result


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    test_single()
