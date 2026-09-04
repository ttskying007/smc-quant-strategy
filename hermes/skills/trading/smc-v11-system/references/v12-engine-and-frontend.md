# V12 Engine & Frontend Rewrite (2026-05-15)

## V12 Engine (`/root/.hermes/scripts/v11/v12_engine.py`)

Replaces V11 engine. Key improvements:

### Detailed Trade Log (30+ fields per trade)
| Field | Description |
|-------|-------------|
| `symbol`, `entry_date`, `exit_date` | Trade timestamp |
| `signal_type`, `signal_date`, `signal_price`, `signal_idx` | Signal details |
| `entry_type`, `entry_price`, `retrace_pct` | Entry method + retrace depth |
| `entry_detail` | Human-readable entry reason |
| `cost_line` | Smart money cost line (OB lower edge) |
| `combo` | Signal combination e.g. `OB@266→LIQ@267→CHOCH@273` |
| `has_sweep`, `has_choch`, `weekly_bull` | Context flags |
| `sl_price`, `sl_pct`, `tp_pct` | Exact SL/TP values |
| `exit_price`, `exit_date`, `exit_reason`, `exit_detail` | Exit: SL_hit / time_stop / timeout |
| `pnl_pct`, `won`, `rr`, `hold_bars` | Performance |
| `market_state`, `atr_pct` | Environment |

### Signal Combination Detection
Uses `detect_smc_setups()` from signals_v20.py:
- Detects true SMC sequences: Demand Zone → Liquidity Sweep → CHOCH → Entry
- ~7.4% of trades have combo signals (1,119 out of 15,029)
- Combo format: `OB@266→LIQ@267→CHOCH@273` (chronological order)

### Anti-Duplication
`seen_bars` set prevents multiple trades at same entry bar for same stock.

### Batch Exit Simulation
- 50% at TP1 (2x ATR), 30% at TP2 (4x ATR), 20% trailing
- Exit reasons: SL_hit, time_stop (30 bar), timeout (40 bar)
- Exit detail format: `TP1+TP2+SL=47.99+SL_hit`

### V12 Full Backtest Results
```
Total: 15,029 trades | 4,702 stocks | WR=99.1% | Avg PnL=+9.80%
Exit reasons: SL_hit 13,371 | time_stop 1,646 | timeout 12
Combo trades: 1,119 (7.4%)
```

## Frontend Rewrite (`/root/.hermes/scripts/smc_unified.py`, port 8890)

### K-line Page (`/kline?s=SYMBOL`)
Full signal rendering using ECharts markArea/markLine/markPoint:

**Rectangle Zones (markArea)** — semi-transparent rectangles:
- FVG, IFVG: purple
- OB: blue (bull) / red (bear)
- BPR: teal
- OTE: green
- PO3: blue/red/green for Accum/Manip/Dist
- Breaker Block, Rejection: purple/orange

**Line Signals (markLine)** — colored horizontal lines:
- CHOCH: cyan solid (bull) / pink solid (bear)
- BOS: green solid (bull) / red solid (bear)
- Sweep: green dashed (SSL) / orange dashed (CBL)
- MSS: light blue dashed
- EQL: grey solid
- LiquidityVoid: grey dashed

**Trade Markers (markPoint):**
- BUY (entry): green pin ↑ + signal combo label (bold, top position)
- SELL (exit): cyan/orange diamond ◆ + PnL% label
- SL line: amber dashed horizontal
- TP line: green dashed horizontal

**Swing Points (markLine zigzag):**
- HH/LH: red labels at swing highs
- HL/LL: green labels at swing lows
- Connecting dashed lines between consecutive swings

**Toggle Switches (17 signal families):**
BOS, BPR, BRK, CHOCH, EQL, FVG, IFVG, LV, MSS, OB, OTE, PB, PO3, RB, Sweep,
+ Swings, SL, TP, [All On] [All Off]

**Version Selector:** V12 (detailed) / V11 / V10 / V9

**Trade Table (14 columns):**
# | Buy Date | Buy Price | Sell Date | Sell Price | Signal | Signal Price | 
Entry | Retrace% | Exit Reason | PnL | SL | RR | Hold Bars

### ECharts Local Serving Pattern
When CDN is blocked (common in GFW environments):
```python
# Download
curl -sL --max-time 30 -o echarts.min.js "https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"

# Serve via Python HTTP handler
elif path == '/echarts.js':
    self._static_file(Path('/root/.hermes/scripts/echarts.min.js'), 'application/javascript')
```

### Dashboard (`/`)
- Brand: SMC V12
- Stats: 15,029 trades, 99.1% WR, 9.80% avg PnL, 96.5% TP1 hit, 4,702 stocks
- Signal table: OB_Bull with count and WR

### Output Files
- JSON: `/root/.hermes/smc_opt_v12/v12_complete.json`
- CSV Log: `/root/.hermes/smc_opt_v12/v12_trade_log.csv` (openable in Excel)
- Engine: `/root/.hermes/scripts/v11/v12_engine.py`

## Server Management
```bash
# Start
cd /root/.hermes/scripts && python3 smc_unified.py &
# Stop
pkill -f "smc_unified.py"
# Health check
curl -so /dev/null -w "%{http_code}" http://localhost:8890/
```
