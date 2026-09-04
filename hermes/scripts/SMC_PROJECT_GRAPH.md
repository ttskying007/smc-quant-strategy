# SMC Project Full Graph (v2)

**593 Python files, 143770 LOC**

## SMC Version Evolution

| Version | Files | LOC | Signal Density | Key Files |
|---------|-------|-----|----------------|-----------|
| Root | 117 | 18294 | 3.4/file | smc_unified.py, daily_multi_source_crawler.py, smc_auto_optimizer.py |
| V10.5 | 2 | 981 | 32.5/file | signals.py, sequence_validator.py |
| V2 | 6 | 2639 | 3.7/file | smc_trade_viewer_v2.py, smc_api_v2.py, smc_optimizer_v2.py |
| V3 | 14 | 4129 | 5.2/file | smc_trade_viewer_v3.py, proxy_guardian_v3.py, smc_engine_v3.py |
| V4 | 16 | 3298 | 3.1/file | smc_engine_v4.py, smc_optimizer_v4.py, smc_dashboard_v4.py |
| V5 | 6 | 1972 | 7.8/file | smc_engine_v5.py, smc_optimizer_v5_v2.py, smc_optimizer_v5.py |
| V6 | 3 | 1290 | 3.7/file | smc_engine_v6.py, v6_module.py, proxy_guardian_v6.py |
| V7 | 7 | 2993 | 1.9/file | smc_engine_v7.py, smc_engine_v7_plus.py, v7_module.py |
| V8 | 4 | 1655 | 2.8/file | smc_engine_v8.py, proxy_guardian_v8_fixed.py, smc_optimizer_v8.py |
| V9 | 8 | 2474 | 7.4/file | smc_watchlist.py, smc_backtest.py, smc_annotations.py |
| V10 | 9 | 2765 | 7.1/file | smc_webui_v10.py, swing_points.py, smc_backtest_v10.py |
| V11 | 320 | 80404 | 7.9/file | signals_v11.py, signals_vPine.py, signals_v11_backup_v37.py |
| V12 | 1 | 440 | 2.0/file | backtest_v12.py |
| V13 | 3 | 412 | 0.0/file | backtest_v13.py, analyze_v13.py, merge_v13.py |
| V14 | 6 | 802 | 2.3/file | backtest_v14.py, v14_viewer.py, analyze_v14_full.py |
| V15 | 1 | 156 | 11.0/file | v15_viewer.py |
| V16 | 1 | 148 | 11.0/file | v16_viewer.py |
| V17 | 1 | 205 | 14.0/file | v17_viewer.py |
| V18 | 1 | 148 | 4.0/file | v18_dashboard.py |
| V19 | 1 | 278 | 3.0/file | smc_unified_v19.py |
| V24 | 1 | 59 | 9.0/file | full_review_v24_v34.py |
| V25 | 2 | 570 | 2.0/file | engine_v25.py, backtest_v25.py |
| V26 | 3 | 1207 | 3.3/file | v26_engine.py, engine_v26.py, v26_analysis.py |
| V27 | 3 | 1494 | 27.0/file | smc_core_v27.py, v27_full_scan.py, v27_adapter.py |
| V28 | 3 | 962 | 3.0/file | smc_diagnostics_v28.py, smc_core_v28.py, v28_full_scan.py |
| V29 | 2 | 198 | 0.5/file | v29_full_scan.py, smc_core_v29.py |
| V30 | 1 | 164 | 7.0/file | v30_full_scan.py |
| V31 | 2 | 337 | 9.5/file | v31_full_scan.py, v31_audit.py |
| V33 | 3 | 488 | 4.7/file | v33_engine.py, v33_audit_export.py, smc_batch_v33.py |
| V34 | 6 | 694 | 6.8/file | v34_engine.py, smc_core_luxalgo_v34.py, v34_funnel_audit.py |
| V35 | 4 | 822 | 13.2/file | v35_adaptive.py, v35_engine.py, p2_p4_diagnostics_v35.py |
| V36 | 1 | 337 | 40.0/file | v36_engine.py |
| V38 | 2 | 687 | 7.0/file | smc_live_monitor_v38.py, multi_tf_v38_test.py |
| V39 | 1 | 200 | 4.0/file | v39_prototype.py |
| V53 | 2 | 646 | 2.0/file | smc_engine_v53.py, smc_optimizer_v53.py |
| V54 | 4 | 1151 | 1.5/file | smc_engine_v54.py, smc_webui_v54.py, smc_web_status_api_v54.py |
| V55 | 4 | 864 | 1.2/file | smc_optimizer_v55.py, smc_v55.py, smc_opt_v55.py |
| V61 | 7 | 1717 | 1.4/file | smc_engine_v61.py, run_ga_v61_v3.py, gen_v61_signals.py |
| V62 | 2 | 224 | 0.0/file | smc_engine_v62.py, gen_v62_signals.py |
| V82 | 3 | 1317 | 2.0/file | smc_engine_v82.py, smc_optimizer_v82.py, smc_web_status_api_v82.py |
| V83 | 3 | 2042 | 3.3/file | smc_optimizer_v83.py, smc_engine_v83.py, smc_web_status_api_v83.py |
| V84 | 2 | 890 | 2.0/file | smc_engine_v84.py, smc_optimizer_v84.py |
| V85 | 1 | 214 | 0.0/file | smc_optimizer_v85.py |
| V116 | 2 | 427 | 0.5/file | backtest_v116_full.py, merge_v116.py |
| V251 | 1 | 222 | 6.0/file | backtest_v251.py |
| V258 | 1 | 354 | 0.0/file | v258_backtest.py |

## Top 20 Largest Modules

### smc_unified.py (2749 LOC [Root])
- Classes: Handler
- Functions: load_json, is_winner, exit_key, exit_label, _date_key
- SMC: FVG=13 OB=18 Struct=25 Liq=8

### v11/signals_v11.py (1738 LOC [V11])
- Classes: Signal
- Functions: calc_adaptive_thresholds, detect_fvg_v11, _classify_fvg_width, _check_trend_alignment, _calc_fvg_strength
- SMC: FVG=31 OB=12 Struct=5 Liq=0

### v11/signals_vPine.py (1663 LOC [V11])
- Classes: Signal
- Functions: calc_adaptive_thresholds, detect_swings_vPine, detect_swings_internal, _classify_fvg_width, _check_trend_alignment
- SMC: FVG=10 OB=22 Struct=13 Liq=3

### v11/signals_v11_backup_v37.py (1573 LOC [V11])
- Classes: Signal
- Functions: calc_adaptive_thresholds, detect_fvg_v11, _classify_fvg_width, _check_trend_alignment, _calc_fvg_strength
- SMC: FVG=16 OB=13 Struct=6 Liq=0

### smc_trade_viewer_v3.py (1417 LOC [V3])
- Classes: Handler
- Functions: format_date, load_ohlcv, load_60min_ohlcv, short_sig_label, compute_sl_tp_from_signals
- SMC: FVG=9 OB=5 Struct=6 Liq=0

### v11/signals_v12.py (1270 LOC [V11])
- Classes: Signal
- Functions: calc_adaptive_thresholds, detect_swings_v12, detect_swings_v13_60min, _quick_sh, _quick_sl
- SMC: FVG=8 OB=24 Struct=12 Liq=1

### v11/v44_engine_a.py (1227 LOC [V11])
- Classes: RetestEntry
- Functions: load_ohlcv, short_trend, calc_atr, find_best_swing_sl, detect_market_phase
- SMC: FVG=5 OB=11 Struct=0 Liq=0

### v11/v44_engine_b.py (1207 LOC [V11])
- Classes: RetestEntry
- Functions: load_ohlcv, short_trend, calc_atr, find_best_swing_sl, detect_market_phase
- SMC: FVG=5 OB=11 Struct=0 Liq=0

### v11/v44_engine.py (1207 LOC [V11])
- Classes: RetestEntry
- Functions: load_ohlcv, short_trend, calc_atr, find_best_swing_sl, detect_market_phase
- SMC: FVG=5 OB=11 Struct=0 Liq=0

### v11/v44_engine_c.py (1191 LOC [V11])
- Classes: RetestEntry
- Functions: load_ohlcv, short_trend, calc_atr, find_best_swing_sl, detect_market_phase
- SMC: FVG=4 OB=11 Struct=0 Liq=0

### v25/smc_core_v27.py (1130 LOC [V27])
- Classes: -
- Functions: confirmed_swings, structure_signals, fvg_list, bpr_signals, sweep_signals
- SMC: FVG=13 OB=23 Struct=40 Liq=1

### daily_multi_source_crawler.py (1084 LOC [Root])
- Classes: -
- Functions: retry_request, retry_urllib, load_config, save_config, verify_text
- SMC: FVG=0 OB=0 Struct=0 Liq=0

### smc_trade_viewer_v2.py (1061 LOC [V2])
- Classes: Handler
- Functions: format_date, load_ohlcv, load_60min_ohlcv, short_sig_label, compute_sl_tp_from_signals
- SMC: FVG=7 OB=5 Struct=5 Liq=0

### v11/v469_final.py (927 LOC [V11])
- Classes: -
- Functions: calc_v38_trailing, calc_signal_strength, is_reversal_ob, load_ohlcv, short_trend
- SMC: FVG=18 OB=20 Struct=6 Liq=0

### v11/signals_v15.py (907 LOC [V11])
- Classes: Signal
- Functions: calc_adaptive_thresholds, detect_swings_v15, _merge_same_direction, _filter_tiny_swings, detect_fvg_v15
- SMC: FVG=12 OB=20 Struct=15 Liq=0

### v11/v468_engine.py (866 LOC [V11])
- Classes: -
- Functions: calc_v38_trailing, is_reversal_ob, load_ohlcv, short_trend, calc_atr_v45
- SMC: FVG=16 OB=18 Struct=4 Liq=0

### v11/v470_engine.py (866 LOC [V11])
- Classes: -
- Functions: calc_v38_trailing, is_reversal_ob, load_ohlcv, short_trend, calc_atr_v45
- SMC: FVG=16 OB=18 Struct=4 Liq=0

### v11/v472_engine.py (865 LOC [V11])
- Classes: -
- Functions: calc_v38_trailing, is_reversal_ob, load_ohlcv, short_trend, calc_atr_v45
- SMC: FVG=15 OB=17 Struct=4 Liq=0

### v11/v473_engine.py (865 LOC [V11])
- Classes: -
- Functions: calc_v38_trailing, is_reversal_ob, load_ohlcv, short_trend, calc_atr_v45
- SMC: FVG=15 OB=17 Struct=4 Liq=0

### v11/v474_engine.py (865 LOC [V11])
- Classes: -
- Functions: calc_v38_trailing, is_reversal_ob, load_ohlcv, short_trend, calc_atr_v45
- SMC: FVG=15 OB=17 Struct=4 Liq=0

## Architecture Summary

### Backtests (74 files)
- v9/smc_backtest.py (462 LOC, V9)
- v25/v258_backtest.py (354 LOC, V258)
- v25/state_backtest.py (316 LOC, Root)
- v25/batch_backtest.py (248 LOC, Root)
- v25/backtest_v251.py (222 LOC, V251)
- v25/backtest_v25.py (223 LOC, V25)
- v11/v500_structural_backtest.py (417 LOC, V11)
- v11/v44_backtest_test_b.py (146 LOC, V11)
- v11/v44_backtest_test_a.py (144 LOC, V11)
- v11/v44_backtest_test.py (139 LOC, V11)
- ... and 64 more

### Diagnostics (57 files)
- v25/v34_sl_diagnose.py (27 LOC, V34)
- v25/v34_funnel_audit.py (62 LOC, V34)
- v25/v33_audit_export.py (94 LOC, V33)
- v25/v31_audit.py (61 LOC, V31)
- v25/smc_diagnostics_v28.py (437 LOC, V28)
- v25/p2_p4_diagnostics_v35.py (59 LOC, V35)
- v11/test_v12_diag.py (59 LOC, V11)
- v11/test_poi_diagnostic.py (75 LOC, V11)
- v11/test_diagnose.py (34 LOC, V11)
- v11/future_function_audit.py (74 LOC, V11)
- ... and 47 more

### Optimizers (25 files)
- v11/param_optimizer_v38.py (617 LOC, V11)
- v11/optimizer_v11.py (351 LOC, V11)
- smc_tuner_v3.py (271 LOC, V3)
- smc_optimizer_v85.py (214 LOC, V85)
- smc_optimizer_v84.py (400 LOC, V84)
- smc_optimizer_v83.py (738 LOC, V83)
- smc_optimizer_v82.py (485 LOC, V82)
- smc_optimizer_v8.py (373 LOC, V8)
- smc_optimizer_v5_v2.py (372 LOC, V5)
- smc_optimizer_v55.py (390 LOC, V55)
- ... and 15 more

### SMC Engines (75 files)
- v25/v36_engine.py (337 LOC, V36)
- v25/v35_engine.py (331 LOC, V35)
- v25/v34_engine.py (327 LOC, V34)
- v25/v34_core_diff.py (42 LOC, V34)
- v25/v33_engine.py (301 LOC, V33)
- v25/v32d_zone6_engine.py (301 LOC, Root)
- v25/v32d_reject045_engine.py (299 LOC, Root)
- v25/v32d_hv_zone6_engine.py (301 LOC, Root)
- v25/v32d_hv_engine.py (299 LOC, Root)
- v25/v32d_engine.py (299 LOC, Root)
- ... and 65 more

### Scanners (48 files)
- v25/v31_full_scan.py (276 LOC, V31)
- v25/v30_full_scan.py (164 LOC, V30)
- v25/v29_full_scan.py (124 LOC, V29)
- v25/v28_full_scan.py (138 LOC, V28)
- v25/v27_full_scan.py (286 LOC, V27)
- v25/scan_3y.py (169 LOC, Root)
- v25/full_scan.py (296 LOC, Root)
- v25/daily_scan.py (253 LOC, Root)
- v11/v473_full_scan.py (19 LOC, V11)
- v11/v472_full_scan.py (22 LOC, V11)
- ... and 38 more

### Signal Detectors (40 files)
- v9/smc_signals.py (312 LOC, V9)
- v25/v32a_signal_audit.py (106 LOC, Root)
- v25/signal_quality.py (321 LOC, Root)
- v25/p1_signal_audit_v35.py (42 LOC, V35)
- v11/test_vPine_signals.py (110 LOC, V11)
- v11/test_v12_signals.py (47 LOC, V11)
- v11/stock_signal_matrix.py (161 LOC, V11)
- v11/signals_vPine.py (1663 LOC, V11)
- v11/signals_v22.py (471 LOC, V11)
- v11/signals_v21.py (487 LOC, V11)
- ... and 30 more

### Test Scripts (35 files)
- v11/test_v470_funnel.py (109 LOC, V11)
- v11/test_v470_full.py (82 LOC, V11)
- v11/test_v470_200.py (72 LOC, V11)
- v11/test_v44_import.py (15 LOC, V11)
- v11/test_v12_verify.py (47 LOC, V11)
- v11/test_v12_quick.py (43 LOC, V11)
- v11/test_v12_mult.py (33 LOC, V11)
- v11/test_v12_20.py (42 LOC, V11)
- v11/test_ob_disp.py (37 LOC, V11)
- v11/test_imports.py (15 LOC, V11)
- ... and 25 more

### Web UI (27 files)
- v9/smc_webui.py (360 LOC, V9)
- v18_dashboard.py (148 LOC, V18)
- v17_viewer.py (205 LOC, V17)
- v16_viewer.py (148 LOC, V16)
- v15_viewer.py (156 LOC, V15)
- v14_viewer.py (168 LOC, V14)
- v11_webui_v4.py (383 LOC, V11)
- v11_webui_v3.py (363 LOC, V11)
- v11_webui_v2.py (242 LOC, V11)
- v11_webui.py (125 LOC, V11)
- ... and 17 more

## V35 Files

### v25/p1_signal_audit_v35.py (42 LOC)
- Key functions: sym, main
- SMC: FVG=3 OB=2 Struct=4 Liq=0

### v25/p2_p4_diagnostics_v35.py (59 LOC)
- Key functions: load, f, met, group, q
- SMC: FVG=6 OB=2 Struct=2 Liq=1

### v25/v35_adaptive.py (390 LOC)
- Key functions: f, fdate, symbol_from_filename, profile_for_name, dynamic_exit_plan, find_recent_zone, make_setup, build_profile_setups
- SMC: FVG=0 OB=6 Struct=3 Liq=0

### v25/v35_engine.py (331 LOC)
- Key functions: fdate, symbol_from_filename, _f, zone_invalidated_bull, bar_touches_zone, next_retrace_strict, confirm_at_zone_strict, entry_from_limit_retouch
- SMC: FVG=8 OB=7 Struct=8 Liq=1


> **Full Graph**: 593 files, 143770 LOC
> **Versions detected**: Root, V2, V3, V4, V5, V6, V7, V8, V9, V10, V11, V12, V13, V14, V15, V16, V17, V18, V19, V24, V25, V26, V27, V28, V29, V30, V31, V33, V34, V35, V36, V38, V39, V53, V54, V55, V61, V62, V82, V83, V84, V85, V116, V251, V258, V10.5
