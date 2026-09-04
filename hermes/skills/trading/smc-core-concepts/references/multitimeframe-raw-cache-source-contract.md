# Multi-timeframe raw cache and multi-source monitoring contract

## Purpose

Before testing multi-timeframe price structure, volume absorption, Spring/Test, SOS/Backup, or Selling Climax, establish a reproducible, same-price-basis OHLCV layer covering the full frozen study period.

## Data basis

- Treat one provider and one price basis as the **historic writer** for each research dataset. Do not fill individual missing intraday bars from a second provider.
- For 2023–2026 SH/SZ intraday history, Baostock `adjustflag=3` supplies the raw OHLCV writer; 15m requests must be chunked by quarter and 60m requests by year to avoid silent provider caps.
- Derive weekly bars only from the same raw daily series. Do not combine QFQ daily bars with raw intraday bars when deriving POIs, structural SL/TP, event thresholds, or replay outcomes.
- Keep provider differences as audit facts. A secondary provider may witness availability and recent overlap, but an overlap mismatch means it must **not** be used for automatic per-bar substitution.

## Completeness gate per security

Only persist an eligible security after all of these pass:

| Frame | Required validation |
|---|---|
| Daily | valid OHLCV, ordered dates, frozen period coverage |
| Weekly | deterministic aggregation from raw daily: first open / max high / min low / last close / summed volume and amount |
| 60m | every locally available daily date has exactly 10:30, 11:30, 14:00, 15:00 bars |
| 15m | every locally available daily date has exactly 09:45–11:30 and 13:15–15:00, 16 bars |

Use atomic writes; never write a partly fetched security as eligible cache data. Quarantine securities unsupported by the historic provider rather than presenting partial coverage as full-market evidence.

## Operations

1. Probe primary and independent witness sources before a build batch.
2. Build a bounded, idempotent batch and resume only missing eligible securities.
3. Probe sources again after the batch; write timestamped and `latest` health artifacts.
4. Lock the batch controller to prevent scheduler overlap.
5. Do not launch ontology/replay research while cache completeness is below the predeclared scope; after completion, run full-universe frame coverage, timestamp-slot, OHLC validation, and daily→weekly aggregation audits.

## Multi-source roles

- **Primary raw writer:** creates frozen research cache.
- **Witness source:** detects outage, blocking, cap changes, or recent-source drift; it never silently repairs the raw writer's sequence.
- **Operational daily source:** may support a separate current-market epoch, but has no authority to rewrite frozen historical raw bars.

This separation protects causal replay from a hidden source switch that would otherwise look like a trading improvement or degradation.
