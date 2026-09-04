# Real-Time Trading Simulator — Implementation Details

## Architecture

```
v19_picks.json (265 stocks)
    ↓ pick['symbol'], pick['price'], pick['regime'], pick['sl_initial_pct'], pick['tp_tiers']
TradingSimulator.execute_buy()
    ↓
    ├─ is_trading_time() → reject if closed
    ├─ fetch_prices() → Hubble real-time quote
    ├─ suspended? limit_up? volume<1000? → reject
    ├─ already held? max 20? → reject
    ├─ calculate_position_size() → Half-Kelly
    ├─ apply slippage (buy_price = current × 1.001)
    ├─ deduct commission (0.03%)
    └─ create Position + Order → save_state()

TradingSimulator.check_positions()
    ↓
    ├─ fetch_prices() for all active positions
    ├─ for each position:
    │   ├─ T+1 check (buy_date == today → skip)
    │   ├─ SL hit? (current ≤ sl_price) → execute_sell()
    │   ├─ TP hit? (current ≥ tp_prices[-1]) → execute_sell()
    │   └─ 30% drawdown? (current < avg_cost × 0.7) → execute_sell()
    └─ save_state()
```

## Position Sizing Algorithm

```python
def calculate_position_size(price, sl_pct, atr_pct):
    equity = cash + sum(p.shares × p.current_price)
    kelly = (avg_rr × win_rate - (1 - win_rate)) / avg_rr  # Full Kelly
    kelly = max(0.05, min(kelly × 0.5, 0.10))             # Half-Kelly, 5-10% cap
    
    max_position = equity × 0.05      # 5% max per position
    min_position = equity × 0.01      # 1% minimum
    
    position_value = min(max_position, equity × kelly)
    position_value = max(min_position, position_value)
    
    shares = int(position_value / price / 100) × 100
    return shares, position_value / equity
```

## Fee Model (A-share standard)

| Fee | Rate | When |
|-----|------|------|
| Commission (buy) | 0.03% | On order fill |
| Commission (sell) | 0.03% | On order fill |
| Stamp tax | 0.10% | On sell only |
| Slippage | 0.10% | Added to buy price, deducted from sell price |

## Trading Hours Detection

```python
def is_trading_time():
    now = datetime.now(timezone(timedelta(hours=8)))  # CST
    wd = now.weekday()       # 0-4 = Mon-Fri
    t = now.hour * 60 + now.minute
    
    if wd >= 5: return False, 'weekend'
    if 570 <= t < 690: return True, 'morning'       # 9:30-11:30
    if 780 <= t < 900: return True, 'afternoon'      # 13:00-15:00
    return False, 'closed'
```

## Suspension Detection

Hubble API `/api/v2/cnstock/securities` returns a `status` field per stock.
If status contains '停牌' or 'SUSPEND', the stock is suspended and buy orders are rejected.

## Order Lifecycle

```
PENDING → (check suspension/limit/volume/cash) →
    ├─ FILLED: all checks passed, position created
    └─ REJECTED: with reason (停牌/涨停/流动性不足/资金不足/已持仓/非交易时段)
```

## Cron Job

Job ID: `b05510545b8c`
Schedule: `*/30 9-11,13-14 * * 1-5` (Mon-Fri, every 30min during trading)
Action: Scan v19_picks.json for entries → check positions for SL/TP → output summary

## CLI Reference

```bash
python3 /tmp/trading_sim.py status   # Portfolio summary
python3 /tmp/trading_sim.py scan     # Scan picks and execute buys
python3 /tmp/trading_sim.py check    # Check positions for SL/TP
python3 /tmp/trading_sim.py reset    # Wipe all data, start fresh
```

## Pitfalls

1. **T+1 violation**: Do NOT allow selling on same day as buy. Check `pos.buy_date != today` before executing sell.

2. **Hubble price returning 0**: Non-trading hours return empty data. Always check `price > 0` before executing any order.

3. **Order saved every time**: `save_state()` is called after every buy/sell to prevent data loss on crash. This means I/O on every trade → accept the overhead for data safety.

4. **Portfolio JSON corruption**: If portfolio.json gets corrupted, the system falls back to fresh state (100万 cash, 0 positions). The old file is NOT backed up.

5. **Limit up stocks**: `chgPct > 9.5%` AND `price ≈ high` → stock is at limit-up, cannot buy. Detect via Hubble API fields.
