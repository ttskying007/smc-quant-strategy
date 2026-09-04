# V46.1/V35 SMC Signal Visual Accuracy Repair

## Trigger
Use this note when the user says K-line SMC labels are still visually inaccurate after apparent Pine/LuxAlgo alignment, especially for BOS / CHOCH / MSS / OB markers.

## Session lesson
A previous fix separated `swing_len=5` and `internal_len=3` and improved chart labels, but the user still correctly observed inaccurate structure markers. The deeper issue was not label formatting. The pivot core itself still allowed structure anchors to drift into trend middles.

## Root cause pattern
1. **One-sided leg translation is insufficient for visual structure accuracy**
   - Translating LuxAlgo `leg(size)` using only right-confirmation can emit consecutive highs or lows without an intervening confirmed opposite swing.
   - That creates BOS/CHOCH events anchored to candles that are not true market structure pivots.
   - Visual symptom: BOS/CHOCH/MSS labels appear in the middle of a move, not at meaningful structural breaks.

2. **Layer collapse and semantic mixing must both be prevented**
   - `swing_len == internal_len` collapses structure layers.
   - Even after separating lengths, internal MSS can still visually pollute swing BOS/CHOCH if duplicate or near-duplicate events are rendered as independent primary signals.

3. **OB correctness depends on structure correctness**
   - If BOS/CHOCH is anchored incorrectly, OB windows are also wrong.
   - OB metadata should preserve the event and pivot that created it so future audits can verify whether OB is structurally justified.

## Durable fix pattern
For K-line-visible structure correctness, use a two-sided confirmed swing pivot before generating swing BOS/CHOCH:

```python
pivotHigh = high[k] > max(high[k-size:k]) and high[k] > max(high[k+1:k+size+1])
pivotLow  = low[k]  < min(low[k-size:k])  and low[k]  < min(low[k+1:k+size+1])
confirm_idx = k + size
```

Keep backtest causality by making the pivot available only at `confirm_idx`, not at `k`.

Recommended architecture:
- Swing layer: `swing_len=5`, produces chart BOS/CHOCH and OB creation.
- Internal layer: `internal_len=3`, contributes only qualified MSS early-warning markers.
- Internal MSS must not create OB and must not duplicate same-bar same-direction swing structure.
- K-line labels must include direction: `CHOCH↑/↓`, `BOS↑/↓`, `MSS↑/↓`.
- OB records should include `created_by_pivot_label` and `created_by_pivot_price` in addition to event index/date/type.

## Verification checklist
After changing signal core, do all of these before reporting success:

1. `python3 -m py_compile` target core and frontend server files.
2. Run single-symbol trace, e.g. 600519, and inspect first structure events with:
   - `type`
   - `direction`
   - `index/date`
   - `price/break_price`
   - `swing_idx/swing_label`
   - `old_trend`
   - `source_level`
   - `is_internal_mss`
3. Count same-bar/near-bar duplicate structure events.
4. Count structures and OBs before/after; expect stricter core to reduce noisy labels.
5. Restart frontend and verify `/api/kline_full?symbol=600519.SH&ver=V46_1` returns updated counts.
6. Verify the K-line HTML/render path contains directional labels, not generic undirected text.

## Reporting discipline for this user
Do not claim “fully Pine-aligned” unless a bar-by-bar reference comparison has been completed. If only structural improvements and API/chart synchronization were verified, say exactly that and identify remaining Pine-diff work.
