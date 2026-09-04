#!/usr/bin/env python3
# SMC V9 — Backtest Engine (Enhanced)
"""
SMC交易回测引擎 — 完整版本。

核心功能:
1. evaluate_trades() — 单股票模拟交易，含完整买卖日志
2. evaluate_params() — 多股票批量评估
3. compute_score() — WR^2.0评分公式

V9新增:
- 每笔交易含: 入场原因、出场原因、信号详情、结构标注引用
- 日志系统: 完整交易日志(JSON + 可读文本)
- KPI: WR, RR, PF, Sharpe, MaxDD, AvgReturn, WinAvg, LossAvg
- 交易明细: 含多信号引用、结构验证
"""

import math, logging, time
from datetime import datetime
from collections import defaultdict

try:
    from . import smc_config as config
    from .smc_signals import detect_all_signals, score_signal
    from .smc_hubble import fetch_kline, kline_to_ohlcv, calc_atr_pct
except ImportError:
    from v9 import smc_config as config
    from v9.smc_signals import detect_all_signals, score_signal
    from v9.smc_hubble import fetch_kline, kline_to_ohlcv, calc_atr_pct

log = logging.getLogger('smc_v9.backtest')


# ═══════════════════════════════════════════════════════════════════════
# 交易原因生成器
# ═══════════════════════════════════════════════════════════════════════

def _reason_entry(sig, ohlcv, idx, params):
    """生成入场原因描述。

    基于信号类型、位置、强度、以及当前市场上下文。
    """
    sig_type = sig['type']
    direction = sig.get('direction', 'bull')
    price = sig.get('price', sig.get('upper', sig.get('lower', ohlcv[idx + 1]['o'] if idx + 1 < len(ohlcv) else 0)))
    strength = sig.get('strength', 0)
    atr = params.get('atr_pct', calc_atr_pct(ohlcv))

    reason_parts = []

    # 信号类型基础原因
    base_reasons = {
        'FVG': 'FVG未回补区域形成 买方/卖方缺口',
        'IFVG': '反向FVG确认 趋势增强',
        'SweepUp': '上方流动性扫荡 多头陷阱 空头入场',
        'SweepDown': '下方流动性扫荡 空头陷阱 多头入场',
        'OB_Bull': '机构订单块(买方) 大型买盘聚集区',
        'OB_Bear': '机构订单块(卖方) 大型卖盘聚集区',
        'BPR_Bull': '平衡区突破(买方) 需求集中释放',
        'BPR_Bear': '平衡区突破(卖方) 供应集中释放',
        'MSB_Up': '市场结构向上突破 趋势转多',
        'MSB_Down': '市场结构向下突破 趋势转空',
    }
    reason_parts.append(base_reasons.get(sig_type, f'SMC信号:{sig_type}'))

    # 方向说明
    if direction == 'bull':
        reason_parts.append('方向:做多')
    else:
        reason_parts.append('方向:做空')

    # 强度
    if strength > 2.0:
        reason_parts.append('强度:强')
    elif strength > 1.0:
        reason_parts.append('强度:中')
    else:
        reason_parts.append('强度:弱')

    # 波动率上下文
    if atr > 0:
        if atr > 5:
            reason_parts.append(f'波动率高({atr:.1f}% ATR)')
        elif atr < 1:
            reason_parts.append(f'波动率低({atr:.1f}% ATR)')

    return ' | '.join(reason_parts)


def _reason_exit(trade_result, bar_idx, exit_bar):
    """生成出场原因描述。

    Args:
        trade_result: {'hit_sl','hit_tp','partial','timeout','entry','exit',...}
        bar_idx: 出场时的K线索引
        exit_bar: 出场时的ohlcv bar
    """
    if trade_result.get('hit_tp'):
        return f"触发止盈(tp={trade_result.get('tp_price',0):.2f}) 获利{trade_result.get('ret',0):.2f}%"
    elif trade_result.get('hit_sl'):
        return f"触发止损(sl={trade_result.get('sl_price',0):.2f}) 亏损{trade_result.get('ret',0):.2f}%"
    elif trade_result.get('partial'):
        return f"部分离场(未触SL/TP) 收益{trade_result.get('ret',0):.2f}%"
    elif trade_result.get('timeout'):
        return f"超时未达标(60根K线) 强制出场 收益{trade_result.get('ret',0):.2f}%"
    else:
        candle_desc = f"收盘{exit_bar.get('c',0):.2f}" if exit_bar else "N/A"
        return f"自动出场 {candle_desc} 收益{trade_result.get('ret',0):.2f}%"


def _reason_trade_quality(sig, ohlcv, idx):
    """给出交易质量评估。

    基于: 信号汇聚(多信号重叠)、位置(是否在趋势中)、成交量配合。
    """
    quality = 0
    reasons = []
    bar = ohlcv[idx] if idx < len(ohlcv) else None
    if not bar:
        return 2.0, ['数据不足']

    # 成交量检查
    if idx >= 10:
        avg_vol = sum(ohlcv[j]['v'] for j in range(idx - 10, idx)) / 10
        if avg_vol > 0 and bar['v'] > avg_vol * 1.5:
            quality += 1
            reasons.append('放量确认')
        elif avg_vol > 0 and bar['v'] > avg_vol:
            quality += 0.5
            reasons.append('量能正常')

    # 波动率检查(大K线更有意义)
    body = abs(bar['c'] - bar['o'])
    range_pct = body / bar['o'] * 100 if bar['o'] > 0 else 0
    if range_pct > 2:
        quality += 1
        reasons.append('K线实体大(高置信度)')

    # 位置检查(靠近EQL更好)
    mid = (bar['h'] + bar['l']) / 2
    if idx >= 20:
        eq_range = sum(ohlcv[j]['c'] for j in range(idx - 20, idx)) / 20
        dist = abs(mid - eq_range) / eq_range * 100 if eq_range > 0 else 0
        if dist < 1:
            quality += 0.5
            reasons.append('价格在EQL附近(均衡)')

    quality = min(quality, 5.0)
    if quality < 1:
        reasons.append('质量待观察')
    quality = max(quality, 1.0)

    return quality, reasons if reasons else ['正常']


# ═══════════════════════════════════════════════════════════════════════
# 单股票回测
# ═══════════════════════════════════════════════════════════════════════

def evaluate_trades(ohlcv, params):
    """生成并模拟交易 — 含完整入场/出场原因、信号日志。

    Args:
        ohlcv: [{'o','h','l','c','v'}, ...] 正序
        params: 参数dict

    Returns:
        dict: {n_trades, wins, losses, returns[], rr_list[], 
               trades[{完整交易日志}], trade_logs[文本描述]}
    """
    signals = detect_all_signals(ohlcv, params)
    if not signals:
        return _empty_result('no_signals')

    # 解参
    score_min = params.get('score_min', 0.5)
    confirm_range = params.get('confirm_range', 3)
    max_trades = params.get('max_trades', 3)
    sl_pct = params.get('sl_pct', 3.0)
    tp_pct = params.get('tp_pct', 9.0)
    vol_adapt = params.get('vol_adapt_sl', 0.6)
    atr_min = params.get('atr_min_pct', 0.3)
    atr_max = params.get('atr_max_pct', 8.0)

    # TP/SL >= 1.5
    if tp_pct / sl_pct < 1.5:
        return _empty_result('tp_sl_ratio')

    # ATR过滤
    atr_pct = calc_atr_pct(ohlcv)
    if atr_pct > 0:
        if atr_pct < atr_min or atr_pct > atr_max:
            return _empty_result('atr_out_of_range')

    # 信号评分+排序
    scored = [(score_signal(s, ohlcv), s) for s in signals]
    scored.sort(key=lambda x: -x[0])

    trades = []
    trade_logs = []
    trade_rejection = []

    for sig_score, sig in scored:
        if sig_score < score_min:
            continue
        if len(trades) >= max_trades:
            break
        idx = sig['idx']

        # 防聚集
        too_close = any(abs(t['idx'] - idx) <= confirm_range for t in trades)
        if too_close:
            trade_rejection.append({
                'idx': idx, 'type': sig['type'], 'reason': 'clustering',
                'score': sig_score,
            })
            continue

        # 入场价格: 信号后下一根K线开盘价
        entry = ohlcv[idx + 1]['o'] if idx + 1 < len(ohlcv) else ohlcv[idx]['c']

        # 波动率自适应SL/TP
        vol_factor = 1.0 - vol_adapt * (1.0 - min(atr_pct / 5.0, 1.0))
        sl_adapted = max(0.5, sl_pct * vol_factor)
        tp_adapted = max(sl_adapted * 1.5, tp_pct * vol_factor)

        is_bull = 'Bull' in sig['type'] or sig.get('direction') == 'bull'

        if is_bull:
            sl = entry * (1 - sl_adapted / 100)
            tp = entry * (1 + tp_adapted / 100)
        else:
            sl = entry * (1 + sl_adapted / 100)
            tp = entry * (1 - tp_adapted / 100)

        # 模拟出场
        hit_sl = hit_tp = False
        exit_price = entry
        exit_candle_idx = idx + 2
        max_lookahead = min(idx + 60, len(ohlcv))

        for j in range(idx + 2, max_lookahead):
            bar = ohlcv[j]
            if is_bull:
                if bar['l'] <= sl:
                    hit_sl, exit_price = True, sl
                    exit_candle_idx = j
                    break
                if bar['h'] >= tp:
                    hit_tp, exit_price = True, tp
                    exit_candle_idx = j
                    break
            else:
                if bar['h'] >= sl:
                    hit_sl, exit_price = True, sl
                    exit_candle_idx = j
                    break
                if bar['l'] <= tp:
                    hit_tp, exit_price = True, tp
                    exit_candle_idx = j
                    break

        # 收益率
        ret = (exit_price - entry) / entry * 100
        if not is_bull:
            ret = -ret

        # 实际R:R
        if hit_tp:
            rr = abs(tp_adapted / sl_adapted)
        elif hit_sl:
            rr = abs(ret) / sl_adapted if ret != 0 else 0.001
        else:
            rr = abs(tp_adapted / sl_adapted) * 0.5

        rr = max(rr, 0.001)

        # 入场原因 (文字描述)
        entry_reason = _reason_entry(sig, ohlcv, idx, params)

        # 出场原因
        trade_result_info = {
            'hit_sl': hit_sl, 'hit_tp': hit_tp,
            'partial': not hit_sl and not hit_tp,
            'timeout': not hit_sl and not hit_tp and exit_candle_idx >= max_lookahead - 1,
            'ret': ret, 'sl_price': sl, 'tp_price': tp,
        }
        exit_bar = ohlcv[exit_candle_idx] if exit_candle_idx < len(ohlcv) else None
        exit_reason = _reason_exit(trade_result_info, exit_candle_idx, exit_bar)

        # 交易质量
        quality, quality_reasons = _reason_trade_quality(sig, ohlcv, idx)

        # 构建完整交易结构
        trade = {
            'idx': idx,
            'entry': round(entry, 2),
            'exit': round(exit_price, 2),
            'sl': round(sl, 2),
            'tp': round(tp, 2),
            'ret': round(ret, 2),
            'win': ret > 0,
            'rr': round(rr, 2),
            'direction': 'long' if is_bull else 'short',
            'signal_type': sig['type'],
            'signal_score': round(sig_score, 1),
            'signals_total': len(signals),

            # V9新增: 完整原因
            'entry_reason': entry_reason,
            'exit_reason': exit_reason,
            'quality_score': round(quality, 1),
            'quality_reasons': quality_reasons,

            # 信号详情
            'signal': {
                'type': sig['type'],
                'idx': sig['idx'],
                'direction': sig.get('direction', ''),
                'strength': round(sig.get('strength', 0), 2),
                'upper': sig.get('upper', None),
                'lower': sig.get('lower', None),
                'break_level': sig.get('break_level', None),
                'wick_ratio': sig.get('wick_ratio', None),
                'score': round(sig_score, 1),
            },

            # 出场详情
            'exit_detail': {
                'hit_sl': hit_sl,
                'hit_tp': hit_tp,
                'exit_candle': exit_candle_idx,
                'sl_adapted': round(sl_adapted, 2),
                'tp_adapted': round(tp_adapted, 2),
                'atr_pct': round(atr_pct, 2),
            },

            'sl_adapted': round(sl_adapted, 2),
            'tp_adapted': round(tp_adapted, 2),
        }
        trades.append(trade)

        # 可读日志文本
        log_entry = _format_trade_log(trade)
        trade_logs.append(log_entry)

    n = len(trades)
    wins = sum(1 for t in trades if t['win'])
    returns = [t['ret'] for t in trades]
    rr_list = [t['rr'] for t in trades]

    return {
        'n_trades': n,
        'wins': wins,
        'losses': n - wins,
        'returns': returns,
        'rr_list': rr_list,
        'signal_scores': [t['signal_score'] for t in trades],
        'signals_per_stock': len(signals),
        'trades': trades,
        'trade_logs': trade_logs,      # V9: 可读交易日志
        'rejected_signals': trade_rejection,  # V9: 被过滤的信号
        'atr_pct': round(atr_pct, 2),
        'params_used': {
            'sl_pct': sl_pct,
            'tp_pct': tp_pct,
            'score_min': score_min,
            'max_trades': max_trades,
            'confirm_range': confirm_range,
            'vol_adapt_sl': vol_adapt,
        },
    }


def _format_trade_log(trade):
    """生成单笔交易的人类可读日志。"""
    win_str = '✅ 盈利' if trade['win'] else '❌ 亏损'
    direction = '🟢 做多' if trade['direction'] == 'long' else '🔴 做空'
    return (
        f"━━━ 交易 #{trade['idx']} ━━━\n"
        f"方向: {direction}\n"
        f"信号: {trade['signal_type']} (评分:{trade['signal_score']})\n"
        f"入场: {trade['entry']} | 出场: {trade['exit']}\n"
        f"SL: {trade['sl']} | TP: {trade['tp']}\n"
        f"收益率: {trade['ret']}% | R:R: {trade['rr']}\n"
        f"{win_str}\n"
        f"入场原因: {trade.get('entry_reason', '-')[:80]}\n"
        f"出场原因: {trade.get('exit_reason', '-')[:80]}\n"
        f"质量评分: {trade.get('quality_score', '-')}\n"
    )


def _empty_result(reason='no_trades'):
    return {
        'n_trades': 0, 'wins': 0, 'losses': 0,
        'returns': [], 'rr_list': [], 'signal_scores': [],
        'signals_per_stock': 0, 'trades': [], 'trade_logs': [],
        'rejected_signals': [],
        'error': reason,
    }


# ═══════════════════════════════════════════════════════════════════════
# 批量评估
# ═══════════════════════════════════════════════════════════════════════

def evaluate_params(params, stocks, progress_cb=None):
    """多股票参数评估 — 保留每只股票的完整交易日志。

    Args:
        params: 参数dict
        stocks: ['600519.SH', ...]
        progress_cb: optional callback(idx, total)

    Returns: dict with score, wr, n, pf, rr_avg, ret, coverage, sr, avg_quality, per_stock
    """
    all_results = {}
    per_stock_detail = {}
    total = len(stocks)

    for idx, symbol in enumerate(stocks):
        try:
            kline = fetch_kline(symbol, 'daily', 120)
            if not kline or len(kline) < 30:
                all_results[symbol] = _empty_result('no_data')
                all_results[symbol]['symbol'] = symbol
                continue

            ohlcv = kline_to_ohlcv(kline)
            result = evaluate_trades(ohlcv, params)

            key = {
                'symbol': symbol,
                'n_trades': result['n_trades'],
                'wins': result['wins'],
                'losses': result['losses'],
                'returns': result['returns'],
                'rr_list': result['rr_list'],
                'trades': result.get('trades', []),
                'trade_logs': result.get('trade_logs', []),
            }
            all_results[symbol] = key
            per_stock_detail[symbol] = {
                'trades': result.get('trades', []),
                'logs': result.get('trade_logs', []),
                'n': result['n_trades'],
            }

        except Exception as e:
            log.warning(f"evaluate_params {symbol}: {e}")
            all_results[symbol] = _empty_result(str(e))

        if progress_cb and idx % 5 == 0:
            progress_cb(idx, total)

    score_result = compute_score(all_results)
    score_result['per_stock'] = per_stock_detail

    return score_result


# ═══════════════════════════════════════════════════════════════════════
# 评分系统
# ═══════════════════════════════════════════════════════════════════════

def compute_score(eval_results):
    """V9评分 — WR^2.0 + 完整KPI.

    Returns:
        {'score', 'wr', 'n', 'pf', 'rr_avg', 'ret', 'coverage', 'sr',
         'avg_quality', 'max_drawdown', 'win_avg', 'loss_avg', ...}
    """
    total_trades = sum(r.get('n_trades', 0) for r in eval_results.values()
                       if isinstance(r, dict))
    total_wins = sum(r.get('wins', 0) for r in eval_results.values()
                     if isinstance(r, dict))
    all_returns = []
    all_rr = []
    all_quality = []

    stock_with_trades = 0
    total_stocks = len(eval_results)

    for r in eval_results.values():
        if not isinstance(r, dict):
            continue
        rets = r.get('returns', [])
        all_returns.extend(rets)
        all_rr.extend(r.get('rr_list', []))
        all_quality.extend(r.get('signal_scores', []))
        if rets:
            stock_with_trades += 1

    if total_trades == 0:
        return _zero_score(total_stocks)

    wr = total_wins / total_trades * 100
    rr_avg = sum(all_rr) / len(all_rr) if all_rr else 0
    ret_total = sum(all_returns) if all_returns else 0
    avg_quality = sum(all_quality) / len(all_quality) if all_quality else 0

    # PF
    gross_win = sum(r for r in all_returns if r > 0) or 0.001
    gross_loss = abs(sum(r for r in all_returns if r < 0)) or 0.001
    pf = gross_win / gross_loss

    # SR
    if len(all_returns) > 1:
        avg_r = sum(all_returns) / len(all_returns)
        var = sum((r - avg_r) ** 2 for r in all_returns) / len(all_returns)
        std = math.sqrt(var) if var > 0 else 1
        sr = avg_r / std * math.sqrt(252 if len(all_returns) > 10 else 1)
    else:
        sr = 0

    # MaxDD
    max_dd = _max_drawdown(all_returns)

    # 胜/败平均值
    win_rets = [r for r in all_returns if r > 0]
    loss_rets = [r for r in all_returns if r < 0]
    win_avg = sum(win_rets) / len(win_rets) if win_rets else 0
    loss_avg = sum(loss_rets) / len(loss_rets) if loss_rets else 0

    coverage_pct = stock_with_trades / total_stocks * 100 if total_stocks > 0 else 0

    # ═══ Core Score ═══
    score = (wr / 100) ** 2.0 * math.sqrt(min(total_trades, 50)) * min(3, pf) * min(2.5, rr_avg)

    if rr_avg < 1.2 and total_trades >= 3:
        score *= 0.1
    if total_trades < 8:
        score = 0
    elif total_trades < 15:
        score *= max(0.3, total_trades / 15)

    score = max(0, score)

    return {
        'score': round(score, 2),
        'wr': round(wr, 1),
        'n': total_trades,
        'wins': total_wins,
        'losses': total_trades - total_wins,
        'pf': round(pf, 2),
        'rr_avg': round(rr_avg, 2),
        'ret': round(ret_total, 2),
        'coverage': round(coverage_pct, 1),
        'sr': round(sr, 2),
        'avg_quality': round(avg_quality, 2),
        'max_drawdown': round(max_dd, 2),
        'win_avg': round(win_avg, 2),
        'loss_avg': round(loss_avg, 2),
        'win_rate_detail': {
            'wins': total_wins,
            'losses': total_trades - total_wins,
            'total': total_trades,
            'wr_pct': round(wr, 1),
        },
        'coverage_detail': {
            'stocks_with_trades': stock_with_trades,
            'total_stocks': total_stocks,
            'coverage_pct': round(coverage_pct, 1),
        },
    }


def _max_drawdown(returns):
    """计算最大回撤(%)"""
    if not returns:
        return 0
    peak = 0
    dd = 0
    running = 0
    for r in returns:
        running += r
        if running > peak:
            peak = running
        drawdown = peak - running
        if drawdown > dd:
            dd = drawdown
    return dd


def _zero_score(total_stocks):
    return {
        'score': 0, 'wr': 0, 'n': 0, 'wins': 0, 'losses': 0,
        'pf': 0, 'rr_avg': 0, 'ret': 0,
        'coverage': 0, 'sr': 0, 'avg_quality': 0,
        'max_drawdown': 0, 'win_avg': 0, 'loss_avg': 0,
        'win_rate_detail': {'wins': 0, 'losses': 0, 'total': 0, 'wr_pct': 0},
        'coverage_detail': {'stocks_with_trades': 0, 'total_stocks': total_stocks, 'coverage_pct': 0},
    }


# ═══════════════════════════════════════════════════════════════════════
# 快捷测试
# ═══════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print("=== SMC V9 Backtest Engine ===")
    print("Functions:", [
        n for n in dir() if n.startswith(('evaluate_', 'compute_', '_reason',
                                          '_format', '_max', '_empty'))
    ])
    print("\nNOTE: Run via v9.smc_webui or import")