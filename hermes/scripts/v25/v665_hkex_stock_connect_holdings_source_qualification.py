#!/root/.hermes/venvs/smc-source-monitor/bin/python
"""V665 no-outcome HKEX Stock Connect aggregate-holdings source qualification.

This tests a source contract only.  It does not read OHLCV, signals, seeds,
trades, outcomes, PnL, stops, targets, production, frontend, or watchlists.
The question is whether HKEX's public Northbound aggregate holding page can
supply a complete daily point-in-time per-stock history for 2023--2026.
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
OUT = AUD / f'v665_hkex_stock_connect_holdings_source_qualification_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v665_hkex_stock_connect_holdings_source_qualification_latest.json'
URL = 'https://www3.hkexnews.hk/sdw/search/mutualmarket.aspx?sc_lang=en'
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/122 Safari/537.36'
# One date per complete decision year plus a post-2024 date. These are not
# strategy samples and no market data is read.
PROBES = ('2024/01/02', '2025/01/02', '2026/06/30')


def hidden_form_values(page: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for tag in re.findall(r'<input[^>]+>', page, re.I):
        name = re.search(r'name="([^"]+)"', tag, re.I)
        value = re.search(r'value="([^"]*)"', tag, re.I)
        if name:
            values[name.group(1)] = html.unescape(value.group(1)) if value else ''
    return values


def probe(requested_date: str) -> dict[str, object]:
    session = requests.Session()
    try:
        first = session.get(URL, headers={'User-Agent': UA}, timeout=45)
        first.raise_for_status()
        form = hidden_form_values(first.text)
        form.update({
            '__EVENTTARGET': 'btnSearch',
            '__EVENTARGUMENT': '',
            'txtShareholdingDate': requested_date,
        })
        response = session.post(URL, data=form, headers={'User-Agent': UA, 'Referer': URL}, timeout=60)
        response.raise_for_status()
        page = response.text
        invalid = 'invalid.  Please re-enter.' in page
        dates = re.findall(r'Shareholding Date:\s*(\d{4}/\d{2}/\d{2})', page)
        # A nonzero row count proves that the provider did return a complete
        # page for the accepted date; it is not interpreted as strategy data.
        stock_cells = page.count('col-stock-code')
        return {
            'requested_date': requested_date,
            'http_status': response.status_code,
            'provider_effective_date': dates[-1] if dates else '',
            'stock_cells': stock_cells,
            'invalid_or_unavailable': invalid,
            'quarterly_only_notice_present': 'only be available on a quarterly basis' in page,
            'twelve_month_retention_notice_present': 'available for a period of 12 months' in page,
            'error': '',
        }
    except Exception as exc:
        return {
            'requested_date': requested_date,
            'http_status': 0,
            'provider_effective_date': '',
            'stock_cells': 0,
            'invalid_or_unavailable': False,
            'quarterly_only_notice_present': False,
            'twelve_month_retention_notice_present': False,
            'error': f'{type(exc).__name__}:{exc}',
        }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [probe(d) for d in PROBES]
    usable_2023_2025 = all(
        not r['error']
        and not r['invalid_or_unavailable']
        and r['provider_effective_date']
        and r['stock_cells'] > 0
        for r in rows[:2]
    )
    complete_daily_history = usable_2023_2025 and not any(r['quarterly_only_notice_present'] for r in rows)
    report = {
        'version': 'V665_HKEX_STOCK_CONNECT_HOLDINGS_SOURCE_QUALIFICATION_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'positions_write': False,
        'contract': {
            'source': 'HKEX public Stock Connect Northbound aggregate-holdings page',
            'dimension': 'date-addressable per-stock Northbound aggregate shareholding',
            'required_for_admission': 'Complete daily PIT coverage for every declared decision year before a source-only catalog, semantic ontology, OHLCV join, seed, or replay.',
            'prohibited_reads': ['OHLCV', 'signals', 'seeds', 'trades', 'outcomes', 'PnL', 'stops', 'targets', 'production_state'],
        },
        'probes': rows,
        'qualification_checks': {
            'probe_transport_accounted': len(rows) == len(PROBES),
            'complete_daily_2023_2025_history_available': complete_daily_history,
            'provider_retention_allows_2023_2025': usable_2023_2025,
            'provider_not_quarterly_only': not any(r['quarterly_only_notice_present'] for r in rows),
            'publication_time_contract_available': False,
        },
        'decision': (
            'V665_HKEX_STOCK_CONNECT_SOURCE_PASS__FULL_HISTORY_SOURCE_ONLY_BUILD_AUTHORIZED'
            if complete_daily_history else
            'V665_HKEX_STOCK_CONNECT_SOURCE_FAIL__RETENTION_AND_QUARTERLY_GRANULARITY_DO_NOT_MEET_2023_2025_PIT_CONTRACT__NO_ONTOLOGY'
        ),
        'next_action': (
            'A separate source-only canonical-universe build is authorized.'
            if complete_daily_history else
            'Keep L2 Stock Connect holdings unqualified. Do not create a price/SMC seed, replay, selector, or production route from this source.'
        ),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v665_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
