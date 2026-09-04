#!/usr/bin/env python3
"""Sync Phase 2 daily_scan picks → V66 data pipeline
1. Merge Phase 2 picks into v66_picks.json
2. Generate v66_trades.json entries from Phase 2 picks
3. Update v66_report.json with Phase 2 metrics
"""
import json, shutil
from pathlib import Path
from datetime import datetime

ROOT = Path('/root/.hermes')
V25_DIR = ROOT / 'smc_opt_v25'
V66_DIR = ROOT / 'smc_opt_v66'

# Backup first
for f in ['v66_picks.json', 'v66_trades.json', 'v66_report.json']:
    src = V66_DIR / f
    if src.exists():
        bak = V66_DIR / f'{f}.bak_phase2_sync_{datetime.now().strftime("%Y%m%d%H%M%S")}'
        shutil.copy2(src, bak)
        print(f"  Backup: {bak.name}")

# Load Phase 2 picks
phase2_picks = json.loads((V25_DIR / 'v26_picks.json').read_text())
phase2_active = [p for p in phase2_picks if p.get('is_active_pick')]
phase2_latest = [p for p in phase2_active if p.get('entry_date', '') >= '20260609']
print(f"\nPhase 2 picks: total={len(phase2_picks)} active={len(phase2_active)} latest={len(phase2_latest)}")

# Load existing V66 data
v66_picks_old = json.loads((V66_DIR / 'v66_picks.json').read_text())
v66_trades_old = json.loads((V66_DIR / 'v66_trades.json').read_text())
print(f"V66 old: picks={len(v66_picks_old)} trades={len(v66_trades_old)}")

# === STEP 1: Merge picks ===
# Keep historical V66 picks (non-active) + Phase 2 active picks
v66_historical = [p for p in v66_picks_old if not p.get('is_active_pick')]

# Convert Phase 2 picks to V66 format
phase2_as_v66 = []
for p in phase2_latest:
    v66_pick = dict(p)
    v66_pick['engine'] = 'V66_FULL_MARKET_SCAN'
    v66_pick['definition_version'] = 'V66_PHASE2_POI_RETRACE'
    v66_pick['pick_scope'] = 'ACTIVE_CANDIDATE'
    v66_pick['is_active_pick'] = True
    # Add join_date = pick_date
    v66_pick['join_date'] = p.get('pick_date') or p.get('select_date') or p.get('entry_date')
    v66_pick['select_date'] = p.get('select_date') or p.get('pick_date') or p.get('entry_date')
    # Ensure zone fields
    if not v66_pick.get('zone_low') and v66_pick.get('dz_low'):
        v66_pick['zone_low'] = v66_pick['dz_low']
    if not v66_pick.get('zone_high') and v66_pick.get('dz_high'):
        v66_pick['zone_high'] = v66_pick['dz_high']
    # SL/TP
    if not v66_pick.get('sl') and v66_pick.get('v25_sl_price'):
        v66_pick['sl'] = v66_pick['v25_sl_price']
    if not v66_pick.get('tp1'):
        tiers = v66_pick.get('v25_tp_tiers', [])
        if tiers and isinstance(tiers[0], dict):
            v66_pick['tp1'] = tiers[0].get('price', 0)
    # Cost line
    if not v66_pick.get('cost_line'):
        zl = v66_pick.get('zone_low', 0) or v66_pick.get('dz_low', 0)
        zh = v66_pick.get('zone_high', 0) or v66_pick.get('dz_high', 0)
        v66_pick['cost_line'] = (zl + zh) / 2 if zl and zh else v66_pick.get('entry_price', 0)
    # Volatility
    if not v66_pick.get('volatility_pct'):
        risk = v66_pick.get('risk_pct') or v66_pick.get('v25_sl_pct') or 0
        v66_pick['volatility_pct'] = risk
    
    # Dedup: same symbol + same entry_date
    phase2_as_v66.append(v66_pick)

# Dedup by symbol+entry_date
seen = set()
deduped = []
for p in phase2_as_v66:
    key = (p.get('symbol'), p.get('entry_date'))
    if key not in seen:
        seen.add(key)
        deduped.append(p)
phase2_as_v66 = deduped

# Merge: historical + Phase 2 active
v66_picks_new = v66_historical + phase2_as_v66
print(f"\nMerged picks: {len(v66_historical)} historical + {len(phase2_as_v66)} Phase 2 = {len(v66_picks_new)} total")

# Write picks
(V66_DIR / 'v66_picks.json').write_text(json.dumps(v66_picks_new, ensure_ascii=False, indent=2))
print(f"Written: v66_picks.json ({len(v66_picks_new)} picks)")

# === STEP 2: Generate trades from Phase 2 picks ===
# Phase 2 picks that are "live" (haven't exited yet) → add as open trades
phase2_trades = []
for p in phase2_as_v66:
    trade = {
        'symbol': p.get('symbol'),
        'name': p.get('name', ''),
        'entry_date': p.get('entry_date', ''),
        'signal_date': p.get('signal_date') or p.get('confirm_date') or p.get('pick_date') or '',
        'signal_type': p.get('zone_type', ''),
        'signal_price': p.get('price', p.get('entry_price', 0)),
        'entry_price': p.get('entry_price', 0),
        'exit_price': 0,
        'exit_date': '',
        'entry_type': p.get('conf_type', ''),
        'conf_type': p.get('conf_type', ''),
        'zone_type': p.get('zone_type', ''),
        'zone_low': p.get('zone_low', p.get('dz_low', 0)),
        'zone_high': p.get('zone_high', p.get('dz_high', 0)),
        'pick_date': p.get('pick_date', ''),
        'select_date': p.get('select_date', ''),
        'join_date': p.get('join_date', ''),
        'cost_line': p.get('cost_line', 0),
        'smart_money_cost': p.get('cost_line', p.get('smart_money_cost', 0)),
        'volatility_pct': p.get('volatility_pct', p.get('risk_pct', 0)),
        'sl': p.get('sl', p.get('v25_sl_price', 0)),
        'sl_pct': p.get('sl_initial_pct', p.get('v25_sl_pct', 0)),
        'tp1': p.get('tp1', 0),
        'tp_pct': p.get('tp_pct', 0),
        'pnl_pct': 0,
        'rr': 0,
        'hold_bars': 0,
        'won': False,
        'exit_reason': 'OPEN',
        'entry_detail': 'phase2_poi_retrace',
        'engine': 'V66_FULL_MARKET_SCAN',
        'definition_version': 'V66_PHASE2_POI_RETRACE',
        'ctx_seq': p.get('ctx_seq', ''),
        'seq': p.get('seq', ''),
        'market_state': p.get('market_state') or p.get('regime') or '',
        'quality_score': p.get('score', 0),
        'had_retrace': True,
        'sweep_tag': p.get('sweep_tag', ''),
        'zone_age': p.get('zone_age', 0),
        'entry_idx': p.get('entry_idx'),
        'sig_idx': p.get('zone_bar'),
        'confirmed_at': p.get('zone_bar', 0) + p.get('zone_age', 0) if p.get('zone_bar') else None,
        # Signal chain: zone → structure → retrace
        'retrace_depth_pct': p.get('retrace_depth_pct', 0),
    }
    # Compute TP percentage
    ep = trade['entry_price']
    tp1 = trade.get('tp1', 0)
    if ep and tp1:
        trade['tp_pct'] = round((tp1 / ep - 1) * 100, 2)
    
    phase2_trades.append(trade)

# Keep old V66 historical trades + add Phase 2 live trades
# Mark old trades as historical (entry_date < 20260609)
v66_old_closed = [t for t in v66_trades_old if t.get('entry_date', '') < '20260609']
v66_trades_new = v66_old_closed + phase2_trades
print(f"Merged trades: {len(v66_old_closed)} old closed + {len(phase2_trades)} Phase 2 open = {len(v66_trades_new)} total")

# Write trades
(V66_DIR / 'v66_trades.json').write_text(json.dumps(v66_trades_new, ensure_ascii=False, indent=2))
print(f"Written: v66_trades.json ({len(v66_trades_new)} trades)")

# === STEP 3: Update report ===
report = {
    'generated_at': datetime.now().isoformat(timespec='seconds'),
    'profile': 'V66 Phase 2 POI Retrace (同步自 daily_scan)',
    'source': 'daily_scan.py Phase 2 → v26_picks.json',
    'n_source_picks': len(phase2_picks),
    'n_phase2_active': len(phase2_active),
    'n_phase2_latest': len(phase2_latest),
    'n_trades': len(v66_trades_new),
    'n_picks': len(v66_picks_new),
    'n_historical_trades': len(v66_old_closed),
    'n_live_trades': len(phase2_trades),
    'phase2_backtest': json.loads((V25_DIR / 'phase2_backtest_results.json').read_text()) if (V25_DIR / 'phase2_backtest_results.json').exists() else {},
    'entry_logic': 'POI_RETRACE (价格回撤zone后入场, 非立即入场)',
    'key_changes': [
        'entry_mode: immediate → POI retrace (30 bars window)',
        'ctx_seq format: zone → structure → RETRACE',
        'SL buffer: zone_low - 0.5% hard floor',
        'entry validation: entry must touch zone',
    ],
    'metrics': {
        'old_immediate': {'wr': 47.6, 'rr': 0.71, 'cum_pnl': -7789.9, 'sl_rate': 38.3, 'per_trade': -0.94},
        'new_poi_retrace': {'wr': 54.7, 'rr': 0.84, 'cum_pnl': 197.4, 'sl_rate': 41.4, 'per_trade': 0.03},
        'improvement': {'wr_diff': 7.1, 'rr_diff': 0.13, 'cum_diff': 7987.3, 'per_trade_diff': 0.97}
    }
}

(V66_DIR / 'v66_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(f"Written: v66_report.json")

print(f"\n=== SYNC COMPLETE ===")
print(f"v66_picks.json: {len(v66_picks_new)} picks ({len(phase2_as_v66)} Phase 2 active)")
print(f"v66_trades.json: {len(v66_trades_new)} trades ({len(phase2_trades)} Phase 2 open)")
