# -*- coding: utf-8 -*-
"""reject_backfill.py —— R6: 拒绝账本历史回填(研究级重放, 2026-09-13)。

目的: R5 评估器需等账本逐日积累(数周才有 n>=20), 历史回填用同一套
classify_title/stage_and_deep/adx14 逻辑重放过去 60 个交易日公告,
立即产出分层前向收益证据。**纯研究输出, 不改任何生产过滤器。**

纪律标注: 回填是"研究级重放"(同逻辑同数据源), 与 R5 起的生产账本
(reject_ledger.json)分账 —— 写 reject_ledger_backfill.json, 不混 provenance;
正式 n>=20 判定仍以生产账本前瞻积累为准, 回填报告仅提供预览证据。

窗口规则: signal 日 ∈ [asof-80 交易日, asof-21 交易日](60 个交易日),
保证每条记录 fwd5/10/20 全窗口完整(K线 asof=20260911)。
用法: python reject_backfill.py [--days 60] [--eval]
  --days: signal 日数量(默认60, 全部保证 fwd20 完整)
  --eval: 回填后立即跑 reject_forward_eval(对回填账本)
"""
import io, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paper_sim  # noqa (bars_of/stage_and_deep/adx14_of/load_ledger/ROOT)
# 教训#7(R8): stdout wrap 只在 __main__ 做 —— 本模块会被 reject_fill_replay import,
# 模块级 wrap 会在调用方(已 wrap)再包一层, GC 关闭首个 wrapper → "I/O operation on closed file"

from core.events import classify_title
from core.trading_calendar import td_set
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
BACKFILL_FILE = os.path.join(paper_sim.ROOT, "reject_ledger_backfill.json")
FWD_GUARD_TD = 21  # signal 日距 asof 至少 21 个交易日 → fwd20 必完整


def compute_window(asof_d8, days=60, guard_td=FWD_GUARD_TD, tds=None):
    """纯函数: signal 日窗口 = tds[asof_idx-guard-days+1 : asof_idx-guard+1]。
    返回 (signal_dates_d8 升序列表, asof_d8)。asof 不在日历 → 抛 ValueError。"""
    tds = sorted(td_set()) if tds is None else sorted(tds)
    if asof_d8 not in tds:
        raise ValueError(f"asof {asof_d8} 不在交易日历")
    i = tds.index(asof_d8)
    hi = i - guard_td + 1  # 最晚 signal 日(含)
    lo = max(0, hi - days)
    return tds[lo:hi], asof_d8


def replay(signal_dates_d8, bars_of=None, ledger=None, conn=None, stage_and_deep=None, adx14_of=None):
    """纯重放: 对窗口内每个公告日重建拒绝记录(schema 与 _persist_rejects 一致)。
    与 daily_selection 同逻辑: classify→dup(主账本 known)→bars→stage→ADX。
    bars_of 等可注入(测试); 返回 records 列表。"""
    bars_of = bars_of or paper_sim.bars_of
    stage_and_deep = stage_and_deep or paper_sim.stage_and_deep
    adx14_of = adx14_of or paper_sim.adx14_of
    ledger = paper_sim.load_ledger() if ledger is None else ledger
    known = {(t.get("code"), str(t.get("signal_date", "")).replace("-", "")) for t in ledger}
    conn = sqlite3.connect(paper_sim.CFG.ANNOUNCE_DB) if conn is None else conn
    cur = conn.cursor()
    _bars_cache = {}
    records = []
    passed = []
    for d8 in signal_dates_d8:
        dd = f"{d8[:4]}-{d8[4:6]}-{d8[6:8]}"
        cur.execute("SELECT stock_code, stock_name, title FROM announce WHERE date=? AND (title LIKE '%增持%' OR title LIKE '%回购%')", (dd,))
        rows = cur.fetchall()
        seen_orders = set()
        for code, name, title in rows:
            try:
                is_ev, _kind, pol, _a, _p = classify_title(title)
                if not is_ev or pol < 0:
                    records.append({"code": code, "name": name, "date": d8, "stage": "EVENT_FILTER", "title": str(title)[:80]})
                    continue
            except Exception:
                pass
            if (code, d8) in known or (code, d8) in seen_orders:
                records.append({"code": code, "name": name, "date": d8, "stage": "DUP_EXISTING", "title": str(title)[:80]})
                continue
            seen_orders.add((code, d8))
            bs = _bars_cache.get(code)
            if bs is None:
                bs = bars_of(code)
                if bs is not None:
                    _bars_cache[code] = bs
            if not bs or d8 not in [b["t"] for b in bs]:
                records.append({"code": code, "name": name, "date": d8, "stage": "DATA_MISSING", "title": str(title)[:80]})
                continue
            i = [b["t"] for b in bs].index(d8)
            st, _deep = stage_and_deep(bs, i)
            if st not in ("ACCUM", "DOWNTREND"):
                records.append({"code": code, "name": name, "date": d8, "stage": f"STAGE_{st}", "adx": adx14_of(bs, i), "title": str(title)[:80]})
                continue
            adx = adx14_of(bs, i)
            if adx is None or adx < 20:
                records.append({"code": code, "name": name, "date": d8, "stage": "ADX_LT20", "adx": adx, "title": str(title)[:80]})
                continue
            passed.append({"code": code, "name": name, "date": d8, "title": str(title)[:80]})
    return records, passed


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--eval", action="store_true")
    args = ap.parse_args()
    tds = sorted(td_set())
    asof = tds[-1]
    signal_dates, _ = compute_window(asof, days=args.days, tds=tds)
    print(f"K线 asof={asof}, 回填 signal 日 {len(signal_dates)} 个: {signal_dates[0]}..{signal_dates[-1]}(全部 fwd20 完整)")
    t0 = time.time()
    records, passed = replay(signal_dates)
    dt = time.time() - t0
    print(f"重放完成 {dt:.1f}s: 拒绝 {len(records)} 条, 通过(应已在主账本) {len(passed)} 单")
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    out = [{"code": r["code"], "name": r.get("name", ""), "date": r["date"], "stage": r["stage"],
            "adx": r.get("adx"), "title": r.get("title", ""), "ts": ts, "provenance": "backfill_replay"}
           for r in records]
    json.dump(out, open(BACKFILL_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"已写 {BACKFILL_FILE} ({len(out)} 条, provenance=backfill_replay)")
    if args.eval:
        # 对回填账本评估 —— 用独立子进程跑(避免 stdout TextIOWrapper 双包: 教训#7)
        import subprocess
        _ev = os.path.join(HERE, "_backfill_eval_child.py")
        with open(_ev, "w", encoding="utf-8") as f:
            f.write(
                "# -*- coding: utf-8 -*-\n"
                "import json, os, sys\n"
                f"sys.path.insert(0, r'{HERE}')\n"
                "import paper_sim\n"
                "import reject_forward_eval as rfe\n"
                f"out = json.load(open(r'{BACKFILL_FILE}', encoding='utf-8'))\n"
                "agg = rfe.evaluate(out)\n"
                "pas = rfe.passed_cohort_forward(paper_sim.load_ledger())\n"
                "pas_avg = (pas.get('per_stage', {}).get('PASSED_ORDER', {}) or {}).get('fwd_avg', {})\n"
                "print(f\"回填评估: total_n={agg['total_n']} 可评估={sum(s['evaluable'] for s in agg['per_stage'].values())} 不可评估={agg['unavailable']}\")\n"
                "for stage, s in sorted(agg['per_stage'].items(), key=lambda kv: -kv[1]['n']):\n"
                "    v = 'below_min_n' if s['evaluable'] < 20 else rfe._avg_vs_pass(s['fwd_avg'].get('h20'), pas_avg.get('h20'))\n"
                "    print(f\"  {stage:16s} n={s['n']:4d} avail={s['evaluable']:4d} h5={s['fwd_avg'].get('h5')} h10={s['fwd_avg'].get('h10')} h20={s['fwd_avg'].get('h20')} mfe={s['mfe_avg']} mae={s['mae_avg']} tp1={s['tp1_hit_rate']} sl={s['sl_hit_rate']} -> {v}\")\n"
                "print(f\"通过组对照(主账本挂单口径): h20={pas_avg.get('h20')}\")\n"
                f"rep = dict(json.load(open(r'{os.path.join(HERE, 'handover', 'reject_backfill_report.json')}', encoding='utf-8')) if os.path.exists(r'{os.path.join(HERE, 'handover', 'reject_backfill_report.json')}') else {{}})\n"
                f"rep.update({{'generated_at': '{ts}', 'provenance': 'backfill_replay', 'window': ['{signal_dates[0]}', '{signal_dates[-1]}'], 'days': {len(signal_dates)}, 'rejected': agg, 'passed_cohort': pas, 'discipline': '研究级重放预览; 正式 n>=20 判定以生产账本前瞻积累为准'}})\n"
                f"os.makedirs(r'{os.path.dirname(os.path.join(HERE, 'handover', 'reject_backfill_report.json'))}', exist_ok=True)\n"
                f"json.dump(rep, open(r'{os.path.join(HERE, 'handover', 'reject_backfill_report.json')}', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)\n"
                "print('已写 handover/reject_backfill_report.json')\n"
            )
        r = subprocess.run([sys.executable, "-X", "utf8", _ev], capture_output=True, text=True)
        os.remove(_ev)
        print(r.stdout if r.stdout else "", end="")
        if r.returncode != 0:
            print(r.stderr[-1500:])
            return 1
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.exit(main())