#!/usr/bin/env python3
"""SMC monitor state helpers for daily/manual picks and TP/SL review."""
from __future__ import annotations
import json, pathlib, datetime, uuid, urllib.request

ROOT = pathlib.Path('/root/.hermes')
MON_DIR = ROOT / 'smc_monitor'
STATE = MON_DIR / 'positions.json'
DAILY_DIR = MON_DIR / 'daily'
REVIEW = MON_DIR / 'closed_reviews.json'
LEDGER = MON_DIR / 'trade_ledger.json'


def now_iso():
    return datetime.datetime.now().isoformat(timespec='seconds')


def ymd():
    return datetime.datetime.now().strftime('%Y%m%d')


def date_key(v):
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def t1_exit_allowed(pos, exit_dt=None):
    buy_date = date_key(pos.get('filled_at') or pos.get('created_at'))
    exit_date = date_key(exit_dt or now_iso()) or ymd()
    return bool(buy_date and exit_date and exit_date > buy_date)


def t1_entry_allowed(pick_date, entry_dt=None):
    """A-share production entry hard gate: a pick can only be filled after its pick date."""
    pd = date_key(pick_date)
    ed = date_key(entry_dt or now_iso()) or ymd()
    return bool(pd and ed and ed > pd)


def should_delay_entry_until_next_trading_day(pick_date, source='auto_daily', entry_dt=None):
    """True when an automatic daily pick must stay pending until a later trading day.

    Production auto/manual daily ingestion should not turn a same-day signal into
    an OPEN position during the same session. Manual ad-hoc trades remain under
    explicit operator control.
    """
    if source not in ('auto_daily', 'manual_daily'):
        return False
    return not t1_entry_allowed(pick_date, entry_dt or now_iso())


def market_entry_allowed(ts=None):
    ts = ts or datetime.datetime.now()
    mins = ts.hour * 60 + ts.minute
    return ts.weekday() < 5 and ((570 <= mins < 690) or (780 <= mins < 900))


def load_json(path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def classify_pick(p):
    z = str(p.get('zone_type') or p.get('signal_type') or '').upper()
    role = str(p.get('trade_role') or p.get('entry_type') or '')
    score = float(p.get('score') or p.get('quality_score') or 0)
    rr = float(p.get('rr') or p.get('realized_r') or 0)
    cats = []
    if 'REENTRY' in role:
        cats.append('二次入场')
    if 'OB' in z:
        cats.append('OB')
    if 'FVG' in z:
        cats.append('FVG')
    if 'BPR' in z:
        cats.append('BPR')
    if score >= 12 or rr >= 4:
        cats.append('高质量')
    if not cats:
        cats.append('其它SMC')
    return cats


def pick_key(p):
    return '|'.join(str(x or '') for x in [p.get('symbol'), p.get('pick_date') or p.get('entry_date') or p.get('signal_date'), p.get('zone_idx'), p.get('conf_index'), p.get('entry_type')])


def is_same_day_pick(p):
    return date_key(p.get('select_date') or p.get('pick_date') or p.get('entry_date') or p.get('signal_date')) == ymd()


def sample_class_for_position(pos):
    """Classify whether a monitor position is clean production or diagnostic-only."""
    flags = []
    source = pos.get('source') or ''
    raw = pos.get('raw_pick') or {}
    pick = _parse_ymd(pos.get('pick_date') or raw.get('pick_date') or raw.get('select_date'))
    filled = _parse_ymd(pos.get('filled_at') or pos.get('created_at'))
    today = datetime.datetime.now().date()
    age = _business_age_days(pick, filled or today) if pick else None
    if source in ('manual_daily', 'manual'):
        flags.append('MANUAL_OR_IMPORTED_SOURCE')
    if age is not None and age > 3:
        flags.append(f'STALE_PICK_{age}TRD')
    # A-share T+1 forbids same-day exit after a buy; it does not forbid buying
    # a same-day signal during trading hours. Same-day exit is enforced by
    # t1_exit_allowed().
    zl, zh = _zone_bounds({**raw, **pos})
    if not (zl and zh):
        flags.append('MISSING_ZONE')
    if (pos.get('zone_idx') is None and raw.get('zone_bar') is None) or (pos.get('conf_index') is None and raw.get('entry_idx') is None and raw.get('confirm_idx') is None and raw.get('conf_idx') is None):
        flags.append('MISSING_PROVENANCE')
    if pos.get('status') == 'WATCH_ONLY':
        flags.append('WATCH_ONLY')
    if flags:
        return 'DIAGNOSTIC_ONLY', flags
    return 'PRODUCTION_CLEAN', flags


def _parse_ymd(v):
    s = date_key(v)
    if not s:
        return None
    try:
        return datetime.datetime.strptime(s, '%Y%m%d').date()
    except Exception:
        return None


def _pick_date(p):
    return date_key(p.get('select_date') or p.get('pick_date') or p.get('entry_date') or p.get('conf_date') or p.get('retrace_date') or p.get('signal_date') or p.get('date'))


def _f(v, default=0.0):
    try:
        return float(v or 0)
    except Exception:
        return default


def _zone_bounds(p):
    zl = _f(p.get('execution_zone_low') or p.get('zone_low') or p.get('raw_zone_low') or p.get('dz_low'))
    zh = _f(p.get('execution_zone_high') or p.get('zone_high') or p.get('raw_zone_high') or p.get('dz_high'))
    if zl and zh and zl > zh:
        zl, zh = zh, zl
    return zl, zh


def enrich_pick_fields(p):
    """Normalize production-critical pick fields without changing engine output."""
    p = dict(p)
    p['pick_date'] = _pick_date(p) or p.get('pick_date') or ymd()
    zl, zh = _zone_bounds(p)
    if zl:
        p.setdefault('zone_low', zl)
        p.setdefault('dz_low', zl)
    if zh:
        p.setdefault('zone_high', zh)
        p.setdefault('dz_high', zh)
    if not p.get('zone_type'):
        p['zone_type'] = p.get('signal_type') or p.get('v59_setup_family') or ''
    if p.get('zone_idx') is None and p.get('zone_bar') is not None:
        p['zone_idx'] = p.get('zone_bar')
    if p.get('conf_index') is None:
        for key in ('confirm_idx', 'conf_idx', 'entry_idx'):
            if p.get(key) is not None:
                p['conf_index'] = p.get(key)
                break
    if not p.get('conf_date'):
        p['conf_date'] = p.get('confirm_date') or p.get('entry_date') or p.get('pick_date')
    if not p.get('seq'):
        p['seq'] = p.get('ctx_seq') or p.get('detail') or '->'.join(str(x or '') for x in [p.get('source_event'), p.get('zone_type'), p.get('conf_type')])
    ep = _f(p.get('price') or p.get('entry_price') or p.get('last_close'))
    p.setdefault('price', ep)
    p.setdefault('entry_price', ep)
    risk_pct = _f(p.get('risk_pct') or p.get('sl_initial_pct'))
    sl = _f(p.get('sl'))
    if not risk_pct and ep and sl:
        risk_pct = max(0, (ep - sl) / ep * 100)
        p['risk_pct'] = round(risk_pct, 4)
    if not p.get('smart_money_cost'):
        p['smart_money_cost'] = (zl + zh) / 2 if zl and zh else ep
    if not p.get('market_state') and not p.get('regime'):
        p['market_state'] = p.get('quality_tier') or (f'RISK {risk_pct:.1f}%' if risk_pct else p.get('zone_type', ''))
    return p


def _business_age_days(start, end):
    if not start or not end or start > end:
        return None
    d = start
    n = 0
    while d < end:
        d += datetime.timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def production_entry_gate(p, exec_price=0, source='auto_daily'):
    """Production-only validation before a pick becomes an OPEN/NEXT_DAY_PENDING position.

    This does not alter the signal engine. It only prevents stale/non-auditable/zone-invalid
    candidates from entering the realtime monitor as executable trades.
    """
    if source == 'manual':
        return {'action': 'ACCEPT', 'reasons': [], 'entry_zone_relation': 'MANUAL'}
    p = enrich_pick_fields(p)
    reasons = []
    action = 'ACCEPT'
    pd = _parse_ymd(_pick_date(p))
    today = _parse_ymd(ymd()) or datetime.datetime.now().date()
    age_days = _business_age_days(pd, today) if pd else None
    if pd is None:
        reasons.append('MISSING_PICK_DATE')
    elif age_days is not None and age_days > 3:
        reasons.append(f'STALE_PICK_{age_days}TRD')
    if p.get('pick_scope') not in ('ACTIVE_CANDIDATE', 'ACTIVE_ENTRY', None, ''):
        reasons.append('NOT_ACTIVE_CANDIDATE')
    zl, zh = _zone_bounds(p)
    zone_type = str(p.get('zone_type') or '').upper()
    needs_zone = any(k in zone_type for k in ('FVG', 'OB', 'BPR', 'LIQUIDITYVOID'))
    if needs_zone and not (zl > 0 and zh > 0):
        reasons.append('MISSING_EXECUTABLE_ZONE')
    if needs_zone and not p.get('conf_type'):
        reasons.append('MISSING_CONFIRMATION')
    entry = _f(exec_price or p.get('price') or p.get('entry_price') or p.get('last_close'))
    relation = 'NO_ZONE'
    dist_pct = 0.0
    if entry > 0 and zl > 0 and zh > 0:
        if zl <= entry <= zh:
            relation = 'INSIDE_ZONE'
        elif entry < zl:
            dist_pct = (zl - entry) / entry * 100
            relation = f'BELOW_ZONE_{dist_pct:.2f}%'
            if dist_pct > 2.0:
                reasons.append(f'PRICE_BELOW_ZONE_{dist_pct:.2f}%')
        else:
            dist_pct = (entry - zh) / entry * 100
            relation = f'ABOVE_ZONE_{dist_pct:.2f}%'
            max_above = 3.0 if 'OB' in zone_type else 5.0
            if dist_pct > max_above:
                reasons.append(f'PRICE_ABOVE_ZONE_{dist_pct:.2f}%')
    risk_pct = _f(p.get('risk_pct') or p.get('sl_initial_pct'))
    min_risk = 0.0 if source == 'v526_open' else (0.8 if str(p.get('engine') or '').startswith(('V88', 'V86', 'V85')) or p.get('contract_source') else 2.5)
    if entry and risk_pct and risk_pct < min_risk:
        reasons.append(f'TOO_TIGHT_RISK_{risk_pct:.2f}%')
    if reasons:
        action = 'WATCH_ONLY'
    return {
        'action': action,
        'reasons': reasons,
        'age_days': age_days,
        'entry_zone_relation': relation,
        'entry_zone_distance_pct': round(dist_pct, 3),
        'zone_low': round(zl, 4) if zl else 0,
        'zone_high': round(zh, 4) if zh else 0,
        'checked_entry_price': round(entry, 4) if entry else 0,
    }


def automatic_buy_authorized(p):
    """Require registry + row-level BUY authorization; active metadata is insufficient."""
    registry = load_json(MON_DIR / 'production_registry.json', {})
    epoch = registry.get('data_epoch') or {}
    strategy = str(registry.get('production_strategy') or '')
    row_strategy = str(p.get('production_strategy') or p.get('strategy') or p.get('engine') or '')
    signal_date = date_key(p.get('signal_date') or p.get('pick_date') or p.get('select_date'))
    registry_authorized = (
        registry.get('buy_enabled') is True
        and bool(strategy)
        and row_strategy == strategy
        and epoch.get('valid') is True
        and epoch.get('status') == 'COMMITTED'
        and bool(epoch.get('epoch_id'))
        and str(p.get('data_epoch_id') or '') == str(epoch.get('epoch_id'))
        and signal_date == date_key(epoch.get('market_date'))
        and p.get('current_raw_scanner_source') is True
        and p.get('semantic_oracle_pass') is True
        and p.get('chronology_pass') is True
        and p.get('strict_t1_contract') is True
    )
    return (
        registry_authorized
        and p.get('is_active_pick') is True
        and p.get('pick_scope') in ('ACTIVE_CANDIDATE', 'ACTIVE_ENTRY')
        and str(p.get('live_guard_status') or '') == 'BUY_VALID'
        and str(p.get('trade_action') or '') == 'BUY'
        and p.get('buy_enabled') is True
        and p.get('tradable') is True
    )


def live_execution_price(symbol):
    code = ''.join(ch for ch in str(symbol or '') if ch.isdigit())
    if not code:
        return 0, ''
    prefix = 'sz' if code.startswith(('0', '3')) else ('sh' if code.startswith('6') else 'bj')
    try:
        with urllib.request.urlopen(f'http://qt.gtimg.cn/q={prefix}{code}', timeout=5) as resp:
            parts = resp.read().decode('gbk', errors='replace').split('"')[1].split('~')
        price = float(parts[3] or 0)
        open_price = float(parts[5] or 0)
        if price > 0:
            return price, 'tencent_last'
        if open_price > 0:
            return open_price, 'tencent_open'
    except Exception:
        pass
    stem = str(symbol or '').replace('.', '_')
    for suffix in ('daily_750', 'daily_300'):
        arr = load_json(ROOT / 'kline_cache' / f'{stem}_{suffix}.json', [])
        if arr:
            b = arr[-1]
            price = float(b.get('c') or b.get('o') or 0)
            if price > 0:
                return price, f'kline_{date_key(b.get("t") or b.get("date"))}'
    return 0, ''


def to_position(p, source='auto_daily', operator_note=''):
    p = enrich_pick_fields(p)
    entry = float(p.get('price') or p.get('entry_price') or p.get('last_close') or 0)
    exec_source = 'planned_entry_price'
    if source in ('auto_daily', 'manual_daily') and market_entry_allowed() and not should_delay_entry_until_next_trading_day(p.get('pick_date') or p.get('select_date') or p.get('entry_date'), source):
        live_price, live_source = live_execution_price(p.get('symbol'))
        if live_price > 0:
            entry = live_price
            exec_source = live_source
    gate = production_entry_gate(p, exec_price=entry, source=source)
    sl = float(p.get('sl') or 0)
    risk_pct = float(p.get('risk_pct') or p.get('sl_initial_pct') or 0)
    if source in ('auto_daily', 'manual_daily') and entry and risk_pct and not should_delay_entry_until_next_trading_day(p.get('pick_date') or p.get('select_date') or p.get('entry_date'), source):
        sl = entry * (1 - risk_pct / 100)
    elif not sl and entry and risk_pct:
        sl = entry * (1 - risk_pct / 100)
    tp1 = float(p.get('tp1') or p.get('tp') or 0)
    old_entry = float(p.get('price') or p.get('entry_price') or p.get('last_close') or 0)
    if source in ('auto_daily', 'manual_daily') and old_entry and entry and tp1 and not should_delay_entry_until_next_trading_day(p.get('pick_date') or p.get('select_date') or p.get('entry_date'), source):
        tp1 = entry * (1 + (tp1 - old_entry) / old_entry)
    if not tp1 and entry and p.get('tp_tiers'):
        first = p.get('tp_tiers')[0]
        if isinstance(first, dict):
            tp1 = float(first.get('price') or 0)
    zl, zh = _zone_bounds(p)
    return {
        'id': str(uuid.uuid5(uuid.NAMESPACE_URL, source + '|' + pick_key(p))),
        'source': source,
        'status': 'OPEN',
        'created_at': now_iso(),
        'joined_at': now_iso(),
        'pick_date': p.get('pick_date') or p.get('entry_date') or p.get('signal_date') or ymd(),
        'join_date': p.get('join_date') or p.get('joined_at') or p.get('created_at') or p.get('pick_date') or ymd(),
        'symbol': p.get('symbol'),
        'name': p.get('name', ''),
        'category': classify_pick(p),
        'entry_price': round(entry, 4),
        'execution_price_source': exec_source,
        'sl_price': round(sl, 4),
        'tp1_price': round(tp1, 4),
        'risk_pct': round(risk_pct, 4),
        'zone_type': p.get('zone_type') or p.get('signal_type'),
        'conf_type': p.get('conf_type'),
        'entry_type': p.get('entry_type'),
        'seq': p.get('seq') or p.get('ctx_seq') or p.get('detail') or '',
        'zone_idx': p.get('zone_idx'),
        'conf_index': p.get('conf_index'),
        'zone_low': round(zl, 4) if zl else 0,
        'zone_high': round(zh, 4) if zh else 0,
        'cost_line': round(float(p.get('smart_money_cost') or ((zl + zh) / 2 if zl and zh else entry) or 0), 4),
        'vol_class': p.get('v25_vol_class') or p.get('market_state') or p.get('regime') or p.get('quality_tier') or (f'RISK {risk_pct:.1f}%' if risk_pct else ''),
        'production_gate': gate,
        'entry_zone_relation': gate.get('entry_zone_relation'),
        'entry_zone_distance_pct': gate.get('entry_zone_distance_pct'),
        'sample_class': 'PRODUCTION_CLEAN',
        'sample_issue_flags': [],
        'operator_note': operator_note,
        'raw_pick': p,
    }


def load_trade_ledger():
    return load_json(LEDGER, [])


def append_trade_event(action, pos, live=None):
    live = live or {}
    raw = pos.get('raw_pick') or {}
    event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, '|'.join(str(x or '') for x in [
        pos.get('id'), action, pos.get('closed_at') if action == 'SELL' else pos.get('created_at')
    ])))
    rows = load_trade_ledger()
    if event_id in {x.get('id') for x in rows}:
        return False
    entry = float(pos.get('entry_price') or 0)
    cur = float(live.get('currentPrice') or pos.get('exit_price') or 0)
    pnl = live.get('pnlPct')
    if pnl is None and action == 'SELL' and entry and cur:
        pnl = (cur - entry) / entry * 100
    rows.append({
        'id': event_id,
        'action': action,
        'event_date': date_key(pos.get('closed_at') if action == 'SELL' else (pos.get('filled_at') or pos.get('created_at'))) or ymd(),
        'created_at': now_iso(),
        'symbol': pos.get('symbol'),
        'engine': raw.get('engine') or pos.get('engine') or 'V66',
        'select_date': date_key(raw.get('select_date') or raw.get('pick_date') or pos.get('pick_date')),
        'buy_date': date_key(pos.get('filled_at') or pos.get('created_at')),
        'sell_date': date_key(pos.get('closed_at')) if action == 'SELL' else '',
        'score': raw.get('score') or raw.get('quality_score') or raw.get('breakout_quality_score') or 0,
        'quality': raw.get('entry_quality') or raw.get('quality_tier') or '',
        'retrace_pct': raw.get('retrace_pct') or 0,
        'current_price': cur,
        'zone': pos.get('zone_type') or raw.get('zone_type') or raw.get('signal_type') or '',
        'pnl_pct': round(float(pnl), 3) if pnl not in (None, '') else '',
        'sl': pos.get('sl_price') or raw.get('sl') or 0,
        'tp': pos.get('tp1_price') or raw.get('tp1') or raw.get('tp') or 0,
        'seq': pos.get('seq') or raw.get('seq') or raw.get('ctx_seq') or raw.get('detail') or '',
        'source': pos.get('source'),
        'sample_class': pos.get('sample_class') or sample_class_for_position(pos)[0],
        'sample_issue_flags': pos.get('sample_issue_flags') or sample_class_for_position(pos)[1],
        'pick_date': date_key(pos.get('pick_date') or raw.get('pick_date') or raw.get('select_date')),
        'join_date': date_key(pos.get('joined_at') or pos.get('created_at')),
        'filled_at': pos.get('filled_at') or '',
        'zone_low': pos.get('zone_low') or raw.get('zone_low') or raw.get('dz_low') or 0,
        'zone_high': pos.get('zone_high') or raw.get('zone_high') or raw.get('dz_high') or 0,
        'entry_zone_relation': pos.get('entry_zone_relation') or '',
        'production_gate': pos.get('production_gate') or {},
        'reason': pos.get('close_reason') if action == 'SELL' else 'BUY',
        'position_id': pos.get('id'),
    })
    save_json(LEDGER, rows)
    return True


def load_positions():
    return load_json(STATE, [])


def save_positions(rows):
    save_json(STATE, rows)


def fill_pending_orders():
    if not market_entry_allowed():
        return {'changed': 0, 'reason': 'MARKET_NOT_OPEN_FOR_ENTRY'}
    rows = load_positions()
    changed = 0
    filled = []
    validation_only = []
    today = ymd()
    for pos in rows:
        if pos.get('status') != 'NEXT_DAY_PENDING':
            continue
        pick_date = date_key(pos.get('pick_date') or (pos.get('raw_pick') or {}).get('select_date'))
        if not pick_date or not t1_entry_allowed(pick_date, today):
            pos['pending_reason'] = 'SAME_DAY_PICK_NO_BUY' if pick_date == today else (pos.get('pending_reason') or 'WAIT_T1_ENTRY')
            continue
        old_entry = float(pos.get('entry_price') or 0)
        live_price, live_source = live_execution_price(pos.get('symbol'))
        if live_price <= 0:
            continue
        raw = dict(pos.get('raw_pick') or {})
        raw.setdefault('symbol', pos.get('symbol'))
        raw.setdefault('pick_date', pos.get('pick_date'))
        raw.setdefault('zone_type', pos.get('zone_type'))
        raw.setdefault('conf_type', pos.get('conf_type'))
        raw.setdefault('zone_low', pos.get('zone_low'))
        raw.setdefault('zone_high', pos.get('zone_high'))
        raw.setdefault('risk_pct', pos.get('risk_pct'))
        gate = production_entry_gate(raw, exec_price=live_price, source=pos.get('source') or 'auto_daily')
        pos['production_gate'] = gate
        pos['entry_zone_relation'] = gate.get('entry_zone_relation')
        pos['entry_zone_distance_pct'] = gate.get('entry_zone_distance_pct')
        if gate.get('action') != 'ACCEPT':
            pos['status'] = 'WATCH_ONLY'
            pos['pending_reason'] = 'PRODUCTION_GATE_REJECTED'
            pos['reject_reason'] = ';'.join(gate.get('reasons') or [])
            pos['rejected_at'] = now_iso()
            pos['sample_class'], pos['sample_issue_flags'] = sample_class_for_position(pos)
            validation_only.append(pos.get('symbol'))
            changed += 1
            continue
        risk_pct = float(pos.get('risk_pct') or 0)
        old_tp1 = float(pos.get('tp1_price') or 0)
        pos['joined_at'] = pos.get('joined_at') or pos.get('created_at')
        pos['created_at'] = now_iso()
        pos['status'] = 'OPEN'
        pos['entry_price'] = round(live_price, 4)
        pos['execution_price_source'] = live_source or 'next_day_live_price'
        if risk_pct:
            pos['sl_price'] = round(live_price * (1 - risk_pct / 100), 4)
        if old_entry and old_tp1:
            pos['tp1_price'] = round(live_price * (1 + (old_tp1 - old_entry) / old_entry), 4)
        pos['filled_from_status'] = 'NEXT_DAY_PENDING'
        pos['filled_at'] = pos['created_at']
        pos['pending_reason'] = ''
        pos['sample_class'], pos['sample_issue_flags'] = sample_class_for_position(pos)
        append_trade_event('BUY', pos)
        changed += 1
        filled.append(pos.get('symbol'))
    if changed:
        save_positions(rows)
    return {'changed': changed, 'filled': filled, 'validation_only': validation_only}


def ingest_daily_picks(picks, source='auto_daily'):
    positions = load_positions()
    existing = {x.get('id') for x in positions}
    existing_live_keys = {(x.get('symbol'), date_key(x.get('pick_date')), x.get('zone_type')) for x in positions if x.get('status') in ('OPEN', 'NEXT_DAY_PENDING')}
    added = []
    pending = []
    validation_only = []
    rejected = []
    categorized = {}
    active_looking = [enrich_pick_fields(p) for p in picks if p.get('is_active_pick') and p.get('pick_scope') in ('ACTIVE_CANDIDATE', 'ACTIVE_ENTRY')]
    unauthorized = [] if source == 'manual' else [p for p in active_looking if not automatic_buy_authorized(p)]
    active = active_looking if source == 'manual' else [p for p in active_looking if automatic_buy_authorized(p)]
    for p in unauthorized:
        rejected.append({
            'symbol': p.get('symbol'), 'pick_date': p.get('pick_date'),
            'zone_type': p.get('zone_type'), 'reasons': ['BUY_VALID_AUTHORIZATION_MISSING'],
            'relation': '',
        })
    existing_pending_count = 0
    for p in active:
        pos = to_position(p, source=source)
        gate = pos.get('production_gate') or production_entry_gate(p, exec_price=pos.get('entry_price'), source=source)
        market_closed_pending = source in ('auto_daily', 'manual_daily') and (not market_entry_allowed() or should_delay_entry_until_next_trading_day(pos.get('pick_date'), source))
        if gate.get('action') != 'ACCEPT':
            pos['status'] = 'WATCH_ONLY'
            pos['pending_reason'] = 'PRODUCTION_GATE_REJECTED'
            pos['reject_reason'] = ';'.join(gate.get('reasons') or [])
            pos['rejected_at'] = now_iso()
            pos['sample_class'], pos['sample_issue_flags'] = sample_class_for_position(pos)
            validation_only.append(pos)
            rejected.append({'symbol': pos.get('symbol'), 'pick_date': pos.get('pick_date'), 'zone_type': pos.get('zone_type'), 'reasons': gate.get('reasons') or [], 'relation': gate.get('entry_zone_relation')})
        elif market_closed_pending:
            pos['status'] = 'NEXT_DAY_PENDING'
            pos['pending_reason'] = 'WAIT_NEXT_TRADING_DAY_ENTRY' if should_delay_entry_until_next_trading_day(pos.get('pick_date'), source) else 'MARKET_CLOSED_WAIT_NEXT_OPEN'
            pos['pending_at'] = now_iso()
            pos['sample_class'] = 'PENDING_T1'
            pos['sample_issue_flags'] = []
            pos['filled_at'] = ''
        else:
            pos['sample_class'], pos['sample_issue_flags'] = sample_class_for_position(pos)
        live_key = (pos.get('symbol'), date_key(pos.get('pick_date')), pos.get('zone_type'))
        if live_key in existing_live_keys:
            existing_pending_count += sum(1 for x in positions if x.get('status') == 'NEXT_DAY_PENDING' and (x.get('symbol'), date_key(x.get('pick_date')), x.get('zone_type')) == live_key)
        if pos['id'] not in existing and live_key not in existing_live_keys and pos.get('symbol'):
            positions.append(pos)
            existing.add(pos['id'])
            existing_live_keys.add(live_key)
            added.append(pos)
            if pos.get('status') == 'NEXT_DAY_PENDING':
                pending.append(pos)
            elif pos.get('status') == 'OPEN':
                append_trade_event('BUY', pos)
        for c in pos['category']:
            categorized.setdefault(c, []).append(pos)
    save_positions(positions)
    daily = {
        'date': ymd(),
        'generated_at': now_iso(),
        'source': source,
        'added': len(added),
        'buy_added': sum(1 for p in added if p.get('status') == 'OPEN'),
        'pending_count': len(pending),
        'validation_only': len(validation_only),
        'rejected_count': len(rejected),
        'rejected': rejected,
        'existing_pending_count': existing_pending_count,
        'active_count': len(active),
        'active_looking_count': len(active_looking),
        'unauthorized_count': len(unauthorized),
        'categories': categorized,
        'positions': added,
    }
    save_json(DAILY_DIR / f'{ymd()}_{source}.json', daily)
    return daily


def add_manual_pick(symbol, entry_price=0, sl_price=0, tp1_price=0, note=''):
    p = {'symbol': symbol.upper(), 'price': float(entry_price or 0), 'entry_price': float(entry_price or 0), 'sl': float(sl_price or 0), 'tp1': float(tp1_price or 0), 'pick_date': ymd(), 'zone_type': 'MANUAL', 'entry_type': 'MANUAL', 'conf_type': 'MANUAL', 'pick_scope': 'ACTIVE_CANDIDATE', 'is_active_pick': True}
    pos = to_position(p, source='manual', operator_note=note)
    rows = load_positions()
    if pos['id'] not in {x.get('id') for x in rows}:
        rows.append(pos)
        save_positions(rows)
        append_trade_event('BUY', pos)
    return pos


def close_review(pos, live, reason):
    entry = float(pos.get('entry_price') or 0)
    cur = float(live.get('currentPrice') or 0)
    pnl = (cur - entry) / entry * 100 if entry and cur else 0
    if reason == 'SL_HIT':
        cause = '止损触发：先判定为信号/入场/市场结构三类待复盘；若价格直接跌破zone且未reclaim，优先信号质量或zone失效；若入场后很快止损，优先入场位置问题。'
        fix = '自动迭代方向：回放该symbol的source_event→zone→confirm→entry链路，检查zone是否已失效、entry是否追高、SL是否低于真实结构低点；不通过则加入下一版质量过滤。'
    else:
        cause = '止盈触发：检查是否符合原始TP1/runner计划，以及是否卖早。'
        fix = '自动迭代方向：进入90D闭环复盘，若后续仍有新SMC setup则归入re-entry，不强行延长原单。'
    sample_class, sample_flags = sample_class_for_position(pos)
    root_cause = 'VALID_SIGNAL_FAILED'
    if 'T1_SAME_DAY_FILL' in sample_flags:
        root_cause = 'T1_EXECUTION_VIOLATION'
    elif any(f.startswith('STALE_PICK') or f == 'MANUAL_OR_IMPORTED_SOURCE' for f in sample_flags):
        root_cause = 'HISTORICAL_POLLUTION'
    elif 'MISSING_ZONE' in sample_flags:
        root_cause = 'MISSING_ZONE'
    elif str(pos.get('entry_zone_relation') or '').startswith('BELOW_ZONE'):
        root_cause = 'ZONE_INVALIDATED_BELOW_ENTRY'
    elif str(pos.get('entry_zone_relation') or '').startswith('ABOVE_ZONE'):
        root_cause = 'PRICE_TOO_FAR_ABOVE_ZONE'
    return {'id': pos.get('id'), 'symbol': pos.get('symbol'), 'closed_at': now_iso(), 'reason': reason, 'entry_price': entry, 'exit_price': cur, 'pnl_pct': round(pnl, 3), 'planned_sl': pos.get('sl_price'), 'planned_tp1': pos.get('tp1_price'), 'design_match': (cur <= float(pos.get('sl_price') or 0) if reason == 'SL_HIT' else cur >= float(pos.get('tp1_price') or 0)), 'sample_class': sample_class, 'sample_issue_flags': sample_flags, 'root_cause': root_cause, 'entry_zone_relation': pos.get('entry_zone_relation') or '', 'diagnosis': cause, 'repair_plan': fix, 'position': pos, 'live': live}


def update_with_live_results(live_picks):
    fill_result = fill_pending_orders()
    rows = load_positions()
    reviews = load_json(REVIEW, [])
    changed = 0
    open_by_symbol = {}
    for idx, p in enumerate(rows):
        if p.get('status') == 'OPEN':
            open_by_symbol.setdefault(p.get('symbol'), []).append((idx, p))
    for live in live_picks:
        st = live.get('status')
        if st not in ('SL_HIT', 'TP_HIT'):
            continue
        arr = open_by_symbol.get(live.get('symbol'), [])
        if not arr:
            continue
        idx, pos = arr[0]
        if not t1_exit_allowed(pos):
            continue
        rows[idx]['status'] = 'CLOSED'
        rows[idx]['closed_at'] = now_iso()
        rows[idx]['close_reason'] = st
        rows[idx]['exit_price'] = live.get('currentPrice')
        review = close_review(rows[idx], live, st)
        rows[idx]['review_id'] = review['id'] + '|' + review['closed_at']
        reviews.append(review)
        append_trade_event('SELL', rows[idx], live)
        changed += 1
    if changed:
        save_positions(rows)
        save_json(REVIEW, reviews)
    return {'changed': changed, 'pending_fill': fill_result, 'open': sum(1 for p in rows if p.get('status') == 'OPEN'), 'closed': sum(1 for p in rows if p.get('status') == 'CLOSED')}


def summary():
    rows = load_positions()
    daily_files = sorted(DAILY_DIR.glob('*.json'), reverse=True)[:20] if DAILY_DIR.exists() else []
    cats = {}
    for p in rows:
        if p.get('status') == 'OPEN':
            for c in p.get('category') or ['未分类']:
                cats[c] = cats.get(c, 0) + 1
    return {
        'total': len(rows),
        'open': sum(1 for p in rows if p.get('status') == 'OPEN'),
        'pending': sum(1 for p in rows if p.get('status') == 'NEXT_DAY_PENDING'),
        'watch_only': sum(1 for p in rows if p.get('status') == 'WATCH_ONLY'),
        'closed': sum(1 for p in rows if p.get('status') == 'CLOSED'),
        'categories': cats,
        'daily_files': [str(f) for f in daily_files],
        'review_count': len(load_json(REVIEW, [])),
    }
