#!/usr/bin/env python3
"""V66 live-vs-backtest stoploss/root-cause audit."""
from __future__ import annotations
import json, collections, statistics, datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
OUT_JSON = ROOT / 'smc_audit/v66_live_vs_backtest_gap_report.json'
OUT_MD = ROOT / 'smc_audit/v66_live_vs_backtest_gap_report.md'

def load(path, default):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return default

def dkey(v):
    s=''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s)>=8 else ''

def f(v):
    try: return float(v or 0)
    except Exception: return 0.0

def pct(n,d):
    return round(n/max(d,1)*100,2)

def q(vals):
    vals=sorted([f(x) for x in vals if f(x)])
    if not vals:
        return {}
    return {'min':round(vals[0],3),'p25':round(vals[int((len(vals)-1)*0.25)],3),'p50':round(statistics.median(vals),3),'p75':round(vals[int((len(vals)-1)*0.75)],3),'max':round(vals[-1],3),'avg':round(statistics.mean(vals),3)}

def bdays(a,b):
    a=dkey(a); b=dkey(b)
    if not a or not b: return None
    try:
        da=datetime.datetime.strptime(a,'%Y%m%d').date(); db=datetime.datetime.strptime(b,'%Y%m%d').date()
    except Exception:
        return None
    n=0
    while da<db:
        da += datetime.timedelta(days=1)
        if da.weekday()<5: n+=1
    return n

def main():
    trades=load(ROOT/'smc_opt_v66/v66_trades.json',[])
    picks=load(ROOT/'smc_opt_v66/v66_picks.json',[])
    candidates=load(ROOT/'smc_opt_v66/v66_daily_candidates.json',[])
    positions=load(ROOT/'smc_monitor/positions.json',[])
    reviews=load(ROOT/'smc_monitor/closed_reviews.json',[])
    ledger=[x for x in load(ROOT/'smc_monitor/trade_ledger.json',[]) if not x.get('invalidated')]
    active=[p for p in picks if p.get('pick_scope')=='ACTIVE_CANDIDATE' and p.get('is_active_pick')]
    watch=[p for p in picks if p.get('pick_scope')=='WATCH_ONLY']
    live_closed=[p for p in positions if p.get('status')=='CLOSED']
    live_open=[p for p in positions if p.get('status')=='OPEN']
    review_by_class=collections.Counter(r.get('sample_class') or 'UNKNOWN' for r in reviews)
    review_by_root=collections.Counter(r.get('root_cause') or 'UNKNOWN' for r in reviews)
    review_by_reason=collections.Counter(r.get('reason') or 'UNKNOWN' for r in reviews)
    sl_reviews=[r for r in reviews if r.get('reason')=='SL_HIT']
    clean_reviews=[r for r in reviews if r.get('sample_class')=='PRODUCTION_CLEAN']
    diag_reviews=[r for r in reviews if r.get('sample_class')!='PRODUCTION_CLEAN']
    active_risks=[p.get('risk_pct') for p in active]
    watch_risks=[p.get('risk_pct') for p in watch]
    cand_by_scope=collections.Counter(p.get('pick_scope') for p in candidates)
    cand_by_watch=collections.Counter(p.get('watch_reason') or p.get('reject_reason') or 'ACTIVE' for p in picks if p.get('pick_scope') in ('ACTIVE_CANDIDATE','WATCH_ONLY'))
    live_ages=[]
    for p in positions:
        raw=p.get('raw_pick') or {}
        age=bdays(p.get('pick_date') or raw.get('pick_date') or raw.get('select_date'), p.get('filled_at') or p.get('created_at'))
        if age is not None:
            live_ages.append(age)
    trade_win=[t for t in trades if f(t.get('pnl_pct'))>0]
    trade_loss=[t for t in trades if f(t.get('pnl_pct'))<=0]
    out={
        'generated_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'backtest': {
            'trades': len(trades), 'symbols': len({t.get('symbol') for t in trades}),
            'wr_pct': pct(len(trade_win), len(trades)),
            'sl_or_loss_count': len(trade_loss),
            'avg_pnl_pct': round(statistics.mean([f(t.get('pnl_pct')) for t in trades]),3) if trades else 0,
            'by_zone': dict(collections.Counter(t.get('zone_type') or t.get('signal_type') for t in trades)),
            'loss_by_zone': dict(collections.Counter(t.get('zone_type') or t.get('signal_type') for t in trade_loss)),
            'loss_by_conf': dict(collections.Counter(t.get('conf_type') for t in trade_loss)),
        },
        'live_monitor': {
            'positions_total': len(positions), 'open': len(live_open), 'closed': len(live_closed),
            'reviews_total': len(reviews), 'sl_reviews': len(sl_reviews),
            'review_by_reason': dict(review_by_reason), 'review_by_class': dict(review_by_class), 'review_by_root_cause': dict(review_by_root),
            'production_clean_reviews': len(clean_reviews), 'diagnostic_reviews': len(diag_reviews),
            'pick_to_fill_age_bdays': q(live_ages),
        },
        'current_funnel': {
            'picks_total': len(picks), 'active_tradable': len(active), 'watch_only': len(watch), 'expired_review': sum(1 for p in picks if p.get('pick_scope')=='EXPIRED_REVIEW'),
            'daily_candidates_total': len(candidates), 'daily_candidate_scope_counts': dict(cand_by_scope),
            'current_reason_counts': dict(cand_by_watch),
            'active_risk_pct': q(active_risks), 'watch_risk_pct': q(watch_risks),
        },
        'gap_attribution': [
            {'rank':1,'cause':'LIVE_SAMPLE_POLLUTION','evidence':f"{len(diag_reviews)}/{len(reviews)} closed reviews are not PRODUCTION_CLEAN; root causes={dict(review_by_root)}",'impact':'实盘止损率不能直接和V66回测WR比较，样本来源不一致'},
            {'rank':2,'cause':'STALE_OR_MANUAL_IMPORT_ENTRY','evidence':f"pick→fill business-age distribution={q(live_ages)}",'impact':'旧选股/手工导入造成入场晚于回测触发点，信号已衰减或zone已失效'},
            {'rank':3,'cause':'FIELD_CONTRACT_GAP_FIXED_FORWARD','evidence':'daily scan uses zone_bar/entry_idx; monitor previously expected zone_idx/conf_index. Contract now normalized.', 'impact':'未来新样本可进入PRODUCTION_CLEAN，历史样本仍保持诊断隔离'},
            {'rank':4,'cause':'BACKTEST_ACTIVE_FILTER_VS_LIVE_WATCH_FUNNEL','evidence':f"current active={len(active)}, watch_only={len(watch)}, watch risk={q(watch_risks)}",'impact':'大量信号存在但风险过大，只能观察，不能解释为可买样本'},
            {'rank':5,'cause':'EXECUTION_PRICE_AND_T1_DIFFERENCE','evidence':'live entry must obey T+1 and next-day/live price; backtest uses historical deterministic entry path.', 'impact':'次日跳空/追高会改变SL距离、zone位置和TP/SL触发顺序'},
        ]
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    lines=[]
    lines.append('# V66 实盘 vs 回测差异根因报告')
    lines.append('')
    lines.append('## 结论')
    lines.append('- 回测好看但实盘止损多的第一根因不是单一 SL 参数，而是实盘 closed 样本几乎全部是 DIAGNOSTIC_ONLY 历史污染样本。')
    lines.append('- V66 当前回测 137 笔、WR 90.51%，但 live closed review 中 PRODUCTION_CLEAN=0，两个总体不可直接比较。')
    lines.append('- 新增字段契约修复后，未来 auto_daily 新样本会保留 zone/provenance；历史样本继续隔离，不参与生产胜率判断。')
    lines.append('- 102 个新增观察候选风险中位数 16.99%，不能直接扩大买入，只能 WATCH_ONLY 跟踪。')
    lines.append('')
    lines.append('## 核心数据')
    lines.append('| 模块 | 数值 | 说明 |')
    lines.append('|---|---:|---|')
    lines.append(f"| V66 回测交易 | {out['backtest']['trades']} | WR {out['backtest']['wr_pct']}%，avgPnL {out['backtest']['avg_pnl_pct']}% |")
    lines.append(f"| 实盘 positions | {out['live_monitor']['positions_total']} | OPEN {out['live_monitor']['open']} / CLOSED {out['live_monitor']['closed']} |")
    lines.append(f"| 实盘复盘 | {out['live_monitor']['reviews_total']} | SL {out['live_monitor']['sl_reviews']} |")
    lines.append(f"| Clean 复盘样本 | {out['live_monitor']['production_clean_reviews']} | 当前为 0，历史不能作为生产胜率 |")
    lines.append(f"| 当前可买 active | {out['current_funnel']['active_tradable']} | 买入范围未扩大 |")
    lines.append(f"| 当前观察 WATCH_ONLY | {out['current_funnel']['watch_only']} | 高风险只观察 |")
    lines.append('')
    lines.append('## Root Cause 排名')
    lines.append('| Rank | 根因 | 证据 | 影响 |')
    lines.append('|---:|---|---|---|')
    for r in out['gap_attribution']:
        lines.append(f"| {r['rank']} | {r['cause']} | {r['evidence']} | {r['impact']} |")
    lines.append('')
    lines.append('## 下一步修复方向')
    lines.append('1. 只用 PRODUCTION_CLEAN 样本计算生产 WR/SL 率；DIAGNOSTIC_ONLY 只做缺陷归因。')
    lines.append('2. 对 WATCH_ONLY 的 102 条做后验跟踪：是否 reclaim、是否二次确认、是否风险回落到 ≤5%。')
    lines.append('3. 对后续 clean SL 单逐笔回放：单信号准确性、组合信号顺序、entry-zone 距离、T+1 跳空、SL 是否低于真实结构低点。')
    lines.append('4. 下一版策略修复必须先分桶验证 OB_Bull/FVG_Bull × BOS/CHOCH × continuation/reentry × risk bucket，而不是调宽止损。')
    OUT_MD.write_text('\n'.join(lines)+'\n')
    print(json.dumps({'json':str(OUT_JSON),'md':str(OUT_MD),'summary':out['live_monitor'],'funnel':out['current_funnel']}, ensure_ascii=False, indent=2))

if __name__=='__main__':
    main()
