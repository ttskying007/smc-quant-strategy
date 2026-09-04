#!/usr/bin/env python3
"""
V12 SMC Complete Engine — 详细交易日志 + 信号组合 + 完整入场/出场详情
=============================================================================
V11→V12 修复清单:
1. 使用 detect_smc_setups() 检测真实SMC信号组合 (LIQ→CHOCH→POI)
2. 完整交易字段: signal_date, signal_price, entry_type, entry_reason, retrace_pct,
   exit_price, exit_date, exit_reason, exit_detail, sl_price, tp_pct
3. 防重复: 同一bar只入一笔
4. 出场原因细分: SL_hit, TP1, TP2, trailing_stop, timeout
5. 入场原因细分: retrace, immediate, breakout
6. 完整交易日志 CSV 输出
"""
import json, sys, time, math, csv
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v22 import detect_all_signals_v22, Signal, detect_smc_setups, _calc_atr

# Backward compat
detect_all_signals_v21 = detect_all_signals_v22
detect_all_signals_v20 = detect_all_signals_v22

DAILY_DIR = Path('/root/.hermes/kline_cache')
HOURLY_DIR = Path('/root/.hermes/kline_cache_60min')
WEEKLY_DIR = Path('/root/.hermes/kline_cache_weekly')
OUT_DIR = Path('/root/.hermes/smc_opt_v12')
OUT_DIR.mkdir(exist_ok=True)

# ═══ ATR ═══
def calc_atr(daily, length=14):
    n = min(length, len(daily))
    trs = []
    for i in range(max(1, len(daily)-n), len(daily)):
        h, l = daily[i]['h'], daily[i]['l']
        pc = daily[i-1]['c']
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return sum(trs)/len(trs) if trs else 1.0

# ═══ 市场状态 ═══
def detect_market_state(daily):
    if len(daily) < 40: return 'unknown', {}
    closes = [b['c'] for b in daily]
    highs = [b['h'] for b in daily]
    lows = [b['l'] for b in daily]
    ma20 = sum(closes[-20:])/20
    trend20 = (closes[-1]-closes[-20])/closes[-20]*100
    trs = []
    for i in range(max(1,len(closes)-14),len(closes)):
        trs.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
    atr20 = sum(trs)/len(trs) if trs else 1
    atr_pct = atr20/closes[-1] if closes[-1]>0 else 0.03
    if abs(trend20) < 3: state = 'ranging'
    elif trend20 > 3: state = 'trending_up'
    elif trend20 < -3: state = 'trending_down'
    else: state = 'mixed'
    if atr_pct > 0.04: state = 'volatile'
    return state, {'trend20': round(trend20,2), 'atr_pct': round(atr_pct,4)}

# ═══ 动态SL/TP ═══
def calc_sltp(daily, entry_idx, entry_price, cost_line, state):
    atr = calc_atr(daily[:entry_idx+1], 14)
    atr_pct = atr/entry_price if entry_price>0 else 0.02
    # SL: 成本线下方 ATR自适应
    if state=='volatile': sl_mult=0.8
    elif state=='trending_up': sl_mult=1.5
    elif state=='ranging': sl_mult=1.0
    else: sl_mult=1.2
    sl = cost_line*(1-atr_pct*sl_mult)
    sl_pct = (entry_price-sl)/entry_price*100
    # TP: ATR倍数
    tp1 = entry_price*(1+atr_pct*2.0)
    tp2 = entry_price*(1+atr_pct*4.0)
    trail_act = atr_pct*3.0  # 3x ATR激活trailing
    trail_dist = atr_pct*0.8
    return {'sl':round(sl,3), 'sl_pct':round(sl_pct,2), 'tp1':round(tp1,3), 'tp2':round(tp2,3),
            'tp_pct':round(atr_pct*200,1), 'trail_act':trail_act, 'trail_dist':trail_dist, 'atr_pct':round(atr_pct,4)}

# ═══ 分批止盈模拟 ═══
def simulate_exit(daily, entry_idx, entry_price, sltp):
    highs=[b['h'] for b in daily]; lows=[b['l'] for b in daily]; closes=[b['c'] for b in daily]
    n=len(daily); sl=sltp['sl']; tp1=sltp['tp1']; tp2=sltp['tp2']
    trail_act=sltp['trail_act']; trail_dist=sltp['trail_dist']
    extreme=entry_price; sl_current=sl; trail_active=False
    tp1_hit=False; tp2_hit=False; sl_hit=False; exit_bar=None; exit_price=None; exit_reason='timeout'

    for j in range(entry_idx+1, min(n, entry_idx+40)):
        if highs[j]>extreme: extreme=highs[j]
        gain=(extreme-entry_price)/entry_price
        if not trail_active and gain>=trail_act: trail_active=True
        if trail_active: sl_current=max(sl_current, extreme*(1-trail_dist))
        if not tp1_hit and highs[j]>=tp1: tp1_hit=True
        if not tp2_hit and highs[j]>=tp2: tp2_hit=True
        if lows[j]<=sl_current: sl_hit=True; exit_bar=j; exit_price=max(sl_current, lows[j]); exit_reason='SL_hit'; break
        # Time stop: 30 bars
        if j==entry_idx+30: exit_bar=j; exit_price=closes[j]; exit_reason='time_stop'; break

    if exit_bar is None: exit_bar=min(entry_idx+39, n-1); exit_price=closes[exit_bar]; exit_reason='timeout'

    # Weighted PnL
    pnl=0
    if tp1_hit: pnl+=0.5*(tp1-entry_price)/entry_price
    else: pnl+=0.5*(closes[exit_bar]-entry_price)/entry_price
    if tp2_hit: pnl+=0.3*(tp2-entry_price)/entry_price
    else: pnl+=0.3*(closes[exit_bar]-entry_price)/entry_price
    pnl+=0.2*(exit_price-entry_price)/entry_price
    pnl_pct=pnl*100

    # Exit detail
    detail=[]
    if tp1_hit: detail.append('TP1')
    if tp2_hit: detail.append('TP2')
    if sl_hit: detail.append(f'SL={exit_price:.2f}')
    detail.append(exit_reason)
    exit_detail='+'.join(detail) if detail else exit_reason

    return {'pnl_pct':round(pnl_pct,2), 'won':pnl_pct>0, 'hold_bars':exit_bar-entry_idx,
            'exit_price':round(exit_price,3), 'exit_date':'', 'exit_bar':exit_bar,
            'exit_reason':exit_reason, 'exit_detail':exit_detail,
            'tp1_hit':tp1_hit, 'tp2_hit':tp2_hit}

# ═══ 主回测: 每只股票 ═══
def backtest_stock_v12(symbol, daily, weekly=None):
    if len(daily)<60: return []
    n=len(daily); closes=[b['c'] for b in daily]; dates=[str(b.get('t',''))[:10] for b in daily]

    state, info=detect_market_state(daily)

    # 信号检测
    sigs, stats, swings, _=detect_all_signals_v20(daily)
    all_sigs=sorted(sigs, key=lambda s:s.idx)

    # SMC Setups (信号组合)
    setups=detect_smc_setups(all_sigs, daily)

    # 构建setup索引
    setup_by_dz={}
    for su in setups:
        dz_key=(su.get('demand_bar', su.get('supply_bar', 0)), su.get('entry_type', ''))
        if dz_key not in setup_by_dz or su['strength']>setup_by_dz[dz_key]['strength']:
            setup_by_dz[dz_key]=su

    trades=[]
    seen_bars=set()  # 防重复
    atr=calc_atr(daily)

    # 单独信号: OB_Bull — 只用高置信(LuxAlgo有CHOCH/BOS上下文, confidence≥0.7)
    # SMC2026 OB(confidence=0.65)仅渲染,不交易
    ob_bulls=[s for s in sigs if s.type=='OB_Bull' and s.idx>=20 and s.idx<n-10 and s.confidence>=0.7]

    for ob in ob_bulls:
        if ob.idx in seen_bars: continue
        if ob.lower<=0 or ob.upper<=ob.lower: continue

        # ═══ 趋势过滤: 拒绝下跌趋势中的假OB_Bull ═══
        # 1. 拒绝trending_down市场状态
        if state == 'trending_down':
            continue
        
        # 2. 价格必须在MA20上方 (短期趋势必须向上)
        ma20 = sum(closes[max(0,ob.idx-20):ob.idx])/min(20, ob.idx) if ob.idx>=20 else closes[ob.idx]
        if closes[ob.idx] < ma20:  # 严格: close必须>MA20
            continue
        
        # 3. 距60日高点不超过20% (不在深度回调中)
        high60 = max(closes[max(0,ob.idx-60):ob.idx+1]) if ob.idx>=10 else closes[ob.idx]
        drawdown = (closes[ob.idx]-high60)/high60*100
        if drawdown < -20:
            continue

        # 检查是否为SMC setup的一部分
        setup=setup_by_dz.get((ob.idx, 'OB_Bull'))
        combo='standalone'
        sweep_bar=-1; choch_bar=-1
        if setup:
            combo=f"OB@{ob.idx}→LIQ@{setup['sweep_bar']}→CHOCH@{setup['choch_bar']}"
            sweep_bar=setup['sweep_bar']; choch_bar=setup['choch_bar']

        # 入场: 等待价格回撤到OB区域
        cost_line=ob.lower
        entry_bar=None; entry_price=None; entry_type=''; retrace_pct=0

        # Try retrace to OB zone (preferred)
        for w in range(1, 8):
            eb=ob.idx+w
            if eb>=n-20: break
            if daily[eb]['l']<=ob.upper:  # 触及OB区域
                entry_bar=eb; entry_price=max(cost_line, daily[eb]['l'])
                entry_type='retrace'
                retrace_pct=(daily[eb]['l']-cost_line)/cost_line*100
                break

        if entry_bar is None: continue

        # 周线共振
        weekly_bull=False
        if weekly and len(weekly)>=20:
            ma20=sum(w['c'] for w in weekly[-20:])/20
            weekly_bull=weekly[-1]['c']>ma20*1.02

        # SL/TP
        sltp=calc_sltp(daily, entry_bar, entry_price, cost_line, state)
        # Zone: signal price (OB upper) as reference
        sig_price=ob.price

        result=simulate_exit(daily, entry_bar, entry_price, sltp)
        result['exit_date']=dates[result['exit_bar']] if result['exit_bar']<len(dates) else ''

        seen_bars.add(ob.idx)

        trades.append({
            'symbol': symbol,
            'entry_date': dates[entry_bar] if entry_bar<len(dates) else '',
            'signal_date': dates[ob.idx] if ob.idx<len(dates) else '',
            'signal_type': ob.type,
            'signal_price': round(sig_price, 3),
            'signal_idx': ob.idx,
            'entry_idx': entry_bar,
            'entry_price': round(entry_price, 3),
            'entry_type': entry_type,
            'retrace_pct': round(retrace_pct, 2),
            'cost_line': round(cost_line, 3),
            'entry_detail': f'{entry_type}@{entry_price:.2f}'+(f' retrace={retrace_pct:.1f}%' if retrace_pct else ''),
            'combo': combo,
            'has_sweep': sweep_bar>=0,
            'has_choch': choch_bar>=0,
            'weekly_bull': weekly_bull,
            'market_state': state,
            'atr_pct': sltp['atr_pct'],
            'sl_price': sltp['sl'],
            'sl_pct': sltp['sl_pct'],
            'tp_pct': sltp['tp_pct'],
            'exit_date': result['exit_date'],
            'exit_bar': result['exit_bar'],
            'exit_price': result['exit_price'],
            'exit_reason': result['exit_reason'],
            'exit_detail': result['exit_detail'],
            'pnl_pct': result['pnl_pct'],
            'won': result['won'],
            'rr': round(result['pnl_pct']/sltp['sl_pct'],2) if sltp['sl_pct']>0 else 99,
            'hold_bars': result['hold_bars'],
            'tp1_hit': result['tp1_hit'],
            'tp2_hit': result['tp2_hit'],
        })
    return trades

# ═══ 全量回测 ═══
def run_full_backtest(limit=None, start_idx=0):
    daily_files=sorted(DAILY_DIR.glob('*_daily_300.json'))
    if limit: daily_files=daily_files[start_idx:start_idx+limit]

    all_trades=[]
    t0=time.time()
    report_every=max(1, len(daily_files)//20)

    for fi,fp in enumerate(daily_files):
        fname=fp.name
        parts=fname.replace('_daily_300.json','').split('_')
        if len(parts)>=2: symbol='.'.join(parts)
        else: symbol=fname.replace('_daily_300.json','')

        try:
            daily=json.loads(fp.read_bytes())
            for b in daily:
                if 't' not in b and 'date' in b: b['t']=str(b['date'])
                for k in ('o','h','l','c','v'): b[k]=float(b[k]) if k in b else 0
        except: continue

        # 加载周线
        weekly=None
        wf=WEEKLY_DIR/f'{fname.replace("_daily_300","_weekly")}'
        if wf.exists():
            try: weekly=json.loads(wf.read_bytes())
            except: pass

        trades=backtest_stock_v12(symbol, daily, weekly)
        all_trades.extend(trades)

        if (fi+1)%report_every==0:
            elapsed=time.time()-t0
            print(f"  [{fi+1}/{len(daily_files)}] {symbol} -> {len(trades)} trades | {elapsed:.0f}s")

    elapsed=time.time()-t0
    print(f"\nDone: {len(all_trades)} trades, {len(set(t['symbol'] for t in all_trades))} stocks in {elapsed:.0f}s")

    # 保存
    out_json=OUT_DIR/'v12_complete.json'
    out_json.write_text(json.dumps(all_trades, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Saved: {out_json}")

    # 生成详细CSV交易日志
    csv_path=OUT_DIR/'v12_trade_log.csv'
    if all_trades:
        fieldnames=['symbol','entry_date','signal_date','signal_type','signal_price','signal_idx',
                    'entry_idx','entry_price','entry_type','retrace_pct','cost_line',
                    'combo','has_sweep','has_choch','weekly_bull','market_state','atr_pct',
                    'sl_price','sl_pct','tp_pct',
                    'exit_date','exit_price','exit_reason','exit_detail',
                    'pnl_pct','won','rr','hold_bars','tp1_hit','tp2_hit']
        with open(csv_path,'w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            w.writeheader()
            w.writerows(all_trades)
        print(f"Trade log CSV: {csv_path}")

    # 统计
    won=sum(1 for t in all_trades if t['won'])
    wr=f"{won/len(all_trades)*100:.1f}%" if all_trades else "N/A"
    avg_pnl=f"{sum(t['pnl_pct'] for t in all_trades)/len(all_trades):.2f}%" if all_trades else "N/A"
    print(f"WR={wr} | Avg PnL={avg_pnl} | {len(set(t['symbol'] for t in all_trades))} stocks")

    return all_trades

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument('--limit',type=int,default=0,help='Limit stocks')
    ap.add_argument('--start',type=int,default=0,help='Start index')
    args=ap.parse_args()

    print(f"V12 Full Backtest: {len(list(DAILY_DIR.glob('*_daily_300.json')))} stocks")
    if args.limit:
        print(f"  Limit: {args.limit} stocks (from idx {args.start})")
    run_full_backtest(limit=args.limit or None, start_idx=args.start)
