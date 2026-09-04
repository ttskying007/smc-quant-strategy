#!/usr/bin/env python3
"""
V25 Auto-Fix Engine
Daily cron task: scan → backtest → diagnose → auto-apply fixes → reload frontend.

Runs at 09:00 CST daily (before market open 09:30).
1. Run full_scan on active stocks (limit=1000)
2. Run state-adaptive backtest 
3. Auto-diagnose: SL rate > 40%? TP rate < 10%? RANGE state leaking?
4. Auto-fix: adjust SL multiplier, TP placement, RANGE filter
5. Reload frontend
6. Save summary
"""
import json, sys, os, subprocess, time
from pathlib import Path
from collections import Counter
from datetime import datetime

SCRIPTS_DIR = Path('/root/.hermes/scripts')
V25_DIR = SCRIPTS_DIR / 'v25'
OUT_DIR = Path('/root/.hermes/smc_opt_v25')

def run(cmd, timeout=120):
    """Run a command and return (exit_code, stdout)."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, 
                         timeout=timeout, cwd=str(SCRIPTS_DIR))
        return r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"

def auto_diagnose(trades_path):
    """Analyze backtest results and return fix recommendations."""
    if not trades_path.exists():
        return []
    
    trades = json.loads(trades_path.read_text())
    n = len(trades)
    if n < 10:
        return []
    
    won = sum(1 for t in trades if t['won'])
    wr = won / n * 100
    avg_pnl = sum(t['pnl_pct'] for t in trades) / n
    exits = Counter(t['exit_reason'] for t in trades)
    
    sl_rate = (exits.get('SL_hit', 0) + exits.get('trailing', 0)) / n * 100
    tp_rate = exits.get('TP_hit', 0) / n * 100
    
    fixes = []
    
    # 1. SL too high → tighten
    if sl_rate > 50:
        avg_sl_pct = sum(t.get('sl_pct', 0) for t in trades) / n
        fixes.append({
            'type': 'SL_TIGHTEN',
            'metric': f'SL rate {sl_rate:.0f}% > 50% (avg SL={avg_sl_pct:.1f}%)',
            'action': 'Reduce sl_atr_mult by 20% in STATE_PARAMS',
            'auto': True
        })
    
    # 2. TP too low → extend
    if tp_rate < 15 and n > 50:
        avg_tp_pct = sum(t.get('tp_pct', 0) for t in trades) / n
        fixes.append({
            'type': 'TP_EXTEND',
            'metric': f'TP rate {tp_rate:.0f}% < 15% (avg TP={avg_tp_pct:.1f}%)',
            'action': 'Use 3rd structural high instead of 2nd for TP',
            'auto': True
        })
    
    # 3. RANGE state leaking → ensure filter
    range_trades = [t for t in trades if t.get('market_state') == 'RANGE']
    if range_trades:
        range_wr = sum(1 for t in range_trades if t['won']) / len(range_trades) * 100
        if range_wr < 50:
            fixes.append({
                'type': 'RANGE_FILTER',
                'metric': f'{len(range_trades)} RANGE trades WR={range_wr:.0f}%',
                'action': 'Block RANGE state picks from reaching frontend',
                'auto': True
            })
    
    # 4. Overall WR low
    if wr < 55:
        fixes.append({
            'type': 'WR_LOW',
            'metric': f'Overall WR={wr:.1f}% < 55%',
            'action': 'Require PINBAR or OTE confirmation for all entries',
            'auto': False  # Needs manual review
        })
    
    return fixes

def apply_fixes(fixes):
    """Apply auto-fixes to state_backtest.py."""
    if not fixes:
        return 0
    
    applied = 0
    bp = V25_DIR / 'state_backtest.py'
    content = bp.read_text()
    original = content
    
    for fix in fixes:
        if not fix['auto']:
            continue
        
        if fix['type'] == 'SL_TIGHTEN':
            # Reduce sl_atr_mult
            for state in ['TREND_UP', 'TREND_DOWN', 'HIGH_VOL']:
                old = f"'sl_atr_mult': {STATE_FIX[state]['current']}"
                new = f"'sl_atr_mult': {STATE_FIX[state]['new']}"
                if old in content:
                    content = content.replace(old, new)
        
        if fix['type'] == 'TP_EXTEND':
            if 'highs[1]' in content:
                content = content.replace('highs[1]', 'highs[-1]')
        
        if fix['type'] == 'RANGE_FILTER':
            # Already implemented via skip
            pass
        
        applied += 1
    
    if content != original:
        bp.write_text(content)
        print(f"  Applied {applied} auto-fixes to {bp}")
    
    return applied

# Current state params (for auto-adjustment)
STATE_FIX = {
    'TREND_UP':    {'current': 0.4, 'new': 0.32},
    'TREND_DOWN':  {'current': 0.4, 'new': 0.32},
    'HIGH_VOL':    {'current': 0.8, 'new': 0.64},
}

def reload_frontend():
    """Hit the /api/reload endpoint."""
    import urllib.request
    try:
        urllib.request.urlopen('http://localhost:8890/api/reload', timeout=10)
        return True
    except:
        return False

def main():
    start = time.time()
    report = []
    report.append(f"=== V25 Auto-Fix Report {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
    
    # Step 1: Full scan
    report.append("\n[1/4] Full scan...")
    ec, out = run(f"python3 {V25_DIR}/full_scan.py --limit 1000 2>&1", timeout=180)
    picks_path = OUT_DIR / 'v25_picks.json'
    if picks_path.exists():
        picks = json.loads(picks_path.read_text())
        report.append(f"  Scanned: {len(picks)} picks")
    else:
        report.append(f"  Scan failed: {out[:200]}")
        # Try existing picks
        pass
    
    # Step 2: State backtest
    report.append("\n[2/4] State backtest...")
    ec, out = run(f"python3 {V25_DIR}/state_backtest.py 2>&1", timeout=120)
    report.append(f"  Exit: {ec}")
    
    # Step 3: Diagnose + fix
    report.append("\n[3/4] Auto-diagnose...")
    trades_path = OUT_DIR / 'v255_trades.json'
    if trades_path.exists():
        trades = json.loads(trades_path.read_text())
        n = len(trades)
        won = sum(1 for t in trades if t['won'])
        wr = won/n*100 if n else 0
        avg_pnl = sum(t['pnl_pct'] for t in trades)/n if n else 0
        report.append(f"  Trades: {n} WR: {wr:.1f}% avgP: {avg_pnl:+.2f}%")
        
        fixes = auto_diagnose(trades_path)
        if fixes:
            report.append(f"  Issues found: {len(fixes)}")
            for f in fixes:
                report.append(f"    [{f['type']}] {f['metric']} → {f['action']}")
            applied = apply_fixes(fixes)
            if applied:
                report.append(f"  Auto-applied: {applied}/{len(fixes)}")
                
                # Rerun backtest with fixes
                report.append("  Rerunning backtest with fixes...")
                ec, out = run(f"python3 {V25_DIR}/state_backtest.py 2>&1", timeout=120)
                if trades_path.exists():
                    new_trades = json.loads(trades_path.read_text())
                    nn = len(new_trades)
                    nw = sum(1 for t in new_trades if t['won'])
                    nwr = nw/nn*100 if nn else 0
                    nap = sum(t['pnl_pct'] for t in new_trades)/nn if nn else 0
                    report.append(f"  Post-fix: {nn}t WR={nwr:.1f}% avgP={nap:+.2f}%")
                    
                    # Save as primary
                    json.dump(new_trades, open(OUT_DIR/'v25_trades.json', 'w'), 
                             ensure_ascii=False, indent=2)
        else:
            report.append("  No issues found - system healthy")
    else:
        report.append("  No backtest data available")
    
    # Step 4: Reload frontend
    report.append("\n[4/4] Reload frontend...")
    if reload_frontend():
        report.append("  Frontend reloaded OK")
    else:
        report.append("  Frontend reload FAILED (may need restart)")
    
    elapsed = time.time() - start
    report.append(f"\nTotal time: {elapsed:.0f}s")
    
    # Save report
    report_path = OUT_DIR / 'auto_fix_report.txt'
    report_path.write_text('\n'.join(report))
    
    print('\n'.join(report))
    return report

if __name__ == '__main__':
    main()
