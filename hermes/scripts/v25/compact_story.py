#!/usr/bin/env python3
"""
V25.3b Compact SMC Story Synthesis
Reduces 10-signal ctx_seq to 3-4 essential SMC story beats:

Core SMC Patterns (3-4 signals):
  1. Sweep → CHOCH → Zone → Entry    (liquidity grab reversal)
  2. Sweep → BOS → Zone → Entry      (liquidity grab continuation)  
  3. CHOCH → Zone → Entry            (structure shift)
  4. BOS → Sweep → Zone → Entry      (BOS then liquidity test)
  5. Zone → Sweep → CHOCH → Entry    (zone sweep confirmation)

Priority filter: Sweep > CHOCH/BOS > Zone > Entry
Noise to discard: BPR, EQL, duplicate types, opposing-direction signals
"""
import json, sys
from pathlib import Path
from collections import defaultdict

# Essential structural signal types (in SMC story priority)
ESSENTIAL_TYPES = {
    'Sweep_BSL', 'Sweep_SSL',           # Liquidity sweep
    'CHOCH_Bull', 'CHOCH_Bear',         # Change of character
    'BOS_Bull', 'BOS_Bear',             # Break of structure
    'MSS_Bull', 'MSS_Bear',             # Market structure shift
    'LiquidityVoid',                     # Liquidity void
    'FVG_Bull', 'FVG_Bear',             # Fair value gap
    'OB_Bull', 'OB_Bear',               # Order block
    'BreakerBlock_Bull', 'BreakerBlock_Bear',  # Breaker
    'IFVG_Bull', 'IFVG_Bear',           # Inverted FVG
    'OTE_Bull', 'OTE_Bear',             # Optimal trade entry
    'Pinbar_Bull', 'Pinbar_Bear',       # Pinbar reversal
    'Rejection_Support', 'Rejection_Resistance',  # Rejection wick
}

# Noise types to always discard
NOISE_TYPES = {
    'BPR',          # Balanced price range — noise
    'EQL_High', 'EQL_Low',  # Equal highs/lows — noise
    'PO3_Acc', 'PO3_Man', 'PO3_DIS',  # Power of 3 — not structural
}

# SMC Story priority: higher = more important, appears earlier in story
SIGNAL_PRIORITY = {
    'Sweep_BSL': 1, 'Sweep_SSL': 1,
    'LiquidityVoid': 2,
    'CHOCH_Bull': 3, 'CHOCH_Bear': 3,
    'BOS_Bull': 4, 'BOS_Bear': 4,
    'MSS_Bull': 5, 'MSS_Bear': 5,
    'BreakerBlock_Bull': 6, 'BreakerBlock_Bear': 6,
    'IFVG_Bull': 7, 'IFVG_Bear': 7,
    'FVG_Bull': 8, 'FVG_Bear': 8,
    'OB_Bull': 9, 'OB_Bear': 9,
    'Rejection_Support': 10, 'Rejection_Resistance': 10,
    'OTE_Bull': 11, 'OTE_Bear': 11,
    'Pinbar_Bull': 12, 'Pinbar_Bear': 12,
}


def extract_direction(seq_parts):
    """Determine dominant direction: 'bull' or 'bear'"""
    bull_count = sum(1 for s in seq_parts if 'Bull' in s or 'BSL' in s)
    bear_count = sum(1 for s in seq_parts if 'Bear' in s or 'SSL' in s)
    return 'bull' if bull_count >= bear_count else 'bear'


def compact_story(ctx_seq, max_signals=4):
    """
    Reduce a long ctx_seq to a compact 3-4 signal SMC story.
    
    Input: "BPR→BPR→BreakerBlock_Bull→Sweep_BSL→OTE_Bull→IFVG_Bull→FVG_Bear→IFVG_Bear→BPR→BPR"
    Output: "Sweep_BSL → BreakerBlock_Bull → OTE_Bull"
    """
    if not ctx_seq:
        return ''
    
    parts = [p.strip() for p in ctx_seq.split('→') if p.strip()]
    
    # 1. Discard noise
    filtered = [p for p in parts if p not in NOISE_TYPES]
    if not filtered:
        return ' → '.join(parts[:max_signals])
    
    # 2. Determine dominant direction
    direction = extract_direction(filtered)
    
    # 3. Keep only signals matching the dominant direction
    direction_filtered = []
    for p in filtered:
        is_bull = 'Bull' in p or 'BSL' in p or 'LiquidityVoid' == p
        is_bear = 'Bear' in p or 'SSL' in p
        is_neutral = not is_bull and not is_bear
        
        if is_neutral:
            # Keep neutral structural signals (they apply to both directions)
            if p in ESSENTIAL_TYPES:
                direction_filtered.append(p)
        elif (direction == 'bull' and is_bull) or (direction == 'bear' and is_bear):
            direction_filtered.append(p)
    
    if len(direction_filtered) <= 1:
        direction_filtered = filtered  # Fallback
    
    # 4. Deduplicate: group Sweep types, BOS+MSS together, OTE+Pinbar together
    deduped = []
    for p in direction_filtered:
        base_type = p.replace('_Bull', '').replace('_Bear', '')
        
        # Normalize: Sweep_BSL and Sweep_SSL → 'Sweep'
        if base_type in ('Sweep_BSL', 'Sweep_SSL'):
            base_type = 'Sweep'
        # BOS and MSS → 'BOS'
        if base_type in ('BOS', 'MSS'):
            base_type = 'Structure'
        
        if deduped:
            prev = deduped[-1]
            prev_base = prev.replace('_Bull', '').replace('_Bear', '')
            if prev_base in ('Sweep_BSL', 'Sweep_SSL'):
                prev_base = 'Sweep'
            if prev_base in ('BOS', 'MSS'):
                prev_base = 'Structure'
            
            if base_type == prev_base:
                continue  # Skip same category
        deduped.append(p)
    
    # 5. Sort by SMC story priority (Sweep first, Entry last)
    deduped.sort(key=lambda s: SIGNAL_PRIORITY.get(s, 99))
    
    # 6. Keep only max_signals (ensure Sweep + CHOCH/BOS + Zone + Entry)
    if len(deduped) <= max_signals:
        final = deduped
    else:
        # Prioritize: always keep first Sweep, first CHOCH/BOS, first Zone, last Entry
        sweep = None
        structure = None
        zone = None
        entry = None
        
        for s in deduped:
            t = s.replace('_Bull', '').replace('_Bear', '')
            if sweep is None and t in ('Sweep_BSL', 'Sweep_SSL', 'LiquidityVoid'):
                sweep = s
            elif structure is None and t in ('CHOCH', 'BOS', 'MSS'):
                structure = s
            elif zone is None and t in ('FVG', 'OB', 'BreakerBlock', 'IFVG'):
                zone = s
            elif entry is None and t in ('OTE', 'Pinbar', 'Rejection_Support', 'Rejection_Resistance'):
                entry = s
        
        final = [s for s in [sweep, structure, zone, entry] if s is not None]
        
        # If we still have space, add remaining by priority
        remaining = [s for s in deduped if s not in final]
        for s in remaining[:max_signals - len(final)]:
            final.append(s)
            final.sort(key=lambda s: SIGNAL_PRIORITY.get(s, 99))
    
    # 7. Human-readable story
    story = ' → '.join(final)
    return story


def compact_all_picks(picks_path=None, output_path=None):
    """Compact all picks' ctx_seq to short SMC stories."""
    if picks_path is None:
        picks_path = '/root/.hermes/smc_opt_v25/v25_picks.json'
    if output_path is None:
        output_path = picks_path
    
    picks = json.loads(Path(picks_path).read_text())
    
    upgraded = 0
    for p in picks:
        old_seq = p.get('ctx_seq', '')
        new_story = compact_story(old_seq)
        
        if len(new_story.split('→')) < len(old_seq.split('→')):
            upgraded += 1
        
        p['ctx_seq'] = new_story
        p['detail'] = new_story
        p['story'] = new_story
    
    Path(output_path).write_text(json.dumps(picks, ensure_ascii=False, indent=2))
    
    # Stats
    from collections import Counter
    story_lens = Counter(len(p['ctx_seq'].split('→')) for p in picks)
    print(f"Compacted {upgraded}/{len(picks)} picks")
    print(f"Story lengths: {dict(sorted(story_lens.items()))}")
    
    # Show examples
    print("\nSample stories:")
    for p in picks[:8]:
        print(f"  {p['symbol']}: {p['ctx_seq']}")
    
    return picks


if __name__ == '__main__':
    compact_all_picks()
