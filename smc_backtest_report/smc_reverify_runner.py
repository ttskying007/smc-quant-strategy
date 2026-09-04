# -*- coding: utf-8 -*-
"""SMC_REVERIFY_RUNNER - 通用新本体准入流水线框架（固化版）。

所有新 SMC 本体晋级生产前必须按此框架执行（防再犯规则 R1-R7/R13-R15/R22）：

  ① outcome-free seed 生成（只读 entry 前数据，目标/止损入场前可见）
  ② 独立 oracle（同语义不同实现的身份集合对比）
  ③ 冻结严格 T+1 回放（可成交入场、费用、SL 优先、GAP_SL）
  ④ smc_gates 经济门槛（V633：n/WR/AvgNet/PF/payoff/年/月/T+1）
  ⑤ 统一准入报告 + artifact 落盘

用法：
  from smc_reverify_runner import run_admission
  report = run_admission(name='MY_ONTOLOGY', kline_dir=..., seed_fn=..., oracle_fn=...,
                         replay_fn=..., params={...}, out_dir=...)
"""
import csv, json, os, time, datetime


def run_admission(name, kline_dir, seed_fn, oracle_fn, replay_fn, params, out_dir,
                  years=("2023", "2024", "2025", "2026")):
    """seed_fn(symbol, bars, params) -> list[seed dict with entry_identity & entry fields]
       oracle_fn(symbol, bars) -> set of identity strings (independent implementation)
       replay_fn(seed, bars, params) -> trade dict or None (frozen strict T+1)
    """
    from smc_gates import check_economic_gate
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()

    def _date(b):
        s = "".join(c for c in str(b.get("t") or b.get("date") or "") if c.isdigit())
        return s[:8] if len(s) >= 8 else ""

    def _bars(path):
        try:
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception:
            return []
        out = []
        for r in raw if isinstance(raw, list) else []:
            t = _date(r)
            o, h, l, c = (float(r.get(k) or 0) for k in ("o", "h", "l", "c"))
            if t and o and h and l and c:
                out.append({"t": t, "o": o, "h": h, "l": l, "c": c})
        out.sort(key=lambda b: b["t"])
        return out

    seeds, trades = [], []
    n_files = 0
    for p in sorted(os.listdir(kline_dir)):
        if not p.endswith("_daily_750.json"):
            continue
        n_files += 1
        bars = _bars(os.path.join(kline_dir, p))
        if len(bars) < 200:
            continue
        sym = p.replace("_daily_750.json", "").replace("_", ".", 1)
        for sd in seed_fn(sym, bars, params):
            seeds.append(sd)
            tr = replay_fn(sd, bars, params)
            if tr is not None:
                trades.append(tr)
        if n_files % 500 == 0:
            print(f"  [{name}] scanned {n_files}, seeds {len(seeds)}, trades {len(trades)} ({time.time()-t0:.0f}s)", flush=True)

    # oracle
    oracle_ids = set()
    for p in sorted(os.listdir(kline_dir)):
        if not p.endswith("_daily_750.json"):
            continue
        sym = p.replace("_daily_750.json", "").replace("_", ".", 1)
        bars = _bars(os.path.join(kline_dir, p))
        if len(bars) < 200:
            continue
        oracle_ids |= oracle_fn(sym, bars)
    seed_ids = {s.get("entry_identity") for s in seeds if s.get("entry_identity")}
    inter = seed_ids & oracle_ids

    gate = check_economic_gate(trades, years=years)

    report = {
        "schema_version": "SMC_ADMISSION_RUNNER_V1",
        "ontology": name,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "params": params,
        "scanned_files": n_files,
        "seed_count": len(seeds),
        "trade_count": len(trades),
        "oracle": {"seed_ids": len(seed_ids), "oracle_ids": len(oracle_ids),
                   "intersection": len(inter),
                   "oracle_coverage_pct": round(100 * len(inter) / len(seed_ids), 2) if seed_ids else 0.0,
                   "note": "coverage<100% 表示 oracle 实现未覆盖 seed 全部逻辑段（实现覆盖差异），须排查是否为缺陷"},
        "economic_gate": gate,
        "elapsed_sec": round(time.time() - t0, 1),
        "artifacts": {"seeds": os.path.join(out_dir, f"{name}_seeds.csv"),
                      "trades": os.path.join(out_dir, f"{name}_trades.csv"),
                      "report": os.path.join(out_dir, f"{name}_admission_report.json")},
    }
    with open(os.path.join(out_dir, f"{name}_seeds.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(seeds[0].keys()) if seeds else ["symbol"])
        w.writeheader()
        for s in seeds:
            w.writerow(s)
    with open(os.path.join(out_dir, f"{name}_trades.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(trades[0].keys()) if trades else ["symbol"])
        w.writeheader()
        for t in trades:
            w.writerow(t)
    with open(os.path.join(out_dir, f"{name}_admission_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(f"[{name}] DONE: seeds={len(seeds)} trades={len(trades)} gate_pass={gate['gate_pass']} ({time.time()-t0:.0f}s)")
    return report
