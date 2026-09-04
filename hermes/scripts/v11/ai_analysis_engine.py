#!/usr/bin/env python3
"""
SMC AI Analysis Engine — 信号质量多维评估 + 出入场精度分析 + 自适应推荐
=========================================================================
分析维度:
  1. 信号质量: OB位置/结构/位移, FVG回补率, CHOCH有效性, Sweep深度
  2. 出入场精度: 入场时机(过早/过晚), 出场时机(过早/过晚), 最大回撤
  3. 模式识别: 赢/输交易的特征差异, 信号组合效果
  4. 自适应推荐: 基于分析结果给出参数调整建议
"""
import json, sys, math, time
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20, _calc_atr

CACHE = Path('/root/.hermes/kline_cache')
CACHE_60 = Path('/root/.hermes/kline_cache_60min')
V9_FILE = Path('/root/.hermes/smc_opt_v9/v9_mtf_full.json')
OUT_DIR = Path('/root/.hermes/smc_opt_v9/analysis')
OUT_DIR.mkdir(exist_ok=True)


def analyze_signal_quality(all_trades):
    """分析各信号类型的质量"""
    from collections import Counter
    
    results = {}
    for sig_type in ['OB_Bull', 'FVG_Bull', 'CHOCH_Bull', 'BOS_Bull', 'Sweep_SSL']:
        trades = [t for t in all_trades if t['signal_type'] == sig_type]
        if not trades: continue
        
        won = sum(1 for t in trades if t['won'])
        lost = len(trades) - won
        avg_pnl = sum(t['pnl_pct'] for t in trades) / len(trades)
        avg_sl = sum(t['sl_pct'] for t in trades) / len(trades)
        avg_hold = sum(t['hold_bars'] for t in trades) / len(trades)
        tp_rate = sum(1 for t in trades if t.get('exit_type') == 'tp') / len(trades) * 100
        
        # Win/Loss analysis
        win_trades = [t for t in trades if t['won']]
        loss_trades = [t for t in trades if not t['won']]
        avg_win = sum(t['pnl_pct'] for t in win_trades) / len(win_trades) if win_trades else 0
        avg_loss = sum(t['pnl_pct'] for t in loss_trades) / len(loss_trades) if loss_trades else 0
        win_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 99
        
        # Entry source breakdown
        h60 = sum(1 for t in trades if t.get('entry_source') == '60min')
        
        results[sig_type] = {
            'count': len(trades), 'won': won, 'lost': lost,
            'wr': round(won/len(trades)*100, 1),
            'avg_pnl': round(avg_pnl, 2), 'avg_sl': round(avg_sl, 2),
            'avg_hold': round(avg_hold, 1), 'tp_rate': round(tp_rate, 1),
            'avg_win': round(avg_win, 2), 'avg_loss': round(avg_loss, 2),
            'win_loss_ratio': round(win_loss_ratio, 1),
            'h60_pct': round(h60/len(trades)*100, 1),
        }
    
    return results


def analyze_entry_timing(trades_sample):
    """分析入场时机问题"""
    # 分类入场问题
    early_entry = []   # 入场后先跌后涨 (有回撤但最终盈利)
    late_entry = []    # 入场前已涨很多 (错过主升浪)
    perfect_entry = [] # 入场即涨无回撤
    
    for t in trades_sample:
        pnl = t['pnl_pct']
        hold = t['hold_bars']
        
        if pnl > 5 and hold <= 3:
            perfect_entry.append(t)
        elif pnl < -2:
            early_entry.append(t)  # 亏损 = 入场太早或方向错了
        elif pnl > 5 and hold > 5:
            early_entry.append(t)  # 大盈利但持仓久 = 可能入场过早
    
    return {
        'perfect': len(perfect_entry),
        'early': len(early_entry),
        'late': len(late_entry),
        'total': len(trades_sample),
        'perfect_pct': round(len(perfect_entry)/max(len(trades_sample),1)*100, 1),
    }


def analyze_exit_timing(trades_sample):
    """分析出场时机问题"""
    too_early = []    # 出场后继续涨 (>5%)
    too_late = []     # 出场前已有大幅回撤
    good_exit = []    # TP命中
    
    for t in trades_sample:
        if t.get('exit_type') == 'tp':
            good_exit.append(t)
        elif t['won'] and t['pnl_pct'] < 3:
            too_early.append(t)  # 盈利但很小 = trailing过早
        elif not t['won']:
            too_late.append(t)   # 亏损 = SL触发太晚或太宽
    
    return {
        'good': len(good_exit),
        'too_early': len(too_early),
        'too_late': len(too_late),
        'too_early_pct': round(len(too_early)/max(len(trades_sample),1)*100, 1),
    }


def analyze_ob_signal_detail(all_trades):
    """深度分析OB_Bull信号 — 逐维度检查"""
    ob_trades = [t for t in all_trades if t['signal_type'] == 'OB_Bull']
    if not ob_trades: return {}
    
    # 按入场来源分析
    daily_ob = [t for t in ob_trades if t.get('entry_source') != '60min']
    h60_ob = [t for t in ob_trades if t.get('entry_source') == '60min']
    
    # 按PnL分档
    pnl_buckets = {'big_win': [], 'win': [], 'small_win': [], 'loss': []}
    for t in ob_trades:
        p = t['pnl_pct']
        if p > 10: pnl_buckets['big_win'].append(t)
        elif p > 3: pnl_buckets['win'].append(t)
        elif p > 0: pnl_buckets['small_win'].append(t)
        else: pnl_buckets['loss'].append(t)
    
    return {
        'total': len(ob_trades),
        'daily_entry': len(daily_ob),
        'h60_entry': len(h60_ob),
        'daily_wr': round(sum(1 for t in daily_ob if t['won'])/max(len(daily_ob),1)*100, 1),
        'h60_wr': round(sum(1 for t in h60_ob if t['won'])/max(len(h60_ob),1)*100, 1),
        'pnl_distribution': {k: len(v) for k, v in pnl_buckets.items()},
        'avg_daily_pnl': round(sum(t['pnl_pct'] for t in daily_ob)/max(len(daily_ob),1), 2),
        'avg_h60_pnl': round(sum(t['pnl_pct'] for t in h60_ob)/max(len(h60_ob),1), 2),
    }


def analyze_smart_money_context(all_trades, n_sample=500):
    """SMC聪明钱上下文分析 — 检查信号前后是否有正确的SMC结构"""
    import random
    sample = random.sample(all_trades, min(n_sample, len(all_trades)))
    
    results = {
        'with_liquidity_sweep': 0,    # 信号前有流动性猎杀
        'with_structure_break': 0,    # 信号前有结构突破
        'at_swing_point': 0,          # 信号在真实摆动点
        'with_fvg_nearby': 0,         # 信号附近有FVG
        'isolated_signal': 0,         # 孤立的信号(无上下文)
        'analyzed': 0,
        'context_win_rates': defaultdict(list),
    }
    
    for t in sample:
        symbol = t['symbol']
        results['analyzed'] += 1
        
        # Load daily data
        fn = symbol.replace('.SH','_SH').replace('.SZ','_SZ').replace('.BJ','_BJ') + '_daily_300.json'
        fp = CACHE / fn
        if not fp.exists(): fp = CACHE / (symbol + '_daily_300.json')
        if not fp.exists(): continue
        
        try:
            data = json.loads(fp.read_bytes())
            sigs, stats, swings, _ = detect_all_signals_v20(data)
            
            entry_idx = t['entry_idx']
            sig_type = t['signal_type']
            
            # Check for liquidity sweep before signal (within 10 bars)
            has_sweep = any(
                ('Sweep' in s.type) and s.idx < entry_idx and entry_idx - s.idx <= 10
                for s in sigs
            )
            
            # Check for structure break (CHOCH/BOS) before signal
            has_structure = any(
                ('CHOCH' in s.type or 'BOS' in s.type) 
                and s.idx < entry_idx and entry_idx - s.idx <= 15
                for s in sigs
            )
            
            # Check if at swing point
            at_swing = any(
                abs(s.bar_idx - entry_idx) <= 2 for s in swings
            ) if swings else False
            
            # Check for FVG nearby
            has_fvg = any(
                'FVG' in s.type and abs(s.idx - entry_idx) <= 5
                for s in sigs
            )
            
            context_count = sum([has_sweep, has_structure, at_swing, has_fvg])
            ctx_key = f"ctx_{context_count}"
            
            if has_sweep: results['with_liquidity_sweep'] += 1
            if has_structure: results['with_structure_break'] += 1
            if at_swing: results['at_swing_point'] += 1
            if has_fvg: results['with_fvg_nearby'] += 1
            if context_count == 0: results['isolated_signal'] += 1
            
            results['context_win_rates'][ctx_key].append(t['won'])
            
        except Exception as e:
            continue
    
    # Calculate context WR
    ctx_wr = {}
    for k, wins in results['context_win_rates'].items():
        if wins:
            ctx_wr[k] = round(sum(wins)/len(wins)*100, 1)
    
    results['context_wr'] = ctx_wr
    del results['context_win_rates']  # Clean up raw data
    
    return results


def generate_recommendations(quality, smc_context, entry_analysis, exit_analysis):
    """基于分析结果生成自适应推荐"""
    recs = []
    
    # Signal quality recommendations
    if 'FVG_Bull' in quality:
        fvg = quality['FVG_Bull']
        if fvg['wr'] < 55:
            recs.append({
                'area': '信号过滤',
                'severity': 'high',
                'finding': f'FVG_Bull WR={fvg["wr"]}% — 日线FVG回补率过高',
                'recommendation': '添加FVG回补检查：若FVG已被回补>50%则跳过。或仅用在周线趋势强bullish时。',
            })
    
    if 'BOS_Bull' in quality:
        bos = quality['BOS_Bull']
        if bos['wr'] < 50:
            recs.append({
                'area': '信号过滤',
                'severity': 'high',
                'finding': f'BOS_Bull WR={bos["wr"]}% — 不适合独立交易',
                'recommendation': 'BOS仅作为CHOCH/OB的确认信号，不作为独立入场依据。',
            })
    
    if 'OB_Bull' in quality:
        ob = quality['OB_Bull']
        if ob['h60_pct'] < 30:
            recs.append({
                'area': '入场精度',
                'severity': 'medium',
                'finding': f'OB_Bull仅{ob["h60_pct"]}%使用60min入场',
                'recommendation': '提升60min数据覆盖率，60min入场可提高OB的入场精度。',
            })
    
    # Entry/exit recommendations
    if entry_analysis.get('perfect_pct', 0) < 30:
        recs.append({
            'area': '入场时机',
            'severity': 'high',
            'finding': f'仅{entry_analysis["perfect_pct"]}%的入场是"完美"的(入场即涨无回撤)',
            'recommendation': '增加入场确认：等待OB区域被测试后出现Pinbar/Engulf确认再入场，而非触及即入。',
        })
    
    if exit_analysis.get('too_early_pct', 0) > 30:
        recs.append({
            'area': '出场时机',
            'severity': 'medium',
            'finding': f'{exit_analysis["too_early_pct"]}%的交易出场过早(PnL<3%)',
            'recommendation': '放宽trailing激活阈值从+5%到+7%，增加最小持有bar数。',
        })
    
    # SMC context recommendations
    isolated_pct = smc_context.get('isolated_signal', 0) / max(smc_context.get('analyzed', 1), 1) * 100
    if isolated_pct > 20:
        recs.append({
            'area': 'SMC上下文',
            'severity': 'high',
            'finding': f'{isolated_pct:.0f}%的信号缺乏SMC上下文(无LIQ/STRUCT/摆动点)',
            'recommendation': '强制要求每个入场信号至少有1个SMC上下文确认(LIQ Sweep或CHOCH/BOS在前)。',
        })
    
    # Context WR analysis
    ctx_wr = smc_context.get('context_wr', {})
    if ctx_wr:
        best_ctx = max(ctx_wr.items(), key=lambda x: x[1])
        worst_ctx = min(ctx_wr.items(), key=lambda x: x[1])
        recs.append({
            'area': 'SMC上下文',
            'severity': 'info',
            'finding': f'有{best_ctx[0]}个上下文的信号WR={best_ctx[1]}%，孤立信号WR={ctx_wr.get("ctx_0", "N/A")}%',
            'recommendation': f'优先选择有{best_ctx[0].replace("ctx_","")}个SMC上下文确认的信号。',
        })
    
    return recs


def run_full_analysis():
    """主分析流程"""
    print("=" * 70)
    print("SMC AI Analysis Engine")
    print("=" * 70)
    
    # Load data
    all_trades = json.loads(V9_FILE.read_bytes()) if V9_FILE.exists() else []
    if not all_trades:
        print("ERROR: No V9 backtest data")
        return
    
    print(f"\nLoaded {len(all_trades)} trades from V9 backtest")
    
    # 1. Signal quality
    print("\n[1/4] Analyzing signal quality...")
    quality = analyze_signal_quality(all_trades)
    
    print("\n--- Signal Quality Summary ---")
    for sig, q in sorted(quality.items(), key=lambda x: -x[1]['wr']):
        print(f"  {sig:15s}: n={q['count']:5d} WR={q['wr']:5.1f}% avgPnL={q['avg_pnl']:+6.2f}% "
              f"avgWin={q['avg_win']:+5.2f}% avgLoss={q['avg_loss']:+5.2f}% W/L={q['win_loss_ratio']:.1f}x "
              f"TP={q['tp_rate']:.0f}% h60={q['h60_pct']:.0f}%")
    
    # 2. Entry/Exit timing
    print("\n[2/4] Analyzing entry/exit timing...")
    entry_analysis = analyze_entry_timing(all_trades)
    exit_analysis = analyze_exit_timing(all_trades)
    
    print(f"  Entry: perfect={entry_analysis['perfect']} ({entry_analysis['perfect_pct']}%) "
          f"early={entry_analysis['early']}")
    print(f"  Exit:  good={exit_analysis['good']} too_early={exit_analysis['too_early']} ({exit_analysis['too_early_pct']}%)")
    
    # 3. Smart money context
    print("\n[3/4] Analyzing SMC smart money context...")
    smc_context = analyze_smart_money_context(all_trades, n_sample=1000)
    
    print(f"  Analyzed: {smc_context['analyzed']} trades")
    print(f"  With LIQ sweep:   {smc_context['with_liquidity_sweep']} ({smc_context['with_liquidity_sweep']/max(smc_context['analyzed'],1)*100:.0f}%)")
    print(f"  With STRUCT break: {smc_context['with_structure_break']} ({smc_context['with_structure_break']/max(smc_context['analyzed'],1)*100:.0f}%)")
    print(f"  At swing point:   {smc_context['at_swing_point']} ({smc_context['at_swing_point']/max(smc_context['analyzed'],1)*100:.0f}%)")
    print(f"  With FVG nearby:  {smc_context['with_fvg_nearby']} ({smc_context['with_fvg_nearby']/max(smc_context['analyzed'],1)*100:.0f}%)")
    print(f"  Isolated (no ctx): {smc_context['isolated_signal']} ({smc_context['isolated_signal']/max(smc_context['analyzed'],1)*100:.0f}%)")
    print(f"  Context WR: {smc_context.get('context_wr', {})}")
    
    # 4. OB deep dive
    print("\n[4/4] Deep-diving OB_Bull signal...")
    ob_detail = analyze_ob_signal_detail(all_trades)
    print(f"  OB_Bull: {ob_detail.get('total',0)} trades")
    print(f"  Daily entry: {ob_detail.get('daily_entry',0)} WR={ob_detail.get('daily_wr',0)}% avgPnL={ob_detail.get('avg_daily_pnl',0):+.2f}%")
    print(f"  60min entry: {ob_detail.get('h60_entry',0)} WR={ob_detail.get('h60_wr',0)}% avgPnL={ob_detail.get('avg_h60_pnl',0):+.2f}%")
    print(f"  PnL distribution: {ob_detail.get('pnl_distribution', {})}")
    
    # Generate recommendations
    print("\n" + "=" * 70)
    print("AI RECOMMENDATIONS")
    print("=" * 70)
    recommendations = generate_recommendations(quality, smc_context, entry_analysis, exit_analysis)
    
    for i, rec in enumerate(recommendations):
        sev_icon = {'high': '🔴', 'medium': '🟡', 'info': '🔵'}.get(rec['severity'], '⚪')
        print(f"\n{sev_icon} [{rec['area']}] {rec['finding']}")
        print(f"   → {rec['recommendation']}")
    
    # Save results
    report = {
        'signal_quality': quality,
        'entry_analysis': entry_analysis,
        'exit_analysis': exit_analysis,
        'smc_context': {k: v for k, v in smc_context.items() if k != 'context_win_rates'},
        'ob_detail': ob_detail,
        'recommendations': recommendations,
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    
    out_file = OUT_DIR / 'ai_analysis_report.json'
    json.dump(report, open(out_file, 'w'), ensure_ascii=False, indent=2)
    print(f"\nReport saved: {out_file}")
    
    return report


if __name__ == '__main__':
    run_full_analysis()
