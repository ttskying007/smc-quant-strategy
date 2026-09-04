# V246 current-smoke gate after historical production pass

## Trigger

Use this when a historical SMC candidate/rule appears to pass production metrics, but it is derived from a parent live-scanner rule or a post-filter/addback over current scanner rows.

## Durable lesson

A historical production pass is not enough to promote or write watchlist/frontend artifacts. Before promotion, rerun the current scanner chain and prove the same rule can produce actionable rows from current scanner output. If the parent current rule set is empty, any strict child post-filter/addback over that parent must also be empty.

## Verified pattern from V244→V247

- V244 industry participation probe improved a historical candidate but did not pass production/research gate by itself.
- V245 source-field separator found a research-only filter (`v244_industry != C27医药制造业`).
- V246 industry weak-bucket addback produced a historical production pass:
  - n=573
  - WR=94.4154%
  - avg=7.6022%
  - min_year_n=71
  - all_year_wr_min=92.22%
  - micro_profit_pct=0.349%
  - T+1 violations=0
- V164 current scanner dry-run was rerun first:
  - scanned_symbols=4655
  - source_rows=38794
  - recent45_rows=1827
  - field missing=0
  - outcome_field_leak_rows=0
- V236 and V241 current smoke still returned raw_rule_rows=0.
- V247 concluded V246 current rows=0 because V246 is a strict post-filter/addback over V239/V244 parent current rows.

## Required gate

Before promoting any historically good child rule:

1. Rerun the scanner dry-run that materializes current scanner rows (for this lineage, V164 corrected scanner dry-run).
2. Rerun the parent current-smoke/audit scripts from the refreshed scanner output.
3. Rerun the child current-smoke wrapper.
4. Verify:
   - production_write=false
   - frontend_write=false
   - watchlist_write=false
   - selector_leak_fields=[]
   - active/outcome pollution=0
   - T+1 violations=0 for historical evidence
5. If parent `raw_rule_rows == 0`, do not attempt to rescue promotion by writing historical rows. Report current candidate count as zero and keep the rule in shadow/research state.

## Reporting shape

Report this as a compact table:

| layer | historical result | current raw rows | current actionable rows | decision |
|---|---:|---:|---:|---|
| parent scanner rule | ... | ... | ... | ... |
| child/post-filter rule | ... | ... | ... | ... |

Always explicitly distinguish `historical production pass` from `current actionable candidate`. Historical rows must not be used as live picks.