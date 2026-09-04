#!/usr/bin/env python3
"""
SMC 实盘信号监控与推送系统 V1
================================
定时扫描可交易股票的最新信号, 发现入场机会时推送提醒.

工作流程:
1. 加载V14全量可交易股票列表
2. 每日/定时扫描最新K线
3. 检测信号序列+共振+入场决策
4. 如有入场信号, 推送提醒

使用方法:
  python3 smc_live_monitor.py --check     # 单次检查
  python3 smc_live_monitor.py --daemon    # 持续运行(每5分钟检查)
"""
import json, sys, time, os
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.sequencer_v11 import analyze_sequence_v11
from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
from v11.adaptive_params import calc_stock_params, detect_market_phase
from v11.weekly_trend import synthesize_weekly, weekly_trend

CACHE_DIR = Path('/root/.hermes/kline_cache')
RESULT_DIR = Path('/root/.hermes/smc_opt_v14')
SIGNAL_LOG = Path('/root/.hermes/smc_signals/live_signals.json')
SIGNAL_LOG.parent.mkdir(parents=True, exist_ok=True)

ALERT_THRESHOLD = 0.65  # 最低共振阈值
SL_DEFAULT = 0.5
TP_DEFAULT = 5.0


def load_tradable_stocks(limit=100):
    """加载V14可交易股票及其最优参数"""
    result_file = RESULT_DIR / 'v14_full.json'
    if not result_file.exists():
        print(f"V14结果不存在: {result_file}")
        return []
    
    with open(result_file) as f:
        data = json.load(f)
    
    stocks = data.get('stocks', data.get('results', []))
    tradable = []
    
    for s in stocks:
        perf = s.get('perf', {})
        if not perf or perf.get('n_trades', 0) < 3:
            continue
        wr = perf.get('win_rate', 0)
        if wr < 50:
            continue  # 只跟踪WR>=50%的股票
        
        tradable.append({
            'symbol': s.get('symbol'),
            'sl_pct': perf.get('sl_pct', SL_DEFAULT),
            'tp_pct': perf.get('tp_pct', TP_DEFAULT),
            'win_rate': wr,
            'avg_rr': perf.get('avg_rr', 0),
            'n_trades': perf.get('n_trades', 0),
        })
    
    tradable.sort(key=lambda x: -x['win_rate'] * min(x['avg_rr'], 10))
    return tradable[:limit]


def check_stock(symbol, sl_pct=0.5, tp_pct=5.0):
    """检查单只股票是否有入场信号
    
    Returns:
        有信号: Dict with entry info
        无信号: None
    """
    fname = f"{symbol.replace('.', '_')}_daily_300.json"
    fpath = CACHE_DIR / fname
    if not fpath.exists():
        return None
    
    ohlcv = json.loads(fpath.read_text())
    if not ohlcv or len(ohlcv) < 100:
        return None
    
    # Normalize dates
    for bar in ohlcv:
        if 'date' not in bar and 't' in bar:
            bar['date'] = str(bar['t'])
    
    phase = detect_market_phase(ohlcv)
    params = calc_stock_params(ohlcv, symbol, phase=phase, tf='daily')
    
    # 检测全部信号
    all_signals = detect_all_signals_v11(ohlcv, params=params, tf='daily')['all']
    if not all_signals or len(all_signals) < 5:
        return None
    
    # 最近60根K线内的信号
    recent_signals = [s for s in all_signals if s.get('idx', 0) >= len(ohlcv) - 60]
    if len(recent_signals) < 3:
        return None
    
    # 分析最新K线处的信号
    end_idx = len(ohlcv) - 1
    sigs_at_end = [s for s in all_signals if s.get('idx', 0) <= end_idx]
    
    seq_result = analyze_sequence_v11(sigs_at_end, params=params)
    best_seq = seq_result.get('best_sequence')
    if not best_seq:
        return None
    
    seq_name = best_seq.get('name', '')
    is_scout = 'SCOUT' in seq_name
    seq_dir = 'bull' if 'LONG' in seq_name else 'bear'
    
    # Bull-only for now
    if seq_dir != 'bull':
        return None
    
    # 共振和入场决策
    window = ohlcv[:end_idx + 1]
    tf_sequences = {'daily': seq_result}
    resonance = evaluate_full_resonance_v11(
        all_signals=sigs_at_end, tf_sequences=tf_sequences, ohlcv=window,
    )
    
    if resonance.total < ALERT_THRESHOLD:
        return None
    
    params_override = {**params, 'sl_pct': sl_pct, 'tp_pct': tp_pct}
    decision = make_entry_decision_v11(
        resonance, seq_result, params_override, tf_sequences=tf_sequences
    )
    
    if decision['action'] != 'enter':
        return None
    
    # 信号质量检查
    entry_sig = seq_result.get('entry_signal', {})
    sig_idx = entry_sig.get('idx', end_idx)
    sig_type = entry_sig.get('type', '')
    
    # 成交量检查
    if sig_idx > 30:
        bar_vol = ohlcv[sig_idx].get('v', ohlcv[sig_idx].get('vol', 0))
        avg_vol = sum(ohlcv[i].get('v', ohlcv[i].get('vol', 0))
                       for i in range(sig_idx-30, sig_idx)) / 30
        if bar_vol < avg_vol * 0.8:
            return None
    
    # Weekly trend filter
    weekly = synthesize_weekly(ohlcv[:end_idx+1])
    if len(weekly) >= 3:
        wt = weekly_trend(weekly, lookback=min(5, len(weekly)))
        if wt == 'down':
            return None
    
    last_bar = ohlcv[-1]
    current_price = last_bar['c']
    latest_date = last_bar.get('date', '?')
    
    return {
        'symbol': symbol,
        'time': datetime.now().isoformat(),
        'date': latest_date,
        'signal_type': seq_name,
        'direction': seq_dir,
        'resonance': round(resonance.total, 3),
        'grade': resonance.grade(),
        'confidence': round(decision['confidence'], 3),
        'entry_price': round(decision.get('entry_price', current_price), 2),
        'current_price': round(current_price, 2),
        'sl': round(decision.get('sl', current_price * (1 - sl_pct/100)), 2),
        'tp': round(decision.get('tp', current_price * (1 + tp_pct/100)), 2),
        'n_signals': len(recent_signals),
        'phase': phase,
    }


def check_all_stocks(stocks, limit_per_run=50):
    """批量检查可交易股票"""
    signals_found = []
    errors = 0
    
    # 优先检查WR高的股票
    stocks_sorted = sorted(stocks, key=lambda x: -x['win_rate'])
    
    for s in stocks_sorted[:limit_per_run]:
        try:
            result = check_stock(s['symbol'], s['sl_pct'], s['tp_pct'])
            if result:
                signals_found.append(result)
                print(f"  SIGNAL: {s['symbol']:12s} {result['signal_type']:20s} "
                      f"res={result['resonance']:.2f} price={result['current_price']:.2f}")
                time.sleep(0.1)  # 避免API限流
        except Exception as e:
            errors += 1
            if errors > 5:
                break
    
    return signals_found


def save_signals(signals):
    """保存/追加信号到日志"""
    existing = []
    if SIGNAL_LOG.exists():
        with open(SIGNAL_LOG) as f:
            try:
                existing = json.load(f)
            except:
                existing = []
    
    # 去重: 同股票30分钟内不重复
    now = datetime.now().timestamp()
    symbols_in_log = set()
    for s in existing:
        try:
            t = datetime.fromisoformat(s['time']).timestamp()
            if now - t < 1800:  # 30分钟内
                symbols_in_log.add(s['symbol'])
        except:
            pass
    
    new_signals = [s for s in signals if s['symbol'] not in symbols_in_log]
    if new_signals:
        existing.extend(new_signals)
        if len(existing) > 1000:
            existing = existing[-1000:]
        
        with open(SIGNAL_LOG, 'w') as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
    
    return new_signals


def format_alert(signal):
    """格式化为推送消息"""
    return (
        f"【SMC信号】{signal['symbol']}\n"
        f"类型: {signal['signal_type']}\n"
        f"方向: {signal['direction']}\n"
        f"共振: {signal['resonance']:.2f} ({signal['grade']})\n"
        f"入场: {signal['entry_price']:.2f} | 现价: {signal['current_price']:.2f}\n"
        f"SL: {signal['sl']:.2f} | TP: {signal['tp']:.2f}\n"
        f"日期: {signal['date']}"
    )


def main():
    import argparse
    parser = argparse.ArgumentParser(description='SMC 实盘信号监控')
    parser.add_argument('--check', action='store_true', help='单次检查')
    parser.add_argument('--daemon', action='store_true', help='持续监控')
    parser.add_argument('--limit', type=int, default=100, help='监控股票数')
    parser.add_argument('--interval', type=int, default=300, help='检查间隔(秒)')
    
    args = parser.parse_args()
    
    print(f"{'='*60}")
    print(f"SMC 实盘信号监控 V1")
    print(f"  加载V14可交易股票 (top {args.limit})...")
    print(f"{'='*60}")
    
    stocks = load_tradable_stocks(limit=args.limit)
    print(f"  加载 {len(stocks)} 只可交易股票")
    
    if not stocks:
        print("  错误: 没有可交易股票数据")
        sys.exit(1)
    
    if args.daemon:
        print(f"\n  持续监控模式 (每{args.interval}s检查一次)")
        print(f"  按 Ctrl+C 停止\n")
        while True:
            signals = check_all_stocks(stocks)
            new_sigs = save_signals(signals)
            
            for sig in new_sigs:
                print(f"\n{format_alert(sig)}\n")
            
            if not signals:
                print(f"  [{datetime.now().strftime('%H:%M:%S')}] 无信号")
            
            time.sleep(args.interval)
    else:
        signals = check_all_stocks(stocks)
        new_sigs = save_signals(signals)
        
        print(f"\n{'='*60}")
        print(f"检查完成: {len(signals)} 个信号, {len(new_sigs)} 个新增")
        print(f"{'='*60}")
        
        for sig in new_sigs:
            print(f"\n{format_alert(sig)}")


if __name__ == '__main__':
    main()
