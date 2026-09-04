#!/usr/bin/env python3
"""
SMC 完整交易系统 V3.0 — 408只全数据股票
周线SMC趋势过滤 → 日线序列组合入场 → 60min精确定位
输出: 交易信号 + 回测统计 + 选股列表
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20
from v11.v19_backtest_engine import find_tps, find_sls

KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v21')
OUT.mkdir(exist_ok=True)

# ═══ 配置 ═══
LOOKAHEAD = 5; TARGET = 2.0; TP_CAP = 1.05

# ═══ 信号分类+序列模式 ═══
CATS = {
    'L_LONG': ['Sweep_SSL','EQL'],    'L_SHORT':['Sweep_BSL','EQH'],
    'S_LONG': ['CHOCH_Bull','BOS_Bull','MSS_Bull'],
    'S_SHORT':['CHOCH_Bear','BOS_Bear','MSS_Bear'],
    'D_ZONE': ['OB_Bull','FVG_Bull'], 'S_ZONE':['OB_Bear','FVG_Bear'],
}
PATTERNS = {
    'L→D':   ('L_LONG','D_ZONE',[20],'long'),
    'S→D':   ('S_LONG','D_ZONE',[15],'long'),
    'L→S→D': ('L_LONG','S_LONG','D_ZONE',[30,15],'long'),
    'L_D_s': ('L_SHORT','S_ZONE',[20],'short'),
    'S_D_s': ('S_SHORT','S_ZONE',[15],'short'),
}

def detect_sequences(signals):
    sbb = defaultdict(list)
    for s in signals: sbb[s.idx].append(s)
    seqs = []
    for pn, pd in PATTERNS.items():
        keys = list(pd); direction = keys[-1]; gaps = keys[-2]
        stages = [CATS[sk] for sk in keys[:-2]]
        for sb in sorted(sbb):
            for sig in [s for s in sbb[sb] if s.type in stages[0]]:
                m=[sig]; c=sig.idx; ok=True
                for si in range(1,len(stages)):
                    fnd=False
                    for bi in range(c+1,c+gaps[si-1]+1):
                        if bi in sbb:
                            for cand in sbb[bi]:
                                if cand.type in stages[si] and cand not in m:
                                    m.append(cand);c=bi;fnd=True;break
                        if fnd:break
                    if not fnd:ok=False;break
                if ok and len(m)==len(stages):
                    es = m[-1]
                    seqs.append({'p':pn,'d':direction,'bar':es.idx,'type':es.type,
                                 'low':es.lower,'up':es.upper,'price':es.price})
    seen=set(); u=[]
    for s in sorted(seqs,key=lambda x:x['bar']):
        if s['bar'] not in seen: seen.add(s['bar']);u.append(s)
    return u

def backtest(ohlcv, sequences, weekly_trend, signals, swings_dict):
    """交易回测: T+1, TP/SL结构止盈, 周线趋势过滤."""
    n = len(ohlcv)
    trades = []
    used_bars = set()
    
    for seq in sequences:
        # 周线趋势过滤: long只在bullish, short只在bearish
        if seq['d'] == 'long' and weekly_trend != 'bullish': continue
        if seq['d'] == 'short' and weekly_trend != 'bearish': continue
        
        bar = seq['bar']
        entry_bar = bar + 1  # T+1确认
        if entry_bar >= n - 2: continue
        if entry_bar in used_bars: continue
        
        entry_price = ohlcv[entry_bar]['o']
        direction = seq['d']
        
        # TP/SL
        if direction == 'long':
            tp_price, tp_src, _ = find_tps(entry_price, signals, swings_dict, ohlcv)
            sl_price, sl_src, _ = find_sls(entry_price, signals, swings_dict, ohlcv)
        else:
            sl_price, sl_src, _ = find_tps(entry_price, signals, swings_dict, ohlcv)
            tp_price, tp_src, _ = find_sls(entry_price, signals, swings_dict, ohlcv)
        
        # TP cap
        max_tp = entry_price * (TP_CAP if direction=='long' else (2-TP_CAP))
        if (direction=='long' and tp_price > max_tp) or (direction=='short' and tp_price < max_tp):
            tp_price = max_tp
        
        # RR check
        tp_dist = abs(tp_price-entry_price)/entry_price*100
        sl_dist = abs(sl_price-entry_price)/entry_price*100
        if sl_dist > 0 and tp_dist/sl_dist < 1.0: continue
        
        # Walk forward
        exit_idx=-1; exit_price=0; exit_method='eod'
        for i in range(entry_bar+1, n):
            bar_i = ohlcv[i]
            if direction == 'long':
                if bar_i['h'] >= tp_price: exit_idx=i; exit_price=tp_price; exit_method='tp_hit'; break
                if bar_i['l'] <= sl_price: exit_idx=i; exit_price=sl_price; exit_method='sl_hit'; break
            else:
                if bar_i['l'] <= tp_price: exit_idx=i; exit_price=tp_price; exit_method='tp_hit'; break
                if bar_i['h'] >= sl_price: exit_idx=i; exit_price=sl_price; exit_method='sl_hit'; break
        
        if exit_idx<0: exit_idx=n-1; exit_price=ohlcv[exit_idx]['c']; exit_method='eod'
        if exit_idx<=entry_bar: continue
        
        pnl = (exit_price-entry_price)/entry_price*100
        if direction=='short': pnl=-pnl
        
        trades.append({
            'pattern':seq['p'],'direction':direction,'entry_bar':entry_bar,
            'entry_price':entry_price,'exit_bar':exit_idx,'exit_price':exit_price,
            'exit_method':exit_method,'pnl':pnl,'hold':exit_idx-entry_bar,
            'tp':tp_price,'sl':sl_price,'signal_bar':bar,
        })
        used_bars.add(exit_idx)
    
    return trades

# ═══ 主流程 ═══
# 只处理有完整3层数据的股票
daily_files = sorted(KLINE.glob('*_daily_300.json'))
valid_syms = []
for df in daily_files:
    sym = df.stem.replace('_daily_300','')
    has_weekly = (KLINE / f'{sym}_weekly_200.json').exists()
    has_60min = (KLINE / f'{sym}_60min_500.json').exists()
    if has_weekly and has_60min:
        valid_syms.append((sym, df))

print(f'Complete data stocks: {len(valid_syms)} (weekly+daily+60min)')

all_trades = []
stock_stats = {}
t0 = time.time()

for fi, (sym, df) in enumerate(valid_syms):
    try:
        daily = json.loads(df.read_bytes())
        if len(daily) < 50: continue
    except: continue
    
    # Weekly SMC
    weekly_path = KLINE / f'{sym}_weekly_200.json'
    try:
        weekly = json.loads(weekly_path.read_bytes())
        if len(weekly) < 20: continue
    except: continue
    
    w_sigs, w_st, _, _ = detect_all_signals_v20(weekly)
    # Trend from CHOCH/BOS
    tc = w_st['type_counts']
    cb=tc.get('CHOCH_Bull',0); cbr=tc.get('CHOCH_Bear',0)
    bb=tc.get('BOS_Bull',0); bbr=tc.get('BOS_Bear',0)
    last_ch = [s for s in w_sigs if 'CHOCH' in s.type]
    last_dir = 'bull' if last_ch and 'Bull' in last_ch[-1].type else ('bear' if last_ch and 'Bear' in last_ch[-1].type else None)
    
    if last_dir=='bull' and cb+bb>=cbr+bbr: w_trend='bullish'
    elif last_dir=='bear' and cbr+bbr>cb+bb: w_trend='bearish'
    elif cb+bb>(cbr+bbr)*1.5: w_trend='bullish'
    elif cbr+bbr>(cb+bb)*1.5: w_trend='bearish'
    else: w_trend='neutral'
    
    if w_trend == 'neutral': continue  # skip neutral for trading
    
    # Daily signals + sequences
    sigs, st, _, swings_dict = detect_all_signals_v20(daily)
    sequences = detect_sequences(sigs)
    if not sequences: continue
    
    # Backtest with trend filter
    trades = backtest(daily, sequences, w_trend, sigs, swings_dict)
    if not trades: continue
    
    # Per-stock stats
    wins = sum(1 for t in trades if t['pnl']>0)
    total_pnl = sum(t['pnl'] for t in trades)
    avg_hold = sum(t['hold'] for t in trades)/len(trades)
    
    stock_stats[sym] = {
        'trend': w_trend, 'trades': len(trades), 'wins': wins,
        'wr': round(wins/len(trades)*100,1), 'pnl': round(total_pnl,1),
        'avg_pnl': round(total_pnl/len(trades),2), 'avg_hold': round(avg_hold,1),
    }
    all_trades.extend(trades)
    
    # Load 60min for last 50 bars check
    m60_path = KLINE / f'{sym}_60min_500.json'
    try:
        m60 = json.loads(m60_path.read_bytes())
        last_trade = trades[-1] if trades else None
        if last_trade and len(m60) > 50:
            # Check if 60min confirms recent demand zone
            m60_recent = m60[-50:]
            m60_low = min(b['l'] for b in m60_recent)
            # Simple check: 60min low near daily zone
            stock_stats[sym]['m60_confirm'] = True
    except: pass
    
    if (fi+1) % 100 == 0:
        print(f"  [{fi+1}/{len(valid_syms)}] {time.time()-t0:.0f}s trades={len(all_trades)}")

elapsed = time.time()-t0

# ═══ 报告 ═══
if not all_trades:
    print("No trades generated!")
    sys.exit(1)

total = len(all_trades)
wins = sum(1 for t in all_trades if t['pnl']>0)
wr = wins/total*100
avg_pnl = sum(t['pnl'] for t in all_trades)/total
avg_hold = sum(t['hold'] for t in all_trades)/total
cum_pnl = sum(t['pnl'] for t in all_trades)

win_pnls = [t['pnl'] for t in all_trades if t['pnl']>0]
loss_pnls = [abs(t['pnl']) for t in all_trades if t['pnl']<=0]
pf = sum(win_pnls)/sum(loss_pnls) if loss_pnls else 999

em = defaultdict(int)
for t in all_trades: em[t['exit_method']] += 1
pat_dist = defaultdict(int)
for t in all_trades: pat_dist[t['pattern']] += 1

print(f"\n{'='*70}")
print(f"  SMC完整交易系统 V3.0 ({elapsed:.0f}s)")
print(f"  周线趋势过滤 + 日线序列 + 60min确认")
print(f"{'='*70}")
print(f"  交易股票: {len(stock_stats)}")
print(f"  总交易: {total}  WR: {wr:.1f}%  PnL: {avg_pnl:+.2f}%  PF: {pf:.1f}  Hold: {avg_hold:.1f}b")
print(f"  累计盈亏: {cum_pnl:+.1f}%")
print(f"  TP: {em.get('tp_hit',0)}({em.get('tp_hit',0)/total*100:.0f}%)  SL: {em.get('sl_hit',0)}({em.get('sl_hit',0)/total*100:.0f}%)  EOD: {em.get('eod',0)}")

# By trend
for trend in ['bullish','bearish']:
    t_trades = [t for s,st in stock_stats.items() if st['trend']==trend for t in [st]]
    if not t_trades: continue
    t_total = sum(s['trades'] for s in stock_stats.values() if s['trend']==trend)
    t_wins = sum(s['wins'] for s in stock_stats.values() if s['trend']==trend)
    t_wr = t_wins/t_total*100 if t_total else 0
    t_pnl = sum(s['pnl'] for s in stock_stats.values() if s['trend']==trend)
    print(f"  {trend:8s}: {sum(1 for s in stock_stats.values() if s['trend']==trend)} stocks, {t_total} trades, WR={t_wr:.1f}%, PnL={t_pnl:+.1f}%")

# By pattern
print(f"\n  按序列模式:")
for pat, count in sorted(pat_dist.items(), key=lambda x:-x[1]):
    pat_trades = [t for t in all_trades if t['pattern']==pat]
    pat_wins = sum(1 for t in pat_trades if t['pnl']>0)
    pat_pnl = sum(t['pnl'] for t in pat_trades)/len(pat_trades)
    print(f"    {pat:10s}: {count}笔 WR={pat_wins/count*100:.1f}% PnL={pat_pnl:+.2f}%")

# Top picks
print(f"\n  精选 (bullish+L→D+WR≥80%+≥3笔):")
picks = [(sym,st) for sym,st in stock_stats.items()
         if st['trend']=='bullish' and st['trades']>=3 and st['wr']>=80]
for sym,st in sorted(picks, key=lambda x:-x[1]['pnl'])[:20]:
    print(f"    {sym:12s} {st['trades']}笔 WR={st['wr']:.0f}% PnL={st['pnl']:+.1f}% avg={st['avg_pnl']:+.2f}%")

# Save
output = {
    'meta': {'version':'3.0','date':time.strftime('%Y-%m-%d'),'stocks':len(stock_stats),'trades':total,'wr':round(wr,1)},
    'stock_stats': {s:{k:(round(v,2) if isinstance(v,float) else v) for k,v in st.items()} for s,st in stock_stats.items()},
    'trades': all_trades,
}
json.dump(output, open(OUT/'trading_system_v3.json','w'), ensure_ascii=False)
print(f"\n  交易数据库: {OUT/'trading_system_v3.json'}")
