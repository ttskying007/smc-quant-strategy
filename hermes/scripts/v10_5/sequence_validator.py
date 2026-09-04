#!/usr/bin/env python3
# SMC V10.5 — Signal Sequence Validation Framework
"""
核心命题: 信号发生的时间顺序是否决定胜率？

验证方法: 穷举所有信号类型的排列组合，对每只股票回测，
统计每种序列的胜率/盈亏比/交易次数，找出最优序列模式。

序列类型 (按发生顺序):
  1. Sweep → CHOCH → FVG Retest → OB     (Gold 4步)
  2. Sweep → CHOCH → FVG Retest            (Gold 3步)  
  3. CHOCH → FVG Retest → OB              (Silver 3步)
  4. Sweep → FVG Retest → OB               (Silver 3步)
  5. Sweep → CHOCH                         (Bronze 2步)
  6. CHOCH → FVG Retest                    (Bronze 2步)
  7. Sweep → FVG Retest                    (Bronze 2步)
  ... 共64种理论组合 (4种信号 × 有无的顺序排列)

关键指标:
  - 每种序列的 WR (胜率)
  - 每种序列的 RR_avg (平均盈亏比)
  - 每种序列的 PF (盈亏因子)
  - 每种序列的 N_trades (交易数)
  - 序列完整度的影响 (2步 vs 3步 vs 4步)

输出: 排序后的序列性能矩阵 → 找出最佳入场组合
"""

import json, math, logging, time
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from collections import defaultdict
from itertools import combinations, permutations
from dataclasses import dataclass, field

log = logging.getLogger('smc_v10_5.sequence_validator')


# ═══════════════════════════════════════════════════════════════════════
# Sequence definitions
# ═══════════════════════════════════════════════════════════════════════

SIGNAL_ATOMS = {
    'SwD': {'type': 'SweepDown', 'direction': 'bull', 'desc': 'SSL扫荡'},
    'SwU': {'type': 'SweepUp', 'direction': 'bear', 'desc': 'BSL扫荡'},
    'ChB': {'type': 'CHOCH_Bull', 'direction': 'bull', 'desc': '看涨CHOCH'},
    'ChS': {'type': 'CHOCH_Bear', 'direction': 'bear', 'desc': '看跌CHOCH'},
    'FvB': {'type': 'FVG_Bull_Retest', 'direction': 'bull', 'desc': '看涨FVG回测'},
    'FvS': {'type': 'FVG_Bear_Retest', 'direction': 'bear', 'desc': '看跌FVG回测'},
    'ObB': {'type': 'OB_Bull_Confirm', 'direction': 'bull', 'desc': '看涨OB确认'},
    'ObS': {'type': 'OB_Bear_Confirm', 'direction': 'bear', 'desc': '看跌OB确认'},
    'RjB': {'type': 'Rejection_Support', 'direction': 'bull', 'desc': '支撑拒绝'},
    'RjS': {'type': 'Rejection_Resistance', 'direction': 'bear', 'desc': '阻力拒绝'},
}

# Pre-defined sequences to test (max 4 steps)
PREDEFINED_SEQUENCES = {
    # ── LONG sequences ──
    'L_GOLD4': {
        'atoms': ['SwD', 'ChB', 'FvB', 'ObB'],
        'min_atoms': 4,
        'direction': 'bull',
        'name': 'Long Gold 4-step',
        'desc': 'SSL扫荡→看涨CHOCH→FVG回测→OB确认',
        'tier': 'gold',
    },
    'L_GOLD3a': {
        'atoms': ['SwD', 'ChB', 'FvB'],
        'min_atoms': 3,
        'direction': 'bull',
        'name': 'Long Gold 3-step (no OB)',
        'desc': 'SSL扫荡→看涨CHOCH→FVG回测',
        'tier': 'gold',
    },
    'L_GOLD3b': {
        'atoms': ['SwD', 'ChB', 'ObB'],
        'min_atoms': 3,
        'direction': 'bull',
        'name': 'Long Gold 3-step (no FVG)',
        'desc': 'SSL扫荡→看涨CHOCH→OB确认',
        'tier': 'gold',
    },
    'L_SILVER3': {
        'atoms': ['ChB', 'FvB', 'ObB'],
        'min_atoms': 3,
        'direction': 'bull',
        'name': 'Long Silver 3-step',
        'desc': '看涨CHOCH→FVG回测→OB确认',
        'tier': 'silver',
    },
    'L_SILVER2a': {
        'atoms': ['SwD', 'ChB'],
        'min_atoms': 2,
        'direction': 'bull',
        'name': 'Long Silver Sweep+CHOCH',
        'desc': 'SSL扫荡→看涨CHOCH',
        'tier': 'silver',
    },
    'L_SILVER2b': {
        'atoms': ['ChB', 'FvB'],
        'min_atoms': 2,
        'direction': 'bull',
        'name': 'Long Silver CHOCH+FVG',
        'desc': '看涨CHOCH→FVG回测',
        'tier': 'silver',
    },
    'L_SILVER2c': {
        'atoms': ['SwD', 'FvB'],
        'min_atoms': 2,
        'direction': 'bull',
        'name': 'Long Silver Sweep+FVG',
        'desc': 'SSL扫荡→FVG回测',
        'tier': 'silver',
    },
    'L_BRONZE2a': {
        'atoms': ['SwD', 'ObB'],
        'min_atoms': 2,
        'direction': 'bull',
        'name': 'Long Bronze Sweep+OB',
        'desc': 'SSL扫荡→OB确认',
        'tier': 'bronze',
    },
    'L_BRONZE2b': {
        'atoms': ['ChB', 'ObB'],
        'min_atoms': 2,
        'direction': 'bull',
        'name': 'Long Bronze CHOCH+OB',
        'desc': '看涨CHOCH→OB确认',
        'tier': 'bronze',
    },
    
    # ── SHORT sequences ──
    'S_GOLD4': {
        'atoms': ['SwU', 'ChS', 'FvS', 'ObS'],
        'min_atoms': 4,
        'direction': 'bear',
        'name': 'Short Gold 4-step',
        'desc': 'BSL扫荡→看跌CHOCH→FVG回测→OB确认',
        'tier': 'gold',
    },
    'S_GOLD3a': {
        'atoms': ['SwU', 'ChS', 'FvS'],
        'min_atoms': 3,
        'direction': 'bear',
        'name': 'Short Gold 3-step (no OB)',
        'desc': 'BSL扫荡→看跌CHOCH→FVG回测',
        'tier': 'gold',
    },
    'S_SILVER3': {
        'atoms': ['ChS', 'FvS', 'ObS'],
        'min_atoms': 3,
        'direction': 'bear',
        'name': 'Short Silver 3-step',
        'desc': '看跌CHOCH→FVG回测→OB确认',
        'tier': 'silver',
    },
    'S_SILVER2a': {
        'atoms': ['SwU', 'ChS'],
        'min_atoms': 2,
        'direction': 'bear',
        'name': 'Short Silver Sweep+CHOCH',
        'desc': 'BSL扫荡→看跌CHOCH',
        'tier': 'silver',
    },
    'S_SILVER2b': {
        'atoms': ['ChS', 'FvS'],
        'min_atoms': 2,
        'direction': 'bear',
        'name': 'Short Silver CHOCH+FVG',
        'desc': '看跌CHOCH→FVG回测',
        'tier': 'silver',
    },
    'S_SILVER2c': {
        'atoms': ['SwU', 'FvS'],
        'min_atoms': 2,
        'direction': 'bear',
        'name': 'Short Silver Sweep+FVG',
        'desc': 'BSL扫荡→FVG回测',
        'tier': 'silver',
    },
    
    # ── Single signals (baseline) ──
    'L_SINGLE_Sw': {'atoms': ['SwD'], 'min_atoms': 1, 'direction': 'bull', 'name': 'Sweep only', 'tier': 'single'},
    'L_SINGLE_Fv': {'atoms': ['FvB'], 'min_atoms': 1, 'direction': 'bull', 'name': 'FVG only', 'tier': 'single'},
    'L_SINGLE_Ob': {'atoms': ['ObB'], 'min_atoms': 1, 'direction': 'bull', 'name': 'OB only', 'tier': 'single'},
    'S_SINGLE_Sw': {'atoms': ['SwU'], 'min_atoms': 1, 'direction': 'bear', 'name': 'Sweep only', 'tier': 'single'},
    'S_SINGLE_Fv': {'atoms': ['FvS'], 'min_atoms': 1, 'direction': 'bear', 'name': 'FVG only', 'tier': 'single'},
    'S_SINGLE_Ob': {'atoms': ['ObS'], 'min_atoms': 1, 'direction': 'bear', 'name': 'OB only', 'tier': 'single'},
}


# ═══════════════════════════════════════════════════════════════════════
# Signal normalization
# ═══════════════════════════════════════════════════════════════════════

def normalize_signals_to_atoms(signals: List[Dict]) -> List[Dict]:
    """Convert raw signals to atom tokens for sequence matching."""
    atoms = []
    
    type_map = {
        'SweepDown': 'SwD', 'SweepUp': 'SwU',
        'CHOCH_Bull': 'ChB', 'CHOCH_Bear': 'ChS',
        'MSB_Up': 'ChB', 'MSB_Down': 'ChS',
        'FVG_Bull': 'FvB', 'FVG_Bear': 'FvS',
        'BPR_Bull': 'FvB', 'BPR_Bear': 'FvS',
        'IFVG': 'FvS',
        'OB_Bull': 'ObB', 'OB_Bear': 'ObS',
        'Rejection_Support': 'RjB', 'Rejection_Resistance': 'RjS',
        'LiquidityVoid': None,
    }
    
    for sig in signals:
        sig_type = sig.get('type', '')
        atom = type_map.get(sig_type)
        
        if atom:
            direction = sig.get('direction', '')
            # Only include if direction matches atom
            atom_info = SIGNAL_ATOMS.get(atom, {})
            if atom_info.get('direction') == direction or atom in ('FvB', 'FvS', 'ObB', 'ObS'):
                atoms.append({
                    'atom': atom,
                    'idx': sig.get('idx', 0),
                    'price': sig.get('price', sig.get('upper', sig.get('lower', 0))),
                    'direction': direction,
                    'original': sig,
                })
    
    # Sort by index
    atoms.sort(key=lambda a: a['idx'])
    return atoms


# ═══════════════════════════════════════════════════════════════════════
# Sequence matching
# ═══════════════════════════════════════════════════════════════════════

def match_sequence(atoms: List[Dict], seq_def: Dict, max_gap=8) -> Optional[List[int]]:
    """Check if a predefined sequence appears in the atom list.
    
    Returns list of indices in atoms list if matched, None otherwise.
    """
    seq_atoms = seq_def['atoms']
    min_atoms = seq_def.get('min_atoms', len(seq_atoms))
    
    if len(atoms) < min_atoms:
        return None
    
    # Greedy subsequence match
    atom_idx = 0
    matched_indices = []
    
    for target_atom in seq_atoms:
        while atom_idx < len(atoms):
            if atoms[atom_idx]['atom'] == target_atom:
                # Check gap from previous match
                if matched_indices:
                    prev = atoms[matched_indices[-1]]
                    curr = atoms[atom_idx]
                    if curr['idx'] - prev['idx'] > max_gap:
                        return None  # too far apart
                matched_indices.append(atom_idx)
                atom_idx += 1
                break
            atom_idx += 1
        else:
            # Didn't find this atom
            break
    
    if len(matched_indices) >= min_atoms:
        return matched_indices
    
    return None


# ═══════════════════════════════════════════════════════════════════════
# Sequence backtest
# ═══════════════════════════════════════════════════════════════════════

def backtest_sequence(ohlcv, atoms, seq_def, 
                      sl_pct=3.0, tp_pct=9.0, max_hold=40) -> Dict:
    """Backtest a specific sequence pattern.
    
    For each match, enter at the last signal's next bar open,
    exit at SL/TP or after max_hold bars.
    """
    matches = []
    atom_idx = 0
    max_gap = 8
    
    while atom_idx < len(atoms):
        result = match_sequence(atoms[atom_idx:], seq_def, max_gap)
        if result:
            # Adjust indices relative to start
            real_indices = [atom_idx + r for r in result]
            matches.append(real_indices)
            # Skip to after the match
            atom_idx = real_indices[-1] + 1
        else:
            atom_idx += 1
    
    if not matches:
        return {'n': 0, 'wins': 0, 'losses': 0, 'wr': 0, 'rr_avg': 0, 
                'pf': 0, 'returns': [], 'matches': 0}
    
    n = len(ohlcv)
    is_bull = seq_def['direction'] == 'bull'
    trades = []
    
    for match in matches:
        # Entry: next bar after last signal
        last_signal_idx = atoms[match[-1]]['idx']
        entry_idx = last_signal_idx + 1
        if entry_idx >= n - 2:
            continue
        
        entry = ohlcv[entry_idx]['o']
        
        # SL/TP
        if is_bull:
            sl = entry * (1 - sl_pct / 100)
            tp = entry * (1 + tp_pct / 100)
        else:
            sl = entry * (1 + sl_pct / 100)
            tp = entry * (1 - tp_pct / 100)
        
        # Simulate exit
        hit_sl = hit_tp = False
        exit_price = entry
        exit_idx = entry_idx
        max_look = min(entry_idx + max_hold, n)
        
        for j in range(entry_idx + 1, max_look):
            bar = ohlcv[j]
            if is_bull:
                if bar['l'] <= sl:
                    hit_sl, exit_price, exit_idx = True, sl, j
                    break
                if bar['h'] >= tp:
                    hit_tp, exit_price, exit_idx = True, tp, j
                    break
            else:
                if bar['h'] >= sl:
                    hit_sl, exit_price, exit_idx = True, sl, j
                    break
                if bar['l'] <= tp:
                    hit_tp, exit_price, exit_idx = True, tp, j
                    break
        
        ret = (exit_price - entry) / entry * 100
        if not is_bull:
            ret = -ret
        
        trades.append({
            'entry': round(entry, 2),
            'exit': round(exit_price, 2),
            'ret': round(ret, 2),
            'win': ret > 0,
            'hit_tp': hit_tp,
            'hit_sl': hit_sl,
            'bars_held': exit_idx - entry_idx,
        })
    
    n_trades = len(trades)
    wins = sum(1 for t in trades if t['win'])
    returns = [t['ret'] for t in trades]
    
    wr = wins / n_trades * 100 if n_trades > 0 else 0
    rr_avg = tp_pct / sl_pct  # theoretical; actual varies
    
    gross_win = sum(r for r in returns if r > 0)
    gross_loss = abs(sum(r for r in returns if r <= 0))
    pf = gross_win / gross_loss if gross_loss > 0 else 99
    
    return {
        'n': n_trades,
        'wins': wins,
        'losses': n_trades - wins,
        'wr': round(wr, 1),
        'rr_avg': round(rr_avg, 2),
        'pf': round(pf, 2),
        'returns': returns,
        'matches': len(matches),
        'avg_bars_held': round(sum(t['bars_held'] for t in trades) / n_trades, 1) if n_trades > 0 else 0,
    }


# ═══════════════════════════════════════════════════════════════════════
# Comprehensive sequence validation
# ═══════════════════════════════════════════════════════════════════════

def validate_all_sequences(ohlcv, atoms, sl_pct=3.0, tp_pct=9.0) -> Dict:
    """Test ALL predefined sequences and rank by performance.
    
    Returns:
        {
            'rankings': sorted list of (seq_name, seq_result),
            'best_long': best long sequence,
            'best_short': best short sequence,
            'by_tier': {tier: avg_wr},
            'by_steps': {n_steps: avg_wr},
        }
    """
    results = {}
    
    for seq_name, seq_def in PREDEFINED_SEQUENCES.items():
        result = backtest_sequence(ohlcv, atoms, seq_def, sl_pct, tp_pct)
        result['seq_name'] = seq_name
        result['seq_def'] = seq_def
        results[seq_name] = result
    
    # Rank by WR (descending)
    # Prefer sequences with more trades (N > 2)
    rankings = sorted(
        [(name, r) for name, r in results.items()],
        key=lambda x: (x[1]['wr'] if x[1]['n'] >= 3 else 0, x[1]['n']),
        reverse=True,
    )
    
    # Best per direction
    best_long = max(
        [(name, r) for name, r in results.items() if r.get('seq_def', {}).get('direction') == 'bull' and r['n'] >= 2],
        key=lambda x: (x[1]['wr'], x[1]['n']),
        default=(None, None),
    )
    
    best_short = max(
        [(name, r) for name, r in results.items() if r.get('seq_def', {}).get('direction') == 'bear' and r['n'] >= 2],
        key=lambda x: (x[1]['wr'], x[1]['n']),
        default=(None, None),
    )
    
    # By tier
    by_tier = defaultdict(lambda: {'total_wr': 0, 'count': 0, 'total_n': 0})
    for name, r in results.items():
        tier = r.get('seq_def', {}).get('tier', 'unknown')
        if r['n'] > 0:
            by_tier[tier]['total_wr'] += r['wr'] * r['n']
            by_tier[tier]['total_n'] += r['n']
            by_tier[tier]['count'] += 1
    
    tier_stats = {}
    for tier, data in by_tier.items():
        tier_stats[tier] = {
            'avg_wr': round(data['total_wr'] / data['total_n'], 1) if data['total_n'] > 0 else 0,
            'total_n': data['total_n'],
            'count': data['count'],
        }
    
    # By number of steps
    by_steps = defaultdict(lambda: {'total_wr': 0, 'count': 0, 'total_n': 0})
    for name, r in results.items():
        steps = len(r.get('seq_def', {}).get('atoms', []))
        if r['n'] > 0:
            by_steps[steps]['total_wr'] += r['wr'] * r['n']
            by_steps[steps]['total_n'] += r['n']
            by_steps[steps]['count'] += 1
    
    step_stats = {}
    for steps, data in by_steps.items():
        step_stats[steps] = {
            'avg_wr': round(data['total_wr'] / data['total_n'], 1) if data['total_n'] > 0 else 0,
            'total_n': data['total_n'],
            'count': data['count'],
        }
    
    return {
        'rankings': rankings,
        'best_long': best_long,
        'best_short': best_short,
        'by_tier': tier_stats,
        'by_steps': step_stats,
    }


# ═══════════════════════════════════════════════════════════════════════
# Cross-stock sequence aggregation
# ═══════════════════════════════════════════════════════════════════════

def aggregate_cross_stock(stock_results: Dict[str, Dict]) -> Dict:
    """Aggregate sequence validation results across multiple stocks.
    
    This gives us the statistically robust answer:
    Which signal sequence has the highest WR across the entire market?
    """
    cross = defaultdict(lambda: {
        'total_n': 0, 'total_wins': 0, 'total_losses': 0,
        'all_returns': [], 'stock_count': 0,
        'tier': '', 'direction': '',
    })
    
    for symbol, result in stock_results.items():
        rankings = result.get('rankings', [])
        
        for seq_name, seq_result in rankings:
            c = cross[seq_name]
            c['total_n'] += seq_result.get('n', 0)
            c['total_wins'] += seq_result.get('wins', 0)
            c['total_losses'] += seq_result.get('losses', 0)
            c['all_returns'].extend(seq_result.get('returns', []))
            c['stock_count'] += 1
            if not c['tier']:
                c['tier'] = seq_result.get('seq_def', {}).get('tier', '')
                c['direction'] = seq_result.get('seq_def', {}).get('direction', '')
    
    # Compute aggregate stats
    aggregated = {}
    for seq_name, c in cross.items():
        n = c['total_n']
        if n < 5:  # minimum sample size
            continue
        
        wr = c['total_wins'] / n * 100
        returns = c['all_returns']
        
        gross_win = sum(r for r in returns if r > 0)
        gross_loss = abs(sum(r for r in returns if r <= 0))
        pf = gross_win / gross_loss if gross_loss > 0 else 99
        
        avg_ret = sum(returns) / len(returns) if returns else 0
        
        aggregated[seq_name] = {
            'n': n,
            'wins': c['total_wins'],
            'losses': c['total_losses'],
            'wr': round(wr, 1),
            'pf': round(pf, 2),
            'avg_ret': round(avg_ret, 2),
            'stock_count': c['stock_count'],
            'tier': c['tier'],
            'direction': c['direction'],
            'desc': PREDEFINED_SEQUENCES.get(seq_name, {}).get('desc', ''),
        }
    
    # Sort by WR
    ranked = sorted(aggregated.items(), key=lambda x: (x[1]['wr'], x[1]['n']), reverse=True)
    
    return {
        'ranked_sequences': ranked,
        'total_stocks_tested': len(stock_results),
    }


# ═══════════════════════════════════════════════════════════════════════
# Sequence visualization
# ═══════════════════════════════════════════════════════════════════════

def format_sequence_report(agg_result: Dict) -> str:
    """Format cross-stock sequence validation as readable report."""
    ranked = agg_result.get('ranked_sequences', [])
    total_stocks = agg_result.get('total_stocks_tested', 0)
    
    lines = [
        f"",
        f"╔══════════════════════════════════════════════════════════╗",
        f"║   信号序列验证报告 — {total_stocks}只股票跨市场汇总      ║",
        f"╚══════════════════════════════════════════════════════════╝",
        f"",
        f"  {'排名':<4} {'序列':<18} {'层级':<8} {'方向':<6} {'交易数':<8} {'WR':<8} {'PF':<8} {'描述'}",
        f"  {'-'*4} {'-'*18} {'-'*8} {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*40}",
    ]
    
    for i, (name, data) in enumerate(ranked[:20]):
        tier = data.get('tier', '?')
        direction = '多' if data.get('direction') == 'bull' else ('空' if data.get('direction') == 'bear' else '?')
        desc = data.get('desc', '')
        
        wr_color = '🟢' if data['wr'] >= 70 else ('🟡' if data['wr'] >= 55 else '🔴')
        
        lines.append(
            f"  {i+1:<4} {name:<18} {tier:<8} {direction:<6} "
            f"{data['n']:<8} {wr_color}{data['wr']}%{'':<4} "
            f"{data['pf']:<8.2f} {desc}"
        )
    
    # Summary by tier
    lines.append(f"")
    lines.append(f"  层级汇总:")
    tiers = defaultdict(lambda: {'n': 0, 'total_wr': 0, 'count': 0})
    for name, data in ranked:
        tier = data.get('tier', '?')
        tiers[tier]['n'] += data['n']
        tiers[tier]['total_wr'] += data['wr'] * data['n']
        tiers[tier]['count'] += 1
    
    tier_order = ['gold', 'silver', 'bronze', 'single']
    for tier in tier_order:
        if tier in tiers:
            t = tiers[tier]
            avg_wr = t['total_wr'] / t['n'] if t['n'] > 0 else 0
            lines.append(f"    {tier:8s}: {t['count']:2d}序列, {t['n']:4d}笔交易, avg WR={avg_wr:.1f}%")
    
    lines.append(f"")
    return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════════
# Quick test runner
# ═══════════════════════════════════════════════════════════════════════

def validate_one_stock(symbol: str, ohlcv: List[Dict], signals: List[Dict],
                       sl_pct=3.0, tp_pct=9.0) -> Dict:
    """Run full sequence validation on one stock."""
    atoms = normalize_signals_to_atoms(signals)
    
    if len(atoms) < 2:
        return {'error': 'too few atoms', 'n_atoms': len(atoms)}
    
    result = validate_all_sequences(ohlcv, atoms, sl_pct, tp_pct)
    result['symbol'] = symbol
    result['n_atoms'] = len(atoms)
    result['n_signals'] = len(signals)
    
    return result
