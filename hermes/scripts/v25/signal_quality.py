#!/usr/bin/env python3
"""
V25.3 Signal Quality Scoring Engine
Scores every SMC trade setup on 4 dimensions:
  Z - Zone quality (what kind of zone, how strong)
  S - Signal sequence (Sweep→CHOCH→Zone→Retrace completeness)  
  C - Confirmation quality (entry confirmation type + confluence)
  M - Multi-TF resonance (Weekly + Daily + 60min alignment)

Combined: Elite(≥15) / Standard(10-14) / Speculative(5-9) / Reject(<5)
"""
import json, sys, os, re
from pathlib import Path
from collections import defaultdict, Counter
from typing import List, Dict, Tuple, Optional

sys.path.insert(0, '/root/.hermes/scripts')
sys.path.insert(0, '/root/.hermes/scripts/v11')

# ── Scoring Tables ──

# Zone quality: higher = better structural zone
ZONE_SCORES = {
    # Premium zones (smart money reversal points)
    'BreakerBlock_Bull': 7,  # Failed bear OB → strong bull support
    'BreakerBlock_Bear': 7,
    'IFVG_Bull': 6,          # Inverted FVG = strong demand
    'IFVG_Bear': 6,
    
    # Standard zones
    'FVG_Bull': 5,
    'FVG_Bear': 5,
    'OB_Bull': 4,
    'OB_Bear': 4,
    
    # Liquidity-based zones (weaker standalone)
    'LiquidityVoid': 3,
    'BPR_Bull': 4,           # Balanced Price Range
    'BPR_Bear': 4,
    
    # Rejection zones (needs confirmation)
    'Rejection_Support': 3,
    'Rejection_Resistance': 3,
    'OTE_Support': 3,
    'OTE_Resistance': 3,
    
    # Default
    'default': 4,
}

# Signal sequence quality multipliers
# Key: sequence pattern (regex-like keyword matching), value: bonus score
SEQUENCE_BONUS = {
    # Complete SMC setups
    'Sweep_CHOCH_Zone': 3,      # Liquidity sweep → CHOCH → Zone
    'CHOCH_Zone_Retrace': 2,    # CHOCH → Zone → Retrace
    'Sweep_CHOCH_Retrace': 3,   # Sweep → CHOCH → Retrace entry
    
    # Strong partial setups
    'CHOCH_MSS_Zone': 2,        # CHOCH → Market Structure Shift → Zone
    'Sweep_Zone': 1,            # Sweep → Zone (no CHOCH)
    'Zone_CHOCH': 1,            # Zone then CHOCH (retrospective)
    'BOS_Zone': 1,              # BOS confirmation → Zone
    
    # Confluence bonuses
    'Pinbar_at_Zone': 1,        # Pinbar exactly at zone boundary
    'OTE_at_Zone': 1,           # OTE level hitting zone
    'LiquidityVoid_Fill': 1,    # LV getting filled at zone
    'Rejection_at_Zone': 1,     # Rejection wick at zone
    
    # Penalties  
    'No_Sweep': -1,             # Missing liquidity sweep before entry
    'No_CHOCH': -1,             # No CHOCH/BOS confirmation
    'Isolated_Zone': -2,        # Zone with no surrounding structure
}

# Confirmation quality
CONF_SCORES = {
    'IDM_BOUNCE': 6,    # Inducement bounce
    'PB_BOUNCE': 5,     # Pullback bounce
    'REV_BOUNCE': 4,    # Reversal bounce
    'OTE_ENTRY': 5,     # Optimal trade entry zone hit
    'PINBAR_ENTRY': 5,  # Pinbar at zone
    'SWEEP_ENTRY': 6,   # Entry at liquidity sweep level
    'BREAKER_ENTRY': 7, # Entry at breaker block
    'default': 4,
}


def parse_signal_sequence(ctx_seq: str) -> Dict:
    """
    Parse a signal sequence string like:
    "Sweep_BSL→CHOCH→EQL_Low→OTE→BOS→IFVG"
    Returns structured analysis.
    """
    if not ctx_seq:
        return {'signals': [], 'has_sweep': False, 'has_choch': False, 
                'has_bos': False, 'has_zone': False, 'has_retrace': False,
                'has_pinbar': False, 'has_ote': False, 'has_lv': False,
                'has_mss': False, 'has_breaker': False, 'has_ifvg': False}
    
    parts = [p.strip() for p in ctx_seq.split('→') if p.strip()]
    
    result = {
        'signals': parts,
        'length': len(parts),
        'has_sweep': any('Sweep' in p or 'BSL' in p or 'SSL' in p for p in parts),
        'has_choch': any('CHOCH' in p for p in parts),
        'has_bos': any('BOS' in p for p in parts),
        'has_zone': any(p in ('FVG','FVG_Bull','FVG_Bear','OB','OB_Bull','OB_Bear',
                              'IFVG','IFVG_Bull','IFVG_Bear','BreakerBlock','BreakerBlock_Bull',
                              'BreakerBlock_Bear','BPR') or 'FVG' in p or 'OB' in p or 'Breaker' in p 
                        for p in parts),
        'has_retrace': any(p in ('OTE','IDM','PB_BOUNCE','IDM_BOUNCE','PB') or 'OTE' in p for p in parts),
        'has_pinbar': any('Pinbar' in p for p in parts),
        'has_ote': any('OTE' in p for p in parts),
        'has_lv': any('LiquidityVoid' in p for p in parts),
        'has_mss': any('MSS' in p for p in parts),
        'has_breaker': any('Breaker' in p for p in parts),
        'has_ifvg': any('IFVG' in p for p in parts),
        'has_eql': any('EQL' in p or 'EQH' in p for p in parts),
        'has_bpr': any('BPR' in p for p in parts),
        'has_rejection': any('Rejection' in p for p in parts),
        'has_po3': any('PO3' in p for p in parts),
    }
    return result


def score_signal_sequence(ctx_seq: str) -> Tuple[int, List[str]]:
    """
    Score signal sequence 0-10 based on SMC chain completeness.
    Returns (score, reasons)
    """
    parsed = parse_signal_sequence(ctx_seq)
    score = 5  # Base
    reasons = []
    
    # Liquidity sweep = the setup trigger (most important)
    if parsed['has_sweep']:
        score += 2
        reasons.append('Sweep(+2)')
    else:
        score -= 1
        reasons.append('NoSweep(-1)')
    
    # CHOCH/BOS = structural confirmation
    if parsed['has_choch']:
        score += 2
        reasons.append('CHOCH(+2)')
    elif parsed['has_bos']:
        score += 1
        reasons.append('BOS(+1)')
    else:
        score -= 1
        reasons.append('NoCHOCH(-1)')
    
    # MSS = market structure shift (stronger than CHOCH alone)
    if parsed['has_mss']:
        score += 1
        reasons.append('MSS(+1)')
    
    # Retrace/OTE = optimal entry zone
    if parsed['has_retrace'] or parsed['has_ote']:
        score += 1
        reasons.append('Retrace(+1)')
    
    # Confluence signals
    if parsed['has_pinbar']:
        score += 1
        reasons.append('Pinbar(+1)')
    if parsed['has_lv']:
        score += 1
        reasons.append('LV(+1)')
    if parsed['has_eql']:
        score += 1
        reasons.append('EQL(+1)')
    
    # Breaker/IFVG = higher quality zones
    if parsed['has_breaker']:
        score += 1
        reasons.append('Breaker(+1)')
    if parsed['has_ifvg']:
        score += 1
        reasons.append('IFVG(+1)')
    
    # Sequence length (more signals = more confirmation)
    if parsed['length'] >= 5:
        score += 1
        reasons.append(f'Len{parsed["length"]}(+1)')
    elif parsed['length'] <= 2:
        score -= 1
        reasons.append(f'Len{parsed["length"]}(-1)')
    
    # Rejection at zone = strong
    if parsed['has_rejection']:
        score += 1
        reasons.append('Rejection(+1)')
    
    return max(0, min(10, score)), reasons


def score_zone_quality(zone_type: str, zone_age: int = 0, 
                        detail: str = '', conf_type: str = '') -> Tuple[int, List[str]]:
    """Score zone quality 0-10."""
    reasons = []
    
    # Base zone score
    base = ZONE_SCORES.get(zone_type, ZONE_SCORES['default'])
    
    # Age adjustment: fresher zones are better, stale zones penalized
    if zone_age <= 5:
        age_bonus = 0  # Fresh is expected, not a bonus
    elif zone_age <= 10:
        age_bonus = 0
    elif zone_age <= 20:
        age_bonus = -1
        reasons.append('Aged(-1)')
    else:
        age_bonus = -2
        reasons.append('Stale(-2)')
    
    # Confirmation type bonus
    if conf_type == 'IDM_BOUNCE':
        conf_bonus = 1
        reasons.append('IDM(+1)')
    elif conf_type == 'PB_BOUNCE':
        conf_bonus = 0
    elif conf_type == 'REV_BOUNCE':
        conf_bonus = -1
        reasons.append('REV(-1)')
    else:
        conf_bonus = 0
    
    score = base + age_bonus + conf_bonus
    
    # Parse detail for additional signals
    parsed = parse_signal_sequence(detail)
    if parsed['has_breaker']:
        score += 1
        reasons.append('BreakerZone(+1)')
    if parsed['has_ifvg']:
        score += 1
        reasons.append('IFVGZone(+1)')
    
    return max(0, min(10, score)), reasons


def score_entry_confirmation(conf_type: str, detail: str = '') -> Tuple[int, List[str]]:
    """Score entry confirmation quality 0-10."""
    reasons = []
    
    base = CONF_SCORES.get(conf_type, CONF_SCORES['default'])
    reasons.append(f'{conf_type}({base})')
    
    # Additional confluence from signal sequence
    parsed = parse_signal_sequence(detail)
    score = base
    
    if parsed['has_ote']:
        score += 1
        reasons.append('OTE(+1)')
    if parsed['has_pinbar']:
        score += 1
        reasons.append('Pinbar(+1)')
    if parsed['has_lv']:
        score += 1
        reasons.append('LV(+1)')
    if parsed['has_sweep']:
        score += 1
        reasons.append('Sweep(+1)')
    
    return max(0, min(10, score)), reasons


def score_mtf_resonance(entry_date: str = '', regime: str = '') -> Tuple[int, List[str]]:
    """
    Score multi-timeframe resonance 0-10.
    Currently uses regime as proxy — full MTF requires weekly/60min kline data.
    """
    reasons = []
    
    # Regime-based scoring (proxy for MTF alignment)
    regime_scores = {
        'TREND_UP': 5,      # Strong bullish across timeframes
        'WEAK_UP': 3,       # Mild bullish
        'RANGE': 1,         # No clear direction
        'WEAK_DOWN': 3,     # Mild bearish
        'TREND_DOWN': 5,    # Strong bearish
    }
    
    score = regime_scores.get(regime, 4)
    reasons.append(f'Regime:{regime}({score})')
    
    return score, reasons


def compute_combined_quality(zone_score: int, seq_score: int, 
                              conf_score: int, mtf_score: int) -> Dict:
    """Compute combined quality tier and multiplier."""
    total = zone_score + seq_score + conf_score + mtf_score
    
    if total >= 15:
        tier = 'ELITE'
        position_mult = 1.5
        color = '#39d353'
    elif total >= 11:
        tier = 'STANDARD'
        position_mult = 1.0
        color = '#58a6ff'
    elif total >= 7:
        tier = 'SPECULATIVE'
        position_mult = 0.5
        color = '#d2991d'
    else:
        tier = 'REJECT'
        position_mult = 0
        color = '#f85149'
    
    return {
        'total': total,
        'tier': tier,
        'position_mult': position_mult,
        'color': color,
        'breakdown': {
            'zone': zone_score,
            'sequence': seq_score,
            'confirmation': conf_score,
            'mtf_resonance': mtf_score,
        }
    }


def score_all_picks(picks: List[Dict]) -> List[Dict]:
    """Score all picks with V25.3 quality metrics."""
    scored = []
    
    for p in picks:
        zone_type = p.get('zone_type', '')
        if not zone_type:
            detail = p.get('detail', p.get('ctx_seq', ''))
            zone_type = detail.split('→')[0].strip() if '→' in detail else 'FVG_Bull'
        
        detail = p.get('detail', p.get('ctx_seq', ''))
        conf_type = p.get('conf_type', 'IDM_BOUNCE')
        zone_age = p.get('zone_age', 0)
        regime = p.get('regime', 'WEAK_UP')
        entry_date = str(p.get('entry_date', ''))
        
        # Score each dimension
        zone_score, zone_reasons = score_zone_quality(zone_type, zone_age, detail, conf_type)
        seq_score, seq_reasons = score_signal_sequence(detail)
        conf_score, conf_reasons = score_entry_confirmation(conf_type, detail)
        mtf_score, mtf_reasons = score_mtf_resonance(entry_date, regime)
        
        quality = compute_combined_quality(zone_score, seq_score, conf_score, mtf_score)
        
        # Enhance pick
        enhanced = dict(p)
        enhanced.update({
            'v253_quality': quality['total'],
            'v253_tier': quality['tier'],
            'v253_position_mult': quality['position_mult'],
            'v253_breakdown': quality['breakdown'],
            'v253_zone_score': zone_score,
            'v253_seq_score': seq_score,
            'v253_conf_score': conf_score,
            'v253_mtf_score': mtf_score,
            'v253_zone_reasons': zone_reasons,
            'v253_seq_reasons': seq_reasons,
            'v253_conf_reasons': conf_reasons,
            'v253_mtf_reasons': mtf_reasons,
        })
        scored.append(enhanced)
    
    return scored


# ── Main ──

def run_v253_scoring(picks_path=None, output_dir=None):
    """Run V25.3 quality scoring on picks."""
    if picks_path is None:
        picks_path = '/root/.hermes/smc_opt_v25/v25_picks.json'
    if output_dir is None:
        output_dir = Path('/root/.hermes/smc_opt_v25')
    
    output_dir = Path(output_dir)
    
    picks = json.loads(Path(picks_path).read_text())
    print(f"Loaded {len(picks)} picks from {picks_path}")
    
    scored = score_all_picks(picks)
    
    # Sort by quality (highest first)
    scored.sort(key=lambda p: -p['v253_quality'])
    
    # Save
    out_path = output_dir / 'v253_scored_picks.json'
    out_path.write_text(json.dumps(scored, ensure_ascii=False, indent=2))
    print(f"\nSaved {len(scored)} scored picks to {out_path}")
    
    # Stats
    tiers = Counter(p['v253_tier'] for p in scored)
    print(f"\nQuality distribution:")
    for tier in ['ELITE', 'STANDARD', 'SPECULATIVE', 'REJECT']:
        n = tiers.get(tier, 0)
        pct = n / len(scored) * 100
        print(f"  {tier:12s}: {n:4d} ({pct:5.1f}%)")
    
    # Top picks
    print(f"\nTop 5 ELITE picks:")
    elite = [p for p in scored if p['v253_tier'] == 'ELITE']
    for p in elite[:5]:
        bd = p['v253_breakdown']
        detail = p.get('detail', '')
        print(f"  {p['symbol']}: Q={p['v253_quality']} Z={bd['zone']} S={bd['sequence']} "
              f"C={bd['confirmation']} M={bd['mtf_resonance']} | {detail[:60]}")
    
    # Dimension averages
    avg_z = sum(p['v253_zone_score'] for p in scored) / len(scored)
    avg_s = sum(p['v253_seq_score'] for p in scored) / len(scored)
    avg_c = sum(p['v253_conf_score'] for p in scored) / len(scored)
    avg_m = sum(p['v253_mtf_score'] for p in scored) / len(scored)
    print(f"\nAvg scores: Z={avg_z:.1f} S={avg_s:.1f} C={avg_c:.1f} M={avg_m:.1f} "
          f"Total={avg_z+avg_s+avg_c+avg_m:.1f}")
    
    return scored


if __name__ == '__main__':
    run_v253_scoring()
