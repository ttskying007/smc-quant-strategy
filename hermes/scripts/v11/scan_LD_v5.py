#!/usr/bin/env python3
"""
SMC V5 — 市场状态驱动 + 策略管理 + 动态仓位
=============================================
RULE 1: Always detect Market State before trading
RULE 2: OB strategy always enabled  
RULE 3: ALL→ZONE combos enabled only in Mean Reversion
   LIQ(Sweep_SSL/EQL) + STRUCT(CHOCH/BOS/MSS) → ZONE(OB优先/FVG)
RULE 4: Position size determined by signal score
RULE 5: Risk dynamically scaled by recent performance
RULE 6: System trades portfolio, not individual signals

市场状态: FVG回补率(最近20FVG) → Expansion / MeanReversion / Transition
SignalScore: HTF方向 + FreshOB + LIQ距离 + 市场匹配
仓位: BaseRisk × StrategyWeight × SignalScore × RiskScaler
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timedelta

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20
from v11.v19_backtest_engine import find_tps, find_sls

KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v21')
OUT.mkdir(exist_ok=True)

# ═══ 信号定义 ═══
LIQ_LONG = ['Sweep_SSL', 'EQL']
STRUCT_LONG = ['CHOCH_Bull','BOS_Bull','MSS_Bull']
ALL_START = LIQ_LONG + STRUCT_LONG  # 全部可作为组合起点
MIN_GAP = 1; MAX_GAP = 10

DNA_FILE = OUT / 'stock_dna_v11.json'
dna = {}
if DNA_FILE.exists():
    with open(DNA_FILE) as f: dna = json.load(f).get('dna', {})

# ═══ V5 仓位参数 ═══
BASE_RISK = 1.0          # 基础风险单位
L1_WEIGHT = 0.60         # OB策略权重
L2_WEIGHT = 0.20         # LIQ→FVG策略权重
RISK_SCALE_GOOD = 1.2    # WR>70%时放大
RISK_SCALE_BAD = 0.5     # WR<50%时缩小
CONSEC_LOSS_CAP = 3      # 连续亏损保护阈值

def weekly_smc_trend(weekly):
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

def daily_to_weekly(daily):
    w = []
    for i in range(0, len(daily), 5):
        c = daily[i:i+5]
        if len(c) >= 3:
            w.append({'o':c[0]['o'],'h':max(b['h'] for b in c),'l':min(b['l'] for b in c),'c':c[-1]['c']})
    return w

# ═══ V5 市场状态检测 ═══
def detect_market_state(daily, signals, sbb):
    """
    FVG回补率 = 最近20个FVG_Bull中被回补的比例
    回补定义: FVG bar之后, 价格跌入FVG区域(low ≤ FVG.upper)至少一次
    """
    n = len(daily)
    fvg_signals = [s for s in signals if s.type == 'FVG_Bull']
    
    if len(fvg_signals) < 5:
        return 'transition', 0.0  # insufficient data
    
    # Take last 20 FVGs
    recent_fvgs = sorted(fvg_signals, key=lambda x: x.idx)[-20:]
    
    filled = 0
    for fvg in recent_fvgs:
        fvg_upper = fvg.upper if hasattr(fvg,'upper') and fvg.upper else fvg.price * 1.01
        # Check if price ever touched FVG zone after the FVG bar
        for i in range(fvg.idx + 1, min(fvg.idx + 30, n)):
            if daily[i]['l'] <= fvg_upper:
                filled += 1
                break
    
    fill_rate = filled / len(recent_fvgs)
    
    if fill_rate > 0.60:
        return 'mean_reversion', fill_rate
    elif fill_rate < 0.40:
        return 'expansion', fill_rate
    else:
        return 'transition', fill_rate

# ═══ V5 SignalScore ═══
def calc_signal_score(sym, signal_type, market_state, daily, signals, sbb, entry_bar, gap=0):
    """SignalScore ∈ [0, 1]"""
    score = 0.0
    
    # HTF同方向 (+0.2)
    sd = dna.get(sym, {})
    trend = sd.get('trend', '?')
    if trend == 'bullish': score += 0.2
    
    # Fresh OB (+0.2) — OB_Bull特有的
    if signal_type == 'OB_Bull':
        score += 0.2
    
    # LIQ后 ≤5bar (+0.2) — LIQ→FVG特有的
    if signal_type == 'LIQ→FVG' and gap <= 5:
        score += 0.2
    
    # 市场状态匹配 (+0.4)
    if signal_type == 'OB_Bull':
        # OB在任何市场都可用, 全分
        score += 0.4
    elif signal_type == 'LIQ→FVG':
        if market_state == 'mean_reversion':
            score += 0.4  # 最佳匹配
        elif market_state == 'transition':
            score += 0.2  # 勉强可用
        # expansion: 0分(策略已关闭,不会到这里)
    
    return min(1.0, score)

# ═══ V5 仓位计算 ═══
def calc_position_size(strategy_weight, signal_score, risk_scaler):
    return BASE_RISK * strategy_weight * signal_score * risk_scaler

# ═══ V5 风险缩放 ═══
def calc_risk_scaler(recent_trades):
    """基于最近20笔交易动态调整风险"""
    if len(recent_trades) < 5:
        return 1.0
    
    recent = recent_trades[-20:]
    wins = sum(1 for t in recent if t['pnl'] > 0)
    wr = wins / len(recent)
    
    # 连续亏损检查
    cons_loss = 0
    for t in reversed(recent):
        if t['pnl'] <= 0: cons_loss += 1
        else: break
    
    if cons_loss >= CONSEC_LOSS_CAP:
        return 0.5  # 连续亏损保护
    
    if wr > 0.70:
        return RISK_SCALE_GOOD
    elif wr < 0.50:
        return RISK_SCALE_BAD
    return 1.0

# ═══ MAIN ═══
t0 = time.time()
daily_files = sorted(KLINE.glob('*_daily_300.json'))
picks = []
market_states = {}
trade_log = []  # simulated trade history for risk scaling

for fi, df in enumerate(daily_files):
    sym = df.stem.replace('_daily_300', '')
    try:
        daily = json.loads(df.read_bytes())
        if len(daily) < 50: continue
    except: continue
    
    # Weekly trend
    weekly_path = KLINE / f'{sym}_weekly_200.json'
    weekly = None
    if weekly_path.exists():
        try: weekly = json.loads(weekly_path.read_bytes())
        except: pass
    if weekly is None or len(weekly) < 20:
        weekly = daily_to_weekly(daily)
    w_trend, _ = weekly_smc_trend(weekly)
    if w_trend != 'bullish': continue
    
    # Daily signals
    sigs, st, _, swings_dict = detect_all_signals_v20(daily)
    sbb = defaultdict(list)
    for s in sigs: sbb[s.idx].append(s)
    
    n = len(daily)
    last_date = datetime.strptime(str(daily[-1].get('t', daily[-1].get('date', '')))[:8], '%Y%m%d')
    cutoff = last_date - timedelta(days=30)
    sd = dna.get(sym, {})
    
    # ── V5 Step 1: Market State ──
    market_state, fill_rate = detect_market_state(daily, sigs, sbb)
    market_states[sym] = {'state': market_state, 'fill_rate': round(fill_rate, 2)}
    
    # ── V5 Step 2: Strategy Management ──
    l1_enabled = True  # OB always on
    l2_enabled = (market_state == 'mean_reversion')  # LIQ→FVG only in MR
    
    # Risk scaler (simulated — would use real trade log in production)
    risk_scaler = 1.0
    
    # ── V5 Step 3: Scan signals ──
    candidates = []
    
    for i in range(max(0, n-50), n-3):
        if i not in sbb: continue
        types_at_bar = [s.type for s in sbb[i]]
        sig_date = str(daily[i].get('t', daily[i].get('date', '')))[:8]
        try:
            if datetime.strptime(sig_date, '%Y%m%d') < cutoff: continue
        except: continue
        
        entry_bar = i + 1
        if entry_bar >= n: continue
        ep = daily[entry_bar]['o']
        if ep == 0: continue
        
        # ── L1: OB_Bull (always on) ──
        if l1_enabled:
            for s in sbb[i]:
                if s.type != 'OB_Bull': continue
                tp, _, _ = find_tps(ep, sigs, swings_dict, daily)
                sl, _, _ = find_sls(ep, sigs, swings_dict, daily)
                if tp is None: tp = ep * 1.05
                if tp > ep * 1.05: tp = ep * 1.05
                if sl is None: sl = ep * 0.97
                
                score = calc_signal_score(sym, 'OB_Bull', market_state, daily, sigs, sbb, entry_bar)
                pos_size = calc_position_size(L1_WEIGHT, score, risk_scaler)
                
                candidates.append({
                    'tier': 'L1', 'signal': 'OB_Bull', 'score': round(score, 2),
                    'pos_size': round(pos_size, 2), 'state': market_state,
                    'ep': ep, 'sl': round(sl, 2), 'tp': round(tp, 2),
                    'entry_bar': entry_bar, 'sig_date': sig_date,
                    'zone_bar': i, 'zone_type': 'OB_Bull',
                    'zone_low': s.lower if hasattr(s,'lower') else 0,
                    'hist_wr': sd.get('v11_wr',0), 'ob_wr': sd.get('ob_wr',0),
                    'hist_trades': sd.get('v11_trades',0), 'trend': w_trend,
                    'fill_rate': round(fill_rate, 2),
                })
        
        # ── L2: ALL→ZONE combos (Market State gated, OB优先) ──
        if l2_enabled:
            start_sigs = [s for s in sbb[i] if s.type in ALL_START]
            for start_s in start_sigs:
                # Scan for ZONE: OB_Bull优先
                best_zone = None; best_gap = 99
                for j in range(i+MIN_GAP, min(i+MAX_GAP+1, n)):
                    if j not in sbb: continue
                    zone_candidates = [s for s in sbb[j] if s.type in ['OB_Bull','FVG_Bull']]
                    if not zone_candidates: continue
                    # OB priority
                    zone_candidates.sort(key=lambda x: 0 if x.type=='OB_Bull' else 1)
                    zone = zone_candidates[0]
                    gap = j - i
                    if gap < best_gap:
                        best_gap = gap; best_zone = (zone, j)
                    break  # first bar with ZONE
                
                if not best_zone: continue
                zone, j = best_zone
                gap = j - i
                entry_bar2 = j + 1
                if entry_bar2 >= n: continue
                ep2 = daily[entry_bar2]['o']
                
                tp2, _, _ = find_tps(ep2, sigs, swings_dict, daily)
                sl2, _, _ = find_sls(ep2, sigs, swings_dict, daily)
                if tp2 is None: tp2 = ep2 * 1.05
                if tp2 > ep2 * 1.05: tp2 = ep2 * 1.05
                if sl2 is None: sl2 = ep2 * 0.97
                
                tpd = abs(tp2-ep2)/ep2*100; sld = abs(sl2-ep2)/ep2*100
                if sld == 0 or tpd/sld < 1.0: continue  # RR filter
                
                score = calc_signal_score(sym, 'COMBO', market_state, daily, sigs, sbb, entry_bar2, gap)
                pos_size = calc_position_size(L2_WEIGHT, score, risk_scaler)
                
                candidates.append({
                    'tier': 'L2', 'signal': f'{start_s.type}→{zone.type}', 'score': round(score, 2),
                    'pos_size': round(pos_size, 2), 'state': market_state,
                    'ep': ep2, 'sl': round(sl2, 2), 'tp': round(tp2, 2),
                    'entry_bar': entry_bar2, 'sig_date': sig_date,
                    'zone_bar': j, 'zone_type': zone.type, 'gap': gap,
                    'liq_type': start_s.type, 'liq_bar': i,
                    'zone_low': zone.lower if hasattr(zone,'lower') else 0,
                    'hist_wr': sd.get('v11_wr',0), 'ob_wr': sd.get('ob_wr',0),
                    'hist_trades': sd.get('v11_trades',0), 'trend': w_trend,
                    'fill_rate': round(fill_rate, 2),
                })
    
    # ── Dedup by entry_bar, prefer higher score ──
    candidates.sort(key=lambda x: (x['entry_bar'], -x['score']))
    seen = set()
    for c in candidates:
        key = (sym, c['entry_bar'])
        if key in seen: continue
        seen.add(key)
        pick = {
            'symbol': sym, 'tier': c['tier'], 'signal': c['signal'],
            'score': c['score'], 'pos_size': c['pos_size'],
            'state': c['state'], 'fill_rate': c['fill_rate'],
            'signal_date': c['sig_date'], 'entry_date': c['sig_date'],
            'entry_price': c['ep'], 'sl': c['sl'], 'tp': c['tp'],
            'zone_bar': c['zone_bar'], 'zone_type': c['zone_type'],
            'zone_low': c.get('zone_low',0), 'gap': c.get('gap',0),
            'hist_wr': c['hist_wr'], 'ob_wr': c['ob_wr'],
            'hist_trades': c['hist_trades'], 'trend': c['trend'],
        }
        # L2 combo extra fields
        if c['tier'] == 'L2':
            pick['liq_type'] = c.get('liq_type', '?')
            pick['liq_bar'] = c.get('liq_bar', 0)
        picks.append(pick)
    
    if (fi+1) % 1000 == 0:
        print(f"  [{fi+1}/{len(daily_files)}] {time.time()-t0:.0f}s picks={len(picks)}")

elapsed = time.time() - t0

# Stats
l1c = sum(1 for p in picks if p['tier']=='L1')
l2c = sum(1 for p in picks if p['tier']=='L2')
state_dist = Counter(p['state'] for p in picks)
score_buckets = Counter(round(p['score'], 1) for p in picks)

print(f"\n{'='*60}")
print(f"  SMC V5 — 市场状态驱动 — {elapsed:.0f}s")
print(f"  🥇 L1 OB_Bull:    {l1c}个")
print(f"  🥈 L2 LIQ→FVG:    {l2c}个 (仅MeanReversion)")
print(f"  总计:             {len(picks)}个")
print(f"\n  市场状态分布: {dict(state_dist)}")
print(f"\n  SignalScore分布: {dict(sorted(score_buckets.items()))}")
print(f"\n  L2按市场状态:")
l2_states = Counter(p['state'] for p in picks if p['tier']=='L2')
print(f"    {dict(l2_states)}")

output = {
    'meta': {'version':'V5 Market-State','date':time.strftime('%Y-%m-%d %H:%M'),
             'l1':l1c,'l2':l2c,'total':len(picks),'elapsed':round(elapsed,1)},
    'market_states': {s: {'state':v['state'],'fill_rate':v['fill_rate']} for s,v in market_states.items()},
    'picks': picks,
}
json.dump(output, open(OUT/'LD_picks_v5.json','w'), ensure_ascii=False)
print(f"\n  保存: {OUT/'LD_picks_v5.json'}")
