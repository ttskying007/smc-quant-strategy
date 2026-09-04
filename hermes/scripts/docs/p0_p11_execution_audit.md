# P0-P11 SMC V47 Execution Audit

Generated: 2026-05-26

| Phase | Scope | Current status | Evidence | Required next action |
|---|---|---|---|---|
| P0 | Rebuild/output contract P0 | DONE | `audit_v47_smc_system.py` p0_failures=[] | keep regression audit |
| P1 | Signal definition matrix | DONE | `docs/smc_signal_audit_matrix_v47.md` | keep updated |
| P2 | OB wave-turn correctness | DONE for OB | 153/153 OB trades wave_turn_label; Kline OB missing wave=0 | keep regression audit |
| P3 | FVG pine-like correctness | DONE candidate | `audit_v47_pine_fvg.py`, v46/v47 failures={} | add to all-audit bundle |
| P4 | Sweep/MSS/BOS/CHOCH structure correctness | PARTIAL | `audit_v47_wave_structure.py`: 59 breaks, wave_labeled=0 | implement/audit wave break layer or keep blocked |
| P5 | Combination signal lifecycle | PARTIAL | V46.1 lifecycle exists; V47 candidate expanded recall hurt WR | V47.1 must preserve V46.1 kept gate |
| P6 | Entry production repair | CANDIDATE | V47 candidate avg_entry_zone_pos 0.583 vs V46 0.99 | V47.1 on V46 kept only |
| P7 | SL production repair | CANDIDATE | V47 fake SL 8.02 vs V46 12.05, but WR down | V47.1 on V46 kept only |
| P8 | Exit/RR production repair | CANDIDATE | V47 sold_early 49.03 vs V46 85.78, but WR down | V47.1 on V46 kept only |
| P9 | Full backtest + per-trade autopsy | PARTIAL | V46 and V47 candidate autopsies exist | run V47.1 full autopsy |
| P10 | Frontend/Kline/picks/replay sync | DONE for V46.1 only | APIs verified V46.1 | sync only if V47.1 passes gates |
| P11 | Productionization | NOT DONE | V47 candidate not promoted due WR/SL regression | produce V47.1 candidate and gate |

## Production gate for V47.1

V47.1 can replace V46.1 only if all pass:

- WR >= 80%
- SL rate <= 18%
- avg pnl >= 6.5% or total weighted improvement clear
- avg_entry_zone_pos < 0.75
- sold_early_rate < 55%
- fake_sl_rate <= 8.5%
- P0 audit failures = 0
- OB wave provenance = 100%
- FVG dedicated audit failures = 0
- frontend contract passes after sync
