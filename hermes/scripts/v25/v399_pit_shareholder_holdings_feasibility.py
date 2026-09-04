#!/usr/bin/env python3
"""V399 no-write feasibility gate for PIT top-shareholder snapshots.

This tests whether public quarterly/annual report metadata and the structured
Top-10 shareholder snapshots can be joined *before* a fixed V381 entry date.
It intentionally reads only symbol and entry_date; it never reads outcome,
PnL, exit, or trade-quality fields and cannot write production files.
"""
from __future__ import annotations

import csv
import json
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path("/root/.hermes")
TRADES = ROOT / "smc_audit/v381_true_mtf_raw_daily_poi_m60_replay_no_write_20260712_110522/v381_trades.csv"
AUDIT = ROOT / "smc_audit"
TS = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT = AUDIT / f"v399_pit_shareholder_holdings_feasibility_no_write_{TS}"
LATEST = AUDIT / "v399_pit_shareholder_holdings_feasibility_latest.json"

ANN_URL = "https://np-anotice-stock.eastmoney.com/api/security/ann"
HOLDER_URL = "https://emweb.securities.eastmoney.com/PC_HSF10/ShareholderResearch/PageSDGD"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
REPORT_RE = re.compile(r"(?P<year>20\d{2})年(?P<kind>年度|半年度|第?[一二三四1234]季度)报告")


def clean_date(value: object) -> str:
    return "".join(c for c in str(value or "") if c.isdigit())[:8]


def report_end(title: str) -> str | None:
    title = re.sub(r"\s+", "", title)
    if "摘要" in title or "英文" in title or "修订" in title or "更正" in title:
        return None
    match = REPORT_RE.search(title)
    if not match:
        return None
    year, kind = match.group("year"), match.group("kind")
    suffix = {
        "年度": "1231",
        "半年度": "0630",
        "一季度": "0331", "第一季度": "0331", "1季度": "0331",
        "三季度": "0930", "第三季度": "0930", "3季度": "0930",
        "二季度": "0630", "第二季度": "0630", "2季度": "0630",
        "四季度": "1231", "第四季度": "1231", "4季度": "1231",
    }.get(kind)
    return year + suffix if suffix else None


def prefix(symbol: str) -> str:
    code, market = symbol.split(".")
    return ("SH" if market == "SH" else "SZ") + code


def fixed_identities() -> list[dict[str, str]]:
    with TRADES.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        return [{"symbol": row["symbol"], "entry_date": clean_date(row["entry_date"])} for row in reader]


def get_json(url: str, params: dict[str, object]) -> tuple[requests.Response, dict[str, object]]:
    """Retry Eastmoney's transient HTML anti-bot pages; never treat them as no data."""
    last_error: Exception | None = None
    for attempt in range(6):
        try:
            response = requests.get(url, params=params, headers=HEADERS, timeout=30)
            payload = response.json()
            if isinstance(payload, dict):
                return response, payload
            raise ValueError("non-object JSON payload")
        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(0.75 * (attempt + 1))
    raise RuntimeError(f"transient endpoint failure after retries: {last_error}")


def announcements(symbol: str) -> tuple[str, list[dict[str, str]]]:
    rows: list[dict[str, str]] = []
    page = 1
    while True:
        response, payload = get_json(
            ANN_URL,
            {
                "client_source": "web", "page_size": 100, "page_index": page,
                "ann_type": "A", "stock_list": symbol.split(".")[0],
                "begin_time": "2022-01-01", "end_time": "2026-07-11",
            },
        )
        payload = payload.get("data", {})
        listed = payload.get("list") or []
        for item in listed:
            period = report_end(str(item.get("title") or ""))
            notice = clean_date(item.get("notice_date"))
            if period and notice:
                rows.append({
                    "report_end": period,
                    "notice_date": notice,
                    "announcement_id": str(item.get("art_code") or ""),
                    "publication_time": str(item.get("eiTime") or ""),
                    "title": str(item.get("title") or ""),
                })
        pages = int(payload.get("total_hits") or 0)
        if page * 100 >= pages or not listed:
            break
        page += 1
    # Each filing can have a full report and duplicate correction/abstract records.
    # Retain the earliest documented announcement for a report period.
    earliest: dict[str, dict[str, str]] = {}
    for row in rows:
        old = earliest.get(row["report_end"])
        if old is None or row["notice_date"] < old["notice_date"]:
            earliest[row["report_end"]] = row
    return symbol, list(earliest.values())


def holder_snapshot(key: tuple[str, str]) -> tuple[tuple[str, str], dict[str, object]]:
    symbol, end = key
    response, payload = get_json(
        HOLDER_URL,
        {"code": prefix(symbol), "date": f"{end[:4]}-{end[4:6]}-{end[6:]}"},
    )
    rows = payload.get("sdgd") or []
    return key, {
        "http_ok": response.status_code == 200,
        "row_count": len(rows),
        "has_holder_name": any(bool(x.get("HOLDER_NAME")) for x in rows if isinstance(x, dict)),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    identities = fixed_identities()
    symbols = sorted({row["symbol"] for row in identities})
    metadata: dict[str, list[dict[str, str]]] = {}
    errors: dict[str, str] = {}

    # Four workers plus retry keep this public endpoint below its transient anti-bot threshold.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(announcements, symbol): symbol for symbol in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                got_symbol, rows = future.result()
                metadata[got_symbol] = rows
            except Exception as exc:  # keep feasibility accounting explicit
                errors[symbol] = f"{type(exc).__name__}: {exc}"

    selected: list[dict[str, str]] = []
    unavailable: Counter[str] = Counter()
    for row in identities:
        reports = metadata.get(row["symbol"], [])
        eligible = [
            report for report in reports
            if report["report_end"] < row["entry_date"] and report["notice_date"] < row["entry_date"]
        ]
        if not eligible:
            unavailable["NO_PRIOR_PUBLIC_REPORT"] += 1
            selected.append({**row, "mapping_status": "NO_PRIOR_PUBLIC_REPORT"})
            continue
        report = max(eligible, key=lambda x: (x["report_end"], x["notice_date"]))
        selected.append({**row, **report, "mapping_status": "MAPPED"})

    keys = sorted({(row["symbol"], row["report_end"]) for row in selected if row["mapping_status"] == "MAPPED"})
    snapshots: dict[tuple[str, str], dict[str, object]] = {}
    snapshot_errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(holder_snapshot, key): key for key in keys}
        for future in as_completed(futures):
            key = futures[future]
            try:
                got_key, data = future.result()
                snapshots[got_key] = data
            except Exception as exc:
                snapshot_errors["|".join(key)] = f"{type(exc).__name__}: {exc}"

    by_year: dict[str, Counter[str]] = defaultdict(Counter)
    output_rows: list[dict[str, object]] = []
    for row in selected:
        year = row["entry_date"][:4]
        status = row["mapping_status"]
        snap: dict[str, object] = {}
        if status == "MAPPED":
            snap = snapshots.get((row["symbol"], row["report_end"]), {})
            if not snap:
                status = "SNAPSHOT_REQUEST_FAILED"
            elif int(snap.get("row_count") or 0) == 0:
                status = "NO_STRUCTURED_HOLDER_SNAPSHOT"
            elif not bool(snap.get("has_holder_name")):
                status = "SNAPSHOT_MISSING_HOLDER_NAME"
            else:
                status = "PIT_HOLDER_SNAPSHOT_READY"
        by_year[year]["total"] += 1
        by_year[year][status] += 1
        output_rows.append({**row, "mapping_status": status, **snap})

    total = len(output_rows)
    ready = sum(row["mapping_status"] == "PIT_HOLDER_SNAPSHOT_READY" for row in output_rows)
    yearly = {}
    for year, counts in sorted(by_year.items()):
        n, ok = counts["total"], counts["PIT_HOLDER_SNAPSHOT_READY"]
        yearly[year] = {**dict(counts), "ready_pct": round(ok / n * 100, 4) if n else 0}

    fields = [
        "symbol", "entry_date", "report_end", "notice_date", "publication_time",
        "announcement_id", "title", "mapping_status", "http_ok", "row_count", "has_holder_name",
    ]
    with (OUT / "v399_fixed_identity_pit_holder_mapping.csv").open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output_rows)

    gate = {
        "mapping_ready_pct_min": 95.0,
        "each_year_ready_pct_min": 95.0,
        "publication_rule": "only report_end < entry_date and public notice_date < entry_date; same-day use is prohibited",
        "outcome_replay_allowed": False,
    }
    all_years_pass = all(x["ready_pct"] >= 95.0 for x in yearly.values())
    coverage_pass = ready / total * 100 >= 95.0 if total else False
    result = {
        "version": "V399_PIT_TOP10_SHAREHOLDER_HOLDINGS_FEASIBILITY_NO_WRITE",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "no_write": True,
        "production_write": False,
        "frontend_write": False,
        "watchlist_write": False,
        "input_contract": "fixed V381 identities: reads symbol and entry_date only; does not read outcome/PnL/exit fields",
        "source_contract": "Eastmoney public report announcement metadata + report-period structured Top-10 shareholder snapshot",
        "pit_contract": gate["publication_rule"],
        "counts": {
            "fixed_identities": total,
            "symbols": len(symbols),
            "announcement_metadata_ready_symbols": len(metadata),
            "announcement_metadata_failed_symbols": len(errors),
            "unique_symbol_report_snapshots": len(keys),
            "snapshot_request_failures": len(snapshot_errors),
            "pit_holder_snapshot_ready": ready,
            "ready_pct": round(ready / total * 100, 4) if total else 0,
        },
        "yearly": yearly,
        "feasibility_gate": gate,
        "feasibility_pass": coverage_pass and all_years_pass,
        "decision": (
            "PIT_HOLDER_SOURCE_FEASIBLE__FEATURE_SCHEMA_AND_FROZEN_OUTCOME_REPLAY_NEXT"
            if coverage_pass and all_years_pass else
            "PIT_HOLDER_SOURCE_INSUFFICIENT_COVERAGE__NO_OUTCOME_REPLAY"
        ),
        "invariants": {
            "outcome_fields_read": False,
            "same_day_report_use_forbidden": True,
            "all_selected_reports_public_before_entry": all(
                row.get("mapping_status") != "PIT_HOLDER_SNAPSHOT_READY" or row["notice_date"] < row["entry_date"]
                for row in output_rows
            ),
            "all_selected_report_periods_before_entry": all(
                row.get("mapping_status") != "PIT_HOLDER_SNAPSHOT_READY" or row["report_end"] < row["entry_date"]
                for row in output_rows
            ),
        },
        "artifacts": {
            "out_dir": str(OUT),
            "mapping": str(OUT / "v399_fixed_identity_pit_holder_mapping.csv"),
            "latest": str(LATEST),
        },
        "errors": {"announcement_metadata": errors, "holder_snapshot": snapshot_errors},
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / "v399_report.json").write_text(text, encoding="utf-8")
    LATEST.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
