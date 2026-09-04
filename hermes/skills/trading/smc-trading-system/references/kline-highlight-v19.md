# K-line Highlight System V19 (2026-05-18)

## Two-Tier Highlight Architecture

When user clicks a stock from the monitor page, the K-line API (`/api/kline_full`) provides two highlight layers:

### Tier 1: Zone Origin (Z:SEQ)
- Source: cross-reference pick with V19 trades to get `zone_bar`
- Label: `Z:OB→IDM` — shows the demand zone origin and its signal sequence
- This is the reason the stock was SELECTED (unbreached zone)

### Tier 2: Recent Active Signals
- Source: `signals_list` from `detect_sigs()` on current 300-bar kline
- Searches last 50 bars for key SMC signals (OB/CH/LIQ/FVG/PB/BRK/IF/etc.)
- Shows WHY the zone is still relevant TODAY
- Max 6 recent signals to avoid clutter

## Frontend Rendering
- Zone origin: `roundRect 52×24` with red background `#ff0000` + yellow border `#ffff00`
- Recent signals: same `roundRect` with white text on red
- Each signal gets a circled number (①-⑨) via `String.fromCharCode(0x245F + num)`

## Critical Bug Fixed (2026-05-18)
**Old approach**: search for "most recent unbreached OB" → map nearby signals → mark
- Problem: highlights were at random OB locations unrelated to any actual trade
- User feedback: "看着离当前是比较远的距离"

**New approach**: 
1. Look up pick → get zone_bar from cross-referenced trade
2. Scan signals in last 50 bars → highlight recent activity
- This shows BOTH why the stock was picked AND what's happening now

## Data Flow
```
Monitor click → /kline?s=003027.SZ&seq=OB→IDM
  → _api_kline_full(symbol, ver=V19)
    → reload_picks() → find stock_pick
    → ver_map['V19'] → find stock_trade → get zone_bar
    → detect_sigs(data) → signals_list
    → highlight = [Z:, OB, CH, LIQ, ...]
    → JSON response with highlight array
```

## Pitfall: zone_bar not in picks
V19 picks don't carry `zone_bar` — must cross-reference with V19_TRADES:
```python
stock_pick = next(p for p in picks if p['symbol'] == symbol)
stock_trade = next(t for t in V19_TRADES if t['symbol'] == symbol)
zb = stock_trade['zone_bar']  # NOT stock_pick['zone_bar']
```
