#!/usr/bin/env python3
"""
SMC 全维度回测 V4 — 所有股票 × 多周期 × 多时间窗口
======================================================
维度:
  1. 周期: 日线(全部) → +周线过滤 → +60min确认
  2. 时间窗口: full(全部) / mid(最近150bar) / recent(最近50bar)
  3. 趋势: bullish / bearish / neutral
  4. 序列: L→D / S→D / L→S→D / L_D_s / S_D_s
  5. T+1: 次日开盘入场

输出: 完整统计表 + JSON数据库
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20
from v11.v19_backtest_engine import find_tps, find_sls
from v11.weekly_trend import synthesize_weekly, weekly_trend as wt_func

KLINE = Path('/root/.hermes/kline_cache')
KLINE_60 = Path('/root/.hermes/kline_cache_60min')
OUT = Path('/root/.hermes/smc_opt_v21')
OUT.mkdir(exist_ok=True)

# ═══ 配置 ═══
LOOKAHEAD = 5; TARGET = 2.0; TP_CAP = 1.05
MIN_DAILY = 50; MIN_WEEKLY = 20
FORCE_REAL_WEEKLY = False  # True = 仅用Hubble真实周线; False = daily合成周线也可
USE_60MIN_FILTER = False    # 60min确认（太慢，默认关闭）
SKIP_NEUTRAL = True         # 跳过neutral趋势的股票

# ═══ 信号分类 ═══
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

def weekly_smc_trend(weekly):
    """周线SMC趋势: CHOCH/BOS方向"""
    if len(weekly) < 20: return 'neutral', {}
    sigs, st, _, _ = detect_all_signals_v20(weekly)
    tc = st['type_counts']
    cb=tc.get('CHOCH_Bull',0); cbr=tc.get('CHOCH_Bear',0)
    bb=tc.get('BOS_Bull',0); bbr=tc.get('BOS_Bear',0)
    last_ch = [s for s in sigs if 'CHOCH' in s.type]
    last_dir = 'bull' if last_ch and 'Bull' in last_ch[-1].type else ('bear' if last_ch and 'Bear' in last_ch[-1].type else None)
    if last_dir=='bull' and cb+bb>=cbr+bbr: return 'bullish', tc
    if last_dir=='bear' and cbr+bbr>cb+bb: return 'bearish', tc
    if cb+bb>(cbr+bbr)*1.5: return 'bullish', tc
    if cbr+bbr>(cb+bb)*1.5: return 'bearish', tc
    return 'neutral', tc

def simple_weekly_trend(weekly):
    """简易周线趋势: MA20方向"""
    if len(weekly) < 8: return 'neutral'
    recent = weekly[-8:]
    ma20 = sum(b['c'] for b in weekly[-20:]) / min(20, len(weekly))
    if recent[-1]['c'] > ma20 * 1.02: return 'bullish'
    if recent[-1]['c'] < ma20 * 0.98: return 'bearish'
    return 'neutral'

def backtest_trades(ohlcv, sequences, weekly_trend, signals, swings_dict, start_bar=0):
    """T+1交易回测，从start_bar开始"""
    n = len(ohlcv)
    trades = []
    used_bars = set()
    
    for seq in sequences:
        if seq['bar'] < start_bar: continue
        
        # 周线趋势过滤
        if seq['d'] == 'long' and weekly_trend != 'bullish': continue
        if seq['d'] == 'short' and weekly_trend != 'bearish': continue
        
        bar = seq['bar']
        entry_bar = bar + 1  # T+1
        if entry_bar >= n - 2: continue
        if entry_bar in used_bars: continue
        
        entry_price = ohlcv[entry_bar]['o']
        direction = seq['d']
        
        # TP/SL from structure
        if direction == 'long':
            tp_price, tp_src, _ = find_tps(entry_price, signals, swings_dict, ohlcv)
            sl_price, sl_src, _ = find_sls(entry_price, signals, swings_dict, ohlcv)
        else:
            sl_price, sl_src, _ = find_tps(entry_price, signals, swings_dict, ohlcv)
            tp_price, tp_src, _ = find_sls(entry_price, signals, swings_dict, ohlcv)
        
        # TP cap
        if entry_price == 0: continue
        max_tp = entry_price * (TP_CAP if direction=='long' else (2-TP_CAP))
        if (direction=='long' and tp_price > max_tp) or (direction=='short' and tp_price < max_tp):
            tp_price = max_tp
        
        # RR check
        tp_dist = abs(tp_price-entry_price)/entry_price*100
        sl_dist = abs(sl_price-entry_price)/entry_price*100
        if sl_dist == 0: continue
        if tp_dist/sl_dist < 1.0: continue
        
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
            'tp':tp_price,'sl':sl_price,
        })
        used_bars.add(exit_idx)
    
    return trades

def summary(trades, label=''):
    if not trades: return {'label':label,'n':0,'wr':0,'pnl':0,'pf':0}
    n=len(trades); wins=sum(1 for t in trades if t['pnl']>0)
    cum=sum(t['pnl'] for t in trades); avg_pnl=cum/n
    win_pnls=[t['pnl'] for t in trades if t['pnl']>0]
    loss_pnls=[abs(t['pnl']) for t in trades if t['pnl']<=0]
    tp_hits=sum(1 for t in trades if t['exit_method']=='tp_hit')
    sl_hits=sum(1 for t in trades if t['exit_method']=='sl_hit')
    avg_hold=sum(t['hold'] for t in trades)/n
    pf=sum(win_pnls)/sum(loss_pnls) if loss_pnls else 999
    return {'label':label,'n':n,'wr':round(wins/n*100,1),'cum_pnl':round(cum,1),
            'avg_pnl':round(avg_pnl,2),'pf':round(pf,1),'tp_pct':round(tp_hits/n*100,1),
            'sl_pct':round(sl_hits/n*100,1),'avg_hold':round(avg_hold,1)}

def run_window(ohlcv, weekly, sequences, signals, swings_dict, w_trend, start_bar, label):
    """在指定窗口运行回测"""
    active_seqs = [s for s in sequences if s['bar'] >= max(start_bar, 0)]
    trades = backtest_trades(ohlcv, active_seqs, w_trend, signals, swings_dict, start_bar)
    return summary(trades, label)

# ═══ MAIN ═══
t0 = time.time()
daily_files = sorted(KLINE.glob('*_daily_300.json'))
print(f"Total daily files: {len(daily_files)}")

all_results = []  # per-stock results
total_trades = []

trend_dist = defaultdict(int)
window_stats = defaultdict(lambda: defaultdict(list))  # window -> trend -> [stock_pnls]
pattern_stats = defaultdict(lambda: {'trades':0,'wins':0,'pnls':[],'holds':[]})

for fi, df in enumerate(daily_files):
    sym = df.stem.replace('_daily_300','')
    try:
        daily = json.loads(df.read_bytes())
        if len(daily) < MIN_DAILY: continue
    except: continue
    
    # === Weekly ===
    weekly = None
    w_trend = 'neutral'
    weekly_path = KLINE / f'{sym}_weekly_200.json'
    if FORCE_REAL_WEEKLY and weekly_path.exists():
        try:
            weekly = json.loads(weekly_path.read_bytes())
        except: pass
    if weekly is None or len(weekly) < MIN_WEEKLY:
        # Synthesize from daily
        weekly = synthesize_weekly(daily)
    
    if len(weekly) < 8: continue
    
    # Weekly trend: try SMC first, fallback to MA
    w_trend, _ = weekly_smc_trend(weekly)
    if w_trend == 'neutral':
        w_trend = simple_weekly_trend(weekly)
    
    if SKIP_NEUTRAL and w_trend == 'neutral': continue
    
    # === Daily signals ===
    sigs, st, _, swings_dict = detect_all_signals_v20(daily)
    sequences = detect_sequences(sigs)
    if not sequences: continue
    
    # === Multi-window backtest ===
    n = len(daily)
    windows = {
        'full':   0,
        'mid':    max(0, n-150),
        'recent': max(0, n-50),
    }
    
    stock_result = {'sym':sym,'trend':w_trend,'n_bars':n,'n_seqs':len(sequences)}
    
    for wn, start_bar in windows.items():
        trades = backtest_trades(daily, sequences, w_trend, sigs, swings_dict, start_bar)
        if not trades: continue
        
        s = summary(trades, f'{sym}_{wn}')
        stock_result[wn] = s
        
        if wn == 'full':
            total_trades.extend(trades)
            for t in trades:
                pattern_stats[t['pattern']]['trades'] += 1
                if t['pnl'] > 0: pattern_stats[t['pattern']]['wins'] += 1
                pattern_stats[t['pattern']]['pnls'].append(t['pnl'])
                pattern_stats[t['pattern']]['holds'].append(t['hold'])
        
        window_stats[wn][w_trend].append(s['cum_pnl'])
    
    if 'full' in stock_result:
        all_results.append(stock_result)
        trend_dist[w_trend] += 1
    
    if (fi+1) % 500 == 0:
        elapsed = time.time()-t0
        print(f"  [{fi+1}/{len(daily_files)}] {elapsed:.0f}s stocks={len(all_results)} trades={len(total_trades)}")

elapsed = time.time()-t0

# ═══ 全局报告 ═══
print(f"\n{'='*80}")
print(f"  SMC 全维度回测 V4 — {elapsed:.0f}s — {len(all_results)}只有效股票")
print(f"{'='*80}")

# Baseline: all daily-only trades (no weekly filter)
no_filter_trades = []
for res in all_results:
    sym=res['sym']
    try:
        daily = json.loads((KLINE / f'{sym}_daily_300.json').read_bytes())
        sigs, st, _, swings_dict = detect_all_signals_v20(daily)
        sequences = detect_sequences(sigs)
        trades = backtest_trades(daily, sequences, 'bullish', sigs, swings_dict, 0)
        # Also bearish for shorts
        trades2 = backtest_trades(daily, sequences, 'bearish', sigs, swings_dict, 0)
        no_filter_trades.extend(trades)
        no_filter_trades.extend(trades2)
    except: pass

bs = summary(no_filter_trades, 'Baseline(无过滤)')
print(f"\n  Baseline(无过滤全量): {bs['n']}笔 WR={bs['wr']}% PnL={bs['avg_pnl']:+.2f}% cum={bs['cum_pnl']:+.1f}% PF={bs['pf']}")

# With weekly filter
fs = summary(total_trades, 'V4(周线过滤)')
print(f"  V4(周线过滤):         {fs['n']}笔 WR={fs['wr']}% PnL={fs['avg_pnl']:+.2f}% cum={fs['cum_pnl']:+.1f}% PF={fs['pf']}")
print(f"  交易量减少:           {(1-fs['n']/bs['n'])*100:.0f}%")
print(f"  TP={fs['tp_pct']}%  SL={fs['sl_pct']}%  Hold={fs['avg_hold']}b")

# ═══ 趋势分布 ═══
print(f"\n  趋势分布: bullish={trend_dist.get('bullish',0)} bearish={trend_dist.get('bearish',0)} neutral={trend_dist.get('neutral',0)}")

# ═══ 按窗口 × 趋势 ═══
print(f"\n{'='*80}")
print(f"  多窗口 × 趋势 详细统计")
print(f"{'='*80}")
print(f"  {'窗口':<8s} {'趋势':<10s} {'股票':>5s} {'笔数':>6s} {'WR':>6s} {'PnL':>7s} {'PF':>6s} {'TP%':>5s} {'SL%':>5s}")
print(f"  {'-'*70}")

for wn in ['full','mid','recent']:
    for trend in ['bullish','bearish','neutral']:
        pnls = window_stats[wn].get(trend, [])
        if not pnls: continue
        # Get actual trades for this window+trend
        w_trades = []
        for res in all_results:
            if res['trend'] != trend: continue
            wd = res.get(wn)
            if wd and wd['n'] > 0:
                try:
                    daily = json.loads((KLINE / f"{res['sym']}_daily_300.json").read_bytes())
                    sigs, st, _, swings_dict = detect_all_signals_v20(daily)
                    sequences = detect_sequences(sigs)
                    start = 0 if wn=='full' else (len(daily)-150 if wn=='mid' else len(daily)-50)
                    trades = backtest_trades(daily, sequences, trend, sigs, swings_dict, max(0,start))
                    w_trades.extend(trades)
                except: pass
        s = summary(w_trades)
        print(f"  {wn:<8s} {trend:<10s} {len(pnls):>5d} {s['n']:>6d} {s['wr']:>5.1f}% {s['avg_pnl']:>+6.2f}% {s['pf']:>5.1f} {s['tp_pct']:>4.1f}% {s['sl_pct']:>4.1f}%")

# ═══ 按序列模式 ═══
print(f"\n{'='*80}")
print(f"  序列模式统计 (全窗口汇总)")
print(f"{'='*80}")
for pat in ['L→D','S→D','L→S→D','L_D_s','S_D_s']:
    ps = pattern_stats[pat]
    if ps['trades'] == 0: continue
    wr = ps['wins']/ps['trades']*100
    avg_pnl = sum(ps['pnls'])/len(ps['pnls'])
    cum_pnl = sum(ps['pnls'])
    avg_hold = sum(ps['holds'])/len(ps['holds'])
    tp_count = sum(1 for p in ps['pnls'] if p > 0)
    sl_count = sum(1 for p in ps['pnls'] if p < 0)
    print(f"  {pat:10s}: {ps['trades']:>5d}笔 WR={wr:.1f}% PnL={avg_pnl:+.2f}% cum={cum_pnl:+.1f}% hold={avg_hold:.1f}b")

# ═══ Top Picks ═══
print(f"\n{'='*80}")
print(f"  精选: bullish+full WR≥80%+≥5笔")
print(f"{'='*80}")
picks = [(r['sym'],r) for r in all_results 
         if r['trend']=='bullish' and 'full' in r and r['full']['n']>=5 and r['full']['wr']>=80]
for sym,r in sorted(picks, key=lambda x:-x[1]['full']['cum_pnl'])[:20]:
    fd = r['full']
    print(f"  {sym:12s} {fd['n']}笔 WR={fd['wr']}% PnL={fd['avg_pnl']:+.2f}% cum={fd['cum_pnl']:+.1f}% PF={fd['pf']}")

# ═══ 保存 ═══
output = {
    'meta': {'version':'4.0','date':time.strftime('%Y-%m-%d %H:%M'),'stocks':len(all_results),'elapsed':round(elapsed),
             'baseline':bs,'filtered':fs},
    'trend_dist': dict(trend_dist),
    'window_trend_stats': {wn:{trend:len(pnls) for trend,pnls in wt.items()} for wn,wt in window_stats.items()},
    'pattern_stats': {pat:{'n':ps['trades'],'wr':round(ps['wins']/ps['trades']*100,1),
                          'cum_pnl':round(sum(ps['pnls']),1),'avg_hold':round(sum(ps['holds'])/len(ps['holds']),1)}
                      for pat,ps in pattern_stats.items() if ps['trades']>0},
    'stock_results': {r['sym']:{k:v for k,v in r.items() if k!='sym'} for r in all_results},
}
json.dump(output, open(OUT/'full_backtest_v4.json','w'), ensure_ascii=False)
print(f"\n  保存: {OUT/'full_backtest_v4.json'} ({len(all_results)} stocks)")
print(f"  耗时: {elapsed:.0f}s")
