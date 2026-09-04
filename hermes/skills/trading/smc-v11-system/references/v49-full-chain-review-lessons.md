# V49 full-chain per-trade review lessons

- Script: `/root/.hermes/scripts/v25/v49_full_chain_review.py`.
- Outputs: `/root/.hermes/smc_audit/v49_full_chain_review.json` and `.md`.
- Review dimensions: signal trace, entry zone position, SL/risk, exit legs, realized R, MFE/MAE, post30/post120 MFE, sold-early, severe-sold-early, fake-SL, per-trade issue tags.
- Current V49 review (132 trades): WR 88.64%, SL 10.61%, avgPnL 15.11%, avg MFE 31.863%, median MFE 19.724%, avg post30 MFE 41.022%, realized R avg 3.146 vs MFE R avg 6.607, avg MFE capture 0.133.
- Main architecture issue: not signal win-rate, but exit monetization. 98/132 sold early, 72/132 severe sold early, 15 runner-capture-too-low, 7 fake-SL. V49 preserves WR but captures too little of available MFE.
- Entry split: `FALLBACK_OLD_ENTRY_NO_DEEP_FILL` 65 trades, WR 98.46%, SL 0%, avgPnL 15.136%, avg MFE capture 0.322; `ZONE_MID_EXECUTABLE` 67 trades, WR 79.1%, SL 20.9%, avgPnL 15.085%, avg MFE capture -0.051, fakeSL 10.45%. ZONE_MID is the loss/fake-SL bucket despite similar avgPnL from large winners.
- Zone split: OB 89 trades avgPnL 16.161, WR 88.76, SL 11.24, fakeSL 7.87; FVG 43 trades avgPnL 12.936, WR 88.37, SL 9.3, fakeSL 0. FVG has lower avgPnL and lower MFE capture, OB has fake-SL problem.
- Exit split: TRAILING_STOP 106 trades avgPnL 17.047 but sold_early 79.25%; TIMEOUT_PARTIAL 6 trades avgPnL 37.452 and capture 0.532; SL/GAP_SL has 7 fake-SL cases, mostly ZONE_MID OB.
- Direction for next repair: do not further optimize aggregate WR/RR first. Build structure-based runner exit and per-bucket entry/SL rules: ZONE_MID needs a wait-for-reclaim / wider structural SL / stricter confirmation; FALLBACK/CHASE bucket should be renamed and audited because it wins but is outside raw zone; OB needs fake-SL repair; FVG needs separate runner/capture logic.
