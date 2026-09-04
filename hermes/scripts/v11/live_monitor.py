#!/usr/bin/env python3
"""
SMC Live Monitor — 实时信号扫描 + 选股推荐
==========================================
每5分钟扫描V10.2精选股票，检测新信号并生成推荐。
集成到前端 /monitor 页面。
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20

DAILY_DIR = Path('/root/.hermes/kline_cache')
OUT_DIR = Path('/root/.hermes/smc_opt_v10')
MONITOR_DIR = Path('/root/.hermes/smc_opt_v10/monitor')
MONITOR_DIR.mkdir(exist_ok=True)


def scan_recent_signals(picks_file=None, top_n=50):
    """扫描精选股票的最新信号"""
    # Load picks
    picks_path = picks_file or (OUT_DIR / 'v10_picks.json')
    try:
        picks = json.loads(picks_path.read_bytes())
    except:
        # Fallback to V9 picks
        picks_path = Path('/root/.hermes/smc_opt_v9/v9_picks.json')
        picks = json.loads(picks_path.read_bytes())
    
    picks = picks[:top_n]
    results = []
    
    for p in picks:
        symbol = p['symbol']
        fn = symbol.replace('.SH','_SH').replace('.SZ','_SZ').replace('.BJ','_BJ') + '_daily_300.json'
        fp = DAILY_DIR / fn
        if not fp.exists(): fp = DAILY_DIR / (symbol + '_daily_300.json')
        if not fp.exists(): continue
        
        try:
            daily = json.loads(fp.read_bytes())
            sigs, stats, _, _ = detect_all_signals_v20(daily)
            
            # Filter for recent signals (last 5 bars)
            n = len(daily)
            recent = [s for s in sigs if s.idx >= n - 5]
            
            if not recent:
                continue
            
            # Check for OB_Bull and Sweep_SSL (V10.2 signals)
            ob_bulls = [s for s in recent if s.type == 'OB_Bull']
            sweep_ssl = [s for s in recent if s.type == 'Sweep_SSL']
            
            # Check SMC context
            ob_with_ctx = []
            for ob in ob_bulls:
                for s in sigs:
                    if s.type in ('Sweep_SSL','Sweep_BSL','CHOCH_Bull') and s.idx < ob.idx and ob.idx - s.idx <= 10:
                        ob_with_ctx.append({'ob': ob, 'ctx': s.type, 'ctx_bar': s.idx})
                        break
            
            sweep_with_zone = []
            for sw in sweep_ssl:
                for s in sigs:
                    if s.type == 'OB_Bull' and s.idx >= sw.idx and s.idx - sw.idx <= 5:
                        sweep_with_zone.append({'sweep': sw, 'zone': s.type, 'zone_bar': s.idx})
                        break
            
            entry = {
                'symbol': symbol,
                'last_bar': str(daily[-1].get('t', daily[-1].get('date','')))[:10],
                'last_close': round(daily[-1]['c'], 2),
                'picks_wr': p['wr'],
                'picks_avg': p['avg_pnl'],
                'picks_trades': p['trades'],
                'ob_bull_count': len(ob_bulls),
                'sweep_ssl_count': len(sweep_ssl),
                'ob_with_ctx': len(ob_with_ctx),
                'sweep_with_zone': len(sweep_with_zone),
                'score': 0,
            }
            
            # Score: OB with context = 3, Sweep with zone = 3, both = 5
            if ob_with_ctx: entry['score'] += 3
            if sweep_with_zone: entry['score'] += 3
            if ob_with_ctx and sweep_with_zone: entry['score'] += 2  # Both = bonus
            
            if entry['score'] >= 3:
                results.append(entry)
                
        except Exception as e:
            continue
    
    results.sort(key=lambda x: -x['score'])
    return results


def generate_signal_report():
    """生成监控报告"""
    results = scan_recent_signals()
    
    high_confidence = [r for r in results if r['score'] >= 5]
    medium_confidence = [r for r in results if 3 <= r['score'] < 5]
    
    report = {
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_scanned': 50,
        'stocks_with_signals': len(results),
        'high_confidence': len(high_confidence),
        'medium_confidence': len(medium_confidence),
        'signals': results,
        'top_picks': results[:10],
    }
    
    # Save
    json.dump(report, open(MONITOR_DIR / 'live_report.json', 'w'), ensure_ascii=False, indent=2)
    
    # Print summary
    print(f"Live Monitor Report: {report['generated_at']}")
    print(f"  Scanned: {report['total_scanned']} | Signals: {report['total_scanned']}")
    print(f"  High confidence (score>=5): {report['high_confidence']}")
    print(f"  Medium confidence (score>=3): {report['medium_confidence']}")
    
    if high_confidence:
        print(f"\n  🔴 HIGH Confidence Signals:")
        for r in high_confidence[:10]:
            print(f"    {r['symbol']:12s} score={r['score']} OB={r['ob_with_ctx']} Swp={r['sweep_with_zone']} close={r['last_close']}")
    
    if medium_confidence:
        print(f"\n  🟡 MEDIUM Confidence:")
        for r in medium_confidence[:5]:
            print(f"    {r['symbol']:12s} score={r['score']} OB={r['ob_with_ctx']} Swp={r['sweep_with_zone']}")
    
    return report


if __name__ == '__main__':
    generate_signal_report()
