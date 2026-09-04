#!/usr/bin/env python3
"""SMC morning holdings + picks push report.

Markdown-table formatted for WeChat/QQ readability.
"""
from __future__ import annotations
import json, pathlib, datetime, urllib.request, subprocess, sys

BASE='http://127.0.0.1:8890'
ROOT=pathlib.Path('/root/.hermes')
OUTDIR=ROOT/'smc_push_reports'; OUTDIR.mkdir(exist_ok=True)


def run_daily_preflight():
    """Run refresh_daily_750 + daily_scan + ingest before building the push."""
    script = ROOT / 'scripts/v25/smc_daily_ops.py'
    started = datetime.datetime.now()
    timeout = 2400
    try:
        proc = subprocess.run([sys.executable, str(script)], cwd=str(ROOT / 'scripts'), text=True, capture_output=True, timeout=timeout)
        ok = proc.returncode == 0
        err = (proc.stderr or proc.stdout or '')[-1200:]
    except subprocess.TimeoutExpired as e:
        ok = False
        stdout = e.stdout.decode(errors='replace') if isinstance(e.stdout, bytes) else (e.stdout or '')
        stderr = e.stderr.decode(errors='replace') if isinstance(e.stderr, bytes) else (e.stderr or '')
        err = (stderr or stdout or '')[-1200:] + f'\nTIMEOUT after {timeout}s'
        proc = None
    except Exception as e:
        ok = False
        err = str(e)
        proc = None
    finished = datetime.datetime.now()
    return {
        'ok': ok,
        'started_at': started.isoformat(timespec='seconds'),
        'finished_at': finished.isoformat(timespec='seconds'),
        'duration_sec': round((finished - started).total_seconds(), 1),
        'returncode': getattr(proc, 'returncode', 124 if 'TIMEOUT' in str(err) else -1),
        'timeout_sec': timeout,
        'error_tail': err,
    }


def load_json(path, default):
    try:
        return json.loads(pathlib.Path(path).read_text())
    except Exception:
        return default

def get_api(path, default):
    try:
        return json.loads(urllib.request.urlopen(BASE+path, timeout=25).read().decode('utf-8','ignore'))
    except Exception:
        return default

def date_key(v):
    s=''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s)>=8 else ''

def fmt_date(v):
    s=date_key(v)
    return f'{s[4:6]}-{s[6:8]}' if len(s)==8 else '-'

def fmt_price(x):
    try:
        v=float(x or 0)
        return '-' if v == 0 else f'{v:.2f}'
    except Exception:
        return '-'

def fmt_pct(x):
    try:
        v=float(x or 0)
        return f'{v:+.2f}%'
    except Exception:
        return '-'

def safe(x, n=18):
    s=str(x or '-').replace('\n',' ').replace('|','/')
    return s if len(s)<=n else s[:n-1]+'…'

def name(x):
    return x.get('name') or x.get('stock_name') or '-'

def signal(x):
    parts=[x.get('v59_setup_family') or x.get('trade_role') or x.get('entry_type'), x.get('zone_type') or x.get('signal_type'), x.get('conf_type')]
    s=' '.join(str(p) for p in parts if p and str(p)!='None')
    return s or x.get('seq') or x.get('ctx_seq') or '-'

def md_table(headers, rows):
    out=['| '+' | '.join(headers)+' |', '| '+' | '.join(['---']*len(headers))+' |']
    for r in rows:
        out.append('| '+' | '.join(safe(c, 22) for c in r)+' |')
    return '\n'.join(out)

def pos_buy_date(p):
    return date_key(p.get('buy_date') or p.get('created_at') or p.get('filled_at')) or date_key(p.get('entry_date'))

def pos_row(idx, p, live_by_sym):
    sym=p.get('symbol') or '-'
    live=live_by_sym.get(sym,{})
    cur=live.get('currentPrice') or p.get('current_price') or p.get('last_close') or 0
    entry=p.get('entry_price') or p.get('price') or 0
    pnl=live.get('pnlPct')
    if pnl is None and entry and cur:
        try: pnl=(float(cur)-float(entry))/float(entry)*100
        except Exception: pnl=0
    status=live.get('status') or p.get('status') or '-'
    return [idx, fmt_date(p.get('pick_date')), fmt_date(pos_buy_date(p)), sym, name(p), fmt_price(entry), fmt_price(cur), fmt_pct(pnl), fmt_price(p.get('sl_price') or p.get('sl')), fmt_price(p.get('tp1_price') or p.get('tp1') or p.get('tpPrice')), status, signal(p)]

def pick_status(p, held, pending):
    sym=p.get('symbol') or '-'
    if sym in held:
        return '已持仓'
    if sym in pending or p.get('monitor_status') == 'NEXT_DAY_PENDING':
        return '待次日买入'
    return '候选'

def pick_row(idx, p, held, pending):
    sym=p.get('symbol') or '-'
    return [idx, pick_status(p, held, pending), fmt_date(p.get('pick_date') or p.get('entry_date')), fmt_date(p.get('join_date')), sym, name(p), fmt_price(p.get('entry_price') or p.get('price')), fmt_price(p.get('sl')), fmt_price(p.get('tp1') or p.get('tpPrice')), p.get('monitor_status') or p.get('state') or p.get('pick_scope') or '-', signal(p), p.get('breakout_quality_score') or p.get('score') or '-']

def main():
    now=datetime.datetime.now()
    preflight=run_daily_preflight()
    ops=load_json(ROOT/'smc_monitor/ops_latest.json', {})
    pd=ops.get('pick_diagnostics') or {}
    merge=ops.get('daily_scan_merge') or {}
    scan=ops.get('daily_scan') or {}
    scan_time=scan.get('finished_at') or merge.get('finished_at') or ops.get('generated_at') or '-'
    data_date=ops.get('data_date') or pd.get('data_date') or merge.get('latest_scan_date') or '-'
    summary=get_api('/api/summary',{})
    production_version=summary.get('version') or 'V185'
    production_engine=summary.get('engine') or '-'
    live=get_api('/api/live-prices',{}).get('picks',[])
    live_by_sym={x.get('symbol'):x for x in live if x.get('symbol')}
    mon=get_api('/api/monitor/state',{})
    raw_positions=mon.get('positions',[])
    open_positions=[p for p in raw_positions if p.get('status')=='OPEN']
    pending_positions=[p for p in raw_positions if p.get('status')=='NEXT_DAY_PENDING']
    seen=set(); positions=[]
    for p in open_positions:
        key=(p.get('symbol'), p.get('pick_date') or p.get('entry_date'), p.get('entry_price'), p.get('sl_price'), p.get('created_at'))
        if key in seen: continue
        seen.add(key); positions.append(p)
    picks=get_api('/api/picks',[])
    active=[p for p in picks if p.get('is_active_pick') and p.get('pick_scope') in ('ACTIVE_CANDIDATE','ACTIVE_ENTRY','POST_ENTRY_MONITOR','NEAR_ZONE_WATCH')]
    latest_pick_date=max([date_key(p.get('pick_date') or p.get('entry_date')) for p in active] or [''])
    held={p.get('symbol') for p in positions if p.get('symbol')}
    pending={p.get('symbol') for p in pending_positions if p.get('symbol')}
    latest=[p for p in active if date_key(p.get('pick_date') or p.get('entry_date')) == latest_pick_date]
    historical=[p for p in active if date_key(p.get('pick_date') or p.get('entry_date')) != latest_pick_date and p.get('symbol') not in held and p.get('symbol') not in pending]
    held_picks=[p for p in active if p.get('symbol') in held]
    pending_picks=[p for p in active if p.get('symbol') in pending or p.get('monitor_status') == 'NEXT_DAY_PENDING']

    def sort_key(x):
        return (-(float(x.get('breakout_quality_score') or x.get('score') or 0)), x.get('symbol') or '')

    lines=[]
    lines.append(f"# SMC早盘推送 {now.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"版本: {production_version}｜引擎: {production_engine}｜OPEN持仓: {len(positions)}｜待次日买入: {len(pending_positions)}｜数据日期: {data_date}｜最后扫描: {scan_time}｜最新选股日: {latest_pick_date or '-'}｜最新日选股: {len(latest)}｜全部Active: {len(active)}")
    if preflight.get('ok'):
        lines.append(f"预检: 已先执行刷新K线+daily_scan+ingest，用时 {preflight.get('duration_sec')}s")
    else:
        lines.append(f"预检: 失败 returncode={preflight.get('returncode')}｜{safe(preflight.get('error_tail'), 80)}")
    lines.append('')
    lines.append('## 持仓监控')
    if positions:
        rows=[pos_row(i,p,live_by_sym) for i,p in enumerate(sorted(positions, key=lambda x:x.get('symbol') or ''),1)]
        lines.append(md_table(['#','选股日','买入日','代码','名称','成本','现价','盈亏','止损','止盈','状态','信号'], rows))
    else:
        lines.append('无OPEN持仓')
    lines.append('')
    lines.append('## 待次日买入')
    if pending_positions:
        rows=[[i, fmt_date(p.get('pick_date')), fmt_date(p.get('created_at')), p.get('symbol'), name(p), fmt_price(p.get('entry_price')), fmt_price(p.get('sl_price')), fmt_price(p.get('tp1_price')), p.get('pending_reason') or 'NEXT_DAY_PENDING', signal(p)] for i,p in enumerate(sorted(pending_positions, key=lambda x:x.get('symbol') or ''),1)]
        lines.append(md_table(['#','选股日','加入日','代码','名称','参考入场','止损','止盈','状态','信号'], rows))
    else:
        lines.append('无NEXT_DAY_PENDING')
    lines.append('')
    lines.append('## 最新交易日选股')
    if latest:
        rows=[pick_row(i,p,held,pending) for i,p in enumerate(sorted(latest, key=sort_key),1)]
        lines.append(md_table(['#','标识','选股日','加入日','代码','名称','成本','止损','止盈','监控状态','信号','BQ'], rows))
    else:
        lines.append('无最新交易日ACTIVE选股')
    lines.append('')
    lines.append('## 已持仓匹配选股')
    if held_picks:
        rows=[pick_row(i,p,held,pending) for i,p in enumerate(sorted(held_picks, key=lambda x:x.get('symbol') or ''),1)]
        lines.append(md_table(['#','标识','选股日','加入日','代码','名称','成本','止损','止盈','监控状态','信号','BQ'], rows))
    else:
        lines.append('无已持仓匹配选股')
    lines.append('')
    lines.append('## 历史候选')
    if historical:
        rows=[pick_row(i,p,held,pending) for i,p in enumerate(sorted(historical, key=sort_key),1)]
        lines.append(md_table(['#','标识','选股日','加入日','代码','名称','成本','止损','止盈','监控状态','信号','BQ'], rows))
    else:
        lines.append('无历史候选')
    lines.append('')
    lines.append('备注: 买入日固定取真实created_at/buy_date；最新交易日选股、历史候选、已持仓、NEXT_DAY_PENDING分开展示，避免历史候选混入今日选股。')
    text='\n'.join(lines)
    out=OUTDIR/f'{now.strftime("%Y%m%d_%H%M%S")}_morning_push.md'
    out.write_text(text)
    print(text)
    print(f"\n[报告文件] {out}")

if __name__=='__main__':
    main()
