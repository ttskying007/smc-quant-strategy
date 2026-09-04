# Self-Discovery & Auto-Fix Pattern (V20)

## Principle

The user expects the system to **discover problems before being told**. Every modification must trigger a cross-validation sweep across all affected dimensions.

## The RR Inversion Lesson (V20.5)

## V21 Self-Audit Additions (2026-05-18)

### Entry logic verification
After any entry logic change, verify every trade has:
- `conf_type` populated (not empty string)
- `retrace_bar` tracked (not -1)
- Entry price within zone: ≥60% of trades should be inside zone range

```python
confs = Counter(t.get('conf_type','') for t in trades)
assert confs.get('', 0) == 0, f"{confs.get('',0)} trades missing conf_type!"

in_zone = sum(1 for t in trades if t['cost_line']*0.98 <= t['entry_price'] <= t['cost_line']*1.02)
print(f"Entry within zone: {in_zone/len(trades)*100:.0f}%")
```

### max_age audit
When forking engine from older version, check max_age definition. V18 default 120 is too loose; V19 per-regime caps are correct.
```bash
grep -n "max_age" engine.py
```

### conf_type audit
Every trade must carry `conf_type`. Without it, impossible to diagnose which confirmation method works best.

### Live price API health
Hubble (43.167.234.49:3101) can go down silently. Always have Tencent (qt.gtimg.cn) fallback. Both wrapped in try/except, results accumulated.

**What happened**: Autopsy recommended two independent fixes:
1. "SL too tight" → `sl_initial_pct × 1.3`
2. "TP too low" → `tp_tiers last tier +20%`

Each was applied in isolation. Result: SL(6.5%) > TP1(4%) in 3 of 4 regimes → RR=0.5-0.6x → mathematical negative expectancy.

**User caught it**: "这个方案的盈亏比不够，甚至sl要比tp高的多"

**Root cause**: Cross-validation was missing. Fixing SL and TP independently without re-verifying their ratio.

## Mandatory Cross-Validation Checklist

After ANY parameter change, must verify:

| Change | Must Verify |
|--------|------------|
| SL modification | TP1/SL ratio ≥ 1.0 (target 1.5) |
| TP modification | Timeout rate ≤ 20% |
| max_age change | Trade count impact, zone_age distribution |
| Context filter change | v19_seq PnL correlation drift |
| Regime filter change | Per-regime WR and avgPnL |
| Signal window change | Sequence frequency shift |

## Auto-Fix Pipeline Pattern

```
Cron triggers → 
  1. Load latest backtest data
  2. Run diagnostic checklist:
     - RR check: for t in trades: TP1/SL < 1.0 → alert
     - SL rate: sl_hit / total > 5% → widen
     - Timeout rate: timeout / total > 20% → extend hold
     - Seq correlation: pnl_correlation.v19_seq < -1.0 → recalibrate
  3. Apply fixes → regenerate picks → restart frontend
  4. Log findings
```

## Quality Gates Before Delivery

1. Full backtest on all 4905 stocks (no sampling)
2. RR ≥ 1.0 on ALL trades (0 exceptions)
3. v19_seq PnL correlation ≥ -0.5
4. SL hit rate ≤ 3%
5. No unexplained losses (ctx_score ≥ 5 but lost)
6. All 7 frontend pages return 200

## User Feedback Signal Hierarchy

| Signal | Meaning | Response |
|--------|---------|----------|
| "为什么你没发现" | Expected proactive audit | Add to cross-validation checklist |
| "是不是还不完整" | Architecture gap suspected | Full-system audit, not targeted fix |
| "有没有继续迭代空间" | Current solution insufficient | Propose complete redesign |
| "全部核查排除" | Demand comprehensive audit | Run diagnostic on all dimensions |
