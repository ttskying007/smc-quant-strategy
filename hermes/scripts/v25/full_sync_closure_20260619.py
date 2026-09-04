#!/usr/bin/env python3
from __future__ import annotations
import json, urllib.request, pathlib, subprocess, collections, datetime
ROOT=pathlib.Path('/root/.hermes'); SCRIPTS=ROOT/'scripts'; AUDIT=ROOT/'smc_audit'; AUDIT.mkdir(exist_ok=True)

def sh(cmd, timeout=180):
    try:
        p=subprocess.run(cmd, shell=True, cwd=str(SCRIPTS), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        return {'cmd':cmd,'exit':p.returncode,'output':p.stdout[-4000:], 'timeout':False}
    except subprocess.TimeoutExpired as e:
        out=e.stdout if isinstance(e.stdout,str) else ''
        return {'cmd':cmd,'exit':124,'output':out[-4000:], 'timeout':True}

def get(path):
    with urllib.request.urlopen('http://127.0.0.1:8890'+path, timeout=25) as r:
        return json.loads(r.read().decode())

def raw(path):
    return urllib.request.urlopen('http://127.0.0.1:8890'+path, timeout=25).read().decode('utf-8','ignore')

def nonempty(v): return v not in (None,'',0,0.0,[],{})

commands={
 'compile_core':('python3 -m py_compile smc_unified.py smc_monitor_state.py test_monitor_entry_execution_contract.py v25/v90_daily_full_market_scanner.py v25/v66_daily_completeness_gate.py v25/v66_release_gate.py v25/v104_strict_reclaim_backtest.py',180),
 'monitor_contract':('python3 test_monitor_entry_execution_contract.py',120),
 'daily_completeness_gate':('python3 v25/v66_daily_completeness_gate.py',120),
 'release_gate':('python3 v25/v66_release_gate.py',120),
}
cmd_results={k:sh(*v) for k,v in commands.items()}
api={p:get(p) for p in ['/api/reload','/api/summary','/api/picks','/api/picks/contract','/api/live-prices']}
picks=api['/api/picks'].get('picks') if isinstance(api['/api/picks'],dict) else api['/api/picks']
live_rows=api['/api/live-prices'].get('picks', [])
picks_completed_pollution=sum(1 for r in picks if any(nonempty(r.get(k)) for k in ['exit_date','net_pnl_pct']))
picks_scope_counts=dict(collections.Counter(r.get('pick_scope') or r.get('pickScope') for r in picks))
live_status_counts=dict(collections.Counter(r.get('status') for r in live_rows))
live_nontradable_pnl=sum(1 for r in live_rows if not (r.get('tradable') or r.get('isTradableLive')) and abs(float(r.get('pnlPct') or r.get('pnl_pct') or 0))>1e-9)
live_bad_status=sum(1 for r in live_rows if not (r.get('tradable') or r.get('isTradableLive')) and r.get('status') not in ('WATCH_ONLY_CONTEXT','NON_TRADABLE_CONTEXT'))
v104=json.loads((ROOT/'smc_opt_v104_strict_reclaim/v104_report.json').read_text())
v105=json.loads((AUDIT/'v105_matrix_closure_20260618.json').read_text())
daily=json.loads((AUDIT/'v66_daily_completeness_gate.json').read_text())
release=json.loads((AUDIT/'v66_release_gate.json').read_text())
html_root=raw('/'); html_monitor=raw('/monitor'); html_live=raw('/live')
summary={
 'generated_at':datetime.datetime.now().isoformat(timespec='seconds'),
 'fixes_applied':['daily gate current candidate counts now align to V90 scanner','dashboard/monitor labels distinguish 可交易 vs 观察','live JS handles object DNA/combo values','live WATCH_ONLY_CONTEXT counted as 观察上下文 not 持仓'],
 'command_results':{k:{'exit':v['exit'],'timeout':v['timeout'],'tail':v['output'][-800:]} for k,v in cmd_results.items()},
 'api':{'summary_version':api['/api/summary'].get('version'),'last_kline_date':(api['/api/summary'].get('data_status') or {}).get('last_kline_date'),'reload':api['/api/reload'],'picks_count':len(picks),'picks_scope_counts':picks_scope_counts,'picks_completed_pollution':picks_completed_pollution,'contract':api['/api/picks/contract'],'live_total':api['/api/live-prices'].get('total'),'live_rows':len(live_rows),'live_status_counts':live_status_counts,'live_tradable_count':api['/api/live-prices'].get('tradableLiveCount'),'live_watch_count':api['/api/live-prices'].get('watchContextCount'),'live_nontradable_pnl_nonzero':live_nontradable_pnl,'live_bad_nontradable_status':live_bad_status},
 'gates':{'daily_pass':daily.get('pass'),'daily_candidate_source':daily.get('current_candidate_source'),'daily_candidate_date_counts':daily.get('daily_candidate_date_counts'),'daily_active_latest_count':daily.get('active_latest_count'),'daily_watch_latest_count':daily.get('watch_latest_count'),'release_pass':release.get('pass'),'release_failed_checks':release.get('failed_checks')},
 'strategy_research':{'v104_release_gate_pass':(v104.get('release_gate') or {}).get('pass'),'v104_semantic_fail':(v104.get('semantic_audit') or {}).get('fail_count'),'v104_entry_before_reclaim':(v104.get('semantic_audit') or {}).get('entry_before_reclaim'),'v105_promotable':(v105.get('decision') or {}).get('v105_promotable'),'v105_reason':(v105.get('decision') or {}).get('reason')},
 'frontend_smoke':{'dashboard_label_fixed':'当前选股上下文 Top15 (可交易0只 / 观察49只' in html_root,'monitor_label_fixed':'当前选股上下文 — 可交易0只 / 观察49只' in html_monitor,'live_js_object_safe_patch_present':'typeof dnaRaw === \'string\'' in html_live,'live_watch_context_summary_patch_present':'观察上下文' in html_live and '真实持仓' in html_live}
}
assert cmd_results['compile_core']['exit']==0
assert cmd_results['monitor_contract']['exit']==0
assert daily.get('pass') is True and release.get('pass') is True
assert len(picks)==49 and picks_scope_counts.get('WATCH_ONLY')==49 and picks_completed_pollution==0
assert api['/api/picks/contract']['tradable_active_pick_count']==0 and api['/api/picks/contract']['watch_only_count']==49
assert api['/api/live-prices'].get('tradableLiveCount')==0 and api['/api/live-prices'].get('watchContextCount')==7 and live_nontradable_pnl==0 and live_bad_status==0
assert daily.get('current_candidate_source')=='V90_DAILY_SCANNER' and daily.get('watch_latest_count')==49
assert (v104.get('semantic_audit') or {}).get('fail_count')==0 and (v104.get('release_gate') or {}).get('pass') is False and (v105.get('decision') or {}).get('v105_promotable') is False
assert all(summary['frontend_smoke'].values()), summary['frontend_smoke']
summary['overall_pass']=True
summary['open_items']=['策略层未晋级：V104/V105均为RESEARCH_ONLY，下一阶段需V106信号层重建；这不是生产/API同步缺陷。','Pine/LuxAlgo语义正确性仍需单独re-derivation audit；当前sequence/provenance gate不等于语义正确性证明。','/root/.hermes/scripts 非git仓库，GitNexus detect-changes不能提供变更范围证明；本轮用py_compile+单测+gate+API+browser smoke闭环。']
out=AUDIT/'full_sync_closure_20260619.json'; out.write_text(json.dumps(summary,ensure_ascii=False,indent=2))
md=AUDIT/'full_sync_closure_20260619.md'; md.write_text('# SMC Full Sync Closure 20260619\n\n```json\n'+json.dumps(summary,ensure_ascii=False,indent=2)+'\n```\n')
print(json.dumps({'overall_pass':True,'json':str(out),'md':str(md),'api':summary['api'],'gates':summary['gates'],'frontend_smoke':summary['frontend_smoke'],'open_items':summary['open_items']},ensure_ascii=False,indent=2))
