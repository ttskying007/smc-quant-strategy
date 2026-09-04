# V72 Layered Pool + Frontend Field Contract Lessons

## Trigger
Use this reference when expanding an SMC candidate pool into parallel quality tiers, or when a frontend page shows blank pick/live fields after adding a new engine version.

## Durable Lessons
- Do not promote a strict micro-sample version as production just because WR/SL look good. If the strict layer has only dozens of trades over 3 years, keep it as a sub-layer and build broader Base / QualityA / QualityB / Strict tiers from an upstream pool.
- Keep current production untouched when adding experimental tiers. Register the new version behind `ver=<VERSION>` and keep `ACTIVE_VERSION` unchanged until full production gates pass.
- For layered SL-buffer experiments, write an independent output directory and report files instead of overwriting the production engine directory.
- Field contract fixes must be centralized in the frontend normalization layer, not patched separately in each table renderer.

## V72 Pattern
- Source pool: read the largest validated upstream candidate set, then apply only proven overlay gates needed for contract continuity.
- Tier examples:
  - `Base`: broad source after required continuity overlay.
  - `QualityA`: `sl_buffer_below_zone_pct >= 0.25`.
  - `QualityB`: `sl_buffer_below_zone_pct >= 0.50`.
  - `Strict`: `sl_buffer_below_zone_pct >= 0.75`.
- Each trade/pick should carry provenance fields such as `quality_tier`, `sl_buffer_below_zone_pct`, `entry_above_zone_high_pct`, `definition_version`, and source pool name.

## Frontend Registration Checklist
1. Add a version directory constant, e.g. `V72_DIR = Path('/root/.hermes/smc_opt_v72_layered')`.
2. Add `get_version_trades('<VERSION>')` loader with lite stripping of large nested fields.
3. Add `get_version_picks('<VERSION>')` loader through `normalize_v27_picks(..., get_version_trades(..., lite=False))`.
4. Do not insert the experimental version into the `ACTIVE_VERSION` chain unless explicitly promoting it.
5. Restart the 8890 frontend and validate both API and HTML pages.

## Required Field Fallbacks
Normalize these once in `_normalize_pick_scope()` or equivalent:
- `pick_date`: fallback from `pick_date/conf_date/retrace_date/entry_date/signal_date/date`.
- `select_date`: fallback to normalized `pick_date`.
- `join_date`: fallback from `join_date/joined_date/created_at/select_date/pick_date` so the column is never blank.
- `zone_type`: fallback from `signal_type/v59_setup_family/engine`.
- `signal_type`: fallback from `zone_type/v59_setup_family/engine`.
- `zone_low/zone_high`: fallback from execution/raw/demand-zone fields.
- `smart_money_cost/cost_line`: fallback to existing cost field, then zone midpoint, then entry price.
- `volatility_pct/v25_vol_class`: fallback from ATR/risk/SL percentage, then quality tier or zone type.

## Live Page Fallbacks
For `/api/live-prices`, monitor positions may have sparse `raw_pick`. Before output:
- Merge `raw_pick` with durable position fields for `zone_type`, `signal_type`, `conf_type`, `zone_low`, `zone_high`, `cost_line`, `smart_money_cost`, `risk_pct`, and `volatility_pct`.
- Compute final `costLine` from cost fields, zone midpoint, or entry price.
- Compute final `volClass` from explicit class, market state, quality tier, risk percentage, or zone type.
- Emit `zoneType` as `zone_type/signal_type/v59_setup_family/engine/UNKNOWN` rather than an empty string.

## Verification
Run all checks before declaring completion:
- Python syntax compile for touched frontend/scripts.
- Direct import or script check that new version loads expected trade/pick counts.
- Empty-field audit over normalized picks: `select_date`, `join_date`, `zone_type`, `cost_line`, `volatility` all zero empty count.
- HTTP check after restart: `/monitor` includes `选股日期`, `加入日期`, and `Zone`; `/api/live-prices` sample has `pickDate`, `joinDate`, `zoneType`, `costLine`, and `volClass`.
