# PIT announcement-payload source qualification

## When metadata alone is insufficient

A timestamped title archive is not evidence for a semantic field that is absent from the title. For example, an earnings-preannouncement title proves an announcement occurred, but does not prove positive/negative profit direction. Do not infer the missing field from title wording.

## Source-only qualification sequence

1. Start with a complete canonical metadata denominator containing `symbol`, `announcement_id`, `notice_date`, and `publication_time`.
2. Probe the provider payload endpoint using a deterministic sample independent of content and market outcomes (for example, hash-sort `announcement_id`, then take a fixed count per year).
3. For every probe assert all of:
   - HTTP success;
   - payload `art_code == announcement_id`;
   - payload publication time matches metadata publication time;
   - non-empty payload body.
4. Define any field extractor only from explicit current-period body text. Record unclassified notices; never silently treat them as positive/negative.
5. Keep the pilot source-only: prohibit OHLCV, seeds, trades, outcomes, PnL, targets, stops, and strategy labels.

## Resumable full-payload build

- Derive the denominator from the metadata archive, not already-downloaded files.
- Write each raw payload atomically under a provider-isolated, year-partitioned cache.
- Store provider identity, metadata and payload timestamps, content hash, and the original body.
- Retry transient transport failures with bounded backoff.
- Persist terminal fetch/identity/empty-body failures separately. A failure record is **not** a valid payload and must cause the later full coverage/PIT audit to fail closed; it only prevents an infinite retry loop.
- The latest daily-cache session may be `PIT_PENDING_PUBLICATION`: because its exchange disclosure cannot legally inform a same-day decision, do not report that unpublishable tail as a historical build failure. It becomes eligible after the daily cache advances.

## Promotion boundary

A source-pilot pass only authorizes a complete source coverage/PIT/semantic catalog audit. It does not authorize an outcome-blind seed, a strategy ontology, or any production write. Only after full coverage and timestamp contracts pass may a separately preregistered ontology begin.