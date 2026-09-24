# -*- coding: utf-8 -*-
r"""R90 — 用修正过的 core.structure(mode='auto') 重算全部 v22 链路 (combo_v22_chain_v2_norm.csv)

每腿:
  - 信号日上下文在 entry_date 的上一根 bar (与 gen_v22_chain.py i 一致)
  - 用 core.chain.build_chain(bs, i, mode='auto') 重出趋势 / events_tail / BSL/SSL / OB / FVG / breakout / retrace
  - 与链 v1 对比: trend_state / last_event_kind / breakout_kind / retrace_state 翻转标记
  - 写入 combo_v22_chain_v2_norm.csv (不覆盖原 combo_v22_trades.csv)

目标: 骨结构变化后, 告诉用户多大规模腿会冲击决策 (§v24 s1-s14 影子字段依赖链字段)
"""
import csv, io, json, sys, os, time
from pathlib import Path
sys.path.insert(0, r'E:\test\smc_project\research')

ROOT = Path(r'E:\test\smc_project')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from core.chain import build_chain

KC = ROOT / 'hermes' / 'kline_cache_tencent'


def bars_of(code6):
    p = KC / (code6 + ('_SH' if code6.startswith('6') else '_SZ') + '_daily_800.json')
    if not p.exists():
        return []
    raw = json.loads(p.read_text(encoding='utf-8'))
    bs = []
    for r in raw:
        t = ''.join(x for x in str(r.get('t') or '') if x.isdigit())[:8]
        if t and r.get('o') and r.get('h') and r.get('l') and r.get('c'):
            try:
                bs.append({'t': t, 'o': float(r['o']), 'h': float(r['h']),
                           'l': float(r['l']), 'c': float(r['c']),
                           'v': float(r.get('v') or 0)})
            except Exception:
                continue
    bs.sort(key=lambda b: b['t'])
    return bs


def main():
    rows = list(csv.DictReader(open(ROOT / 'research' / 'combo_v22_trades.csv', encoding='utf-8-sig')))
    print(f'v22 legs: {len(rows)}')

    t0 = time.time()
    out_rows = []
    flips = {'trend_state': 0, 'last_event_kind': 0, 'breakout_kind': 0, 'retrace_state': 0}
    tested = 0
    err = 0
    bar_cache = {}
    for idx, row in enumerate(rows):
        sym = row['symbol']
        code6 = sym[:6]
        if code6 not in bar_cache:
            bar_cache[code6] = bars_of(code6)
        bs = bar_cache[code6]
        if not bs:
            err += 1
            continue
        dates = [b['t'] for b in bs]
        ed = str(row['entry_date'])
        if ed not in dates:
            err += 1
            continue
        ei = dates.index(ed)
        i = ei - 1  # 信号日 = 入场前一根 (gen_v22_chain 口径)
        if i < 60:
            err += 1
            continue
        try:
            ch = build_chain(bs, i, mode='auto')
        except Exception as e:
            err += 1
            continue
        tested += 1

        # 提取旧链对比
        try:
            old = json.loads(row.get('chain_json') or '{}')
        except Exception:
            old = {}
        new_trend = ch.get('trend_state') or 'none'
        old_trend = row.get('trend_state') or old.get('trend_state') or ''
        new_last_kind = (ch.get('events_tail') or [{}])[-1].get('kind', '') if ch.get('events_tail') else ''
        old_last_kind = row.get('last_event_kind') or ''
        new_brk_kind = (ch.get('breakout') or {}).get('kind', '') or ''
        old_brk_kind = row.get('breakout_kind') or ''
        new_rt = (ch.get('retrace') or {}).get('state', '') or ''
        old_rt = row.get('retrace_state') or ''
        for name, o, n in (('trend_state', old_trend, new_trend),
                            ('last_event_kind', old_last_kind, new_last_kind),
                            ('breakout_kind', old_brk_kind, new_brk_kind),
                            ('retrace_state', old_rt, new_rt)):
            if str(o) != str(n):
                flips[name] += 1
        out_rows.append({
            'symbol': sym, 'entry_date': ed, 'src': row.get('src', ''),
            'net_pnl_pct': row.get('net_pnl_pct', ''),
            'pnl': float(row.get('pnl') or row.get('net_pnl_pct') or 0),
            'old_trend': old_trend, 'new_trend': new_trend,
            'old_last_event': old_last_kind, 'new_last_event': new_last_kind,
            'old_breakout_kind': old_brk_kind, 'new_breakout_kind': new_brk_kind,
            'old_breakout_date': row.get('breakout_date', ''),
            'new_breakout_date': (ch.get('breakout') or {}).get('date', ''),
            'old_retrace_state': old_rt, 'new_retrace_state': new_rt,
            'chain_json_v2': json.dumps(ch, ensure_ascii=False),
        })
        if idx % 200 == 199:
            print(f'  {idx+1}/{len(rows)} t={time.time()-t0:.0f}s err={err}')

    out_path = ROOT / 'research' / 'combo_v22_chain_v2_norm.csv'
    with open(out_path, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    print(f'\n写入 {out_path.name}: {len(out_rows)} 腿 ({time.time()-t0:.0f}s, err={err})')
    print(f'测试腿: {tested}')
    base = max(1, tested)
    for k, v in flips.items():
        print(f'  {k} 翻转: {v} = {v/base*100:.1f}%')


if __name__ == '__main__':
    main()
