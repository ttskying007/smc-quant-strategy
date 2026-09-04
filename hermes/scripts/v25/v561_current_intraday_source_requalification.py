#!/usr/bin/env python3
"""V561: source-only requalification.  No candidates, outcomes, or replay."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
OUT = AUD / f'v561_current_intraday_source_requalification_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v561_current_intraday_source_requalification_latest.json'
SYMBOLS = ['000001.SZ', '600519.SH', '920982.BJ']
REQUIRED_START = '2023-01-01'


def sina_symbol(symbol: str) -> str:
    code, ex = symbol.split('.')
    return f"{'sh' if ex == 'SH' else 'sz' if ex == 'SZ' else 'bj'}{code}"


def date_range(rows: object) -> dict:
    if not isinstance(rows, list) or not rows:
        return {'bar_count': 0, 'start': None, 'end': None}
    dates = sorted(str(x.get('day', ''))[:10] for x in rows if isinstance(x, dict) and x.get('day'))
    return {'bar_count': len(rows), 'start': dates[0] if dates else None, 'end': dates[-1] if dates else None}


def sina_probe(session: requests.Session, symbol: str) -> dict:
    try:
        response = session.get(
            'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData',
            params={'symbol': sina_symbol(symbol), 'scale': 15, 'ma': 'no', 'datalen': 10000}, timeout=45,
        )
        response.raise_for_status()
        return {'symbol': symbol, 'http_status': response.status_code, 'error': '', **date_range(response.json())}
    except Exception as exc:
        return {'symbol': symbol, 'http_status': None, 'error': f'{type(exc).__name__}:{exc}', 'bar_count': 0, 'start': None, 'end': None}


def tencent_probe(session: requests.Session, symbol: str) -> dict:
    code, ex = symbol.split('.')
    prefix = 'sh' if ex == 'SH' else 'sz' if ex == 'SZ' else 'bj'
    try:
        response = session.get(
            'https://ifzq.gtimg.cn/appstock/app/kline/mkline',
            params={'param': f'{prefix}{code},m15,,,10000'}, timeout=45,
        )
        response.raise_for_status()
        payload = response.json().get('data') or {}
        raw = next(iter(payload.values()), {}) if isinstance(payload, dict) else {}
        rows = raw.get('m15') or []
        dates = sorted(str(x[0])[:10] for x in rows if isinstance(x, list) and x)
        return {'symbol': symbol, 'http_status': response.status_code, 'error': '', 'bar_count': len(rows), 'start': dates[0] if dates else None, 'end': dates[-1] if dates else None}
    except Exception as exc:
        return {'symbol': symbol, 'http_status': None, 'error': f'{type(exc).__name__}:{exc}', 'bar_count': 0, 'start': None, 'end': None}


def qualified(rows: list[dict]) -> bool:
    return all(not x['error'] and x['start'] and x['start'] <= REQUIRED_START for x in rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=False)
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0'})
    # Each probe requests the provider's maximum advertised window. It opens no research artifacts.
    sina = [sina_probe(session, s) for s in SYMBOLS]
    tencent = [tencent_probe(session, s) for s in SYMBOLS]
    report = {
        'version': 'V561_CURRENT_INTRADAY_SOURCE_REQUALIFICATION_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'purpose': 'Fresh provider-window check only; it opens no seed, trade, outcome, or replay artifact.',
        'predeclared_gate': {
            'required_start': REQUIRED_START,
            'minimum': 'Each representative SH/SZ/BJ response must reach 2023-01-01 or earlier before a provider can proceed to canonical-universe/slot qualification.',
            'no_cross_source_mixing': True,
        },
        'sources': {'sina_m15': sina, 'tencent_m15': tencent},
        'gate': {
            'sina_reaches_required_history': qualified(sina),
            'tencent_reaches_required_history': qualified(tencent),
            'canonical_universe_slot_audit_authorized': qualified(sina) or qualified(tencent),
            'outcome_blind_new_ontology_authorized': qualified(sina) or qualified(tencent),
        },
        'decision': 'SOURCE_HISTORY_GATE_PASS__CAN_PROCEED_TO_CANONICAL_UNIVERSE_SLOT_AUDIT' if qualified(sina) or qualified(tencent) else 'SOURCE_HISTORY_GATE_FAIL__NO_NEW_REPLAY_OR_ONTOLOGY_AUTHORIZED',
        'artifacts': {'out_dir': str(OUT), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v561_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
