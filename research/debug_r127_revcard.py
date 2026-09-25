# -*- coding: utf-8 -*-
import csv as _csv_rev, json, html, traceback
try:
    rows = list(_csv_rev.DictReader(open(r'E:\test\smc_project\research\combo_reverse_candidates.csv', encoding='utf-8-sig')))
    print('rows:', len(rows), flush=True)
    eqh = [r for r in rows if r['side'] == 'EQH']
    print('eqh:', len(eqh), flush=True)
    ov = json.load(open(r'E:\test\smc_project\research\handover\_r126_overlap.json', encoding='utf-8'))
    print('ov keys:', list(ov.keys())[:4], flush=True)
    lst = ''.join("<span>%s</span>" % html.escape(r['symbol']) for r in rows[:3])
    print('lst ok:', lst, flush=True)
    # 模拟卡 f-string
    _rev_list = ''.join(
        f"<span class='mono' style='display:inline-block;margin:2px;padding:1px 6px;border:1px solid #30363d;border-radius:3px;font-size:0.85em'>"
        f"{html.escape(r['symbol'])} <b style='color:{'#f85149' if r['side']=='EQH' else '#3fb950'}'>{r['side']}拒绝</b> {r['signal_date']} → {r['ret_10b_signed']}%</span>"
        for r in rows[:5])
    print('fstring ok', flush=True)
except Exception:
    traceback.print_exc()
