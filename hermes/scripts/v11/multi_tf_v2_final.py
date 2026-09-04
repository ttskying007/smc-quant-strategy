#!/usr/bin/env python3
"""
SMC 多周期选股+监控系统 V2.0
==============================
三层架构: 周线SMC趋势 → 日线SMC序列组合 → 60min入场定位
输出: JSON数据库 + 可查询选股接口
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20, _calc_atr

KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v21')
OUT.mkdir(exist_ok=True)

TARGET = 2.0; LOOKAHEAD = 5; MIN_SAMPLES = 3

# ═══ 信号分类和序列模式 ═══
CATS = {
    'L_LONG':  ['Sweep_SSL', 'EQL'],      'L_SHORT': ['Sweep_BSL', 'EQH'],
    'S_LONG':  ['CHOCH_Bull','BOS_Bull','MSS_Bull'],
    'S_SHORT': ['CHOCH_Bear','BOS_Bear','MSS_Bear'],
    'D_ZONE':  ['OB_Bull','FVG_Bull'],    'S_ZONE':  ['OB_Bear','FVG_Bear'],
}

PATTERNS = {
    'L→D':   ('L_LONG','D_ZONE',[20],'long'),
    'S→D':   ('S_LONG','D_ZONE',[15],'long'),
    'L→S→D': ('L_LONG','S_LONG','D_ZONE',[30,15],'long'),
    'L_D_s': ('L_SHORT','S_ZONE',[20],'short'),
    'S_D_s': ('S_SHORT','S_ZONE',[15],'short'),
    'L_S_D_s':('L_SHORT','S_SHORT','S_ZONE',[30,15],'short'),
}

def daily_to_weekly(daily):
    w = []
    for i in range(0, len(daily), 5):
        c = daily[i:i+5]
        if len(c) >= 3:
            w.append({'o':c[0]['o'],'h':max(b['h'] for b in c),'l':min(b['l'] for b in c),'c':c[-1]['c']})
    return w

def weekly_smc(weekly):
    if len(weekly) < 30: return 'neutral', {}
    sigs, st, _, _ = detect_all_signals_v20(weekly)
    tc = st['type_counts']
    cb = tc.get('CHOCH_Bull',0); cbr = tc.get('CHOCH_Bear',0)
    bb = tc.get('BOS_Bull',0); bbr = tc.get('BOS_Bear',0)
    last = [s for s in sigs if 'CHOCH' in s.type]
    last_dir = 'bull' if last and 'Bull' in last[-1].type else ('bear' if last and 'Bear' in last[-1].type else None)
    if last_dir == 'bull' and cb+bb >= cbr+bbr: return 'bullish', tc
    if last_dir == 'bear' and cbr+bbr > cb+bb: return 'bearish', tc
    if cb+bb > (cbr+bbr)*1.5: return 'bullish', tc
    if cbr+bbr > (cb+bb)*1.5: return 'bearish', tc
    return 'neutral', tc

def detect_sequences(signals):
    sbb = defaultdict(list)
    for s in signals: sbb[s.idx].append(s)
    seqs = []
    for pn, pat_data in PATTERNS.items():
        # pat_data = (s1, s2, [gaps], dir) or (s1, s2, s3, [gaps], dir)
        keys = list(pat_data)
        direction = keys[-1]
        gaps = keys[-2]
        stage_keys = keys[:-2]  # category keys for each stage
        stages = [CATS[sk] for sk in stage_keys]
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
                    seqs.append({'p':pn,'d':direction,'bar':m[-1].idx})
    seen=set(); u=[]
    for s in sorted(seqs,key=lambda x:x['bar']):
        if s['bar'] not in seen: seen.add(s['bar']);u.append(s)
    return u

def test(ohlcv, seqs, start=0):
    n=len(ohlcv); r=defaultdict(lambda:{'h':0,'t':0,'rr':[]})
    for s in seqs:
        b=s['bar']; 
        if b<start or b+LOOKAHEAD>=n: continue
        ep=ohlcv[b]['c']; mh=max(ohlcv[i]['h'] for i in range(b+1,min(b+LOOKAHEAD+1,n)))
        ret=(mh-ep)/ep*100; r[s['p']]['t']+=1; r[s['p']]['rr'].append(ret)
        if ret>=TARGET: r[s['p']]['h']+=1
    return {k:{'h':v['h'],'t':v['t'],'rate':round(v['h']/v['t'],3),
               'avg':round(sum(v['rr'])/len(v['rr']),2)}
            for k,v in r.items() if v['t']>=MIN_SAMPLES}

# ═══ MAIN ═══
daily_files = sorted(KLINE.glob('*_daily_300.json'))
profiles = {}
t0 = time.time()

for fi, df in enumerate(daily_files):
    sym = df.stem.replace('_daily_300','')
    try:
        daily = json.loads(df.read_bytes())
        if len(daily) < 50: continue
    except: continue
    
    # Weekly: only use real API data, skip if missing
    weekly_path = KLINE / f'{sym}_weekly_200.json'
    if not weekly_path.exists():
        continue  # skip stocks without real weekly data
    
    try:
        weekly = json.loads(weekly_path.read_bytes())
        if len(weekly) < 20: continue
    except:
        continue
    
    w_trend, w_sigs = weekly_smc(weekly)
    
    # 60min
    m60 = None
    m60_path = KLINE / f'{sym}_60min_500.json'
    if m60_path.exists():
        try: m60 = json.loads(m60_path.read_bytes())
        except: pass
    
    # Daily sequences
    sigs, st, _, _ = detect_all_signals_v20(daily)
    seqs = detect_sequences(sigs)
    if not seqs: continue
    
    # Multi-window test
    n = len(daily)
    wins = {'full':0,'mid':max(0,n-150),'recent':max(0,n-50)}
    profile = {'sym':sym,'w_trend':w_trend,'w_sigs':{k:v for k,v in w_sigs.items() if isinstance(v,int)} if isinstance(w_sigs,dict) else {},
               'd_sigs':st['type_counts'],'d_seqs':len(seqs),'windows':{},'has_60min':m60 is not None}
    
    for wn, start in wins.items():
        perf = test(daily, seqs, start)
        if perf: profile['windows'][wn] = perf
    
    if 'full' in profile['windows']:
        full = profile['windows']['full']
        best = max(((p, s) for p, s in full.items() if PATTERNS[p][-1]=='long'),
                   key=lambda x: x[1]['rate'], default=(None,None))
        if best[0]:
            profile['best_pat'] = best[0]
            profile['best_rate'] = best[1]['rate']
            profile['best_n'] = best[1]['t']
        profiles[sym] = profile
    
    if (fi+1) % 500 == 0:
        print(f"  [{fi+1}/{len(daily_files)}] {time.time()-t0:.0f}s p={len(profiles)}")

elapsed = time.time()-t0

# ═══ REPORT ═══
print(f"\n{'='*70}")
print(f"  SMC多周期选股系统V2.0 — {len(profiles)}只有效序列")
print(f"{'='*70}")

# Trend distribution
td = defaultdict(int)
for p in profiles.values(): td[p['w_trend']] += 1
m60_count = sum(1 for p in profiles.values() if p['has_60min'])
print(f"  周线趋势: bullish={td['bullish']} bearish={td['bearish']} neutral={td['neutral']}")
print(f"  60min覆盖: {m60_count}/{len(profiles)}")

# Best pattern × trend
pt = defaultdict(lambda: defaultdict(list))
for p in profiles.values():
    bp = p.get('best_pat')
    if bp: pt[p['w_trend']][bp].append(p.get('best_rate',0))

print(f"\n  周线趋势 × 最佳日线组合:")
for trend in ['bullish','bearish','neutral']:
    pats = pt[trend]
    if not pats: continue
    total = sum(len(v) for v in pats.values())
    for pat, rates in sorted(pats.items(), key=lambda x:-len(x[1])):
        print(f"    {trend:8s} {pat:10s} {len(rates):>4d}只 avg_rate={sum(rates)/len(rates):.0%}")

# Stock picks
print(f"\n  精选: bullish+L→D+rate≥80%+有60min")
picks = [(sym,p) for sym,p in profiles.items()
         if p['w_trend']=='bullish' and p.get('best_pat')=='L→D'
         and p.get('best_rate',0)>=0.8 and p['has_60min']]
for sym,p in sorted(picks,key=lambda x:-x[1].get('best_rate',0))[:20]:
    print(f"    {sym:12s} rate={p.get('best_rate',0):.0%} n={p.get('best_n',0)} seqs={p['d_seqs']}")

# Save
output = {'meta':{'version':'2.0','date':time.strftime('%Y-%m-%d'),'stocks':len(profiles),'has_60min':m60_count},
          'profiles':profiles}
json.dump(output,open(OUT/'multi_tf_db_v2.json','w'),ensure_ascii=False)
print(f"\n  数据库: {OUT/'multi_tf_db_v2.json'}")
