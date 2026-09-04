# SMC Frontend V9 Architecture

## Server
- Single-file Python HTTP server: `/root/.hermes/scripts/smc_unified.py`
- Port: 8890
- Dependency: `v11.signals_v20` for on-demand signal detection
- Data: loads V8+V9 backtest JSONs at startup

## Pages
1. **Dashboard** (`/`): Stats cards + signal type breakdown + Top25 picks table
2. **K-line** (`/kline?s=CODE`): ECharts candlestick chart + signal scatter markers + V9 trade table. Input for symbol + timeframe (daily/60min)
3. **Backtest** (`/backtest`): PnL distribution histogram + hold bar distribution
4. **Monitor** (`/monitor`): Top50 picks from V9 selection, auto-refresh every 30s
5. **AI Analysis** (`/analysis`): Quality assessment matrix + known issues tracker

## API Endpoints
- `GET /api/kline?symbol=X&tf=daily|60min` → {klines, signals_list, trades}
- `GET /api/picks` → Top50 picks JSON
- `GET /api/summary` → {total_trades, win_rate, avg_pnl, stocks, signals}

## Design
- Dark theme (CSS variables: --bg=#0a0e14, --card=#131820)
- ECharts 5.5.0 via CDN for charts
- No build step, no npm, no JS framework
- All CSS/JS inline in Python string templates

## Port Conflict (hermes-web-ui)
oh-my-hermes CTO profiles hardcode ports 8642-8651. The ops profile takes 8648, colliding with hermes-web-ui Express server. Fix: delete profile dirs at `~/.hermes/profiles/{cto,dev,pm,qa,ops,security,legal,lider,investigador}`.
