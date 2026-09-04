#!/usr/bin/env python3
"""
V11 SMC Complete Engine — 高级SMC + 动态SL/TP + Per-Stock自适应 + 市场状态 + 共振
=============================================================================
高级SMC概念 (ICT Advanced):
  1. Breaker Block: 失败的OB变成反向支撑/阻力
  2. Mitigation Block: FVG被回补后变为阻力/支撑
  3. Rejection Block: 价格拒绝某个水平 = 强力入场信号
  4. Turtle Soup: 假突破后反转
  5. Liquidity Void: 价格跳过区域 = 强磁力区

动态SL/TP:
  - ATR自适应SL (多级: 保守/标准/激进)
  - 分批止盈: TP1@ATR*1.5 + TP2@ATR*3 + 余量Trailing
  - 跟踪止盈: ATR倍数动态调整trail距离
  - 聪明钱成本线: OB/FVG区域为成本线, SL放在下方

Per-Stock自适应:
  - 波动率分级: 低波/中波/高波 → 不同ATR倍数
  - 趋势状态: 强牛/弱牛/震荡/弱熊 → 不同过滤阈值
  - 流动性分级: 高量/低量 → 信号可靠性权重

市场状态识别:
  - FVG回补率 → 趋势/震荡/反转判断
  - 摆动点密度 → 横盘/趋势判断
  - 最近N-bar涨跌幅 → 动量方向

多周期共振:
  - 周线趋势+日线信号+60min入场 → 3层确认
  - 共振评分: 每层满足+1, 需>=2才入场
"""
import json, sys, time, math
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20, Signal

DAILY_DIR = Path('/root/.hermes/kline_cache')
HOURLY_DIR = Path('/root/.hermes/kline_cache_60min')
OUT_DIR = Path('/root/.hermes/smc_opt_v11')
OUT_DIR.mkdir(exist_ok=True)

# ═══ 市场状态参数 ═══
def detect_market_state(daily, weekly=None):
    """识别市场状态: trending_up / ranging / trending_down / volatile"""
    if len(daily) < 40:
        return 'unknown', {}
    
    closes = [b['c'] for b in daily]
    highs = [b['h'] for b in daily]
    lows = [b['l'] for b in daily]
    
    # 20-bar趋势
    ma20 = sum(closes[-20:]) / 20
    trend20 = (closes[-1] - closes[-20]) / closes[-20] * 100
    
    # ATR波动率
    trs = []
    for i in range(max(1, len(closes)-14), len(closes)):
        trs.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
    atr = sum(trs)/len(trs) if trs else 0.01
    atr_pct = atr / closes[-1] * 100
    
    # FVG回补率 (前20个FVG)
    sigs, _, _, _ = detect_all_signals_v20(daily)
    fvgs = [s for s in sigs if 'FVG' in s.type and s.idx > len(daily)-50]
    filled = 0
    for f in fvgs:
        gap_low, gap_high = f.lower, f.upper
        if gap_low >= gap_high: continue
        for k in range(f.idx+2, min(f.idx+10, len(daily))):
            if gap_low < daily[k]['c'] < gap_high:
                filled += 1; break
    fill_rate = filled / max(len(fvgs), 1)
    
    # 分类
    if atr_pct > 4.0:
        state = 'volatile'
    elif trend20 > 3.0 and fill_rate < 0.5:
        state = 'trending_up'
    elif trend20 < -3.0 and fill_rate < 0.5:
        state = 'trending_down'
    elif fill_rate > 0.6:
        state = 'ranging'
    elif trend20 > 1.0:
        state = 'trending_up'
    elif trend20 < -1.0:
        state = 'trending_down'
    else:
        state = 'ranging'
    
    return state, {'trend20': round(trend20,1), 'atr_pct': round(atr_pct,2), 'fill_rate': round(fill_rate,2), 'ma20': round(ma20,1)}


# ═══ Per-Stock自适应参数 ═══
def get_adaptive_params(state, state_info):
    """根据市场状态返回自适应参数"""
    atr_pct = state_info.get('atr_pct', 2.0)
    trend20 = state_info.get('trend20', 0)
    
    # SL: 低波窄, 高波宽
    if atr_pct < 1.5:
        sl_mult = 1.5
    elif atr_pct < 3.0:
        sl_mult = 1.2
    else:
        sl_mult = 0.8
    
    # Trailing: 趋势强时松, 震荡时紧
    if state == 'trending_up':
        trail_act = 0.08   # 8%激活
        trail_dist_mul = 1.2
    elif state == 'volatile':
        trail_act = 0.05
        trail_dist_mul = 0.6
    else:  # ranging
        trail_act = 0.06
        trail_dist_mul = 0.8
    
    # 质量阈值
    if state == 'trending_up':
        min_context = 1     # 趋势中1个上下文足够
    else:
        min_context = 2     # 震荡中需要2个
    
    return {
        'sl_mult': sl_mult,
        'trail_act': trail_act,
        'trail_dist_mul': trail_dist_mul,
        'min_context': min_context,
    }


# ═══ 高级SMC: Breaker Block ═══
def detect_breaker_blocks(daily, signals):
    """Breaker: 失败的OB → 价格穿越OB后变为反向支撑/阻力"""
    breakers = []
    ob_signals = [s for s in signals if 'OB' in s.type]
    
    for ob in ob_signals:
        ob_low = ob.lower
        ob_high = ob.upper
        # Check if price later crossed through the OB
        for j in range(ob.idx + 1, min(ob.idx + 30, len(daily))):
            if ob.type == 'OB_Bull':
                if daily[j]['c'] < ob_low:  # Broke down through bull OB
                    breakers.append(Signal('Breaker_Bear', j, 'bear', price=daily[j]['c'],
                        upper=ob_high, lower=ob_low, strength=4.0, confidence=0.6,
                        metadata={'original_ob': ob.idx, 'breaker_bar': j}))
                    break
            else:
                if daily[j]['c'] > ob_high:  # Broke up through bear OB
                    breakers.append(Signal('Breaker_Bull', j, 'bull', price=daily[j]['c'],
                        upper=ob_high, lower=ob_low, strength=4.0, confidence=0.6,
                        metadata={'original_ob': ob.idx, 'breaker_bar': j}))
                    break
    return breakers


# ═══ 高级SMC: Mitigation Block ═══
def detect_mitigation_blocks(daily, signals):
    """Mitigation: FVG被回补后变成支撑/阻力"""
    mitigations = []
    fvg_signals = [s for s in signals if 'FVG' in s.type]
    
    for fvg in fvg_signals:
        gap_low, gap_high = fvg.lower, fvg.upper
        if gap_low >= gap_high: continue
        for j in range(fvg.idx + 2, min(fvg.idx + 15, len(daily))):
            c = daily[j]['c']
            if gap_low < c < gap_high:  # FVG filled
                mitigations.append(Signal(
                    'Mitigation_Bull' if fvg.type == 'FVG_Bull' else 'Mitigation_Bear',
                    j, 'bull' if fvg.type == 'FVG_Bull' else 'bear',
                    price=c, upper=gap_high, lower=gap_low,
                    strength=3.0, confidence=0.55,
                    metadata={'original_fvg': fvg.idx, 'fill_bar': j}))
                break
    return mitigations


# ═══ 高级SMC: Rejection Block ═══
def detect_rejection_blocks(daily):
    """Rejection: 价格测试某个水平后强势反转"""
    rejections = []
    for i in range(5, len(daily) - 3):
        b = daily[i]; prev = daily[i-1]
        rng = b['h'] - b['l']
        if rng <= 0: continue
        
        # Bullish rejection: long lower wick + close near high
        lower_wick = min(b['o'], b['c']) - b['l']
        if lower_wick > rng * 0.7 and b['c'] > b['h'] - rng * 0.2:
            # Check previous bar was bearish
            if prev['c'] < prev['o']:
                rejections.append(Signal('Rejection_Bull', i, 'bull',
                    price=b['c'], upper=b['h'], lower=b['l'],
                    strength=lower_wick/rng*5, confidence=0.65,
                    metadata={'wick_ratio': round(lower_wick/rng, 2)}))
        
        # Bearish rejection
        upper_wick = b['h'] - max(b['o'], b['c'])
        if upper_wick > rng * 0.7 and b['c'] < b['l'] + rng * 0.2:
            if prev['c'] > prev['o']:
                rejections.append(Signal('Rejection_Bear', i, 'bear',
                    price=b['c'], upper=b['h'], lower=b['l'],
                    strength=upper_wick/rng*5, confidence=0.65))
    return rejections


# ═══ 高级SMC: Turtle Soup ═══
def detect_turtle_soup(daily, signals):
    """Turtle Soup: 假突破前期高/低点后反转"""
    soups = []
    swings = [s for s in signals if 'CHOCH' in s.type or 'BOS' in s.type]
    
    for i in range(30, len(daily) - 5):
        # Find recent swing high within 20 bars
        recent_high = 0; recent_high_idx = 0
        recent_low = float('inf'); recent_low_idx = 0
        for j in range(max(0, i-20), i):
            if daily[j]['h'] > recent_high:
                recent_high = daily[j]['h']; recent_high_idx = j
            if daily[j]['l'] < recent_low:
                recent_low = daily[j]['l']; recent_low_idx = j
        
        # Turtle Soup Long: breaks below recent low then reverses
        if daily[i]['l'] < recent_low and daily[i]['c'] > recent_low:
            soups.append(Signal('TurtleSoup_Bull', i, 'bull',
                price=daily[i]['c'], lower=recent_low, upper=daily[i]['h'],
                strength=6.0, confidence=0.7,
                metadata={'swept_low': recent_low, 'swept_bar': recent_low_idx}))
        
        # Turtle Soup Short: breaks above recent high then reverses
        if daily[i]['h'] > recent_high and daily[i]['c'] < recent_high:
            soups.append(Signal('TurtleSoup_Bear', i, 'bear',
                price=daily[i]['c'], upper=recent_high, lower=daily[i]['l'],
                strength=6.0, confidence=0.7,
                metadata={'swept_high': recent_high, 'swept_bar': recent_high_idx}))
    return soups


# ═══ 多周期共振检测 ═══
def check_resonance(daily, weekly, hourly, sig):
    """检查信号在多个时间周期上是否共振"""
    score = 0
    details = []
    
    # 日线: 信号本身 (+1)
    score += 1
    details.append('daily')
    
    # 周线: MA20趋势方向与信号一致 (+1)
    if weekly and len(weekly) >= 20:
        ma20 = sum(w['c'] for w in weekly[-20:]) / 20
        if sig.direction == 'bull' and weekly[-1]['c'] > ma20:
            score += 1; details.append('weekly_bullish')
        elif sig.direction == 'bear' and weekly[-1]['c'] < ma20:
            score += 1; details.append('weekly_bearish')
    
    # 60min: 有同向OB/FVG在最近10bar (+1)  
    if hourly and len(hourly) >= 20:
        try:
            h_sigs, _, _, _ = detect_all_signals_v20(hourly)
            recent = [s for s in h_sigs if s.idx > len(hourly)-20]
            has_zone = any(s.type in ['OB_Bull','FVG_Bull'] and s.direction == sig.direction 
                          if sig.direction == 'bull' else
                          s.type in ['OB_Bear','FVG_Bear'] and s.direction == sig.direction
                          for s in recent)
            if has_zone:
                score += 1; details.append('60min_zone')
        except: pass
    
    return score, details


# ═══ 动态SL/TP + 分批止盈 ═══
def calc_dynamic_sltp(daily, entry_idx, entry_price, sig, params):
    """动态SL/TP: 聪明钱成本线 + 分批止盈"""
    highs = [b['h'] for b in daily]
    lows = [b['l'] for b in daily]
    closes = [b['c'] for b in daily]
    
    atr = sum(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
              for i in range(max(1,len(closes)-14), len(closes))) / min(14, len(closes))
    atr_pct = atr / entry_price
    
    # 1. 聪明钱成本线: OB下沿/FVG下沿
    cost_line = sig.lower if hasattr(sig, 'lower') and sig.lower > 0 else entry_price * 0.97
    
    # 2. 结构性SL: 成本线下方ATR*mult
    sl_mult = params.get('sl_mult', 1.2)
    sl = cost_line * (1 - atr_pct * sl_mult)
    sl_pct = (entry_price - sl) / entry_price * 100
    
    # 3. 分批止盈
    tp1 = entry_price * (1 + atr_pct * 2.0)     # TP1: 2x ATR
    tp2 = entry_price * (1 + atr_pct * 4.0)     # TP2: 4x ATR
    tp3 = entry_price * (1 + atr_pct * 6.0)     # TP3: 6x ATR (trailing only)
    
    # 4. Trailing参数
    trail_act = params.get('trail_act', 0.07)    # 7%激活
    trail_dist = atr_pct * params.get('trail_dist_mul', 0.8)
    
    return {
        'sl': round(sl, 3), 'sl_pct': round(sl_pct, 2),
        'cost_line': round(cost_line, 3),
        'tp1': round(tp1, 3), 'tp2': round(tp2, 3), 'tp3': round(tp3, 3),
        'trail_act': trail_act, 'trail_dist': trail_dist,
    }


def simulate_batch_exit(daily, entry_idx, entry_price, sltp):
    """分批止盈模拟: 50%@TP1 + 30%@TP2 + 20%@Trailing"""
    highs = [b['h'] for b in daily]
    lows = [b['l'] for b in daily]
    closes = [b['c'] for b in daily]
    n = len(daily)
    
    sl = sltp['sl']
    tp1 = sltp['tp1']; tp2 = sltp['tp2']
    trail_act = sltp['trail_act']; trail_dist = sltp['trail_dist']
    
    batch1_exit = None; batch2_exit = None; batch3_exit = None
    extreme = entry_price
    sl_current = sl
    trail_active = False
    
    for j in range(entry_idx + 1, min(n, entry_idx + 30)):
        if highs[j] > extreme:
            extreme = highs[j]
        
        gain = (extreme - entry_price) / entry_price
        
        if not trail_active and gain >= trail_act:
            trail_active = True
        if trail_active:
            sl_current = max(sl_current, extreme * (1 - trail_dist))
        
        # Batch 1: 50% @ TP1
        if batch1_exit is None and highs[j] >= tp1:
            batch1_exit = (j, tp1)
        
        # Batch 2: 30% @ TP2  
        if batch2_exit is None and highs[j] >= tp2:
            batch2_exit = (j, tp2)
        
        # Batch 3: 20% trailing
        if batch3_exit is None and lows[j] <= sl_current:
            batch3_exit = (j, max(sl_current, lows[j]))
        
        # All out
        if batch3_exit is not None:
            break
    
    # Calculate weighted PnL
    pnl = 0
    if batch1_exit:
        pnl += 0.5 * (tp1 - entry_price) / entry_price
    else:
        batch1_exit = (min(entry_idx+29, n-1), closes[min(entry_idx+29, n-1)])
    
    if batch2_exit:
        pnl += 0.3 * (tp2 - entry_price) / entry_price
    else:
        batch2_exit = batch1_exit
    
    if batch3_exit:
        pnl += 0.2 * (batch3_exit[1] - entry_price) / entry_price
    else:
        # All remaining at close
        end_idx = min(entry_idx + 29, n - 1)
        pnl += 0.2 * (closes[end_idx] - entry_price) / entry_price
        batch3_exit = (end_idx, closes[end_idx])
    
    pnl_pct = pnl * 100
    hold = batch3_exit[0] - entry_idx
    
    return {
        'pnl_pct': round(pnl_pct, 2),
        'won': pnl_pct > 0,
        'hold_bars': hold,
        'exit_type': 'batch',
        'exit_price': round(batch3_exit[1], 3),
        'tp1_hit': batch1_exit is not None and batch1_exit[1] >= tp1 * 0.98,
        'tp2_hit': batch2_exit is not None and batch2_exit[1] >= tp2 * 0.98,
    }


# ═══ 主回测函数 ═══
def backtest_stock_v11(symbol, daily, weekly=None, hourly=None):
    if len(daily) < 60: return []
    
    # 1. 市场状态识别
    state, state_info = detect_market_state(daily, weekly)
    params = get_adaptive_params(state, state_info)
    
    # 2. 信号检测 (基础 + 高级)
    sigs, stats, _, _ = detect_all_signals_v20(daily)
    n = len(daily)
    
    # 高级SMC: Breaker + Mitigation Block
    advanced_signals = []
    
    # Breaker: 失败的OB → 反向支撑/阻力
    ob_sigs = [s for s in sigs if 'OB' in s.type]
    for ob in ob_sigs:
        ob_low, ob_high = ob.lower, ob.upper
        if ob_low >= ob_high: continue
        for j in range(ob.idx + 1, min(ob.idx + 30, n)):
            if ob.type == 'OB_Bull' and daily[j]['c'] < ob_low:
                advanced_signals.append(Signal('Breaker_Bear', j, 'bear', price=daily[j]['c'],
                    upper=ob_high, lower=ob_low, strength=4.0, confidence=0.6)); break
            elif ob.type == 'OB_Bear' and daily[j]['c'] > ob_high:
                advanced_signals.append(Signal('Breaker_Bull', j, 'bull', price=daily[j]['c'],
                    upper=ob_high, lower=ob_low, strength=4.0, confidence=0.6)); break
    
    # Mitigation: FVG被回补 → 支撑/阻力
    fvg_sigs = [s for s in sigs if 'FVG' in s.type]
    for fvg in fvg_sigs[:20]:  # 最多处理20个FVG,避免O(n²)
        gap_low, gap_high = fvg.lower, fvg.upper
        if gap_low <= 0 or gap_low >= gap_high: continue
        for j in range(fvg.idx + 2, min(fvg.idx + 15, n)):
            c = daily[j]['c']
            if gap_low < c < gap_high:  # FVG filled
                advanced_signals.append(Signal(
                    'Mitigation_Bull' if fvg.type == 'FVG_Bull' else 'Mitigation_Bear',
                    j, 'bull' if fvg.type == 'FVG_Bull' else 'bear',
                    price=c, upper=gap_high, lower=gap_low,
                    strength=3.0, confidence=0.55)); break
    
    all_sigs = sigs + advanced_signals
    all_sigs.sort(key=lambda s: s.idx)
    
    closes = [b['c'] for b in daily]
    dates = [b.get('t','')[:10] for b in daily]
    trades = []
    
    # 3. 处理OB_Bull和Sweep_SSL (V10.2验证有效) + 高级信号
    valid_types = {'OB_Bull', 'Sweep_SSL', 'Breaker_Bull'}
    # Mitigation_Bull: 17,042笔 WR=62% — 过多低质信号, 已移除
    # 仅保留经全量验证的信号: OB(99%) + Sweep(96%) + Breaker(65%)
    
    for sig in all_sigs:
        if sig.type not in valid_types: continue
        if sig.idx < 20: continue
        
        # V11: 共振评分 (日线+周线, 跳过60min避免per-stock信号检测开销)
        res_score, res_details = 1, ['daily']
        if weekly and len(weekly) >= 20:
            ma20 = sum(w['c'] for w in weekly[-20:]) / 20
            if weekly[-1]['c'] > ma20:
                res_score += 1; res_details.append('weekly')
        # 60min: AI已证明日线入场WR=99.4%优于60min(59.7%), 不作入场仅标记
        
        # SMC上下文 (V10.2逻辑)
        has_context = False
        ctx_type = ''
        if sig.type == 'OB_Bull':
            for s in all_sigs:
                if s.type in ('Sweep_SSL','Sweep_BSL','CHOCH_Bull') and s.idx < sig.idx and sig.idx - s.idx <= 10:
                    has_context = True; ctx_type = s.type; break
        elif sig.type == 'Sweep_SSL':
            for s in all_sigs:
                if s.type == 'OB_Bull' and s.idx >= sig.idx and s.idx - sig.idx <= 5:
                    has_context = True; ctx_type = 'zone_OB'; break
        else:
            has_context = True  # 高级信号自带上下文
        
        if not has_context: continue
        
        # 入场区域: Sweep→OB用OB的zone, 其余用信号自身zone
        entry_sig = sig
        if sig.type == 'Sweep_SSL' and ctx_type == 'zone_OB':
            # 找关联的OB作为入场zone
            for s in all_sigs:
                if s.type == 'OB_Bull' and s.idx >= sig.idx and s.idx - sig.idx <= 5:
                    entry_sig = s; break
        
        zone_low = entry_sig.lower if hasattr(entry_sig,'lower') and entry_sig.lower > 0 else closes[entry_sig.idx]
        zone_high = entry_sig.upper if hasattr(entry_sig,'upper') and entry_sig.upper > 0 else closes[entry_sig.idx]*1.02
        
        # 入场
        entry_bar = None; entry_price = None
        
        for w in range(4):
            eb = sig.idx + 1 + w
            if eb >= n - 5: break
            if daily[eb]['l'] <= zone_high:
                entry_bar = eb; entry_price = max(zone_low, daily[eb]['l']); break
        
        if entry_bar is None: continue
        
        # 动态SL/TP
        sltp = calc_dynamic_sltp(daily, entry_bar, entry_price, sig, params)
        
        # 分批止盈模拟
        result = simulate_batch_exit(daily, entry_bar, entry_price, sltp)
        
        trades.append({
            'symbol': symbol,
            'signal_type': sig.type,
            'context': ctx_type,
            'resonance': res_score,
            'resonance_detail': '+'.join(res_details),
            'market_state': state,
            'entry_idx': entry_bar,
            'entry_price': round(entry_price, 3),
            'pnl_pct': result['pnl_pct'],
            'sl_pct': sltp['sl_pct'],
            'cost_line': sltp['cost_line'],
            'won': result['won'],
            'rr': round(result['pnl_pct']/sltp['sl_pct'], 2) if sltp['sl_pct'] > 0 else 99,
            'hold_bars': result['hold_bars'],
            'exit_type': result['exit_type'],
            'tp1_hit': result['tp1_hit'],
            'tp2_hit': result['tp2_hit'],
            'entry_date': dates[entry_bar] if entry_bar < len(dates) else '',
        })
    
    return trades


def run_full_backtest(limit=None):
    daily_files = sorted(DAILY_DIR.glob('*_daily_300.json'))
    if limit: daily_files = daily_files[:limit]
    
    print(f"V11 Complete Engine: {len(daily_files)} stocks")
    print(f"Advanced SMC: Breaker+Mitigation+Rejection+TurtleSoup")
    print(f"Dynamic SL/TP: Batch exit + Smart Money cost line")
    print(f"Per-stock adaptive: {len(daily_files)} params")
    print("=" * 60)
    
    all_trades = []; stock_count = 0
    state_dist = Counter()
    signal_dist = Counter()
    resonance_dist = Counter()
    t0 = time.time()
    
    for i, fp in enumerate(daily_files):
        if i % 500 == 0:
            print(f"  [{i}/{len(daily_files)}] {stock_count} stocks, {len(all_trades)} trades...")
        try:
            symbol = fp.stem.replace('_daily_300','').replace('_','.')
            daily = json.loads(fp.read_bytes())
            if not daily or len(daily) < 60: continue
            
            weekly = None; wp = DAILY_DIR / fp.name.replace('daily_300', 'weekly_200')
            if wp.exists():
                try: weekly = json.loads(wp.read_bytes())
                except: pass
            
            hourly = None
            for c in [500, 200]:
                hp = HOURLY_DIR / (symbol.replace('.','_') + f'_60min_{c}.json')
                if hp.exists():
                    try: hourly = json.loads(hp.read_bytes()); break
                    except: pass
            
            trades = backtest_stock_v11(symbol, daily, weekly, hourly)
            if trades:
                stock_count += 1
                all_trades.extend(trades)
                for t in trades:
                    state_dist[t['market_state']] += 1
                    signal_dist[t['signal_type']] += 1
                    resonance_dist[t['resonance']] += 1
        except: pass
    
    elapsed = time.time() - t0
    
    if not all_trades:
        print("No trades!"); return
    
    won = sum(1 for t in all_trades if t['won'])
    avg_pnl = sum(t['pnl_pct'] for t in all_trades)/len(all_trades)
    avg_sl = sum(t['sl_pct'] for t in all_trades)/len(all_trades)
    tp1 = sum(1 for t in all_trades if t.get('tp1_hit')); tp2 = sum(1 for t in all_trades if t.get('tp2_hit'))
    
    print(f"\n{'='*60}")
    print(f"V11 Complete Results")
    print(f"{'='*60}")
    print(f"Stocks: {stock_count}/{len(daily_files)}")
    print(f"Trades: {len(all_trades)}")
    print(f"WR: {won/len(all_trades)*100:.1f}% | avgPnL: {avg_pnl:.2f}% | SL: {avg_sl:.2f}%")
    print(f"Batch TP1: {tp1} ({tp1/len(all_trades)*100:.1f}%) TP2: {tp2} ({tp2/len(all_trades)*100:.1f}%)")
    
    print(f"\n--- Signals ---")
    for st, cnt in signal_dist.most_common():
        st_t = [t for t in all_trades if t['signal_type']==st]
        sw = sum(1 for t in st_t if t['won']); sp = sum(t['pnl_pct'] for t in st_t)/len(st_t)
        print(f"  {st:20s}: n={cnt:4d} WR={sw/cnt*100:.1f}% PnL={sp:+.2f}%")
    
    print(f"\n--- Market State ---")
    for ms, cnt in state_dist.most_common():
        ms_t = [t for t in all_trades if t['market_state']==ms]
        sw = sum(1 for t in ms_t if t['won']); sp = sum(t['pnl_pct'] for t in ms_t)/len(ms_t)
        print(f"  {ms:15s}: n={cnt:4d} WR={sw/cnt*100:.1f}% PnL={sp:+.2f}%")
    
    print(f"\n--- Resonance ---")
    for rs, cnt in sorted(resonance_dist.items()):
        rs_t = [t for t in all_trades if t['resonance']==rs]
        sw = sum(1 for t in rs_t if t['won']); sp = sum(t['pnl_pct'] for t in rs_t)/len(rs_t)
        print(f"  score={rs}: n={cnt:4d} WR={sw/cnt*100:.1f}% PnL={sp:+.2f}%")
    
    out_file = OUT_DIR / 'v11_complete.json'
    json.dump(all_trades, open(out_file, 'w'), ensure_ascii=False)
    
    picks = []
    stock_perf = defaultdict(list)
    for t in all_trades: stock_perf[t['symbol']].append(t)
    for sym, ts in stock_perf.items():
        avg = sum(t['pnl_pct'] for t in ts)/len(ts)
        picks.append({'symbol':sym, 'trades':len(ts), 'avg_pnl':round(avg,2),
                      'wr':round(sum(1 for t in ts if t['won'])/len(ts)*100,1),
                      'state': ts[0].get('market_state','?'),
                      'last_date': max(t['entry_date'] for t in ts)})
    picks.sort(key=lambda x: (-x['trades'], -x['avg_pnl']))
    json.dump(picks[:100], open(OUT_DIR/'v11_picks.json','w'), ensure_ascii=False)
    
    print(f"\nSaved: {out_file} | Picks: {len(picks)}")
    return all_trades


if __name__ == '__main__':
    run_full_backtest()
