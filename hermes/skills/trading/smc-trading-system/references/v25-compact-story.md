# V25.3b Signal Story Compacting

## Problem
V25 scan collected ALL signal types between zone formation and entry (including noise like BPR, EQL, PO3, opposing-direction IFVG), producing 10-signal chains:
`BPR→BPR→BreakerBlock_Bull→Sweep_BSL→OTE_Bull→IFVG_Bull→FVG_Bear→IFVG_Bear→BPR→BPR`

## User Correction
"序列数量过多了，我们一般最多三到四个，主要是思路：流动性扫除后出现的反转，然后突破了前后，价格回撤到兴趣点等这类的"

## Solution: compact_story()

### Core SMC Story Patterns (3-4 signals)
```
Sweep → CHOCH → BreakerBlock → OTE     (liquidity sweep → structure shift → breaker zone → entry)
CHOCH → MSS → FVG → OTE                (character change → market shift → FVG → entry)
BOS → BreakerBlock → OTE               (break of structure → breaker zone → entry)
BreakerBlock → OTE                     (breaker zone → entry, fast setup)
```

### Compacting Rules
1. Only collect STRUCTURAL signals: Sweep_BSL/SSL, CHOCH, BOS, MSS, LiquidityVoid
2. Discard NOISE: BPR, EQL_High/Low, PO3_Acc/Man/DIS, opposing-direction IFVG/FVG
3. Category dedup: Sweep_BSL+SSL merged to "Sweep", BOS+MSS merged to one slot
4. Always keep: Zone type → Entry confirmation (minimum story)
5. Expand window: look back 5 bars before zone (not just zone→entry) to catch prior Sweep/CHOCH
6. Human-readable names: strip _Bull/_Bear suffixes, ZONE_RETRACE → Retrace

### Implementation
- /root/.hermes/scripts/v25/compact_story.py — standalone compactor
- full_scan.py — integrated at source during scanning
- Key function: compact_story(ctx_seq, max_signals=4)
- Priority order: Sweep(1) > LQ_Void(2) > CHOCH(3) > BOS(4) > MSS(5) > Breaker(6) > IFVG(7) > FVG(8) > OB(9) > Rejection(10) > OTE(11) > Pinbar(12)

### Distribution (200 ELITE picks)
- 2-signal: ~150 (fast entry, zone→entry in 1-2 bars)
- 3-signal: ~25 (standard SMC)
- 4-signal: ~25 (complete SMC sequence)

### Trap: Collecting ALL Signals
Symptom: 10-signal noise chains with BPR/BPR/BPR repeating
Root cause: ctx_seq = '→'.join(s.type for s in zone_sigs[-10:]) — unfiltered collection
Fix: Filter to essential_intermediate set + category dedup + max 4 signals
Prevention: After any signal collection code change, run Counter(len(ctx_seq.split('→'))) to verify distribution