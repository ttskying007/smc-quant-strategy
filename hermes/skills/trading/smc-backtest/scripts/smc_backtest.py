#!/usr/bin/env python3
"""
SMC Backtest Runner — 可独立运行的 SMC 回测脚本

用法:
  python3 scripts/smc_backtest.py --market cn --symbol 000001.SZ --interval daily --strategy full-smc
  python3 scripts/smc_backtest.py --market crypto --symbol BTCUSDT --strategy sweep-fvg --tp-rr 2.5
"""

import json, sys, math, urllib.request, argparse
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
from smc_scanner import (
    fetch_data, normalize_klines, detect_fvg, detect_liquidity_sweep,
    detect_market_structure, detect_order_blocks, score_signal
)

BASE = "http://43.167.234.49:3101"
HEADERS = {"X-API-Key": "123456", "Content-Type": "application/json"}


class BacktestConfig:
    def __init__(self, **kwargs):
        self.market = kwargs.get('market', 'cn')
        self.symbol = kwargs.get('symbol', '000001.SZ')
        self.interval = kwargs.get('interval', 'daily')
        self.limit = kwargs.get('limit', 500)
        self.reserve = kwargs.get('reserve', 80)
        self.strategy = kwargs.get('strategy', 'fvg-only')
        self.sl_atr_mult = kwargs.get('sl_atr_mult', 1.5)
        self.tp_rr = kwargs.get('tp_rr', 2.0)
        self.min_score = kwargs.get('min_score', 0)
        self.exchange = kwargs.get('exchange', 'binance')
        self.only_long = kwargs.get('only_long', False)  # True=仅多单


def calc_atr(bars, period=14):
    if len(bars) < period:
        return bars[-1]['h'] - bars[-1]['l'] if bars else 0
    trs = []
    for i in range(-period, 0):
        tr = max(
            bars[i]['h'] - bars[i]['l'],
            abs(bars[i]['h'] - bars[i-1]['c']),
            abs(bars[i]['l'] - bars[i-1]['c'])
        )
        trs.append(tr)
    return sum(trs) / len(trs)


def calc_sl(signal, entry, atr, config):
    if config.sl_atr_mult == 0:
        return None
    if signal['direction'] == 'long':
        return entry - atr * config.sl_atr_mult
    else:
        return entry + atr * config.sl_atr_mult


def simulate_trade(bars, start_idx, entry, sl, tp, direction):
    for i in range(start_idx, len(bars)):
        b = bars[i]
        if direction == 'long':
            if b['l'] <= sl:
                return {'exit': sl, 'reason': 'sl', 'pnl': (sl - entry)/entry, 'bars': i-start_idx+1}
            if b['h'] >= tp:
                return {'exit': tp, 'reason': 'tp', 'pnl': (tp - entry)/entry, 'bars': i-start_idx+1}
        else:
            if b['h'] >= sl:
                return {'exit': sl, 'reason': 'sl', 'pnl': (entry - sl)/entry, 'bars': i-start_idx+1}
            if b['l'] <= tp:
                return {'exit': tp, 'reason': 'tp', 'pnl': (entry - tp)/entry, 'bars': i-start_idx+1}
    last = bars[-1]['c']
    pnl = (last - entry)/entry if direction == 'long' else (entry - last)/entry
    return {'exit': last, 'reason': 'eod', 'pnl': pnl, 'bars': len(bars)-start_idx+1}


def normalize_klines(raw, market):
    """统一K线格式为 {o, h, l, c, v}，并反转确保旧->新"""
    # API可能返回 {schema, data: [...]} 格式
    raw_data = raw.get('data', raw) if isinstance(raw, dict) else raw
    if isinstance(raw_data, list):
        bars = []
        for k in raw_data:
            if isinstance(k, dict):
                bars.append({
                    'o': float(k.get('open', k.get('o', 0))),
                    'h': float(k.get('high', k.get('h', 0))),
                    'l': float(k.get('low', k.get('l', 0))),
                    'c': float(k.get('close', k.get('c', 0))),
                    'v': float(k.get('volume', k.get('vol', k.get('v', 0)))),
                    't': k.get('time', k.get('t', ''))
                })
            elif isinstance(k, list) and len(k) >= 5:
                bars.append({'o': float(k[1]), 'h': float(k[2]), 'l': float(k[3]), 'c': float(k[4]),
                             'v': float(k[5]) if len(k) > 5 else 0, 't': k[0]})
        # API倒序(最新在前)需要反转
        if len(bars) >= 2 and bars[0]['t'] > bars[1]['t']:
            bars.reverse()
        return bars
    return []

def backtest(config):
    print(f"\n{'='*60}")
    print(f"  回测: {config.symbol} | {config.market.upper()} | {config.interval}")
    print(f"  策略: {config.strategy} | SL: {config.sl_atr_mult}×ATR | TP: {config.tp_rr}R")
    print(f"  仅多单: {config.only_long}")
    print(f"{'='*60}")

    raw = fetch_data(config.market, config.symbol, config.interval, config.limit, config.exchange)
    bars = normalize_klines(raw, config.market)
    if len(bars) < config.reserve + 50:
        print(f"❌ 数据不足 (获取到{len(bars)}根K线)")
        return

    trades = []
    for i in range(config.reserve, len(bars) - 3):
        win = bars[:i+1]
        fvg = detect_fvg(win)
        swp = detect_liquidity_sweep(win)

        direction = None
        if config.strategy == 'fvg-only' and fvg:
            direction = fvg[-1]['direction']
        elif config.strategy == 'sweep-fvg' and fvg and swp:
            # 找方向一致的最强组合
            best = None
            for f in fvg[-5:]:
                for s in swp[-5:]:
                    if s['direction'] == f['direction'] and abs(s['index'] - f['index']) <= 10:
                        score = f['strength'] + s['wick_ratio'] * 0.5
                        if best is None or score > best[2]:
                            best = (f, s, score, f['direction'])
            if best:
                direction = best[3]
        elif config.strategy == 'full-smc' and fvg and swp:
            struct = detect_market_structure(win)
            best = None
            if struct and struct.get('direction'):
                for f in fvg[-5:]:
                    for s in swp[-5:]:
                        if s['direction'] == f['direction'] == struct['direction']:
                            if best is None or f['strength'] + s['wick_ratio'] > best[2]:
                                best = (f, s, f['strength'] + s['wick_ratio'], struct['direction'])
                if best:
                    direction = best[3]
        elif config.strategy == 'ob-reclaim':
            ob = detect_order_blocks(win)
            direction = ob[-1]['direction'] if ob else None

        if not direction: continue
        if config.only_long and direction != 'long': continue

        entry = bars[i+1]['o']
        atr = calc_atr(win)
        sl = entry - atr * config.sl_atr_mult if direction == 'long' else entry + atr * config.sl_atr_mult
        tp = entry + (entry-sl) * config.tp_rr if direction == 'long' else entry - (sl-entry) * config.tp_rr

        result = simulate_trade(bars, i+2, entry, sl, tp, direction)
        result['entry'] = entry
        trades.append(result)

    # 绩效统计
    total = len(trades)
    if total == 0:
        print("\n❌ 没有符合条件的交易")
        return

    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    win_rate = len(wins) / total * 100
    avg_win = sum(t['pnl'] for t in wins) / len(wins) * 100 if wins else 0
    avg_loss = sum(t['pnl'] for t in losses) / len(losses) * 100 if losses else 0
    profit_factor = abs(sum(t['pnl'] for t in wins) / sum(t['pnl'] for t in losses)) if losses and sum(t['pnl'] for t in losses) != 0 else float('inf')
    rr_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
    total_return = sum(t['pnl'] for t in trades) * 100

    # 最大回撤
    equity = []; run = 0
    for t in trades:
        run += t['pnl']
        equity.append(run)
    peak = max(equity) if equity else 0
    trough = min(equity) if equity else 0
    max_dd = (peak - trough) / peak * 100 if peak > 0 else 0

    returns = [t['pnl'] for t in trades]
    avg_r = sum(returns) / len(returns)
    std_r = math.sqrt(sum((r - avg_r)**2 for r in returns) / len(returns)) if len(returns) > 1 else 0
    sharpe = (avg_r / std_r * math.sqrt(252)) if std_r > 0 else 0

    print(f"""
{'─'*60}                                                                                                                                                                                                                                   
📊 绩效结果                                                                                                                                                                                                                                  
{'─'*60}                                                                                                                                                                                                                                    
  总交易次数:    {total:>6}                                                                                                                                                                                                                 
  胜率:          {win_rate:>6.1f}%                                                                                                                                                                                                          
  盈利交易:      {len(wins):>6}                                                                                                                                                                                                             
  亏损交易:      {len(losses):>6}                                                                                                                                                                                                           
  平均盈利:      +{avg_win:>5.2f}%                                                                                                                                                                                                          
  平均亏损:      {avg_loss:>+6.2f}%                                                                                                                                                                                                         
  盈亏比:        {rr_ratio:>6.2f}                                                                                                                                                                                                           
  盈利因子:      {profit_factor:>6.2f}                                                                                                                                                                                                      
  最大回撤:      {max_dd:>6.2f}%                                                                                                                                                                                                            
  Sharpe Ratio:  {sharpe:>6.2f}                                                                                                                                                                                                             
  总收益率:      {total_return:>+6.2f}%                                                                                                                                                                                                     
{'─'*60}
""")

def main():
    parser = argparse.ArgumentParser(description='SMC 回测脚本')
    parser.add_argument('--market', choices=['cn', 'hk', 'us', 'crypto'], default='cn')
    parser.add_argument('--symbol', default='000001.SZ')
    parser.add_argument('--interval', default='daily')
    parser.add_argument('--limit', type=int, default=500)
    parser.add_argument('--exchange', default='binance')
    parser.add_argument('--sl-atr-mult', type=float, default=1.5)
    parser.add_argument('--tp-rr', type=float, default=2.0)
    parser.add_argument('--only-long', action='store_true', help='仅交易多单')
    parser.add_argument('--strategy', default='fvg-only', choices=['fvg-only', 'sweep-fvg', 'full-smc', 'ob-reclaim'])
    args = parser.parse_args()

    config = BacktestConfig(
        market=args.market, symbol=args.symbol, interval=args.interval,
        limit=args.limit, exchange=args.exchange, strategy=args.strategy,
        sl_atr_mult=args.sl_atr_mult, tp_rr=args.tp_rr,
        only_long=args.only_long
    )
    backtest(config)


if __name__ == '__main__':
    main()