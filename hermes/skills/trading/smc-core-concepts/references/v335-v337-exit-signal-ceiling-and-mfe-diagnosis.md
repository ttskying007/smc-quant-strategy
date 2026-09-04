# V335–V337 Exit Contract vs Signal-Family Ceiling Audit

Use this when an SMC route looks historically strong in a selected population but fails production promotion, or when WR and Avg PnL cannot both satisfy the gate.

## Trigger

- A historical selected set passes headline gates, but current scanner/full-universe validation fails.
- Fixed SL/TP can produce either high WR or high Avg, but not both.
- Runner/TP1 overlay improves WR but still cannot reach average PnL.
- Need to decide whether to keep tuning exits or rebuild the signal/expansion filter.

## Required Sequence

1. **Separate selected-population quality from full-universe quality**
   - Selected-only V246/V330-style rows can show 94–96% WR.
   - Before promotion, replay the same rule on the full scanner universe, not only the historical selected rows.
   - If full-universe WR/Avg drops, label the route as selected-only/shadow and do not promote.

2. **Run exit-contract frontier before blaming the signal**
   - Test fixed single-target contracts across SL buffer, R multiple, and max hold.
   - Report the tradeoff table:
     - high WR / low Avg bucket;
     - high Avg / low WR bucket;
     - any rule satisfying both.
   - If no rule satisfies both WR and Avg, do not keep surface-tuning SL/TP.

3. **Run TP1 + runner overlay frontier**
   - Test fast TP1, runner fraction, TP2, max hold, and trailing modes.
   - Diagnose whether runner raises Avg without reintroducing micro-profit pollution.
   - If TP1+runner keeps WR high but Avg remains low, the issue is not simply “exiting too early”.

4. **Run MFE/MAE ceiling diagnosis**
   - For each candidate family, compute forward path metrics (e.g. 20-bar MFE/MAE/close return):
     - MFE average/median;
     - MFE ≥ 8/10/15% rates;
     - MAE ≤ -5/-8% breach rates;
     - close-at-horizon average;
     - expansion-quality rate = `MFE>=10% AND MAE>-5%`.
   - This distinguishes:
     - no expansion available → true signal-family ceiling;
     - expansion exists but exits fail to harvest it → exit/lifecycle architecture issue;
     - expansion exists only in tiny unstable buckets → research-only, not production.

## V335–V337 Findings Pattern

- Fixed single-target exits produced either:
  - WR ≥ 93% with Avg around 3.7–5.1%, or
  - Avg ≥ 7.6% with WR collapsing to roughly 73–83%.
- TP1+runner overlays could reach very high WR but still kept Avg far below production target and introduced micro-profit pollution in some variants.
- MFE/MAE diagnosis showed the family did contain expansion:
  - broad base had large MFE but high MAE breach;
  - tighter F1/F2-style families had materially better MFE and lower MAE;
  - the best expansion predicates were strong but too sparse to promote directly.

## Promotion Rules

Do **not** promote when:

- the pass only exists inside a historical selected set;
- full-universe replay fails yearly WR or Avg gates;
- the best high-MFE predicates have `min_year_n` too low;
- current rows are already closed by replay and there are no true open actionable rows;
- high WR is achieved via tiny TP/micro-profit behavior.

Only promote after all of these pass:

- full-universe replay, not selected-only;
- strict T+1 audit (`exit_date != entry_date`);
- yearly count and yearly WR gate;
- Avg PnL gate and micro-profit cap;
- current non-history actionable/open supply exists;
- endpoint/frontend mapping remains shadow-only until strategy gates pass.

## Reporting Shape for Lei

Report as a compact table:

| Test | Best result | Failing gate | Decision |
|---|---:|---:|---|
| selected-only historical | WR/Avg/n | none or caveat | shadow candidate |
| full-universe fixed exits | WR vs Avg tradeoff | WR or Avg | reject/tune next |
| TP1+runner | WR/Avg/micro | Avg/micro/n | reject/diagnose |
| MFE/MAE | MFE10, MAE5, expansion quality | sample/year stability | next generator |

Do not claim strategy completion from endpoint/API cleanliness or selected-only backtest quality.
