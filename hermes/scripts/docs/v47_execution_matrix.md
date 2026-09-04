# V47 SMC Production Execution Matrix

Generated: 2026-05-26

## Completed before this phase

| Area | Status | Evidence |
|---|---|---|
| Rebuild not hung | DONE | V46.1 rebuild completed, output mtime 2026-05-26 10:52 |
| OB wave-turn top-level provenance | DONE | 153/153 OB trades have top-level wave_turn_label |
| Output contract P0 audit | DONE | `audit_v47_smc_system.py` p0_failures=[] |
| Trade bar executability audit | DONE | TRADE_FAILURES fixed to 0 via exit_price_final/open gap audit |
| Frontend V46.1 summary/picks/rejects/kline contract | DONE | APIs verified; Kline OB missing wave=0 |

## Open items to execute now

| ID | Task | Current evidence | Required completion condition |
|---|---|---|---|
| T1 | Productionize zone_mid/deeper retrace entry | avg_entry_zone_pos=0.99 | V47 candidate uses executable midpoint/deeper entry where touched; avg_entry_zone_pos materially < V46.1 |
| T2 | Productionize structural SL | avg_sl_dist_pct=3.984, fake_sl_rate=12.05 | SL based on raw zone / structural low with cap; fake_sl reduced without WR collapse |
| T3 | Productionize runner/liquidity exit | sold_early_rate=85.78, avg_mfe_capture=0.087 | exit_legs include runner/structure/liquidity logic; sold_early materially reduced, avg_pnl/RR improved |
| T4 | Pine-like FVG dedicated audit | generic lux audit fvgs=0, FVG bounds 262/262 | Separate FVG audit reports FVG source/bounds/touch/fill/invalid status |
| T5 | Wave BOS/CHOCH/MSS layer audit | Kline BOS/CHOCH/MSS wave-labeled=0 | Dedicated audit quantifies structure layer mismatch and/or V47 adds wave break fields |
| T6 | Full V47 rebuild | no newer production V47 output | `/root/.hermes/smc_opt_v47_candidate` full output + audit files |
| T7 | Frontend sync | V46.1 active only | Either V47 synced into frontend version map or explicitly kept offline candidate with verified files |

## Execution rule

Do not overwrite V46.1 production until V47 candidate passes full audit. V47 output goes to:

`/root/.hermes/smc_opt_v47_candidate/`
