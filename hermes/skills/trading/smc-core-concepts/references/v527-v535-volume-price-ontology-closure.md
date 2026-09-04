# V527–V535 volume-price ontology closure

## Scope and fixed acceptance gate

All tests below are **no-write**: no production, frontend, watchlist, or position mutation. Before any outcome is opened, each ontology must pass: total seeds >=300, each of 2023–2026 >=40, immutable date identity, strict causal chronology, and no outcome field. A passed seed set must then match a separately implemented raw-bar Oracle exactly. The one frozen replay contract is: eligible-session open, exit scanning only from the following session, `SL-first` same-bar collision, 20 sessions maximum hold, 0.20% round-trip fee, serial one-position-per-symbol, stop at the causal low ×0.99, and target only a pre-event confirmed 3L/3R swing high above entry.

Promotion requires `n>=300`, each year `n>=40`, WR>=55%, AvgNet>=+0.5%, PF>=1.15, payoff>=0.7, each-year AvgNet>0, zero T+1 violations, and no duplicate symbol-entry.

## V527–V529: Spring → low-effort Test → SOS — CLOSED

- Causal story: confirmed swing low → high-effort SSL spring/reclaim → low-effort test holds the spring → SOS → following-session open.
- The current date-identity lineage passed support (8,124 seeds) and independent Oracle (8,124/8,124).
- Frozen replay: 7,329 closed trades; WR 62.2322%; AvgNet **−0.3586%**; payoff 0.5270; PF 0.8687. AvgNet: 2023 −0.8036%, 2024 −0.3611%, 2025 +0.3565%, 2026 −1.1295%.
- T+1=0 and all targets pre-spring. The failure is economic, not chronology. Do not search test window, volume ratio, SL/TP, hold, or regime variants.

## V530–V532: SOS → low-effort Backup-to-the-Edge → Reacceptance — CLOSED

- Causal story: confirmed swing high → high-effort SOS breakout → low-effort backup holds broken edge → reacceptance above backup high → following-session open.
- Support: 1,570 seeds, 2023–26 = 236/359/701/274. Independent Oracle: 1,570/1,570.
- Frozen replay: 1,440 closed; WR 55.0694%; AvgNet **−0.5342%**; payoff 0.6374; PF 0.7825. Yearly AvgNet: −0.7496%, −1.2845%, −0.0900%, −0.5024%.
- Independent recomputation matched all metrics, T+1=0, targets pre-reacceptance=1, duplicate symbol-entry=0. Close this ontology without parameter variants.

## V533–V535: Selling Climax → Automatic Rally → Secondary Test → SOS — CLOSED

- Causal story: high-effort bearish wide-range selling climax → automatic rally above climax high → lower-effort secondary test holds climax low → SOS above rally high → following-session open.
- Support: 26,313 seeds, 2023–26 = 4,021/10,084/7,825/4,375. Independent Oracle: 26,313/26,313.
- Frozen replay: 20,441 closed; aggregate WR 68.1522%, AvgNet +1.5283%, PF 1.6097, payoff 0.7522. But year stability fails: 2023 AvgNet **−0.4942%**, 2024 +3.7111%, 2025 +0.8640%, 2026 **−0.6006%**. The aggregate result is dominated by 2024 (7,896 trades), not an all-regime edge.
- T+1=0, targets pre-SOS=1, duplicate symbol-entry=0; independent recomputation matches. It is closed—do not mine 2024, loosen gates, or alter exits.

## Direction after closure

V517–V523 high-volume **spring/reclaim + immediate next-bar response** remains the only current daily-volume lineage that passed frozen all-year research promotion; it remains shadow-only and must obey its exact scanner-time epoch contract. Three delayed confirmation patterns failed despite high seed support. The next valid research ontology must use a genuinely different pre-entry information set or causal object (for example, PIT disclosure/auction/order-flow data with source-completeness gates), not another daily-volume delay, threshold, target, stop, holding-period, or regime variant.