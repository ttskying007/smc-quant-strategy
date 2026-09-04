# V26 cron auto-repair gatekeeping and frontend restart notes

Session-derived durable pattern for V25/V26 SMC scheduled repair jobs.

## Auto-repair thresholds

For V26/V25 cron repair runs, do not change parameters just because a weaker bucket exists. Apply the explicit gates:

- `WR < 85%`: analyze losses root cause and adjust market-state/state parameters.
- `TP1 hit rate < 70%`: tighten TP1 target.
- `SL rate > 20%`: inspect high-SL combinations and adjust only the offending combinations.
- If all three are within threshold, leave parameters unchanged and report any borderline risk bucket as observation only.

Example: WR 85.3%, TP1 77.8%, SL 14.5% is a no-change result even if one market-state bucket (e.g. TREND_UP) has SL around 20%.

## Frontend restart path

The SMC unified frontend entrypoint is under:

```bash
/root/.hermes/scripts/smc_unified.py
```

A restart flow should be:

```bash
ss -tlnp | grep 8890 || true
# kill old 8890 pid(s)
python3 /root/.hermes/scripts/smc_unified.py
```

If a launch attempt reports `OSError: [Errno 98] Address already in use`, immediately re-check:

```bash
ss -tlnp | grep 8890 || true
```

Sometimes a replacement process has already bound the port; do not keep starting duplicate frontends.

## Verification pages

After restart, verify all standard pages:

```bash
for p in / /kline /backtest /monitor /analysis /autopsy /stoploss /v45 /docs; do
  curl -s -o /dev/null -w '%{http_code} %s\n' "http://127.0.0.1:8890$p"
done
```

All should return `200` before reporting success.
