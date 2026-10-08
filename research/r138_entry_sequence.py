# -*- coding: utf-8 -*-
"""R138: 入场序列合规检查 — 按用户指定顺序逐步判定: ①趋势 ②突破后的回撤 ③到达POI。

用户 2026-10 投诉: "入场的位置还是有问题, 先查趋势, 再看是否突破后的回撤, 再看是否到达poi点"。
R133 只做了点状违规判定(无顺序链), R134 是强纪律对照引擎(已被回测证伪, 记录-only)。
本脚本(新增, 不动任何既有产物): 对 combo_v22 全腿按三步链逐腿判定并分层统计——

  S1 趋势步 (合格=结构已偏多):
       trend_state=='up'  或  入场前最近突破为 BOS↑/CHoCH↑ (结构翻多)
       失败: 仍处下跌结构且最近突破为 ↓ (趋势向下)
  S2 回撤步 (须先通过 S1 才有意义):
       retrace_state=='retrace_ok' = 已突破且回踩未穿位
       no_retrace=未回踩就进场 / retrace_fail=回踩穿位(破位失败)
  S3 POI步 (须先通过 S1+S2):
       入场价位于 POI: in_ob==True(订单块) | in_fvg=='bull'(多缺口) | in_ote==True(OTE带)

输出: research/combo_v25_entry_sequence.csv + handover/_r138_entry_sequence.json
分层统计: 各步合格率 → 全序通过 vs 各违规层级 PnL 对比 (写入审计卡)。
"""
import csv, json, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(r'E:\test\smc_project')


def main():
    rows = list(csv.DictReader(open(ROOT / 'research/combo_v22_smc_full_v2.csv', encoding='utf-8-sig')))

    def _tf(x):
        return str(x or '').strip() == 'True'

    def verdict(r):
        trend = str(r.get('trend_state') or '')
        bk = str(r.get('breakout_kind') or '')
        rs = str(r.get('retrace_state') or '')
        pnl = None
        try:
            pnl = float(r.get('net_pnl_pct') or 0)
        except Exception:
            pass
        # S1 趋势
        s1_ok = (trend == 'up') or bk in ('BOS↑', 'CHoCH↑')
        if not s1_ok:
            return 'S1_TREND_FAIL', pnl
        # S2 突破后回撤
        # 结构翻多突破须回踩到位
        if rs == 'no_retrace':
            return 'S2_NO_PULLBACK', pnl
        if rs == 'retrace_fail':
            return 'S2_PULLBACK_BROKE', pnl
        if rs != 'retrace_ok':
            return 'S2_UNKNOWN', pnl
        # S3 到达POI
        at_poi = _tf(r.get('in_ob')) or str(r.get('in_fvg')) == 'bull' or _tf(r.get('in_ote'))
        if not at_poi:
            return 'S3_NOT_AT_POI', pnl
        return 'ALL_OK', pnl

    out, cohorts = [], {}
    for r in rows:
        v, pnl = verdict(r)
        out.append({
            'symbol': r['symbol'], 'entry_date': r['entry_date'],
            'trend_state': r.get('trend_state'), 'breakout_kind': r.get('breakout_kind'),
            'breakout_date': r.get('breakout_date'), 'breakout_price': r.get('breakout_price'),
            'retrace_state': r.get('retrace_state'), 'retrace_signal': r.get('retrace_signal'),
            'retrace_price': r.get('retrace_price'),
            'in_ob': r.get('in_ob'), 'in_fvg': r.get('in_fvg'), 'in_ote': r.get('in_ote'),
            'ote_zone': r.get('ote_zone'), 'buy_price': r.get('buy_price'),
            'net_pnl_pct': r.get('net_pnl_pct'), 'verdict': v,
        })
        c = cohorts.setdefault(v, [])
        if pnl is not None:
            c.append(pnl)

    def _stats(pnls):
        if not pnls:
            return {'n': 0}
        gp = sum(x for x in pnls if x > 0)
        gl = -sum(x for x in pnls if x < 0)
        return {'n': len(pnls), 'avg': round(sum(pnls) / len(pnls), 2),
                'wr': round(sum(1 for x in pnls if x > 0) / len(pnls) * 100, 1),
                'pf': round(gp / gl, 2) if gl > 0 else 99}

    stats = {k: _stats(v) for k, v in sorted(cohorts.items())}
    all_pnls = [float(r['net_pnl_pct'] or 0) for r in rows if r.get('net_pnl_pct')]
    stats['BASELINE_ALL'] = _stats(all_pnls)

    with open(ROOT / 'research/combo_v25_entry_sequence.csv', 'w', newline='', encoding='utf-8-sig') as f:
        if out:
            w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
            w.writeheader()
            w.writerows(out)
    json.dump(stats, open(ROOT / 'research/handover/_r138_entry_sequence.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    print('=== R138 入场序列三步判定 (①趋势→②突破后回撤→③到POI) — 全', len(rows), '腿 ===')
    for k, v in stats.items():
        if k == 'BASELINE_ALL':
            print(f"  基线全量: n={v['n']} avg={v['avg']}% WR={v['wr']}% PF={v['pf']}")
        else:
            print(f"  {k:22s} n={v.get('n',0):5d} avg={v.get('avg','-')}% WR={v.get('wr','-')}% PF={v.get('pf','-')}")
    print('写出 combo_v25_entry_sequence.csv + _r138_entry_sequence.json')


if __name__ == '__main__':
    main()
