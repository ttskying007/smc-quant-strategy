#!/usr/bin/env python3
"""Refresh A-share 750-bar daily kline cache from Tencent fqkline.

Uses curl -L because Python urllib is unreliable with Tencent redirects in this environment.
Default updates the full cached universe. Use --only-stale to skip files already at the latest
observed cache date.
"""
from __future__ import annotations
import argparse, concurrent.futures, datetime as dt, json, os, pathlib, shutil, subprocess, tempfile, time, urllib.parse, urllib.request
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

KLINE_DIR = pathlib.Path('/root/.hermes/kline_cache')
MONITOR_DIR = pathlib.Path('/root/.hermes/smc_monitor')
EPOCH_DIR = MONITOR_DIR / 'kline_epochs'
CURRENT_MANIFEST = MONITOR_DIR / 'kline_epoch_current.json'
BARS = 750
SINA_URL = 'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData'
MIN_REFRESH_COVERAGE = 0.90
MIN_CURRENT_DATE_COVERAGE = 0.99
MAX_LATEST_AGE_DAYS = 4


def symbol_from_file(fp: pathlib.Path):
    name = fp.stem.replace('_daily_750','').replace('_daily_300','')
    if '_SH' in name:
        return name.replace('_SH',''), 'sh'
    if '_SZ' in name:
        return name.replace('_SZ',''), 'sz'
    if '_BJ' in name:
        return name.replace('_BJ',''), 'bj'
    return None


def out_path(code, market):
    sym = f'{code}.{market.upper()}'
    fname = sym.replace('.SH','_SH').replace('.SZ','_SZ').replace('.BJ','_BJ')
    return KLINE_DIR / f'{fname}_daily_{BARS}.json'


def latest_date(fp):
    try:
        arr = json.loads(fp.read_text())
        if not arr: return ''
        return str(arr[-1].get('t') or arr[-1].get('date') or '')[:8]
    except Exception:
        return ''


def parse_tencent(raw, code, market):
    data = json.loads(raw)
    key = f'{market}{code}'
    stock = (data.get('data') or {}).get(key) or {}
    rows = stock.get('qfqday') or stock.get('day') or []
    out = []
    for k in rows:
        if len(k) < 5: continue
        out.append({'t': str(k[0]).replace('-',''), 'o': float(k[1]), 'c': float(k[2]),
                    'h': float(k[3]), 'l': float(k[4]), 'v': float(k[5]) if len(k)>5 else 0})
    return out


def tencent_market_is_open(raw):
    """Read Tencent's market-status witness; do not trust host clock for a daily close."""
    try:
        data = json.loads(raw)
        market = ((data.get('data') or {}).get('market') or [''])[0]
        return '_open_交易中' in str(market)
    except (json.JSONDecodeError, TypeError, AttributeError, IndexError):
        return None


def parse_sina(raw):
    rows = json.loads(raw)
    if not isinstance(rows, list):
        return []
    out = []
    for k in rows:
        try:
            out.append({'t': str(k['day'])[:10].replace('-',''), 'o': float(k['open']),
                        'c': float(k['close']), 'h': float(k['high']), 'l': float(k['low']),
                        'v': float(k.get('volume') or 0)})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def aligned_with_existing(path, rows, allow_latest_update=False):
    if not path.exists():
        return True
    try:
        old = {str(x.get('t') or x.get('date'))[:8]: x for x in json.loads(path.read_text())}
        latest = max(old, default='')
        overlap = [x for x in rows if x['t'] in old and not (allow_latest_update and x['t'] == latest)][-5:]
        for row in overlap:
            prior = old[row['t']]
            for key in ('o', 'c', 'h', 'l'):
                a, b = float(row[key]), float(prior[key])
                if abs(a - b) > max(0.02, abs(b) * 0.0001):
                    return False
        return True
    except Exception:
        return False


def merge_new_rows(path, rows, replace_latest=False):
    if not path.exists():
        return rows
    old = json.loads(path.read_text())
    latest = max((str(x.get('t') or x.get('date'))[:8] for x in old), default='')
    updates = {x['t']: x for x in rows if x['t'] > latest or (replace_latest and x['t'] == latest)}
    return [updates.pop(str(x.get('t') or x.get('date'))[:8], x) for x in old] + [updates[d] for d in sorted(updates)]


def write_atomic(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, prefix=path.name + '.', suffix='.tmp', delete=False) as handle:
        temp = pathlib.Path(handle.name)
        json.dump(rows, handle, ensure_ascii=False)
    temp.replace(path)


def completed_market_cutoff(now=None):
    now = now or datetime.now(ZoneInfo('Asia/Shanghai'))
    today = now.strftime('%Y%m%d')
    if now.weekday() < 5 and now.time() < dt.time(15, 10):
        return (now.date() - dt.timedelta(days=1)).strftime('%Y%m%d')
    return today


def keep_completed_rows(rows, cutoff=None, market_open=None):
    cutoff = cutoff or completed_market_cutoff()
    # The provider can be behind or the host clock can be wrong. A bar dated
    # today remains mutable until Tencent itself reports the market closed.
    if market_open is True:
        today = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d')
        previous_day = (dt.datetime.strptime(today, '%Y%m%d').date() - dt.timedelta(days=1)).strftime('%Y%m%d')
        cutoff = min(cutoff, previous_day)
    return [row for row in rows if row.get('t', '') <= cutoff][-BARS:]


def evaluate_refresh_gate(requested, ok, latest_counts, before_latest_counts, now=None):
    """Require a coherent, recent market date instead of request success alone."""
    now = now or datetime.now(ZoneInfo('Asia/Shanghai'))
    latest_counts = Counter(latest_counts or {})
    before_latest_counts = Counter(before_latest_counts or {})
    request_coverage = ok / requested if requested else 1.0
    observed_latest = max((str(x)[:8] for x in latest_counts if str(x)[:8].isdigit()), default='')
    before_latest = max((str(x)[:8] for x in before_latest_counts if str(x)[:8].isdigit()), default='')
    current_count = latest_counts.get(observed_latest, 0) if observed_latest else 0
    current_coverage = current_count / requested if requested else 1.0
    failures = []
    if not ok or not observed_latest:
        failures.append('NO_SUCCESSFUL_REFRESH')
    if request_coverage < MIN_REFRESH_COVERAGE:
        failures.append('REQUEST_COVERAGE_BELOW_MIN')
    if current_coverage < MIN_CURRENT_DATE_COVERAGE:
        failures.append('CURRENT_DATE_COVERAGE_BELOW_MIN')
    if before_latest and observed_latest and observed_latest < before_latest:
        failures.append('LATEST_DATE_REGRESSED')
    if observed_latest:
        observed_day = dt.datetime.strptime(observed_latest, '%Y%m%d').date()
        age_days = (now.date() - observed_day).days
        if age_days < 0:
            failures.append('LATEST_DATE_IN_FUTURE')
        elif age_days > MAX_LATEST_AGE_DAYS:
            failures.append('LATEST_DATE_STALE')
    else:
        age_days = None
    return {
        'gate_pass': not failures,
        'gate_failures': failures,
        'observed_latest_date': observed_latest,
        'latest_age_days': age_days,
        'request_coverage_pct': round(request_coverage * 100, 2),
        'current_date_count': current_count,
        'current_date_coverage_pct': round(current_coverage * 100, 2),
    }


def fetch_one(item, stage_dir=None):
    code, market = item
    url = f'http://ifzq.gtimg.cn/appstock/app/fqkline/get?param={market}{code},day,,,{BARS + 1},qfq'
    cmd = ['curl','-sSL','--max-time','15',url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        rows = []
        provider_market_open = None
        if r.returncode == 0 and r.stdout.strip():
            try:
                rows = parse_tencent(r.stdout, code, market)
                provider_market_open = tencent_market_is_open(r.stdout)
            except (json.JSONDecodeError, TypeError, ValueError):
                rows = []
        source = 'tencent'
        # Tencent may serve one current-day bar for BJ. Discard it while its
        # market-status witness is open before deciding whether a history
        # fallback is necessary.
        rows = keep_completed_rows(rows, market_open=provider_market_open)
        existing = out_path(code, market)
        # During an open session Tencent currently gives many BJ symbols only the
        # mutable intraday bar. It is not a completed daily observation. Preserve
        # the already committed previous close instead of falling back to Sina
        # (whose adjusted history is a different series and correctly fails the
        # alignment guard).
        if not rows and provider_market_open is True and existing.exists():
            target = pathlib.Path(stage_dir) / existing.name if stage_dir else existing
            if stage_dir:
                shutil.copy2(existing, target)
            preserved = json.loads(existing.read_text())
            return {'ok': True, 'code': code, 'market': market, 'rows': len(preserved),
                    'latest': latest_date(existing), 'source': 'tencent_open_preserve_existing',
                    'short_listing_history': valid_short_listing_history(preserved),
                    'staged_path': str(target), 'target_path': str(existing)}
        if len(rows) < 100 and not (rows and existing.exists()):
            symbol = f'{market}{code}'
            sina_url = SINA_URL + '?' + urllib.parse.urlencode({'symbol': symbol, 'scale': 240, 'ma': 'no', 'datalen': BARS + 1})
            req = urllib.request.Request(sina_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=25) as response:
                rows = parse_sina(response.read().decode('utf-8', errors='replace'))
            source = 'sina_fallback'
        rows = keep_completed_rows(rows, market_open=provider_market_open if source == 'tencent' else None)
        p = existing
        # Tencent sometimes returns the full qfq history, but for selected
        # instruments (notably BJ) it returns only the current daily row. A
        # one-row response must be append-merged, never overwrite 750 bars.
        partial_tencent = source == 'tencent' and len(rows) < 100
        # A partial Tencent reply is allowed to replace only its own most
        # recent cached daily bar. Older overlap must still align exactly;
        # this prevents a one-row reply from rewriting history while allowing
        # the official close to supersede a late intraday snapshot.
        if source == 'sina_fallback' or partial_tencent:
            if not aligned_with_existing(p, rows, allow_latest_update=partial_tencent):
                return {'ok': False, 'code': code, 'market': market, 'error': f'{source}_price_alignment_failed'}
            rows = merge_new_rows(p, rows, replace_latest=partial_tencent)
        short_listing = valid_short_listing_history(rows)
        if len(rows) < 100 and not short_listing:
            return {'ok': False, 'code': code, 'market': market, 'error': f'rows={len(rows)}'}
        target = pathlib.Path(stage_dir) / p.name if stage_dir else p
        write_atomic(target, rows)
        return {'ok': True, 'code': code, 'market': market, 'rows': len(rows), 'latest': rows[-1]['t'],
                'source': source, 'short_listing_history': short_listing, 'staged_path': str(target), 'target_path': str(p)}
    except Exception as e:
        return {'ok': False, 'code': code, 'market': market, 'error': str(e)[:200]}


def valid_short_listing_history(rows, now=None):
    """Accept a genuinely recent IPO history, never a one-bar provider truncation.

    A full 750-bar series is impossible for new listings.  Those rows are
    eligible only when they are a coherent daily sequence with enough history
    and begin within the past year; a short reply for an established symbol
    still fails closed.
    """
    now = now or datetime.now(ZoneInfo('Asia/Shanghai')).date()
    if not (20 <= len(rows) < 100):
        return False
    dates = [str(x.get('t') or x.get('date') or '')[:8] for x in rows]
    if any(len(day) != 8 or not day.isdigit() for day in dates):
        return False
    if dates != sorted(set(dates)):
        return False
    try:
        first = dt.datetime.strptime(dates[0], '%Y%m%d').date()
    except ValueError:
        return False
    return first >= now - dt.timedelta(days=370)


def read_json(path, default=None):
    try:
        return json.loads(pathlib.Path(path).read_text())
    except Exception:
        return default


def recover_incomplete_promotions():
    """Rollback an interrupted promotion unless its current manifest was committed."""
    current = read_json(CURRENT_MANIFEST, {}) or {}
    if not EPOCH_DIR.exists():
        return []
    recovered = []
    for journal_path in EPOCH_DIR.glob('*/promotion_journal.json'):
        journal = read_json(journal_path, {}) or {}
        if journal.get('state') != 'PREPARING':
            continue
        epoch_id = journal.get('epoch_id')
        if current.get('epoch_id') == epoch_id and current.get('status') == 'COMMITTED':
            journal['state'] = 'COMMITTED'
            write_atomic(journal_path, journal)
            continue
        backup_dir = journal_path.parent / 'backup'
        for item in journal.get('targets', []):
            target = pathlib.Path(item['target'])
            backup = backup_dir / target.name
            if item.get('existed') and backup.exists():
                os.replace(backup, target)
            elif not item.get('existed') and target.exists():
                target.unlink()
        journal['state'] = 'ROLLED_BACK'
        journal['recovered_at'] = datetime.now().isoformat(timespec='seconds')
        write_atomic(journal_path, journal)
        recovered.append(epoch_id)
    return recovered


def promote_epoch(epoch_id, stage_dir, successful, gate):
    """Promote a gated epoch; current manifest is the final atomic commit point."""
    backup_dir = pathlib.Path(stage_dir) / 'backup'
    backup_dir.mkdir(parents=True, exist_ok=True)
    targets = []
    for result in successful:
        target = pathlib.Path(result['target_path'])
        targets.append({'target': str(target), 'existed': target.exists()})
        if target.exists():
            os.link(target, backup_dir / target.name)
    journal_path = pathlib.Path(stage_dir) / 'promotion_journal.json'
    journal = {'epoch_id': epoch_id, 'state': 'PREPARING', 'targets': targets}
    write_atomic(journal_path, journal)
    try:
        for result in successful:
            os.replace(result['staged_path'], result['target_path'])
        manifest = {
            'epoch_id': epoch_id,
            'status': 'COMMITTED',
            'committed_at': datetime.now().isoformat(timespec='seconds'),
            'market_date': gate['observed_latest_date'],
            'file_count': len(successful),
            'gate': gate,
        }
        write_atomic(CURRENT_MANIFEST, manifest)
        journal['state'] = 'COMMITTED'
        write_atomic(journal_path, journal)
        shutil.rmtree(backup_dir, ignore_errors=True)
        return manifest
    except Exception:
        for item in targets:
            target = pathlib.Path(item['target'])
            backup = backup_dir / target.name
            if item['existed'] and backup.exists():
                os.replace(backup, target)
            elif not item['existed'] and target.exists():
                target.unlink()
        journal['state'] = 'ROLLED_BACK'
        write_atomic(journal_path, journal)
        raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=20)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--only-stale', action='store_true')
    ap.add_argument('--inject-gate-failure', action='store_true', help=argparse.SUPPRESS)
    args = ap.parse_args()

    recovered_epochs = recover_incomplete_promotions()

    symbols = {}
    for pat in ('*_daily_750.json', '*_daily_300.json'):
        for fp in KLINE_DIR.glob(pat):
            x = symbol_from_file(fp)
            if x: symbols[x] = True
    items = sorted(symbols)
    before_latest = Counter(latest_date(out_path(c,m)) for c,m in items if out_path(c,m).exists())
    target_latest = ''
    if before_latest:
        target_latest = before_latest.most_common(1)[0][0]
    if args.only_stale and target_latest:
        items = [(c,m) for c,m in items if latest_date(out_path(c,m)) < target_latest]
    if args.limit:
        items = items[:args.limit]

    epoch_id = datetime.now().strftime('%Y%m%dT%H%M%S_%f')
    stage_dir = EPOCH_DIR / epoch_id
    stage_dir.mkdir(parents=True, exist_ok=False)
    start = time.time()
    ok = fail = 0; latest = Counter(); errors = Counter(); sources = Counter(); latest_by_market = {}
    samples = []; successful = []
    print(f'Refreshing {len(items)} stocks (workers={args.workers}, only_stale={args.only_stale}, target_latest={target_latest})', flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_one, it, stage_dir): it for it in items}
        for i, fut in enumerate(concurrent.futures.as_completed(futs), 1):
            res = fut.result()
            if res.get('ok'):
                ok += 1; latest[res.get('latest','')] += 1; sources[res.get('source','unknown')] += 1
                market = res.get('market', 'unknown')
                latest_by_market.setdefault(market, Counter())[res.get('latest', '')] += 1
                successful.append(res)
            else:
                fail += 1; errors[res.get('error','UNKNOWN')] += 1
                if len(samples) < 20: samples.append(res)
            if i % 500 == 0:
                print(f'  {i}/{len(items)} ok={ok} fail={fail}', flush=True)
    coverage = ok / len(items) if items else 1.0
    gate = evaluate_refresh_gate(len(items), ok, latest, before_latest)
    if args.inject_gate_failure:
        gate['gate_pass'] = False
        gate['gate_failures'] = list(gate['gate_failures']) + ['INJECTED_GATE_FAILURE']
    gate_pass = gate['gate_pass']
    manifest = None
    if gate_pass:
        manifest = promote_epoch(epoch_id, stage_dir, successful, gate)
        epoch_status = 'COMMITTED'
    else:
        shutil.rmtree(stage_dir, ignore_errors=True)
        epoch_status = 'REJECTED'
    summary = {'generated_at': datetime.now().isoformat(timespec='seconds'), 'requested': len(items),
               'ok': ok, 'failed': fail, 'elapsed_sec': round(time.time()-start,1),
               'coverage_pct': round(coverage * 100, 2), 'gate_pass': gate_pass,
               'gate_failures': gate['gate_failures'],
               'observed_latest_date': gate['observed_latest_date'],
               'latest_age_days': gate['latest_age_days'],
               'current_date_count': gate['current_date_count'],
               'current_date_coverage_pct': gate['current_date_coverage_pct'],
               'epoch_id': epoch_id, 'epoch_status': epoch_status,
               'current_manifest': manifest, 'recovered_epochs': recovered_epochs,
               'before_latest_counts': dict(before_latest), 'latest_counts': dict(latest),
               'latest_counts_by_market': {market: dict(counts) for market, counts in sorted(latest_by_market.items())},
               'source_counts': dict(sources), 'error_samples': samples, 'top_errors': dict(errors.most_common(10))}
    write_atomic(MONITOR_DIR / 'kline_refresh_latest.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not gate_pass:
        raise SystemExit(2)

if __name__ == '__main__':
    main()
