#!/usr/bin/env python3
"""
SMC Full Dashboard — 全信号渲染 + 回测看板 + 实时监控 + AI分析 + 架构文档
V11: OB_Bull + Sweep_SSL + Breaker_Bull + 自适应SL/TP
"""
import json, sys, time, html, statistics, os, subprocess, threading, sqlite3
import datetime as dtmod
from pathlib import Path
from collections import Counter
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta

sys.path.insert(0, '/root/.hermes/scripts')
sys.path.insert(0, '/root/.hermes/scripts/v25')
import v517_frontend_adapter as v517_frontend
PORT = 8890
BACKTEST_DAYS = 365 * 3
# Version helpers / lightweight caches
_V50_SIGNAL_SNAPSHOT_CACHE = None
_V50_SIGNAL_SNAPSHOT_MTIME = None

def load_v50_signal_snapshot(symbol=None):
    """Load one symbol from the large V50 signal snapshot without parsing the full 700MB file."""
    global _V50_SIGNAL_SNAPSHOT_CACHE, _V50_SIGNAL_SNAPSHOT_MTIME
    fp = Path('/root/.hermes/smc_opt_v50_signal/v50_signal_snapshot.json')
    if not fp.exists():
        return [] if symbol else {}
    mt = fp.stat().st_mtime
    if symbol:
        try:
            import mmap
            key = json.dumps(symbol).encode()
            with fp.open('rb') as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as data:
                pos = data.find(key)
                if pos < 0:
                    return []
                colon = data.find(b':', pos + len(key))
                start = data.find(b'[', colon)
                if colon < 0 or start < 0:
                    return []
                depth = 0; in_str = False; esc = False
                for i in range(start, len(data)):
                    c = data[i]
                    if in_str:
                        if esc: esc = False
                        elif c == 92: esc = True
                        elif c == 34: in_str = False
                    else:
                        if c == 34: in_str = True
                        elif c == 91: depth += 1
                        elif c == 93:
                            depth -= 1
                            if depth == 0:
                                return json.loads(data[start:i+1])
        except Exception:
            return []
        return []
    if _V50_SIGNAL_SNAPSHOT_CACHE is None or _V50_SIGNAL_SNAPSHOT_MTIME != mt:
        _V50_SIGNAL_SNAPSHOT_CACHE = {}
        _V50_SIGNAL_SNAPSHOT_MTIME = mt
    return _V50_SIGNAL_SNAPSHOT_CACHE or {}

# FIX(2026-08-17): 生产版本只由 production registry 决定（R16）。
# 文件存在性推断已废除。V88 因前视偏差被正式否决
# （REJECTED_LOOKAHEAD，证据：V88重验报告.md）。EMPTY_BOOK 时为哨兵值。
try:
    import json as _json_mod
    _REGISTRY_RAW = _json_mod.loads(Path('/root/.hermes/smc_monitor/production_registry.json').read_text())
except Exception:
    _REGISTRY_RAW = {}
ACTIVE_VERSION = str(_REGISTRY_RAW.get('production_strategy') or 'EMPTY_BOOK')
REJECTED_VERSIONS = {
    'V88': 'REJECTED_LOOKAHEAD: TP target used future-20-bar highs; reverify WR 80%->41.6%, PF 6.2->1.10 (V88重验报告.md)',
    'V86': 'REJECTED_LOOKAHEAD: same future-bar liquidity lineage as V88',
    'V85': 'REJECTED_LOOKAHEAD: signal layer feeds V86/V88 future-bar liquidity',
}

ACTIVE_TRADE_FILE = (None if ACTIVE_VERSION == 'EMPTY_BOOK' else Path('/root/.hermes/smc_opt_v88_production_contract/v88_trades.json') if ACTIVE_VERSION == 'V88'
                     else Path('/root/.hermes/smc_opt_v86_production_gate/v86_trades.json') if ACTIVE_VERSION == 'V86'
                     else Path('/root/.hermes/smc_opt_v85_production_gate/v85_trades.json') if ACTIVE_VERSION == 'V85'
                     else Path('/root/.hermes/smc_opt_v80_full_candidate_production_gate/v80_trades.json') if ACTIVE_VERSION == 'V80'
                     else Path('/root/.hermes/smc_opt_v68_strict_ld/v68_trades.json') if ACTIVE_VERSION == 'V68'
                     else Path('/root/.hermes/smc_opt_v66/v66_trades.json') if ACTIVE_VERSION == 'V66'
                     else Path('/root/.hermes/smc_opt_v65/v65_trades.json') if ACTIVE_VERSION == 'V65'
                     else Path('/root/.hermes/smc_opt_v64/v64_trades.json') if ACTIVE_VERSION == 'V64'
                     else Path('/root/.hermes/smc_opt_v63/v63_trades.json') if ACTIVE_VERSION == 'V63'
                     else Path('/root/.hermes/smc_opt_v62/v62_trades.json') if ACTIVE_VERSION == 'V62'
                     else Path('/root/.hermes/smc_opt_v61/v61_trades.json') if ACTIVE_VERSION == 'V61'
                     else Path('/root/.hermes/smc_opt_v60/v60_trades.json') if ACTIVE_VERSION == 'V60'
                     else Path('/root/.hermes/smc_opt_v59/v59_trades.json') if ACTIVE_VERSION == 'V59'
                     else Path('/root/.hermes/smc_opt_v58/v58_trades.json') if ACTIVE_VERSION == 'V58'
                     else Path('/root/.hermes/smc_opt_v57/v57_trades.json') if ACTIVE_VERSION == 'V57'
                     else Path('/root/.hermes/smc_opt_v56/v56_trades.json') if ACTIVE_VERSION == 'V56'
                     else Path('/root/.hermes/smc_opt_v55/v55_trades.json') if ACTIVE_VERSION == 'V55'
                     else Path('/root/.hermes/smc_opt_v54/v54_trades.json') if ACTIVE_VERSION == 'V54'
                     else Path('/root/.hermes/smc_opt_v53/v53_trades.json') if ACTIVE_VERSION == 'V53'
                     else Path('/root/.hermes/smc_opt_v52/v52_trades.json') if ACTIVE_VERSION == 'V52'
                     else Path('/root/.hermes/smc_opt_v51/v51_trades.json') if ACTIVE_VERSION == 'V51'
                     else Path('/root/.hermes/smc_opt_v50/v50_trades.json') if ACTIVE_VERSION == 'V50'
                     else Path('/root/.hermes/smc_opt_v49_exit_optimized/v49_trades.json') if ACTIVE_VERSION == 'V49'
                     else Path('/root/.hermes/smc_opt_v48_1_production/v48_1_trades.json') if ACTIVE_VERSION == 'V48_1'
                     else Path('/root/.hermes/smc_opt_v47_2_candidate/v47_2_trades.json') if ACTIVE_VERSION == 'V47_2'
                     else Path('/root/.hermes/smc_opt_v46_1_layered_3y/v46_1_trades.json') if ACTIVE_VERSION == 'V46_1'
                     else Path('/root/.hermes/smc_opt_v44/v44_full.json') if ACTIVE_VERSION == 'V44'
                     else Path('/root/.hermes/smc_opt_v41/v41_trades.json') if ACTIVE_VERSION == 'V41'
                     else Path('/root/.hermes/smc_opt_v40/v40_trades.json') if ACTIVE_VERSION == 'V40'
                     else Path('/root/.hermes/smc_opt_v39/v39_trades.json') if ACTIVE_VERSION == 'V39'
                     else Path('/root/.hermes/smc_opt_v38/v38_trades.json') if ACTIVE_VERSION == 'V38'
                     else Path('/root/.hermes/smc_opt_v37/v37_trades.json') if ACTIVE_VERSION == 'V37'
                     else Path('/root/.hermes/smc_opt_v36/v36_trades.json') if ACTIVE_VERSION == 'V36'
                     else Path('/root/.hermes/smc_opt_v34d_final/v34_trades.json') if ACTIVE_VERSION == 'V34D'
                     else Path('/root/.hermes/smc_opt_v24/v24_trades.json') if ACTIVE_VERSION == 'V24'
                     else Path('/root/.hermes/smc_opt_v33/v33_trades.json') if ACTIVE_VERSION == 'V33'
                     else Path('/root/.hermes/smc_opt_v32d/v32d_trades.json') if ACTIVE_VERSION == 'V32D'
                     else Path('/root/.hermes/smc_opt_v32c/v32c_trades.json') if ACTIVE_VERSION == 'V32C'
                     else Path('/root/.hermes/smc_opt_v32b/v32b_trades.json') if ACTIVE_VERSION == 'V32B'
                     else Path('/root/.hermes/smc_opt_v31/v31_trades.json') if ACTIVE_VERSION == 'V31'
                     else Path('/root/.hermes/smc_opt_v30/v30_trades.json') if ACTIVE_VERSION == 'V30'
                     else Path('/root/.hermes/smc_opt_v29/v29_trades.json') if ACTIVE_VERSION == 'V29'
                     else Path('/root/.hermes/smc_opt_v28/v28_trades.json') if ACTIVE_VERSION == 'V28'
                     else Path('/root/.hermes/smc_opt_v27/v27_trades.json'))
ACTIVE_PICK_FILE = (None if ACTIVE_VERSION == 'EMPTY_BOOK' else Path('/root/.hermes/smc_opt_v88_production_contract/v88_picks.json') if ACTIVE_VERSION == 'V88'
                    else Path('/root/.hermes/smc_opt_v86_production_gate/v86_picks.json') if ACTIVE_VERSION == 'V86'
                    else Path('/root/.hermes/smc_opt_v85_production_gate/v85_picks.json') if ACTIVE_VERSION == 'V85'
                    else Path('/root/.hermes/smc_opt_v80_full_candidate_production_gate/v80_picks.json') if ACTIVE_VERSION == 'V80'
                    else Path('/root/.hermes/smc_opt_v68_strict_ld/v68_picks.json') if ACTIVE_VERSION == 'V68'
                    else Path('/root/.hermes/smc_opt_v66/v66_picks.json') if ACTIVE_VERSION == 'V66'
                    else Path('/root/.hermes/smc_opt_v65/v65_picks.json') if ACTIVE_VERSION == 'V65'
                    else Path('/root/.hermes/smc_opt_v64/v64_picks.json') if ACTIVE_VERSION == 'V64'
                    else Path('/root/.hermes/smc_opt_v63/v63_picks.json') if ACTIVE_VERSION == 'V63'
                    else Path('/root/.hermes/smc_opt_v62/v62_picks.json') if ACTIVE_VERSION == 'V62'
                    else Path('/root/.hermes/smc_opt_v61/v61_picks.json') if ACTIVE_VERSION == 'V61'
                    else Path('/root/.hermes/smc_opt_v60/v60_picks.json') if ACTIVE_VERSION == 'V60'
                    else Path('/root/.hermes/smc_opt_v59/v59_picks.json') if ACTIVE_VERSION == 'V59'
                    else Path('/root/.hermes/smc_opt_v58/v58_picks.json') if ACTIVE_VERSION == 'V58'
                    else Path('/root/.hermes/smc_opt_v57/v57_picks.json') if ACTIVE_VERSION == 'V57'
                    else Path('/root/.hermes/smc_opt_v56/v56_picks.json') if ACTIVE_VERSION == 'V56'
                    else Path('/root/.hermes/smc_opt_v55/v55_picks.json') if ACTIVE_VERSION == 'V55'
                    else Path('/root/.hermes/smc_opt_v54/v54_picks.json') if ACTIVE_VERSION == 'V54'
                    else Path('/root/.hermes/smc_opt_v53/v53_picks.json') if ACTIVE_VERSION == 'V53'
                    else Path('/root/.hermes/smc_opt_v52/v52_picks.json') if ACTIVE_VERSION == 'V52'
                    else Path('/root/.hermes/smc_opt_v51/v51_picks.json') if ACTIVE_VERSION == 'V51'
                    else Path('/root/.hermes/smc_opt_v50/v50_picks.json') if ACTIVE_VERSION == 'V50'
                    else Path('/root/.hermes/smc_opt_v49_exit_optimized/v49_picks.json') if ACTIVE_VERSION == 'V49'
                    else Path('/root/.hermes/smc_opt_v48_1_production/v48_1_picks.json') if ACTIVE_VERSION == 'V48_1'
                    else Path('/root/.hermes/smc_opt_v47_2_candidate/v47_2_picks.json') if ACTIVE_VERSION == 'V47_2'
                    else Path('/root/.hermes/smc_opt_v46_1_layered_3y/v46_1_watchlist.json') if ACTIVE_VERSION == 'V46_1'
                    else Path('/root/.hermes/smc_opt_v44/v44_picks.json') if ACTIVE_VERSION == 'V44'
                    else Path('/root/.hermes/smc_opt_v41/v41_picks.json') if ACTIVE_VERSION == 'V41'
                    else Path('/root/.hermes/smc_opt_v40/v40_picks.json') if ACTIVE_VERSION == 'V40'
                    else Path('/root/.hermes/smc_opt_v39/v39_picks.json') if ACTIVE_VERSION == 'V39'
                    else Path('/root/.hermes/smc_opt_v38/v38_picks.json') if ACTIVE_VERSION == 'V38'
                    else Path('/root/.hermes/smc_opt_v37/v37_picks.json') if ACTIVE_VERSION == 'V37'
                    else Path('/root/.hermes/smc_opt_v36/v36_picks.json') if ACTIVE_VERSION == 'V36'
                    else Path('/root/.hermes/smc_opt_v34d_final/v34_picks.json') if ACTIVE_VERSION == 'V34D'
                    else Path('/root/.hermes/smc_opt_v24/v24_picks.json') if ACTIVE_VERSION == 'V24'
                    else Path('/root/.hermes/smc_opt_v33/v33_picks.json') if ACTIVE_VERSION == 'V33'
                    else Path('/root/.hermes/smc_opt_v32d/v32d_picks.json') if ACTIVE_VERSION == 'V32D'
                    else Path('/root/.hermes/smc_opt_v32c/v32c_picks.json') if ACTIVE_VERSION == 'V32C'
                    else Path('/root/.hermes/smc_opt_v32b/v32b_picks.json') if ACTIVE_VERSION == 'V32B'
                    else Path('/root/.hermes/smc_opt_v31/v31_picks.json') if ACTIVE_VERSION == 'V31'
                    else Path('/root/.hermes/smc_opt_v30/v30_picks.json') if ACTIVE_VERSION == 'V30'
                    else Path('/root/.hermes/smc_opt_v29/v29_picks.json') if ACTIVE_VERSION == 'V29'
                    else Path('/root/.hermes/smc_opt_v28/v28_picks.json') if ACTIVE_VERSION == 'V28'
                    else Path('/root/.hermes/smc_opt_v27/v27_picks.json'))

V47_2_DIR = Path('/root/.hermes/smc_opt_v47_2_candidate')
V48_1_DIR = Path('/root/.hermes/smc_opt_v48_1_production')
V49_DIR = Path('/root/.hermes/smc_opt_v49_exit_optimized')
V50_DIR = Path('/root/.hermes/smc_opt_v50')
V51_DIR = Path('/root/.hermes/smc_opt_v51')
V52_DIR = Path('/root/.hermes/smc_opt_v52')
V53_DIR = Path('/root/.hermes/smc_opt_v53')
V54_DIR = Path('/root/.hermes/smc_opt_v54')
V55_DIR = Path('/root/.hermes/smc_opt_v55')
V56_DIR = Path('/root/.hermes/smc_opt_v56')
V57_DIR = Path('/root/.hermes/smc_opt_v57')
V58_DIR = Path('/root/.hermes/smc_opt_v58')
V59_DIR = Path('/root/.hermes/smc_opt_v59')
V60_DIR = Path('/root/.hermes/smc_opt_v60')
V61_DIR = Path('/root/.hermes/smc_opt_v61')
V62_DIR = Path('/root/.hermes/smc_opt_v62')
V63_DIR = Path('/root/.hermes/smc_opt_v63')
V64_DIR = Path('/root/.hermes/smc_opt_v64')
V65_DIR = Path('/root/.hermes/smc_opt_v65')
V66_DIR = Path('/root/.hermes/smc_opt_v66')
V68_DIR = Path('/root/.hermes/smc_opt_v68_strict_ld')
V80_DIR = Path('/root/.hermes/smc_opt_v80_full_candidate_production_gate')
V85_DIR = Path('/root/.hermes/smc_opt_v85_production_gate')
V86_DIR = Path('/root/.hermes/smc_opt_v86_production_gate')
V88_DIR = Path('/root/.hermes/smc_opt_v88_production_contract')
V90_DIR = Path('/root/.hermes/smc_opt_v90_daily_full_market_scanner')
V91_DIR = Path('/root/.hermes/smc_opt_v91_shadow_zone_entry_scanner')
V97_DIR = Path('/root/.hermes/smc_opt_v97_structural_rr_contract')
V98_DIR = Path('/root/.hermes/smc_opt_v98_reachable_5r_probability_gate')
V99_DIR = Path('/root/.hermes/smc_opt_v99_high_wr_gate')
V100_DIR = Path('/root/.hermes/smc_opt_v100_structural_net_gate')
V102_DIR = Path('/root/.hermes/smc_opt_v102_balanced_volume_gate')
V185_DIR = Path('/root/.hermes/smc_opt_v185_combined_production_candidate')
V175_DIR = Path('/root/.hermes/smc_opt_v175_semantic_split')
V172_DIR = Path('/root/.hermes/smc_opt_v172_v167_high_quality_gate')
V167_DIR = Path('/root/.hermes/smc_opt_v167_exact_scanner_gate')
V103A_DIR = Path('/root/.hermes/smc_opt_v103a_risk_gate')
V101_DIR = Path('/root/.hermes/smc_opt_v101_mtf_dna_combo_contract')
V152_DIR = Path('/root/.hermes/smc_opt_v152_hybrid_lifecycle_gate')
V72_DIR = Path('/root/.hermes/smc_opt_v72_layered')
PRODUCTION_REGISTRY_FILE = Path('/root/.hermes/smc_monitor/production_registry.json')
KLINE_EPOCH_CURRENT_FILE = Path('/root/.hermes/smc_monitor/kline_epoch_current.json')
V526_LIVE_STATE_FILE = Path('/root/.hermes/smc_monitor/v526_live_state.json')


def _production_registry():
    try:
        data = json.loads(PRODUCTION_REGISTRY_FILE.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _current_committed_data_epoch(fallback=None):
    """For an EMPTY_BOOK, expose cache freshness without implying a buy license."""
    try:
        epoch = json.loads(KLINE_EPOCH_CURRENT_FILE.read_text(encoding='utf-8'))
        if epoch.get('status') == 'COMMITTED' and epoch.get('epoch_id') and epoch.get('market_date'):
            return {'valid': True, 'epoch_id': epoch['epoch_id'], 'market_date': epoch['market_date'], 'status': 'COMMITTED'}
    except Exception:
        pass
    return fallback or {}


def _production_empty_book():
    registry = _production_registry()
    return registry.get('production_strategy') is None


def _v526_live_production():
    return _production_registry().get('production_strategy') == 'V526_V517_DAILY_EFFORT_RESULT_ABSORPTION'


def _v526_state():
    return _load_json_dict(V526_LIVE_STATE_FILE, {})

def _promoted_contract_dir():
    # V152 is a diagnostic artifact only: later V153 audit proved synthetic-BE
    # and micro-profit pollution, so its report must not promote frontend/API.
    # V103A files remain audit artifacts until ex-ante gates are proven clean.
    # Do not promote them into frontend/live routing: v103a_active_picks.json
    # contains historical completed trades, not current full-market candidates.
    if _production_empty_book():
        return None, ''
    if (V185_DIR / 'v185_report.json').exists():
        return V185_DIR, 'v185'
    if (V175_DIR / 'v175_report.json').exists():
        return V175_DIR, 'v175'
    if (V172_DIR / 'v172_report.json').exists():
        return V172_DIR, 'v172'
    if (V167_DIR / 'v167_report.json').exists():
        return V167_DIR, 'v167'
    if (V102_DIR / 'v101_report.json').exists():
        return V102_DIR, 'v102'
    if (V101_DIR / 'v101_report.json').exists():
        return V101_DIR, 'v101'
    if (V100_DIR / 'v100_report.json').exists():
        return V100_DIR, 'v100'
    return None, ''


def _load_v103a_stability_report():
    fp = V103A_DIR / 'v103a_stability_report.json'
    if not fp.exists():
        return {}
    try:
        return json.loads(fp.read_text())
    except Exception:
        return {}


def _pct_cell(v):
    try:
        return f"{float(v):.2f}%"
    except Exception:
        return '-'


def _build_v103a_stability_html():
    data = _load_v103a_stability_report()
    if not data:
        return ''
    versions = data.get('versions') or []
    comp = data.get('comparison') or {}
    by_label = {str(v.get('label', '')).upper(): v for v in versions if isinstance(v, dict)}
    v102 = data.get('v102') or by_label.get('V102') or (versions[0] if versions else {})
    v103 = data.get('v103a') or by_label.get('V103A') or (versions[-1] if versions else {})

    def g(item, key, default=0):
        return (item or {}).get(key, default)

    metric_rows = []
    for label, item in [('V102', v102), ('V103A', v103)]:
        gross = g(item, 'global') or g(item, 'gross') or {}
        metric_rows.append(
            f"<tr><td class=mono>{html.escape(label)}</td>"
            f"<td class=mono>{gross.get('trades','-')}</td>"
            f"<td class=mono style='color:#f85149'>{_pct_cell(gross.get('sl_rate'))}</td>"
            f"<td class=mono style='color:#3fb950'>{_pct_cell(gross.get('net_win_rate_ge_0_8'))}</td>"
            f"<td class=mono>{_pct_cell(gross.get('avg_net_pnl_pct'))}</td>"
            f"<td class=mono>{html.escape(str(item.get('months_lt_5','-')))}</td>"
            f"<td class=mono>{html.escape(','.join(m.get('month','') for m in item.get('true_anomaly_months', [])) or '-')}</td></tr>"
        )

    rolling_rows = []
    for key in ('rolling20', 'rolling50'):
        for label, item in [('V102', v102), ('V103A', v103)]:
            r = (item or {}).get(key) or {}
            rolling_rows.append(
                f"<tr><td class=mono>{key}</td><td class=mono>{label}</td>"
                f"<td class=mono>{r.get('count', r.get('windows','-'))}</td>"
                f"<td class=mono style='color:#f85149'>{_pct_cell(r.get('max_sl_rate'))}</td>"
                f"<td class=mono>{_pct_cell(r.get('mean_sl_rate', r.get('avg_sl_rate')))}</td>"
                f"<td class=mono>{_pct_cell(r.get('stdev_sl_rate'))}</td></tr>"
            )

    delta_rows = ''.join([
        f"<tr><td>rolling20 最大SL率</td><td class=mono>{_pct_cell(comp.get('rolling20_max_delta'))}</td></tr>",
        f"<tr><td>rolling20 方差</td><td class=mono>{_pct_cell(comp.get('rolling20_stdev_delta'))}</td></tr>",
        f"<tr><td>rolling50 最大SL率</td><td class=mono>{_pct_cell(comp.get('rolling50_max_delta'))}</td></tr>",
        f"<tr><td>rolling50 方差</td><td class=mono>{_pct_cell(comp.get('rolling50_stdev_delta'))}</td></tr>",
        f"<tr><td>移除异常月份</td><td class=mono>{html.escape(','.join(comp.get('anomaly_months_removed') or []) or '-')}</td></tr>",
        f"<tr><td>残留异常月份</td><td class=mono>{html.escape(','.join(comp.get('anomaly_months_remaining') or []) or '-')}</td></tr>",
    ])

    return f"""
<div class=\"card\"><h2>V103-A 稳定性审计</h2>
<p style=\"color:#8b949e\">数据源：v103a_stability_report.json；口径：net WR≥0.8% + 月度SL率 + rolling20/rolling50。</p>
<div class=\"flex\" style=\"gap:8px\">
<div style=\"flex:1\"><h3>月度汇总</h3><table><thead><tr><th>版本</th><th>交易</th><th>SL率</th><th>Net WR</th><th>Avg Net</th><th>&lt;5笔月</th><th>异常月</th></tr></thead><tbody>{''.join(metric_rows)}</tbody></table></div>
<div style=\"flex:1\"><h3>改善幅度</h3><table><tbody>{delta_rows}</tbody></table></div>
</div>
<h3>Rolling 稳定性</h3><table><thead><tr><th>窗口</th><th>版本</th><th>样本窗</th><th>最大SL率</th><th>平均SL率</th><th>SL方差</th></tr></thead><tbody>{''.join(rolling_rows)}</tbody></table>
</div>"""

def _frontend_version_label():
    """Visible production label: keep V88 data-routing shell, show promoted contract."""
    if _production_empty_book():
        return 'EMPTY_BOOK'
    d, prefix = _promoted_contract_dir()
    return prefix.upper() if d else ACTIVE_VERSION

FRONTEND_VERSION = _frontend_version_label()
V66_DAILY_CANDIDATES = V66_DIR / 'v66_daily_candidates.json'

# V54 monitor lifecycle state: daily/manual picks -> live monitoring -> TP/SL review.
try:
    from smc_monitor_state import ingest_daily_picks, add_manual_pick, load_positions, summary as monitor_state_summary, update_with_live_results, fill_pending_orders, load_trade_ledger, load_json as monitor_load_json, REVIEW as MONITOR_REVIEW, date_key as monitor_date_key, t1_exit_allowed
except Exception:
    ingest_daily_picks = add_manual_pick = load_positions = monitor_state_summary = update_with_live_results = fill_pending_orders = load_trade_ledger = None
    monitor_load_json = None
    MONITOR_REVIEW = None
    monitor_date_key = None
    t1_exit_allowed = None

CACHE = Path('/root/.hermes/kline_cache')
CACHE_60 = Path('/root/.hermes/kline_cache_60min')
OUT_V9 = Path('/root/.hermes/smc_opt_v9')
OUT_V10 = Path('/root/.hermes/smc_opt_v10')
OUT_V11 = Path('/root/.hermes/smc_opt_v11')
AI_REPORT = OUT_V9 / 'analysis' / 'ai_analysis_report.json'
MONITOR_DIR = Path('/root/.hermes/smc_opt_v6')
MONITOR_PICKS = Path('/root/.hermes/smc_opt_v6/monitor_clean.json')

V45_NATIVE_DIR = Path('/root/.hermes/smc_opt_v45_native')
V45_1_DIR = Path('/root/.hermes/smc_opt_v45_1')
V45_2_DIR = Path('/root/.hermes/smc_opt_v45_2')
V45_3_DIR = Path('/root/.hermes/smc_opt_v45_3')
V45_4_DIR = Path('/root/.hermes/smc_opt_v45_4')
V45_5_DIR = Path('/root/.hermes/smc_opt_v45_5')
V44_STOPLOSS_AUDIT = Path('/root/.hermes/smc_opt_v44/v44_stoploss_next_audit.json')


def load_json(path, default=None):
    try:
        if Path(path).exists():
            return json.loads(Path(path).read_text())
    except: pass
    return default or []


def _load_json_dict(path, default=None):
    try:
        p = Path(path)
        if p.exists():
            data = json.loads(p.read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else (default or {})
    except Exception:
        pass
    return default or {}

def _load_json_list(path, default=None, limit=None):
    try:
        p = Path(path)
        if p.exists():
            data = json.loads(p.read_text(encoding='utf-8'))
            if isinstance(data, dict) and 'all_trades' in data:
                data = data.get('all_trades', [])
            if not isinstance(data, list):
                data = []
            return data[:limit] if limit else data
    except Exception:
        pass
    return default or []

def load_v45_bundle(version='v45_4', limit_events=5000, limit_rows=1000):
    if version in ('v45_5', 'V45.5', 'V45_5'):
        base = V45_5_DIR
        files = {'report': base/'v45_5_report.json','validation': base/'v45_5_validation_summary.json','events': base/'events_v45_5.json','setups': base/'setups_v45_5.json','trades': base/'v45_5_trades.json','picks': base/'v45_5_picks.json','watchlist': base/'v45_5_watchlist.json','replay': base/'v45_5_replay_audit.json'}
    elif version in ('v45_4', 'V45.4', 'V45_4'):
        base = V45_4_DIR
        files = {'report': base/'v45_4_report.json','validation': base/'v45_4_validation_summary.json','events': base/'events_v45_4.json','setups': base/'setups_v45_4.json','trades': base/'v45_4_trades.json','picks': base/'v45_4_picks.json','watchlist': base/'v45_4_watchlist.json','replay': base/'v45_4_replay_audit.json'}
    elif version in ('v45_3', 'V45.3', 'V45_3'):
        base = V45_3_DIR
        files = {'report': base/'v45_3_report.json','validation': base/'v45_3_validation_summary.json','events': base/'events_v45_3.json','setups': base/'setups_v45_3.json','trades': base/'v45_3_trades.json','picks': base/'v45_3_picks.json','watchlist': base/'v45_3_watchlist.json','replay': base/'v45_3_replay_audit.json'}
    elif version in ('v45_2', 'V45.2', 'V45_2'):
        base = V45_2_DIR
        files = {'report': base/'v45_2_report.json','validation': base/'v45_2_validation_summary.json','events': base/'events_v45_2.json','setups': base/'setups_v45_2.json','trades': base/'v45_2_trades.json','picks': base/'v45_2_picks.json','watchlist': base/'v45_2_watchlist.json','replay': base/'v45_2_replay_audit.json'}
    elif version in ('v45_1', 'V45.1', 'V45_1'):
        base = V45_1_DIR
        files = {'report': base/'v45_1_report.json','validation': base/'v45_1_validation_summary.json','events': base/'events_v45_1.json','setups': base/'setups_v45_1.json','trades': base/'v45_1_trades.json','picks': base/'v45_1_picks.json','watchlist': base/'v45_1_watchlist.json','replay': base/'v45_1_replay_audit.json'}
    else:
        base = V45_NATIVE_DIR
        files = {'report': base/'v45_native_report.json','validation': base/'v45_validation_summary.json','events': base/'events_v45_native.json','setups': base/'setups_v45_native.json','trades': base/'v45_trades.json','picks': base/'v45_picks.json','watchlist': base/'v45_picks.json','replay': base/'v45_trades.json'}
    return {'version': version,'base': str(base),'exists': base.exists(),'report': _load_json_dict(files['report'], {}),'validation': _load_json_dict(files['validation'], {}),'events': _load_json_list(files['events'], [], limit_events),'setups': _load_json_list(files['setups'], [], limit_rows),'trades': _load_json_list(files['trades'], [], limit_rows),'picks': _load_json_list(files['picks'], [], limit_rows),'watchlist': _load_json_list(files['watchlist'], [], limit_rows),'replay': _load_json_list(files['replay'], [], limit_rows),'files': {k: str(v) for k, v in files.items()}}

# ── V27 compatibility: win detection uses pnl_pct > 0, not 'won' field ──
def is_winner(t):
    """True if trade is winning. Modern engines use pnl_pct; legacy may only use 'won'."""
    if isinstance(t, dict) and t.get('pnl_pct') not in (None, ''):
        try:
            return float(t.get('pnl_pct') or 0) > 0
        except (TypeError, ValueError):
            pass
    return bool(t.get('won', False))

def exit_key(t_or_reason):
    """Canonical exit reason key for V25-V31 frontend/diagnostics sync.

    Older engines emitted mixed-case names such as SL_hit/trailing/timeout,
    while V27+ emits SL_HIT/TRAILING_STOP. All analysis surfaces must count
    the same economic event regardless of casing/version.
    """
    reason = t_or_reason.get('exit_reason', '?') if isinstance(t_or_reason, dict) else t_or_reason
    r = str(reason or '?').strip().upper()
    aliases = {
        'SL_HIT': 'SL_HIT', 'STOP_LOSS': 'SL_HIT',
        'TP_HIT': 'TP_HIT', 'TP1_HIT': 'TP1_HIT', 'TP2_HIT': 'TP2_HIT', 'TP3_HIT': 'TP3_HIT',
        'TP1': 'TP1_HIT', 'TP2': 'TP2_HIT', 'TP3': 'TP3_HIT',
        'TRAILING': 'TRAILING_STOP', 'TRAILING_STOP': 'TRAILING_STOP', 'RUNNER_TRAIL': 'TRAILING_STOP',
        'TIMEOUT': 'TIMEOUT', 'TIME_STOP': 'TIMEOUT', 'TIMEOUT_PARTIAL': 'TIMEOUT_PARTIAL',
        'MULTI_EXIT': 'MULTI_EXIT',
    }
    return aliases.get(r, r)

EXIT_NAMES = {
    'SL_HIT': '止损', 'TP_HIT': '止盈', 'TP1_HIT': 'TP1', 'TP2_HIT': 'TP2', 'TP3_HIT': 'TP3',
    'TRAILING_STOP': '跟踪止盈', 'TIMEOUT': '超时', 'TIMEOUT_PARTIAL': '超时部分', 'MULTI_EXIT': '分批离场',
}

def exit_label(reason):
    k = exit_key(reason)
    return EXIT_NAMES.get(k, k)

def _date_key(v):
    return str(v or '').replace('-', '')[:8]

def _float_or_zero(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0

def _apply_smc_field_contract(row, default_engine=None):
    """Fill the cross-surface SMC field contract without changing row semantics."""
    r = dict(row or {})
    z = r.get('zone') if isinstance(r.get('zone'), dict) else {}
    gate = r.get('production_gate') if isinstance(r.get('production_gate'), dict) else {}
    ep = _float_or_zero(r.get('entry_price') or r.get('price') or r.get('current_price'))
    r['engine'] = r.get('engine') or r.get('strategy_version') or default_engine or ACTIVE_VERSION
    # V100/V98 structural-contract rows store POI geometry inside nested
    # production_gate, while older frontend code only read flat zone_low/high.
    # Promote those fields before all monitor/live/API surfaces format Zone,
    # cost line and volatility.
    if not r.get('production_gate') and gate:
        r['production_gate'] = gate
    if not r.get('zone_type'):
        r['zone_type'] = gate.get('zone_type') or gate.get('poi_type') or gate.get('type') or r.get('signal_type') or ''
    if not r.get('signal_type'):
        r['signal_type'] = r.get('zone_type') or ''
    r['zone_type'] = (r.get('zone_type') or r.get('signal_type') or z.get('type') or
                      r.get('v59_setup_family') or r.get('engine') or '')
    r['signal_type'] = r.get('signal_type') or r.get('zone_type') or ''
    r['pick_date'] = _date_key(r.get('pick_date') or r.get('select_date') or r.get('conf_date') or r.get('confirm_date') or r.get('retrace_date') or r.get('entry_date') or r.get('signal_date') or r.get('date'))
    r['signal_date'] = _date_key(r.get('signal_date') or r.get('conf_date') or r.get('confirm_date') or r.get('retrace_date') or r.get('pick_date') or r.get('entry_date') or r.get('date'))
    r['select_date'] = _date_key(r.get('select_date') or r.get('pick_date'))
    r['join_date'] = _date_key(r.get('join_date') or r.get('joined_date') or r.get('joined_at') or r.get('created_at') or r.get('select_date') or r.get('pick_date'))
    r['zone_low'] = _float_or_zero(r.get('zone_low') or r.get('execution_zone_low') or r.get('raw_zone_low') or r.get('dz_low') or r.get('lower') or z.get('zone_low') or z.get('low') or gate.get('zone_low') or gate.get('low'))
    r['zone_high'] = _float_or_zero(r.get('zone_high') or r.get('execution_zone_high') or r.get('raw_zone_high') or r.get('dz_high') or r.get('upper') or z.get('zone_high') or z.get('high') or gate.get('zone_high') or gate.get('high'))
    r['dz_low'] = _float_or_zero(r.get('dz_low') or r.get('zone_low'))
    r['dz_high'] = _float_or_zero(r.get('dz_high') or r.get('zone_high'))
    if not r.get('smart_money_cost'):
        r['smart_money_cost'] = r.get('cost_line') or r.get('v25_cost_line') or ((r['zone_low'] + r['zone_high']) / 2 if r['zone_low'] and r['zone_high'] else ep)
    if not r.get('cost_line'):
        r['cost_line'] = r.get('smart_money_cost') or ep
    if not r.get('volatility_pct'):
        r['volatility_pct'] = r.get('v25_atr_pct') or r.get('atr_pct') or r.get('risk_pct') or r.get('sl_initial_pct') or r.get('v25_sl_pct') or 0
    if not r.get('risk_pct'):
        r['risk_pct'] = r.get('sl_pct') or r.get('sl_initial_pct') or r.get('v25_sl_pct') or r.get('volatility_pct') or 0
    if not r.get('sl_pct'):
        r['sl_pct'] = r.get('risk_pct') or r.get('sl_initial_pct') or r.get('v25_sl_pct') or 0
    # Entry zone position
    if r.get('entry_zone_position') is None and r.get('zone_low') and r.get('zone_high') and ep:
        zl, zh = r['zone_low'], r['zone_high']
        if zh > zl:
            r['entry_zone_position'] = round((ep - zl) / (zh - zl), 4)
    # Canonical tp1/tp2 from design-price fields
    if not r.get('tp1'):
        r['tp1'] = _float_or_zero(r.get('tp1_design_price_v59') or r.get('tp1_design_price_v56') or r.get('tp1_design_price_v55'))
    if not r.get('tp2'):
        r['tp2'] = _float_or_zero(r.get('tp2_design_price_v59') or r.get('tp2_design_price_v56') or r.get('tp2_design_price_v55'))
    if not r.get('v25_cost_line'):
        r['v25_cost_line'] = r.get('cost_line') or r.get('smart_money_cost')
    if not r.get('v25_vol_class'):
        r['v25_vol_class'] = r.get('vol_class') or r.get('market_state') or r.get('regime') or r.get('quality_tier') or (f"RISK {_float_or_zero(r.get('volatility_pct')):.1f}%" if _float_or_zero(r.get('volatility_pct')) else r.get('zone_type') or '')
    if not r.get('vol_class'):
        r['vol_class'] = r.get('v25_vol_class') or (f"RISK {_float_or_zero(r.get('volatility_pct')):.1f}%" if _float_or_zero(r.get('volatility_pct')) else r.get('zone_type') or '')
    # V167+ cross-surface contract: never let DNA/组合/MTF/signal_price render blank.
    # Enriched production artifacts should carry real V101-style fields; these
    # fallbacks preserve a deterministic contract for older/un-enriched rows.
    if not r.get('signal_price'):
        r['signal_price'] = r.get('break_level') or r.get('signal_level') or r.get('price') or r.get('entry_price') or ep
    if not r.get('combo_contract_key'):
        event = str(r.get('event_type') or r.get('source_event') or r.get('signal_type') or '').upper()
        zone = str(r.get('zone_type') or r.get('poi_source') or r.get('signal_type') or '').upper()
        if 'SSL_SWEEP_CHOCH' in event and ('DEMAND' in zone or 'OB' in zone):
            r['combo_contract_key'] = 'REVERSAL_SSL_CHOCH_DEMAND_OB_STRUCTURAL_5R'
        elif 'BOS' in event and 'CONTINUATION' in event:
            r['combo_contract_key'] = 'CONTINUATION_BOS_PULLBACK_STRUCTURAL'
        elif 'BOS' in event or 'BREAKOUT' in event:
            r['combo_contract_key'] = 'BREAKOUT_BOS_ACCEPTANCE'
        else:
            r['combo_contract_key'] = r.get('combo_family') or 'PULLBACK_DISCOUNT_RECLAIM'
    if not r.get('combo_contract'):
        r['combo_contract'] = r.get('combo_contract_key')
    if not r.get('dna_preferred_behavior'):
        fam = str(r.get('combo_family') or r.get('combo_contract_key') or '').upper()
        r['dna_preferred_behavior'] = 'REVERSAL_SPECIALIST' if 'REVERSAL' in fam else ('CONTINUATION_OR_BREAKOUT_SPECIALIST' if 'CONTINUATION' in fam or 'BREAKOUT' in fam else 'WATCH_ONLY_UNCLASSIFIED')
    for _prefix, _state_key in (('weekly', 'weekly_state'), ('daily', 'daily_state'), ('m60', 'm60_state')):
        _state = r.get(_state_key) if isinstance(r.get(_state_key), dict) else {}
        if not r.get(f'{_prefix}_trend_state'):
            r[f'{_prefix}_trend_state'] = _state.get('trend_state') or 'UNKNOWN_MTF_NOT_ENRICHED'
        if not r.get(f'{_prefix}_structure_state'):
            r[f'{_prefix}_structure_state'] = _state.get('structure_state') or 'UNKNOWN_STRUCTURE_NOT_ENRICHED'
    if not r.get('daily_structure_state') and r.get('daily_state'):
        r['daily_structure_state'] = (r.get('daily_state') or {}).get('structure_state') if isinstance(r.get('daily_state'), dict) else r.get('daily_structure_state')
    if not r.get('daily_structure_state'):
        r['daily_structure_state'] = r.get('daily_trend_state') or 'UNKNOWN_STRUCTURE_NOT_ENRICHED'
    # Browser/API compatibility aliases used by monitor/live tables.
    r['pickDate'] = r.get('pickDate') or r.get('pick_date')
    r['joinDate'] = r.get('joinDate') or r.get('join_date')
    r['zoneLow'] = r.get('zoneLow') or r.get('zone_low')
    r['zoneHigh'] = r.get('zoneHigh') or r.get('zone_high')
    r['zoneType'] = r.get('zoneType') or r.get('zone_type')
    if not r.get('zone'):
        zl = _float_or_zero(r.get('zone_low'))
        zh = _float_or_zero(r.get('zone_high'))
        r['zone'] = f"{zl:.2f}~{zh:.2f}" if zl and zh else (r.get('zone_type') or '')
    r['costLine'] = r.get('costLine') or r.get('cost_line')
    r['volClass'] = r.get('volClass') or r.get('v25_vol_class')
    r['volatilityPct'] = r.get('volatilityPct') or r.get('volatility_pct')
    r['riskPct'] = r.get('riskPct') or r.get('risk_pct') or r.get('sl_pct')
    if r.get('volatility') in (None, ''):
        r['volatility'] = r.get('volatility_pct') or r.get('volatilityPct') or 0
    r['selectDate'] = r.get('selectDate') or r.get('select_date') or r.get('pick_date')
    r['entryDate'] = r.get('entryDate') or r.get('entry_date')
    r['选股日期'] = r.get('选股日期') or r.get('select_date') or r.get('pick_date')
    r['加入日期'] = r.get('加入日期') or r.get('join_date')
    r['semantic_layer'] = r.get('semantic_layer') or 'UNAUDITED'
    r['strict_audit_status'] = r.get('strict_audit_status') or 'UNAUDITED'
    r['signal_correctness_claim'] = r.get('signal_correctness_claim') or ('STRICT_PASS_FIELD_REPAIR_NEEDED' if r.get('strict_audit_status') == 'PASS' else 'PENDING_REPLAY')
    if not r.get('entry_mode'):
        if r.get('zone_type') == 'OB_Bull':
            r['entry_mode'] = 'OB_ZONE_RETRACE_OR_WATCH'
        elif r.get('zone_type') == 'FVG_Bull':
            r['entry_mode'] = 'FVG_IMMEDIATE_OR_REENTRY'
        else:
            r['entry_mode'] = ''
    if not r.get('market_state'):
        fam = r.get('v59_setup_family') or r.get('trade_role') or ''
        r['market_state'] = 'TREND_CONTINUATION_LEGACY' if fam == 'CONTINUATION_SETUP' else ('REENTRY_BREAKOUT_LEGACY' if fam == 'REENTRY_SETUP' else (r.get('regime') or ''))
    return r


def _contract_summary_html(rows, title='DNA/组合合同同步核验', limit=5):
    """Render a compact cross-surface contract block for frontend parity checks."""
    contracted = [_apply_smc_field_contract(r, default_engine=ACTIVE_VERSION) for r in (rows or [])]
    sample = contracted[:limit]
    if not sample:
        return f'<div class="card" style="border-left:3px solid #d29922"><h3>{html.escape(title)}</h3><p style="color:#8b949e">当前窗口无可展示行；API字段合同仍由 /api/picks、/api/live-prices、/api/summary 验证。</p></div>'
    from collections import Counter
    combo_counts = Counter(str(r.get('combo_contract_key') or r.get('combo_contract') or 'UNKNOWN') for r in contracted)
    dna_counts = Counter(str(r.get('dna_preferred_behavior') or r.get('smc_dna') or 'UNKNOWN') for r in contracted)
    engine_counts = Counter(str(r.get('engine') or ACTIVE_VERSION) for r in contracted)
    required = ['engine','pick_date','join_date','zone_type','zone_low','zone_high','cost_line','volatility_pct','signal_type','conf_type','signal_price','dna_preferred_behavior','combo_contract_key','weekly_trend_state','daily_structure_state','m60_state']
    missing = {k: sum(1 for r in contracted if r.get(k) in (None, '', 0, 0.0) and k not in ('zone_low','zone_high')) for k in required}
    missing_txt = ' | '.join(f'{k}:{v}' for k,v in missing.items() if v) or '全部0缺失'
    rows_html = ''
    for r in sample:
        zl = _float_or_zero(r.get('zone_low'))
        zh = _float_or_zero(r.get('zone_high'))
        zone = f'{r.get("zone_type") or r.get("signal_type") or "-"} [{zl:.2f}~{zh:.2f}]' if zl and zh else str(r.get('zone') or r.get('zone_type') or '-')
        rows_html += (
            f'<tr><td class=mono><a href="/kline?s={html.escape(str(r.get("symbol","")))}" style="color:var(--blue)">{html.escape(str(r.get("symbol","-")))}</a></td>'
            f'<td class=mono>{html.escape(str(r.get("engine") or ACTIVE_VERSION))}</td>'
            f'<td class=mono>{html.escape(str(r.get("pick_date") or "-"))}</td>'
            f'<td class=mono>{html.escape(str(r.get("join_date") or "-"))}</td>'
            f'<td class=mono style="font-size:10px;color:#58a6ff">{html.escape(zone)}</td>'
            f'<td class=mono style="color:#d29922">{_float_or_zero(r.get("cost_line")):.2f}</td>'
            f'<td class=mono>{_float_or_zero(r.get("volatility_pct")):.2f}%</td>'
            f'<td class=mono style="font-size:9px;color:#3fb950">{html.escape(str(r.get("dna_preferred_behavior") or r.get("smc_dna") or "-"))}</td>'
            f'<td class=mono style="font-size:9px;color:#d29922">{html.escape(str(r.get("combo_contract_key") or r.get("combo_contract") or "-"))}</td>'
            f'<td class=mono style="font-size:9px">{html.escape(str(r.get("weekly_trend_state") or r.get("weekly_state") or "-"))}/{html.escape(str(r.get("daily_structure_state") or r.get("daily_state") or "-"))}/{html.escape(str(r.get("m60_state") or "-"))}</td></tr>'
        )
    top_combo = ', '.join(f'{html.escape(k)}:{v}' for k,v in combo_counts.most_common(3))
    top_dna = ', '.join(f'{html.escape(k)}:{v}' for k,v in dna_counts.most_common(3))
    top_engine = ', '.join(f'{html.escape(k)}:{v}' for k,v in engine_counts.most_common(3))
    return f'''<div class="card" style="border-left:3px solid #58a6ff"><h3>{html.escape(title)}</h3>
<p style="color:#8b949e">版本={FRONTEND_VERSION} | 样本/总数={len(sample)}/{len(contracted)} | 引擎: {top_engine} | DNA: {top_dna} | 组合合同: {top_combo} | 字段缺失: {html.escape(missing_txt)}</p>
<table><thead><tr><th>代码</th><th>引擎</th><th>选股日期</th><th>加入日期</th><th>Zone</th><th>成本线</th><th>波动</th><th>DNA</th><th>组合合同</th><th>MTF</th></tr></thead><tbody>{rows_html}</tbody></table></div>'''


def _parse_date_key(v):
    s = _date_key(v)
    if len(s) != 8 or not s.isdigit():
        return None
    try:
        return datetime.strptime(s, '%Y%m%d')
    except ValueError:
        return None

def _trade_cutoff_from_data(trades):
    dates = [_parse_date_key(t.get('entry_date')) for t in trades]
    dates = [d for d in dates if d is not None]
    return max(dates) - timedelta(days=BACKTEST_DAYS) if dates else None

def normalize_v27_trades(trades):
    """Canonical contract for all frontend surfaces. Supports V27 and V28."""
    cutoff = _trade_cutoff_from_data(trades)
    out = []
    for t in trades:
        d = _parse_date_key(t.get('entry_date'))
        if ACTIVE_VERSION not in ('V88', 'V86', 'V85') and cutoff is not None and (d is None or d < cutoff):
            continue
        engine = t.get('engine', '')
        if engine in ('V27_STRICT', 'V28_PURE_SMC', 'V29_HIGH_QUALITY', 'V30_SMC_SEQUENCE', 'V31_ICT_ARCH', 'V32B_STRICT_ENTRY', 'V32C_LIMIT_RTO', 'V32D_FILTERED_RTO', 'V33_MSS_RTO', 'V34D_LUX_OB_QUALITY', 'V36_OVERLAP_FILTERED', 'V37_PAYOFF_REPAIRED', 'V38_PINE_GAP_CLOSED', 'V39_CHOCH_QUALITY', 'V40_REPLAY_EXIT', 'V41_REPLAY_ENTRY_EXIT', 'V44_STOPLOSS_REPAIR') or str(engine).startswith('V44') or t.get('definition_version') in ('smc_core_v27', 'smc_core_v28', 'smc_core_v29', 'smc_core_v30', 'smc_core_v31', 'smc_core_v32b', 'smc_core_v32c', 'smc_core_v32d', 'smc_core_v33', 'smc_core_v34', 'smc_core_v36', 'smc_core_v37', 'smc_core_v38', 'smc_core_v39', 'smc_core_v40', 'smc_core_v41', 'smc_core_v44'):
            t['won'] = _float_or_zero(t.get('pnl_pct')) > 0
        t['exit_key'] = exit_key(t)
        # Fill empty seq/ctx_seq/detail for frontend compatibility
        if not t.get('ctx_seq'):
            t['ctx_seq'] = f"{t.get('zone_type','')}→{t.get('source_event','')}→{t.get('conf_type','')}"
        if not t.get('seq'):
            t['seq'] = f"{t.get('zone_type','')}-{t.get('source_event','')}-{t.get('conf_type','')}"
        if not t.get('detail'):
            t['detail'] = t['ctx_seq']
        out.append(t)
    return out

def normalize_v27_picks(picks, trades):
    """Keep picks synchronized with the active 3-year trade universe.

    V46.1/V47.2 contract: /api/picks must represent current watchlist/active candidates,
    not historical backtest representatives. Watch rows do not always have
    entry_date, so use pick_date/conf_date/retrace_date/signal_date and preserve
    WATCH_ONLY / ACTIVE_CANDIDATE scopes.
    """
    cutoff = _trade_cutoff_from_data(trades)
    out = []
    for p in picks:
        scope = p.get('pick_scope')
        date_src = (p.get('pick_date') or p.get('conf_date') or p.get('retrace_date') or
                    p.get('entry_date') or p.get('signal_date') or p.get('date'))
        d = _parse_date_key(date_src)
        current_scoped_versions = ('V88', 'V86', 'V85', 'V80', 'V46_1', 'V47_2', 'V48_1', 'V49', 'V50', 'V51', 'V52', 'V53', 'V54', 'V55', 'V56', 'V57', 'V58', 'V59', 'V60', 'V61', 'V62', 'V63', 'V64', 'V65', 'V66', 'V68')
        if ACTIVE_VERSION not in current_scoped_versions and cutoff is not None and (d is None or d < cutoff):
            continue
        if ACTIVE_VERSION in current_scoped_versions and scope == 'HISTORICAL_BACKTEST_TRADE':
            continue
        out.append(p)
    return out

# ── Performance caches ──
_TRADES_CACHE = None
_TRADES_LITE_CACHE = None  # stripped of nested zone/struct_event dicts
_PICKS_CACHE = None
_CACHE_MTIME = 0
_SUMMARY_CACHE = None
_SUMMARY_MTIME = 0

def get_v44_summary_fast():
    """Read lightweight summary from V44 full file without materializing all trades.
    Falls back to cached full trades only if summary is absent.
    """
    global _SUMMARY_CACHE, _SUMMARY_MTIME
    f = ACTIVE_TRADE_FILE
    if f is None or not f.exists():
        return {}
    mt = f.stat().st_mtime
    if _SUMMARY_CACHE is not None and _SUMMARY_MTIME == mt:
        return _SUMMARY_CACHE
    try:
        import re
        txt = f.read_text()
        def grab(name):
            m = re.search(r'"'+name+r'"\s*:\s*([-0-9.]+)', txt)
            return float(m.group(1)) if m else 0
        total = int(grab('total_trades') or grab('n_trades'))
        tradable = int(grab('tradable') or grab('stocks'))
        wr = grab('win_rate') or grab('wr')
        avg = grab('avg_pnl')
        # signal counts require full parse; keep empty for fast health summary. Detailed pages lazy-load.
        _SUMMARY_CACHE = {'total_trades': total, 'win_rate': round(wr,1), 'avg_pnl': round(avg,2), 'stocks': tradable, 'signals': {}}
        _SUMMARY_MTIME = mt
        return _SUMMARY_CACHE
    except Exception:
        return {}

def _active_pick_mtime():
    mt = ACTIVE_PICK_FILE.stat().st_mtime if ACTIVE_PICK_FILE is not None and ACTIVE_PICK_FILE.exists() else 0
    if ACTIVE_VERSION == 'V88' and (V185_DIR / 'v185_active_picks.json').exists():
        mt = max(mt, (V185_DIR / 'v185_active_picks.json').stat().st_mtime)
    if ACTIVE_VERSION == 'V88' and (V175_DIR / 'v175_active_picks.json').exists():
        mt = max(mt, (V175_DIR / 'v175_active_picks.json').stat().st_mtime)
    if ACTIVE_VERSION == 'V88' and (V172_DIR / 'v172_active_picks.json').exists():
        mt = max(mt, (V172_DIR / 'v172_active_picks.json').stat().st_mtime)
    if ACTIVE_VERSION == 'V88' and (V167_DIR / 'v167_active_picks.json').exists():
        mt = max(mt, (V167_DIR / 'v167_active_picks.json').stat().st_mtime)
    if ACTIVE_VERSION == 'V88' and (V103A_DIR / 'v103a_active_picks.json').exists():
        mt = max(mt, (V103A_DIR / 'v103a_active_picks.json').stat().st_mtime)
    if ACTIVE_VERSION == 'V88' and (V90_DIR / 'v90_active_picks.json').exists():
        mt = max(mt, (V90_DIR / 'v90_active_picks.json').stat().st_mtime)
    if ACTIVE_VERSION == 'V88' and (V102_DIR / 'v101_active_picks.json').exists():
        mt = max(mt, (V102_DIR / 'v101_active_picks.json').stat().st_mtime)

    if ACTIVE_VERSION == 'V88' and (V101_DIR / 'v101_active_picks.json').exists():
        mt = max(mt, (V101_DIR / 'v101_active_picks.json').stat().st_mtime)
    if ACTIVE_VERSION == 'V88' and (V100_DIR / 'v100_active_picks.json').exists():
        mt = max(mt, (V100_DIR / 'v100_active_picks.json').stat().st_mtime)
    if ACTIVE_VERSION == 'V88' and (V99_DIR / 'v99_active_picks.json').exists():
        mt = max(mt, (V99_DIR / 'v99_active_picks.json').stat().st_mtime)
    if ACTIVE_VERSION == 'V88' and (V98_DIR / 'v98_active_picks.json').exists():
        mt = max(mt, (V98_DIR / 'v98_active_picks.json').stat().st_mtime)
    if ACTIVE_VERSION == 'V88' and (V97_DIR / 'v97_active_picks.json').exists():
        mt = max(mt, (V97_DIR / 'v97_active_picks.json').stat().st_mtime)
    if ACTIVE_VERSION == 'V88' and (V91_DIR / 'v91_active_picks.json').exists():
        mt = max(mt, (V91_DIR / 'v91_active_picks.json').stat().st_mtime)
    if ACTIVE_VERSION == 'V66' and V66_DAILY_CANDIDATES.exists():
        mt = max(mt, V66_DAILY_CANDIDATES.stat().st_mtime)
    return mt


def _merge_v66_daily_picks(raw_picks):
    if ACTIVE_VERSION != 'V66' or not V66_DAILY_CANDIDATES.exists():
        return raw_picks
    if any(p.get('source') == 'full_market_kline_scan' for p in (raw_picks or [])):
        return raw_picks
    daily = _load_json_list(V66_DAILY_CANDIDATES, [])
    seen = set()
    merged = []
    for p in daily + list(raw_picks or []):
        key = '|'.join(str(x or '') for x in [p.get('symbol'), p.get('pick_date') or p.get('entry_date'), p.get('engine'), p.get('zone_bar') or p.get('zone_idx')])
        if key in seen:
            continue
        seen.add(key)
        merged.append(p)
    return merged


def _v88_latest_market_date():
    dates = []
    for path in (V185_DIR / 'v185_report.json', V175_DIR / 'v175_report.json', V172_DIR / 'v172_report.json', V167_DIR / 'v167_report.json', V103A_DIR / 'v103a_report.json', V102_DIR / 'v101_report.json', V101_DIR / 'v101_report.json', V100_DIR / 'v100_report.json', V99_DIR / 'v99_report.json', V98_DIR / 'v98_report.json', V97_DIR / 'v97_report.json', V91_DIR / 'v91_shadow_scan_report.json', V90_DIR / 'v90_daily_scan_report.json'):
        try:
            if path.exists():
                report = json.loads(path.read_text()) or {}
                dates.append(_date_key(report.get('latest_market_date') or report.get('latest_date')))
        except Exception:
            pass
    return max([d for d in dates if d], default='')


def _latest_v88_scanner_rows(rows):
    """V88 monitor shows the latest full-market scanner output, never old backtest rows."""
    rows = list(rows or [])
    if not rows:
        return []
    if any(str(p.get('engine') or '').startswith('V90_DAILY_SCANNER') for p in rows):
        return rows
    latest_market = _v88_latest_market_date()
    latest_month = latest_market[:6]
    if latest_month:
        current_month = [p for p in rows if latest_month in {
            _date_key(p.get('pick_date') or p.get('select_date'))[:6],
            _date_key(p.get('join_date') or p.get('entry_date'))[:6],
        }]
        if current_month:
            return current_month
    latest = max((_date_key(p.get('pick_date') or p.get('select_date') or p.get('entry_date')) for p in rows), default='')
    if not latest:
        return []
    return [p for p in rows if _date_key(p.get('pick_date') or p.get('select_date') or p.get('entry_date')) == latest]


def _dedupe_v88_scanner_rows(rows):
    seen = set()
    merged = []
    for p in rows or []:
        key = '|'.join(str(x or '') for x in [p.get('symbol'), p.get('pick_date') or p.get('entry_date'), p.get('engine'), p.get('entry_idx')])
        if key in seen:
            continue
        seen.add(key)
        merged.append(p)
    return merged


def _last_cached_daily_price(symbol):
    sym_file = str(symbol or '').replace('.SH','_SH').replace('.SZ','_SZ').replace('.BJ','_BJ')
    for fp in (CACHE / f'{sym_file}_daily_750.json', CACHE / f'{sym_file}_daily_300.json'):
        if fp.exists():
            try:
                arr = json.loads(fp.read_text())
                if arr:
                    b = arr[-1]
                    return {
                        'price': _float_or_zero(b.get('c')),
                        'date': str(b.get('t') or b.get('date') or '')[:8],
                    }
            except Exception:
                pass
    return {'price': 0.0, 'date': ''}


def _apply_current_price_live_guard(rows):
    out = []
    registry_buy_enabled = _production_registry().get('buy_enabled') is True
    for row in rows or []:
        p = dict(row)
        entry = _float_or_zero(p.get('entry_price') or p.get('price'))
        sl = _float_or_zero(p.get('sl') or p.get('sl_price'))
        if not sl and entry:
            sl_pct = _float_or_zero(p.get('risk_pct') or p.get('sl_initial_pct'))
            sl = entry * (1 - sl_pct / 100) if sl_pct else 0
        tp = _float_or_zero(p.get('tp1') or p.get('tp'))
        if not tp and p.get('tp_tiers'):
            try:
                tp = _float_or_zero((p.get('tp_tiers') or [{}])[0].get('price'))
            except Exception:
                tp = 0
        last = _last_cached_daily_price(p.get('symbol'))
        current = last.get('price') or _float_or_zero(p.get('current_price')) or entry
        gap = ((current - entry) / entry * 100) if current and entry else None
        threshold = _float_or_zero(p.get('live_guard_threshold_pct')) or 1.5
        active_candidate = bool(p.get('pick_scope') == 'ACTIVE_CANDIDATE' and p.get('is_active_pick'))
        tradable = active_candidate and registry_buy_enabled
        guard = p.get('live_guard_status') or ''
        reason = p.get('live_guard_reason') or ''
        if active_candidate and not registry_buy_enabled:
            guard = 'WATCH_ONLY_PRODUCTION_REGISTRY_BLOCKED'
            reason = 'PRODUCTION_REGISTRY_BUY_DISABLED'
        if tradable and current and entry:
            if sl and current <= sl:
                tradable = False
                guard = 'WATCH_ONLY_SL_ALREADY_HIT'
                reason = 'CURRENT_LAST_PRICE_BELOW_OR_EQUAL_SL'
            elif tp and current >= tp:
                tradable = False
                guard = 'WATCH_ONLY_TP_ALREADY_HIT'
                reason = 'CURRENT_LAST_PRICE_ABOVE_OR_EQUAL_TP'
            elif gap is not None and abs(gap) > threshold:
                tradable = False
                guard = 'WATCH_ONLY_PRICE_NOT_NEAR_ENTRY'
                reason = 'CURRENT_LAST_PRICE_NOT_WITHIN_ENTRY_GAP'
            else:
                guard = 'BUY_VALID'
                reason = 'CURRENT_LAST_PRICE_WITHIN_ENTRY_GAP_AND_NOT_TP_SL'
        p['current_price'] = round(current, 4) if current else 0
        p['last_price'] = round(current, 4) if current else 0
        p['last_price_date'] = last.get('date') or ''
        p['current_entry_gap_pct'] = round(gap, 2) if gap is not None else None
        p['live_guard_status'] = guard
        p['live_guard_reason'] = reason
        p['tradable'] = tradable
        p['buy_enabled'] = tradable
        p['trade_action'] = 'BUY' if tradable else 'WATCH_ONLY'
        p['tradeAction'] = p['trade_action']
        p['isTradableLive'] = tradable
        p['status'] = 'ACTIVE_BUY_VALID' if tradable else 'WATCH_ONLY_CONTEXT'
        p['monitor_status'] = p.get('monitor_status') or p['status']
        out.append(p)
    return out


def _merge_v90_daily_picks(raw_picks):
    if ACTIVE_VERSION != 'V88':
        return raw_picks
    if _production_empty_book():
        return []
    v185_path = V185_DIR / 'v185_active_picks.json'
    if v185_path.exists():
        # V185 combines V175 baseline with a non-overlapping true-takeover runner child.
        return _dedupe_v88_scanner_rows(_load_json_list(v185_path, []))
    v175_path = V175_DIR / 'v175_active_picks.json'
    if v175_path.exists():
        # V175 keeps V172 economics and fixes the semantic contract labels.
        return _dedupe_v88_scanner_rows(_load_json_list(v175_path, []))
    v172_path = V172_DIR / 'v172_active_picks.json'
    if v172_path.exists():
        # V172 is the high-quality V167 overlay; artifacts are current scanner
        # candidates with live guard applied, not historical completed trades.
        return _dedupe_v88_scanner_rows(_load_json_list(v172_path, []))
    v167_path = V167_DIR / 'v167_active_picks.json'
    if v167_path.exists():
        # V167 artifacts are already the exact recent45 scanner BUY set; do not
        # re-slice by latest V90 market month or silently drop valid recent rows.
        return _dedupe_v88_scanner_rows(_load_json_list(v167_path, []))
    daily_path = V90_DIR / 'v90_active_picks.json'
    if not daily_path.exists():
        return []
    daily = _load_json_list(daily_path, [])
    return _dedupe_v88_scanner_rows(_latest_v88_scanner_rows(daily))


def _merge_v91_shadow_picks(raw_picks):
    if ACTIVE_VERSION != 'V88':
        return raw_picks
    if (V185_DIR / 'v185_active_picks.json').exists():
        return raw_picks
    if (V175_DIR / 'v175_active_picks.json').exists():
        return raw_picks
    if (V172_DIR / 'v172_active_picks.json').exists():
        return raw_picks
    if (V167_DIR / 'v167_active_picks.json').exists():
        return raw_picks
    # V91 is a shadow scanner. Production/live pages must stay sourced from the
    # latest V90 full-market daily scan, not shadow or historical structural rows.
    return _dedupe_v88_scanner_rows(_latest_v88_scanner_rows(raw_picks))


def _v100_production_rows(rows):
    """Frontend production contract: promoted audit files may contain all tiers;
    production pages must only evaluate whitelisted production rows.
    """
    if not isinstance(rows, list):
        return []
    prod = [r for r in rows if r.get('production_eligible_v185') is True or r.get('production_eligible_v175') is True or r.get('production_eligible_v172') is True or r.get('production_eligible_v167') is True or r.get('production_eligible_v102') is True or r.get('production_eligible_v101') is True or r.get('v100_tier') == 'A_PRODUCTION_CORE' or r.get('production_grade') == 'A_PRODUCTION']
    return prod


def _promoted_trade_file():
    # V152 is diagnostic-only after V153 pollution audit; do not route trades.
    if ACTIVE_VERSION == 'V88' and (V185_DIR / 'v185_trades.json').exists():
        return V185_DIR / 'v185_trades.json'
    if ACTIVE_VERSION == 'V88' and (V175_DIR / 'v175_trades.json').exists():
        return V175_DIR / 'v175_trades.json'
    if ACTIVE_VERSION == 'V88' and (V172_DIR / 'v172_trades.json').exists():
        return V172_DIR / 'v172_trades.json'
    if ACTIVE_VERSION == 'V88' and (V167_DIR / 'v167_trades.json').exists():
        return V167_DIR / 'v167_trades.json'
    if ACTIVE_VERSION == 'V88' and (V102_DIR / 'v101_trades.json').exists():
        return V102_DIR / 'v101_trades.json'
    if ACTIVE_VERSION == 'V88' and (V101_DIR / 'v101_trades.json').exists():
        return V101_DIR / 'v101_trades.json'
    if ACTIVE_VERSION == 'V88' and (V100_DIR / 'v100_trades.json').exists():
        return V100_DIR / 'v100_trades.json'
    if ACTIVE_VERSION == 'V88' and (V99_DIR / 'v99_trades.json').exists():
        return V99_DIR / 'v99_trades.json'
    return ACTIVE_TRADE_FILE


def _cache_valid():
    global _CACHE_MTIME
    f = _promoted_trade_file()
    if f is None or not f.exists():
        return False
    mt = max(f.stat().st_mtime, _active_pick_mtime())
    return mt == _CACHE_MTIME

def _refresh_cache():
    global _TRADES_CACHE, _TRADES_LITE_CACHE, _PICKS_CACHE, _CACHE_MTIME
    f = _promoted_trade_file()
    if f is not None and f.exists():
        raw = json.loads(f.read_text())
        if ACTIVE_VERSION == 'V44' and isinstance(raw, dict):
            raw = raw.get('all_trades', [])
        if ACTIVE_VERSION == 'V88' and f in (V185_DIR / 'v185_trades.json', V175_DIR / 'v175_trades.json', V172_DIR / 'v172_trades.json', V167_DIR / 'v167_trades.json', V102_DIR / 'v101_trades.json', V101_DIR / 'v101_trades.json', V100_DIR / 'v100_trades.json'):
            raw = _v100_production_rows(raw)
        raw = normalize_v27_trades(raw)
        _TRADES_CACHE = raw
        _CACHE_MTIME = max(f.stat().st_mtime, _active_pick_mtime())
        # Build lightweight copy: strip nested/large fields. V44 is already flat but huge;
        # keep only fields used by K-line overlays and frontend tables to avoid OOM.
        _TRADES_LITE_CACHE = []
        lite_keys = {'symbol','entry_date','exit_date','signal_date','entry_price','exit_price','pnl_pct','won','rr','hold_bars','sl','sl_pct','signal_type','zone_type','direction','entry_mode','conf_type','exit_method','exit_reason','market_state','phase','ctx_seq','seq','detail','entry_idx','sig_idx','confirmed_at','exit_idx','source_event','select_date','pick_date','join_date','cost_line','smart_money_cost','volatility_pct','semantic_layer','strict_audit_status','signal_correctness_claim','semantic_issues','semantic_hard_issue_count','entry_zone_position'}
        for t in raw:
            if ACTIVE_VERSION == 'V44':
                lt = {k: t.get(k) for k in lite_keys if k in t}
            else:
                lt = {k: v for k, v in t.items() if k not in ('zone', 'struct_event')}
            # Inline key zone fields for frontend compatibility
            z = t.get('zone', {})
            if z:
                lt['zone_type'] = lt.get('zone_type') or z.get('type', '')
                lt['zone_low'] = lt.get('zone_low') or z.get('zone_low', 0)
                lt['zone_high'] = lt.get('zone_high') or z.get('zone_high', 0)
            se = t.get('struct_event', {})
            if se:
                lt['source_event'] = lt.get('source_event') or se.get('type', '')
            _TRADES_LITE_CACHE.append(lt)
    else:
        _TRADES_CACHE = []
        _TRADES_LITE_CACHE = []
    p = ACTIVE_PICK_FILE
    raw_picks = json.loads(p.read_text()) if p is not None and p.exists() else []
    raw_picks = _merge_v66_daily_picks(raw_picks)
    raw_picks = _merge_v90_daily_picks(raw_picks)
    raw_picks = _merge_v91_shadow_picks(raw_picks)
    if ACTIVE_VERSION == 'V44' and not p.exists():
        raw_picks = []
    _PICKS_CACHE = normalize_v27_picks(raw_picks, _TRADES_CACHE or [])

def get_trades_cached(lite=True):
    if not _cache_valid():
        _refresh_cache()
    return _TRADES_LITE_CACHE if lite else _TRADES_CACHE

def _get_version_trades_uncached(version=None, lite=True):
    """Return trades for a requested frontend version without changing ACTIVE_VERSION."""
    version = version or ACTIVE_VERSION
    if version == ACTIVE_VERSION:
        return get_trades_cached(lite=lite)
    if version == 'V185':
        raw = _v100_production_rows(_load_json_list(V185_DIR/'v185_trades.json', []))
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V88' and (V102_DIR / 'v101_trades.json').exists():
        raw = _v100_production_rows(_load_json_list(V102_DIR/'v101_trades.json', []))
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V88' and (V101_DIR / 'v101_trades.json').exists():
        raw = _v100_production_rows(_load_json_list(V101_DIR/'v101_trades.json', []))
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V88' and (V100_DIR / 'v100_trades.json').exists():
        raw = _v100_production_rows(_load_json_list(V100_DIR/'v100_trades.json', []))
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V88' and (V99_DIR / 'v99_trades.json').exists():
        raw = _load_json_list(V99_DIR/'v99_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V88':
        raw = _load_json_list(V88_DIR/'v88_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V86':
        raw = _load_json_list(V86_DIR/'v86_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V85':
        raw = _load_json_list(V85_DIR/'v85_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V80':
        raw = _load_json_list(V80_DIR/'v80_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V68':
        raw = _load_json_list(V68_DIR/'v68_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V66':
        raw = _load_json_list(V66_DIR/'v66_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V72':
        raw = _load_json_list(V72_DIR/'v72_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V65':
        raw = _load_json_list(V65_DIR/'v65_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V64':
        raw = _load_json_list(V64_DIR/'v64_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V63':
        raw = _load_json_list(V63_DIR/'v63_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V62':
        raw = _load_json_list(V62_DIR/'v62_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V61':
        raw = _load_json_list(V61_DIR/'v61_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V60':
        raw = _load_json_list(V60_DIR/'v60_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V59':
        raw = _load_json_list(V59_DIR/'v59_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V58':
        raw = _load_json_list(V58_DIR/'v58_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V57':
        raw = _load_json_list(V57_DIR/'v57_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V56':
        raw = _load_json_list(V56_DIR/'v56_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V55':
        raw = _load_json_list(V55_DIR/'v55_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V54':
        raw = _load_json_list(V54_DIR/'v54_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V53':
        raw = _load_json_list(V53_DIR/'v53_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V52':
        raw = _load_json_list(V52_DIR/'v52_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V51':
        raw = _load_json_list(V51_DIR/'v51_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V50':
        raw = _load_json_list(V50_DIR/'v50_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V49':
        raw = _load_json_list(V49_DIR/'v49_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V48_1':
        raw = _load_json_list(V48_1_DIR/'v48_1_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    if version == 'V47_2':
        raw = _load_json_list(V47_2_DIR/'v47_2_trades.json', [])
        if lite:
            return [{k: v for k, v in t.items() if k not in ('zone', 'struct_event')} for t in raw]
        return raw
    return get_trades_cached(lite=lite)

_VERSION_TRADES_CACHE = {}

def get_version_trades(version=None, lite=True):
    """Cached wrapper — v101_trades.json is huge; was 5.9s per kline request (FIX 2026-08-20)."""
    version = version or ACTIVE_VERSION
    _k = (version, lite)
    if _k in _VERSION_TRADES_CACHE:
        return _VERSION_TRADES_CACHE[_k]
    _r = _get_version_trades_uncached(version, lite)
    if len(_VERSION_TRADES_CACHE) < 40:
        _VERSION_TRADES_CACHE[_k] = _r
    return _r

def get_version_picks(version=None):
    version = version or ACTIVE_VERSION
    if version == ACTIVE_VERSION:
        return get_picks_cached()
    if version == 'V185':
        return normalize_v27_picks(_load_json_list(V185_DIR/'v185_active_picks.json', []), get_version_trades('V185', lite=False))
    if version == 'V88':
        raw = _merge_v90_daily_picks(_load_json_list(V88_DIR/'v88_picks.json', []))
        raw = _merge_v91_shadow_picks(raw)
        return normalize_v27_picks(raw, get_version_trades('V88', lite=False))
    if version == 'V86':
        return normalize_v27_picks(_load_json_list(V86_DIR/'v86_picks.json', []), get_version_trades('V86', lite=False))
    if version == 'V85':
        return normalize_v27_picks(_load_json_list(V85_DIR/'v85_picks.json', []), get_version_trades('V85', lite=False))
    if version == 'V80':
        return normalize_v27_picks(_load_json_list(V80_DIR/'v80_picks.json', []), get_version_trades('V80', lite=False))
    if version == 'V68':
        return normalize_v27_picks(_load_json_list(V68_DIR/'v68_picks.json', []), get_version_trades('V68', lite=False))
    if version == 'V66':
        raw = _load_json_list(V66_DIR/'v66_picks.json', [])
        return normalize_v27_picks(_merge_v66_daily_picks(raw), get_version_trades('V66', lite=False))
    if version == 'V72':
        return normalize_v27_picks(_load_json_list(V72_DIR/'v72_picks.json', []), get_version_trades('V72', lite=False))
    if version == 'V65':
        return normalize_v27_picks(_load_json_list(V65_DIR/'v65_picks.json', []), get_version_trades('V65', lite=False))
    if version == 'V64':
        return normalize_v27_picks(_load_json_list(V64_DIR/'v64_picks.json', []), get_version_trades('V64', lite=False))
    if version == 'V63':
        return normalize_v27_picks(_load_json_list(V63_DIR/'v63_picks.json', []), get_version_trades('V63', lite=False))
    if version == 'V62':
        return normalize_v27_picks(_load_json_list(V62_DIR/'v62_picks.json', []), get_version_trades('V62', lite=False))
    if version == 'V61':
        return normalize_v27_picks(_load_json_list(V61_DIR/'v61_picks.json', []), get_version_trades('V61', lite=False))
    if version == 'V60':
        return normalize_v27_picks(_load_json_list(V60_DIR/'v60_picks.json', []), get_version_trades('V60', lite=False))
    if version == 'V59':
        return normalize_v27_picks(_load_json_list(V59_DIR/'v59_picks.json', []), get_version_trades('V59', lite=False))
    if version == 'V58':
        return normalize_v27_picks(_load_json_list(V58_DIR/'v58_picks.json', []), get_version_trades('V58', lite=False))
    if version == 'V57':
        return normalize_v27_picks(_load_json_list(V57_DIR/'v57_picks.json', []), get_version_trades('V57', lite=False))
    if version == 'V56':
        return normalize_v27_picks(_load_json_list(V56_DIR/'v56_picks.json', []), get_version_trades('V56', lite=False))
    if version == 'V55':
        return normalize_v27_picks(_load_json_list(V55_DIR/'v55_picks.json', []), get_version_trades('V55', lite=False))
    if version == 'V54':
        return normalize_v27_picks(_load_json_list(V54_DIR/'v54_picks.json', []), get_version_trades('V54', lite=False))
    if version == 'V53':
        return normalize_v27_picks(_load_json_list(V53_DIR/'v53_picks.json', []), get_version_trades('V53', lite=False))
    if version == 'V52':
        return normalize_v27_picks(_load_json_list(V52_DIR/'v52_picks.json', []), get_version_trades('V52', lite=False))
    if version == 'V51':
        return normalize_v27_picks(_load_json_list(V51_DIR/'v51_picks.json', []), get_version_trades('V51', lite=False))
    if version == 'V50':
        return normalize_v27_picks(_load_json_list(V50_DIR/'v50_picks.json', []), get_version_trades('V50', lite=False))
    if version == 'V49':
        return normalize_v27_picks(_load_json_list(V49_DIR/'v49_picks.json', []), get_version_trades('V49', lite=False))
    if version == 'V48_1':
        return normalize_v27_picks(_load_json_list(V48_1_DIR/'v48_1_picks.json', []), get_version_trades('V48_1', lite=False))
    if version == 'V47_2':
        return normalize_v27_picks(_load_json_list(V47_2_DIR/'v47_2_picks.json', []), get_version_trades('V47_2', lite=False))
    return get_picks_cached()

def get_picks_cached():
    if not _cache_valid():
        _refresh_cache()
    return _PICKS_CACHE

V18_IMPROV = load_json(Path('/root/.hermes/smc_opt_v18/v18_improvements.json'), {})  # static reference
# V27 recent signals cache (294MB, lazy-loaded on first K-line request)
_V27_RECENT_CACHE = None

def _invalidate_cache():
    """Force all frontend data readers to reload active trade/pick/summary files."""
    global _CACHE_MTIME, _TRADES_CACHE, _TRADES_LITE_CACHE, _PICKS_CACHE, _SUMMARY_CACHE, _SUMMARY_MTIME
    _TRADES_CACHE = None
    _TRADES_LITE_CACHE = None
    _PICKS_CACHE = None
    _CACHE_MTIME = 0
    _SUMMARY_CACHE = None
    _SUMMARY_MTIME = 0


def _active_version_paths(version=None):
    """Return canonical engine/output paths for the active frontend version."""
    version = version or ACTIVE_VERSION
    if version == 'V185':
        return {
            'script': None,
            'out_dir': V185_DIR,
            'prefix': 'v185',
            'engine_name': 'V185_COMBINED_V175_PLUS_TRUE_TAKEOVER_CHILD',
            'trades': V185_DIR/'v185_trades.json',
            'picks': V185_DIR/'v185_picks.json',
            'watchlist': V185_DIR/'v185_active_picks.json',
            'metrics': V185_DIR/'v185_report.json',
            'history_dir': V185_DIR/'history',
        }
    if version == 'V88':
        return {
            'script': Path('/root/.hermes/scripts/v25/v88_apply_production_contract.py'),
            'out_dir': V88_DIR,
            'prefix': 'v88',
            'engine_name': 'V88_PRODUCTION_CONTRACT',
            'trades': V88_DIR/'v88_trades.json',
            'picks': V88_DIR/'v88_picks.json',
            'watchlist': V88_DIR/'v88_picks.json',
            'metrics': V88_DIR/'v88_production_report.json',
            'history_dir': V88_DIR/'history',
        }
    if version == 'V68':
        return {
            'script': Path('/root/.hermes/scripts/v25/v68_limit_candidate.py'),
            'out_dir': V68_DIR,
            'prefix': 'v68',
            'engine_name': 'V68_STRICT_LD_FVG_LIMIT_STRUCTURE',
            'trades': V68_DIR/'v68_trades.json',
            'picks': V68_DIR/'v68_picks.json',
            'watchlist': V68_DIR/'v68_picks.json',
            'metrics': V68_DIR/'v68_report.json',
            'history_dir': V68_DIR/'history',
        }
    if version == 'V66':
        return {
            'script': Path('/root/.hermes/scripts/v25/v66_engine.py'),
            'out_dir': V66_DIR,
            'prefix': 'v66',
            'engine_name': 'V66_RECENT_REENTRY_RISK_OVERLAY',
            'trades': V66_DIR/'v66_trades.json',
            'picks': V66_DIR/'v66_picks.json',
            'watchlist': V66_DIR/'v66_picks.json',
            'metrics': V66_DIR/'v66_report.json',
            'history_dir': V66_DIR/'history',
        }
    if version == 'V65':
        return {
            'script': Path('/root/.hermes/scripts/v25/v65_engine.py'),
            'out_dir': V65_DIR,
            'prefix': 'v65',
            'engine_name': 'V65_LOSS_REVIEW_GATE',
            'trades': V65_DIR/'v65_trades.json',
            'picks': V65_DIR/'v65_picks.json',
            'watchlist': V65_DIR/'v65_picks.json',
            'metrics': V65_DIR/'v65_report.json',
            'history_dir': V65_DIR/'history',
        }
    if version == 'V64':
        return {
            'script': Path('/root/.hermes/scripts/v25/v64_engine.py'),
            'out_dir': V64_DIR,
            'prefix': 'v64',
            'engine_name': 'V64_CONTINUATION_SPECIALIST_GATE',
            'trades': V64_DIR/'v64_trades.json',
            'picks': V64_DIR/'v64_picks.json',
            'watchlist': V64_DIR/'v64_picks.json',
            'metrics': V64_DIR/'v64_report.json',
            'history_dir': V64_DIR/'history',
        }
    if version == 'V63':
        return {
            'script': Path('/root/.hermes/scripts/v25/v63_engine.py'),
            'out_dir': V63_DIR,
            'prefix': 'v63',
            'engine_name': 'V63_REENTRY_SPECIALIST_GATE',
            'trades': V63_DIR/'v63_trades.json',
            'picks': V63_DIR/'v63_picks.json',
            'watchlist': V63_DIR/'v63_picks.json',
            'metrics': V63_DIR/'v63_report.json',
            'history_dir': V63_DIR/'history',
        }
    if version == 'V62':
        return {
            'script': Path('/root/.hermes/scripts/v25/v62_engine.py'),
            'out_dir': V62_DIR,
            'prefix': 'v62',
            'engine_name': 'V62_FALSE_BREAK_RETEST_GATE',
            'trades': V62_DIR/'v62_trades.json',
            'picks': V62_DIR/'v62_picks.json',
            'watchlist': V62_DIR/'v62_picks.json',
            'metrics': V62_DIR/'v62_report.json',
            'history_dir': V62_DIR/'history',
        }
    if version == 'V61':
        return {
            'script': Path('/root/.hermes/scripts/v25/v61_engine.py'),
            'out_dir': V61_DIR,
            'prefix': 'v61',
            'engine_name': 'V61_EXIT_LAYER_REPAIR',
            'trades': V61_DIR/'v61_trades.json',
            'picks': V61_DIR/'v61_picks.json',
            'watchlist': V61_DIR/'v61_picks.json',
            'metrics': V61_DIR/'v61_report.json',
            'history_dir': V61_DIR/'history',
        }
    if version == 'V60':
        return {
            'script': Path('/root/.hermes/scripts/v25/v60_engine.py'),
            'out_dir': V60_DIR,
            'prefix': 'v60',
            'engine_name': 'V60_FAMILY_QUALITY_GATES',
            'trades': V60_DIR/'v60_trades.json',
            'picks': V60_DIR/'v60_picks.json',
            'watchlist': V60_DIR/'v60_picks.json',
            'metrics': V60_DIR/'v60_report.json',
            'history_dir': V60_DIR/'history',
        }
    if version == 'V59':
        return {
            'script': Path('/root/.hermes/scripts/v25/v59_engine.py'),
            'out_dir': V59_DIR,
            'prefix': 'v59',
            'engine_name': 'V59_FULL_MARKET_GENERATOR',
            'trades': V59_DIR/'v59_trades.json',
            'picks': V59_DIR/'v59_picks.json',
            'watchlist': V59_DIR/'v59_picks.json',
            'metrics': V59_DIR/'v59_report.json',
            'history_dir': V59_DIR/'history',
        }
    if version == 'V58':
        return {
            'script': Path('/root/.hermes/scripts/v25/v58_engine.py'),
            'out_dir': V58_DIR,
            'prefix': 'v58',
            'engine_name': 'V58_CONTINUATION_SETUP',
            'trades': V58_DIR/'v58_trades.json',
            'picks': V58_DIR/'v58_picks.json',
            'watchlist': V58_DIR/'v58_picks.json',
            'metrics': V58_DIR/'v58_report.json',
            'history_dir': V58_DIR/'history',
        }
    if version == 'V57':
        return {
            'script': Path('/root/.hermes/scripts/v25/v57_engine.py'),
            'out_dir': V57_DIR,
            'prefix': 'v57',
            'engine_name': 'V57_SELECTIVE_GRADED_STRUCTURE_EXIT',
            'trades': V57_DIR/'v57_trades.json',
            'picks': V57_DIR/'v57_picks.json',
            'watchlist': V57_DIR/'v57_picks.json',
            'metrics': V57_DIR/'v57_report.json',
            'history_dir': V57_DIR/'history',
        }
    if version == 'V56':
        return {
            'script': Path('/root/.hermes/scripts/v25/v56_engine.py'),
            'out_dir': V56_DIR,
            'prefix': 'v56',
            'engine_name': 'V56_BREAKOUT_QUALITY_TIERS',
            'trades': V56_DIR/'v56_trades.json',
            'picks': V56_DIR/'v56_picks.json',
            'watchlist': V56_DIR/'v56_picks.json',
            'metrics': V56_DIR/'v56_report.json',
            'history_dir': V56_DIR/'history',
        }
    if version == 'V55':
        return {
            'script': Path('/root/.hermes/scripts/v25/v55_engine.py'),
            'out_dir': V55_DIR,
            'prefix': 'v55',
            'engine_name': 'V55_PRETRADE_GATE_ADAPTIVE_TP',
            'trades': V55_DIR/'v55_trades.json',
            'picks': V55_DIR/'v55_picks.json',
            'watchlist': V55_DIR/'v55_picks.json',
            'metrics': V55_DIR/'v55_report.json',
            'history_dir': V55_DIR/'history',
        }
    if version == 'V54':
        return {
            'script': Path('/root/.hermes/scripts/v25/v54_engine.py'),
            'out_dir': V54_DIR,
            'prefix': 'v54',
            'engine_name': 'V54_REENTRY_AWARE',
            'trades': V54_DIR/'v54_trades.json',
            'picks': V54_DIR/'v54_picks.json',
            'watchlist': V54_DIR/'v54_picks.json',
            'metrics': V54_DIR/'v54_report.json',
            'history_dir': V54_DIR/'history',
        }
    if version == 'V53':
        return {
            'script': Path('/root/.hermes/scripts/v25/v53_engine.py'),
            'out_dir': V53_DIR,
            'prefix': 'v53',
            'engine_name': 'V53_SIGNAL_SNAPSHOT_TREND_LAYERED_RUNNER',
            'trades': V53_DIR/'v53_trades.json',
            'picks': V53_DIR/'v53_picks.json',
            'watchlist': V53_DIR/'v53_picks.json',
            'metrics': V53_DIR/'v53_report.json',
            'history_dir': V53_DIR/'history',
        }
    if version == 'V52':
        return {
            'script': Path('/root/.hermes/scripts/v25/v52_engine.py'),
            'out_dir': V52_DIR,
            'prefix': 'v52',
            'engine_name': 'V52_SIGNAL_SNAPSHOT_4R_CONFIRM_RECLAIM_EXIT',
            'trades': V52_DIR/'v52_trades.json',
            'picks': V52_DIR/'v52_picks.json',
            'watchlist': V52_DIR/'v52_picks.json',
            'metrics': V52_DIR/'v52_report.json',
            'history_dir': V52_DIR/'history',
        }
    if version == 'V51':
        return {
            'script': Path('/root/.hermes/scripts/v25/v51_engine.py'),
            'out_dir': V51_DIR,
            'prefix': 'v51',
            'engine_name': 'V51_SIGNAL_SNAPSHOT_4R_STRUCT_EXIT',
            'trades': V51_DIR/'v51_trades.json',
            'picks': V51_DIR/'v51_picks.json',
            'watchlist': V51_DIR/'v51_picks.json',
            'metrics': V51_DIR/'v51_report.json',
            'history_dir': V51_DIR/'history',
        }
    if version == 'V50':
        return {
            'script': Path('/root/.hermes/scripts/v25/v50_engine.py'),
            'out_dir': V50_DIR,
            'prefix': 'v50',
            'engine_name': 'V50_SIGNAL_SNAPSHOT_STRUCT_EXIT',
            'trades': V50_DIR/'v50_trades.json',
            'picks': V50_DIR/'v50_picks.json',
            'watchlist': V50_DIR/'v50_picks.json',
            'metrics': V50_DIR/'v50_report.json',
            'history_dir': V50_DIR/'history',
        }
    if version == 'V49':
        return {
            'script': Path('/root/.hermes/scripts/v25/v49_exit_optimized.py'),
            'out_dir': V49_DIR,
            'prefix': 'v49',
            'engine_name': 'V49_EXIT_OPTIMIZED_PRODUCTION',
            'trades': V49_DIR/'v49_trades.json',
            'picks': V49_DIR/'v49_picks.json',
            'watchlist': V49_DIR/'v49_picks.json',
            'metrics': V49_DIR/'v49_report.json',
            'history_dir': V49_DIR/'history',
        }
    if version == 'V48_1':
        return {
            'script': Path('/root/.hermes/scripts/v25/v48_1_production.py'),
            'out_dir': V48_1_DIR,
            'prefix': 'v48_1',
            'engine_name': 'V48_1_PRODUCTION',
            'trades': V48_1_DIR/'v48_1_trades.json',
            'picks': V48_1_DIR/'v48_1_picks.json',
            'watchlist': V48_1_DIR/'v48_1_picks.json',
            'metrics': V48_1_DIR/'v48_1_report.json',
            'history_dir': V48_1_DIR/'history',
        }
    if version == 'V47_2':
        return {
            'script': Path('/root/.hermes/scripts/v25/v47_2_high_quality.py'),
            'out_dir': V47_2_DIR,
            'prefix': 'v47_2',
            'engine_name': 'V47_2_HIGH_QUALITY_CANDIDATE',
            'trades': V47_2_DIR/'v47_2_trades.json',
            'picks': V47_2_DIR/'v47_2_picks.json',
            'watchlist': V47_2_DIR/'v47_2_picks.json',
            'metrics': V47_2_DIR/'v47_2_report.json',
            'history_dir': V47_2_DIR/'history',
        }
    if version == 'V46_1':
        return {
            'script': Path('/root/.hermes/scripts/v25/v46_1_layered_3y.py'),
            'out_dir': Path('/root/.hermes/smc_opt_v46_1_layered_3y'),
            'prefix': 'v46_1',
            'engine_name': 'V46_1_LAYERED_SMC2026_3Y',
            'trades': Path('/root/.hermes/smc_opt_v46_1_layered_3y/v46_1_trades.json'),
            'picks': Path('/root/.hermes/smc_opt_v46_1_layered_3y/v46_1_picks.json'),
            'watchlist': Path('/root/.hermes/smc_opt_v46_1_layered_3y/v46_1_watchlist.json'),
            'metrics': Path('/root/.hermes/smc_opt_v46_1_layered_3y/v46_1_validation_summary.json'),
            'history_dir': Path('/root/.hermes/smc_opt_v46_1_layered_3y/history'),
        }
    return None

def get_v27_recent():
    global _V27_RECENT_CACHE
    if _V27_RECENT_CACHE is None:
        _V27_RECENT_CACHE = load_json(Path('/root/.hermes/smc_opt_v27/v27_recent_signals.json'), {})
    return _V27_RECENT_CACHE
# Default to V23
def _vdata(path, default=None):
    return load_json(Path(path), default or [])

def reload_trades():
    """Fast — uses memory cache"""
    return get_trades_cached(lite=False)

def reload_picks():
    """Fast — uses memory cache"""
    return get_picks_cached()



def _max_trade_date(trades, field='entry_date'):
    vals = [_date_key(t.get(field) or t.get('entry_date')) for t in trades]
    vals = [v for v in vals if len(v) == 8 and v.isdigit()]
    return max(vals) if vals else ''

def _normalize_pick_scope(p, latest_trade_date=''):
    """Normalize pick contract. V44 legacy ACTIVE means historical-best, not current active."""
    p = dict(p)
    if ACTIVE_VERSION == 'V44' or str(p.get('engine','')).startswith('V44'):
        p['pick_scope'] = 'HISTORICAL_BEST'
        p['is_active_pick'] = False
        p['setup_status'] = 'HISTORICAL_BACKTEST_TRADE'
        p['active_reason'] = ''
        p['invalid_reason'] = 'V44 legacy picks are per-symbol historical best/backtest representatives, not live active candidates'
        p['state'] = 'HISTORICAL_BEST'
    else:
        scope = p.get('pick_scope')
        if ACTIVE_VERSION in ('V88', 'V185', 'V86', 'V85', 'V46_1', 'V47_2', 'V48_1', 'V49', 'V50', 'V51', 'V52', 'V53', 'V54', 'V55', 'V56', 'V57', 'V58', 'V59', 'V60', 'V61', 'V62', 'V63', 'V64', 'V65', 'V66', 'V68', 'V72'):
            scope = 'ACTIVE_CANDIDATE' if scope == 'ACTIVE_ENTRY' else scope
            scope = 'WATCH_ONLY' if scope in ('NEAR_ZONE_WATCH', 'POST_ENTRY_MONITOR', 'HIGH_RISK_WATCH_ONLY') else scope
            scope = 'REJECTED_CANDIDATE' if scope == 'REJECTED_CANDIDATE' else scope
            p['pick_scope'] = scope or ('ACTIVE_CANDIDATE' if bool(p.get('is_active_pick')) else 'WATCH_ONLY')
            p['is_active_pick'] = bool(p.get('is_active_pick')) and p['pick_scope'] == 'ACTIVE_CANDIDATE'
            p['state'] = p['pick_scope']
        elif not scope:
            is_active = bool(p.get('is_active_pick')) or p.get('state') == 'ACTIVE'
            p['pick_scope'] = 'ACTIVE_CANDIDATE' if is_active else 'HISTORICAL_BEST'
            p['is_active_pick'] = p.get('pick_scope') == 'ACTIVE_CANDIDATE'
        else:
            p['is_active_pick'] = p.get('pick_scope') == 'ACTIVE_CANDIDATE'
    p = _apply_smc_field_contract(p)
    if p.get('zone_idx') is None and p.get('zone_bar') is not None:
        p['zone_idx'] = p.get('zone_bar')
    if p.get('conf_index') is None:
        p['conf_index'] = p.get('confirm_idx') if p.get('confirm_idx') is not None else p.get('entry_idx')
    if not p.get('conf_date'):
        p['conf_date'] = p.get('confirm_date') or p.get('entry_date') or p.get('pick_date')
    if p.get('pick_scope') == 'WATCH_ONLY' and not p.get('watch_reason'):
        p['watch_reason'] = p.get('reject_reason') or p.get('invalid_reason') or 'OBSERVE_ONLY_NOT_TRADABLE'
    # Frontend compatibility fields. V46.1 watchlist is structurally correct but
    # uses engine-native names; normalize once here so monitor/live/API columns do
    # not show blank quality/TP/sequence/zone/price fields.
    ep = float(p.get('entry_price') or p.get('price') or 0)
    p['price'] = float(p.get('price') or ep or 0)
    p['current_price'] = float(p.get('current_price') or p.get('last_close') or p.get('price') or 0)
    p['last_close'] = float(p.get('last_close') or p.get('current_price') or p.get('price') or 0)
    p['score'] = float(p.get('score') if p.get('score') not in (None,'') else p.get('quality_score') or 0)
    q = float(p.get('quality_score') or p.get('score') or 0)
    if not p.get('entry_quality'):
        p['entry_quality'] = 'ELITE' if q >= 7.0 else ('HIGH' if q >= 6.2 else ('STANDARD' if q > 0 else ''))
    if not p.get('seq'):
        p['seq'] = f"{p.get('sequence_kind','')}->{p.get('source_event','')}->{p.get('zone_type','')}->{p.get('conf_type','')}"
    if not p.get('ctx_seq'):
        p['ctx_seq'] = p.get('seq','').replace('->','→')
    if not p.get('detail'):
        p['detail'] = p.get('ctx_seq') or p.get('seq')
    if p.get('tp1') and not p.get('tp_tiers') and ep:
        tiers = []
        for i, key in enumerate(('tp1','tp2','tp3'), 1):
            val = float(p.get(key) or 0)
            if val > 0:
                tiers.append({'price': round(val,4), 'pct': round((val-ep)/ep*100, 2), 'type': f'TP{i}'})
        p['tp_tiers'] = tiers
    p['regime'] = p.get('regime') or p.get('market_state') or p.get('setup_status') or p.get('watch_status') or ''
    if p.get('retrace_pct') in (None, ''):
        zl = float(p.get('zone_low') or 0)
        p['retrace_pct'] = round((ep-zl)/zl*100, 2) if ep and zl else 0
    return p

def get_all_picks_scoped(version=None):
    version = version or ACTIVE_VERSION
    trades = get_version_trades(version, lite=False) if version != ACTIVE_VERSION else reload_trades()
    latest = _max_trade_date(trades)
    picks = get_version_picks(version) if version != ACTIVE_VERSION else reload_picks()
    return [_normalize_pick_scope(p, latest) for p in (picks or [])]

def get_active_picks(include_reject=False, version=None):
    version = version or ACTIVE_VERSION
    if version in ('V88', 'V185', 'V86', 'V85', 'V50', 'V51', 'V52', 'V53', 'V54', 'V55', 'V56', 'V57', 'V58', 'V59', 'V60', 'V61', 'V62', 'V63', 'V64', 'V65', 'V66', 'V68'):
        return [p for p in get_all_picks_scoped(version) if p.get('pick_scope') in ('ACTIVE_CANDIDATE', 'WATCH_ONLY')]
    picks = [p for p in get_all_picks_scoped(version) if p.get('pick_scope') == 'ACTIVE_CANDIDATE' and p.get('is_active_pick')]
    if version == 'V46_1' and not include_reject:
        picks = [p for p in picks if p.get('v46_1_layer') in ('A','B','PASS') or float(p.get('v46_1_position_size') or 0) > 0]
    return picks

def get_reject_picks(version=None):
    version = version or ACTIVE_VERSION
    return [p for p in get_all_picks_scoped(version) if p.get('pick_scope') == 'ACTIVE_CANDIDATE' and p.get('is_active_pick') and (p.get('v46_1_layer') == 'REJECT' or float(p.get('v46_1_position_size') or 0) <= 0)]

def get_pick_contract_summary(version=None):
    version = version or ACTIVE_VERSION
    all_picks = get_all_picks_scoped(version)
    active_all = [p for p in all_picks if p.get('pick_scope') == 'ACTIVE_CANDIDATE' and p.get('is_active_pick')]
    active = get_active_picks(version=version)
    rejected_active = [p for p in active_all if p not in active]
    if version in ('V88', 'V185', 'V86', 'V85', 'V50', 'V51', 'V52', 'V53', 'V54', 'V55', 'V56', 'V57', 'V58', 'V59', 'V60', 'V61', 'V62', 'V63', 'V64', 'V65', 'V66'):
        rejected_active = [p for p in all_picks if p.get('pick_scope') == 'REJECTED_CANDIDATE']
    historical = [p for p in all_picks if p.get('pick_scope') == 'HISTORICAL_BEST']
    watch = [p for p in all_picks if p.get('pick_scope') == 'WATCH_ONLY']
    return {
        'tradable_active_pick_count': len([p for p in active if p.get('pick_scope') == 'ACTIVE_CANDIDATE' and p.get('is_active_pick')]),
        'rejected_active_pick_count': len(rejected_active),
        'active_pick_count': len(active),
        'active_pick_count_including_reject': len(active) + len(rejected_active),
        'historical_best_count': len(historical),
        'watch_only_count': len(watch),
        'raw_pick_file_count': len(all_picks),
        'active_picks_not_historical_all_market': len(active) < len(historical) if historical else True,
        'contract_note': 'V44 legacy picks are historical best/backtest representatives; /api/picks returns active candidates only.' if ACTIVE_VERSION == 'V44' else 'Scoped pick contract enabled.'
    }

def reload_metrics():
    import json as _json
    paths = _active_version_paths(ACTIVE_VERSION) or {}
    # FIX(2026-08-17): metrics must come ONLY from the ACTIVE_VERSION itself.
    # Previously, under ACTIVE_VERSION==V88 this function preferred V185/V175/V172/V167/
    # V102/V101/V100/V99 reports (including V185, which was REJECTED_CAUSALITY),
    # so the dashboard labelled "V88" was actually showing rejected research metrics.
    if ACTIVE_VERSION == 'EMPTY_BOOK':
        return {}
    mp = paths.get('metrics')
    if mp and Path(mp).exists():
        return _json.loads(Path(mp).read_text())
    mp = Path('/root/.hermes/smc_opt_v44/v44_full.json') if ACTIVE_VERSION == 'V44' else Path('/root/.hermes/smc_opt_v31/v31_metrics.json')
    return _json.loads(mp.read_text()) if mp.exists() else {}


def _active_report_stats(scope='production_A_only'):
    """Return report-level net stats for current promoted engine when available."""
    m = reload_metrics()
    if not isinstance(m, dict):
        return {}
    stats = m.get(scope) if isinstance(m.get(scope), dict) else {}
    if not stats and isinstance(m.get('production_stats'), dict):
        stats = m.get('production_stats')
    net_success = m.get('net_success_contract') or {}
    selection_contract = m.get('selection_contract') or m.get('contract') or ''
    if not selection_contract and isinstance(m.get('production_policy'), dict):
        selection_contract = m['production_policy'].get('contract') or m['production_policy'].get('name') or ''
    return {
        'engine': m.get('engine') or ACTIVE_VERSION,
        'version': m.get('version') or ACTIVE_VERSION,
        'total_trades': int(stats.get('n') or m.get('production_total') or m.get('n_trades') or m.get('total_trades') or 0),
        'win_rate': float(stats.get('net_wr_ge_0_8') or stats.get('wr') or m.get('win_rate') or 0),
        'gross_win_rate': float(stats.get('gross_wr_gt_0') or stats.get('gross_wr') or stats.get('wr') or m.get('win_rate') or 0),
        'avg_pnl': float(stats.get('avg_net_pnl') or stats.get('avg_pnl') or m.get('avg_pnl') or 0),
        'gross_avg_pnl': float(stats.get('avg_gross_pnl') or stats.get('avg_pnl') or m.get('avg_pnl') or 0),
        'total_pnl': float(stats.get('cum_net_pnl') or stats.get('total_pnl') or 0),
        'small_profit_pollution_n': int(stats.get('small_profit_pollution_n') or 0),
        'small_profit_pollution_rate': float(stats.get('small_profit_pollution_rate') or 0),
        'net_success_threshold_pct': float(net_success.get('success_threshold_net_pct') or m.get('success_threshold_net_pct') or 0.8),
        'fee_pct': float(net_success.get('fee_pct') or m.get('fee_pct') or 0),
        'selection_contract': selection_contract,
    }

def get_default_trades():
    return reload_trades()

# ── Signal rendering styles ──
_KLINE_FULL_CACHE = {}
_V20C_TRADES_CACHE = None

def _load_v20c_trades_for(symbol, klines, chart_date_idx):
    """Load v20c backtest trades for symbol, enriched with prices/sub-signals (all versions)."""
    global _V20C_TRADES_CACHE
    try:
        _bt = _V20C_TRADES_CACHE
        if _bt is None:
            _bt = []
            with open(r'E:\test\smc_project\research\combo_v20f_trades.csv', encoding='utf-8-sig') as _fh:
                import csv as _csv
                for _row in _csv.DictReader(_fh):
                    _row['net_pnl_pct'] = float(_row.get('net_pnl_pct', 0))
                    _row['hold'] = int(_row.get('hold') or 10 if _row.get('src') == 'CONT' else 15)
                    _row['pnl_pct'] = _row['net_pnl_pct']
                    _row['combo'] = _row.get('src', 'EVENT')
                    _row['signal_type'] = _row.get('src', 'EVENT')
                    _row['zone_type'] = _row.get('src', 'EVENT')
                    _row['exit_reason'] = 'HOLD_EXIT（固定持有到期）'
                    _row['hold_bars'] = _row['hold']
                    _row['rr'] = round(abs(_row['net_pnl_pct']) / 0.5, 1) if _row['net_pnl_pct'] else 0
                    _row['conf_type'] = 'v20c 回测'
                    _row['entry_type'] = 'T+1开盘' if _row.get('src') != 'CONT' else '次日开盘'
                    _row['entry_detail'] = 'durable_sim_position'
                    _row['sub_signals'] = []
                    try:
                        import datetime as _dt2
                        _ed = str(_row.get('entry_date', ''))
                        if len(_ed) == 8:
                            _ex = (_dt2.datetime(int(_ed[:4]), int(_ed[4:6]), int(_ed[6:8])) + _dt2.timedelta(days=int(_row['hold']))).strftime('%Y%m%d')
                            _row['exit_date'] = _ex
                    except Exception:
                        pass
                    _bt.append(_row)
            _V20C_TRADES_CACHE = _bt
        _s = str(symbol)
        trades = [dict(t) for t in _bt if str(t.get('symbol', '')) == _s or ('.' not in str(t.get('symbol', '')) and (str(t.get('symbol', '')) + ('.SH' if str(t.get('symbol', '')).startswith(('6', '9')) else '.SZ'))) == _s]
        for _vt in trades:
            _ve = str(_vt.get('entry_date', ''))
            _vi = chart_date_idx.get(_ve, -1)
            if _vi < 0:
                _vi = chart_date_idx.get(_ve.replace('-', ''), -1)
            if 0 <= _vi < len(klines):
                _vt['entry_price'] = klines[_vi]['o']
                _vt['signal_price'] = klines[_vi]['c']
                _xe = str(_vt.get('exit_date', ''))
                _xi = chart_date_idx.get(_xe, -1)
                if _xi < 0:
                    _xi = chart_date_idx.get(_xe.replace('-', ''), -1)
                if 0 <= _xi < len(klines):
                    _vt['exit_price'] = klines[_xi]['c']
                else:
                    _hi = min(len(klines) - 1, _vi + int(_vt.get('hold', 10)))
                    _vt['exit_price'] = klines[_hi]['c']
                    _vt['exit_date'] = klines[_hi]['date'][:8]
            if _vi >= 0 and _vi < len(klines):
                _vt['sub_signals'] = _v20c_subsignals(_vt.get('src', 'EVENT'), _vi, klines, chart_date_idx)
            else:
                _vt['sub_signals'] = _v20c_subsignals(_vt.get('src', 'EVENT'), -1, klines, chart_date_idx, fallback_ed=_ve)
        return trades
    except Exception:
        return []

def _v20c_subsignals(src, entry_i, klines, date_idx, fallback_ed=''):
    """Generate sub-signal chain for a v20c backtest trade at entry bar (for K-line tooltip/table).
    Uses chart bar index when in range; otherwise calendar-shifted fallback from entry date."""
    import datetime as _dt3
    def _d(i):
        return klines[i]['date'][:8] if 0 <= i < len(klines) else ''
    def _shift(days):
        if 0 <= entry_i < len(klines) and _d(entry_i):
            _ti = max(0, min(len(klines) - 1, entry_i + days))
            return _d(_ti)
        if len(fallback_ed) == 8:
            try:
                return (_dt3.datetime(int(fallback_ed[:4]), int(fallback_ed[4:6]), int(fallback_ed[6:8])) + _dt3.timedelta(days=days)).strftime('%Y%m%d')
            except Exception:
                return fallback_ed
        return fallback_ed or '-'
    subs = []
    if src == 'CONT':
        subs.append({'name': 'MARKUP 确认', 'date': _shift(-15), 'detail': '60日放量拉升 >20%（大资金拉升阶段）'})
        subs.append({'name': '结构支撑回踩', 'date': _shift(-3), 'detail': '回踩 swing low 支撑后收回'})
        subs.append({'name': 'VWAP≥5% 确认', 'date': _shift(-1), 'detail': '价格偏离 VWAP ≥5%（强趋势）'})
        subs.append({'name': '入场(次日开盘)', 'date': _shift(0), 'detail': '开盘买入 固定10日持有'})
    else:
        subs.append({'name': '披露日(增持/回购)', 'date': _shift(-1), 'detail': '内部人公告：增持/回购披露'})
        subs.append({'name': '吸筹阶段确认', 'date': _shift(-20), 'detail': '60日下跌(ACCUM/DOWNTREND 阶段)'})
        subs.append({'name': 'ADX≥20 确认', 'date': _shift(-10), 'detail': '趋势强度 ADX≥20'})
        subs.append({'name': '入场(T+1)', 'date': _shift(0), 'detail': '次日开盘买入 固定15/20日'})
    return subs

SIG_STYLE = {
    'FVG_Bull':  {'fill': 'rgba(156,39,176,0.18)','stroke': 'rgba(156,39,176,0.55)','label': 'FVG','z': 2},
    'FVG_Bear':  {'fill': 'rgba(233,30,99,0.18)','stroke': 'rgba(233,30,99,0.55)','label': 'FVG','z': 2},
    'IFVG_Bull': {'fill': 'rgba(138,43,226,0.18)','stroke': 'rgba(138,43,226,0.55)','label': 'IFVG','z': 2},
    'IFVG_Bear': {'fill': 'rgba(138,43,226,0.18)','stroke': 'rgba(138,43,226,0.55)','label': 'IFVG','z': 2},
    'OB_Bull':   {'fill': 'rgba(33,150,243,0.16)','stroke': 'rgba(33,150,243,0.50)','label': 'OB','z': 3},
    'OB_Bear':   {'fill': 'rgba(244,67,54,0.16)','stroke': 'rgba(244,67,54,0.50)','label': 'OB','z': 3},
    'BPR_Bull':  {'fill': 'rgba(0,150,136,0.14)','stroke': 'rgba(0,150,136,0.50)','label': 'BPR','z': 3},
    'BPR_Bear':  {'fill': 'rgba(0,150,136,0.14)','stroke': 'rgba(0,150,136,0.50)','label': 'BPR','z': 3},
    'Sweep_SSL': {'stroke': '#8BC34A','type':'dashed','width':2,'label':'Sweep','z':4},
    'Sweep_BSL': {'stroke': '#FF9800','type':'dashed','width':2,'label':'Sweep','z':4},
    'CHOCH_Bull':{'stroke': '#00BCD4','type':'solid','width':2,'label':'CHOCH','z':5},
    'CHOCH_Bear':{'stroke': '#E91E63','type':'solid','width':2,'label':'CHOCH','z':5},
    'BOS_Bull':  {'stroke': '#4CAF50','type':'solid','width':2,'label':'BOS','z':5},
    'BOS_Bear':  {'stroke': '#F44336','type':'solid','width':2,'label':'BOS','z':5},
    'MSS_Bull':  {'stroke': '#4FC3F7','type':'dashed','width':2,'label':'MSS','z':5},
    'MSS_Bear':  {'stroke': '#E040FB','type':'dashed','width':2,'label':'MSS','z':5},
    'OTE_Bull':  {'fill': 'rgba(76,175,80,0.12)','stroke':'rgba(76,175,80,0.45)','label':'OTE','z':1},
    'OTE_Bear':  {'fill': 'rgba(76,175,80,0.12)','stroke':'rgba(76,175,80,0.45)','label':'OTE','z':1},
    'EQL':  {'stroke': '#B0BEC5','type':'solid','width':1,'label':'EQL','z':3},
    'EQL_High': {'stroke': '#B0BEC5','type':'solid','width':1,'label':'EQH','z':3},
    'EQL_Low': {'stroke': '#B0BEC5','type':'solid','width':1,'label':'EQL','z':3},
    'PO3_Acc':   {'fill': 'rgba(33,150,243,0.10)','stroke':'rgba(33,150,243,0.40)','label':'PO3-A','z':3},
    'PO3_Man':   {'fill': 'rgba(244,67,54,0.10)','stroke':'rgba(244,67,54,0.40)','label':'PO3-M','z':3},
    'PO3_DIS':   {'fill': 'rgba(76,175,80,0.10)','stroke':'rgba(76,175,80,0.40)','label':'PO3-D','z':3},
    'LiquidityVoid': {'stroke':'#9E9E9E','type':'dashed','width':1,'label':'LV','z':2},
    'LiquidityVoid_Bull': {'stroke':'#9E9E9E','type':'dashed','width':1,'label':'LV','z':2},
    'LiquidityVoid_Bear': {'stroke':'#9E9E9E','type':'dashed','width':1,'label':'LV','z':2},
    'Rejection_Resistance': {'fill':'rgba(255,152,0,0.10)','stroke':'rgba(255,152,0,0.35)','label':'RB','z':3},
    'Rejection_Support': {'fill':'rgba(76,175,80,0.10)','stroke':'rgba(76,175,80,0.35)','label':'RB','z':3},
    'BreakerBlock_Bull': {'fill':'rgba(156,39,176,0.10)','stroke':'rgba(156,39,176,0.35)','label':'BRK','z':3},
    'BreakerBlock_Bear': {'fill':'rgba(156,39,176,0.10)','stroke':'rgba(156,39,176,0.35)','label':'BRK','z':3},
    'Pinbar_Bull': {'stroke':'#FFD700','type':'dashed','width':1,'label':'PB','z':4},
    'Pinbar_Bear': {'stroke':'#FFC107','type':'dashed','width':1,'label':'PB','z':4},
}
SIG_FAMILY = {
    'FVG_Bull':'fvg','FVG_Bear':'fvg','IFVG_Bull':'ifvg','IFVG_Bear':'ifvg',
    'OB_Bull':'ob','OB_Bear':'ob','BPR_Bull':'bpr','BPR_Bear':'bpr',
    'Sweep_SSL':'sweep','Sweep_BSL':'sweep','structure':'structure',
    'CHOCH_Bull':'choch','CHOCH_Bear':'choch',
    'BOS_Bull':'bos','BOS_Bear':'bos',
    'MSS_Bull':'mss','MSS_Bear':'mss','OTE_Bull':'ote','OTE_Bear':'ote',
    'EQL':'eql','EQL_High':'eql','EQL_Low':'eql','LV':'lv','BRK':'brk',
    'LiquidityVoid':'lv','LiquidityVoid_Bull':'lv','LiquidityVoid_Bear':'lv','Rejection_Resistance':'rb','Rejection_Support':'rb',
    'BreakerBlock_Bull':'brk','BreakerBlock_Bear':'brk',
    'Pinbar_Bull':'pinbar','Pinbar_Bear':'pinbar',
}
FAMILY_COLORS = {
    'fvg':'#9C27B0','ifvg':'#7B1FA2','ob':'#2196F3','sweep':'#8BC34A',
    'choch':'#00BCD4','bos':'#4CAF50','mss':'#4FC3F7','ote':'#4CAF50',
    'eql':'#B0BEC5','po3':'#7C4DFF','bpr':'#009688','lv':'#9E9E9E',
    'rb':'#FF9800','brk':'#9C27B0','pinbar':'#FFD700',
}
FAMILY_LABELS = {
    'fvg':'FVG','ifvg':'IFVG','ob':'OB','sweep':'Sweep','choch':'CHOCH',
    'bos':'BOS','mss':'MSS','ote':'OTE','eql':'EQL','po3':'PO3',
    'bpr':'BPR','lv':'LV','rb':'RB','brk':'BRK','pinbar':'PB',
}

CSS = """
:root{--bg:#0a0e14;--card:#131820;--border:#1e2a3a;--text:#c9d1d9;--accent:#39d353;--red:#f85149;--blue:#58a6ff}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font:13px -apple-system,BlinkMacSystemFont,sans-serif;line-height:1.5}
nav{background:var(--card);border-bottom:2px solid var(--border);display:flex;align-items:center;padding:0 16px;flex-wrap:wrap;gap:2px}
nav a{color:var(--text);text-decoration:none;padding:12px 14px;font-size:12px;font-weight:500;border-bottom:2px solid transparent}
nav a:hover,nav a.active{color:var(--accent);border-bottom-color:var(--accent)}
nav .brand{font-weight:700;font-size:14px;color:#fff;margin-right:16px}
.container{max-width:1400px;margin:0 auto;padding:16px}
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:14px}
.card h2{font-size:14px;color:var(--blue);margin-bottom:10px;font-weight:600}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px}
.stat{padding:14px;border-radius:8px;background:var(--card);border:1px solid var(--border);text-align:center}
.stat .val{font-size:24px;font-weight:700}.stat .lbl{font-size:11px;color:#8b949e;margin-top:3px}
.stat.green .val{color:var(--accent)}.stat.red .val{color:var(--red)}.stat.blue .val{color:var(--blue)}
table{width:100%;border-collapse:collapse;font-size:11px}
th{background:var(--border);padding:8px 10px;text-align:left;font-weight:600;color:var(--blue)}
td{padding:6px 10px;border-bottom:1px solid var(--border)}
tr:hover{background:rgba(88,166,255,0.05)}
.badge{padding:2px 7px;border-radius:3px;font-size:10px;font-weight:600}
.badge-bull{background:rgba(57,211,83,0.15);color:var(--accent)}
.badge-tp{background:rgba(88,166,255,0.15);color:var(--blue)}
.badge-trail{background:rgba(188,140,255,0.15);color:#bc8cff}
.progress{height:3px;background:var(--border);border-radius:2px;overflow:hidden;margin-top:2px}
.progress-bar{height:100%;border-radius:2px}
.chart-container{width:100%;height:650px;margin:8px 0}
.signal-row{display:flex;align-items:center;gap:6px;padding:3px 0}
.signal-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.flex{display:flex;gap:12px;flex-wrap:wrap}.flex>*{flex:1;min-width:280px}
.mono{font-family:"JetBrains Mono",monospace;font-size:11px}
input,select{background:var(--bg);color:var(--text);border:1px solid var(--border);padding:7px 10px;border-radius:5px;font-size:12px}
button{background:var(--accent);color:#000;border:none;padding:7px 14px;border-radius:5px;cursor:pointer;font-weight:600;font-size:11px}
.green{color:var(--accent)}.red{color:var(--red)}.blue{color:var(--blue)}
.filter label{cursor:pointer;font-size:11px;display:inline-flex;align-items:center;gap:4px;padding:3px 6px;border-radius:3px;user-select:none}
.filter label:hover{background:rgba(88,166,255,0.08)}
.filter input[type=checkbox]{accent-color:var(--blue)}
.tog{padding:3px 8px;border-radius:3px;font-weight:600;font-size:11px}
.sig{display:inline-block;padding:1px 5px;border-radius:2px;font-size:9px;font-weight:600;margin:1px}
.sig-fvg{background:rgba(156,39,176,0.2);color:#ce93d8}
.sig-ifvg{background:rgba(138,43,226,0.2);color:#b39ddb}
.sig-ob{background:rgba(33,150,243,0.2);color:#90caf9}
.sig-sweep{background:rgba(139,195,74,0.2);color:#aed581}
.sig-choch{background:rgba(0,188,212,0.2);color:#80deea}
.sig-bos{background:rgba(76,175,80,0.2);color:#a5d6a7}
.sig-mss{background:rgba(79,195,247,0.2);color:#81d4fa}
.sig-ote{background:rgba(76,175,80,0.2);color:#a5d6a7}
.sig-eql{background:rgba(176,190,197,0.2);color:#cfd8dc}
.sig-po3{background:rgba(124,77,255,0.2);color:#b39ddb}
.sig-bpr{background:rgba(0,150,136,0.2);color:#80cbc4}
.sig-lv{background:rgba(158,158,158,0.2);color:#bdbdbd}
.sig-rb{background:rgba(255,152,0,0.2);color:#ffcc80}
.sig-brk{background:rgba(156,39,176,0.2);color:#ce93d8}
.sig-pinbar{background:rgba(255,215,0,0.2);color:#ffe082}
"""

JS_ECHARTS = '<script src="/echarts.js"></script>'

# ════════════════════════════════════════════
# KLINE FULL JS — Rectangle zones + Line breaks + Buy/Sell markers + Swings
# ════════════════════════════════════════════
KLINE_FULL_JS = r"""
var chart, allSeries, allSwings, allTrades, ohlcvData, dates;
var currentVersion = 'V88';
var currentSeq = [];
var tablePages = {signals:1, swings:1, trades:1};
var tablePageSize = 100;
var families = {};
FAMILY_LIST.forEach(function(f){families[f]=true});
// Default chart mode: reduce noise. Keep core zones/structure visible; show sweep as point only.
['eql','lv','po3','rb','pinbar'].forEach(function(f){families[f]=false});

function parseSeqFromURL(){
    var p=new URLSearchParams(window.location.search);
    var s=p.get('seq')||'';
    if(!s)return[];
    // Split on -> or - or →
    return s.split(/->|→|-/).filter(function(x){return x.length>0});
}
currentSeq=parseSeqFromURL();

function fmtDate(d){
    var s=String(d);
    if(s.length>=10&&s[4]=='-')return s.slice(0,10);
    if(s.length==8)return s.slice(0,4)+'-'+s.slice(4,6)+'-'+s.slice(6,8);
    return s.slice(0,10)||s;
}
function loadKline(){
    var sym=document.getElementById('sym').value;
    var tf=document.getElementById('tf').value;
    var ver=document.getElementById('ver').value; currentVersion=ver;
    document.getElementById('status').textContent='loading...';
    var seqParam=currentSeq.length>0?'&seq='+encodeURIComponent(currentSeq.join('-')):'';
    fetch('/api/kline_full?symbol='+encodeURIComponent(sym)+'&tf='+tf+'&ver='+ver+seqParam)
    .then(function(r){return r.json()}).then(function(d){
        if(d.error){document.getElementById('status').textContent=d.error;return;}
        var researchEmpty = d.version==='V517_EFFORT_RESULT' && !d.trade_count;
        document.getElementById('status').textContent = researchEmpty
            ? '该股票没有 V517 冻结回放交易；下方仅为 display-only SMC 上下文，未从旧版本回填，也不是当前候选。'
            : (d.count+' bars | '+d.signal_count+' signals | '+d.trade_count+' trades');
        // debug: log trade markers
        if(d.trades&&d.trades.length)console.log('[V20C] trades:',d.trades.length,'idx:',d.trades[0]._chart_idx,'ep:',d.trades[0].entry_price);
        allSeries=d.signals_list||[];
        allSwings=d.wave_swings||d.swings||[];
        allTrades=d.trades||[];
        tablePages={signals:1,swings:1,trades:1};
        window._highlight=d.highlight||[];
        ohlcvData=d.klines.map(function(k){return[k.o,k.c,k.l,k.h]});
        dates=d.klines.map(function(k){return k.date});
        renderKline(d);
        // FIX(2026-08-19): 模拟持仓/挂单信号标注（信号点 + 挂单/TP/SL 线 + 条件说明）
        window._simMarkers=d.sim_markers||null;
        if(window._simMarkers&&(window._simMarkers.points.length||window._simMarkers.lines.length)){
            var sp=[], sln=[];
            (window._simMarkers.points||[]).forEach(function(p){
                sp.push({coord:[p.date,p.price],symbol:'pin',symbolSize:16,itemStyle:{color:p.color||'#58a6ff'},label:{show:true,fontSize:9,color:'#fff',fontWeight:'bold',formatter:p.label||('信号'+p.order)},_tt:p.tt});
            });
            (window._simMarkers.lines||[]).forEach(function(l){
                sln.push({yAxis:l.price,label:{show:true,fontSize:9,color:l.color||'#888',formatter:l.label},lineStyle:{color:l.color||'#888',type:'dashed',width:1.5},_tt:l.label});
            });
            if(chart){
                chart.setOption({series:[{name:'K',type:'candlestick',markPoint:{data:sp,label:{show:true,fontSize:9,color:'#fff',fontWeight:'bold'}},markLine:{silent:false,symbol:['none','none'],data:sln,emphasis:{lineStyle:{width:2}}}}]});
            }
            var condBox=document.getElementById('sim-cond');
            if(condBox&&window._simMarkers.conditions)condBox.innerHTML='<div class="card" style="border-left:3px solid #d29922"><h3>🎯 模拟交易信号标注（买入原因 / TP / SL / 顺序）</h3><p style="color:#8b949e">'+window._simMarkers.conditions+'</p><p style="color:#8b949e;font-size:12px">🔵 ①信号点=事件/信号发生日（含策略原因）②买入点=成交日 ③卖出点=平仓日；🟡入场线 🟢TP线 🔴SL线（悬停彩线查看 TP/SL 条件）。点击图中标记查看详情。</p></div>';
        }
        renderSignalsTable(d.signals_list);
        renderTradesTable(d.trades);
        renderSwingsTable(d.swings);
        updateVersionBadge(ver,d);
        if(d.version==='V517_EFFORT_RESULT'){
            setTimeout(function(){
                var box=document.getElementById('kline-contract'); if(!box)return;
                var t=(d.trades||[])[0]||{}; var risk=Number(t.entry_price||0)-Number(t.stop||t.sl_price||0); var rr=risk>0?(Number(t.target||t.tp1||0)-Number(t.entry_price||0))/risk:0;
                var trace=d.trade_count ? '组合：确认摆动低点 → 高量SSL下扫收回 → response突破sweep high → 严格T+1开盘入场。入场 '+Number(t.entry_price||0).toFixed(2)+'；结构SL '+Number(t.stop||t.sl_price||0).toFixed(2)+'（sweep low×0.99）；结构TP '+Number(t.target||t.tp1||0).toFixed(2)+'（入场前可见最近swing high）；计划RR '+rr.toFixed(2)+'R；实际出场 '+(t.exit_reason||'-')+'。当前未满足RR≥1.5生产合同，REPLAY_ONLY / NO_BUY。' : '该股票不在 V517 frozen replay；没有信号是正确的空结果，未从旧版本补图。';
                box.innerHTML='<p style="color:#58a6ff">版本=V517_EFFORT_RESULT | '+trace+'</p>';
            },900);
        }
    }).catch(function(e){document.getElementById('status').textContent='Error: '+e});
}

// ── Build UI arrays for ECharts ──
function buildMarkAreas(af){
    var fa=[];
    var seq=0;
    allSeries.forEach(function(s){
        if(!af[s.family])return;
        var style=SIG_STYLE_MAP[s.type]||{};
        if(!style.fill)return;
        var upper=Number(s.upper)||0, lower=Number(s.lower)||0;
        if(upper<=0||lower<=0||upper===lower)return;
        var idx=Number(s.idx);
        var endX=idx+10<dates.length?dates[idx+10]:dates[dates.length-1];
        seq++;
        fa.push([{
            name:(s.seq||seq)+''+style.label,
            xAxis:dates[idx],yAxis:lower,
            _tt:(s.type||style.label)+'<br/>锚点bar: '+idx+' '+(dates[idx]||'')+'<br/>区域: '+lower.toFixed(2)+' ~ '+upper.toFixed(2)+'<br/>规则: '+(s.pine_rule||''),
            itemStyle:{color:style.fill,borderColor:style.stroke,borderWidth:1,opacity:0.7}
        },{xAxis:endX,yAxis:upper,_tt:(s.type||style.label)+'<br/>锚点bar: '+idx+' '+(dates[idx]||'')+'<br/>区域: '+lower.toFixed(2)+' ~ '+upper.toFixed(2)+'<br/>规则: '+(s.pine_rule||'')}]);
    });
    return fa;
}
function buildMarkLines(af){
    var ml=[];
    allSeries.forEach(function(s){
        if(!af[s.family])return;
        var style=SIG_STYLE_MAP[s.type]||{};
        if(!style.stroke||style.fill)return;
        // Sweep is a one-bar liquidity event; do not draw it as a 20-bar horizontal line.
        if(s.family==='sweep')return;
        var price=Number(s.price||s.upper||0);
        if(price<=0)return;
        var idx=Number(s.idx);
        var startIdx=Number(s.line_start_idx);
        var endIdx=Number(s.line_end_idx);
        if(isNaN(startIdx)) startIdx=idx;
        if(isNaN(endIdx)) endIdx=idx+20<dates.length?idx+20:dates.length-1;
        var labelPrefix=(s.seq||'')+style.label;
        var tt=labelPrefix+'<br/>发生bar: '+idx+' '+(dates[idx]||'')+'<br/>价格: '+price;
        if(s.family==='bos'||s.family==='choch'||s.family==='mss'){
            var pidx=Number(s.pivot_idx);
            if(!isNaN(pidx)&&pidx>=0&&pidx<dates.length) startIdx=Number(s.line_start_idx ?? pidx);
            endIdx=Number(s.line_end_idx ?? idx);
            if(isNaN(startIdx)) startIdx=pidx;
            if(isNaN(endIdx)) endIdx=idx;
            tt=labelPrefix+'<br/>线段含义: '+(s.line_semantics||'前高/前低到突破K线')
                +'<br/>方向: '+(s.line_direction||'')
                +'<br/>从左侧结构点: '+(isNaN(pidx)?'-':pidx)+' '+(s.pivot_date||dates[startIdx]||'')+' @ '+Number(s.pivot_price||price).toFixed(2)
                +'<br/>到右侧突破K: '+idx+' '+(dates[idx]||'')+' close='+Number(s.break_price||price).toFixed(2)
                +'<br/>左→右: '+(s.from_left||'confirmed previous high/low')+' → '+(s.to_right||'first close break')
                +'<br/>规则: '+(s.pine_rule||'close crossover/crossunder pivot level');
            price=Number(s.line_start_price||s.pivot_price||price);
        }
        ml.push([{xAxis:dates[startIdx],yAxis:price,_tt:tt},{xAxis:dates[endIdx],yAxis:price,_tt:tt,lineStyle:{color:style.stroke,type:style.type||'dashed',width:style.width||1,opacity:0.6},label:{show:true,formatter:(s.seq||'')+style.label,color:style.stroke,fontSize:9,position:'start'}}]);
    });
    return ml;
}
function buildSignalPoints(af){
    var fp=[];
    var seqLabels={'Sweep_SSL':'LIQ','Sweep_BSL':'LIQ','OB_Bull':'OB','OB_Bear':'OB',
        'CHOCH_Bull':'CHOCH↑','CHOCH_Bear':'CHOCH↓','BOS_Bull':'BOS↑','BOS_Bear':'BOS↓',
        'FVG_Bull':'FVG','FVG_Bear':'FVG','Pinbar_Bull':'PB','Pinbar_Bear':'PB',
        'BreakerBlock_Bull':'BRK','BreakerBlock_Bear':'BRK','MSS_Bull':'MSS↑','MSS_Bear':'MSS↓'};
    // Use API-returned highlight data for precise bar-level sequence
    var hlMap={};
    if(window._highlight&&window._highlight.length>0){
        window._highlight.forEach(function(h){hlMap[h.bar]={n:h.num,t:h.type};});
    }
    allSeries.forEach(function(s){
        if(!af[s.family])return;
        var price=Number(s.price||s.upper||0);
        if(price<=0)return;
        var idx=Number(s.idx);
        var color=(SIG_STYLE_MAP[s.type]||{}).stroke||'#888';
        var sl=seqLabels[s.type]||'';
        var hl=hlMap[idx];
        var isKey=!!sl;
        if(hl){
            var cn=String.fromCharCode(0x245F+hl.n);
            fp.push({
                name:cn+hl.t,coord:[dates[idx],price],value:cn+hl.t,
                symbol:'roundRect',symbolSize:[56,24],
                itemStyle:{color:'#ff0000',borderColor:'#ffff00',borderWidth:3},
                label:{show:true,formatter:cn+hl.t,color:'#ffffff',fontSize:14,fontWeight:'bold',position:'inside'}
            });
        }else if(isKey){
            var isSweep=(s.family==='sweep');
            fp.push({
                name:sl,coord:[dates[idx],price],value:sl,
                symbol:isSweep?(s.direction==='bull'?'triangle':'path://M0,10 L10,10 L5,0 Z'):'diamond',
                symbolSize:isSweep?10:9,
                symbolRotate:isSweep?(s.direction==='bull'?180:0):0,
                itemStyle:{color:isSweep?'#ffd166':'#f85149',borderColor:'#111',borderWidth:1},
                label:{show:true,formatter:sl,color:'#fff',fontSize:7,fontWeight:'bold',position:'inside'}
            });
        }else{
            // Non-key raw signals are available in table/toggles; avoid cluttering chart.
            if(!hl) return;
        }
    });
    return fp;
}
function buildSwingLines(af){
    // HH/HL/LL/LH zigzag polyline — filtered by swing toggle
    if(!af['swings'])return [];
    if(!allSwings||allSwings.length<2)return[];
    var coords=[];
    allSwings.forEach(function(sw){
        var idx=Number(sw.bar);
        if(idx>=0&&idx<dates.length){
            coords.push({coord:[dates[idx],Number(sw.price)],label:sw.label||''});
        }
    });
    if(coords.length<2)return[];
    // Build markLines connecting consecutive swings
    var lines=[];
    for(var i=0;i<coords.length-1;i++){
        var clr=coords[i].label&&coords[i].label[0]==='H'?'#ff6b6b':'#51cf66';
        lines.push([{
            xAxis:coords[i].coord[0],yAxis:coords[i].coord[1],
            label:{show:true,formatter:coords[i].label,color:clr,fontSize:9,fontWeight:'bold',position:'start'}
        },{
            xAxis:coords[i+1].coord[0],yAxis:coords[i+1].coord[1],
            lineStyle:{color:clr,width:1.5,opacity:0.5,type:'dashed'},
            label:{show:true,formatter:coords[i+1].label,color:clr,fontSize:9,fontWeight:'bold',position:'end'}
        }]);
    }
    return lines;
}
function buildTradeMarkers(af){
    var entries=[],exits=[],sllines=[],tplines=[];
    allTrades.forEach(function(t,ti){
        var idx=Number(t._chart_idx);
        if(idx<0||idx>=dates.length)return;
        var ep=Number(t.entry_price);
        var xp=Number(t.exit_price);
        var pnl=Number(t.pnl_pct||0);
        var rr=Number(t.rr||0);
        var won=(t.pnl_pct||0)>0;
        var combo=t._combo||('T'+(ti+1));
        if(!(ep>0)&&!(xp>0))return;
        var tt='Trade #'+(ti+1)+'<br/>'+combo+'<br/>'+t.entry_date+'<br/>Price: '+ep.toFixed(2)+' > '+xp.toFixed(2)+'<br/>PnL: '+(pnl>=0?'+':'')+pnl.toFixed(2)+'% | RR: '+rr.toFixed(1)+'x<br/>'+t.entry_type+' | '+(won?'WON':'LOST');
        // Entry: BUY marker — green pin with price label
        entries.push({name:combo,coord:[dates[idx],ep],value:combo,_tt:tt,
            itemStyle:{color:'#00e676'},
            symbol:'pin',symbolSize:36,
            label:{show:true,formatter:combo+'\n'+ep.toFixed(2),fontSize:10,color:'#fff',position:'top',fontWeight:'bold'}});
        // Exit: SELL marker — red diamond (OPEN monitor positions have no exit yet)
        var xi=t._exit_idx||idx+5;
        if(xi>=dates.length)xi=dates.length-1;
        if(xp>0){
            exits.push({coord:[dates[xi],xp],value:(pnl>=0?'+':'')+pnl.toFixed(1)+'%',_tt:tt,
                itemStyle:{color:won?'#00e5ff':'#ff6d00'},
                symbol:'diamond',symbolSize:16,
                label:{show:true,formatter:(pnl>=0?'+':'')+pnl.toFixed(1)+'%',fontSize:9,
                    color:won?'#00e5ff':'#ff6d00',position:'bottom'}});
        }
        // SL line
        var sl=Number(t.sl||0);
        if(sl>0&&af['sl']!==false){
            var slend=idx+10<dates.length?dates[idx+10]:dates[dates.length-1];
            sllines.push([{xAxis:dates[idx],yAxis:sl},{xAxis:slend,yAxis:sl,
                lineStyle:{color:'#d29922',type:'dashed',width:1,opacity:0.7},
                label:{show:true,formatter:'SL '+sl.toFixed(2)+' ('+(t.sl_pct||0).toFixed(2)+'%)',color:'#d29922',fontSize:9,position:'start'}}]);
        }
        // TP line
        var tp=Number(t.tp_price||0);
        if(tp>0&&tp>ep&&af['tp']!==false){
            var tpend=idx+10<dates.length?dates[idx+10]:dates[dates.length-1];
            tplines.push([{xAxis:dates[idx],yAxis:tp},{xAxis:tpend,yAxis:tp,
                lineStyle:{color:'#3fb950',type:'dashed',width:1,opacity:0.5},
                label:{show:true,formatter:'TP '+tp.toFixed(2)+' ('+(t.tp_pct||0).toFixed(1)+'%)',color:'#3fb950',fontSize:9,position:'end'}}]);
        }
    });
    return {entries:entries,exits:exits,sllines:sllines,tplines:tplines};
}
function renderKline(d){
    if(!chart){chart=echarts.init(document.getElementById('chart'),'dark');window.addEventListener('resize',function(){chart.resize()});}
    var af={};
    FAMILY_LIST.forEach(function(f){
        var cb=document.getElementById('sf-'+f);
        af[f]=cb?cb.checked:true;
    });
    af['sl']=document.getElementById('showSL')?document.getElementById('showSL').checked:true;
    af['tp']=document.getElementById('showTP')?document.getElementById('showTP').checked:true;
    af['swings']=document.getElementById('showSwings')?document.getElementById('showSwings').checked:true;

    var fa=buildMarkAreas(af);
    var fl=buildMarkLines(af);
    var fp=buildSignalPoints(af);
    var swl=buildSwingLines(af);
    var tm=buildTradeMarkers(af);

    var allPoints=fp.concat(tm.entries).concat(tm.exits);
    var allLines=fl.concat(tm.sllines).concat(tm.tplines);
    if(af['swings'])allLines=allLines.concat(swl);

    chart.clear();
    chart.setOption({
        animation:false,backgroundColor:'#0d1117',
        tooltip:{trigger:'axis',axisPointer:{type:'cross'},
            formatter:function(params){
                for(var i=0;i<params.length;i++){
                    var p=params[i];
                    if(p.componentType==='markPoint'&&p.data&&p.data._tt)return p.data._tt;
                    if(p.componentType==='markLine'&&p.data&&p.data._tt)return p.data._tt;
                    if(p.componentType==='markArea'&&p.data&&p.data._tt)return p.data._tt;
                }return false;
            }
        },
        dataZoom:[{type:'inside',start:0,end:100},{type:'slider',start:0,end:100,bottom:10,height:25,borderColor:'#30363d',backgroundColor:'#161b22'}],
        grid:{left:'5%',right:'5%',bottom:'15%',top:'5%'},
        xAxis:{type:'category',data:dates,axisLine:{lineStyle:{color:'#30363d'}},axisLabel:{rotate:45,fontSize:10,interval:Math.max(1,Math.floor(dates.length/20)),color:'#8b949e'},splitLine:{show:false}},
        yAxis:{scale:true,splitLine:{lineStyle:{color:'#21262d',type:'dashed'}},axisLabel:{color:'#8b949e',fontSize:11}},
        series:[{name:'K',type:'candlestick',data:ohlcvData,
            itemStyle:{color:'#f85149',color0:'#3fb950',borderColor:'#f85149',borderColor0:'#3fb950'},
            markPoint:{data:allPoints,label:{show:true,fontSize:8,color:'#fff',fontWeight:'bold'},emphasis:{scale:true}},
            markArea:{silent:false,data:fa,emphasis:{itemStyle:{opacity:0.5}}},
            markLine:{silent:false,symbol:['circle','circle'],symbolSize:4,data:allLines,emphasis:{lineStyle:{width:2}}}
        }]
    });
}

function pageControls(kind,total){
    var pages=Math.max(1,Math.ceil(total/tablePageSize));
    if(tablePages[kind]<1)tablePages[kind]=1;
    if(tablePages[kind]>pages)tablePages[kind]=pages;
    return '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:6px 0;color:#8b949e;font-size:12px">'+
        '<span>第 '+tablePages[kind]+'/'+pages+' 页，本页 '+Math.min(tablePageSize,Math.max(0,total-(tablePages[kind]-1)*tablePageSize))+' 条 / 共 '+total+' 条</span>'+
        '<button onclick="tablePages.\''+kind+'\'--;renderPagedTable(\''+kind+'\')" style="background:#21262d;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;padding:2px 8px">上一页</button>'+
        '<button onclick="tablePages.\''+kind+'\'++;renderPagedTable(\''+kind+'\')" style="background:#21262d;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;padding:2px 8px">下一页</button>'+
        '<label>每页 <select onchange="tablePageSize=parseInt(this.value,10);tablePages.signals=1;tablePages.swings=1;tablePages.trades=1;renderSignalsTable(allSeries);renderTradesTable(allTrades);renderSwingsTable(allSwings)" style="background:#161b22;color:#c9d1d9;border:1px solid #30363d"><option '+(tablePageSize==50?'selected':'')+'>50</option><option '+(tablePageSize==100?'selected':'')+'>100</option><option '+(tablePageSize==200?'selected':'')+'>200</option><option '+(tablePageSize==500?'selected':'')+'>500</option></select></label>'+
        '</div>';
}
function renderPagedTable(kind){
    if(kind==='signals')renderSignalsTable(allSeries);
    if(kind==='trades')renderTradesTable(allTrades);
    if(kind==='swings')renderSwingsTable(allSwings);
}

function renderSignalsTable(sigs){
    var el=document.getElementById('signal-tbl');
    if(!sigs||!sigs.length){el.innerHTML='<p style=color:#8b949e>no signals</p>';return}
    var famMap={fvg:'fvg',ifvg:'ifvg',ob:'ob',sweep:'sweep',choch:'choch',bos:'bos',mss:'mss',ote:'ote',eql:'eql',po3:'po3',bpr:'bpr',lv:'lv',rb:'rb',brk:'brk',pinbar:'pinbar'};
    var start=(tablePages.signals-1)*tablePageSize, page=sigs.slice(start,start+tablePageSize);
    el.innerHTML=pageControls('signals',sigs.length)+'<table style=margin-top:8px><thead><tr><th>#</th><th>信号</th><th>Bar</th><th>信号日</th><th>方向</th><th>价格</th><th>Zone</th><th>成本线</th><th>波动</th><th>强度</th><th>置信</th></tr></thead><tbody>'+page.map(function(s,pi){
        var si=start+pi;
        var fam=famMap[s.family]||'fvg';
        var zl=Number(s.zone_low||s.lower||0), zh=Number(s.zone_high||s.upper||0);
        var zone=(zl&&zh&&zl!==zh)?(zl.toFixed(2)+'~'+zh.toFixed(2)):((zl&&zh)?zl.toFixed(2):'-');
        var cost=Number(s.cost_line||s.smart_money_cost||0);
        var volPct=Number(s.volatility_pct||0);
        var volStr=volPct?(volPct.toFixed(1)+'%'):(s.v25_vol_class||s.market_state||'-');
        return'<tr><td class=mono>'+(si+1)+'</td><td><span class=\"sig sig-'+fam+'\">'+(s.zone_type||s.type)+'</span></td><td class=mono>'+s.idx+'</td><td class=mono>'+(s.signal_date||s.date||'')+'</td><td>'+s.direction+'</td><td class=mono>'+(Number(s.price)||0).toFixed(2)+'</td><td class=mono>'+zone+'</td><td class=mono>'+(cost?cost.toFixed(2):'-')+'</td><td class=mono>'+volStr+'</td><td class=mono>'+(Number(s.strength)||0).toFixed(1)+'</td><td class=mono>'+(Number(s.confidence)||0).toFixed(2)+'</td></tr>';
    }).join('')+'</tbody></table>';
}

function renderTradesTable(trades){
    var el=document.getElementById('trade-tbl');
    if(!trades||!trades.length){el.innerHTML='<p style=color:#8b949e>no trades for this stock</p>';return}
    var start=(tablePages.trades-1)*tablePageSize, page=trades.slice(start,start+tablePageSize);
    el.innerHTML=pageControls('trades',trades.length)+'<table style=margin-top:8px><thead><tr><th>#</th><th>选股日</th><th>加入日</th><th>买入日</th><th>买入价</th><th>卖出日</th><th>卖出价</th><th>信号</th><th>DNA</th><th>组合合同</th><th>MTF</th><th>Zone</th><th>成本线</th><th>波动</th><th>入场</th><th>回撤%</th><th>出场原因</th><th>子信号</th><th>PnL</th><th>SL</th><th>RR</th><th>持仓</th></tr></thead><tbody>'+page.map(function(t,pi){
        var ti=start+pi;
        var pnl=Number(t.pnl_pct||0);
        var cls=pnl>0?'green':'red';
        var zl=Number(t.zone_low||0), zh=Number(t.zone_high||0);
        var zone=(zl&&zh)?(zl.toFixed(2)+'~'+zh.toFixed(2)):'-';
        var cost=Number(t.cost_line||t.smart_money_cost||0);
        var vol=Number(t.volatility_pct||0);
        var dna=(t.dna_preferred_behavior||t.symbol_dna_mode||'-');
        var comboKey=(t.combo_contract_key||t.combo_role||t.combo_contract||'-');
        var mtf=(t.mtf_permission||t.combo_mtf_permission||'-');
        var subs=(t.sub_signals||[]).map(function(s,i){return 'S'+(i+1)+s.name+'('+s.date+')';}).join(' → ');
        return'<tr><td class=mono>'+(ti+1)+'</td><td class=mono>'+(t.select_date||t.pick_date||'')+'</td><td class=mono>'+(t.join_date||'')+'</td><td class=mono>'+(t.entry_date||'')+'</td><td class=mono>'+(Number(t.entry_price)||0).toFixed(2)+'</td><td class=mono>'+(t.exit_date||(t.entry_date||''))+'</td><td class=mono>'+(Number(t.exit_price)||0).toFixed(2)+'</td><td style=font-size:10px>'+(t.signal_type||t.zone_type||'')+'</td><td class=mono style=font-size:9px;color:#3fb950>'+dna+'</td><td class=mono style=font-size:9px;color:#d29922>'+comboKey+'</td><td class=mono style=font-size:9px>'+mtf+'</td><td class=mono>'+zone+'</td><td class=mono>'+(cost?cost.toFixed(2):'-')+'</td><td class=mono>'+(vol?vol.toFixed(1)+'%':'-')+'</td><td>'+(t.conf_type||t.entry_type||'')+'</td><td class=mono>'+(Number(t.retrace_pct||t.risk_pct)||0).toFixed(1)+'%</td><td style=font-size:10px>'+(t.exit_reason||'')+'</td><td style=font-size:9px;color:#bc8cff title="'+subs+'">'+(subs?subs.substring(0,26)+'…':'')+'</td><td class='+cls+'>'+(pnl>=0?'+':'')+pnl.toFixed(2)+'%</td><td class=mono>'+(Number(t.sl_pct||t.sl||0)).toFixed(2)+'%</td><td class=mono>'+(Number(t.rr)||0).toFixed(1)+'x</td><td class=mono>'+(t.hold_bars||0)+'</td></tr>';
    }).join('')+'</tbody></table>';
}

function renderSwingsTable(swings){
    var el=document.getElementById('swing-tbl');
    if(!swings||!swings.length){el.innerHTML='<p style=color:#8b949e>no swings</p>';return}
    var start=(tablePages.swings-1)*tablePageSize, page=swings.slice(start,start+tablePageSize);
    el.innerHTML=pageControls('swings',swings.length)+'<table style=margin-top:8px><thead><tr><th>#</th><th>Bar</th><th>类型</th><th>价格</th><th>标签</th></tr></thead><tbody>'+page.map(function(sw,pi){
        var si=start+pi;
        var clr=sw.label&&sw.label[0]==='H'?'#ff6b6b':'#51cf66';
        return'<tr><td class=mono>'+(si+1)+'</td><td class=mono>'+sw.bar+'</td><td style=\"color:'+clr+'\">'+sw.type+'</td><td class=mono>'+(Number(sw.price)||0).toFixed(2)+'</td><td style=\"font-weight:bold;color:'+clr+'\">'+(sw.label||'')+'</td></tr>';
    }).join('')+'</tbody></table>';
}

function updateVersionBadge(ver,d){
    var badge=document.getElementById('ver-badge');
    if(!badge)return;
    var displayVer = d.frontend_version || d.version || ver;
    badge.textContent=displayVer+' | '+d.trade_count+' trades';
}

function toggleAllSignals(state){
    FAMILY_LIST.forEach(function(f){
        var cb=document.getElementById('sf-'+f);
        if(cb)cb.checked=state;
    });
    renderKline();
}
function toggleSwings(){
    renderKline();
}
function toggleSL(){
    renderKline();
}
function toggleTP(){
    renderKline();
}
FAMILY_LIST.forEach(function(f){
    setTimeout(function(){
        var cb=document.getElementById('sf-'+f);
        if(cb)cb.addEventListener('change',renderKline);
    },100);
});
function initializeKlineFromURL(){
    var p=new URLSearchParams(window.location.search);
    var sym=p.get('symbol')||p.get('s')||'';
    var ver=p.get('ver')||p.get('version')||'';
    var tf=p.get('tf')||'';
    if(sym&&document.getElementById('sym')) document.getElementById('sym').value=sym;
    if(ver&&document.getElementById('ver')) document.getElementById('ver').value=ver;
    if(tf&&document.getElementById('tf')) document.getElementById('tf').value=tf;
}
function lockEmptyBookKline(){
    // FIX(2026-08-17): 解除 EMPTY_BOOK 下对 K 线版本的强制锁定。
    // 之前这里无条件把版本设为 V517，使用户无法选择其它研究版本；
    // EMPTY_BOOK 只限制写入，不限制视觉检查与版本选择，用户自由选择。
    // (no-op: 保留函数以兼容调用点)
}
initializeKlineFromURL();
lockEmptyBookKline();
setTimeout(loadKline,300);
""".replace('FAMILY_LIST', json.dumps(sorted(set(SIG_FAMILY.values()))))


def build_kline(symbol='600519.SH', version=None):
    version = version or ACTIVE_VERSION
    is_v517 = str(version).upper() in ('V517', 'V517_EFFORT_RESULT')
    kline_contract_title = 'V517 replay / 因果执行合同' if is_v517 else 'K线交易 DNA/组合合同同步'
    kline_contract_placeholder = 'V517 frozen replay 加载中…' if is_v517 else '加载中...'
    fam_list = sorted(set(SIG_FAMILY.values()))
    toggle_html = ''
    for f in fam_list:
        clr = FAMILY_COLORS.get(f, '#888')
        lbl = FAMILY_LABELS.get(f, f.upper())
        toggle_html += f'<label style="border-left:3px solid {clr}"><input type="checkbox" id="sf-{f}" checked> {lbl}</label>\n'

    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>SMC Kline - {symbol}</title><style>{CSS}</style></head><body>
{build_nav()}
<div class="container">
<div class="card"><h2>📈 {symbol} <span id="ver-badge" style="font-size:11px;color:#8b949e;margin-left:12px">{FRONTEND_VERSION}</span></h2>
<div style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap">
<input id="sym" value="{symbol}" style="flex:1;min-width:120px">
<select id="tf"><option value="daily">日线</option><option value="weekly">周线</option><option value="60min">60min</option></select>
<select id="ver" onchange="loadKline()"><option value="V20C" {'selected' if str(version).upper() in ('V20C',) else ''}>v20c 双方向组合（事件+SMC+延续 / 当前研究）</option><option value="V517" {'selected' if str(version).upper() in ('V517','V517_EFFORT_RESULT') else ''}>V517 日线量价吸收（冻结回放 / 当前门禁失败）</option><option value="V88" {'selected' if str(version).upper() not in ('V517','V517_EFFORT_RESULT','V20C') else ''}>{FRONTEND_VERSION} 生产合同</option><option value="V66">V66 近期REENTRY风险修复</option><option value="V65">V65 亏损复盘门禁</option><option value="V64">V64 CONTINUATION专项提升</option><option value="V63">V63 REENTRY专项提升</option><option value="V62">V62 假突破二次门禁</option><option value="V61">V61 出场层修复</option><option value="V60">V60 分族质量门禁</option><option value="V59">V59 全市场3年生成器</option><option value="V58">V58 continuation再入场</option><option value="V57">V57 分级结构破位退出</option><option value="V56">V56 突破质量分层</option><option value="V55">V55 前置门禁+自适应TP</option><option value="V54">V54 二次SMC再入场</option><option value="V53">V53 趋势分层runner</option><option value="V52">V52 二次确认+reclaim</option><option value="V51">V51 4R结构锁定</option><option value="V50">V50 信号快照同源</option><option value="V49">V49 移动止盈止损优化版</option><option value="V48_1">V48.1 生产版(出场修复+弱ZONE过滤)</option><option value="V47_2">V47.2 高质量生产版</option><option value="V46_1">V46.1 SMC2026分层质量门控</option><option value="V45.4">V45.4 FVG二次确认默认版</option><option value="V45.5">V45.5 Reclaim实验(拒绝默认)</option><option value="V45.3">V45.3 出场风控版</option><option value="V45.2">V45.2 质量过滤版</option><option value="V45.1">V45.1 召回修复版</option><option value="V45">V45 Native正确性基线</option><option value="V41">V41 复盘持仓微调版</option><option value="V40">V40 复盘出场修复版</option><option value="V39">V39 CHOCH质量扩展版</option><option value="V38">V38 Pine缺口补齐版</option><option value="V37">V37 盈亏比修复版</option><option value="V36">V36 重叠去重+RANGE FVG修复版</option><option value="V34D">V34D LuxAlgo同源OB质量版</option><option value="V33">V33 MSS结构修复</option><option value="V32D">V32D HIGH_VOL过滤</option><option value="V32C">V32C 严格限价入场</option><option value="V32B">V32B 严格入场/止损修复</option><option value="V32A">V32A Pine-like信号正确性核心</option><option value="V31">V31 ICT架构(SH/MSS/FVG + OSOK + 严格序列)</option><option value="V30">V30 严格序列(Sweep→CHOCH/MSS→Zone→确认)</option><option value="V29">V29 高质过滤</option><option value="V28">V28 质量分层</option><option value="V27">V27 严格SMC</option><option value="V19">V19 实证评分</option><option value="V18">V18 自迭代</option><option value="V17">V17 完整SMC</option><option value="V16.2">V16.2 高级SMC</option><option value="V16.1">V16.1 多周期</option><option value="V16">V16 SMC</option><option value="V15">V15 Zone</option></select>
<button onclick="loadKline()">🔄 加载</button><span id="status" style="color:var(--blue);line-height:32px"></span>
</div>
<div class="filter">
<span style="color:#8b949e;font-weight:bold;margin-right:8px">🔍 信号:</span>
{toggle_html}
<span style="flex:1"></span>
<label class="tog" style="border-left:3px solid #ff6b6b"><input type="checkbox" id="showSwings" checked onchange="toggleSwings()"> 🔷 Swings</label>
<label class="tog" style="border-left:3px solid #d29922"><input type="checkbox" id="showSL" checked onchange="toggleSL()"> 🛑 SL</label>
<label class="tog" style="border-left:3px solid #3fb950"><input type="checkbox" id="showTP" checked onchange="toggleTP()"> 🎯 TP</label>
<button style="padding:2px 8px;background:#21262d;color:#c9d1d9;border:1px solid #30363d;border-radius:3px;cursor:pointer;font-size:10px" onclick="toggleAllSignals(true)">全开</button>
<button style="padding:2px 8px;background:#21262d;color:#c9d1d9;border:1px solid #30363d;border-radius:3px;cursor:pointer;font-size:10px" onclick="toggleAllSignals(false)">全关</button>
</div>
<div id="chart" class="chart-container"></div><div id="sim-cond"></div></div>

<div class="flex">
<div class="card"><h2>🔷 HH/HL/LL/LH 摆动点</h2><div id="swing-tbl"></div></div>
<div class="card"><h2>📋 信号列表</h2><div id="signal-tbl"></div></div>
</div>
<div class="card"><h2>📊 交易记录</h2><div id="trade-tbl"></div></div>
<div class="card" style="border-left:3px solid #58a6ff"><h2>{kline_contract_title}</h2><div id="kline-contract">{kline_contract_placeholder}</div></div>
</div>""" + JS_ECHARTS + "<script>var SIG_STYLE_MAP=" + json.dumps(SIG_STYLE) + ";" + KLINE_FULL_JS + "\nasync function loadKlineContract(){try{var sym=document.getElementById('sym').value||'" + symbol + "';var ver=document.getElementById('ver').value||'" + ACTIVE_VERSION + "';if(String(ver).toUpperCase()==='V517'){document.getElementById('kline-contract').innerHTML='<p style=\"color:#58a6ff\">版本=V517_EFFORT_RESULT | 冻结 replay 因果节点和交易已在上方绘制；REPLAY_ONLY / Shadow NO_BUY，不适用旧版 DNA、组合合同或 MTF 字段。</p>';return;}var r=await fetch('/api/kline_full?symbol='+encodeURIComponent(sym)+'&tf=daily&ver='+encodeURIComponent(ver));var d=await r.json();var rows=(d.trades||[]).slice(0,8);var html='<p style=\"color:#8b949e\">版本=" + FRONTEND_VERSION + " | 交易标识='+(d.trades||[]).length+' | 展示K线图上的信号/组合信号/DNA合同字段</p><table><thead><tr><th>代码</th><th>买入日</th><th>卖出日</th><th>信号</th><th>DNA</th><th>组合合同</th><th>MTF</th><th>Zone</th></tr></thead><tbody>';for(var t of rows){html+='<tr><td class=mono>'+sym+'</td><td class=mono>'+(t.entry_date||'-')+'</td><td class=mono>'+(t.exit_date||'-')+'</td><td class=mono>'+(t.signal_type||t.zone_type||'-')+'</td><td class=mono style=\"color:#3fb950;font-size:9px\">'+(t.dna_preferred_behavior||t.smc_dna||'-')+'</td><td class=mono style=\"color:#d29922;font-size:9px\">'+(t.combo_contract_key||t.combo_contract||'-')+'</td><td class=mono style=\"font-size:9px\">'+(t.weekly_trend_state||t.weekly_state||'-')+'/'+(t.daily_structure_state||t.daily_state||'-')+'/'+(t.m60_state||'-')+'</td><td class=mono>'+(t.zone||((t.zone_low&&t.zone_high)?(Number(t.zone_low).toFixed(2)+'~'+Number(t.zone_high).toFixed(2)):'-'))+'</td></tr>';}html+='</tbody></table>';document.getElementById('kline-contract').innerHTML=html;}catch(e){document.getElementById('kline-contract').innerHTML='<span style=\"color:#f85149\">合同加载失败: '+e+'</span>';}}setTimeout(loadKlineContract,800);" + "</script></body></html>"


def build_dashboard(qs=None):
    if _v526_live_production():
        registry = _production_registry()
        positions = [p for p in (load_positions() if load_positions else []) if str((p.get('raw_pick') or {}).get('engine') or '') == registry.get('production_strategy')]
        pending = _load_json_list(Path('/root/.hermes/smc_monitor/v526_pending_orders.json'), [])
        live = _v526_state()
        rows = ''.join(f'<tr><td class="mono">{html.escape(str(p.get("symbol") or ""))}</td><td>{html.escape(str(p.get("status") or ""))}</td><td class="mono">{p.get("entry_price",0):.3f}</td><td class="mono" style="color:#f85149">{p.get("sl_price",0):.3f}</td><td class="mono" style="color:#3fb950">{p.get("tp1_price",0):.3f}</td><td>{html.escape(str(p.get("pick_date") or ""))}</td><td>{html.escape(str(p.get("filled_at") or "-"))}</td></tr>' for p in positions) or '<tr><td colspan="7">当前无持仓；等待全市场 scanner 产生新的 PENDING_NEXT_OPEN。</td></tr>'
        return f'''<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>SMC V526 生产仪表盘</title><style>{CSS}</style></head><body>{build_nav()}<div class="container">
<div class="card" style="border-left:3px solid #3fb950"><h2>V526 生产链路已启用</h2><p>当前策略：V517 日线量价吸收。只接受：确认 Swing Low → 高量 SSL 下扫收回 → response 突破 → <b>下一交易日开盘</b>。历史 replay 不会回填成买单。</p><p>数据 epoch：{html.escape(str((registry.get('data_epoch') or {}).get('epoch_id') or '-'))}；当前持仓 {sum(p.get('status') == 'OPEN' for p in positions)}；待开盘验证 {sum(p.get('status') == 'PENDING_NEXT_OPEN' for p in pending)}。</p></div>
<div class="card"><h3>实时执行状态</h3><p>{html.escape(str(live.get('mode') or '-'))}｜检查 {live.get('checked',0)}｜本次平仓 {live.get('changed',0)}｜更新时间 {html.escape(str(live.get('generated_at') or '-'))}</p><table><thead><tr><th>代码</th><th>状态</th><th>买入</th><th>结构SL</th><th>结构TP</th><th>信号日</th><th>实际买入时间</th></tr></thead><tbody>{rows}</tbody></table></div>
<p><a href="/monitor" style="color:#58a6ff">当前选股 / 待执行 / 持仓</a>　<a href="/live" style="color:#58a6ff">实时监控与出场</a>　<a href="/backtest" style="color:#58a6ff">V517 冻结回测</a></p></div></body></html>'''
    # FIX(2026-08-18): COMBO 组合策略准生产仪表盘分支（避免 "No backtest data" 报错）
    if _production_registry().get('production_strategy') == 'COMBO_SMC_EVENT':
        registry = _production_registry()
        try:
            combo = json.loads(Path('/root/.hermes/smc_monitor/combo_dashboard.json').read_text(encoding='utf-8'))
        except Exception:
            combo = {}
        paper = combo.get('paper_production') or {}
        yearly = combo.get('yearly') or []
        y_rows = ''.join(
            f"<tr><td>{y.get('year','-')}</td><td>{y.get('n',0)}</td><td>{y.get('wr',0)}%</td>"
            f"<td>{y.get('avg',0):+.2f}%</td><td>{y.get('pf',0):.2f}</td></tr>" for y in yearly)
        # paper holdings detail table (v2: signal/date/trigger/TP/SL/status + kline link)
        try:
            _led = json.loads(Path('/root/.hermes/smc_monitor/paper_ledger.json').read_text(encoding='utf-8'))
            _led.sort(key=lambda t: str(t.get('pick_date', t.get('signal_date', ''))), reverse=True)
            _pos_rows = ''.join(
                f'<tr><td class="mono"><a href="/kline?symbol={html.escape(str(t.get("code",""))) + ".SH" if str(t.get("code","")).startswith("6") else html.escape(str(t.get("code",""))) + ".SZ"}">{html.escape(str(t.get("code","")))}</a></td>'
                f'<td>{html.escape(str(t.get("name","")))}</td>'
                f'<td>{html.escape(str(t.get("signal_combo", t.get("source",""))))}</td>'
                f'<td>{html.escape(str(t.get("signal_date", t.get("disclose_date",""))))}</td>'
                f'<td>{html.escape(str(t.get("pick_date", t.get("created_at","-"))))}</td>'
                f'<td class="mono">{t.get("entry_price",0):.3f}</td>'
                f'<td class="mono" style="color:#3fb950">{t.get("tp_price",0):.3f}</td>'
                f'<td class="mono" style="color:#f85149">{t.get("sl_price",0):.3f}</td>'
                f'<td>{html.escape(str(t.get("status","")))}</td>'
                f'<td>{html.escape(str(t.get("filled_at","-") or "-"))}</td>'
                f'<td style="color:{("#f85149" if (t.get("mark_pnl_pct") or t.get("pnl_pct") or 0) < 0 else "#3fb950")}">{(t.get("mark_pnl_pct") if t.get("status") != "CLOSED" else t.get("pnl_pct")) if t.get("mark_pnl_pct") is not None or t.get("pnl_pct") is not None else "-"}</td></tr>'
                for t in _led if t.get("status") != "CLOSED")
            combo_pos_table = f'<div class="card"><h3>模拟持仓/挂单（{sum(1 for t in _led if t.get("status") != "CLOSED")}）</h3><table><thead><tr><th>代码</th><th>名称</th><th>信号组合</th><th>信号日期</th><th>选股日期</th><th>挂单价</th><th>TP</th><th>SL</th><th>状态</th><th>成交时间</th><th>盈亏</th></tr></thead><tbody>{_pos_rows or "<tr><td colspan=11>无</td></tr>"}</tbody></table><p style="color:#8b949e">点击代码跳转 K 线查看。选股日期=该股票被选股纳入的日期。状态：PENDING_ORDER=挂单中（实时价未达挂单价）/ FILLED=已成交 / OPEN=旧持仓。</p></div>'
        except Exception:
            combo_pos_table = ''
        return f'''<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>SMC 组合策略仪表盘</title><style>{CSS}</style></head><body>{build_nav()}<div class="container">
<div class="card" style="border-left:3px solid #f0883e"><h2>组合策略准生产（纸面跟踪）</h2>
<p>策略：SMC 三周期 TP2-R20（动量）+ 内部人事件增持/回购（事件 alpha）；模式：<b>PAPER_PRODUCTION（纸面，非真实资金）</b>；buy_enabled={html.escape(str(registry.get('buy_enabled')))}。</p>
<p style="color:#8b949e">当前纸面持仓：{paper.get('open_positions',0)}；浮盈：{paper.get('open_avg_mark_pnl',0):+.2f}%（WR {paper.get('open_wr_mark',0)}%）；数据日 {html.escape(str(paper.get('today','')))}；已平仓：{paper.get('closed_trades',0)}。回测年度见下。</p></div>
{combo_pos_table}
<div class="card"><h2>组合回测（每年）</h2><table><thead><tr><th>年</th><th>n</th><th>胜率</th><th>平均收益</th><th>PF</th></tr></thead><tbody>{y_rows or '<tr><td colspan=5>无</td></tr>'}</tbody></table></div>
<p><a href="/combo" style="color:#58a6ff">查看组合完整仪表盘（逐月/当前候选）</a></p></div></body></html>'''
    if _production_empty_book():
        research = v517_frontend.bundle()
        metrics = research.get('metrics') or {}
        scanner = _load_json_dict(Path('/root/.hermes/smc_audit/v700_pure_smc_ssl_reclaim_current_scanner_latest.json'), {})
        shadow = research.get('shadow') or {}
        epoch = (_production_registry().get('data_epoch') or {})
        funnel = scanner.get('diagnostic_funnel') or {}
        funnel_counts = funnel.get('counts') or {}
        funnel_labels = [
            ('fresh_on_committed_epoch', '最新 epoch 有效日K'),
            ('confirmed_swing_low', '当前最近可见未消耗Swing锚点'),
            ('ssl_breach', 'SSL 刺穿≥0.3%'),
            ('sweep_reclaim', 'Sweep 收回摆动低点'),
            ('high_volume_sweep_reclaim', '量能前20日Top20%'),
            ('response_break', '响应收盘突破 Sweep 高点'),
            ('full_current_setup', '完整当前 setup'),
        ]
        funnel_summary = ''.join(
            f'<tr><td>{html.escape(label)}</td><td class="mono">{int(funnel_counts.get(key, 0) or 0)}</td></tr>'
            for key, label in funnel_labels
        )
        partial_rows = list(funnel.get('partial_rows') or [])
        scanner_generated_at = scanner.get('generated_at') or '-'
        scanner_market_date = scanner.get('market_date') or epoch.get('market_date') or '-'
        raw_qs = qs or {}
        def _batch_int(name, default):
            try:
                value = raw_qs.get(name, [default])
                value = value[0] if isinstance(value, list) else value
                return int(value)
            except (TypeError, ValueError):
                return default
        batch_size = _batch_int('obs_size', 100)
        batch_size = batch_size if batch_size in (50, 100, 200, 500) else 100
        batch_total = max(1, (len(partial_rows) + batch_size - 1) // batch_size)
        batch_page = min(max(1, _batch_int('obs_page', 1)), batch_total)
        batch_start = (batch_page - 1) * batch_size
        page_rows = partial_rows[batch_start:batch_start + batch_size]
        def _batch_href(page):
            return f'/?obs_page={page}&obs_size={batch_size}'
        prev_link = (f'<a href="{_batch_href(batch_page - 1)}" style="color:#58a6ff">← 上一批</a>' if batch_page > 1 else '<span style="color:#484f58">← 上一批</span>')
        next_link = (f'<a href="{_batch_href(batch_page + 1)}" style="color:#58a6ff">下一批 →</a>' if batch_page < batch_total else '<span style="color:#484f58">下一批 →</span>')
        batch_controls = (f'<p class="mono">完整名单分批：第 {batch_page}/{batch_total} 批，显示 {batch_start + 1}–{min(batch_start + batch_size, len(partial_rows))} / {len(partial_rows)} 只　{prev_link}　{next_link}　'
                          + '　'.join(f'<a href="/?obs_page=1&obs_size={size}" style="color:#58a6ff">{size}/批</a>' for size in (50, 100, 200, 500)) + '</p>')
        partial_table = ''.join(
            '<tr>'
            f'<td class="mono">{html.escape(str(row.get("symbol") or "-"))}</td>'
            f'<td class="mono">{html.escape(str(row.get("furthest_stage") or "-"))}</td>'
            f'<td class="mono" style="color:#d29922">{html.escape(str(row.get("next_required") or "-"))}</td>'
            f'<td class="mono">{html.escape(str(row.get("swing_date") or "-"))}</td>'
            f'<td class="mono">{html.escape(str(row.get("swing_confirm_date") or "-"))}</td>'
            f'<td class="mono">{html.escape(str(row.get("sweep_date") or "-"))}</td>'
            f'<td class="mono">{html.escape(str(row.get("swing_to_sweep_bars") or "-"))}</td>'
            f'<td class="mono">{html.escape(str(row.get("prior20_volume_rank") or "-"))}</td>'
            '</tr>'
            for row in page_rows
        ) or '<tr><td colspan="8">当前批次没有可见未消耗 Swing 锚点观察行。</td></tr>'
        stage_order = ('CONFIRMED_SWING_LOW', 'SSL_BREACH', 'SWEEP_RECLAIM', 'HIGH_VOLUME_SWEEP_RECLAIM', 'RESPONSE_BREAK', 'FULL_CURRENT_SETUP')
        def reached_at_least(stage):
            return [row for row in partial_rows if stage_order.index(str(row.get('furthest_stage') or 'CONFIRMED_SWING_LOW')) >= stage_order.index(stage)]
        def symbol_list(rows):
            return '　'.join(f'<span class="mono" style="display:inline-block;margin:2px 7px 2px 0">{html.escape(str(row.get("symbol") or "-"))}</span>' for row in rows) or '<span style="color:#8b949e">无</span>'
        confirmed_rows = reached_at_least('CONFIRMED_SWING_LOW')
        breach_rows = reached_at_least('SSL_BREACH')
        reclaim_rows = reached_at_least('SWEEP_RECLAIM')
        reclaim_detail = ''.join(
            '<tr>'
            f'<td class="mono">{html.escape(str(row.get("symbol") or "-"))}</td>'
            f'<td class="mono">{html.escape(str(row.get("swing_date") or "-"))}</td>'
            f'<td class="mono">{html.escape(str(row.get("swing_confirm_date") or "-"))}</td>'
            f'<td class="mono">{html.escape(str(row.get("sweep_date") or "-"))}</td>'
            f'<td class="mono">{html.escape(str(row.get("swing_to_sweep_bars") or "-"))}</td>'
            f'<td class="mono">{html.escape(str(row.get("prior20_volume_rank") or "-"))}</td>'
            f'<td class="mono" style="color:#d29922">{html.escape(str(row.get("next_required") or "-"))}</td>'
            '</tr>'
            for row in reclaim_rows
        ) or '<tr><td colspan="5">无完成 Sweep 收回的当前观察行。</td></tr>'
        return f'''<!doctype html><html lang="zh"><head><meta charset="utf-8"><meta http-equiv="refresh" content="120"><title>SMC 仪表盘</title><style>{CSS}</style></head><body>{build_nav()}<div class="container">
<div class="card" style="border-left:3px solid #d29922"><h2>仪表盘 — EMPTY_BOOK（生产）</h2><p>当前可交易候选 <b>0</b> 只、持仓 <b>0</b> 只。没有通过因果与生产门禁的策略，因此禁止历史回填、watchlist 写入和买入。</p><p style="color:#8b949e">已提交数据 epoch：{html.escape(str(epoch.get('epoch_id') or '-'))}；市场日：{html.escape(_fmt_date_label(epoch.get('market_date')))}；状态：{html.escape(str(epoch.get('status') or '-'))}。页面每 120 秒自动重载。</p></div>
<div class="stats"><div class="stat"><div class="val">{metrics.get('n', 0)}</div><div class="lbl">V517 冻结研究回放</div></div><div class="stat blue"><div class="val">{metrics.get('gross_wr_pct', 0)}%</div><div class="lbl">研究 Gross WR</div></div><div class="stat"><div class="val">{metrics.get('avg_net_pnl_pct', 0):+.2f}%</div><div class="lbl">研究 AvgNet</div></div><div class="stat" style="color:#d29922"><div class="val">{scanner.get('pending_next_open_count', 0)}</div><div class="lbl">当前 epoch 待次日验证</div></div><div class="stat"><div class="val">{len(shadow.get('validations') or [])}</div><div class="lbl">本 epoch shadow 验证</div></div></div>
<div class="card" style="border-left:3px solid #a371f7"><h2>当前 epoch 观察漏斗（每日自动刷新，只读）</h2><p>scanner 本次生成：<span class="mono">{html.escape(str(scanner_generated_at))}</span>；响应市场日：<span class="mono">{html.escape(_fmt_date_label(scanner_market_date))}</span>。表内的 Sweep日是链路前一日的刺穿/收回事件，不等于本次 scanner 的响应日。</p><p>这是与当前已提交行情 epoch 同步的原始 scanner 过程证据，不是选股、挂单或买入建议。所有观察行均为 <span class="mono">RESEARCH_BLOCKED_NOT_EXECUTABLE</span>；完整 setup 即使出现，也会因当前冻结回放门禁失败而禁止进入生产。</p><div class="flex"><div style="flex:0 0 300px"><table><thead><tr><th>当日因果阶段</th><th>数量</th></tr></thead><tbody>{funnel_summary}</tbody></table></div><div style="flex:1"><p>完整当前 setup：<b>{funnel.get('full_current_setup_count', 0)}</b>；研究发布阻断：<span class="mono">{html.escape(str(funnel.get('release_blocker') or '-'))}</span>。</p><p style="color:#8b949e">“下一必需条件”精确说明该股票在本 epoch 未能跨过的下一道因果条件；不是后验业绩筛选，也不读取任何未来收益/退出字段。</p></div></div><div class="card" style="border-left:3px solid #58a6ff;background:#111a2b"><h3>本日结构链路解释与完整名单</h3><p>当前不是底层完全没有结构：<b>{len(confirmed_rows)}</b> 只具有当前最近可见、未被此前触碰消耗的 Swing 锚点；其中 <b>{len(breach_rows)}</b> 只发生 SSL 下扫≥0.3%；其中 <b>{len(reclaim_rows)}</b> 只完成下扫后收回。每行展示 Swing 发生日、右侧确认日、实际 Sweep 日和间隔 bar；锚点规则为“最近的、已确认的、此前未被消耗且被本 Sweep 刺穿收回的 SSL”。该 {len(reclaim_rows)} 只的量能分位为 <b>{html.escape(str(reclaim_rows[0].get('prior20_volume_rank') if reclaim_rows else '-'))}</b>，低于门槛 <b>0.80</b>，所以没有进入响应突破检测；当前完整 setup 为 <b>{funnel.get('full_current_setup_count', 0)}</b>。</p><h4>当前最近可见未消耗 Swing 锚点（共 {len(confirmed_rows)}）— 本批 {len(page_rows)} 只</h4><p>{symbol_list(page_rows)}</p>{batch_controls}<h4>发生 SSL 下扫≥0.3%（{len(breach_rows)}）— 全部代码</h4><p>{symbol_list(breach_rows)}</p><h4>完成下扫后收回（{len(reclaim_rows)}）— 全部代码及卡点</h4><table><thead><tr><th>代码</th><th>摆动日</th><th>确认日</th><th>Sweep日</th><th>Swing→Sweep bar</th><th>前20日量能分位</th><th>下一必需条件</th></tr></thead><tbody>{reclaim_detail}</tbody></table></div><h3>全部当前部分达标观察行（{len(partial_rows)}）</h3><table><thead><tr><th>代码</th><th>已达到最远阶段</th><th>下一必需条件</th><th>Swing日</th><th>确认日</th><th>Sweep日</th><th>Swing→Sweep bar</th><th>前20日量能分位</th></tr></thead><tbody>{partial_table}</tbody></table></div>
<div class="card" style="border-left:3px solid #58a6ff"><h2>量价吸收研究状态（只读）</h2><p>链路：确认摆动低点 → 高量 SSL 刺穿收回 → 次日响应突破 → 后一交易日开盘。当前状态：<b>{html.escape(str(research.get('live_release_state') or '-'))}</b>；决策：{html.escape(str((shadow or {}).get('decision') or '-'))}。</p><p>这不是生产选股；研究回放、当前 scanner、shadow 验证、冻结回测严格分离。</p><p><a href="/effort-result" style="color:#58a6ff">查看研究全量指标/年度分解</a>　<a href="/monitor" style="color:#58a6ff">按时间段查看当前选股与研究历史</a>　<a href="/backtest" style="color:#58a6ff">查看全部冻结回放</a>　<a href="/logs" style="color:#58a6ff">查看每日数据刷新与任务日志</a></p></div>
</div></body></html>'''
    from collections import Counter
    trades = reload_trades()
    picks = get_active_picks()
    pick_contract = get_pick_contract_summary()
    
    if not trades:
        return "<h2>No backtest data. Run engine first.</h2>"

    n = len(trades)
    # Auto-detect engines from data
    engines = list(set(t.get('engine', '?') for t in trades))
    
    report_stats = _active_report_stats('production_A_only')
    if report_stats.get('version') in ('V100', 'V101', 'V102') and report_stats.get('total_trades'):
        n = report_stats['total_trades']
        wr = f"{report_stats['win_rate']:.1f}%"
        avg_pnl = f"{report_stats['avg_pnl']:.2f}%"
        total_pnl = f"{report_stats['total_pnl']:+.1f}%"
        metric_note = f"V100生产A池：选股前置门禁；净胜率=net_pnl≥{report_stats['net_success_threshold_pct']:.1f}%，手续费/滑点={report_stats['fee_pct']:.2f}%，小盈利污染={report_stats['small_profit_pollution_n']}"
    else:
        # V27 uses pnl_pct for win detection (no 'won' field)
        won = sum(1 for t in trades if is_winner(t))
        wr = f"{won/n*100:.1f}%"
        avg_pnl = f"{sum(_float_or_zero(t.get('pnl_pct')) for t in trades)/n:.2f}%"
        total_pnl = f"{sum(_float_or_zero(t.get('pnl_pct')) for t in trades):+.1f}%"
        metric_note = 'legacy gross pnl/win metrics'
    stocks = len(set(t.get('symbol','') for t in trades))
    losses = [t for t in trades if not is_winner(t)]
    wins_list = [t for t in trades if is_winner(t)]
    avg_sl = sum(_float_or_zero(t.get('sl_pct', t.get('sl', 0))) for t in losses) / max(len(losses), 1)
    avg_win = sum(_float_or_zero(t.get('pnl_pct')) for t in wins_list) / max(len(wins_list), 1)
    avg_loss = abs(sum(_float_or_zero(t.get('pnl_pct')) for t in losses) / max(len(losses), 1))
    rr_ratio = avg_win / avg_loss if avg_loss > 0 else 0
    rr = f"{rr_ratio:.2f}x"
    tp1 = sum(1 for t in trades if exit_key(t) == 'TP1_HIT')
    tp2 = sum(1 for t in trades if exit_key(t) == 'TP2_HIT')
    
    # Per-regime stats
    eng_html = ""
    colors = ['#3fb950', '#58a6ff', '#d29922', '#f85149']
    regimes = {}
    for t in trades:
        r = t.get('market_state', t.get('regime', '?'))
        if r not in regimes: regimes[r] = []
        regimes[r].append(t)
    for ei, (reg, rt) in enumerate(sorted(regimes.items())):
        en = len(rt)
        ew = f"{sum(1 for t in rt if is_winner(t))/en*100:.1f}%" if en else "-"
        ep = f"{sum(_float_or_zero(t.get('pnl_pct')) for t in rt)/en:.2f}%" if en else "-"
        ec = colors[ei % len(colors)]
        eng_html += f'''<div class="card" style="flex:1;border-left:3px solid {ec}"><h3>🔹 {reg}</h3><div class="stats">
<div class="stat green"><div class="val">{en:,}</div><div class="lbl">交易</div></div>
<div class="stat blue"><div class="val">{ew}</div><div class="lbl">胜率</div></div>
<div class="stat"><div class="val">{ep}</div><div class="lbl">均盈</div></div></div></div>'''

    # Zone type analysis (V25 uses zone_type instead of context_score)
    ctx_data = {}
    for t in trades:
        score = t.get('zone_type', t.get('context_score', '?'))
        if score not in ctx_data: ctx_data[score] = {'t':0, 'w':0}
        ctx_data[score]['t'] += 1
        if is_winner(t): ctx_data[score]['w'] += 1
    ctx_rows = ""
    for s in sorted(ctx_data.keys(), key=lambda k: -ctx_data[k]['t']):
        c = ctx_data[s]
        ctx_rows += f'<tr><td class=mono>{s}</td><td class=mono>{c["t"]}</td><td class=green>{c["w"]/c["t"]*100:.0f}%</td></tr>'

    pick_rows = ""
    for p in picks[:15]:
        p = _apply_smc_field_contract(p, default_engine=ACTIVE_VERSION)
        sym = p.get('symbol','')
        eng = p.get('zone_type', p.get('engine','?'))
        ec = '#58a6ff'
        seq = p.get('ctx_seq', p.get('detail',''))
        score = p.get('quality_score', p.get('v253_quality', p.get('score', 0)))
        retrace = p.get('retrace_pct', p.get('zone_age', 0))
        combo = p.get('combo_contract_key') or p.get('combo_contract') or '-'
        dna = p.get('dna_preferred_behavior') or p.get('smc_dna') or '-'
        pick_rows += f'<tr><td class=mono><a href="/kline?s={sym}" style="color:var(--blue)">{sym}</a></td>' \
                     f'<td class=mono style="color:{ec}">{str(eng)[:14]}</td>' \
                     f'<td class=mono style="color:#ffd700">{score}</td>' \
                     f'<td class=mono>{retrace}</td>' \
                     f'<td class=mono style="font-size:9px;color:#3fb950">{html.escape(str(dna))[:24]}</td>' \
                     f'<td class=mono style="font-size:9px;color:#d29922">{html.escape(str(combo))[:36]}</td>' \
                     f'<td class=mono style="font-size:9px">{str(seq)[:30]}</td></tr>'
    contract_block = _contract_summary_html(picks, '仪表盘选股 DNA/组合合同同步')
    tradable_count = pick_contract.get('tradable_active_pick_count', 0)
    watch_count = pick_contract.get('watch_only_count', 0)

    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>SMC {FRONTEND_VERSION} Dashboard</title><meta http-equiv="refresh" content="120"><style>{CSS}</style></head><body>
{build_nav()}
<div class="container">
<div class="flex" style="gap:8px;margin-bottom:12px">{eng_html}</div>
<div class="stats">
<div class="stat green"><div class="val">{n:,}</div><div class="lbl">生产A池交易</div></div>
<div class="stat blue"><div class="val">{wr}</div><div class="lbl">净胜率≥0.8%</div></div>
<div class="stat"><div class="val">{avg_pnl}</div><div class="lbl">净均盈</div></div>
<div class="stat"><div class="val">{total_pnl}</div><div class="lbl">净累计PnL</div></div>
<div class="stat"><div class="val">{stocks:,}</div><div class="lbl">股票</div></div>
<div class="stat" style="color:#d29922"><div class="val">{rr}</div><div class="lbl">RR</div></div>
</div>
<div class="card" style="border-left:3px solid #3fb950"><b>指标口径：</b>{metric_note}<br><span class="mono">{report_stats.get('selection_contract','')}</span></div>
<div class="flex">
<div class="card"><h2>🔬 SMC上下文影响力</h2>
<table><thead><tr><th>上下文</th><th>笔数</th><th>胜率</th></tr></thead><tbody>{ctx_rows}</tbody></table></div>
<div class="card"><h2>📡 {FRONTEND_VERSION} 当前选股上下文 Top15 (可交易{tradable_count}只 / 观察{watch_count}只 / 历史{pick_contract['historical_best_count']}只)</h2>
<p style="color:#8b949e;margin-bottom:8px">当前生产语义: Demand OB True Takeover/Reclaim；古典SSL Sweep→CHOCH仅作为独立审计字段，不默认声称</p>
<table><thead><tr><th>代码</th><th>引擎</th><th>S</th><th>回撤</th><th>DNA</th><th>组合合同</th><th>序列</th></tr></thead><tbody>{pick_rows}</tbody></table></div>
</div>{contract_block}</div></body></html>"""


def build_equity_curve_data(trades=None, max_positions=20):
    """Portfolio-aware equity curves. Dates are unique/sorted; trade cumulative is diagnostic only."""
    from collections import defaultdict
    trades = trades if trades is not None else reload_trades()
    clean = []
    for t in trades or []:
        d = _date_key(t.get('exit_date') or t.get('entry_date'))
        if len(d) == 8 and d.isdigit():
            clean.append(t)
    sorted_trades = sorted(clean, key=lambda t: (_date_key(t.get('exit_date') or t.get('entry_date')), _date_key(t.get('entry_date')), t.get('symbol','')))

    trade_cum = []
    cum = 0.0
    step = max(1, len(sorted_trades) // 2000)
    for i, t in enumerate(sorted_trades):
        cum += float(t.get('pnl_pct', 0) or 0)
        if i % step == 0 or i == len(sorted_trades) - 1:
            trade_cum.append([_date_key(t.get('exit_date') or t.get('entry_date')), round(cum, 4)])

    by_day = defaultdict(list)
    for t in sorted_trades:
        by_day[_date_key(t.get('exit_date') or t.get('entry_date'))].append(t)

    daily_equal = []
    capped = []
    eq = 100.0
    eq_cap = 100.0
    daily_returns = []
    capped_returns = []
    for d in sorted(by_day):
        day_trades = by_day[d]
        rets = [float(t.get('pnl_pct', 0) or 0) / 100.0 for t in day_trades]
        daily_r = sum(rets) / len(rets) if rets else 0.0
        eq *= (1.0 + daily_r)
        daily_equal.append([d, round(eq, 4), round(daily_r * 100, 4), len(day_trades)])
        daily_returns.append(daily_r * 100)

        ranked = sorted(day_trades, key=lambda t: float(t.get('quality_score', t.get('score', 0)) or 0), reverse=True)[:max_positions]
        cap_rets = [float(t.get('pnl_pct', 0) or 0) / 100.0 for t in ranked]
        cap_r = sum(cap_rets) / len(cap_rets) if cap_rets else 0.0
        eq_cap *= (1.0 + cap_r)
        capped.append([d, round(eq_cap, 4), round(cap_r * 100, 4), len(ranked)])
        capped_returns.append(cap_r * 100)

    dates = [x[0] for x in daily_equal]
    checks = {
        'curve_dates_unique': len(dates) == len(set(dates)),
        'curve_sorted_by_date': dates == sorted(dates),
        'daily_points': len(daily_equal),
        'trade_count': len(sorted_trades),
        'daily_points_less_than_trade_count': len(daily_equal) < len(sorted_trades) if sorted_trades else True,
        'definition': 'daily_equal_weight_equity default; trade_cumulative_pnl is diagnostic only; portfolio_capped_equity max_positions=%s' % max_positions,
    }
    return {
        'daily_equal_weight_equity': daily_equal,
        'portfolio_capped_equity': capped,
        'trade_cumulative_pnl': trade_cum,
        'checks': checks,
        'daily_return_stats': {
            'min': round(min(daily_returns), 4) if daily_returns else 0,
            'max': round(max(daily_returns), 4) if daily_returns else 0,
            'avg': round(sum(daily_returns)/len(daily_returns), 4) if daily_returns else 0,
        },
        'capped_return_stats': {
            'min': round(min(capped_returns), 4) if capped_returns else 0,
            'max': round(max(capped_returns), 4) if capped_returns else 0,
            'avg': round(sum(capped_returns)/len(capped_returns), 4) if capped_returns else 0,
        }
    }

def _filter_trades_by_window(trades, start='', end='', date_field='entry_date'):
    """Return trades inside [start,end] by entry_date and sorted chronologically."""
    s = _date_key(start)
    e = _date_key(end)
    out = []
    for t in trades or []:
        d = _date_key(t.get(date_field) or t.get('entry_date'))
        if s and d and d < s:
            continue
        if e and d and d > e:
            continue
        out.append(t)
    return sorted(out, key=lambda t: (_date_key(t.get(date_field) or t.get('entry_date')), _date_key(t.get('exit_date')), t.get('symbol','')))


def _v517_rr(t):
    entry, stop, target = (_float_or_zero(t.get(k)) for k in ('entry_price', 'stop', 'target'))
    return (target - entry) / (entry - stop) if entry > stop else 0.0


def _v517_audit_rows(rows, limit=None):
    out = []
    for t in (rows if limit is None else rows[:limit]):
        rr = _v517_rr(t)
        sym = html.escape(str(t.get('symbol') or ''))
        out.append(
            f'<tr><td class=mono><a style="color:#58a6ff" href="/kline?symbol={sym}&ver=V517">{sym}</a></td>'
            f'<td class=mono>{_fmt_date_label(t.get("response_date"))}</td><td class=mono>{_fmt_date_label(t.get("entry_date"))}</td>'
            f'<td class=mono>{_fmt_date_label(t.get("exit_date"))}</td><td class=mono>{_float_or_zero(t.get("entry_price")):.2f}</td>'
            f'<td class=mono style="color:#f85149">{_float_or_zero(t.get("stop")):.2f}</td><td class=mono style="color:#3fb950">{_float_or_zero(t.get("target")):.2f}</td>'
            f'<td class=mono style="color:{"#3fb950" if rr >= 1.5 else "#f85149"}">{rr:.2f}R</td>'
            f'<td>{html.escape(str(t.get("exit_reason") or "-"))}</td><td class=mono style="color:{"#3fb950" if _float_or_zero(t.get("pnl_pct")) > 0 else "#f85149"}">{_float_or_zero(t.get("pnl_pct")):+.2f}%</td>'
            f'<td style="font-size:10px">SSL sweep → 高量收回 → response break → T+1</td></tr>'
        )
    return ''.join(out) or '<tr><td colspan="11">无冻结回放记录</td></tr>'


def _v517_period_metric_table(rows, period_field):
    body = []
    for row in rows or []:
        exits = row.get('exit_counts') or {}
        exit_text = ' / '.join(f'{html.escape(str(k))}:{v}' for k, v in sorted(exits.items()))
        body.append(
            f'<tr><td class="mono">{html.escape(str(row.get(period_field, "-")))}</td>'
            f'<td class="mono">{int(_float_or_zero(row.get("trade_count", row.get("n", 0))))}</td>'
            f'<td class="mono">{_float_or_zero(row.get("gross_wr_pct")):.2f}%</td>'
            f'<td class="mono" style="color:{"#3fb950" if _float_or_zero(row.get("avg_net_pnl_pct")) >= 0 else "#f85149"}">{_float_or_zero(row.get("avg_net_pnl_pct")):+.2f}%</td>'
            f'<td class="mono">{_float_or_zero(row.get("total_net_pnl_pct")):+.2f}%</td>'
            f'<td class="mono">{_float_or_zero(row.get("profit_factor")):.2f}</td>'
            f'<td class="mono">{_float_or_zero(row.get("payoff_rr")):.2f}</td>'
            f'<td class="mono">{int(_float_or_zero(row.get("t1_violation_count")))}</td>'
            f'<td style="font-size:10px">{exit_text or "-"}</td></tr>'
        )
    return ''.join(body) or '<tr><td colspan="9">暂无周期指标</td></tr>'


def build_v517_research_backtest():
    rows = v517_frontend.trades()
    valid_rr = [_v517_rr(t) for t in rows]
    pass_n = sum(r >= 1.5 for r in valid_rr)
    b = v517_frontend.bundle(); m = b.get('metrics') or {}
    yearly_table = _v517_period_metric_table(b.get('yearly') or [], 'entry_year')
    monthly_table = _v517_period_metric_table(b.get('monthly') or [], 'entry_month')
    stability = b.get('monthly_stability') or {}
    median_rr = sorted(valid_rr)[len(valid_rr)//2] if valid_rr else 0
    return f'''<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>V517 冻结研究回测</title><style>{CSS}</style></head><body>{build_nav()}<div class="container">
<div class="card" style="border-left:3px solid #58a6ff"><h2>V517 冻结研究回测（只读 / 非生产）</h2><p>完整冻结严格 T+1 回放，可用于检查信号、入场、结构止损和结构目标；不产生当前选股、watchlist 或买入。</p></div>
<div class="stats"><div class="stat"><div class="val">{len(rows)}</div><div class="lbl">冻结交易</div></div><div class="stat"><div class="val">{m.get('gross_wr_pct','-')}%</div><div class="lbl">Gross WR</div></div><div class="stat"><div class="val">{m.get('avg_net_pnl_pct','-')}%</div><div class="lbl">AvgNet</div></div><div class="stat"><div class="val" style="color:#f85149">{pass_n}/{len(rows)}</div><div class="lbl">结构目标 RR≥1.5</div></div></div>
<div class="card" style="border-left:3px solid #f85149"><h3>风险/目标审计：当前 V517 不满足生产 RR 合同</h3><p>SL 固定为 sweep low × 0.99；TP 为入场前可见的最近 swing high，均属于结构锚点。但 {len(rows)} 笔中仅 {pass_n} 笔（{pass_n / len(rows) * 100 if rows else 0:.2f}%）计划 RR≥1.5；中位数 {median_rr:.2f}R。因此此冻结研究不能以“止盈止损比例合格”的名义晋级生产，不能通过前端补线掩盖。</p></div>
<div class="card"><h3>按年度回测数据</h3><p style="color:#8b949e">全部指标按严格可执行 entry_date 分组；仅用于审计，不可反向作为信号过滤器。</p><table><thead><tr><th>入场年</th><th>交易数</th><th>WR</th><th>AvgNet</th><th>TotalNet</th><th>PF</th><th>Payoff</th><th>T+1违规</th><th>出场构成</th></tr></thead><tbody>{yearly_table}</tbody></table></div>
<div class="card"><h3>按月回测数据（完整）</h3><p style="color:#8b949e">观测月数 {stability.get('months_observed', 0)}；AvgNet 为负月 {stability.get('negative_avg_net_month_count', 0)}：{html.escape(', '.join(stability.get('negative_avg_net_months') or []) or '无')}。月度明细是稳定性审计，不用于事后删月或调参。</p><table><thead><tr><th>入场月</th><th>交易数</th><th>WR</th><th>AvgNet</th><th>TotalNet</th><th>PF</th><th>Payoff</th><th>T+1违规</th><th>出场构成</th></tr></thead><tbody>{monthly_table}</tbody></table></div>
<div class="card"><h3>全部 {len(rows)} 笔冻结回放</h3><table><thead><tr><th>代码</th><th>响应日</th><th>买入日</th><th>卖出日</th><th>入场</th><th>结构SL</th><th>结构TP</th><th>计划RR</th><th>出场</th><th>PnL</th><th>因果组合</th></tr></thead><tbody>{_v517_audit_rows(rows)}</tbody></table></div>
</div></body></html>'''


def build_backtest(start='', end=''):
    from collections import Counter, defaultdict
    if _production_registry().get('production_strategy') == 'COMBO_SMC_EVENT':
        # FIX(2026-08-18): 组合策略回测页（COMBO 状态，避免 No backtest data）
        try:
            combo = json.loads(Path('/root/.hermes/smc_monitor/combo_dashboard.json').read_text(encoding='utf-8'))
        except Exception:
            combo = {}
        yearly = combo.get('yearly') or []
        monthly = combo.get('monthly') or []
        y_rows = ''.join(f"<tr><td>{y.get('year','-')}</td><td>{y.get('n',0)}</td><td>{y.get('wr',0)}%</td><td>{y.get('avg',0):+.2f}%</td><td>{y.get('cum',0):+.1f}%</td><td>{y.get('pf',0):.2f}</td></tr>" for y in yearly)
        m_rows = ''.join(f"<tr><td>{m.get('month','-')}</td><td>{m.get('n',0)}</td><td>{m.get('wr',0)}%</td><td>{m.get('avg',0):+.2f}%</td><td>{m.get('cum',0):+.1f}%</td><td>{m.get('pf',0):.2f}</td></tr>" for m in monthly)
        # FIX(2026-08-20): 逐股回测记录（哪些股票有交易 + 明细，点击跳 K 线）
        stock_rows = ''
        try:
            import csv as _csv
            _bt = []
            with open(r'E:\test\smc_project\research\combo_v20f_trades.csv', encoding='utf-8-sig') as _fh:
                for _r in _csv.DictReader(_fh):
                    _r['net_pnl_pct'] = float(_r.get('net_pnl_pct', 0))
                    _bt.append(_r)
            _by_sym = defaultdict(list)
            for _r in _bt:
                _s = str(_r.get('symbol', ''))
                if '.' not in _s:
                    _s = _s + ('.SH' if _s.startswith(('6', '9')) else '.SZ')
                _by_sym[_s].append(_r['net_pnl_pct'])
            _sym_rows = []
            for _sym, _pnls in sorted(_by_sym.items(), key=lambda kv: -sum(kv[1])):
                _n = len(_pnls)
                _avg = sum(_pnls) / _n
                _win = sum(1 for x in _pnls if x > 0)
                _sym_full = _sym if '.' in _sym else (_sym + '.SH' if _sym.startswith(('6', '9')) else _sym + '.SZ')
                _sym_rows.append(
                    f'<tr><td class="mono"><a href="/kline?symbol={html.escape(_sym_full)}">{html.escape(_sym)}</a></td>'
                    f'<td>{_n}</td><td>{100*_win/_n:.0f}%</td><td>{_avg:+.2f}%</td><td>{sum(_pnls):+.1f}%</td></tr>')
            stock_rows = ''.join(_sym_rows[:200]) or '<tr><td colspan=5>无</td></tr>'
        except Exception as _e:
            stock_rows = f'<tr><td colspan=5>加载失败: {_e}</td></tr>'
        return f'''<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>SMC 组合策略回测</title><style>{CSS}</style></head><body>{build_nav()}<div class="container">
<div class="card" style="border-left:3px solid #3fb950"><h2>组合策略回测（SMC 三周期TP2-R20 + 内部人事件）</h2><p style="color:#8b949e">全市场 {combo.get('total_trades',0)} 笔等权合并池；每年/每月详情。研究级数据，纸面跟踪见 /combo。</p></div>
<div class="card"><h2>逐年</h2><table><thead><tr><th>年</th><th>n</th><th>胜率</th><th>平均收益</th><th>累计</th><th>PF</th></tr></thead><tbody>{y_rows or '<tr><td colspan=6>无</td></tr>'}</tbody></table></div>
<div class="card"><h2>逐月</h2><table><thead><tr><th>月</th><th>n</th><th>胜率</th><th>平均收益</th><th>累计</th><th>PF</th></tr></thead><tbody>{m_rows or '<tr><td colspan=6>无</td></tr>'}</tbody></table></div>
<div class="card"><h2>逐股回测记录（有交易的股票，点击代码查看 K 线买卖点）</h2><table><thead><tr><th>代码</th><th>交易数</th><th>胜率</th><th>平均收益</th><th>累计收益</th></tr></thead><tbody>{stock_rows}</tbody></table><p style="color:#8b949e">按累计收益排序（前 200 只）。点击代码跳转 K 线查看历史交易买卖点/信号/子信号。</p></div>
<p><a href="/combo" style="color:#58a6ff">组合完整仪表盘</a></p></div></body></html>'''
    if _production_empty_book():
        return build_v517_research_backtest()
    trades_all = reload_trades()
    if not trades_all: return "<h2>No backtest data</h2>"
    m = reload_metrics()
    ops = _load_ops_latest()
    latest_data_date = _latest_data_date(ops)
    w_start = _date_key(start) or str(m.get('window_start', '20260101'))
    w_end = _date_key(end) or latest_data_date or str(m.get('window_end', '20260521'))
    trades = _filter_trades_by_window(trades_all, w_start, w_end)
    daily_candidates = _load_json_list(V66_DAILY_CANDIDATES, []) if ACTIVE_VERSION == 'V66' else []
    daily_window = [p for p in daily_candidates if w_start <= _date_key(p.get('entry_date') or p.get('pick_date')) <= w_end]
    daily_note = ''
    if daily_window:
        daily_note = f"<p style='color:#d29922;margin:8px 0'>一致性诊断：当前窗口另有最新日选候选 {len(daily_window)} 只（{', '.join(sorted({p.get('symbol','') for p in daily_window})[:12])}），这些是实时选股候选，尚未形成完整卖出结果，所以不计入历史回测交易数。</p>"
    if not trades:
        return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>SMC {FRONTEND_VERSION} Backtest</title><style>{CSS}</style></head><body>
{build_nav()}<div class="container"><div class="card"><h2>{FRONTEND_VERSION} 回测概览</h2><p style="color:#f85149">当前窗口 {w_start}~{w_end} 没有交易。</p><p style="color:#8b949e">全量文件交易 {len(trades_all)} 笔，当前页面统计和详细列表只按 entry_date 落在窗口内的交易计算。</p>{daily_note}</div></div></body></html>"""

    n = len(trades)
    
    won = sum(1 for t in trades if _float_or_zero(t.get('pnl_pct')) > 0)
    wr = won/n*100 if n else 0
    total_pnl = sum(_float_or_zero(t.get('pnl_pct')) for t in trades)
    avg_pnl = total_pnl/n if n else 0
    stocks = len(set(t.get('symbol','') for t in trades))

    pnls = [_float_or_zero(t.get('pnl_pct')) for t in trades]
    buckets = [('<-10%',sum(1 for p in pnls if p<-10)),('-10~-5%',sum(1 for p in pnls if -10<=p<-5)),
               ('-5~-2%',sum(1 for p in pnls if -5<=p<-2)),('-2~0%',sum(1 for p in pnls if -2<=p<0)),
               ('0~2%',sum(1 for p in pnls if 0<=p<2)),('2~5%',sum(1 for p in pnls if 2<=p<5)),
               ('5~10%',sum(1 for p in pnls if 5<=p<10)),('10~20%',sum(1 for p in pnls if 10<=p<20)),
               ('>20%',sum(1 for p in pnls if p>=20))]
    dist_rows = ''.join(f'<tr><td>{k}</td><td class=mono>{v}</td><td><div class="progress"><div class="progress-bar" style="width:{v/n*100:.1f}%;background:var(--accent)"></div></div></td></tr>' for k,v in buckets)

    exit_types = Counter(exit_key(t) for t in trades)
    exit_names = EXIT_NAMES
    exit_rows = ''.join(f'<tr><td>{exit_names.get(k,k)}</td><td class=mono>{v}</td><td class=mono>{v/n*100:.1f}%</td></tr>' for k,v in exit_types.most_common())

    avg_sl = sum(_float_or_zero(t.get('sl_pct', t.get('sl_initial', 0))) for t in trades) / n if n else 0
    wins_list = [t for t in trades if float(t.get('pnl_pct', 0) or 0) > 0]
    losses_list = [t for t in trades if float(t.get('pnl_pct', 0) or 0) <= 0]
    avg_win = sum(float(t.get('pnl_pct', 0) or 0) for t in wins_list) / max(len(wins_list), 1)
    avg_loss_abs = abs(sum(float(t.get('pnl_pct', 0) or 0) for t in losses_list) / max(len(losses_list), 1))
    rr_ratio = avg_win / avg_loss_abs if avg_loss_abs > 0 else 0
    # Window info for backtest form
    
    # Portfolio-aware equity curve: default chart uses unique sorted dates, not unsorted trade-level sum.
    equity_data = build_equity_curve_data(trades)
    daily_equity_json = json.dumps(equity_data['daily_equal_weight_equity'])
    capped_equity_json = json.dumps(equity_data['portfolio_capped_equity'])
    trade_cum_json = json.dumps(equity_data['trade_cumulative_pnl'])
    equity_checks = equity_data['checks']
    sorted_trades = sorted(trades, key=lambda t: (_date_key(t.get('entry_date')), _date_key(t.get('exit_date')), t.get('symbol','')))
    
    # Complete trade history: no dedup and no truncation. The custom rerun result must
    # correspond 1:1 with the active trade JSON/report, so show every trade and expose
    # exit-leg/plan fields used by the V49 simulator. Rows are rendered from JSON on
    # the client so manual date windows can show the complete list with pagination.
    display_trades = sorted_trades
    trade_rows = ""
    for i, t in enumerate(display_trades):
        pnl = float(t.get('pnl_pct', 0) or 0)
        pnl_color = '#3fb950' if pnl >= 0 else '#f85149'
        exit_r = exit_key(t)
        exit_label = exit_names.get(exit_r, exit_r)
        regime = t.get('market_state', t.get('regime','?'))
        regime_short = {
            'HIGH_VOLATILITY':'HV','RANGING':'RG','RANGE':'RG',
            'STRONG_TREND_UP':'ST','WEAK_TREND_UP':'WT','TREND_UP':'TU',
            'TREND_DOWN':'TD','TRANSITION':'TR'
        }.get(regime, str(regime)[:2] if regime else '?')
        ctx = t.get('ctx_seq','')
        hold = t.get('hold_bars', 0)
        ep = float(t.get('entry_price', 0) or 0)
        risk_pct = float(t.get('risk_pct', 0) or 0)
        rr_realized = pnl / risk_pct if risk_pct else 0
        legs = t.get('exit_legs') or []
        legs_txt = ' | '.join(f"{x.get('reason','')} {float(x.get('weight',0) or 0)*100:.0f}%@{float(x.get('price',0) or 0):.2f}" for x in legs)
        plan = t.get('v49_exit_params') or {}
        plan_txt = ''
        if plan:
            plan_txt = f"TP1 {plan.get('tp1_frac',0)*100:.0f}%@{plan.get('tp1_r')}R / TP2 {plan.get('tp2_frac',0)*100:.0f}%@{plan.get('tp2_r')}R / Trail {plan.get('trail_trigger_r')}R-{plan.get('trail_lock_r')}R"
        else:
            plan_txt = f"RR={t.get('rr','')}"
        signal_txt = f"{t.get('zone_type','')} {t.get('source_event','')} {t.get('conf_type','')}"
        trade_rows += (
            f'<tr><td class=mono>{i+1}</td>'
            f'<td class=mono>{t.get("entry_date","")[:10]}</td>'
            f'<td class=mono>{t.get("exit_date","")[:10]}</td>'
            f'<td class=mono><a href="/kline?s={html.escape(str(t["symbol"]))}" style="color:var(--blue)">{html.escape(str(t["symbol"]))}</a></td>'
            f'<td class=mono>{ep:.3f}</td><td class=mono>{float(t.get("exit_price_final", t.get("exit_price",0)) or 0):.3f}</td>'
            f'<td class=mono style="color:{pnl_color};font-weight:bold">{pnl:+.2f}%</td>'
            f'<td class=mono>{rr_realized:+.2f}R</td><td class=mono>{risk_pct:.2f}%</td>'
            f'<td style="font-size:10px">{html.escape(str(exit_label))}</td><td class=mono>{hold}</td>'
            f'<td style="font-size:9px">{html.escape(signal_txt[:42])}</td>'
            f'<td style="font-size:9px">{html.escape(plan_txt)}</td>'
            f'<td style="font-size:9px">{html.escape(legs_txt[:120])}</td>'
            f'<td class=mono style="font-size:9px">{regime_short}</td>'
            f'</tr>'
        )

    sorted_by_pnl = sorted(trades, key=lambda t: float(t.get('pnl_pct', 0) or 0), reverse=True)
    tail_total = total_pnl if abs(total_pnl) > 1e-9 else 1
    tail_items = []
    for tn in (1, 3, 5, 10, 20, 30):
        val = sum(float(t.get('pnl_pct', 0) or 0) for t in sorted_by_pnl[:tn])
        tail_items.append(f'TOP{tn}: {val:+.1f}% / {val/tail_total*100:.1f}%')
    rr_note = f"盈亏比={rr_ratio:.2f}x；中位PnL={statistics.median(pnls) if pnls else 0:.2f}%；{'；'.join(tail_items)}"

    bt_rows = []
    for i, t in enumerate(display_trades):
        t = _apply_smc_field_contract(t)
        pnl = float(t.get('pnl_pct', 0) or 0)
        risk_pct = float(t.get('risk_pct', 0) or 0)
        plan = t.get('v56_adaptive_tp_plan') or t.get('v55_adaptive_tp_plan') or t.get('v53_exit_params') or t.get('v49_exit_params') or {}
        if t.get('v56_adaptive_tp_plan') or t.get('v55_adaptive_tp_plan'):
            plan_txt = f"自适应TP {plan.get('trend_ctx',{}).get('state','?')} | TP1@{plan.get('tp1_r')}R={t.get('tp1_design_price_v56') or t.get('tp1_design_price_v55')} / TP2@{plan.get('tp2_r')}R={t.get('tp2_design_price_v56') or t.get('tp2_design_price_v55')} / 结构破位runner"
        elif plan:
            plan_txt = f"TP1 {float(plan.get('tp1_frac',0) or 0)*100:.0f}%@{plan.get('tp1_r')}R / TP2 {float(plan.get('tp2_frac',0) or 0)*100:.0f}%@{plan.get('tp2_r')}R / Trail {plan.get('trail_trigger_r')}R-{plan.get('trail_lock_r')}R"
        else:
            plan_txt = f"RR={t.get('rr','')}"
        legs = t.get('exit_legs') or []
        legs_txt = ' | '.join(f"{x.get('reason','')} {float(x.get('weight',0) or 0)*100:.0f}%@{float(x.get('price',0) or 0):.2f}" for x in legs)
        regime = t.get('market_state', t.get('regime','?'))
        regime_short = {
            'HIGH_VOLATILITY':'HV','RANGING':'RG','RANGE':'RG',
            'STRONG_TREND_UP':'ST','WEAK_TREND_UP':'WT','TREND_UP':'TU',
            'TREND_DOWN':'TD','TRANSITION':'TR'
        }.get(regime, str(regime)[:2] if regime else '?')
        bt_rows.append({
            'idx': i + 1,
            'entry_date': str(t.get('entry_date',''))[:10],
            'exit_date': str(t.get('exit_date',''))[:10],
            'select_date': str(t.get('select_date') or t.get('pick_date') or '')[:10],
            'pick_date': str(t.get('pick_date') or '')[:10],
            'join_date': str(t.get('join_date') or '')[:10],
            'trigger_date': str(t.get('signal_date') or t.get('zone_date') or t.get('entry_date',''))[:10],
            'symbol': str(t.get('symbol','')),
            'name': str(t.get('name','')),
            'signal_type': str(t.get('zone_type') or t.get('signal_type') or ''),
            'zone_type': str(t.get('zone_type') or t.get('signal_type') or ''),
            'zone_low': float(t.get('zone_low') or 0),
            'zone_high': float(t.get('zone_high') or 0),
            'cost_line': float(t.get('cost_line') or t.get('smart_money_cost') or 0),
            'volatility_pct': float(t.get('volatility_pct') or 0),
            'signal_price': float(t.get('signal_price') or t.get('zone_high') or t.get('entry_price') or 0),
            'current_price': float(t.get('exit_price_final', t.get('exit_price',0)) or 0),
            'entry_price': float(t.get('entry_price', 0) or 0),
            'exit_price': float(t.get('exit_price_final', t.get('exit_price',0)) or 0),
            'pnl_pct': pnl,
            'realized_r': (pnl / risk_pct if risk_pct else 0),
            'risk_pct': risk_pct,
            'sl': float(t.get('sl') or 0),
            'tp1': float(t.get('tp1_design_price_v56') or t.get('tp1_design_price_v55') or t.get('tp1') or 0),
            'tp2': float(t.get('tp2_design_price_v56') or t.get('tp2_design_price_v55') or t.get('tp2') or 0),
            'score': float(t.get('quality_score') or t.get('score') or 0),
            'score_level': ('A' if float(t.get('quality_score') or t.get('score') or 0) >= 8 else 'B' if float(t.get('quality_score') or t.get('score') or 0) >= 6 else 'C'),
            'exit_label': exit_names.get(exit_key(t), exit_key(t)),
            'hold_bars': t.get('hold_bars', 0),
            'signal': f"{t.get('zone_type','')} {t.get('source_event','')} {t.get('conf_type','')}",
            'dna': str(t.get('dna_preferred_behavior') or t.get('smc_dna') or ''),
            'combo': str(t.get('combo_contract_key') or t.get('combo_contract') or ''),
            'mtf': f"{t.get('weekly_trend_state') or t.get('weekly_state') or ''}/{t.get('daily_structure_state') or t.get('daily_state') or ''}/{t.get('m60_state') or ''}",
            'seq': t.get('seq') or t.get('ctx_seq') or '',
            'plan': plan_txt,
            'legs': legs_txt[:180],
            'regime': regime_short,
        })
    bt_rows_json = json.dumps(bt_rows, ensure_ascii=False)
    contract_block = _contract_summary_html(trades, '回测窗口 DNA/组合合同同步')

    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>SMC {FRONTEND_VERSION} Backtest</title>
<script src="/echarts.js"></script>
<style>{CSS}
#pnl-chart {{ width: 100%; height: 320px; margin: 12px 0; }}
</style></head><body>
{build_nav()}
<div class="container">

<div class="card"><h2>📊 {FRONTEND_VERSION} 回测概览</h2>
<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:10px 0;padding:10px;background:#0d1117;border:1px solid #30363d;border-radius:6px">
  <label style="font-size:12px;color:#8b949e">开始 <input id="bt-start" value="{w_start}" style="background:#161b22;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;padding:4px;width:95px"></label>
  <label style="font-size:12px;color:#8b949e">结束 <input id="bt-end" value="{w_end}" style="background:#161b22;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;padding:4px;width:95px"></label>
  <label style="font-size:12px;color:#8b949e"><input type="checkbox" id="bt-update" checked> 先更新K线</label>
  <button onclick="runBacktest()" id="bt-run" style="background:var(--accent);color:#000;border:0;border-radius:4px;padding:5px 14px;font-weight:bold;cursor:pointer">手工触发回测</button>
<span id="bt-status" style="font-size:12px;color:#8b949e">最新行情日: {w_end} | 当前结果窗口: {w_start}~{w_end}</span>
</div>
<script>
function _bt_id(id){{return document.getElementById(id)}}
async function runBacktest(){{
 var btn=_bt_id("bt-run"),st=_bt_id("bt-status");
 var start=_bt_id("bt-start").value.replace(/-/g,"");
 var end=_bt_id("bt-end").value.replace(/-/g,"");
 var up=_bt_id("bt-update").checked?"1":"0";
 btn.disabled=true;st.textContent="更新/回测中，可能需要几分钟...";
 try{{
  var r=await fetch("/api/backtest/run?start="+encodeURIComponent(start)+"&end="+encodeURIComponent(end)+"&update_kline="+up,{{method:"POST"}});
  var d=await r.json();
  if(d.ok){{st.textContent="完成: "+d.trades+"笔 "+d.stocks+"只 WR="+d.wr+"% 窗口 "+(d.window_start||start)+"~"+(d.window_end||end);location.href='/backtest?start='+encodeURIComponent(start)+'&end='+encodeURIComponent(end);}}
  else{{st.textContent="失败: "+(d.error||JSON.stringify(d));}}
 }}catch(e){{st.textContent="失败: "+e;}}
 btn.disabled=false;
}}
</script>
<div class="flex" style="gap:8px;margin:12px 0">
<div class="stat green"><div class="val">{n:,}</div><div class="lbl">窗口交易</div></div>
<div class="stat blue"><div class="val">{wr:.1f}%</div><div class="lbl">窗口胜率</div></div>
<div class="stat"><div class="val">{avg_pnl:+.2f}%</div><div class="lbl">均盈</div></div>
<div class="stat" style="color:var(--accent)"><div class="val">{total_pnl:+.1f}%</div><div class="lbl">累计PnL</div></div>
<div class="stat"><div class="val">{stocks:,}</div><div class="lbl">股票</div></div>
<div class="stat"><div class="val">{avg_sl:.1f}%</div><div class="lbl">均SL</div></div>
</div>

<p style="color:#8b949e;margin:8px 0">当前页面窗口={w_start}~{w_end}，所有统计、资金曲线、交易笔数、详细列表均只计算 entry_date 落在窗口内的 {n} 笔；全量文件共 {len(trades_all)} 笔。</p>
{daily_note}
<p style="color:#8b949e;margin:8px 0">资金曲线已修复：默认=每日等权组合权益；日期点 {equity_checks['daily_points']} 个 / 窗口交易 {equity_checks['trade_count']} 笔；日期唯一={equity_checks['curve_dates_unique']}；日期排序={equity_checks['curve_sorted_by_date']}。交易级累计只作灰色诊断线。</p>
<p style="color:#d29922;margin:8px 0">{rr_note}</p>
<div id="pnl-chart"></div>
<script>
(function() {{
    var daily = {daily_equity_json};
    var capped = {capped_equity_json};
    var tradeCum = {trade_cum_json};
    var dates = daily.map(function(d) {{ return d[0]; }});
    var values = daily.map(function(d) {{ return d[1]; }});
    var cappedValues = capped.map(function(d) {{ return d[1]; }});
    var tradeDates = tradeCum.map(function(d) {{ return d[0]; }});
    var tradeValues = tradeCum.map(function(d) {{ return d[1]; }});
    var chart = echarts.init(document.getElementById('pnl-chart'));
    chart.setOption({{
        title: {{ text: '每日组合权益曲线 / 交易累计诊断', left: 'center', textStyle: {{ color: '#c9d1d9', fontSize: 14 }} }},
        tooltip: {{ trigger: 'axis' }},
        grid: {{ left: 50, right: 20, top: 40, bottom: 30 }},
        xAxis: {{ type: 'category', data: dates, axisLabel: {{ color: '#8b949e', fontSize: 9, interval: Math.floor(dates.length/10) }} }},
        yAxis: {{ type: 'value', axisLabel: {{ color: '#8b949e', formatter: function(v) {{ return v.toFixed(0); }} }} }},
        series: [
        {{ name:'每日等权权益(100起)', type: 'line', data: values, smooth: false, symbol: 'none',
            lineStyle: {{ color: '#3fb950', width: 2 }},
            areaStyle: {{ color: {{ type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
                colorStops: [{{offset: 0, color: 'rgba(63,185,80,0.25)'}}, {{offset: 1, color: 'rgba(63,185,80,0.02)'}}] }} }}
        }},
        {{ name:'每日最多20只权益', type:'line', data:cappedValues, smooth:false, symbol:'none', lineStyle:{{color:'#58a6ff', width:1.5}} }},
        {{ name:'交易累计诊断(非资金曲线)', type:'line', data:tradeValues, smooth:false, symbol:'none', lineStyle:{{color:'#8b949e', width:1, type:'dashed'}}, xAxisIndex:0 }}
        ]
    }});
}})();
</script>
</div>

<div class="flex" style="gap:8px">
<div class="card" style="flex:1"><h3>PnL 分布</h3><table><thead><tr><th>区间</th><th>笔数</th><th>分布</th></tr></thead><tbody>{dist_rows}</tbody></table></div>
<div class="card" style="flex:1"><h3>出场方式</h3><table><thead><tr><th>方式</th><th>笔数</th><th>占比</th></tr></thead><tbody>{exit_rows}</tbody></table></div>
</div>

<div class="card"><h3>📋 历史交易明细 — 完整 {n} 笔，已与当前回测文件一一对应</h3>
<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px;color:#8b949e;font-size:12px">
  <span id="bt-page-info"></span>
  <button onclick="btPrevPage()" style="background:#21262d;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;padding:3px 10px">上一页</button>
  <button onclick="btNextPage()" style="background:#21262d;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;padding:3px 10px">下一页</button>
  <label>每页 <select id="bt-page-size" onchange="btPage=1;renderBacktestRows()" style="background:#161b22;color:#c9d1d9;border:1px solid #30363d"><option>50</option><option selected>100</option><option>200</option><option>500</option></select></label>
  <span>按当前手工回测窗口完整分页展示，不再截断。</span>
</div>
<div style="max-height:720px;overflow:auto">
<table><thead><tr><th>#</th><th>选股日</th><th>加入日</th><th>触发日</th><th>买入日</th><th>卖出日</th><th>代码</th><th>名称</th><th>信号类型</th><th>Zone</th><th>成本线</th><th>波动</th><th>信号价</th><th>当前/出场价</th><th>入场价</th><th>PnL</th><th>评分</th><th>DNA</th><th>组合合同</th><th>MTF</th><th>SL</th><th>TP1/TP2</th><th>出场</th><th>序列</th><th>设计方案</th><th>逐腿日志</th></tr></thead><tbody id="bt-trade-body"></tbody></table>
</div></div>
{contract_block}
<script>
var BT_ROWS={bt_rows_json};
var btPage=1;
function btEsc(s){{return String(s==null?'':s).replace(/[&<>\"]/g,function(c){{return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c];}})}}
function renderBacktestRows(){{
  var size=parseInt(document.getElementById('bt-page-size').value||'100',10);
  var total=BT_ROWS.length, pages=Math.max(1,Math.ceil(total/size));
  if(btPage<1)btPage=1;if(btPage>pages)btPage=pages;
  var start=(btPage-1)*size, rows=BT_ROWS.slice(start,start+size);
  document.getElementById('bt-page-info').textContent='第 '+btPage+'/'+pages+' 页，本页 '+rows.length+' 笔 / 共 '+total+' 笔';
  document.getElementById('bt-trade-body').innerHTML=rows.map(function(t){{
    var pnl=Number(t.pnl_pct||0), color=pnl>=0?'#3fb950':'#f85149';
    return '<tr><td class=mono>'+t.idx+'</td>'+
      '<td class=mono>'+btEsc(t.select_date||t.pick_date)+'</td><td class=mono>'+btEsc(t.join_date)+'</td><td class=mono>'+btEsc(t.trigger_date)+'</td><td class=mono>'+btEsc(t.entry_date)+'</td><td class=mono>'+btEsc(t.exit_date)+'</td>'+
      '<td class=mono><a href="/kline?s='+encodeURIComponent(t.symbol)+'" style="color:var(--blue)">'+btEsc(t.symbol)+'</a></td><td>'+btEsc(t.name)+'</td>'+
      '<td>'+btEsc(t.signal_type)+'</td><td class=mono>'+((Number(t.zone_low||0)&&Number(t.zone_high||0))?(Number(t.zone_low).toFixed(2)+'~'+Number(t.zone_high).toFixed(2)):'-')+'</td><td class=mono>'+(Number(t.cost_line||0)?Number(t.cost_line).toFixed(2):'-')+'</td><td class=mono>'+(Number(t.volatility_pct||0)?Number(t.volatility_pct).toFixed(1)+'%':'-')+'</td><td class=mono>'+Number(t.signal_price||0).toFixed(3)+'</td><td class=mono>'+Number(t.current_price||0).toFixed(3)+'</td>'+
      '<td class=mono>'+Number(t.entry_price||0).toFixed(3)+'</td><td class=mono style="color:'+color+';font-weight:bold">'+(pnl>=0?'+':'')+pnl.toFixed(2)+'%</td>'+
      '<td class=mono>'+btEsc(t.score_level)+'/'+Number(t.score||0).toFixed(1)+'</td>'+
      '<td class=mono style="font-size:9px;color:#3fb950">'+btEsc(t.dna).slice(0,28)+'</td><td class=mono style="font-size:9px;color:#d29922" title="'+btEsc(t.combo)+'">'+btEsc(t.combo).slice(0,34)+'</td><td class=mono style="font-size:9px">'+btEsc(t.mtf).slice(0,40)+'</td>'+
      '<td class=mono style="color:#f85149">'+Number(t.sl||0).toFixed(3)+'</td>' +
      '<td class=mono style="color:#3fb950">'+Number(t.tp1||0).toFixed(3)+' / '+Number(t.tp2||0).toFixed(3)+'</td>'+
      '<td style="font-size:10px">'+btEsc(t.exit_label)+'</td><td style="font-size:9px">'+btEsc(t.seq).slice(0,80)+'</td>'+
      '<td style="font-size:9px">'+btEsc(t.plan)+'</td><td style="font-size:9px">'+btEsc(t.legs)+'</td></tr>';
  }}).join('');
}}
function btPrevPage(){{btPage--;renderBacktestRows()}}
function btNextPage(){{btPage++;renderBacktestRows()}}
renderBacktestRows();
</script>

</div></body></html>"""


def build_monitor(start='', end=''):
    if _v526_live_production():
        registry = _production_registry()
        strategy = registry.get('production_strategy')
        positions = [p for p in (load_positions() if load_positions else []) if str((p.get('raw_pick') or {}).get('engine') or '') == strategy]
        pending = _load_json_list(Path('/root/.hermes/smc_monitor/v526_pending_orders.json'), [])
        active_pending = [p for p in pending if p.get('status') == 'PENDING_NEXT_OPEN']
        position_rows = ''.join(f'<tr><td class="mono"><a href="/kline?symbol={html.escape(str(p.get("symbol") or ""))}&ver=V517">{html.escape(str(p.get("symbol") or ""))}</a></td><td>{html.escape(str(p.get("status") or ""))}</td><td>{html.escape(str(p.get("pick_date") or ""))}</td><td>{html.escape(str(p.get("filled_at") or "-"))}</td><td class="mono">{p.get("entry_price",0):.3f}</td><td class="mono">{p.get("sl_price",0):.3f}</td><td class="mono">{p.get("tp1_price",0):.3f}</td><td>{html.escape(str(p.get("seq") or ""))}</td></tr>' for p in positions) or '<tr><td colspan="8">无已成交 V526 仓位</td></tr>'
        pending_rows = ''.join(f'<tr><td class="mono">{html.escape(str(p.get("symbol") or ""))}</td><td>{html.escape(str(p.get("response_date") or ""))}</td><td>{html.escape(str(p.get("expected_execution_date") or ""))}</td><td class="mono">{p.get("stop",0):.3f}</td><td class="mono">{p.get("target",0):.3f}</td><td>{html.escape(str(p.get("status") or ""))}</td></tr>' for p in active_pending) or '<tr><td colspan="6">当前无待次日开盘验证信号</td></tr>'
        historical_all = v517_frontend.trades()
        historical_rows = _filter_trades_by_window(historical_all, start, end, date_field='response_date')
        historical_dates = [_date_key(t.get('response_date')) for t in historical_all if _date_key(t.get('response_date'))]
        historical_min, historical_max = (min(historical_dates), max(historical_dates)) if historical_dates else ('', '')
        return f'''<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>V526 当前选股与持仓</title><style>{CSS}</style></head><body>{build_nav()}<div class="container"><div class="card" style="border-left:3px solid #3fb950"><h2>V526 当前生产选股</h2><p>仅展示由最新 committed epoch scanner 产生的候选和真实执行状态；不读取 V66/V88/V185 历史文件。</p></div><div class="card"><h3>待下一交易日开盘验证</h3><table><thead><tr><th>代码</th><th>response 日</th><th>预期开盘日</th><th>结构SL</th><th>结构TP</th><th>状态</th></tr></thead><tbody>{pending_rows}</tbody></table></div><div class="card"><h3>已执行 / 实时监控</h3><table><thead><tr><th>代码</th><th>状态</th><th>信号日</th><th>买入时间</th><th>买入价</th><th>结构SL</th><th>结构TP</th><th>因果组合</th></tr></thead><tbody>{position_rows}</tbody></table></div><div class="card" style="border-left:3px solid #58a6ff"><h2>V517 历史研究选股（{len(historical_rows)}/{len(historical_all)} 笔，只读）</h2><p>冻结因果回放记录，用于逐笔核验 response 日、严格 T+1 入场、结构 SL/TP 与出场；不属于当前候选、不会写入监控或仓位。旧 V88/V185 artifact 请查看 <a href="/historical-artifacts" style="color:#58a6ff">旧系统历史审计</a>。</p><form method="get" action="/monitor" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:10px 0"><label>响应日开始 <input name="start" value="{_date_key(start)}" placeholder="{historical_min}" style="width:100px"></label><label>结束 <input name="end" value="{_date_key(end)}" placeholder="{historical_max}" style="width:100px"></label><button type="submit">按时间过滤</button><a href="/monitor" style="color:#58a6ff">清除过滤</a><span style="color:#8b949e;font-size:12px">范围 {historical_min or '-'} ～ {historical_max or '-'}。</span></form><table><thead><tr><th>代码</th><th>响应日</th><th>买入日</th><th>卖出日</th><th>入场</th><th>结构SL</th><th>结构TP</th><th>计划RR</th><th>出场</th><th>PnL</th><th>组合</th></tr></thead><tbody>{_v517_audit_rows(historical_rows)}</tbody></table></div></div></body></html>'''
    # FIX(2026-08-19): COMBO 组合策略监控页（纸面持仓 + 事件/SMC 候选）
    if _production_registry().get('production_strategy') == 'COMBO_SMC_EVENT':
        freshness_html = _freshness_card()
        try:
            ledger = json.loads(Path('/root/.hermes/smc_monitor/paper_ledger.json').read_text(encoding='utf-8'))
        except Exception:
            ledger = []
        open_pos = [t for t in ledger if t.get('status') != 'CLOSED']
        # sort by rank_score desc (ACCUM+放量 first), then pick_date desc
        open_pos.sort(key=lambda t: (int(t.get('rank_score', 0) or 0), str(t.get('pick_date', t.get('signal_date', '')))), reverse=True)
        def _subs_tt(t):
            subs = t.get('sub_signals') or []
            return ' | '.join(f"S{i+1}{s.get('name','')}({s.get('date','')})" for i, s in enumerate(subs)) if subs else '-'
        pos_rows = ''.join(
            f'<tr><td class="mono"><a href="/kline?symbol={html.escape(str(t.get("code",""))) + ".SH" if str(t.get("code","")).startswith("6") else html.escape(str(t.get("code",""))) + ".SZ"}">{html.escape(str(t.get("code","")))}</a></td>'
            f'<td>{html.escape(str(t.get("name","")))}</td>'
            f'<td>{html.escape(str(t.get("signal_combo", t.get("source",""))))}</td>'
            f'<td>{html.escape(str(t.get("signal_date", t.get("disclose_date",""))))}</td>'
            f'<td>{html.escape(str(t.get("pick_date", t.get("created_at","-"))))}</td>'
            f'<td class="mono">{t.get("entry_price",0):.3f}</td>'
            f'<td class="mono" style="color:#3fb950">{t.get("tp1",0):.3f}</td>'
            f'<td class="mono" style="color:#2ea043">{t.get("tp2",0):.3f}</td>'
            f'<td class="mono" style="color:#1f883d">{t.get("tp3",0):.3f}</td>'
            f'<td class="mono" style="color:#56d364">{t.get("tp4", t.get("tp_price",0)):.3f}</td>'
            f'<td class="mono" style="color:#f85149">{t.get("sl1", t.get("sl_price",0)):.3f}</td>'
            f'<td class="mono" style="color:#ff6b6b">{t.get("sl2",0):.3f}</td>'
            f'<td style="font-size:10px" title="{html.escape(_subs_tt(t))}">{html.escape((_subs_tt(t)[:28] + "…") if len(_subs_tt(t)) > 28 else _subs_tt(t))}</td>'
            f'<td>{html.escape(str(t.get("status","")))}</td>'
            f'<td style="color:{("#f85149" if (t.get("mark_pnl_pct") or 0) < 0 else "#3fb950")}">{t.get("mark_pnl_pct",0):+.2f}%</td></tr>'
            for t in open_pos) or '<tr><td colspan="11">当前无模拟持仓/挂单</td></tr>'
        # recent event candidates (last 3 disclosure days)
        try:
            conn2 = sqlite3.connect(r'E:\test\smc_project\announce\smc_announce.db')
            cur2 = conn2.cursor()
            cur2.execute("SELECT DISTINCT date FROM announce ORDER BY date DESC LIMIT 3")
            recent_days = [r[0] for r in cur2.fetchall()]
            ev_rows_all = ''
            for dd in recent_days:
                cur2.execute("SELECT stock_code, stock_name, title FROM announce WHERE date=? AND (title LIKE '%增持%' OR title LIKE '%回购%') AND title NOT LIKE '%完成%' AND title NOT LIKE '%进度%' AND title NOT LIKE '%前十名%' LIMIT 8", (dd,))
                for code, name, title in cur2.fetchall():
                    ev_rows_all += f'<tr><td>{dd}</td><td class="mono">{html.escape(str(code))}</td><td>{html.escape(str(name))}</td><td>{html.escape(str(title)[:50])}</td></tr>'
            conn2.close()
        except Exception:
            ev_rows_all = '<tr><td colspan="4">公告数据读取失败</td></tr>'
        # SMC candidates from scanner
        try:
            scan = json.load(open(r'E:\test\smc_project\research\current_scanner_result.json', encoding='utf-8'))
        except Exception:
            scan = {}
        smc_rows = ''.join(
            f'<tr><td class="mono">{html.escape(str(c.get("symbol","")))}</td><td>{html.escape(str(c.get("entry_date","")))}</td>'
            f'<td>{html.escape(str(c.get("zone_low","")))}-{html.escape(str(c.get("zone_high","")))}</td>'
            f'<td>{html.escape(str(c.get("target","")))}</td></tr>' for c in (scan.get('smc_candidates') or [])[:15]) or '<tr><td colspan="4" style="color:#8b949e">当前无 SMC 信号候选（稀疏正常）</td></tr>'
        cont_rows = ''.join(
            f'<tr><td class="mono">{html.escape(str(c.get("symbol","")))}</td><td>{html.escape(str(c.get("signal_date","")))}</td>'
            f'<td>{html.escape(str(c.get("entry_date","")))}</td><td class="mono">{c.get("support",0)}</td>'
            f'<td class="mono">{c.get("entry_price",0)}</td><td>10日</td></tr>' for c in (scan.get('continuation_candidates') or [])[:15]) or '<tr><td colspan="6" style="color:#8b949e">当前无延续候选（MARKUP 结构支撑，稀疏正常）</td></tr>'
        # FIX(2026-08-22): 最新选股执行结果（时间/扫描/选入/跳过原因）
        _selr_html = ''
        try:
            _sr = json.load(open(r'E:\test\smc_project\research\selection_result.json', encoding='utf-8'))
            _st = _sr.get('stats') or {}
            # FIX(2026-08-26): 被跳过股票明细
            _sd_rows = ''
            for _d in (_sr.get('skipped_detail') or [])[:20]:
                _sd_rows += f'<tr><td class="mono">{html.escape(str(_d.get("date","")))}</td><td class="mono">{html.escape(str(_d.get("code","")))}</td><td>{html.escape(str(_d.get("name","")))}</td><td>{html.escape(str(_d.get("reason","")))}</td></tr>'
            _sd_html = f'''<details style="margin-top:6px"><summary style="cursor:pointer;color:#58a6ff">查看被跳过股票明细（{len(_sr.get("skipped_detail") or [])} 条，最近 20）</summary>
<table><thead><tr><th>披露日</th><th>代码</th><th>名称</th><th>跳过原因</th></tr></thead><tbody>{_sd_rows or '<tr><td colspan=4>无</td></tr>'}</tbody></table></details>''' if _sr.get('skipped_detail') else ''
            _selr_html = f'''<div class="card" style="border-left:3px solid #58a6ff"><h3>📌 最新选股执行结果（{html.escape(str(_sr.get("selected_at","")))}）</h3>
<table><tr><th>扫描事件</th><th>新增选入</th><th>跳过:重复</th><th>跳过:阶段</th><th>跳过:ADX</th><th>跳过:强市</th><th>跳过:无数据</th></tr>
<tr><td>{_st.get("scanned",0)}</td><td style="color:#3fb950">{_st.get("selected",0)}</td><td>{_st.get("skipped_dup",0)}</td><td>{_st.get("skipped_stage",0)}</td><td>{_st.get("skipped_adx",0)}</td><td>{_st.get("skipped_strong",0)}</td><td>{_st.get("skipped_nodata",0)}</td></tr></table>
{_sd_html}
<p style="color:#8b949e">扫描最近 5 日公告（增持/回购）；跳过原因：阶段不合格(非ACCUM/DOWNTREND)、ADX<20、强市(proxy>2%)、无K线数据、已存在。</p></div>'''
        except Exception:
            _selr_html = ''
        # FIX(2026-08-22): realtime price records (for analysis/review)
        _rt_rows = ''
        try:
            _rt = json.load(open(r'E:\test\smc_project\research\realtime_log.json', encoding='utf-8'))
            _rt = _rt[-30:][::-1]
            _rt_rows = ''.join(
                f"<tr><td class=mono>{html.escape(str(r.get('ts','')))}</td>"
                f"<td class=mono><a href=\"/kline?symbol={html.escape(str(r.get('code',''))) + '.SH' if str(r.get('code','')).startswith('6') else html.escape(str(r.get('code',''))) + '.SZ'}\">{html.escape(str(r.get('code','')))}</a></td>"
                f"<td>{html.escape(str(r.get('name','')))}</td>"
                f"<td class=mono>{r.get('price',0):.2f}</td>"
                f"<td>{html.escape(str(r.get('status','')))}</td>"
                f"<td style=\"color:{('#f85149' if (r.get('mark_pnl_pct') or 0) < 0 else '#3fb950')}\">{r.get('mark_pnl_pct',0):+.2f}%</td></tr>"
                for r in _rt)
        except Exception:
            pass
        return f'''<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>COMBO 当前选股与持仓</title><style>{CSS}</style></head><body>{build_nav()}<div class="container">
<div class="card" style="border-left:3px solid #f0883e"><h2>组合策略 v20f 当前选股与持仓（纸面）</h2><p>策略：SMC（SSL扫损+行为DNA） + 事件（内部人确认）。仅纸面跟踪，非真实资金。</p></div>
{freshness_html}
{_selr_html}
<div class="card"><h3>模拟持仓/挂单（{len(open_pos)}）</h3><table><thead><tr><th>代码</th><th>名称</th><th>信号组合</th><th>信号日期</th><th>选股日期</th><th>挂单价</th><th>TP1<br><span style="font-weight:normal;font-size:10px;color:#8b949e">swing高</span></th><th>TP2<br><span style="font-weight:normal;font-size:10px;color:#8b949e">FVG/次近</span></th><th>TP3<br><span style="font-weight:normal;font-size:10px;color:#8b949e">流动性池</span></th><th>TP4<br><span style="font-weight:normal;font-size:10px;color:#8b949e">60日前高</span></th><th>SL1<br><span style="font-weight:normal;font-size:10px;color:#8b949e">swing低</span></th><th>SL2<br><span style="font-weight:normal;font-size:10px;color:#8b949e">FVG/深层</span></th><th>子信号</th><th>状态</th><th>盈亏</th></tr></thead><tbody>{pos_rows}</tbody></table><p style="color:#8b949e">点击代码跳转 K 线；多指标结构分层：TP1(swing高)→TP2(FVG)→TP3(流动性池)→TP4(60日前高)；SL1(swing低)→SL2(FVG/深层)；触发 TP1 后 SL 移保本，TP2 后锁 TP1 利润。</p></div>
<div class="card"><h3>实时价格记录（最近 30 条，每 30 秒刷新）</h3><table><thead><tr><th>时间</th><th>代码</th><th>名称</th><th>价格</th><th>状态</th><th>浮盈</th></tr></thead><tbody>{_rt_rows or '<tr><td colspan=6>暂无实时记录</td></tr>'}</tbody></table><p style="color:#8b949e">价格每 30 秒刷新并记录到 realtime_log.json，用于复盘分析。</p></div>
<div class="card"><h3>最近事件候选（增持/回购，研究级）</h3><table><thead><tr><th>披露日</th><th>代码</th><th>名称</th><th>标题</th></tr></thead><tbody>{ev_rows_all}</tbody></table></div>
<div class="card"><h3>当前 SMC 候选（三周期信号）</h3><table><thead><tr><th>代码</th><th>入场日</th><th>POI</th><th>目标</th></tr></thead><tbody>{smc_rows}</tbody></table></div>
<div class="card" style="border-left:3px solid #3fb950"><h3>延续候选（MARKUP 结构支撑，固定10日）</h3><table><thead><tr><th>代码</th><th>信号日</th><th>入场日</th><th>支撑</th><th>入场价</th><th>持有</th></tr></thead><tbody>{cont_rows}</tbody></table></div>
</div></body></html>'''
    if _production_empty_book():
        all_rows = v517_frontend.trades()
        rows = _filter_trades_by_window(all_rows, start, end, date_field='response_date')
        all_dates = [_date_key(t.get('response_date')) for t in all_rows if _date_key(t.get('response_date'))]
        min_date, max_date = (min(all_dates), max(all_dates)) if all_dates else ('', '')
        start_value = _date_key(start)
        end_value = _date_key(end)
        epoch = (_production_registry().get('data_epoch') or {})
        # FIX(2026-08-17): EMPTY_BOOK 下也展示每日 scanner 候选（当前 committed epoch 的只读扫描结果），
        # 并提供"汇入今日自动选股"按钮（后端 fail-closed：无 BUY_VALID 则 added=0）。遵守 R18/R21：只显示当前扫描候选、不硬编码数字。
        _scan = _load_json_dict(Path('/root/.hermes/smc_audit/v700_pure_smc_ssl_reclaim_current_scanner_latest.json'), {})
        _scan_rows = _scan.get('rows') or []
        _scan_funnel = (_scan.get('diagnostic_funnel') or {}).get('counts') or {}
        _scan_decision = str(_scan.get('decision') or '-')
        _scan_rows_html = ''
        if _scan_rows:
            _scan_rows_html = ''.join(
                f"<tr><td class=mono>{html.escape(str(r.get('symbol') or ''))}</td>"
                f"<td>{html.escape(str(r.get('response_date') or ''))}</td>"
                f"<td>{html.escape(str(r.get('sweep_low') or ''))}</td>"
                f"<td>{html.escape(str(r.get('stop') or ''))}</td>"
                f"<td>{html.escape(str(r.get('target') or ''))}</td>"
                f"<td>{html.escape(str(r.get('prior20_volume_rank') or ''))}</td>"
                f"<td style='color:#d29922'>{html.escape(str(r.get('state') or 'PENDING_NEXT_OPEN'))}（研究门阻挡）</td></tr>"
                for r in _scan_rows)
        else:
            _scan_rows_html = '<tr><td colspan="7" style="color:#8b949e">当前 epoch 无 PENDING_NEXT_OPEN 候选</td></tr>'
        _funnel_html = '；'.join(f"{k}:{v}" for k, v in _scan_funnel.items()) if _scan_funnel else '-'
        return f'''<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>SMC 选股与历史审计</title><style>{CSS}</style></head><body>{build_nav()}<div class="container">
<div class="card" style="border-left:3px solid #d29922"><h2>当前生产：无有效选股（EMPTY_BOOK）</h2><p>截至当前行情数据日 {html.escape(_fmt_date_label(epoch.get('market_date')))}（epoch：{html.escape(str(epoch.get('epoch_id') or '-'))}），当前可交易 0 只、观察 0 只；<b>当前最新选股日：无</b>。生产扫描按合同未运行（无晋级策略）。禁止历史回填、watchlist 写入和买入。</p></div>
<div class="card" style="border-left:3px solid #58a6ff"><h2>每日选股扫描（V700 当前 scanner）</h2><p style="color:#8b949e">scanner 决策：{html.escape(_scan_decision)}；漏斗：{html.escape(_funnel_html)}。以下候选来自当前 committed epoch 的只读扫描，EMPTY_BOOK 下不可执行（研究门阻挡），仅供查看与核验。</p><button class="reselect-btn" onclick="ingestDaily()">汇入今日自动选股到实时监控</button><span id="manual-status" style="margin-left:8px;color:#8b949e;font-size:12px"></span><table><thead><tr><th>代码</th><th>响应日</th><th>sweep低</th><th>止损</th><th>目标</th><th>量能分位</th><th>状态</th></tr></thead><tbody>{_scan_rows_html}</tbody></table></div>
<div class="card" style="border-left:3px solid #58a6ff"><h2>历史冻结回放档案（非生产、非选股；最后历史 response 日：{max_date or '-'}）</h2><p><b>当前生产最新选股日：无。</b>此处日期仅为冻结研究的最后历史 response 日，不是实时扫描结果，也不能用于买入。全部标记 REPLAY_ONLY，和当前 ACTIVE_CANDIDATE 严格隔离。</p><button id="v517-replay-btn" onclick="runV517Replay()">运行冻结研究回放（只读）</button><span id="v517-replay-status" style="margin-left:8px;color:#8b949e;font-size:12px"></span><form method="get" action="/monitor" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:10px 0"><label>历史响应日开始 <input name="start" value="{start_value}" placeholder="{min_date}" style="width:100px"></label><label>结束 <input name="end" value="{end_value}" placeholder="{max_date}" style="width:100px"></label><button type="submit">按时间过滤</button><a href="/monitor" style="color:#58a6ff">清除过滤</a><span style="color:#8b949e;font-size:12px">冻结研究范围 {min_date or '-'} ～ {max_date or '-'}；不是生产扫描日期。</span></form>
<table><thead><tr><th>代码</th><th>响应日</th><th>买入日</th><th>卖出日</th><th>入场</th><th>结构SL</th><th>结构TP</th><th>计划RR</th><th>出场</th><th>PnL</th><th>组合</th></tr></thead><tbody>{_v517_audit_rows(rows)}</tbody></table></div>
</div><script>
async function ingestDaily() {{
  const st=document.getElementById('manual-status'); st.textContent='汇入中...';
  try {{
    const r=await fetch('/api/monitor/ingest-daily'); const d=await r.json();
    st.textContent=d.ok ? ('新增 '+d.added+' 条 / 买入 '+(d.buy_added||0)+' / 新待次日 '+(d.pending_count||0)+' / 观察 '+(d.validation_only||0)+' / active '+d.active_count+'（EMPTY_BOOK 下无 BUY_VALID 则 0 新增，符合 fail-closed）') : ('失败 '+d.error);
  }} catch(e) {{ st.textContent='失败：'+e; }}
}}
async function runV517Replay() {{
  const btn=document.getElementById('v517-replay-btn'), status=document.getElementById('v517-replay-status');
  btn.disabled=true; status.textContent='回放运行中…';
  try {{
    const r=await fetch('/api/reselect',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:'{{}}'}});
    const d=await r.json();
    status.textContent=d.ok ? ('完成：'+d.trades+'笔；'+(d.production_gate_pass?'生产门禁通过':'生产门禁未通过，保持 EMPTY_BOOK')) : ('失败：'+d.error);
  }} catch(e) {{ status.textContent='失败：'+e; }}
  btn.disabled=false;
}}
</script></body></html>'''
    all_scoped_picks = get_all_picks_scoped()
    pick_contract = get_pick_contract_summary()
    picks = [p for p in all_scoped_picks if p.get('pick_scope') in ('ACTIVE_CANDIDATE', 'WATCH_ONLY')] if ACTIVE_VERSION in ('V88', 'V68') else [p for p in all_scoped_picks if p.get('pick_scope') == 'ACTIVE_CANDIDATE' and p.get('is_active_pick')]
    mon = monitor_state_summary() if monitor_state_summary else {'open':0,'closed':0,'categories':{},'review_count':0}
    positions_all = load_positions() if load_positions else []
    def _monitor_position_engine(pos):
        raw = pos.get('raw_pick') if isinstance(pos.get('raw_pick'), dict) else {}
        return str(raw.get('engine') or pos.get('engine') or '')
    positions = [p for p in positions_all if _monitor_position_engine(p).startswith(ACTIVE_VERSION)]
    mon['open'] = sum(1 for p in positions if p.get('status') == 'OPEN')
    mon['closed'] = sum(1 for p in positions if p.get('status') == 'CLOSED')
    mon['review_count'] = sum(1 for p in positions if p.get('status') == 'CLOSED')
    open_positions = [x for x in positions if x.get('status') == 'OPEN']
    pending_positions = [x for x in positions if x.get('status') == 'NEXT_DAY_PENDING']
    watch_positions = [x for x in positions if x.get('status') == 'WATCH_ONLY']
    monitor_positions = open_positions + pending_positions + watch_positions
    join_dates = {}
    pos_status = {}
    for x in positions:
        k = (x.get('symbol'), _date_key(x.get('pick_date')))
        if k[0] and k[1] and k not in join_dates:
            join_dates[k] = _date_key(x.get('joined_at') or x.get('created_at'))
        if k[0] and k[1] and k not in pos_status:
            pos_status[k] = x.get('status') or ''
    cat_counts = Counter()
    for p in monitor_positions:
        for cat in (p.get('category') or []):
            cat_counts[cat] += 1
    # Normalize V27 picks to frontend-expected field names
    for p in picks:
        if not p.get('price'):
            p['price'] = p.get('last_close', p.get('entry_price', 0))
        if not p.get('dz_low'):
            p['dz_low'] = p.get('zone_low', 0)
        if not p.get('dz_high'):
            p['dz_high'] = p.get('zone_high', 0)
        if not p.get('sl_initial_pct') and p.get('sl', 0) > 0 and p.get('entry_price', 0) > 0:
            p['sl_initial_pct'] = round((p['entry_price'] - p['sl']) / p['entry_price'] * 100, 1)
        if not p.get('tp_tiers') and p.get('tp', 0) > 0 and p.get('entry_price', 0) > 0:
            tp_pct = round((p['tp'] - p['entry_price']) / p['entry_price'] * 100, 1)
            p['tp_tiers'] = [{'pct': tp_pct, 'price': p['tp'], 'type': 'TP'}]
        if not p.get('regime'):
            p['regime'] = 'UNKNOWN'
        if p.get('retrace_pct', 0) == 0 and p.get('entry_price', 0) > 0 and p.get('zone_low', 0) > 0:
            p['retrace_pct'] = round((p['entry_price'] - p['zone_low']) / p['zone_low'] * 100, 1)
    # V46.1 active candidates are already lifecycle-filtered by the engine/watchlist.
    # Do not dedupe by symbol here: multiple active structures on one symbol are
    # separate SMC setups and must not disappear from the选股页.
    if any(p.get('state') for p in picks):
        picks = sorted(picks, key=lambda p: (p.get('pick_date',''), p.get('score', p.get('quality_score',0)), p.get('rr',0)), reverse=True)
    elif ACTIVE_VERSION == 'V68':
        picks = sorted(picks, key=lambda p: (p.get('pick_date',''), p.get('pnl_pct',0), p.get('risk_pct',0)), reverse=True)
    else:
        # Scoped contract: never fallback to historical/all-market picks on monitor.
        picks = [p for p in picks if p.get('pick_scope') == 'ACTIVE_CANDIDATE' and p.get('is_active_pick')]
    
    def build_rows(plist, limit=300):
        rows = ""
        for p in plist[:limit]:
            p = _apply_smc_field_contract(p, default_engine=ACTIVE_VERSION)
            score = p.get('score', p.get('quality_score', 0))
            score_bar = "█" * min(int(score), 15)
            quality = p.get('entry_quality', '')
            engine = p.get('engine', '')
            eng_color = '#3fb950' if engine == 'V13' else '#58a6ff'
            qcolor = '#3fb950' if ('zone内' in quality or 'zone附近' in quality) else ('#d29922' if '趋势' in quality else '#58a6ff')
            seq = p.get('seq', p.get('detail',''))
            def fmt_date(v):
                v = str(v or '')[:8]
                return f"{v[4:6]}-{v[6:8]}" if len(v) == 8 else v
            pick_date = p.get('select_date') or p.get('pick_date') or p.get('entry_date')
            key = (p.get('symbol'), _date_key(pick_date))
            join_date = p.get('join_date') or join_dates.get(key, '')
            monitor_status = pos_status.get(key) or p.get('state') or p.get('pick_scope') or ''
            date_str = fmt_date(p.get('entry_date'))
            pick_date_str = fmt_date(pick_date)
            join_date_str = fmt_date(join_date) or '-'
            seq_dated = f"{seq} ({date_str})" if date_str else seq
            # SL/TP params — prefer V25 dynamic fields, fallback to V24
            if 'v25_sl_pct' in p:
                sl = p.get('v25_sl_pct', 0)
            else:
                sl = p.get('sl_initial_pct', 0)
            tp_raw = p.get('v25_tp_tiers') or p.get('tp_tiers', [])
            if isinstance(tp_raw, list) and len(tp_raw) > 0:
                first = tp_raw[0]
                if isinstance(first, dict):
                    # V29 format: [{'price': 7.78, 'pct': 3.5, 'type': 'TP1 ATR', 'alloc': 0.5}, ...]
                    tp_list = [t.get('pct', 0) for t in tp_raw[:3] if t.get('pct', 0) > 0]
                elif isinstance(first, (list, tuple)):
                    tp_list = [t[2] if isinstance(t, (list,tuple)) and len(t) >= 3 else float(t) if isinstance(t, (int,float)) else 0 for t in tp_raw[:3]]
                elif isinstance(first, (int, float)):
                    tp_list = [float(t) for t in tp_raw[:3]]
                else:
                    tp_list = []
            elif isinstance(tp_raw, str) and tp_raw:
                import re
                tp_list = [float(m.group(1)) for m in re.finditer(r'\(([\d.]+)%\)', tp_raw)]
                if not tp_list:
                    tp_list = [float(x.split('(')[1].replace('%)','').replace('%','')) for x in tp_raw.split(',') if '(' in x]
            else:
                tp_list = []
            tp_str = ','.join(f'{t:.1f}%' for t in tp_list[:3]) if tp_list else '?'
            regime = p.get('regime', '?')
            regime_short = {'HIGH_VOLATILITY':'HV','RANGING':'RG','STRONG_TREND_UP':'ST','WEAK_TREND_UP':'WT'}.get(regime, regime[:2])
            regime_color = {'HV':'#ff6b6b','RG':'#ffd700','ST':'#3fb950','WT':'#58a6ff'}.get(regime_short, '#8b949e')
            
            rows += f'<tr><td class=mono><a href="/kline?s={p["symbol"]}&seq={seq}" style="color:var(--blue)">{p["symbol"]}</a></td>'
            zone_label = p.get('zone_type') or p.get('signal_type') or '-'
            zone_val = (f'{html.escape(str(zone_label))}<br><span style="font-size:9px;color:#8b949e">[{p.get("dz_low",0):.2f}~{p.get("dz_high",0):.2f}]</span>'
                        if p.get('dz_low',0) or p.get('dz_high',0) else html.escape(str(zone_label)))
            cost_line = float(p.get('cost_line') or p.get('smart_money_cost') or p.get('v25_cost_line') or 0)
            volatility_pct = float(p.get('volatility_pct') or p.get('risk_pct') or p.get('v25_sl_pct') or 0)
            rows += f'<td class=mono style="color:{eng_color};font-weight:bold">{engine}</td>'
            rows += f'<td class=mono style="font-size:10px;color:#8b949e">{pick_date_str}</td>'
            rows += f'<td class=mono style="font-size:10px;color:#8b949e">{join_date_str}</td>'
            rows += f'<td class=mono style="color:#ffd700">{int(score)} {score_bar}</td>'
            rows += f'<td style="color:{qcolor};font-weight:bold">{quality}</td>'
            rows += f'<td class=mono>{p.get("retrace_pct",0):+.1f}%</td>'
            rows += f'<td class=mono>{p.get("price",0):.2f}</td>'
            rows += f'<td class=mono>{zone_val}</td>'
            rows += f'<td class=mono style="color:#d29922">{cost_line:.2f}</td>'
            rows += f'<td class=mono style="color:#8b949e">{volatility_pct:.2f}%</td>'
            semantic_layer = p.get('semantic_layer') or 'UNAUDITED'
            semantic_color = '#3fb950' if str(p.get('strict_audit_status')) == 'PASS' else ('#d29922' if str(semantic_layer).startswith(('B_', 'D_')) else '#f85149')
            entry_mode = p.get('entry_mode') or '-'
            rows += f'<td class=mono style="color:{regime_color}">{monitor_status or regime_short}</td>'
            rows += f'<td class=mono style="font-size:9px;color:#3fb950">{html.escape(str(p.get("dna_preferred_behavior") or p.get("smc_dna") or "-").replace("_", " ")[:28])}</td>'
            rows += f'<td class=mono style="font-size:9px;color:#d29922" title="{html.escape(str(p.get("combo_contract_key") or p.get("combo_contract") or ""))}">{html.escape(str(p.get("combo_contract_key") or p.get("combo_contract") or "-")[:32])}</td>'
            rows += f'<td class=mono style="color:{semantic_color};font-size:9px" title="{html.escape(str(p.get("semantic_issues") or ""))}">{html.escape(str(semantic_layer).replace("_", " ")[:28])}</td>'
            rows += f'<td class=mono style="font-size:9px;color:#8b949e">{html.escape(str(entry_mode).replace("_", " ")[:24])}</td>'
            rows += f'<td class=mono style="color:#ff6b6b">SL={sl:.1f}%</td>'
            rows += f'<td class=mono style="color:#3fb950;font-size:9px">TP:{tp_str}</td>'
            rows += f'<td style="font-size:10px">{seq_dated}</td></tr>'
        return rows
    
    rows = build_rows(picks, len(picks) if picks else 300) if picks else '<tr><td colspan="19" style="color:#8b949e;padding:18px">当前无有效 ACTIVE_CANDIDATE；历史最佳 '+str(pick_contract.get('historical_best_count',0))+' 只已从选股页隔离，避免误把全市场历史交易股当作今日选股。最后扫描时间见上方状态栏。</td></tr>'
    contract_block = _contract_summary_html(picks, '选股页 ACTIVE_CANDIDATE DNA/组合合同同步')
    cat_html = ''.join(f'<span class="tag">{k}:{v}</span>' for k,v in sorted(cat_counts.items(), key=lambda x:-x[1])) or '<span class="tag">暂无监控仓位</span>'
    def monitor_pos_row(p):
        raw_pick = p.get('raw_pick') if isinstance(p.get('raw_pick'), dict) else {}
        contracted = _apply_smc_field_contract({**raw_pick, **p}, default_engine=raw_pick.get('engine') or ACTIVE_VERSION)
        pick_d = _date_key(contracted.get('pick_date')) or '-'
        join_d = _date_key(contracted.get('join_date') or p.get('joined_at') or p.get('created_at')) or '-'
        status = p.get('status') or '-'
        status_color = '#d29922' if status == 'NEXT_DAY_PENDING' else ('#8b949e' if status == 'WATCH_ONLY' else '#3fb950')
        reason = p.get('reject_reason') or p.get('pending_reason') or p.get('entry_zone_relation') or ''
        engine = html.escape(str(contracted.get('engine') or raw_pick.get('engine') or p.get('engine') or p.get('source') or ACTIVE_VERSION or '-'))
        zl = _float_or_zero(contracted.get('zone_low'))
        zh = _float_or_zero(contracted.get('zone_high'))
        zone_label = contracted.get('zone_type') or '/'.join(p.get('category') or []) or '-'
        zone_val = f'{html.escape(str(zone_label))}<br><span style="font-size:9px;color:#8b949e">[{zl:.2f}~{zh:.2f}]</span>' if zl and zh else html.escape(str(zone_label))
        return f'<tr><td class=mono><a href="/kline?s={p.get("symbol")}" style="color:var(--blue)">{p.get("symbol")}</a></td><td class=mono>{engine}</td><td class=mono>{pick_d}</td><td class=mono>{join_d}</td><td class=mono style="color:{status_color};font-weight:bold" title="{html.escape(str(reason))}">{status}</td><td>{"/".join(p.get("category") or [])}</td><td class=mono style="font-size:10px;color:#58a6ff">{zone_val}</td><td class=mono>{p.get("entry_price",0)}</td><td class=mono style="color:#ff6b6b">{p.get("sl_price",0)}</td><td class=mono style="color:#3fb950">{p.get("tp1_price",0)}</td><td>{p.get("source")}</td><td>{html.escape(str(reason or p.get("seq","")[:80]))}</td></tr>'
    pos_rows = ''.join(monitor_pos_row(p) for p in monitor_positions[:120]) or '<tr><td colspan="12" style="color:#8b949e">暂无汇入实时监控的OPEN/NEXT_DAY_PENDING/WATCH_ONLY仓位</td></tr>'
    # Dynamic engine counts
    eng_stats = {}
    for p in picks:
        eng = p.get('engine', 'Other')
        eng_stats[eng] = eng_stats.get(eng, 0) + 1
    eng_desc = ' | '.join(f'{eng}:{cnt}只' for eng, cnt in sorted(eng_stats.items(), key=lambda x:-x[1]))
    ts_count = sum(1 for p in picks if p.get('turtle_soup'))
    idm_count = sum(1 for p in picks if p.get('induced'))
    
    latest_data_date = _latest_data_date()
    ops_meta = _ops_scan_meta()
    empty_book = _production_empty_book()
    latest_scan_date = ops_meta.get('latest_scan_date') or latest_data_date
    last_scan_at = ops_meta.get('last_scan_at') or '-'
    latest_pick_date = max([_date_key(p.get('pick_date') or p.get('select_date') or p.get('entry_date')) for p in picks] or [''])
    status_parts = [
        f"数据日期:{_fmt_date_label(latest_data_date) if latest_data_date else '-'}",
        (f"生产扫描:{ops_meta.get('scanner_state')} ({ops_meta.get('scanner_reason')})" if empty_book else f"最后扫描:{html.escape(str(last_scan_at))}"),
        ("扫描行情日:-" if empty_book else f"扫描行情日:{_fmt_date_label(latest_scan_date) if latest_scan_date else '-'}"),
        f"最新候选信号:{_fmt_date_label(latest_pick_date) if latest_pick_date else '-'}",
        f"可交易:{pick_contract['tradable_active_pick_count']}只",
        f"观察:{pick_contract['watch_only_count']}只",
        f"HistoricalBest:{pick_contract['historical_best_count']}只",
        f"RawFile:{pick_contract['raw_pick_file_count']}只",
    ]
    if eng_desc:
        status_parts.append(eng_desc)
    status_parts += [f"TurtleSoup:{ts_count}", f"IDM诱导:{idm_count}"]
    status_line = ' | '.join(status_parts)
    monitor_controls = (
        '<p style="color:#d29922">EMPTY_BOOK：生产写入已锁定，无 BUY_VALID 时汇入返回 0 新增（fail-closed）。</p>'
        '<button class="reselect-btn" onclick="ingestDaily()">汇入今日自动选股到实时监控</button>'
        if empty_book else
        '<button class="reselect-btn" onclick="ingestDaily()">汇入今日自动选股到实时监控</button><div class="manual-box" style="margin-top:10px"><input id="msym" placeholder="代码 600519.SH"><input id="mentry" placeholder="入场价"><input id="msl" placeholder="止损价"><input id="mtp" placeholder="TP1价"><input id="mnote" placeholder="备注"><button class="reselect-btn" onclick="addManual()">手工加入监控</button><span id="manual-status" style="color:#8b949e;margin-left:8px"></span></div>'
    )
    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>SMC 选股</title><style>{CSS}
.hist-btn {{ background: #21262d; color: #c9d1d9; border: 1px solid #30363d; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 11px; margin-left: 4px; }}
.hist-btn:hover {{ background: #30363d; }}
.reselect-btn {{ background: var(--accent); color: #000; border: none; padding: 5px 14px; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: bold; margin-left: 12px; }}
.reselect-btn:hover {{ opacity: 0.85; }}
.reselect-btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
.tag {{ display:inline-block;background:#21262d;border:1px solid #30363d;border-radius:12px;padding:3px 8px;margin:2px;color:#c9d1d9;font-size:11px }}
.manual-box input {{ background:#0d1117;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;padding:6px;margin-right:6px;width:110px }}
#hist-select {{ background: #161b22; color: #c9d1d9; border: 1px solid #30363d; padding: 4px 8px; border-radius: 4px; font-size: 11px; }}
</style></head><body>
{build_nav()}
<div class="container">
<div class="card" style="border-left:3px solid var(--accent)"><h2>🎯 {FRONTEND_VERSION} 当前选股上下文 — 可交易{pick_contract['tradable_active_pick_count']}只 / 观察{pick_contract['watch_only_count']}只
  <button class="reselect-btn" id="reselect-btn" onclick="doReselect()">🔄 运行冻结研究回放</button>
  <select id="hist-select" onchange="loadHistory(this.value)" style="margin-left:8px">
    <option value="">📋 历史记录...</option>
  </select>
  <span id="reselect-status" style="font-size:11px;color:#8b949e;margin-left:8px"></span>
</h2>
<p style="color:#8b949e;margin-bottom:10px">{status_line}</p>
<div class="card" style="background:#0b1220;border-left:3px solid #58a6ff"><h3>每日选股 → 实时监控</h3><p>OPEN:{mon.get('open',0)} | NEXT_DAY_PENDING:{len(pending_positions)} | WATCH_ONLY:{len(watch_positions)} | CLOSED:{mon.get('closed',0)} | 复盘:{mon.get('review_count',0)} | 分类: {cat_html}</p>{monitor_controls}<table style="margin-top:10px"><thead><tr><th>代码</th><th>引擎</th><th>选股日期</th><th>加入日期</th><th>状态</th><th>分类</th><th>Zone</th><th>入场</th><th>SL</th><th>TP1</th><th>来源</th><th>序列/原因</th></tr></thead><tbody>{pos_rows}</tbody></table></div>
<table><thead><tr><th>代码</th><th>引擎</th><th>选股日期</th><th>加入日期</th><th>S</th><th>质量</th><th>回撤</th><th>现价</th><th>Zone</th><th>成本线</th><th>波动</th><th>状态</th><th>DNA</th><th>组合合同</th><th>语义</th><th>入场</th><th>SL</th><th>TP</th><th>序列</th></tr></thead><tbody>{rows}</tbody></table>{contract_block}</div></div>
<script>
async function ingestDaily() {{
    const st = document.getElementById('manual-status'); st.textContent='汇入中...';
    const r = await fetch('/api/monitor/ingest-daily'); const d = await r.json();
    st.textContent = d.ok ? ('新增 '+d.added+' 条 / 买入 '+(d.buy_added||0)+' / 新待次日 '+(d.pending_count||0)+' / 观察 '+(d.validation_only||0)+' / 已在待次日 '+(d.existing_pending_count||0)+' / active '+d.active_count) : ('失败 '+d.error);
    if(d.ok) setTimeout(()=>location.reload(),600);
}}
async function addManual() {{
    const q = new URLSearchParams({{symbol:msym.value, entry:mentry.value, sl:msl.value, tp1:mtp.value, note:mnote.value}});
    const r = await fetch('/api/monitor/manual?'+q.toString()); const d = await r.json();
    document.getElementById('manual-status').textContent = d.ok ? ('已加入 '+d.position.symbol) : ('失败 '+d.error);
    if(d.ok) setTimeout(()=>location.reload(),600);
}}
async function doReselect() {{
    const btn = document.getElementById('reselect-btn');
    const st = document.getElementById('reselect-status');
    btn.disabled = true; st.textContent = '⏳ 重选中...';
    try {{
        const r = await fetch('/api/reselect', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{}})}});
        const d = await r.json();
        if (d.ok) {{
            const gate = d.production_gate_pass ? '生产门禁通过' : '生产门禁未通过，保持 EMPTY_BOOK';
            st.textContent = '✅ 回放完成：'+d.trades+'笔，'+gate+' ('+d.time+'s)';
        }}
        else {{ st.textContent = '❌ '+d.error; }}
    }} catch(e) {{ st.textContent = '❌ '+e; }}
    btn.disabled = false;
}}
async function loadHist() {{
    try {{
        const r = await fetch('/api/history');
        const d = await r.json();
        const sel = document.getElementById('hist-select');
        d.files.forEach(f => {{
            sel.innerHTML += '<option value=\"'+f.date+'\">'+f.label+'</option>';
        }});
    }} catch(e) {{}}
}}
function loadHistory(date) {{
    if (!date) return;
    window.location = '/api/history/load?date='+date;
}}
loadHist();
</script></body></html>"""




def _historical_artifact_rows():
    """Quarantined legacy rows for audit only; never current picks, positions, or production metrics."""
    rows = get_version_trades('V185', lite=False)
    return [{**t, 'audit_scope': 'HISTORICAL_ARTIFACT_ONLY', 'trade_action': 'NOT_CURRENT_PICK'} for t in rows]


def _legacy_audit_rows(rows):
    out = []
    for t in rows:
        sym = html.escape(str(t.get('symbol') or ''))
        entry = _float_or_zero(t.get('entry_price'))
        sl = _float_or_zero(t.get('sl_price') or t.get('stop') or t.get('sl'))
        tp = _float_or_zero(t.get('tp1') or t.get('target') or t.get('tp'))
        rr = (tp - entry) / (entry - sl) if entry > sl and tp else _float_or_zero(t.get('rr'))
        out.append(f'<tr><td class=mono><a style="color:#58a6ff" href="/kline?symbol={sym}&ver=V185">{sym}</a></td><td class=mono>{_fmt_date_label(t.get("pick_date") or t.get("signal_date"))}</td><td class=mono>{_fmt_date_label(t.get("entry_date"))}</td><td class=mono>{_fmt_date_label(t.get("exit_date"))}</td><td>{html.escape(str(t.get("signal_type") or t.get("zone_type") or "-"))}</td><td style="font-size:9px">{html.escape(str(t.get("combo_contract_key") or t.get("combo_contract") or "-"))[:64]}</td><td class=mono>{entry:.2f}</td><td class=mono style="color:#f85149">{sl:.2f}</td><td class=mono style="color:#3fb950">{tp:.2f}</td><td class=mono>{rr:.2f}R</td><td>{html.escape(str(t.get("exit_reason") or "-"))}</td><td class=mono>{_float_or_zero(t.get("pnl_pct")):+.2f}%</td></tr>')
    return ''.join(out) or '<tr><td colspan="12">历史 artifact 不存在</td></tr>'


def build_historical_artifacts():
    rows = _historical_artifact_rows()
    historical_dates = [_date_key(r.get('pick_date') or r.get('signal_date') or r.get('entry_date')) for r in rows]
    latest_historical_date = max((d for d in historical_dates if d), default='')
    return f'''<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>SMC 历史选股审计</title><style>{CSS}</style></head><body>{build_nav()}<div class="container"><div class="card" style="border-left:3px solid #d29922"><h2>历史选股 / 回测 artifact 审计（{len(rows)} 笔，隔离只读）</h2><p>最后历史信号日：{_fmt_date_label(latest_historical_date)}。这不是“当前最新选股日”。</p><p>这些是 V185/V88 同源的历史 artifact，用于检查旧信号、组合、入场与 SL/TP；<b style="color:#f85149">不代表当前策略、不能写入选股/监控/仓位，也不得与 V517 研究指标或生产状态混合。</b></p></div><div class="card"><table><thead><tr><th>代码</th><th>信号日</th><th>买入日</th><th>卖出日</th><th>信号</th><th>历史组合合同</th><th>入场</th><th>SL</th><th>TP</th><th>RR</th><th>出场</th><th>PnL</th></tr></thead><tbody>{_legacy_audit_rows(rows)}</tbody></table></div></div></body></html>'''


def _freshness_card():
    """FIX(2026-08-19/22): 数据新鲜度标注卡片（选股时未更新量 + 实时刷新进度 → 前端展示，复用）"""
    _html = ''
    try:
        # FIX(2026-08-22) P1-3: 数据源健康告警（data_health.json）
        try:
            _dh = json.load(open(r'E:\test\smc_project\research\data_health.json', encoding='utf-8'))
            if _dh.get('alerts'):
                _alerts = '；'.join(_dh['alerts'])
                _html += f'<div style="margin-top:6px;padding:6px;background:#3d1d1d;border:1px solid #f85149;border-radius:4px;color:#f85149">⚠️ 数据告警：{html.escape(_alerts)}</div>'
        except Exception:
            pass
        _scan = json.load(open(r'E:\test\smc_project\research\current_scanner_result.json', encoding='utf-8'))
        _fresh = _scan.get('fresh_count', 0)
        _stale = _scan.get('stale_count', 0)
        _cov = _scan.get('coverage_pct', 0)
        _latest = _scan.get('latest_date', '')
        _sel = {}
        try:
            _sel = json.load(open(r'E:\test\smc_project\research\selection_report.json', encoding='utf-8'))
        except Exception:
            pass
        _clr = '#3fb950' if _stale == 0 else ('#d29922' if _stale < 1000 else '#f85149')
        _deadline = _sel.get('deadline', '09:00')
        _sel_time = _sel.get('selected_at', '')
        _note = '数据已全部更新到最新' if _stale == 0 else f'截止 {_deadline} 选股时未更新 {_stale} 只（覆盖率 {_cov}%），已用当前数据选股，后台继续刷新中'
        # FIX(2026-08-22): realtime incremental refresh progress (incremental_refresh.py writes it)
        _prog_html = ''
        try:
            _prog = json.load(open(r'E:\test\smc_project\research\refresh_progress.json', encoding='utf-8'))
            _pd = int(_prog.get('done', 0))
            _pt = int(_prog.get('total', 1))
            _ppct = min(100.0, float(_prog.get('coverage_pct', 0)))
            _pspeed = _prog.get('speed', 0)
            _peta = _prog.get('eta_min', 0)
            _pcur = _prog.get('current', '')
            _pst = _prog.get('status', 'running')
            _stat_txt = '✅ 全市场数据同步完成' if _pst == 'completed' else ('⏳ 增量刷新中…')
            _prog_html = (f'<div style="margin-top:8px;background:#161b22;border-radius:6px;padding:8px 10px">'
                          f'<p style="margin:0 0 6px;font-size:12px;color:#8b949e">{_stat_txt} '
                          f'<b>{_pd}/{_pt}</b> 只（{_ppct:.1f}%）'
                          f'{" | 当前: " + html.escape(_pcur) if _pcur else ""}'
                          f'{" | 速度 " + str(_pspeed) + "/s" if _pspeed else ""}'
                          f'{" | 预计剩余 " + str(_peta) + " 分钟" if _peta else ""}'
                          f' | 更新于 {_prog.get("updated_at","-")}</p>'
                          f'<div style="background:#30363d;border-radius:4px;height:10px;overflow:hidden">'
                          f'<div style="width:{_ppct}%;height:100%;background:{("#3fb950" if _pst=="completed" else "#58a6ff")};transition:width .5s"></div></div></div>')
        except Exception:
            pass
        _html = f'<div class="card" style="border-left:3px solid {_clr}"><h2>📡 数据新鲜度 / 同步进度</h2><p style="color:#8b949e">最新交易日：<b>{_latest}</b>；已更新：<b>{_fresh}</b> 只；未更新：<b style="color:{_clr}">{_stale}</b> 只（覆盖率 {_cov}%）；选股时间：{_sel_time or "-"}</p><p style="color:{_clr}">{_note}</p>{_prog_html}</div>'
    except Exception:
        pass
    return _html


def build_combo():
    """研究组合策略（SMC 三周期TP2-R20 + 内部人事件）展示页 — 只读研究，不写生产。"""
    try:
        combo = json.loads(Path('/root/.hermes/smc_monitor/combo_dashboard.json').read_text(encoding='utf-8'))
    except Exception:
        combo = {}
    yearly = combo.get('yearly') or []
    monthly = combo.get('monthly') or []
    scan = combo.get('current_scanner') or {}
    events = scan.get('event_candidates') or []
    smc_cands = scan.get('smc_candidates') or []
    y_rows = ''.join(
        f"<tr><td>{y.get('year','-')}</td><td>{y.get('n',0)}</td><td>{y.get('wr',0)}%</td>"
        f"<td>{y.get('avg',0):+.2f}%</td><td>{y.get('cum',0):+.1f}%</td><td>{y.get('pf',0):.2f}</td></tr>"
        for y in yearly)
    m_rows = ''.join(
        f"<tr><td>{m.get('month','-')}</td><td>{m.get('n',0)}</td><td>{m.get('wr',0)}%</td>"
        f"<td>{m.get('avg',0):+.2f}%</td><td>{m.get('cum',0):+.1f}%</td><td>{m.get('pf',0):.2f}</td></tr>"
        for m in monthly)
    ev_rows = ''.join(
        f"<tr><td>{html.escape(str(e.get('date','')))}</td><td class=mono>{html.escape(str(e.get('code','')))}</td>"
        f"<td>{html.escape(str(e.get('name','')))}</td><td>{html.escape(str(e.get('title','')))}</td></tr>"
        for e in events[:30])
    smc_rows = ''.join(
        f"<tr><td class=mono>{html.escape(str(c.get('symbol','')))}</td><td>{html.escape(str(c.get('entry_date','')))}</td>"
        f"<td>{html.escape(str(c.get('zone_low','')))}-{html.escape(str(c.get('zone_high','')))}</td>"
        f"<td>{html.escape(str(c.get('target','')))}</td></tr>"
        for c in smc_cands[:20])
    total = combo.get('total_trades', 0)
    paper = combo.get('paper_production') or {}
    # FIX(2026-08-19/22): 数据新鲜度标注（选股时未更新量 → 前端展示）
    freshness_html = _freshness_card()
    # sim holdings table (v2: signal/date/trigger/TP/SL/status + kline link)
    sim_table = ''
    try:
        _sled = json.loads(Path('/root/.hermes/smc_monitor/paper_ledger.json').read_text(encoding='utf-8'))
        _active = [t for t in _sled if t.get('status') != 'CLOSED']
        _active.sort(key=lambda t: (int(t.get('rank_score', 0) or 0), str(t.get('pick_date', t.get('signal_date', '')))), reverse=True)
        def _subs_tt_combo(t):
            subs = t.get('sub_signals') or []
            return ' | '.join(f"S{i+1}{s.get('name','')}({s.get('date','')})" for i, s in enumerate(subs)) if subs else '-'
        _sim_rows = ''.join(
            f'<tr><td class="mono"><a href="/kline?symbol={html.escape(str(t.get("code",""))) + ".SH" if str(t.get("code","")).startswith("6") else html.escape(str(t.get("code",""))) + ".SZ"}">{html.escape(str(t.get("code","")))}</a></td>'
            f'<td>{html.escape(str(t.get("name","")))}</td>'
            f'<td>{html.escape(str(t.get("signal_combo", t.get("source",""))))}</td>'
            f'<td>{html.escape(str(t.get("signal_date", t.get("disclose_date",""))))}</td>'
            f'<td>{html.escape(str(t.get("pick_date", t.get("created_at","-"))))}</td>'
            f'<td>{html.escape(str(t.get("stage", t.get("signal_combo", ""))))}{" +放量" if (t.get("v_ratio") or 0) > 1.2 else ""}</td>'
            f'<td style="font-size:9px;color:#bc8cff" title="{html.escape(_subs_tt_combo(t))}">{html.escape(_subs_tt_combo(t)[:20] + "…") if len(_subs_tt_combo(t)) > 20 else html.escape(_subs_tt_combo(t))}</td>'
            f'<td class="mono">{t.get("entry_price",0):.3f}</td>'
            f'<td class="mono" style="color:#3fb950">{t.get("tp1",0):.3f}</td>'
            f'<td class="mono" style="color:#2ea043">{t.get("tp2",0):.3f}</td>'
            f'<td class="mono" style="color:#1f883d">{t.get("tp3",0):.3f}</td>'
            f'<td class="mono" style="color:#56d364">{t.get("tp4", t.get("tp_price",0)):.3f}</td>'
            f'<td class="mono" style="color:#f85149">{t.get("sl1", t.get("sl_price",0)):.3f}</td>'
            f'<td class="mono" style="color:#ff6b6b">{t.get("sl2",0):.3f}</td>'
            f'<td>{html.escape(str(t.get("status","")))}</td>'
            f'<td>{html.escape(str(t.get("trigger",""))[:24])}</td>'
            f'<td style="color:{("#f85149" if (t.get("mark_pnl_pct") or 0) < 0 else "#3fb950")}">{t.get("mark_pnl_pct",0):+.2f}%</td></tr>'
            for t in _active)
        sim_table = f'<div class="card"><h2>模拟持仓/挂单（{len(_active)}）</h2><table><thead><tr><th>代码</th><th>名称</th><th>信号组合</th><th>信号日期</th><th>选股日期</th><th>阶段/量能</th><th>子信号</th><th>买入价</th><th>TP1<br><span style="font-weight:normal;font-size:9px;color:#8b949e">swing高</span></th><th>TP2<br><span style="font-weight:normal;font-size:9px;color:#8b949e">FVG/次近</span></th><th>TP3<br><span style="font-weight:normal;font-size:9px;color:#8b949e">流动性池</span></th><th>TP4<br><span style="font-weight:normal;font-size:9px;color:#8b949e">60日前高</span></th><th>SL1<br><span style="font-weight:normal;font-size:9px;color:#8b949e">swing低</span></th><th>SL2<br><span style="font-weight:normal;font-size:9px;color:#8b949e">FVG/深层</span></th><th>状态</th><th>触发条件</th><th>盈亏</th></tr></thead><tbody>{_sim_rows or "<tr><td colspan=16>无</td></tr>"}</tbody></table><p style="color:#8b949e">点击代码跳转 K 线；分层止盈：TP1(swing高)→TP2(FVG)→TP3(流动性)→TP4(60日前高)；SL1(swing低)→SL2(FVG/深层)；阶段=ACCUM/DOWNTREND，+放量=大资金响应；子信号悬停查看链。</p></div>'
    except Exception:
        sim_table = ''
    paper_html = ''
    if paper:
        paper_html = f'''<div class="card" style="border-left:3px solid #f0883e"><h2>准生产状态（纸面跟踪）</h2>
<p style="color:#8b949e">状态：<b>{html.escape(str(paper.get('status','')))}</b>；BUY_VALID（纸面）：{paper.get('buy_valid_count',0)}；持仓：{paper.get('open_positions',0)}；已平仓：{paper.get('closed_trades',0)}；平仓胜率：{paper.get('closed_wr',0)}%；平仓均收益：{paper.get('closed_avg_pnl',0):+.2f}%</p>
<p style="color:#d29922">当前持仓浮盈：{paper.get('open_avg_mark_pnl',0):+.2f}%（浮盈胜率 {paper.get('open_wr_mark',0)}%）；数据日：{html.escape(str(paper.get('today','')))}；仅纸面跟踪，不涉及真实资金。</p></div>'''
    return f'''<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>研究组合策略</title><style>{CSS}</style></head><body>{build_nav()}<div class="container">
<div class="card" style="border-left:3px solid #3fb950"><h2>研究组合策略 v20c（反转 + 延续双方向）</h2>
<p style="color:#8b949e">全市场 {total} 笔等权合并池；反转（SMC扫损+事件底部）+ 延续（MARKUP结构支撑）→ 每年均衡。策略：事件反转 66.7% + 延续 31.8% + SMC 1.5%。</p></div>
{paper_html}
{freshness_html}
{sim_table}
<div class="card"><h2>逐年</h2><table><thead><tr><th>年</th><th>n</th><th>胜率</th><th>平均收益</th><th>累计</th><th>PF</th></tr></thead><tbody>{y_rows}</tbody></table></div>
<div class="card"><h2>逐月</h2><table><thead><tr><th>月</th><th>n</th><th>胜率</th><th>平均收益</th><th>累计</th><th>PF</th></tr></thead><tbody>{m_rows}</tbody></table></div>
<div class="card"><h2>当前事件候选（增持/回购，最近 3 个交易日，研究级）</h2><table><thead><tr><th>披露日</th><th>代码</th><th>名称</th><th>标题</th></tr></thead><tbody>{ev_rows or '<tr><td colspan=4 style="color:#8b949e">无</td></tr>'}</tbody></table></div>
<div class="card"><h2>当前 SMC 候选（三周期信号）</h2><table><thead><tr><th>代码</th><th>入场日</th><th>POI区间</th><th>目标</th></tr></thead><tbody>{smc_rows or '<tr><td colspan=4 style="color:#8b949e">无（信号稀疏属正常）</td></tr>'}</tbody></table></div>
</div></body></html>'''


def build_nav():
    if _production_empty_book():
        # FIX(2026-08-17): K线入口不再锁死 V517；EMPTY_BOOK 下由用户自由选择研究版本。
        return f"<nav><span class='brand'>SMC {FRONTEND_VERSION}</span><a href='/'>仪表</a><a href='/kline'>K线</a><a href='/backtest'>冻结研究回测</a><a href='/monitor'>生产状态 / 冻结研究</a><a href='/combo'>研究组合</a><a href='/historical-artifacts'>旧系统历史审计</a><a href='/live'>实时</a><a href='/logs'>日志</a><a href='/compare'>对比</a><a href='/analysis'>分析</a><a href='/autopsy'>复盘</a><a href='/stoploss'>止损</a><a href='/resonance'>共振</a><a href='/effort-result'>V517量价吸收研究</a><a href='/docs'>文档</a></nav>"
    return f"<nav><span class='brand'>SMC {FRONTEND_VERSION}</span><a href='/'>仪表</a><a href='/kline'>K线</a><a href='/backtest'>回测</a><a href='/monitor'>选股</a><a href='/historical-artifacts'>旧系统历史审计</a><a href='/live'>实时</a><a href='/uzi'>UZI评审</a><a href='/logs'>日志</a><a href='/compare'>对比</a><a href='/analysis'>分析</a><a href='/autopsy'>复盘</a><a href='/stoploss'>止损</a><a href='/v45?ver=v45_5'>事件实验({FRONTEND_VERSION})</a><a href='/resonance'>共振</a><a href='/effort-result'>V517量价吸收</a><a href='/docs'>文档</a></nav>"


def _empty_book_page(title, detail):
    """Production-only pages must not render quarantined historical artifacts."""
    registry = _production_registry()
    epoch = registry.get('data_epoch') or {}
    research = v517_frontend.bundle()
    metrics = research.get('metrics') or {}
    return f'''<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>{html.escape(title)}</title><style>{CSS}</style></head><body>{build_nav()}<div class="container">
<div class="card" style="border-left:3px solid #d29922"><h2>{html.escape(title)} — EMPTY_BOOK</h2><p>{html.escape(detail)}</p><p style="color:#8b949e">数据 epoch：{html.escape(str(epoch.get('epoch_id') or '-'))}；市场日：{html.escape(_fmt_date_label(epoch.get('market_date')))}；状态：{html.escape(str(epoch.get('status') or '-'))}。</p><p style="color:#d29922">没有获生产晋级的策略；不得读取 V88/V185 或其它历史 artifacts 作为当前交易、分析或复盘数据。</p></div>
<div class="card" style="border-left:3px solid #58a6ff"><h2>研究与历史审计入口</h2><p><a href="/backtest" style="color:#58a6ff">V517 冻结研究回测</a>　<a href="/monitor" style="color:#58a6ff">当前选股与V517研究历史</a>　<a href="/historical-artifacts" style="color:#58a6ff">旧系统历史选股审计</a></p><p style="color:#8b949e">当前生产仍为 EMPTY_BOOK：历史和研究数据仅用于核验，不会写入实时监控、仓位或买入指令。</p></div>
</div></body></html>'''


def _load_ops_latest():
    return _load_json_dict(Path('/root/.hermes/smc_monitor/ops_latest.json'), {})


def _v526_log_snapshot():
    """Current V526 controller state; never render stale legacy ops as production."""
    registry = _production_registry()
    scanner = _load_json_dict(Path('/root/.hermes/smc_audit/v700_pure_smc_ssl_reclaim_current_scanner_latest.json'), {})
    release = _load_json_dict(Path('/root/.hermes/smc_audit/v522_effort_result_release_audit_latest.json'), {})
    state = _v526_state()
    pending = _load_json_list(Path('/root/.hermes/smc_monitor/v526_pending_orders.json'), [])
    strategy = registry.get('production_strategy')
    positions = [p for p in (load_positions() if load_positions else []) if str((p.get('raw_pick') or {}).get('engine') or '') == strategy]
    cron_path = Path('/etc/cron.d/smc-v526-live-execution')
    try:
        cron_lines = [line.strip() for line in cron_path.read_text().splitlines()
                      if line.strip() and not line.lstrip().startswith('#')]
    except Exception:
        cron_lines = []
    return {
        'production_state': registry.get('state'),
        'production_strategy': strategy,
        'buy_enabled': registry.get('buy_enabled') is True,
        'data_epoch': registry.get('data_epoch') or {},
        'scanner': scanner,
        'release': release,
        'execution': state,
        'pending_next_open_count': sum(p.get('status') == 'PENDING_NEXT_OPEN' for p in pending),
        'open_position_count': sum(p.get('status') == 'OPEN' for p in positions),
        'cron_lines': cron_lines,
    }


def _latest_data_date(ops=None):
    ops = ops if ops is not None else _load_ops_latest()
    vals = []
    refresh = (ops.get('kline_refresh') or {}) if isinstance(ops, dict) else {}
    latest_counts = refresh.get('latest_counts') or (refresh.get('summary') or {}).get('latest_counts') or {}
    vals += [_date_key(k) for k in latest_counts.keys()]
    vals += [_date_key(v) for v in [
        ((ops.get('daily_scan_merge') or {}).get('latest_scan_date') if isinstance(ops, dict) else ''),
        (ops.get('data_date') if isinstance(ops, dict) else ''),
    ]]
    try:
        rep = _load_json_dict(V90_DIR / 'v90_daily_scan_report.json', {})
        vals.append(_date_key(rep.get('latest_market_date') or rep.get('latest_date')))
    except Exception:
        pass
    vals = [v for v in vals if len(v) == 8 and v.isdigit()]
    return max(vals) if vals else ''


def _fmt_date_label(v):
    s = _date_key(v)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else (str(v or '-') or '-')


def _ops_scan_meta(ops=None):
    ops = ops if ops is not None else _load_ops_latest()
    if not isinstance(ops, dict):
        ops = {}
    scan = ops.get('daily_scan') or {}
    merge = ops.get('daily_scan_merge') or {}
    refresh = ops.get('kline_refresh') or {}
    refresh_summary = refresh.get('summary') or {}
    registry = _production_registry()
    if _production_empty_book():
        epoch = _current_committed_data_epoch(registry.get('data_epoch') or {})
        # EMPTY_BOOK disables admission, not observability. V521 is a current,
        # outcome-blind scanner snapshot and must remain visible even when no
        # production strategy is licensed.
        current = _load_json_dict(Path('/root/.hermes/smc_audit/v700_pure_smc_ssl_reclaim_current_scanner_latest.json'), {})
        counts = ((current.get('diagnostic_funnel') or {}).get('counts') or {})
        return {
            'data_date': _date_key(epoch.get('market_date')) or _latest_data_date(ops),
            'latest_scan_date': _date_key(current.get('market_date')),
            'last_scan_at': current.get('generated_at', ''),
            'ops_generated_at': '',
            'scan_returncode': 0 if current else '',
            'scan_duration_sec': '',
            'kline_ok': '',
            'kline_failed': '',
            'scanner_state': 'CURRENT_SCANNER_RAN_NO_PRODUCTION_ADMISSION',
            'scanner_reason': current.get('decision') or 'CURRENT_SCANNER_ARTIFACT_UNAVAILABLE',
            'scanner_funnel': counts,
            'scanner_pending_next_open_count': current.get('pending_next_open_count', 0),
            'scanner_buy_valid_count': current.get('buy_valid_count', 0),
        }
    scanner_dates = []
    scanner_runs = []
    for path in (V100_DIR / 'v100_report.json', V99_DIR / 'v99_report.json', V98_DIR / 'v98_report.json', V97_DIR / 'v97_report.json', V91_DIR / 'v91_shadow_scan_report.json', V90_DIR / 'v90_daily_scan_report.json'):
        try:
            if path.exists():
                rep = json.loads(path.read_text()) or {}
                scanner_dates.append(_date_key(rep.get('latest_market_date') or rep.get('latest_date')))
                if rep.get('run_at') or rep.get('generated_at'):
                    scanner_runs.append(str(rep.get('run_at') or rep.get('generated_at')))
        except Exception:
            pass
    scanner_latest_date = max([d for d in scanner_dates if d], default='')
    scanner_last_run = max(scanner_runs, default='')
    return {
        'data_date': scanner_latest_date or ops.get('data_date') or (ops.get('pick_diagnostics') or {}).get('data_date') or merge.get('latest_scan_date') or _latest_data_date(ops),
        'latest_scan_date': scanner_latest_date or merge.get('latest_scan_date') or ops.get('data_date') or _latest_data_date(ops),
        'last_scan_at': scanner_last_run or scan.get('finished_at') or merge.get('finished_at') or ops.get('generated_at') or '',
        'ops_generated_at': ops.get('generated_at') or '',
        'scan_returncode': scan.get('returncode', ''),
        'scan_duration_sec': scan.get('duration_sec', ''),
        'kline_ok': refresh_summary.get('ok', ''),
        'kline_failed': refresh_summary.get('failed', ''),
    }


def build_logs():
    if _v526_live_production():
        log = _v526_log_snapshot()
        epoch = log['data_epoch']
        scanner = log['scanner']
        release = log['release']
        execution = log['execution']
        def cell(value):
            return html.escape(str(value if value not in (None, '') else '-'))
        rows = [
            ('生产注册表', epoch.get('epoch_id'), log['production_state'], log['production_strategy']),
            ('V521 当前 epoch scanner', scanner.get('generated_at'), scanner.get('pending_next_open_count'), scanner.get('decision')),
            ('V522 production license', release.get('generated_at'), release.get('production_license_state'), release.get('decision')),
            ('V526 最近执行器', execution.get('generated_at'), execution.get('mode'), f"checked={execution.get('checked', 0)}"),
            ('待下一交易日开盘验证', epoch.get('market_date'), log['pending_next_open_count'], '仅 current scanner durable pending rows'),
            ('当前 V526 持仓', execution.get('generated_at'), log['open_position_count'], '仅 BUY_VALID 后真实仓位'),
        ]
        table = ''.join(f'<tr><td>{cell(name)}</td><td class="mono">{cell(at)}</td><td>{cell(count)}</td><td style="font-size:10px">{cell(detail)}</td></tr>' for name, at, count, detail in rows)
        cron = '<br>'.join(cell(line) for line in log['cron_lines']) or '未配置'
        return f'''<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>V526 运行日志</title><meta http-equiv="refresh" content="120"><style>{CSS}</style></head><body>{build_nav()}<div class="container">
<div class="card" style="border-left:3px solid #3fb950"><h2>运行日志 — V526 已获生产许可</h2><p>只展示当前 V526/V517 epoch、执行器与严格 T+1 状态；不读取陈旧的 V66/V88/V185 或 EMPTY_BOOK ops 日志。</p><p style="color:#8b949e">生产状态：{cell(log['production_state'])}；买入开关：{cell(log['buy_enabled'])}；定时任务：<br><span class="mono">{cron}</span></p></div>
<div class="card"><h2>当前链路状态</h2><table><thead><tr><th>阶段</th><th>时间 / epoch</th><th>数量 / 状态</th><th>结论</th></tr></thead><tbody>{table}</tbody></table></div>
<div class="card"><h2>执行语义</h2><p>18:10 刷新日线、验证 shadow、扫描当前 committed epoch 并持久化 PENDING_NEXT_OPEN；09:31 仅在预期下一交易日的真实开盘价位于结构 SL 与 TP 之间时生成 BUY_VALID；盘中每 5 分钟仅监控 V526 OPEN 仓位，且买入当日禁止卖出。</p></div>
</div></body></html>'''
    if _production_empty_book():
        research = v517_frontend.artifacts()
        seed = research.get('seed') or {}
        replay = research.get('replay') or {}
        scanner = research.get('scanner') or {}
        release = research.get('release') or {}
        shadow = research.get('shadow') or {}
        epoch = (_production_registry().get('data_epoch') or {})
        cron_path = Path('/etc/cron.d/smc-v54-daily-picks')
        try:
            cron_line = next((line.strip() for line in cron_path.read_text().splitlines() if line.strip() and not line.lstrip().startswith('#')), '未配置')
        except Exception:
            cron_line = '读取 cron 配置失败'
        def cell(value):
            return html.escape(str(value if value not in (None, '') else '-'))
        rows = [
            ('日线数据 epoch', epoch.get('market_date'), epoch.get('epoch_id'), epoch.get('status')),
            ('V517 outcome-blind seed', seed.get('generated_at'), seed.get('seed_count'), seed.get('decision')),
            ('V519 冻结严格 T+1 回放', replay.get('generated_at'), (replay.get('overall') or {}).get('n'), replay.get('decision')),
            ('V521 scanner-time', scanner.get('generated_at'), scanner.get('pending_next_open_count'), scanner.get('decision')),
            ('V522 研究 release 审计', release.get('generated_at'), (release.get('metrics') or {}).get('n'), release.get('live_release_state')),
            ('V523 exact-next-open shadow', shadow.get('generated_at'), len(shadow.get('validations') or []), shadow.get('decision')),
        ]
        table = ''.join(f'<tr><td>{cell(name)}</td><td class="mono">{cell(at)}</td><td>{cell(count)}</td><td style="font-size:10px">{cell(state)}</td></tr>' for name, at, count, state in rows)
        return f'''<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>SMC 运行日志</title><meta http-equiv="refresh" content="120"><style>{CSS}</style></head><body>{build_nav()}<div class="container">
<div class="card" style="border-left:3px solid #d29922"><h2>运行日志 — EMPTY_BOOK / V517 Shadow</h2><p>生产候选、仓位、旧 V66/V90/V185 流程均已禁用。此页只显示当前数据 epoch 与 V517 的可复现研究链路，避免旧 ops 日志混入当前状态。</p><p style="color:#8b949e">定时任务：{cell(cron_line)}</p></div>
<div class="card"><h2>每日链路状态</h2><table><thead><tr><th>阶段</th><th>生成时间</th><th>数量</th><th>状态/结论</th></tr></thead><tbody>{table}</tbody></table></div>
<div class="card"><h2>运行语义</h2><p>每日 18:10：刷新全市场日线 → 仅用上一 committed epoch 做 exact-next-open shadow 验证 → 仅用新 epoch 生成 PENDING_NEXT_OPEN。无论历史回放表现如何，禁止回填历史交易为当前候选；当前无信号时合法结果是 0 条。</p><p><a href="/effort-result" style="color:#58a6ff">研究指标与逐笔回放</a>　<a href="/monitor" style="color:#58a6ff">按 response 日过滤历史研究</a></p></div>
</div></body></html>'''
    log = _load_ops_latest()
    if not log:
        return f"<!doctype html><html><head><meta charset='utf-8'><title>SMC日志</title><style>{CSS}</style></head><body>{build_nav()}<div class='container'><div class='card'><h2>运行日志</h2><p style='color:#f85149'>暂无 ops_latest.json；等待每日任务或手动运行 smc_daily_ops.py。</p></div></div></body></html>"
    pd = log.get('pick_diagnostics', {})
    an = log.get('analysis_summary', {})
    lv = log.get('live_summary', {})
    di = log.get('daily_ingest', {})
    rv = log.get('review_summary', {})
    files = log.get('files', {})
    empty_book = log.get('pipeline_state') == 'EMPTY_BOOK'
    if empty_book:
        an = {'state': 'HISTORICAL_ANALYTICS_HIDDEN_IN_EMPTY_BOOK'}
        lv = {'state': 'HISTORICAL_POSITION_SUMMARY_HIDDEN_IN_EMPTY_BOOK'}
        rv = {}
    def dict_rows(d):
        return ''.join(f"<tr><td>{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>" for k,v in (d or {}).items()) or '<tr><td colspan=2>无</td></tr>'
    def file_rows(d):
        return ''.join(f"<tr><td>{k}</td><td>{html.escape(str(v.get('mtime','')))}</td><td>{v.get('size',0)}</td><td>{html.escape(str(v.get('path','')))}</td></tr>" for k,v in (d or {}).items())
    def task_rows():
        tasks = [
            ('K线刷新', log.get('kline_refresh') or {}),
            ('生产选择器（EMPTY_BOOK 跳过）' if empty_book else 'V66选择器', log.get('selector') or {}),
            ('最新日扫', log.get('daily_scan') or {}),
            ('日扫合并（EMPTY_BOOK 跳过）' if empty_book else '日扫合并', log.get('daily_scan_merge') or {}),
            ('监控汇入（EMPTY_BOOK 跳过）' if empty_book else '监控汇入', log.get('daily_ingest') or {}),
        ]
        rows = []
        for name, t in tasks:
            status = t.get('returncode', '')
            if status == '':
                status = 'OK' if t.get('ok', True) else 'FAIL'
            result = t.get('reason') or t.get('error') or ''
            if t.get('added') is not None or t.get('validation_only') is not None:
                result = f"added={t.get('added',0)} validation={t.get('validation_only',0)} {result}".strip()
            rows.append(f"<tr><td>{name}</td><td class=mono>{html.escape(str(t.get('started_at','')))}</td><td class=mono>{html.escape(str(t.get('finished_at','')))}</td><td>{html.escape(str(t.get('duration_sec','')))}</td><td>{html.escape(str(status))}</td><td style='font-size:10px'>{html.escape(str(result)[:180])}</td></tr>")
        return ''.join(rows)
    active_rows = ''.join(
        f"<tr><td class=mono><a href='/kline?s={p.get('symbol')}' style='color:var(--blue)'>{p.get('symbol')}</a></td><td>{p.get('entry_date','')}</td><td>{p.get('zone_type','')}</td><td>{p.get('conf_type','')}</td><td>{p.get('v59_setup_family','')}</td><td>{p.get('score', p.get('breakout_quality_score',''))}</td><td>{p.get('pick_scope','')}</td></tr>"
        for p in pd.get('sample_active', [])[:30]
    ) or '<tr><td colspan=7>无</td></tr>'
    review_rows = ''.join(
        f"<tr><td class=mono>{r.get('symbol','')}</td><td>{r.get('closed_at','')}</td><td>{r.get('pnl_pct','')}</td><td>{html.escape(str(r.get('bucket','')))}</td><td>{html.escape(str(r.get('zone_type','')))}</td><td style='font-size:10px'>{html.escape(str(r.get('diagnosis',''))[:160])}</td></tr>"
        for r in rv.get('recent_sl_reviews', [])[-20:]
    ) or '<tr><td colspan=6>暂无SL复盘</td></tr>'
    recent_reviews = ''.join(
        f"<tr><td class=mono>{r.get('symbol','')}</td><td>{r.get('closed_at','')}</td><td>{r.get('reason','')}</td><td>{r.get('pnl_pct','')}</td><td>{r.get('design_match','')}</td><td style='font-size:10px'>{html.escape(str(r.get('repair_plan',''))[:160])}</td></tr>"
        for r in rv.get('recent_reviews', [])[-20:]
    ) or '<tr><td colspan=6>暂无复盘记录</td></tr>'
    empty_book = log.get('pipeline_state') == 'EMPTY_BOOK'
    stale = ('合法 EMPTY_BOOK：当前数据已刷新，但没有通过生产门禁的策略；所有生产扫描/选股均按合同跳过。'
             if empty_book else pd.get('stale_reason') or '最新行情日有候选或选择器正常。')
    data_date = log.get('data_date') or pd.get('data_date') or _latest_data_date(log)
    if empty_book:
        page_status = {
            'backtest': '生产回测禁用；无已晋级策略',
            'monitor': 'EMPTY_BOOK：生产扫描未运行，0只为合法状态',
            'analysis': '历史分析已隔离，不作为当前生产结果',
            'autopsy': '历史复盘已隔离，不作为当前持仓/信号',
        }
    else:
        window = f"默认窗口 {html.escape(str((log.get('analysis_window_start') or '20260101')))}~{data_date}"
        page_status = {
            'backtest': '默认结束日期/结果窗口已同步到最新行情日',
            'monitor': f"页面显示数据日期；可买 {pd.get('active_tradable_count', pd.get('data_date_count',0))} 只 / 观察 {pd.get('watch_only_count',0)} 只",
            'analysis': window,
            'autopsy': window,
        }
    page_sync_rows = ''.join([
        f"<tr><td>回测</td><td class=mono>{data_date}</td><td>{page_status['backtest']}</td></tr>",
        f"<tr><td>选股</td><td class=mono>{data_date}</td><td>{page_status['monitor']}</td></tr>",
        f"<tr><td>分析</td><td class=mono>{data_date}</td><td>{page_status['analysis']}</td></tr>",
        f"<tr><td>复盘</td><td class=mono>{data_date}</td><td>{page_status['autopsy']}</td></tr>",
    ])
    stale_color = '#d29922' if empty_book else ('#f85149' if pd.get('data_date_count', pd.get('today_count',0)) == 0 else '#3fb950')
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>SMC运行日志</title><meta http-equiv='refresh' content='120'><style>{CSS}</style></head><body>{build_nav()}
<div class='container'>
<div class='card' style='border-left:3px solid {stale_color}'><h2>运行日志 / 盲盒拆解 — {log.get('date')}</h2><p style='color:{stale_color};font-weight:bold'>{html.escape(str(stale))}</p><p style='color:#8b949e'>最新行情日: {log.get('data_date') or pd.get('data_date') or _latest_data_date(log)} | 生成时间: {log.get('generated_at')} | 选择器返回码: {(log.get('selector') or {}).get('returncode')}</p></div>
<div class='stats'>
 <div class='stat blue'><div class='val'>{pd.get('data_date_count', pd.get('today_count',0))}</div><div class='lbl'>最新行情日选股</div></div>
 <div class='stat green'><div class='val'>{pd.get('recent_45d_count',0)}</div><div class='lbl'>45日候选</div></div>
 <div class='stat'><div class='val'>{pd.get('active_count',0)}</div><div class='lbl'>Active</div></div>
 <div class='stat'><div class='val'>{pd.get('latest_pick_date','')}</div><div class='lbl'>最新选股日</div></div>
 <div class='stat red'><div class='val'>{an.get('n_rejected',0)}</div><div class='lbl'>筛除</div></div>
 <div class='stat'><div class='val'>{di.get('added',0)}</div><div class='lbl'>今日汇入</div></div>
 <div class='stat'><div class='val'>{rv.get('review_total',0)}</div><div class='lbl'>复盘记录</div></div>
</div>
<div class='card'><h2>页面日期同步状态</h2><table><thead><tr><th>页面</th><th>同步日期</th><th>状态</th></tr></thead><tbody>{page_sync_rows}</tbody></table></div>
<div class='card'><h2>任务执行时间</h2><table><thead><tr><th>任务</th><th>开始</th><th>结束</th><th>耗时(s)</th><th>状态/返回码</th><th>结果</th></tr></thead><tbody>{task_rows()}</tbody></table></div>
<div class='card'><h2>选股漏斗 / 为什么没选到</h2><div class='flex' style='gap:8px'><div style='flex:1'><h3>Scope</h3><table><tbody>{dict_rows(pd.get('active_scope_counts'))}</tbody></table></div><div style='flex:1'><h3>筛除原因</h3><table><tbody>{dict_rows(pd.get('reject_counts'))}</tbody></table></div><div style='flex:1'><h3>信号族</h3><table><tbody>{dict_rows(pd.get('active_by_family'))}</tbody></table></div></div></div>
<div class='card'><h2>当前候选样本</h2><table><thead><tr><th>代码</th><th>选股日</th><th>Zone</th><th>确认</th><th>族</th><th>匹配分</th><th>Scope</th></tr></thead><tbody>{active_rows}</tbody></table></div>
<div class='card'><h2>分析摘要</h2><div class='flex' style='gap:8px'><div style='flex:1'><h3>Metrics</h3><table><tbody>{dict_rows(an.get('metrics'))}</tbody></table></div><div style='flex:1'><h3>Exit</h3><table><tbody>{dict_rows(an.get('exit_counts'))}</tbody></table></div><div style='flex:1'><h3>Live</h3><table><tbody>{dict_rows(lv)}</tbody></table></div></div></div>
<div class='card'><h2>止损复盘归因</h2><table><thead><tr><th>代码</th><th>关闭时间</th><th>PnL</th><th>归因桶</th><th>Zone</th><th>诊断</th></tr></thead><tbody>{review_rows}</tbody></table></div>
<div class='card'><h2>最近复盘记录</h2><table><thead><tr><th>代码</th><th>时间</th><th>原因</th><th>PnL</th><th>符合设计</th><th>修复计划</th></tr></thead><tbody>{recent_reviews}</tbody></table></div>
<div class='card'><h2>{'归档 artifacts（仅审计追溯，不是当前生产数据）' if empty_book else '文件更新时间'}</h2><table><thead><tr><th>文件</th><th>更新时间</th><th>大小</th><th>路径</th></tr></thead><tbody>{file_rows(files)}</tbody></table></div>
</div></body></html>"""


def build_stoploss():
    if _production_empty_book():
        return _empty_book_page('止损归因', '无生产交易，不能用 V44 历史止损归因作为当前风控结论。')
    audit = _load_json_dict(V44_STOPLOSS_AUDIT, {})
    overall = audit.get('overall', {})
    attr = audit.get('loss_attribution_heuristic', {})
    by_entry = audit.get('by_entry_mode', [])
    by_signal = audit.get('by_signal_type', [])
    by_sl = audit.get('by_sl_type', [])
    def rows(items, cols=('key','n','wr','loss_rate','avg','avg_loss','avg_win')):
        out=''
        if isinstance(items, dict):
            items=[{'key':k, 'n':v} for k,v in items.items()]
        for x in (items or [])[:80]:
            out += '<tr>' + ''.join(f'<td>{x.get(c, "")}</td>' for c in cols) + '</tr>'
        return out or '<tr><td colspan="7" style="color:#8b949e">无数据</td></tr>'
    attr_rows=''.join(f'<tr><td>{k}</td><td>{v}</td></tr>' for k,v in attr.items()) or '<tr><td colspan="2">无数据</td></tr>'
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>V44 止损归因</title><style>{CSS}</style></head><body>{build_nav()}
<div class='container'>
<div class='card'><h2>V44 止损/亏损全面排查</h2><p style='color:#8b949e'>数据源: {V44_STOPLOSS_AUDIT}</p></div>
<div class='stats'>
 <div class='stat blue'><div class='val'>{overall.get('n',0)}</div><div class='lbl'>交易数</div></div>
 <div class='stat green'><div class='val'>{overall.get('wr',0)}%</div><div class='lbl'>WR</div></div>
 <div class='stat red'><div class='val'>{overall.get('loss_rate',0)}%</div><div class='lbl'>亏损率/止损压力</div></div>
 <div class='stat blue'><div class='val'>{overall.get('avg',0)}</div><div class='lbl'>均值PnL</div></div>
</div>
<div class='card'><h2>亏损归因</h2><table><thead><tr><th>原因</th><th>数量</th></tr></thead><tbody>{attr_rows}</tbody></table></div>
<div class='card'><h2>按入场方式</h2><table><thead><tr><th>类型</th><th>笔数</th><th>WR</th><th>亏损率</th><th>均值</th><th>均亏</th><th>均赢</th></tr></thead><tbody>{rows(by_entry)}</tbody></table></div>
<div class='card'><h2>按信号类型</h2><table><thead><tr><th>类型</th><th>笔数</th><th>WR</th><th>亏损率</th><th>均值</th><th>均亏</th><th>均赢</th></tr></thead><tbody>{rows(by_signal)}</tbody></table></div>
<div class='card'><h2>按SL类型</h2><table><thead><tr><th>类型</th><th>笔数</th><th>WR</th><th>亏损率</th><th>均值</th><th>均亏</th><th>均赢</th></tr></thead><tbody>{rows(by_sl)}</tbody></table></div>
</div></body></html>"""


def build_v45_page(version='v45_1'):
    b = load_v45_bundle(version, limit_events=2000, limit_rows=500)
    report = b.get('report') or {}
    validation = b.get('validation') or {}
    checks = validation.get('checks') or report.get('checks') or {}
    metrics = validation.get('metrics') or report.get('metrics') or {}
    prod = validation.get('production_acceptance', {})
    reject_counts = validation.get('reject_counts') or report.get('reject_counts') or {}
    watch_counts = validation.get('watch_status_counts') or report.get('watch_status_counts') or {}
    def dict_rows(d, limit=60):
        return ''.join(f'<tr><td>{k}</td><td>{v}</td></tr>' for k,v in list((d or {}).items())[:limit]) or '<tr><td colspan="2">无数据</td></tr>'
    def list_rows(items, cols):
        out=''
        for x in (items or [])[:120]:
            out += '<tr>' + ''.join(f'<td>{x.get(c, "")}</td>' for c in cols) + '</tr>'
        return out or f'<tr><td colspan="{len(cols)}" style="color:#8b949e">无数据</td></tr>'
    pick_cols=['symbol','setup_status','sequence_kind','zone_type','pick_date','entry_price','risk_pct','rr','quality_score','active_reason']
    watch_cols=['symbol','watch_status','sequence_kind','zone_type','signal_date','retrace_date','conf_date','market_state','active_reason']
    trade_cols=['symbol','entry_date','exit_date','sequence_kind','zone_type','entry_mode','conf_type','market_state','pnl_pct','exit_reason']
    display_version = f"{FRONTEND_VERSION} 当前生产事件驱动 SMC（原 {version} 实验契约）" if str(version).lower() in ('v45_5', 'v45.5') else f"{version} 原生事件驱动 SMC"
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>{display_version}</title><style>{CSS}</style></head><body>{build_nav()}
<div class='container'>
<div class='card'><h2>{display_version}</h2><p style='color:#8b949e'>当前生产版本: {FRONTEND_VERSION} | 历史实验接口: {version} | 数据目录: {b.get('base')} | 决策: {prod.get('decision','')}</p></div>
<div class='stats'>
 <div class='stat blue'><div class='val'>{metrics.get('n_trades',0)}</div><div class='lbl'>交易数</div></div>
 <div class='stat green'><div class='val'>{metrics.get('wr',0)}%</div><div class='lbl'>WR</div></div>
 <div class='stat red'><div class='val'>{metrics.get('sl_rate',0)}%</div><div class='lbl'>SL率</div></div>
 <div class='stat blue'><div class='val'>{checks.get('active_pick_count',0)}</div><div class='lbl'>Active Picks</div></div>
 <div class='stat blue'><div class='val'>{checks.get('watchlist_count',0)}</div><div class='lbl'>Watchlist</div></div>
 <div class='stat green'><div class='val'>{str(prod.get('signal_correctness_contract_passed', checks.get('correctness_contract_passed')))}</div><div class='lbl'>正确性契约</div></div>
</div>
<div class='card'><h2>正确性检查</h2><table><thead><tr><th>检查项</th><th>值</th></tr></thead><tbody>{dict_rows(checks, 90)}</tbody></table></div>
<div class='card'><h2>Watch 状态</h2><table><thead><tr><th>状态</th><th>数量</th></tr></thead><tbody>{dict_rows(watch_counts)}</tbody></table></div>
<div class='card'><h2>拒绝漏斗</h2><table><thead><tr><th>原因</th><th>数量</th></tr></thead><tbody>{dict_rows(reject_counts, 90)}</tbody></table></div>
<div class='card'><h2>Active Picks</h2><table><thead><tr>{''.join('<th>'+c+'</th>' for c in pick_cols)}</tr></thead><tbody>{list_rows(b.get('picks'), pick_cols)}</tbody></table></div>
<div class='card'><h2>Watchlist</h2><table><thead><tr>{''.join('<th>'+c+'</th>' for c in watch_cols)}</tr></thead><tbody>{list_rows(b.get('watchlist'), watch_cols)}</tbody></table></div>
<div class='card'><h2>Trades</h2><table><thead><tr>{''.join('<th>'+c+'</th>' for c in trade_cols)}</tr></thead><tbody>{list_rows(b.get('trades'), trade_cols)}</tbody></table></div>
</div></body></html>"""

def build_analysis(start='', end=''):
    if _production_empty_book():
        return _empty_book_page('生产分析', '无生产交易；分析页不再聚合 V185/V88 历史交易。V517 的冻结研究分析仅在研究页展示。')
    # FIX(2026-08-22): COMBO 生产 — 分析 v20c 回测（逐年/逐月/分腿/弱月）
    if _production_registry().get('production_strategy') == 'COMBO_SMC_EVENT':
        try:
            import csv as _csv
            from collections import defaultdict as _dd
            _trades = []
            with open(r'E:\test\smc_project\research\combo_v20f_trades.csv', encoding='utf-8-sig') as _fh:
                for _r in _csv.DictReader(_fh):
                    _r['net_pnl_pct'] = float(_r.get('net_pnl_pct', 0))
                    _trades.append(_r)
            if not _trades:
                return '<h2>无 v20c 回测数据</h2>'
            _year = _dd(list)
            _month = _dd(list)
            _leg = _dd(list)
            for _t in _trades:
                _y = str(_t.get('entry_date', ''))[:4]
                _m = str(_t.get('entry_date', ''))[:6]
                _src = _t.get('src', 'SMC')
                _year[_y].append(_t['net_pnl_pct'])
                _month[_m].append(_t['net_pnl_pct'])
                _leg[_src].append(_t['net_pnl_pct'])
            def _sum(rs):
                if not rs:
                    return 0
                wins = [x for x in rs if x > 0]
                losses = [x for x in rs if x <= 0]
                return sum(rs) / len(rs), 100 * len(wins) / len(rs), (sum(wins) / abs(sum(losses))) if losses else 99
            _y_rows = ''.join(
                f"<tr><td>{_y}</td><td>{len(rs)}</td><td>{_sum(rs)[1]:.0f}%</td><td>{_sum(rs)[0]:+.2f}%</td><td>{_sum(rs)[2]:.2f}</td></tr>"
                for _y, rs in sorted(_year.items()))
            _m_rows = ''.join(
                f"<tr><td>{_m}</td><td>{len(rs)}</td><td>{_sum(rs)[1]:.0f}%</td><td>{_sum(rs)[0]:+.2f}%</td><td>{_sum(rs)[2]:.2f}</td></tr>"
                for _m, rs in sorted(_month.items()))
            _leg_rows = ''.join(
                f"<tr><td>{_l}</td><td>{len(rs)}</td><td>{_sum(rs)[1]:.0f}%</td><td>{_sum(rs)[0]:+.2f}%</td><td>{_sum(rs)[2]:.2f}</td></tr>"
                for _l, rs in sorted(_leg.items()))
            return f'''<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>v20c 组合回测分析</title><style>{CSS}</style></head><body>{build_nav()}<div class="container">
<div class="card" style="border-left:3px solid #3fb950"><h2>v20c 组合回测分析</h2><p style="color:#8b949e">来源 combo_v20f_trades.csv（{len(_trades)} 笔）；逐年/逐月/分腿统计。详细逐年逐月报告见 /backtest。</p></div>
<div class="card"><h2>分腿统计</h2><table><thead><tr><th>腿</th><th>n</th><th>胜率</th><th>平均收益</th><th>PF</th></tr></thead><tbody>{_leg_rows or '<tr><td colspan=5>无</td></tr>'}</tbody></table></div>
<div class="card"><h2>逐年</h2><table><thead><tr><th>年</th><th>n</th><th>胜率</th><th>平均收益</th><th>PF</th></tr></thead><tbody>{_y_rows or '<tr><td colspan=5>无</td></tr>'}</tbody></table></div>
<div class="card"><h2>逐月（弱月识别）</h2><table><thead><tr><th>月</th><th>n</th><th>胜率</th><th>平均收益</th><th>PF</th></tr></thead><tbody>{_m_rows or '<tr><td colspan=5>无</td></tr>'}</tbody></table></div>
<p><a href="/backtest" style="color:#58a6ff">回测详情</a> <a href="/combo" style="color:#58a6ff">组合仪表盘</a></p></div></body></html>'''
        except Exception as _e:
            return f'<h2>v20c 分析加载失败: {_e}</h2>'
    trades_all = reload_trades()
    m = reload_metrics()
    ops = _load_ops_latest()
    latest_ops_date = _latest_data_date(ops)
    w_start = _date_key(start) or str(m.get('window_start', '20260101'))
    w_end = _date_key(end) or latest_ops_date or str(m.get('window_end', '20260521'))
    trades = [_apply_smc_field_contract(t, default_engine=ACTIVE_VERSION) for t in _filter_trades_by_window(trades_all, w_start, w_end)]
    n = len(trades)
    if not n: return "<h2>No backtest data</h2>"

    from collections import Counter, defaultdict
    
    # Context analysis via zone_type
    ctx_stats = defaultdict(lambda: {'n':0, 'won':0, 'pnls':[]})
    for t in trades:
        cs = t.get('zone_type', '?')
        ctx_stats[cs]['n'] += 1
        ctx_stats[cs]['won'] += 1 if is_winner(t) else 0
        ctx_stats[cs]['pnls'].append(_float_or_zero(t.get('pnl_pct')))
    
    ctx_rows = ""
    for cs in sorted(ctx_stats, key=lambda k: -ctx_stats[k]['n']):
        d = ctx_stats[cs]
        wr = d['won']/d['n']*100 if d['n'] else 0
        avg = sum(d['pnls'])/len(d['pnls']) if d['pnls'] else 0
        bar = '█' * min(int(wr/5), 20)
        ctx_rows += f'<tr><td class=mono>{str(cs)[:16]}</td><td class=mono>{d["n"]}笔</td><td class=green>{wr:.1f}%</td><td class=mono>{avg:+.2f}%</td><td style="color:#ffd700">{bar}</td></tr>'
    
    # AI Recommendations from active V31 data
    recs = []
    
    # 1. Exit analysis (canonicalized for V25-V31 compatibility)
    exits = Counter(exit_key(t) for t in trades)
    sl_pct = exits.get('SL_HIT', 0) / n * 100
    tp_pct = exits.get('TP_HIT', 0) / n * 100
    trail_pct = exits.get('TRAILING_STOP', 0) / n * 100
    timeout_pct = exits.get('TIMEOUT', 0) / n * 100
    if sl_pct > 30:
        recs.append(('high', '止损优化', f'{sl_pct:.1f}%交易触止损', '扩大SL倍数或ATR缓冲'))
    if timeout_pct > 5:
        recs.append(('high', '持仓优化', f'{timeout_pct:.1f}%交易超时', '增加max_hold_bars或提高TP触发速度'))
    
    # 2. Market state / regime analysis
    states_analysis = {}
    for t in trades:
        r = t.get('market_state', t.get('regime', '?'))
        if not r or r == '?': r = t.get('engine','?')
        if r not in states_analysis: states_analysis[r] = {'n':0, 'won':0, 'pnl':0}
        states_analysis[r]['n'] += 1
        if is_winner(t): states_analysis[r]['won'] += 1
        states_analysis[r]['pnl'] += _float_or_zero(t.get('pnl_pct'))
    
    # Skip RANGE-like states with poor WR
    for st, d in states_analysis.items():
        if d['n'] >= 3:
            swr = d['won']/d['n']*100
            savg = d['pnl']/d['n']
            if swr < 50:
                recs.append(('high', '状态过滤', f'{st}状态WR={swr:.0f}% avgP={savg:+.1f}%', '考虑过滤该市场状态或降低仓位'))
    
    # 3. Zone quality correlation  
    zone_best = max(ctx_stats.items(), key=lambda x: sum(x[1]['pnls'])/len(x[1]['pnls']) if x[1]['pnls'] else -999) if ctx_stats else ('?', {'pnls':[0]})
    recs.append(('info', 'Zone优选', f'最佳Zone={zone_best[0]}', f'优先选择该Zone类型信号'))
    
    # 4. Confirmation quality
    conf_best = {}
    for t in trades:
        c = t.get('conf_type', '?')[:12]
        if c not in conf_best: conf_best[c] = {'n':0, 'won':0, 'pnl':0}
        conf_best[c]['n'] += 1
        if is_winner(t): conf_best[c]['won'] += 1
        conf_best[c]['pnl'] += _float_or_zero(t.get('pnl_pct'))
    
    if conf_best:
        best_conf = max(conf_best.items(), key=lambda x: (x[1]['won']/x[1]['n'] if x[1]['n']>=3 else 0))
        if best_conf[1]['n'] >= 3:
            recs.append(('info', '入场确认', f'最佳确认={best_conf[0]} WR={best_conf[1]["won"]/best_conf[1]["n"]*100:.0f}%', '优先使用该确认方式入场'))
    
    # 5. Per-state SL/TP display
    regime_rows = ""
    for r in sorted(states_analysis):
        d = states_analysis[r]
        rt = [t for t in trades if t.get('market_state', t.get('regime','?'))==r]
        avg_sl_r = sum(_float_or_zero(t.get('sl_pct')) for t in rt) / len(rt) if rt else 0
        avg_rr_r = sum(_float_or_zero(t.get('rr')) for t in rt) / len(rt) if rt else 0
        rwr = d['won']/d['n']*100 if d['n'] else 0
        rpnl = d['pnl']/d['n'] if d['n'] else 0
        regime_rows += f'<tr><td class=mono>{r}</td><td class=mono>{d["n"]}</td><td class=green>{rwr:.1f}%</td><td class=mono>{rpnl:+.2f}%</td><td class=mono style="color:#ff6b6b">SL={avg_sl_r:.1f}%</td><td class=mono style="color:#3fb950">RR={avg_rr_r:.2f}x</td></tr>'
    
    sev_icons = {'high': '🔴', 'medium': '🟡', 'info': '🔵'}
    rec_rows = ''.join(f'<tr><td>{sev_icons.get(r[0],"⚪")}</td><td><b>{r[1]}</b></td><td>{r[2]}</td><td>{r[3]}</td></tr>' for r in recs)
    
    won = sum(1 for t in trades if is_winner(t))
    wr = won/n*100
    avg_pnl = sum(_float_or_zero(t.get('pnl_pct')) for t in trades)/n
    contract_block = _contract_summary_html(trades, '分析窗口 DNA/组合合同同步')
    ops = _load_ops_latest()
    selector = ops.get('selector') or {}
    scan = ops.get('daily_scan') or {}
    merge = ops.get('daily_scan_merge') or {}
    ingest = ops.get('daily_ingest') or {}
    ops_time_html = f"""<div class=\"card\"><h2>任务执行时间</h2><table><thead><tr><th>任务日</th><th>日志生成</th><th>V66选择器</th><th>最新日扫</th><th>日扫合并</th><th>监控汇入</th></tr></thead><tbody><tr><td class=mono>{html.escape(str(ops.get('date','')))}</td><td class=mono>{html.escape(str(ops.get('generated_at','')))}</td><td class=mono>{html.escape(str(selector.get('started_at','')))} → {html.escape(str(selector.get('finished_at','')))} ({html.escape(str(selector.get('duration_sec','')))}s)</td><td class=mono>{html.escape(str(scan.get('started_at','')))} → {html.escape(str(scan.get('finished_at','')))} ({html.escape(str(scan.get('duration_sec','')))}s)</td><td>{html.escape(str(merge.get('reason','')))}</td><td>{html.escape(str(ingest.get('reason','')))}</td></tr></tbody></table></div>""" if ops else ''
    stability_html = _build_v103a_stability_html()
    
    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>SMC AI分析</title><meta http-equiv="refresh" content="120"><style>{CSS}</style></head><body>
{build_nav()}
<div class="container">

{ops_time_html}
{stability_html}
<div class="card"><h2>📊 {FRONTEND_VERSION} 引擎分析</h2>
<p style="color:#8b949e">模式说明：分析页是窗口聚合统计，不做逐笔复盘；当前窗口 {w_start}~{w_end}，按 entry_date 过滤后 {n} 笔 / 全量 {len(trades_all)} 笔。统计维度：Zone类型、出场方式、市场状态、确认方式，并生成简单规则建议。字段合同已统一补齐：选股日、加入日、Zone、成本线、波动。</p>
<div class="flex" style="gap:8px;margin:12px 0">
<div class="stat green"><div class="val">{n:,}</div><div class="lbl">交易</div></div>
<div class="stat blue"><div class="val">{wr:.1f}%</div><div class="lbl">胜率</div></div>
<div class="stat"><div class="val">{avg_pnl:+.2f}%</div><div class="lbl">均盈</div></div>
<div class="stat" style="color:#d29922"><div class="val">{trail_pct:.0f}%</div><div class="lbl">跟踪出场</div></div>
<div class="stat" style="color:#f85149"><div class="val">{exits.get('SL_HIT',0)}</div><div class="lbl">止损</div></div>
</div></div>

<div class="flex">
<div class="card" style="flex:1"><h2>🔬 上下文影响力 (实测)</h2>
<p style="color:#8b949e;margin-bottom:10px">{FRONTEND_VERSION}实测 — Zone类型对胜率/均盈的影响</p>
<table><thead><tr><th>上下文</th><th>笔数</th><th>胜率</th><th>均盈</th><th>强度</th></tr></thead><tbody>{ctx_rows}</tbody></table></div>

<div class="card" style="flex:1"><h2>📋 市场状态×SL/TP</h2>
<p style="color:#8b949e;margin-bottom:10px">四档自适应参数</p>
<table><thead><tr><th>状态</th><th>笔数</th><th>胜率</th><th>均盈</th><th>SL</th><th>TP</th></tr></thead><tbody>{regime_rows}</tbody></table></div>
</div>

<div class="card"><h2>💡 自动诊断建议</h2>
<table><thead><tr><th></th><th>领域</th><th>发现</th><th>建议</th></tr></thead><tbody>{rec_rows}</tbody></table></div>
{contract_block}

</div></body></html>"""


def build_compare():
    if _production_empty_book():
        return _empty_book_page('引擎版本对比', '没有生产版本可对比；V185 等历史高指标结果已被拒绝，不得显示为当前引擎。')
    from collections import Counter, defaultdict
    trades = reload_trades()
    if not trades: return "<h2>No data</h2>"
    
    # Generate version comparison dynamically
    n = len(trades)
    won = sum(1 for t in trades if is_winner(t))
    wr = won/n*100
    avg_pnl = sum(_float_or_zero(t.get('pnl_pct')) for t in trades)/n
    total_pnl = sum(_float_or_zero(t.get('pnl_pct')) for t in trades)
    stocks = len(set(t.get('symbol','') for t in trades))
    exits = Counter(exit_key(t) for t in trades)
    exit_items = list(exits.items())[:3]
    exit_str = ','.join(f'{k}({c})' for k,c in exit_items)

    # Per-engine breakdown
    by_engine = defaultdict(lambda: {'n':0,'won':0,'pnls':[],'stocks':set()})
    for t in trades:
        eng = t.get('engine','?')
        by_engine[eng]['n'] += 1
        by_engine[eng]['won'] += 1 if is_winner(t) else 0
        by_engine[eng]['pnls'].append(_float_or_zero(t.get('pnl_pct')))
        by_engine[eng]['stocks'].add(t.get('symbol',''))
    
    ver_rows = ""
    for eng in sorted(by_engine):
        d = by_engine[eng]
        if d['n'] == 0: continue
        ew = d['won']/d['n']*100
        ep = sum(d['pnls'])/d['n']
        et = sum(d['pnls'])
        wc = '#3fb950' if ew>=90 else ('#d29922' if ew>=80 else '#f85149')
        ver_rows += f'<tr><td class=mono style="font-weight:bold">{eng}</td><td class=mono>{d["n"]:,}</td><td class=mono>{len(d["stocks"]):,}</td><td class=mono style="color:{wc};font-weight:bold">{ew:.1f}%</td><td class=mono style="color:var(--accent)">{ep:+.2f}%</td><td class=mono>{et:+.0f}%</td><td style="font-size:10px">{exit_str}</td></tr>'
    
    # Stock cross-reference from V19
    by_stock = defaultdict(lambda: {'n':0,'won':0,'pnls':[],'best_eng':'','best_seq':'','best_pnl':-999})
    for t in trades:
        s = t.get('symbol','')
        by_stock[s]['n'] += 1
        by_stock[s]['won'] += 1 if is_winner(t) else 0
        pnl = _float_or_zero(t.get('pnl_pct'))
        by_stock[s]['pnls'].append(pnl)
        if pnl > by_stock[s]['best_pnl']:
            by_stock[s]['best_pnl'] = pnl
            by_stock[s]['best_eng'] = t.get('engine','')
            by_stock[s]['best_seq'] = t.get('seq', t.get('detail', t.get('ctx_seq','')))
    
    pick_rows = ""
    pi = 0
    for sym, d in sorted(by_stock.items(), key=lambda x: -x[1]['n']):
        pi += 1
        sw = d['won']/d['n']*100
        sp = sum(d['pnls'])/d['n']
        q = 'A' if sw>=90 and d['n']>=3 else ('B' if sw>=80 or d['n']>=2 else ('C' if d['n']>=1 else 'D'))
        qc = {'A':'#3fb950','B':'#d29922','C':'#58a6ff','D':'#8b949e'}.get(q,'#8b949e')
        wrc = '#3fb950' if sw>=80 else ('#d29922' if sw>=50 else '#f85149')
        pick_rows += f'<tr><td class=mono>{pi}</td><td class=mono><a href="/kline?s={sym}" style="color:var(--blue)">{sym}</a></td><td class=mono style="color:{qc};font-weight:bold">{q}</td><td class=mono>{d["best_eng"]}</td><td style="font-size:9px">{d["best_seq"]}</td><td class=mono>{d["n"]}</td><td class=mono style="color:{wrc};font-weight:bold">{sw:.1f}%</td><td class=mono style="color:var(--accent)">{sp:+.2f}%</td><td class=mono>{sum(d["pnls"]):+.1f}%</td></tr>'
    
    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>SMC 对比分析</title><meta http-equiv="refresh" content="120"><style>{CSS}</style></head><body>
{build_nav()}
<div class="container">
<div class="card"><h2>📊 引擎版本对比</h2>
<table><thead><tr><th>版本</th><th>交易</th><th>股票</th><th>WR</th><th>均盈</th><th>累计PnL</th><th>出场</th></tr></thead><tbody>{ver_rows}</tbody></table></div>
<div class="card" style="border-left:3px solid var(--accent)"><h2>📡 个股交叉统计 — {len(by_stock)}只</h2>
<p style="color:#8b949e;margin-bottom:10px">按交易次数排序 | A=≥3笔WR≥90% B=≥2笔或WR≥80% C=1笔 D=无信号 | 点击代码跳转K线</p>
<table><thead><tr><th>#</th><th>代码</th><th>评级</th><th>最佳引擎</th><th>最佳序列</th><th>交易</th><th>WR</th><th>均盈</th><th>累计</th></tr></thead><tbody>{pick_rows}</tbody></table></div>
</div></body></html>"""


def _load_v49_closed_loop_review():
    version_key = str(ACTIVE_VERSION).lower().replace('_', '_')
    candidates = [
        Path(f'/root/.hermes/smc_audit/{version_key}_closed_loop_90d_review.json'),
        Path('/root/.hermes/smc_audit/v49_closed_loop_90d_review.json'),
    ]
    for p in candidates:
        if p.exists():
            return _load_json_dict(p, {})
    return {}


def _autopsy_issue_rows(rows, limit=20):
    out = ''
    for r in rows[:limit]:
        r = _apply_smc_field_contract(r, default_engine=ACTIVE_VERSION)
        issues = ','.join(r.get('issues', [])) or 'OK'
        zone = r.get('zone_type') or '-'
        if r.get('zone_low') or r.get('zone_high'):
            zone = f"{zone} [{float(r.get('zone_low') or 0):.2f}~{float(r.get('zone_high') or 0):.2f}]"
        out += (f'<tr><td class=mono><a href="/kline?s={r.get("symbol","")}" style="color:var(--blue)">{r.get("symbol","?")}</a></td>'
                f'<td class=mono>{r.get("select_date") or r.get("pick_date","")}</td><td class=mono>{r.get("join_date","")}</td>'
                f'<td class=mono>{r.get("entry_date","")}</td><td class=mono>{r.get("exit_date","")}</td>'
                f'<td class=mono>{html.escape(str(zone))}</td><td class=mono>{float(r.get("cost_line") or 0):.2f}</td>'
                f'<td class=mono>{float(r.get("volatility_pct") or 0):.2f}%</td>'
                f'<td class=mono>{_float_or_zero(r.get("hold_bars")):.0f}</td><td class=mono>{_float_or_zero(r.get("pnl_pct")):+.2f}%</td>'
                f'<td class=mono>{_float_or_zero(r.get("realized_r")):.2f}R</td><td class=mono>{_float_or_zero(r.get("mfe90_pct")):.2f}%</td>'
                f'<td class=mono>{_float_or_zero(r.get("capture90_rate")):.2f}</td><td>{html.escape(issues)}</td></tr>')
    return out


def build_autopsy(start='', end=''):
    if _production_empty_book():
        return _empty_book_page('生产复盘', '无生产交易；复盘页不再展示 V185/V88 历史逐笔记录或旧 90 日闭环。')
    # FIX(2026-08-22): COMBO 生产 — v20c 逐笔复盘（含子信号链 + 买卖点 + PnL）
    if _production_registry().get('production_strategy') == 'COMBO_SMC_EVENT':
        try:
            import csv as _csv
            _trades = []
            with open(r'E:\test\smc_project\research\combo_v20f_trades.csv', encoding='utf-8-sig') as _fh:
                for _r in _csv.DictReader(_fh):
                    _r['net_pnl_pct'] = float(_r.get('net_pnl_pct', 0))
                    _trades.append(_r)
            _trades.sort(key=lambda t: str(t.get('entry_date', '')), reverse=True)
            _w = _date_key(start) or ''
            _we = _date_key(end) or '99999999'
            _rows = ''.join(
                f"<tr><td class=mono><a href=\"/kline?symbol={html.escape(str(t.get('symbol','')))}\">{html.escape(str(t.get('symbol','')))}</a></td>"
                f"<td class=mono>{html.escape(str(t.get('entry_date','')))}</td><td>{html.escape(str(t.get('src','')))}</td>"
                f"<td class=mono>{t.get('net_pnl_pct',0):+.2f}%</td>"
                f"<td style=\"color:{('#f85149' if t.get('net_pnl_pct',0)<0 else '#3fb950')}\">{'亏' if t.get('net_pnl_pct',0)<0 else '盈'}</td></tr>"
                for t in _trades if _w <= str(t.get('entry_date',''))[:8] <= _we)[:1000]
            _shown = min(len(_trades), 1000)
            _n = len(_trades)
            _win = sum(1 for t in _trades if t['net_pnl_pct'] > 0)
            return f'''<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>v20c 逐笔复盘</title><style>{CSS}</style></head><body>{build_nav()}<div class="container">
<div class="card" style="border-left:3px solid #d29922"><h2>v20d 组合逐笔复盘（分层TP/SL）（{_n} 笔，显示前 {_shown}）</h2><p style="color:#8b949e">总胜率 {100*_win/_n if _n else 0:.0f}%。点击代码跳转 K 线查看买卖点/信号/子信号链/TP/SL。使用开始/结束日期过滤查看其它区间。</p><form method="get" action="/autopsy" style="display:flex;gap:8px;margin:10px 0"><label>开始 <input name="start" value="{html.escape(start)}" style="width:100px"></label><label>结束 <input name="end" value="{html.escape(end)}" style="width:100px"></label><button type="submit">过滤</button></form></div>
<div class="card"><table><thead><tr><th>代码</th><th>买入日</th><th>腿</th><th>PnL</th><th>结果</th></tr></thead><tbody>{_rows or '<tr><td colspan=5>该区间无交易</td></tr>'}</tbody></table></div></div></body></html>'''
        except Exception as _e:
            return f'<h2>v20c 复盘加载失败: {_e}</h2>'
    trades_all = reload_trades()
    m = reload_metrics()
    ops = _load_ops_latest()
    latest_ops_date = _latest_data_date(ops)
    w_start = _date_key(start) or str(m.get('window_start', '20260101'))
    w_end = _date_key(end) or latest_ops_date or str(m.get('window_end', '20260521'))
    trades = [_apply_smc_field_contract(t, default_engine=ACTIVE_VERSION) for t in _filter_trades_by_window(trades_all, w_start, w_end)]
    n = len(trades)
    if n == 0:
        return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>复盘诊断</title><meta http-equiv="refresh" content="120"><style>{CSS}</style></head><body>
{build_nav()}
<div class="container"><div class="card"><h2>🔬 复盘诊断 — 无数据</h2><p>请先运行回测引擎</p></div></div></body></html>"""
    
    from collections import Counter as _Counter
    
    # Basic stats
    won_n = sum(1 for t in trades if is_winner(t))
    wr = won_n / n * 100
    avg_pnl = sum(_float_or_zero(t.get('pnl_pct')) for t in trades) / n
    avg_win = sum(_float_or_zero(t.get('pnl_pct')) for t in trades if is_winner(t)) / max(won_n, 1)
    avg_loss = sum(_float_or_zero(t.get('pnl_pct')) for t in trades if not is_winner(t)) / max(n - won_n, 1)
    avg_hold = sum(_float_or_zero(t.get('hold_bars')) for t in trades) / n
    
    # By zone type
    zones = {}
    for t in trades:
        z = t.get('zone_type', '?')
        if z not in zones: zones[z] = {'t': 0, 'w': 0, 'pnl': 0}
        zones[z]['t'] += 1
        if is_winner(t): zones[z]['w'] += 1
        zones[z]['pnl'] += _float_or_zero(t.get('pnl_pct'))
    
    zone_rows = ''
    for z, d in sorted(zones.items(), key=lambda x: -x[1]['t']):
        zwr = d['w'] / d['t'] * 100 if d['t'] else 0
        zavg = d['pnl'] / d['t'] if d['t'] else 0
        zone_rows += f'<tr><td class=mono>{z}</td><td class=mono>{d["t"]}</td><td class=mono>{zwr:.1f}%</td><td class=mono>{zavg:+.2f}%</td></tr>'
    
    # By confirmation type
    confs = {}
    for t in trades:
        c = t.get('conf_type', '?')[:12]
        if c not in confs: confs[c] = {'t': 0, 'w': 0, 'pnl': 0}
        confs[c]['t'] += 1
        if is_winner(t): confs[c]['w'] += 1
        confs[c]['pnl'] += _float_or_zero(t.get('pnl_pct'))
    
    conf_rows = ''
    for c, d in sorted(confs.items(), key=lambda x: -x[1]['t']):
        cwr = d['w'] / d['t'] * 100 if d['t'] else 0
        cavg = d['pnl'] / d['t'] if d['t'] else 0
        conf_rows += f'<tr><td class=mono>{c}</td><td class=mono>{d["t"]}</td><td class=mono>{cwr:.1f}%</td><td class=mono>{cavg:+.2f}%</td></tr>'
    
    # By market state
    states = {}
    for t in trades:
        s = t.get('market_state', '?')
        if s not in states: states[s] = {'t': 0, 'w': 0, 'pnl': 0}
        states[s]['t'] += 1
        if is_winner(t): states[s]['w'] += 1
        states[s]['pnl'] += _float_or_zero(t.get('pnl_pct'))
    
    state_rows = ''
    for s, d in sorted(states.items(), key=lambda x: -x[1]['t']):
        swr = d['w'] / d['t'] * 100 if d['t'] else 0
        savg = d['pnl'] / d['t'] if d['t'] else 0
        state_rows += f'<tr><td class=mono>{s}</td><td class=mono>{d["t"]}</td><td class=mono>{swr:.1f}%</td><td class=mono>{savg:+.2f}%</td></tr>'
    
    # Exit reasons
    exits = _Counter(exit_key(t) for t in trades)
    exit_rows = ''.join(f'<tr><td class=mono>{exit_label(e)}</td><td class=mono>{c}</td><td class=mono>{c/n*100:.1f}%</td></tr>' for e, c in exits.most_common(8))
    
    # Worst trades
    worst = sorted(trades, key=lambda t: _float_or_zero(t.get('pnl_pct')))[:10]
    worst_rows = ''.join(
        f'<tr><td class=mono><a href="/kline?s={t.get("symbol","")}" style="color:var(--blue)">{t.get("symbol","?")}</a></td>'
        f'<td class=mono>{_float_or_zero(t.get("entry_price")):.2f}</td>'
        f'<td class=mono>{_float_or_zero(t.get("exit_price")):.2f}</td>'
        f'<td class=mono style="color:#f85149">{_float_or_zero(t.get("pnl_pct")):+.2f}%</td>'
        f'<td class=mono>{exit_label(t.get("exit_reason","?"))}</td>'
        f'<td class=mono>{t.get("zone_type","?")}</td>'
        f'<td class=mono>{_float_or_zero(t.get("hold_bars")):.0f}b</td></tr>'
        for t in worst)
    
    # Auto-fix suggestions
    fix_html = ''
    sl_hits = exits.get('SL_HIT', 0)
    timeout_n = exits.get('TIMEOUT', 0)
    sl_rate = sl_hits / n * 100 if n else 0
    
    if sl_rate > 40:
        fix_html += f'<tr><td class=mono style="color:#f85149">HIGH</td><td class=mono>SL调整</td><td>止损率{sl_rate:.0f}%偏高</td><td style="color:var(--accent)">扩大SL×1.2或ATR倍数+0.2</td></tr>'
    if wr < 60:
        fix_html += f'<tr><td class=mono style="color:#f85149">HIGH</td><td class=mono>信号过滤</td><td>胜率{wr:.0f}%偏低</td><td style="color:var(--accent)">收紧入场条件(zone_age/conf_type)</td></tr>'
    if avg_pnl < 1.0:
        fix_html += f'<tr><td class=mono style="color:#d2991d">MED</td><td class=mono>TP优化</td><td>均盈仅{avg_pnl:+.2f}%</td><td style="color:var(--accent)">扩大TP目标或启用跟踪止盈更早激活</td></tr>'
    if avg_loss < -5:
        fix_html += f'<tr><td class=mono style="color:#d2991d">MED</td><td class=mono>SL收紧</td><td>均亏{avg_loss:.2f}%过大</td><td style="color:var(--accent)">收紧止损距离</td></tr>'
    if not fix_html:
        fix_html = '<tr><td colspan=4 style="color:#3fb950">✅ 系统状态良好，无需紧急修复</td></tr>'
    
    title = f'🔬 {FRONTEND_VERSION} 逐笔交易复盘诊断'
    contract_block = _contract_summary_html(trades, '复盘窗口 DNA/组合合同同步')
    cl = _load_v49_closed_loop_review()
    cl_summary = cl.get('summary', {}) if isinstance(cl, dict) else {}
    cl_issues = cl.get('issue_counts', {}) if isinstance(cl, dict) else {}
    cl_worst = cl.get('worst_trades', []) if isinstance(cl, dict) else []
    cl_rows = _autopsy_issue_rows(cl_worst, 20) if cl_worst else '<tr><td colspan=9 style="color:#8b949e">未生成90日闭环复盘，请运行 v25/v49_closed_loop_90d_review.py</td></tr>'
    cl_issue_rows = ''.join(f'<tr><td class=mono>{html.escape(str(k))}</td><td class=mono>{v}</td></tr>' for k,v in sorted(cl_issues.items(), key=lambda x: -x[1])) or '<tr><td colspan=2>无</td></tr>'
    cl_schedule = cl.get('closed_loop_schedule', {}) if isinstance(cl, dict) else {}
    cl_schedule_html = ''.join(f'<li><b>{html.escape(str(k))}</b>：{html.escape(str(v))}</li>' for k,v in cl_schedule.items())
    ops = _load_ops_latest()
    selector = ops.get('selector') or {}
    scan = ops.get('daily_scan') or {}
    merge = ops.get('daily_scan_merge') or {}
    ingest = ops.get('daily_ingest') or {}
    ops_time_html = f"""<div class=\"card\"><h2>任务执行时间</h2><table><thead><tr><th>任务日</th><th>日志生成</th><th>V66选择器</th><th>最新日扫</th><th>日扫合并</th><th>监控汇入</th></tr></thead><tbody><tr><td class=mono>{html.escape(str(ops.get('date','')))}</td><td class=mono>{html.escape(str(ops.get('generated_at','')))}</td><td class=mono>{html.escape(str(selector.get('started_at','')))} → {html.escape(str(selector.get('finished_at','')))} ({html.escape(str(selector.get('duration_sec','')))}s)</td><td class=mono>{html.escape(str(scan.get('started_at','')))} → {html.escape(str(scan.get('finished_at','')))} ({html.escape(str(scan.get('duration_sec','')))}s)</td><td>{html.escape(str(merge.get('reason','')))}</td><td>{html.escape(str(ingest.get('reason','')))}</td></tr></tbody></table></div>""" if ops else ''
    
    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>复盘诊断</title><meta http-equiv="refresh" content="120"><style>{CSS}</style></head><body>
{build_nav()}
<div class="container">
{ops_time_html}
<div class="card"><h2>{title}</h2>
<p style="color:#8b949e">模式说明：复盘页是窗口逐笔诊断摘要；当前窗口 {w_start}~{w_end}，按 entry_date 过滤后 {n} 笔 / 全量 {len(trades_all)} 笔。它会按 Zone、确认、市场状态、出场方式分桶，并列出当前窗口最差10笔用于人工复盘。字段合同已统一补齐：选股日、加入日、Zone、成本线、波动。</p>
<p style="color:#8b949e">四维诊断: Zone类型 → 入场确认 → 市场状态 → 出场时机</p>
<div class="stats">
<div class="stat green"><div class="val">{n:,}</div><div class="lbl">总交易</div></div>
<div class="stat blue"><div class="val">{wr:.1f}%</div><div class="lbl">胜率</div></div>
<div class="stat"><div class="val">{avg_pnl:+.2f}%</div><div class="lbl">均盈</div></div>
<div class="stat"><div class="val">{avg_win:+.2f}%</div><div class="lbl">均赢</div></div>
<div class="stat" style="color:#f85149"><div class="val">{avg_loss:.2f}%</div><div class="lbl">均亏</div></div>
<div class="stat"><div class="val">{avg_hold:.0f}b</div><div class="lbl">均持bar</div></div>
</div>
</div>

<div class="flex" style="gap:8px;margin-bottom:12px">
<div class="card" style="flex:1"><h3>📊 Zone类型分布</h3>
<table><tr><th>Zone</th><th>笔数</th><th>WR</th><th>均盈</th></tr>{zone_rows}</table></div>
<div class="card" style="flex:1"><h3>🎯 入场确认</h3>
<table><tr><th>确认</th><th>笔数</th><th>WR</th><th>均盈</th></tr>{conf_rows}</table></div>
</div>

<div class="flex" style="gap:8px;margin-bottom:12px">
<div class="card" style="flex:1"><h3>📈 市场状态</h3>
<table><tr><th>状态</th><th>笔数</th><th>WR</th><th>均盈</th></tr>{state_rows}</table></div>
<div class="card" style="flex:1"><h3>🚪 出场方式</h3>
<table><tr><th>方式</th><th>笔数</th><th>占比</th></tr>{exit_rows}</table></div>
</div>

<div class="card"><h3>🔧 自动诊断建议</h3>
<table><tr><th>优先级</th><th>组件</th><th>问题</th><th>修复方案</th></tr>
{fix_html}
</table></div>

<div class="card"><h3>⚠️ 最差10笔交易</h3>
<table><tr><th>股票</th><th>买入</th><th>卖出</th><th>PnL</th><th>出场</th><th>Zone</th><th>持仓</th></tr>
{worst_rows}
</table></div>
{contract_block}

<div class="card" style="border-left:3px solid var(--accent)"><h3>90日闭环复盘：选股→监控→退出→持续复盘</h3>
<p style="color:#8b949e">实时监控股票来源：/api/picks 读取当前 active picks/watchlist；选进来后监控 SL/TP/当前价。即使止盈/止损触发，也继续用日线追踪未来90个bar，判断信号质量、入场合理性、是否卖早/卖晚、止盈止损是否合理。</p>
<div class="stats">
<div class="stat"><div class="val">{cl_summary.get('max_hold_bars',0)}</div><div class="lbl">最大持仓bar</div></div>
<div class="stat"><div class="val">{cl_summary.get('hold_over_90_count',0)}</div><div class="lbl">超过90日</div></div>
<div class="stat"><div class="val">{cl_summary.get('small_win_below_2_count',0)}</div><div class="lbl">小于2%盈利</div></div>
<div class="stat"><div class="val">{cl_summary.get('loss_inside_1pct_noise_count',0)}</div><div class="lbl">1%内噪音亏损</div></div>
<div class="stat"><div class="val">{cl_summary.get('win_rr_below_2r_count',0)}</div><div class="lbl">盈利低于2R</div></div>
<div class="stat"><div class="val">{cl_summary.get('avg_90d_capture',0)}</div><div class="lbl">90日MFE捕获</div></div>
</div>
<div class="flex" style="gap:8px;margin-top:10px">
<div style="flex:1"><h4>问题计数</h4><table><tr><th>问题</th><th>次数</th></tr>{cl_issue_rows}</table></div>
<div style="flex:2"><h4>执行节奏</h4><ul style="color:#8b949e;line-height:1.8">{cl_schedule_html}</ul></div>
</div>
<h4>90日闭环最差交易</h4>
<table><tr><th>股票</th><th>选股日</th><th>加入日</th><th>入场</th><th>出场</th><th>Zone</th><th>成本线</th><th>波动</th><th>持仓</th><th>PnL</th><th>R</th><th>MFE90</th><th>捕获</th><th>问题</th></tr>{cl_rows}</table>
</div>
</div></body></html>"""



def build_resonance():
    """Multi-Timeframe Resonance Dashboard"""
    if _production_empty_book():
        return _empty_book_page('多周期共振', 'V517 只验证同周期的结构→量价→价格结果→T+1 执行链；没有获验证的周线/60分钟共振，也没有生产选股。')
    picks = reload_picks()
    if not picks:
        return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>MTF共振</title><style>{CSS}</style></head><body>
{build_nav()}
<div class="container"><div class="card"><h2>📡 多周期共振 — 无数据</h2><p>请先运行扫描生成选股</p></div></div></body></html>"""
    
    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>MTF共振</title><meta http-equiv="refresh" content="120"><style>{CSS}
.resonance-strong {{ background: rgba(57,211,83,0.12); border-left: 3px solid #39d353; }}
.resonance-aligned {{ background: rgba(88,166,255,0.08); border-left: 3px solid #58a6ff; }}
.resonance-weak {{ background: rgba(210,153,34,0.08); border-left: 3px solid #d2991d; }}
.resonance-misalign {{ background: rgba(248,81,73,0.06); border-left: 3px solid #f85149; }}
.r-dot {{ display:inline-block;width:10px;height:10px;border-radius:50%%;margin-right:4px; }}
</style></head><body>
{build_nav()}
<div class="container">
<div class="card"><h2>📡 多周期共振监测</h2>
<p style="color:#8b949e">周线趋势 → 日线信号 → 60min时机 → 综合共振评分</p>
<div id="resonance-table">⏳ 加载中...</div>
</div></div>
<script>
async function loadResonance() {{
    try {{
        const r = await fetch('/api/resonance');
        const data = await r.json();
        let html = '<table><thead><tr><th>代码</th><th>信号</th><th>周线</th><th>日线</th><th>60min</th><th>共振</th><th>评分</th></tr></thead><tbody>';
        for (const p of data) {{
            const cls = p.tier === 'STRONG' ? 'resonance-strong' : p.tier === 'ALIGNED' ? 'resonance-aligned' : p.tier === 'WEAK' ? 'resonance-weak' : 'resonance-misalign';
            const wColor = p.weeklyOk ? '#39d353' : '#f85149';
            const dColor = p.dailyOk ? '#39d353' : '#f85149';
            const hColor = p.hourlyOk ? '#39d353' : '#d2991d';
            html += '<tr class="' + cls + '">' +
                '<td class=mono><a href="/kline?s=' + p.symbol + '" style="color:var(--blue)">' + p.symbol + '</a></td>' +
                '<td style="font-size:10px">' + ((p.ctxSeq && p.ctxSeq !== 'None') ? p.ctxSeq : ((p.signalText && p.signalText !== 'None') ? p.signalText : '-')) + '</td>' +
                '<td><span class="r-dot" style="background:' + wColor + '"></span>' + (p.weeklyTrend || '-') + ' ' + (p.weeklyPct || '') + '</td>' +
                '<td><span class="r-dot" style="background:' + dColor + '"></span>' + (p.dailyRegime || '-') + '</td>' +
                '<td><span class="r-dot" style="background:' + hColor + '"></span>' + (p.hourlyPos || '-') + '</td>' +
                '<td style="font-weight:bold;color:' + (p.tier === 'STRONG' ? '#39d353' : p.tier === 'ALIGNED' ? '#58a6ff' : '#d2991d') + '">' + p.tier + '</td>' +
                '<td class=mono>' + p.totalScore + '/10</td></tr>';
        }}
        html += '</tbody></table>';
        document.getElementById('resonance-table').innerHTML = html;
    }} catch(e) {{
        document.getElementById('resonance-table').innerHTML = '<p style="color:#f85149">API错误: ' + e.message + '</p>';
    }}
}}
loadResonance();
setInterval(loadResonance, 60000);
</script></body></html>"""


def _api_resonance(self):
    """API: MTF resonance data for all current picks."""
    picks = reload_picks()
    if not picks:
        self._json([]); return
    
    # Lazy import + cache weekly scores
    try:
        from v25.mtf_resonance import weekly_trend_score
        if not hasattr(self, '_weekly_cache'):
            self._weekly_cache = {}
    except:
        weekly_trend_score = None
    
    result = []
    for p in picks[:30]:  # Top 30 (was 100, too slow)
        sym = p['symbol']
        
        # Weekly trend (cached)
        weekly_ok = False; weekly_trend = '?'; weekly_pct = ''
        if weekly_trend_score:
            try:
                if sym not in self._weekly_cache:
                    w_score, w_details = weekly_trend_score(sym)
                    self._weekly_cache[sym] = (w_score, w_details)
                else:
                    w_score, w_details = self._weekly_cache[sym]
                weekly_ok = w_score >= 2
                weekly_trend = w_details.get('trend', '?')
                weekly_pct = str(w_details.get('pct_from_ma', '')) + '%'
            except: pass
        
        # Daily structure: V32+ picks use market_state; old versions used regime.
        daily_regime = p.get('market_state') or p.get('regime') or 'UNKNOWN'
        daily_ok = daily_regime in ('TREND_UP', 'RANGE')
        
        # Hourly/daily timing confirmation: V32+ uses BULLISH_REJECTION/PINBAR_RECLAIM, older versions used *_ENTRY.
        conf = p.get('conf_type', '')
        hourly_ok = conf in ('SWEEP_ENTRY', 'PINBAR_ENTRY', 'OTE_ENTRY', 'BULLISH_REJECTION', 'PINBAR_RECLAIM')
        hourly_pos = conf.replace('_ENTRY', '') or '?'
        
        # Combined score
        aligned = sum([weekly_ok, daily_ok, hourly_ok])
        if aligned == 3: tier = 'STRONG'; total = 10
        elif aligned == 2: tier = 'ALIGNED'; total = 7
        elif aligned == 1: tier = 'WEAK'; total = 4
        else: tier = 'MISALIGNED'; total = 1
        
        signal_text = (p.get('ctx_seq') or p.get('seq') or p.get('detail') or
                       p.get('v59_setup_family') or p.get('trade_role') or
                       p.get('zone_type') or p.get('signal_type') or p.get('conf_type') or '')
        if str(signal_text) in ('None', 'null'):
            signal_text = ''
        result.append({
            'symbol': sym,
            'ctxSeq': str(signal_text)[:40],
            'signalText': f"{p.get('v59_setup_family') or p.get('trade_role') or ''} {p.get('zone_type') or p.get('signal_type') or ''} {p.get('conf_type') or ''}".strip(),
            'weeklyOk': weekly_ok, 'weeklyTrend': weekly_trend, 'weeklyPct': weekly_pct,
            'dailyOk': daily_ok, 'dailyRegime': daily_regime,
            'hourlyOk': hourly_ok, 'hourlyPos': hourly_pos,
            'tier': tier, 'totalScore': total,
        })
    
    self._json(result)


def build_diagnostics():
    """V30 SMC Diagnostics page — cohort decomposition, root cause attribution."""
    diag_path = Path('/root/.hermes/smc_opt_v31/v31_diagnostics.json') if ACTIVE_VERSION == 'V31' else (Path('/root/.hermes/smc_opt_v30/v30_diagnostics.json') if ACTIVE_VERSION == 'V30' else (Path('/root/.hermes/smc_opt_v29/v29_diagnostics.json') if ACTIVE_VERSION == 'V29' else Path('/root/.hermes/smc_opt_v28/v28_diagnostics.json')))
    if not diag_path.exists():
        return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>SMC 诊断 V30</title><style>{CSS}</style></head><body>
<nav><span class="brand">SMC {FRONTEND_VERSION}</span><a href="/">仪表</a><a href="/kline">K线</a><a href="/backtest">回测</a><a href="/monitor">选股</a><a href="/live">实时</a><a href="/logs">日志</a><a href="/compare">对比</a><a href="/analysis">分析</a><a href="/autopsy">复盘</a><a href="/resonance">共振</a><a href="/diagnostics" class="active">诊断</a></nav>
<div class="container"><div class="card"><h2>SMC V31 诊断</h2><p style="color:#f85149">诊断数据未生成。请先运行 v31_full_scan.py。</p></div></div></body></html>"""

    diag = json.loads(diag_path.read_text())
    ov = diag.get('overview', {})
    co = diag.get('cohorts', {})
    an = diag.get('anomalies', {})
    fixes = diag.get('fix_suggestions', [])

    def _badge(t, v):
        c = {'CRITICAL': '#f85149', 'HIGH': '#d29922', 'MEDIUM': '#58a6ff', 'LOW': '#3fb950'}
        return f'<span style="background:{c.get(t,"#30363d")};color:#fff;padding:2px 6px;border-radius:4px;font-size:10px">{v}</span>'

    def _fix_list(fixes):
        rows = []
        for f in fixes[:10]:
            pri = f.get('priority', '')
            colors = {'CRITICAL': '#f85149', 'HIGH': '#d29922', 'MEDIUM': '#58a6ff', 'LOW': '#3fb950'}
            bc = colors.get(pri, '#30363d')
            rows.append(f'<div class="fix" style="border-color:{bc}"><b>{_badge(pri, pri)} {f.get("issue","")}</b>'
                       f'<br><small style="color:#8b949e">{f.get("fix","")}</small>'
                       f'<br><small class="green">{f.get("impact","")}</small></div>')
        return ''.join(rows)

    def _exit_table(items):
        rows = []
        for c in items[:8]:
            wr = c.get('wr', 0)
            pnl = c.get('avg_pnl', 0)
            wr_cls = 'green' if wr > 55 else 'red'
            pnl_cls = 'green' if pnl > 0 else 'red'
            rows.append(f'<tr><td style="text-align:left">{c.get("cohort","")}</td><td>{c.get("n_trades",0)}</td>'
                       f'<td class="{wr_cls}">{wr}%</td><td class="{pnl_cls}">{pnl}%</td>'
                       f'<td>{_badge(c.get("severity",""),c.get("severity",""))}</td></tr>')
        return ''.join(rows)

    def _market_table(items):
        rows = []
        for c in items[:8]:
            wr = c.get('wr', 0)
            sl = c.get('sl_rate', 0)
            wr_cls = 'green' if wr > 55 else 'red'
            sl_cls = 'red' if sl > 35 else ''
            rows.append(f'<tr><td style="text-align:left">{c.get("cohort","")}</td><td>{c.get("n_trades",0)}</td>'
                       f'<td class="{wr_cls}">{wr}%</td><td class="{sl_cls}">{sl}%</td>'
                       f'<td style="font-size:10px">{c.get("fix","")}</td></tr>')
        return ''.join(rows)

    def _simple_table(items, fields):
        rows = []
        for c in items[:8]:
            cells = ''.join(f'<td>{c.get(f,"")}</td>' for f in fields)
            rows.append(f'<tr><td style="text-align:left">{c.get("cohort","")}</td>{cells}</tr>')
        return ''.join(rows)

    def _quality_tables(grade_data):
        parts = []
        for grade_name, items in grade_data.items():
            rows = []
            for i in items[:8]:
                wr = i.get('wr', 0)
                pnl = i.get('avg_pnl', 0)
                wr_cls = 'green' if wr > 55 else 'red'
                pnl_cls = 'green' if pnl > 0 else 'red'
                rows.append(f'<tr><td style="text-align:left">{i.get("grade","")}</td><td>{i.get("n_trades",0)}</td>'
                           f'<td class="{wr_cls}">{wr}%</td><td class="{pnl_cls}">{pnl}%</td></tr>')
            parts.append(f'<div class="card"><h4>{grade_name}</h4><table><tr><th>等级</th><th>交易</th><th>WR</th><th>均盈</th></tr>{"".join(rows)}</table></div>')
        return ''.join(parts)

    fix_list = _fix_list(fixes)
    exit_rows = _exit_table(co.get('by_exit_reason', []))
    market_rows = _market_table(co.get('by_market_state', []))
    zone_rows = _simple_table(co.get('by_zone_type', []), ['n_trades', 'wr', 'avg_pnl'])
    resonance_rows = _simple_table(co.get('by_resonance', []), ['n_trades', 'wr', 'avg_pnl'])
    quality_section = _quality_tables(co.get('by_quality_grade', {}))

    # Signal ranking tables
    sr = diag.get('signal_ranking', {})
    fa = diag.get('failure_attribution', [])

    def _rank_table(items, title, limit=8):
        if not items: return ''
        rows_list = []
        for i in items[:limit]:
            wr = i.get('wr', 0)
            pnl = i.get('avg_pnl', 0)
            wr_cls = 'green' if wr > 65 else ('red' if wr < 55 else '')
            pnl_cls = 'green' if pnl > 0 else 'red'
            rows_list.append(
                f'<tr><td style="text-align:left;font-size:10px">{i.get("group","")[:55]}</td>'
                f'<td>{i.get("n",0)}</td>'
                f'<td class="{wr_cls}">{wr}%</td>'
                f'<td class="red">{i.get("sl_rate",0)}%</td>'
                f'<td class="{pnl_cls}">{pnl:+.2f}%</td>'
                f'<td>{i.get("total_pnl",0):+.0f}%</td></tr>'
            )
        rows = ''.join(rows_list)
        return f'<div><h4>{title}</h4><table><tr><th>群组</th><th>n</th><th>WR</th><th>SL</th><th>均盈</th><th>累计</th></tr>{rows}</table></div>'

    # Build ranking sections
    rank_sections = ''
    for key, title in [('by_ctx_seq', '信号链排序'), ('by_resonance_zone', '共振×Zone'), 
                        ('by_market_conf', '市场状态×确认'), ('by_zone_conf', 'Zone×确认')]:
        items = sr.get(key, [])
        if items:
            # worst 5 + best 3
            worst = items[:5]
            best = list(reversed(items[-3:]))
            rank_sections += f'<div style="flex:1;min-width:280px">'
            rank_sections += _rank_table(worst, f'{title} — 最差')
            rank_sections += _rank_table(best, f'{title} — 最优', 3)
            rank_sections += '</div>'

    # Failure attribution
    attr_html = ''
    for a in fa[:8]:
        causes = ' | '.join(a.get('causes', []))
        sev = a.get('severity', 'MEDIUM')
        colors = {'CRITICAL': '#f85149', 'HIGH': '#d29922', 'MEDIUM': '#58a6ff'}
        attr_html += f'<tr><td style="text-align:left;font-size:10px">{a.get("group","")[:60]}</td>'
        attr_html += f'<td>{a.get("n",0)}</td><td class="red">{a.get("wr",0)}%</td>'
        attr_html += f'<td>{a.get("sl_rate",0)}%</td><td>{a.get("avg_quality",0)}</td>'
        attr_html += f'<td style="font-size:9px;max-width:250px">{causes}</td>'
        attr_html += f'<td><span style="color:{colors.get(sev,"#8b949e")};font-weight:bold">{sev}</span></td></tr>'

    wr_val = ov.get('wr', 0)
    pnl_val = ov.get('total_pnl', 0)

    sl_rows = []
    for g in an.get('high_sl_groups', [])[:10]:
        sl_rows.append(f'<tr><td style="text-align:left;font-size:10px">{g.get("group","")[:60]}</td>'
                      f'<td>{g.get("n_trades",0)}</td><td>{g.get("sl_hits",0)}</td>'
                      f'<td class="red">{g.get("sl_rate",0)}%</td></tr>')
    sl_table = ''.join(sl_rows)

    rr_rows = []
    for g in an.get('high_rr_groups', [])[:10]:
        rr_rows.append(f'<tr><td style="text-align:left;font-size:10px">{g.get("group","")[:60]}</td>'
                      f'<td>{g.get("n_trades",0)}</td><td class="green">{g.get("avg_rr",0)}</td>'
                      f'<td>{g.get("wr",0)}%</td><td>{g.get("sl_rate",0)}%</td></tr>')
    rr_table = ''.join(rr_rows)

    html = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><meta http-equiv="refresh" content="300"><title>SMC V31 诊断</title>
<style>{CSS}
.overview-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin-bottom:12px}}
.ov-card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px;text-align:center}}
.ov-card .val{{font-size:24px;font-weight:bold}}
.ov-card .lbl{{font-size:11px;color:#8b949e}}
table{{width:100%;border-collapse:collapse;font-size:11px}}
th,td{{padding:4px 8px;text-align:right;border-bottom:1px solid #21262d}}
th{{background:#161b22;color:#8b949e;font-size:10px;position:sticky;top:0}}
tr:hover{{background:#1c2128}}
.fix{{margin:6px 0;padding:8px 12px;border-radius:6px;border-left:3px solid}}
.green{{color:#3fb950}} .red{{color:#f85149}} .yellow{{color:#d29922}}
</style></head><body>
<nav><span class="brand">SMC {FRONTEND_VERSION}</span><a href="/">仪表</a><a href="/kline">K线</a><a href="/backtest">回测</a><a href="/monitor">选股</a><a href="/live">实时</a><a href="/logs">日志</a><a href="/compare">对比</a><a href="/analysis">分析</a><a href="/autopsy">复盘</a><a href="/resonance">共振</a><a href="/diagnostics" class="active">诊断</a></nav>
<div class="container">
<h2>SMC V31 诊断报告 <span style="font-size:12px;color:#8b949e">{diag.get('generated_at','')}</span></h2>

<div class="overview-grid">
<div class="ov-card"><div class="lbl">总交易</div><div class="val">{ov.get('n_trades',0)}</div></div>
<div class="ov-card"><div class="lbl">胜率</div><div class="val {'green' if wr_val > 55 else 'red'}">{wr_val}%</div></div>
<div class="ov-card"><div class="lbl">总PnL</div><div class="val {'green' if pnl_val > 0 else 'red'}">{pnl_val}%</div></div>
<div class="ov-card"><div class="lbl">均盈</div><div class="val">{ov.get('avg_pnl',0)}%</div></div>
<div class="ov-card"><div class="lbl">均持</div><div class="val">{ov.get('avg_hold_bars',0)}日</div></div>
<div class="ov-card"><div class="lbl">均质量</div><div class="val">{ov.get('avg_quality',0)}</div></div>
<div class="ov-card"><div class="lbl">选股</div><div class="val">{ov.get('n_picks',0)}</div></div>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
<div>
<h3>自动修复建议</h3>
{fix_list}
</div>
<div>
<h3>出场原因分析</h3>
<table><tr><th>原因</th><th>交易</th><th>WR</th><th>均盈</th><th>严重度</th></tr>
{exit_rows}
</table>
</div>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-top:12px">
<div><h3>市场状态</h3><table><tr><th>状态</th><th>交易</th><th>WR</th><th>SL率</th><th>建议</th></tr>
{market_rows}
</table></div>
<div><h3>Zone类型</h3><table><tr><th>类型</th><th>交易</th><th>WR</th><th>均盈</th></tr>
{zone_rows}
</table></div>
<div><h3>共振</h3><table><tr><th>共振</th><th>交易</th><th>WR</th><th>均盈</th></tr>
{resonance_rows}
</table></div>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px">
<div><h3>高SL率群组</h3><table><tr><th>群组</th><th>交易</th><th>SL数</th><th>SL率</th></tr>
{sl_table}
</table></div>
<div><h3>高RR群组</h3><table><tr><th>群组</th><th>交易</th><th>RR</th><th>WR</th><th>SL率</th></tr>
{rr_table}
</table></div>
</div>

<div style="margin-top:12px"><h3>信号质量分层</h3>
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px">
{quality_section}
</div></div>

<div style="margin-top:12px"><h3>信号排名分析</h3>
<div style="display:flex;gap:12px;flex-wrap:wrap">
{rank_sections}
</div></div>

<div style="margin-top:12px"><h3>失败归因分析</h3>
<table><tr><th>组</th><th>n</th><th>WR</th><th>SL率</th><th>Q</th><th>原因</th><th>严重度</th></tr>
{attr_html}
</table></div>

<p style="font-size:10px;color:#8b949e;margin-top:16px">Auto-refresh: 5min | {diag.get('summary','')}</p>
</div></body></html>"""

    return html


def build_effort_result():
    """V517 read-only surface: audit artifacts + scanner-time state, never production picks."""
    return f'''<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>V517 量价吸收研究</title><style>{CSS}
    .gate-pass{{color:#3fb950;font-weight:bold}} .gate-fail{{color:#f85149;font-weight:bold}}
    .section-note{{color:#8b949e;font-size:12px}} table{{width:100%;border-collapse:collapse}} th,td{{padding:7px;border-bottom:1px solid #30363d;text-align:left;font-size:12px}}
    </style></head><body>{build_nav()}<div class="container">
    <div class="card" style="border-left:4px solid #58a6ff"><h2>V517 Daily Effort–Result Absorption</h2>
    <p id="state" class="section-note">加载中…</p><p class="section-note">独立量价信息本体：已确认摆动低点 → 高量下扫收回 → 下一日突破 sweep high → 后一交易日开盘。此页只读呈现冻结研究与 durable pending；后续研究门禁变化只冻结新准入，不能把已授权的当前 epoch pending 改写为历史回填。</p></div>
    <div id="metrics" class="stats"></div>
    <div class="card"><h3>信号与共振链</h3><div id="resonance"></div><p class="section-note">K线默认叠加 Pine-like 可视 SMC 上下文（Swing / OB / FVG / Sweep / BOS / CHOCH）；它只用于逐笔图形核验，不会扩张 V517 的 frozen replay 入场集合。</p></div>
    <div class="card"><h3>回测：冻结严格 T+1</h3><div id="yearly"></div><p class="section-note">回测交易仅用于审计/复盘，绝不作为当前选股来源。</p></div>
    <div class="card" style="border-left:3px solid #f85149"><h3>结构RR≥1.5 可行性审计（V525）</h3><div id="rr-feasibility"></div></div>
    <div class="card"><h3>当前选股 / Scanner-time 状态</h3><div id="picks"></div></div>
    <div class="card"><h3>逐笔复盘与 K 线</h3><div id="trades"></div></div>
    <div class="card"><h3>失败与出场归因</h3><div id="analysis"></div></div>
    <div class="card"><h3>验证门禁与架构文档</h3><div id="audit"></div><p class="section-note">前端同步架构：/root/.hermes/smc_audit/V517_FRONTEND_SYNC_ARCHITECTURE.md；研究闭环：/root/.hermes/skills/trading/smc-core-concepts/references/v517-v523-effort-result-absorption-closure.md</p></div>
    </div><script>
    const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
    const n=v=>Number(v||0).toFixed(2); const d=v=>String(v||'-').replace(/^(\\d{{4}})(\\d{{2}})(\\d{{2}})$/,'$1-$2-$3');
    const table=(heads,rows)=>'<table><thead><tr>'+heads.map(x=>'<th>'+esc(x)+'</th>').join('')+'</tr></thead><tbody>'+(Array.isArray(rows)?rows.join(''):String(rows||''))+'</tbody></table>';
    const row=cells=>'<tr>'+cells.map(x=>'<td>'+x+'</td>').join('')+'</tr>';
    async function load(){{
      const r=await fetch('/api/effort-result'); const x=await r.json(); const m=x.metrics||{{}};
      document.getElementById('state').innerHTML='<b>'+esc(x.research_result)+'</b> | 实时状态：<b>'+esc(x.live_release_state)+'</b> | BUY：<b style="color:#f85149">禁用</b> | '+esc(x.live_release_rule||'');
      document.getElementById('metrics').innerHTML=[['冻结交易',m.n],['Gross WR',n(m.gross_wr_pct)+'%'],['AvgNet', '+'+n(m.avg_net_pnl_pct)+'%'],['PF',n(m.profit_factor)],['Payoff',n(m.payoff_rr)],['T+1违规',((x.audit.trade_integrity||{{}}).t1_violations??0)]].map(a=>'<div class="stat"><div class="val">'+esc(a[1])+'</div><div class="lbl">'+esc(a[0])+'</div></div>').join('');
      document.getElementById('resonance').innerHTML=table(['层','必要条件','状态'],(x.resonance.layers||[]).map(v=>row([esc(v.layer),esc(v.event),'<span class="gate-pass">'+esc(v.state)+'</span>']))+'<p class="section-note">'+esc(x.resonance.note)+'</p>');
      document.getElementById('yearly').innerHTML=table(['年','n','WR','AvgNet','PF','Payoff','TP/SL/Time'],(x.yearly||[]).map(y=>row([y.year,y.n,n(y.gross_wr_pct)+'%',(y.avg_net_pnl_pct>=0?'+':'')+n(y.avg_net_pnl_pct)+'%',n(y.profit_factor),n(y.payoff_rr),esc(JSON.stringify(y.exit_counts||{{}}))])));
      const rg=x.rr_feasibility||{{}}, ro=rg.overall||{{}}; document.getElementById('rr-feasibility').innerHTML='<p><b style="color:#f85149">'+esc(rg.decision||'NO_AUDIT')+'</b></p><p>V517 原始 seeds '+esc(rg.source_seed_count)+'；入场前仅按可见结构目标/结构止损筛到 RR≥1.5 的 '+esc(rg.feasible_seed_count)+'；逐年 '+esc(JSON.stringify(rg.preentry_year_counts||{{}}))+'。</p><p>支持门禁 '+esc(JSON.stringify(rg.support_checks||{{}}))+'；筛后回放 n='+esc(ro.n)+' / WR='+esc(ro.gross_wr_pct)+'% / AvgNet='+esc(ro.avg_net_pnl_pct)+'%。结论：不能用少量高RR子集替代全市场生产策略。</p>';
      const p=x.picks||[], blocked=x.blocked_current_candidates||[]; const currentRows=p.length?p:blocked; const currentLabel=p.length?'已授权 pending（等待精确下一开盘验证）':(blocked.length?'当前扫描命中，但生产门禁阻断（只读，不可执行）':'无当前候选；保持 EMPTY / NO_BUY，不回填历史交易。'); document.getElementById('picks').innerHTML='<p class="section-note">epoch='+esc(x.scanner.epoch_id)+' / 市场日='+esc(x.scanner.market_date)+' / 已授权 pending='+esc(x.scanner.pending_next_open_count)+' / 当前扫描命中='+esc(blocked.length||p.length)+' / 来源='+esc(x.scanner.pending_source)+' / shadow decision='+esc(x.shadow.decision)+'</p><p class="'+(blocked.length?'gate-fail':'section-note')+'">'+esc(currentLabel)+'</p>'+(currentRows.length?table(['代码','状态','响应日','SL','目标','动作/阻断原因'],currentRows.map(v=>row([esc(v.symbol),esc(v.state),d(v.response_date||v.pick_date),n(v.stop||v.sl_price),n(v.target||v.tp1),'<span style="color:#f85149">'+esc(v.trade_action||v.blocked_reason)+'</span>']))):'');
      const ts=x.trades||[]; document.getElementById('trades').innerHTML=table(['代码','sweep','响应','买入','卖出','净PnL','出场','K线'],ts.map(v=>row(['<a href="/kline?symbol='+encodeURIComponent(v.symbol)+'&ver=V517">'+esc(v.symbol)+'</a>',d(v.sweep_date),d(v.response_date),d(v.entry_date),d(v.exit_date),'<span class="'+(Number(v.pnl_pct)>0?'gate-pass':'gate-fail')+'">'+n(v.pnl_pct)+'%</span>',esc(v.exit_reason),'<a href="/kline?symbol='+encodeURIComponent(v.symbol)+'&ver=V517">查看</a>'])));
      document.getElementById('analysis').innerHTML=table(['出场','n','WR','AvgNet'],(x.analysis.exit_reason||[]).map(v=>row([esc(v.exit_reason),v.n,n(v.wr_pct)+'%',n(v.avg_net_pnl_pct)+'%'])));
      const checks=x.audit.checks||{{}}, inv=x.audit.metric_invariants||{{}}; document.getElementById('audit').innerHTML=table(['门禁','结果'],Object.entries({{...checks,...inv}}).map(([k,v])=>row([esc(k),'<span class="'+(v?'gate-pass':'gate-fail')+'">'+esc(v)+'</span>'])));
    }} load().catch(e=>document.getElementById('state').innerHTML='<span class="gate-fail">加载失败 '+esc(e)+'</span>');
    </script></body></html>'''


def build_docs():
    if _production_empty_book():
        registry = _production_registry()
        epoch = registry.get('data_epoch') or {}
        research = v517_frontend.bundle()
        metrics = research.get('metrics') or {}
        return f'''<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>SMC EMPTY_BOOK 架构</title><style>{CSS} pre{{font-family:monospace;white-space:pre-wrap;line-height:1.65}}</style></head><body>{build_nav()}<div class="container"><div class="card"><h2>架构文档 — EMPTY_BOOK + V517 只读研究</h2><pre>生产 Registry: EMPTY_BOOK
数据 epoch: {html.escape(str(epoch.get('epoch_id') or '-'))}
市场日: {html.escape(_fmt_date_label(epoch.get('market_date')))}
生产策略: 无
生产写入 / watchlist 写入 / BUY: false / false / false

生产面
- /api/summary、/api/picks、/api/live-prices 只返回当前 epoch 的 EMPTY_BOOK / 空候选。
- /backtest、/analysis、/autopsy、/compare、/resonance、/stoploss 禁止使用 V88/V185 等历史 artifacts。
- 当前 0 个候选不是错误；不回填历史交易或历史 active picks。

V517 研究面（只读，不是生产版本）
- 本体: confirmed swing low → high-volume SSL reclaim → response break → following-session open。
- 冻结回放: {html.escape(str(metrics.get('n', 0)))} 笔；Gross WR: {html.escape(str(metrics.get('gross_wr_pct', '-')))}%；AvgNet: {html.escape(str(metrics.get('avg_net_pnl_pct', '-')))}%。
- K线仅绘制 V517 frozen replay 的因果节点。若个股不在该 replay，显示“无 V517 回放信号”，不从旧版本补信号。
- API: /api/effort-result；K线: /api/kline_full?symbol=代码&amp;tf=daily&amp;ver=V517。

历史 artifacts
- V88/V185/V90/V103A 文件仅保留审计可追溯性，不能作为当前生产、当前选股或当前风险指标来源。</pre><p><a href="/effort-result" style="color:#58a6ff">V517 研究回放</a>　<a href="/kline?ver=V517" style="color:#58a6ff">V517 K线</a></p></div></div></body></html>'''
    active_paths = _active_version_paths(ACTIVE_VERSION) or {}
    metrics = reload_metrics()
    report_metrics = metrics.get('metrics', metrics if isinstance(metrics, dict) else {})
    autopsy = metrics.get('autopsy_summary', {}) if isinstance(metrics, dict) else {}
    checks = metrics.get('checks', {}) if isinstance(metrics, dict) else {}
    pick_contract = get_pick_contract_summary()
    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>SMC 架构文档</title><style>{CSS} pre{{font-family:"JetBrains Mono",monospace;font-size:11px;line-height:1.6;color:#c9d1d9;overflow-x:auto;white-space:pre-wrap}}</style></head><body>
{build_nav()}
<div class="container">
<div class="card"><h2>📐 架构文档 — SMC {FRONTEND_VERSION} 前端/回测/选股同步版</h2>
<pre>
═══════════════════════════════════════════════════════════════
  SMC {FRONTEND_VERSION} 全栈交易系统架构文档
  Frontend: /root/.hermes/scripts/smc_unified.py
  TradeFile: {ACTIVE_TRADE_FILE}
  PickFile/Watchlist: {ACTIVE_PICK_FILE}
  Engine: {active_paths.get('script','')}
  OutputDir: {active_paths.get('out_dir','')}
  Metrics: {active_paths.get('metrics','')}
  Last Update: 2026-06-15
═══════════════════════════════════════════════════════════════

0. 当前生产契约 — V88 外壳 + V102 平衡放量门禁层
───────────────────────────────────────────────────────────

  当前状态：
    - ACTIVE_VERSION={ACTIVE_VERSION} 是数据路由外壳；FRONTEND_VERSION={FRONTEND_VERSION} 是页面显示生产版本
    - /api/picks 与 /api/live-prices 已读取当前 active picks，并完成字段合同回填
    - /backtest、/analysis、/autopsy、/kline 已读取当前 promoted trades 缓存；V88 外壳仍作为前端路由兼容层
    - /docs 已更新为 V102/V101 生产状态说明

  V99/V100 经济性审计结论：
    - V99 gross WR=95.97%，但 net WR(>=0.8%)=56.27%，小盈利污染来自 V99_PROFIT_PROTECT_STOP
    - V100 修复为结构 TP2/TP3 合同 + net>=0.8% 成功口径，生产A=59笔 / net WR=89.83% / T+1违规=0

  V101/V102 生产方向（已接入）：
    - V101 OutputDir: /root/.hermes/smc_opt_v101_mtf_dna_combo_contract
    - V102 OutputDir: {active_paths.get('out_dir','')}
    - V101 保留 V100 A 生产白名单，新增 weekly/daily/60min 多周期状态、每股 SMC DNA、组合合同字段
    - V102 在 V101 字段合同上增加 balanced volume gate，不改变前端同步字段口径
    - 生产组合: REVERSAL_SSL_CHOCH_DEMAND_OB_STRUCTURAL_5R；V102 同时保留已验证的平衡放量候选行
    - BOS候选组合: CONTINUATION_BOS_PULLBACK_STRUCTURAL 独立候选池，未通过质量审计前不混入核心反转池
    - V101 生产A: 59笔 / net WR=89.83% / avgNetPnL=3.3684% / SL率=10.17% / T+1违规=0
    - V102 当前汇总以 /api/summary 为准: trades={report_metrics.get('n_trades', report_metrics.get('total_trades',0))} / WR={report_metrics.get('wr', report_metrics.get('win_rate',0))}% / avgPnL={report_metrics.get('avg_pnl',0)}%

  当前选股合同:
    - ActiveCandidates: {pick_contract.get('active_pick_count',0)}
    - WatchOnly: {pick_contract.get('watch_only_count',0)}
    - HistoricalBest: {pick_contract.get('historical_best_count',0)}
    - RawFile: {pick_contract.get('raw_pick_file_count',0)}
    - active_picks_not_historical_all_market: {pick_contract.get('active_picks_not_historical_all_market')}

  统一字段合同（选股页 / 实时页 / K线API / 回测 / 分析 / 复盘）:
    - 选股日/加入日/买入日: select_date / pick_date / join_date / entry_date
    - Zone字段: zone_type / zone_low / zone_high / dz_low / dz_high
    - 成本线字段: smart_money_cost / cost_line / v25_cost_line
    - 波动字段: volatility_pct / v25_vol_class
    - 引擎字段: engine / signal_type / conf_type
    - 后端统一入口: _apply_smc_field_contract(row, default_engine)

  当前回测结果:
    - trades: {report_metrics.get('n_trades', report_metrics.get('total_trades',0))}
    - WR: {report_metrics.get('wr', report_metrics.get('win_rate',0))}%
    - SL率: {report_metrics.get('sl_rate',0)}%
    - avgPnL: {report_metrics.get('avg_pnl',0)}%
    - totalPnL: {report_metrics.get('total_pnl',0)}%
    - avg_mfe_capture: {autopsy.get('avg_mfe_capture',0)}
    - sold_early_rate: {autopsy.get('sold_early_rate',0)}%
    - fake_sl_rate: {autopsy.get('fake_sl_rate',0)}%
    - errors_count: {checks.get('errors_count')}
    - watch_errors_count: {checks.get('watch_errors_count')}

  手动重跑:
    - POST /api/backtest/run 或 POST /api/reselect
    - 当前执行: python3 {active_paths.get('script','')}
    - 重跑成功后清空 _TRADES_CACHE/_PICKS_CACHE/_SUMMARY_CACHE，下一次请求强制读盘

  K线图同步:
    - /kline 默认数据路由为 {ACTIVE_VERSION}；页面生产标识为 {FRONTEND_VERSION}，V100 通过 V88 外壳路由读取生产数据
    - /api/kline_full?symbol=代码&tf=daily&ver=V88
    - 信号源：V100 沿用 V98 同源结构信号，只做上层结构/净收益门禁，不改信号检测
    - 高亮链路使用 source_event_idx → zone_idx → retrace_index → conf_index
    - BOS/CHOCH/MSS 附带 wave_ref_idx/date/label/price/distance

1. 系统概览
───────────────────────────────────────────────────────────

本系统是一个完整的 SMC (Smart Money Concepts) 交易分析与回测平台，包含:
  ├── 信号检测: /root/.hermes/scripts/v25/smc_core_pine_like.py + smc_core_luxalgo_v34.py
  ├── 回测/选股: {active_paths.get('script','')}
  ├── 前端服务: /root/.hermes/scripts/smc_unified.py
  ├── K线缓存: /root/.hermes/kline_cache/
  └── 输出目录: {active_paths.get('out_dir','')}

2. 前端同步面
───────────────────────────────────────────────────────────
  /               仪表盘：使用 ACTIVE_VERSION 的 trades/picks
  /backtest       回测：使用 ACTIVE_TRADE_FILE
  /monitor        选股：使用 ACTIVE_PICK_FILE，ACTIVE_CANDIDATE only
  /live           实时：使用当前 active picks
  /kline          K线：默认 V49，可切换历史版本
  /analysis       分析：使用当前 active trades
  /autopsy        复盘：使用当前 active trades
  /resonance      共振：使用当前 active picks/trades
  /docs           当前文档：动态读取 active_paths/metrics

3. API 合同
───────────────────────────────────────────────────────────
  GET /api/summary
  GET /api/picks
  GET /api/picks/contract
  GET /api/picks/rejects
  GET /api/kline_full?symbol=600519.SH&tf=daily&ver={ACTIVE_VERSION}
  POST /api/backtest/run
  POST /api/reselect

4. V49 当前定位
───────────────────────────────────────────────────────────
  生产默认版：是
  并行候选版：否
  V48.1/V47.2/V46.1保留：可在K线下拉/API ver 参数中回看

═══════════════════════════════════════════════════════════════
  本文档供架构审计、代码审查和故障排查使用。
  最后更新: 2026-05-26
═══════════════════════════════════════════════════════════════
</pre></div></div></body></html>"""


def build_v144_preview():
    """Read-only V144 lifecycle preview page; consumes dry-run API only."""
    return f"""<!DOCTYPE html><html lang=\"zh\"><head><meta charset=\"UTF-8\"><title>V144 只读预览</title><style>{CSS}
.v144-status {{ display:inline-block;padding:2px 7px;border-radius:10px;font-size:10px;font-weight:bold }}
.v144-cancel {{ background:#3a1111;color:#ff7b72;border:1px solid #f85149 }}
.v144-keep {{ background:#0f2a18;color:#3fb950;border:1px solid #238636 }}
.v144-note {{ background:#251a05;color:#d29922;border:1px solid #8a6d1d }}
.v144-risk {{ background:#152033;color:#58a6ff;border:1px solid #1f6feb }}
.scope-btn {{ background:#21262d;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;padding:5px 10px;margin-right:6px;cursor:pointer }}
.scope-btn.active {{ background:#1f6feb;color:#fff }}
</style></head><body>{build_nav()}
<div class=\"container\">
<div class=\"card\" style=\"border-left:3px solid #58a6ff\">
<h2>V144 生命周期 dry-run 预览 <span style=\"font-size:12px;color:#8b949e\">shadow-only / display-only / NO_BUY</span></h2>
<p style=\"color:#8b949e\">独立只读页面；不读取/覆盖 /api/picks、/api/live-prices、watchlist、monitor state 或 morning push。所有行 tradable=false、buy_enabled=false、trade_action=NO_BUY。</p>
<div style=\"margin:10px 0\">
<button class=\"scope-btn active\" id=\"btn-latest_per_symbol\" onclick=\"loadPreview('latest_per_symbol')\">最新每股</button>
<button class=\"scope-btn\" id=\"btn-recent45\" onclick=\"loadPreview('recent45')\">近45交易日</button>
<button class=\"scope-btn\" id=\"btn-all\" onclick=\"loadPreview('all')\">全部</button>
<span id=\"v144-meta\" style=\"font-size:12px;color:#8b949e;margin-left:8px\">加载中...</span>
</div>
<div id=\"v144-summary\" class=\"stats\"></div>
<div id=\"v144-table\">加载中...</div>
</div></div>
<script>
let currentScope = 'latest_per_symbol';
function esc(v) {{ return String(v ?? '').replace(/[&<>\"']/g, s => ({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}}[s])); }}
function shortDate(v) {{ v=String(v||''); return v.length>=8 ? v.slice(4,6)+'-'+v.slice(6,8) : (v||'-'); }}
function statusClass(s) {{
  if(s==='CANCEL_AFTER_ENTRY_DAY_CLOSE') return 'v144-cancel';
  if(s==='KEEP_WATCH_NO_LATE_FAILURE') return 'v144-keep';
  if(s==='INTRADAY_RISK_NOTE_ONLY') return 'v144-risk';
  return 'v144-note';
}}
function statusLabel(s) {{
  return {{CANCEL_AFTER_ENTRY_DAY_CLOSE:'盘后取消',KEEP_WATCH_NO_LATE_FAILURE:'继续观察',INTRADAY_RISK_NOTE_ONLY:'盘中风险备注',PRE_BUY_GAP_NOTE_ONLY:'买前缺口备注'}}[s] || s || '-';
}}
async function loadPreview(scope) {{
  currentScope = scope;
  for(const x of ['latest_per_symbol','recent45','all']) document.getElementById('btn-'+x).classList.toggle('active', x===scope);
  const meta = document.getElementById('v144-meta');
  meta.textContent = '加载中...';
  const r = await fetch('/api/v144-dry-run-preview?scope='+encodeURIComponent(scope));
  const d = await r.json();
  const rows = d.rows || [];
  const bad = rows.filter(x => x.tradable || x.buy_enabled || String(x.trade_action||'') !== 'NO_BUY').length;
  const counts = {{}};
  for(const x of rows) counts[x.v144_status || x.lifecycle_status || x.v143_lifecycle_status || 'UNKNOWN'] = (counts[x.v144_status || x.lifecycle_status || x.v143_lifecycle_status || 'UNKNOWN'] || 0) + 1;
  meta.textContent = 'scope=' + esc(d.scope) + ' | rows=' + rows.length + ' | BUY-like=' + bad;
  document.getElementById('v144-summary').innerHTML = Object.entries(counts).map(([k,v]) => '<div><b>'+v+'</b><span>'+statusLabel(k)+'</span></div>').join('') || '<div><b>0</b><span>无数据</span></div>';
  const show = rows.slice(0, 200);
  let html = '<table><thead><tr><th>代码</th><th>状态</th><th>NO_BUY</th><th>日期</th><th>Zone</th><th>入场/风险</th><th>原因</th><th>生命周期</th></tr></thead><tbody>';
  for(const p of show) {{
    const st = p.v144_status || p.lifecycle_status || p.v143_lifecycle_status || '-';
    const zone = (p.zone_low || p.zone_high) ? (Number(p.zone_low||0).toFixed(2)+'~'+Number(p.zone_high||0).toFixed(2)) : '-';
    const reason = p.v144_reason || p.lifecycle_reason || p.v143_lifecycle_reason || p.cancel_reason || p.note || '-';
    const sym = p.symbol || '-';
    html += '<tr><td class=mono><a href="/kline?s='+encodeURIComponent(sym)+'" style="color:var(--blue)">'+esc(sym)+'</a></td>'+
      '<td><span class="v144-status '+statusClass(st)+'">'+esc(statusLabel(st))+'</span></td>'+
      '<td class=mono style="color:#8b949e">'+esc(p.trade_action || 'NO_BUY')+'</td>'+
      '<td class=mono>'+shortDate(p.entry_date || p.pick_date || p.reclaim_date)+'</td>'+
      '<td class=mono>'+esc(zone)+'</td>'+
      '<td class=mono>entry '+Number(p.entry_price||0).toFixed(2)+'<br><span style="font-size:9px;color:#8b949e">risk '+Number(p.risk_pct||p.v138_risk_pct||0).toFixed(2)+'%</span></td>'+
      '<td style="font-size:10px;color:#d29922">'+esc(reason).slice(0,80)+'</td>'+
      '<td style="font-size:10px;color:#8b949e">shadow_only='+esc(p.shadow_only)+' / tradable='+esc(p.tradable)+' / buy_enabled='+esc(p.buy_enabled)+'</td></tr>';
  }}
  html += '</tbody></table>';
  if(rows.length > show.length) html += '<p style="color:#8b949e;margin-top:8px">仅显示前 '+show.length+' 行；完整数据见 /api/v144-dry-run-preview?scope='+esc(scope)+'</p>';
  document.getElementById('v144-table').innerHTML = html;
}}
loadPreview(currentScope).catch(e => {{ document.getElementById('v144-table').innerHTML='<p style="color:#f85149">加载失败 '+esc(e)+'</p>'; }});
</script></body></html>"""


def build_live():
    """实时监控页面 — AJAX局部刷新,不重载整页"""
    # FIX(2026-08-22): COMBO 实时监控（模拟持仓 + 实时价格记录，导航"实时"可达）
    if _production_registry().get('production_strategy') == 'COMBO_SMC_EVENT':
        try:
            led = json.loads(Path('/root/.hermes/smc_monitor/paper_ledger.json').read_text(encoding='utf-8'))
        except Exception:
            led = []
        active = [t for t in led if t.get('status') != 'CLOSED']
        active.sort(key=lambda t: (int(t.get('rank_score', 0) or 0), str(t.get('pick_date', t.get('signal_date', '')))), reverse=True)
        # FIX(2026-08-22): 盈亏统计（活跃持仓）
        _pnls = [t.get('mark_pnl_pct') for t in active if t.get('mark_pnl_pct') is not None]
        _wins = [x for x in _pnls if x > 0]
        _sum = sum(_pnls) if _pnls else 0
        _avg = _sum / len(_pnls) if _pnls else 0
        _winr = 100 * len(_wins) / len(_pnls) if _pnls else 0
        _t1_locked = sum(1 for t in active if t.get('t1_locked'))
        rows = ''.join(
            f'<tr><td class="mono"><a href="/kline?symbol={html.escape(str(t.get("code",""))) + ".SH" if str(t.get("code","")).startswith("6") else html.escape(str(t.get("code",""))) + ".SZ"}">{html.escape(str(t.get("code","")))}</a></td>'
            f'<td>{html.escape(str(t.get("name","")))}</td>'
            f'<td>{html.escape(str(t.get("signal_combo", t.get("source",""))))}</td>'
            f'<td>{html.escape(str(t.get("signal_date","")))}</td>'
            f'<td class="mono">{t.get("entry_price",0):.3f}</td>'
            f'<td class="mono" style="color:#3fb950">{t.get("tp1",0):.3f}</td>'
            f'<td class="mono" style="color:#2ea043">{t.get("tp2",0):.3f}</td>'
            f'<td class="mono" style="color:#1f883d">{t.get("tp3",0):.3f}</td>'
            f'<td class="mono" style="color:#56d364">{t.get("tp4", t.get("tp_price",0)):.3f}</td>'
            f'<td class="mono" style="color:#f85149">{t.get("sl1", t.get("sl_price",0)):.3f}</td>'
            f'<td class="mono" style="color:#ff6b6b">{t.get("sl2",0):.3f}</td>'
            f'<td>{html.escape(str(t.get("status","")))}</td>'
            f'<td>{"🔒T+1锁定" if t.get("t1_locked") else ("TP1✓" if t.get("tp1_hit") else "-")}</td>'
            f'<td style="color:{("#f85149" if (t.get("mark_pnl_pct") or 0) < 0 else "#3fb950")}">{t.get("mark_pnl_pct",0):+.2f}%</td></tr>'
            for t in active)
        stats_html = f'''<div class="card" style="border-left:3px solid #d29922"><h3>📊 持仓盈亏统计（{len(active)} 笔）</h3>
<table><tr><th>总浮盈</th><th>平均浮盈</th><th>浮盈胜率</th><th>T+1锁定(今日买入)</th><th>TP1已触发</th></tr>
<tr><td style="color:{('#f85149' if _sum < 0 else '#3fb950')}">{_sum:+.2f}%</td>
<td style="color:{('#f85149' if _avg < 0 else '#3fb950')}">{_avg:+.2f}%</td>
<td>{_winr:.0f}%</td>
<td>{_t1_locked} 笔</td>
<td>{sum(1 for t in active if t.get('tp1_hit'))} 笔</td></tr></table>
<p style="color:#8b949e">⚠️ A股 T+1：当日买入持仓不可卖出，TP/SL 在买入当日不生效（显示🔒T+1锁定）。次日开始按分层 TP/SL 监控。</p></div>'''
        rt_rows = ''
        try:
            rt = json.load(open(r'E:\test\smc_project\research\realtime_log.json', encoding='utf-8'))
            rt = rt[-20:][::-1]
            rt_rows = ''.join(
                f'<tr><td class="mono">{html.escape(str(r.get("ts","")))}</td>'
                f'<td class="mono">{html.escape(str(r.get("code","")))}</td>'
                f'<td class="mono">{r.get("price",0):.2f}</td>'
                f'<td>{html.escape(str(r.get("status","")))}</td>'
                f'<td style="color:{("#f85149" if (r.get("mark_pnl_pct") or 0) < 0 else "#3fb950")}">{r.get("mark_pnl_pct",0):+.2f}%</td></tr>'
                for r in rt)
        except Exception:
            pass
        # FIX(2026-08-22): 交易日志（买入/卖出）
        _tl_rows = ''
        try:
            _tl = json.load(open(r'E:\test\smc_project\research\trade_log.json', encoding='utf-8'))
            _tl = _tl[-20:][::-1]
            _tl_rows = ''.join(
                f'<tr><td class="mono">{html.escape(str(r.get("ts","")))}</td>'
                f'<td class="mono">{html.escape(str(r.get("code","")))}</td>'
                f'<td>{html.escape(str(r.get("name","")))}</td>'
                f'<td style="color:{("#3fb950" if r.get("action")=="BUY" else "#d29922")}">{html.escape(str(r.get("action","")))}</td>'
                f'<td>{html.escape(str(r.get("signal_combo","")))}</td>'
                f'<td class="mono">{r.get("entry_price",0):.3f}</td>'
                f'<td class="mono">{html.escape(str(r.get("trigger_type", r.get("trigger","-"))))}</td>'
                f'<td style="color:{("#f85149" if (r.get("pnl_pct") or 0) < 0 else "#3fb950")}">{r.get("pnl_pct") if r.get("pnl_pct") is not None else "-"}</td></tr>'
                for r in _tl)
        except Exception:
            pass
        return f'''<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>v20f 实时监控</title><style>{CSS}</style></head><body>{build_nav()}<div class="container">
<div class="card" style="border-left:3px solid #3fb950"><h2>🟢 v20f 模拟持仓实时监控（{len(active)}）<span id="live-stamp" style="font-size:12px;color:#8b949e"></span></h2><p style="color:#8b949e">每 5 秒自动刷新实时价（AJAX），用于 TP/SL 监控与下单；买入=T+1 开盘/回踩成交；分层 TP/SL 次日生效（T+1 当日锁定🔒）。</p></div>
<div class="card" style="border-left:3px solid #d29922"><h3>📊 持仓盈亏统计（实时）</h3><table><tr><th>总浮盈</th><th>平均浮盈</th><th>浮盈胜率</th><th>T+1锁定</th><th>TP1触发</th></tr><tbody id="live-stats"><tr><td colspan="5">加载中…</td></tr></tbody></table></div>
<div class="card"><h3>持仓监控（分层 TP/SL + T+1，5秒实时刷新）</h3><table><thead><tr><th>代码</th><th>名称</th><th>信号日期</th><th>买入价</th><th>现价</th><th>TP1<br><span style="font-weight:normal;font-size:9px;color:#8b949e">swing高</span></th><th>TP2<br><span style="font-weight:normal;font-size:9px;color:#8b949e">FVG</span></th><th>TP3<br><span style="font-weight:normal;font-size:9px;color:#8b949e">流动性</span></th><th>TP4<br><span style="font-weight:normal;font-size:9px;color:#8b949e">60日前高</span></th><th>SL1<br><span style="font-weight:normal;font-size:9px;color:#8b949e">swing低</span></th><th>SL2<br><span style="font-weight:normal;font-size:9px;color:#8b949e">FVG/深层</span></th><th>状态</th><th>T+1/TP</th><th>浮盈</th></tr></thead><tbody id="live-positions">{rows or '<tr><td colspan=14>无持仓</td></tr>'}</tbody></table></div>
<div class="card"><h3>📝 交易日志（最近 20 条，买入/卖出）</h3><table><thead><tr><th>时间</th><th>代码</th><th>名称</th><th>动作</th><th>信号</th><th>价格</th><th>触发类型</th><th>盈亏</th></tr></thead><tbody>{_tl_rows or '<tr><td colspan=8>暂无交易记录</td></tr>'}</tbody></table><p style="color:#8b949e">买入无盈亏（T+1 入场），卖出记录盈亏与触发类型（TP/SL/时间止损）。</p></div>
<div class="card"><h3>实时价格记录（最近 20 条）</h3><table><thead><tr><th>时间</th><th>代码</th><th>价格</th><th>状态</th><th>浮盈</th></tr></thead><tbody>{rt_rows or '<tr><td colspan=5>暂无记录</td></tr>'}</tbody></table></div>
</div>
<script>
async function refreshLive() {{
  try {{
    let d = await (await fetch('/api/live-combo')).json();
    if (!d.ok) return;
    let rows = d.items || [];
    document.getElementById('live-stamp').textContent = '🔄 ' + d.ts;
    let tbody = document.getElementById('live-positions');
    tbody.innerHTML = rows.length ? rows.map(r => {{
      let ep = r.entry_price || 0, q = r.price || 0, pnl = r.pnl_pct || 0;
      let pnlS = (pnl >= 0 ? '+' : '') + pnl.toFixed(2) + '%';
      let pnlC = pnl < 0 ? '#f85149' : '#3fb950';
      let t1 = r.t1_locked ? '🔒' : (r.tp1_hit ? 'TP1✓' : '-');
      return '<tr><td class="mono"><a href="/kline?symbol=' + r.code + (r.code.startsWith('6') ? '.SH' : '.SZ') + '">' + r.code + '</a></td>'
        + '<td>' + (r.name || '') + '</td>'
        + '<td>' + (r.signal_date || '') + '</td>'
        + '<td class="mono">' + ep.toFixed(3) + '</td>'
        + '<td class="mono">' + q.toFixed(3) + '</td>'
        + '<td class="mono" style="color:#3fb950">' + (r.tp1||0).toFixed(3) + '</td>'
        + '<td class="mono" style="color:#2ea043">' + (r.tp2||0).toFixed(3) + '</td>'
        + '<td class="mono" style="color:#1f883d">' + (r.tp3||0).toFixed(3) + '</td>'
        + '<td class="mono" style="color:#56d364">' + (r.tp4||0).toFixed(3) + '</td>'
        + '<td class="mono" style="color:#f85149">' + (r.sl1||0).toFixed(3) + '</td>'
        + '<td class="mono" style="color:#ff6b6b">' + (r.sl2||0).toFixed(3) + '</td>'
        + '<td>' + (r.status || '') + '</td>'
        + '<td>' + t1 + '</td>'
        + '<td style="color:' + pnlC + '">' + pnlS + '</td></tr>';
    }}).join('') : '<tr><td colspan="14">无持仓</td></tr>';
    // 更新统计
    let pnls = rows.map(x => x.pnl_pct || 0).filter(x => x !== 0);
    let sum = pnls.reduce((a,b) => a+b, 0);
    let avg = pnls.length ? (sum / pnls.length) : 0;
    let win = pnls.filter(x => x > 0).length;
    let t1c = rows.filter(x => x.t1_locked).length;
    let tp1c = rows.filter(x => x.tp1_hit).length;
    document.getElementById('live-stats').innerHTML = '<tr><td style="color:' + (sum<0?'#f85149':'#3fb950') + '">' + sum.toFixed(2) + '%</td>'
      + '<td style="color:' + (avg<0?'#f85149':'#3fb950') + '">' + avg.toFixed(2) + '%</td>'
      + '<td>' + (pnls.length ? (100*win/pnls.length).toFixed(0) : '0') + '%</td>'
      + '<td>' + t1c + '</td><td>' + tp1c + '</td></tr>';
  }} catch(e) {{}}
}}
setInterval(refreshLive, 5000);
refreshLive();
</script></body></html>'''
    if _v526_live_production():
        registry = _production_registry()
        epoch = registry.get('data_epoch') or {}
        return f'''<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>V526 实时监控</title><style>{CSS}</style></head><body>{build_nav()}<div class="container"><div class="card" style="border-left:3px solid #3fb950"><h2>V526 实时持仓监控 <span id="stamp" style="font-size:12px;color:#8b949e"></span></h2><p>当前 epoch：{html.escape(str(epoch.get('epoch_id') or '-'))}。仅显示 V526 实盘模拟仓位；SL/TP 由 5 分钟执行器监控，买入当日禁止卖出。</p><table><thead><tr><th>代码</th><th>状态</th><th>买入价</th><th>现价</th><th>PnL</th><th>结构SL</th><th>结构TP</th><th>信号组合</th></tr></thead><tbody id="v526-live"><tr><td colspan="8">加载中…</td></tr></tbody></table></div><div class="card"><h3>执行约束</h3><p>只允许最新 committed scanner 的 PENDING_NEXT_OPEN；严格下一交易日开盘验证；开盘必须在结构 SL 与 TP 之间；T+1 禁止买入当日卖出；不使用历史 replay 或旧版本候选。</p></div></div><script>function esc(x){{return String(x??'').replace(/[&<>\"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}}[c]));}} async function refreshV526(){{let d=await (await fetch('/api/live-prices')).json();let rows=(d.picks||[]);document.getElementById('stamp').textContent='更新 '+new Date().toLocaleTimeString('zh-CN',{{hour12:false}})+'｜持仓 '+rows.length;document.getElementById('v526-live').innerHTML=rows.length?rows.map(p=>{{let e=Number(p.entryPrice||p.entry_price||0),q=Number(p.currentPrice||p.current_price||p.lastPrice||0),sl=Number(p.slPrice||p.sl||0),tp=Number(p.tp1Price||p.tp1||0), pnl=e&&q?((q-e)/e*100).toFixed(2)+'%':'-';return '<tr><td class="mono">'+esc(p.symbol)+'</td><td>'+esc(p.monitorStatus||p.monitor_status||p.status||'OPEN')+'</td><td>'+e.toFixed(3)+'</td><td>'+q.toFixed(3)+'</td><td>'+pnl+'</td><td style="color:#f85149">'+sl.toFixed(3)+'</td><td style="color:#3fb950">'+tp.toFixed(3)+'</td><td>'+esc(p.seq||p.ctxSeq||'')+'</td></tr>';}}).join(''):'<tr><td colspan="8">当前无 V526 持仓；监控器保持运行，等待下一交易日开盘验证后的 BUY_VALID。</td></tr>';}} refreshV526();setInterval(refreshV526,30000);</script></body></html>'''
    from datetime import datetime
    now = datetime.now().strftime('%H:%M:%S')
    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>SMC 实时监控</title>
<style>{CSS}
.status-holding {{ color: #58a6ff; }}
.status-sl-hit {{ color: #f85149; font-weight: bold; }}
.status-tp-hit {{ color: #3fb950; font-weight: bold; }}
.status-sl-hit td, .status-tp-hit td {{ animation: pulse-bg 1s infinite; }}
.status-sl-close {{ color: #d29922; }}
.status-tp-close {{ color: #2ea043; }}
@keyframes pulse-bg {{ 50% {{ background: rgba(248,81,73,0.08); }} }}
.today-op {{ background: rgba(255, 215, 0, 0.12); border-left: 3px solid #ffd700; }}
.signal-sell {{ background: #f85149; color: #fff; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; animation: blink 0.8s infinite; }}
.signal-sell-green {{ background: #3fb950; color: #fff; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; animation: blink 0.8s infinite; }}
.signal-watch {{ background: #d29922; color: #000; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; }}
@keyframes blink {{ 50% {{ opacity: 0.5; }} }}
#refresh-btn {{ background: var(--accent); color: #000; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; margin-left: 12px; }}
#refresh-btn:hover {{ opacity: 0.85; }}
#countdown {{ color: #8b949e; font-size: 11px; margin-left: 8px; }}
.alert-badge {{ display: inline-block; background: #f85149; color: #fff; padding: 1px 6px; border-radius: 10px; font-size: 10px; font-weight: bold; margin-left: 4px; }}
</style></head><body>
{build_nav()}
<div class="container">
<div class="card" style="border-left:3px solid #f85149">
<h2>🔴 实时价格监控 
  <span id="update-time" style="font-size:12px;color:#8b949e">加载中...</span>
  <button id="refresh-btn" onclick="loadPrices()">🔄 刷新</button>
  <span id="countdown"></span>
  <span id="alert-summary" style="margin-left:12px"></span>
</h2>
<div id="live-table">⏳ 加载中...</div>
</div>
<div class="card" style="border-left:3px solid #ffd700;margin-top:12px">
<h2>买入/卖出操作记录 <span style="font-size:12px;color:#8b949e">从启用记录日起持续保留，当日操作高亮</span></h2>
<div id="trade-ledger">⏳ 加载中...</div>
</div></div>
<script>
let refreshTimer = null;
let secondsLeft = 30;
let marketOpen = false;

function updateCountdown() {{
    if (!marketOpen) {{
        document.getElementById('countdown').textContent = '已暂停';
        return;
    }}
    document.getElementById('countdown').textContent = secondsLeft + 's后刷新';
    if (secondsLeft <= 0) {{ loadPrices(); secondsLeft = 30; }}
    else {{ secondsLeft--; }}
}}

async function loadPrices() {{
    secondsLeft = 30;
    try {{
        const t0 = Date.now();
        const r = await fetch('/api/live-prices');
        const data = await r.json();
        const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
        const now = new Date().toLocaleTimeString('zh-CN', {{hour12: false}});
        
        marketOpen = data.market_open || false;
        const scanMeta = data.scanMeta || {{}};
        const lastScan = data.lastScanAt || scanMeta.last_scan_at || '-';
        const scannerState = scanMeta.scanner_state || '';
        const scanDate = scannerState === 'NOT_RUN_EMPTY_BOOK' ? '-' : (data.latestScanDate || scanMeta.latest_scan_date || data.dataDate || '-');
        const scanText = scannerState ? ('生产扫描:' + scannerState) : ('最后扫描:' + lastScan);
        const dateText = '数据日期:' + (data.dataDate || '-') + ' | ' + scanText + ' | 扫描行情日:' + scanDate;
        
        if (!marketOpen) {{
            document.getElementById('update-time').innerHTML = '休市中 | ' + dateText + ' | ' + now;
            document.getElementById('countdown').textContent = '已暂停';
            document.getElementById('refresh-btn').style.display = 'none';
            document.getElementById('alert-summary').innerHTML = '<span style="color:#8b949e;font-size:12px">交易时间: 周一至周五 9:30-11:30 13:00-15:00</span>';
            // Stop refresh interval
            if (refreshTimer) {{ clearInterval(refreshTimer); refreshTimer = null; }}
        }} else {{
            document.getElementById('update-time').innerHTML = '更新: ' + now + ' | ' + dateText + ' (' + elapsed + 's)';
            document.getElementById('countdown').textContent = secondsLeft + 's后刷新';
            document.getElementById('refresh-btn').style.display = '';
            // Restart interval if stopped
            if (!refreshTimer) {{
                refreshTimer = setInterval(updateCountdown, 1000);
                updateCountdown();
            }}
        }}
        
        let html = '<table><thead><tr><th>代码</th><th>选股日期</th><th>加入日期</th><th>买入日期</th><th>入场价</th><th>现价</th><th>最后价格</th><th>行情状态</th><th>PnL%</th><th>成本线</th><th>Zone</th><th>DNA</th><th>组合合同</th><th>SL%</th><th>SL价</th><th>TP1</th><th>TP1价</th><th>信号</th><th>波动</th><th>持仓状态</th><th>操作</th></tr></thead><tbody>';
        let sl_count = 0, tp_count = 0, holding = 0, watch_context = 0, approaching_sl = 0, approaching_tp = 0, closed = 0;
        for (const p of data.picks) {{
            let status = p.status;
            let signal = '';
            let rowClass = '';
            if (status === 'SL_HIT') {{ sl_count++; rowClass = 'status-sl-hit'; signal = '<span class="signal-sell">🔴 止损卖出</span>'; }}
            else if (status === 'TP_HIT') {{ tp_count++; rowClass = 'status-tp-hit'; signal = '<span class="signal-sell-green">🟢 止盈卖出</span>'; }}
            else if (status === 'T1_LOCKED') {{ holding++; rowClass = 'status-sl-close'; signal = '<span class="signal-watch">T+1锁定，今日禁止卖出</span>'; }}
            else if (status === 'SL_CLOSE') {{ approaching_sl++; rowClass = 'status-sl-close'; signal = '<span class="signal-watch">⚠ 接近止损</span>'; }}
            else if (status === 'TP_CLOSE') {{ approaching_tp++; rowClass = 'status-tp-close'; signal = '<span class="signal-watch">接近止盈</span>'; }}
            else if (status === 'NEXT_DAY_PENDING') {{ holding++; rowClass = 'status-sl-close'; signal = '<span class="signal-watch">待次日买入</span>'; }}
            else if (status === 'WATCH_ONLY_CONTEXT' || status === 'NON_TRADABLE_CONTEXT') {{ watch_context++; signal = '<span style="color:#8b949e;font-size:10px">观察上下文</span>'; }}
            else if (status === 'NO_LIVE_LAST_PRICE') {{ holding++; signal = '<span style="color:#8b949e;font-size:10px">最后价</span>'; }}
            else if (status === 'NO_DATA') {{ closed++; signal = '<span style="color:#8b949e;font-size:10px">无价格</span>'; }}
            else {{ holding++; }}
            
            let pnlClass = p.pnlPct > 0 ? 'color:#3fb950' : (p.pnlPct < 0 ? 'color:#f85149' : 'color:#8b949e');
            let pnlStr = p.currentPrice > 0 ? (p.pnlPct>0?'+':'')+p.pnlPct.toFixed(2)+'%' : '<span style="color:#8b949e">-</span>';
            let curStr = p.livePrice > 0 ? p.livePrice.toFixed(2) : '<span style="color:#8b949e">-</span>';
            let lastStr = p.lastPrice > 0 ? p.lastPrice.toFixed(2) + (p.lastPriceDate ? '<br><span style="font-size:9px;color:#8b949e">'+p.lastPriceDate+'</span>' : '') : '<span style="color:#8b949e">-</span>';
            let priceStatus = p.priceStatus || (marketOpen ? '无实时' : '休市');
            let sl_price = p.slPrice > 0 ? p.slPrice.toFixed(2) : '-';
            let tp_price = p.tpPrice > 0 ? p.tpPrice.toFixed(2) : '-';
            
            let sigSeq = p.signalSeq || '';
            let sigShort = sigSeq;  // Already compact 3-4 signals
            let costLineStr = p.costLine > 0 ? p.costLine.toFixed(2) : (p.cost_line > 0 ? Number(p.cost_line).toFixed(2) : '-');
            let volStr = (p.volatilityPct ? Number(p.volatilityPct).toFixed(2)+'%' : (p.volatility_pct ? Number(p.volatility_pct).toFixed(2)+'%' : (p.volClass || p.vol_class || '-')));
            if (p.entryZoneRelation) volStr += '<br><span style="font-size:9px;color:#d29922">' + p.entryZoneRelation + '</span>';
            // Format dates as MM-DD
            const fmtShortDate = (v) => {{ v = String(v || ''); return v.length >= 8 ? v.substring(4,6) + '-' + v.substring(6,8) : (v || '-'); }};
            let pickDateStr = fmtShortDate(p.pickDate);
            let joinDateStr = fmtShortDate(p.joinDate);
            let entryDateStr = fmtShortDate(p.entryDate);
            let zoneStr = p.zoneType || '-';
            if (p.zoneLow || p.zoneHigh) zoneStr = (p.zoneType || 'ZONE') + '<br><span style="font-size:9px;color:#8b949e">[' + Number(p.zoneLow || 0).toFixed(2) + '~' + Number(p.zoneHigh || 0).toFixed(2) + ']</span>';
            let dnaRaw = p.dna_preferred_behavior || p.smc_dna || '-';
            let dnaStr = (typeof dnaRaw === 'string' ? dnaRaw : JSON.stringify(dnaRaw || '-')).replaceAll('_',' ');
            let comboRaw = p.combo_contract_key || p.combo_contract || '-';
            let comboStr = (typeof comboRaw === 'string' ? comboRaw : JSON.stringify(comboRaw || '-'));
            
            html += '<tr class="' + rowClass + '">' +
                '<td class=mono><a href="/kline?s=' + p.symbol + '" style="color:var(--blue)">' + p.symbol + '</a></td>' +
                '<td class=mono style="font-size:10px;color:#8b949e">' + pickDateStr + '</td>' +
                '<td class=mono style="font-size:10px;color:#8b949e">' + joinDateStr + '</td>' +
                '<td class=mono style="font-size:10px;color:#8b949e">' + entryDateStr + '</td>' +
                '<td class=mono>' + p.entryPrice.toFixed(2) + '</td>' +
                '<td class=mono>' + curStr + '</td>' +
                '<td class=mono style="color:#58a6ff">' + lastStr + '</td>' +
                '<td class=mono style="font-size:10px;color:#d29922">' + priceStatus + '</td>' +
                '<td class=mono style="' + pnlClass + '">' + pnlStr + '</td>' +
                '<td class=mono style="color:#d29922">' + costLineStr + '</td>' +
                '<td class=mono style="font-size:10px;color:#58a6ff">' + zoneStr + '</td>' +
                '<td class=mono style="font-size:9px;color:#3fb950">' + dnaStr.slice(0,28) + '</td>' +
                '<td class=mono style="font-size:9px;color:#d29922" title="' + comboStr + '">' + comboStr.slice(0,34) + '</td>' +
                '<td class=mono style="color:#f85149">' + (p.slPct ? p.slPct.toFixed(1)+'%' : '-') + '</td>' +
                '<td class=mono style="color:#f85149">' + sl_price + '</td>' +
                '<td class=mono style="color:#3fb950;font-size:10px">' + (p.tpTiers && p.tpTiers.length && typeof p.tpTiers[0] === 'number' ? p.tpTiers[0].toFixed(0)+'%' : '-') + '</td>' +
                '<td class=mono style="color:#3fb950">' + tp_price + '</td>' +
                '<td class=mono style="font-size:9px" title="' + sigSeq + '">' + sigShort + '</td>' +
                '<td class=mono style="font-size:10px;color:#8b949e">' + volStr + '</td>' +
                '<td class=mono style="font-weight:bold">' + status + '</td>' +
                '<td>' + signal + '</td></tr>';
        }}
        html += '</tbody></table>';
        html += '<p style="margin-top:8px;color:#8b949e">真实持仓: <b style="color:#58a6ff">' + holding + '</b> | 观察上下文: <b>' + watch_context + '</b> | ⚠接近SL: <b style="color:#d29922">' + approaching_sl + '</b> | 接近TP: <b style="color:#2ea043">' + approaching_tp + '</b> | 🔴SL命中: <b style="color:#f85149">' + sl_count + '</b> | 🟢TP命中: <b style="color:#3fb950">' + tp_count + '</b> | ⏸休市/无数据: <b>' + closed + '</b></p>';
        if (data.error) html += '<p style="color:#d29922">⚠ ' + data.error + '</p>';
        document.getElementById('live-table').innerHTML = html;

        let ledgerHtml = '<table><thead><tr><th>操作</th><th>代码</th><th>引擎</th><th>选股日期</th><th>买入日期</th><th>卖出日期</th><th>S</th><th>质量</th><th>回撤</th><th>现价</th><th>Zone</th><th>盈利/亏损</th><th>SL</th><th>TP</th><th>序列</th><th>原因</th></tr></thead><tbody>';
        const ledger = data.tradeLedger || [];
        const fmtDate = (v) => {{ v = String(v || ''); return v.length >= 8 ? v.substring(4,6)+'-'+v.substring(6,8) : (v || '-'); }};
        const money = (v) => {{ v = Number(v || 0); return v ? v.toFixed(2) : '-'; }};
        if (!ledger.length) {{
            ledgerHtml += '<tr><td colspan="16" style="color:#8b949e;padding:14px">暂无买入/卖出记录；从当前日期开始，后续汇入今日选股、手工加入监控、SL/TP卖出都会持续记录。</td></tr>';
        }} else {{
            for (const r of ledger) {{
                const pnl = r.pnl_pct === '' || r.pnl_pct === null || r.pnl_pct === undefined ? '-' : ((Number(r.pnl_pct)>0?'+':'') + Number(r.pnl_pct).toFixed(2) + '%');
                const pnlColor = Number(r.pnl_pct || 0) > 0 ? '#3fb950' : (Number(r.pnl_pct || 0) < 0 ? '#f85149' : '#8b949e');
                const cls = r.is_today ? 'today-op' : '';
                ledgerHtml += '<tr class="'+cls+'">' +
                    '<td class=mono style="font-weight:bold;color:' + (r.action === 'SELL' ? '#f85149' : '#3fb950') + '">' + (r.action || '-') + '</td>' +
                    '<td class=mono><a href="/kline?s=' + r.symbol + '" style="color:var(--blue)">' + r.symbol + '</a></td>' +
                    '<td class=mono>' + (r.engine || '-') + '</td>' +
                    '<td class=mono>' + fmtDate(r.select_date) + '</td>' +
                    '<td class=mono>' + fmtDate(r.buy_date) + '</td>' +
                    '<td class=mono>' + fmtDate(r.sell_date) + '</td>' +
                    '<td class=mono>' + (Number(r.score || 0)).toFixed(0) + '</td>' +
                    '<td>' + (r.quality || '-') + '</td>' +
                    '<td class=mono>' + (Number(r.retrace_pct || 0)).toFixed(1) + '%</td>' +
                    '<td class=mono>' + money(r.current_price) + '</td>' +
                    '<td class=mono>' + (r.zone || '-') + '</td>' +
                    '<td class=mono style="color:'+pnlColor+'">' + pnl + '</td>' +
                    '<td class=mono style="color:#f85149">' + money(r.sl) + '</td>' +
                    '<td class=mono style="color:#3fb950">' + money(r.tp) + '</td>' +
                    '<td style="font-size:9px" title="' + (r.seq || '') + '">' + (r.seq || '-') + '</td>' +
                    '<td style="font-size:10px">' + (r.reason || '-') + '</td></tr>';
            }}
        }}
        ledgerHtml += '</tbody></table>';
        document.getElementById('trade-ledger').innerHTML = ledgerHtml;
        
        // Alert badge
        let alerts = [];
        if (sl_count > 0) alerts.push('<span class="alert-badge">' + sl_count + ' SL</span>');
        if (tp_count > 0) alerts.push('<span class="alert-badge" style="background:#3fb950">' + tp_count + ' TP</span>');
        document.getElementById('alert-summary').innerHTML = alerts.join(' ');
        
        // V20: Browser notification + sound on SL/TP hits
        if ((sl_count > 0 || tp_count > 0) && window.alertedLast !== (sl_count + '-' + tp_count)) {{
            window.alertedLast = sl_count + '-' + tp_count;
            let body = (sl_count>0?sl_count+' SL! ':'') + (tp_count>0?tp_count+' TP!':'');
            if ('Notification' in window && Notification.permission === 'granted') {{
                new Notification('SMC Alert: ' + body);
            }}
            try {{ new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACAf39/f4B/f3+Af39/gH9/f4B/f3+Af39/gH9/f4B/f3+Af39/gH9/f4B/f3+Af39/gH9/f4B/').play(); }} catch(e) {{}}
        }}
    }} catch(e) {{
        document.getElementById('live-table').innerHTML = '<p style="color:#f85149">API错误: ' + e.message + '</p>';
    }}
}}
// Request notification permission
if ('Notification' in window && Notification.permission === 'default') {{
    Notification.requestPermission();
}}
loadPrices();
</script></body></html>"""


def build_trade():
    """实时交易模拟页面"""
    return """<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>SMC 交易模拟</title>
<style>""" + CSS + """
#pnl-chart { width: 100%; height: 280px; margin: 12px 0; }
</style></head><body>
<nav><span class="brand">SMC {FRONTEND_VERSION}</span><a href="/">仪表</a><a href="/kline">K线</a><a href="/backtest">回测</a><a href="/monitor">选股</a><a href="/live">实时</a><a href="/trade" class="active">💰交易</a><a href="/docs">文档</a></nav>
<div class="container">
<div class="card"><h2>💰 实时交易模拟 <span id="update-time" style="font-size:12px;color:#8b949e"></span>
<button id="scan-btn" onclick="scanPicks()" style="background:var(--accent);color:#000;border:none;padding:4px 12px;border-radius:4px;cursor:pointer;margin-left:12px">🔍 扫描选股</button>
<button onclick="checkPositions()" style="background:#58a6ff;color:#fff;border:none;padding:4px 12px;border-radius:4px;cursor:pointer;margin-left:4px">✅ 检查持仓</button>
</h2>
<div class="flex" style="gap:8px;margin:12px 0" id="stats"></div>
<div id="pnl-chart"></div></div>

<div class="flex" style="gap:8px">
<div class="card" style="flex:1"><h3>📊 持仓</h3><div id="positions">加载中...</div></div>
<div class="card" style="flex:1"><h3>📋 最近订单</h3><div id="orders">加载中...</div></div>
</div>
<div id="scan-result" style="margin-top:8px"></div>
</div>
<script src="/echarts.js"></script>
<script>
async function loadStatus() {
    let r = await fetch('/api/trade/status'); let d = await r.json();
    document.getElementById('update-time').textContent = new Date().toLocaleTimeString('zh-CN',{hour12:false});
    document.getElementById('stats').innerHTML = `
<div class="stat green"><div class="val">${d.equity.toLocaleString()}</div><div class="lbl">总权益</div></div>
<div class="stat"><div class="val">${d.cash.toLocaleString()}</div><div class="lbl">现金</div></div>
<div class="stat" style="color:${d.total_pnl>=0?'#3fb950':'#f85149'}"><div class="val">${d.total_pnl>=0?'+':''}${d.total_pnl.toLocaleString()}</div><div class="lbl">总盈亏</div></div>
<div class="stat" style="color:${d.total_pnl_pct>=0?'#3fb950':'#f85149'}"><div class="val">${d.total_pnl_pct>=0?'+':''}${d.total_pnl_pct}%</div><div class="lbl">收益率</div></div>
<div class="stat blue"><div class="val">${d.positions_count}/${d.max_positions}</div><div class="lbl">持仓</div></div>
<div class="stat"><div class="val">${d.trades_closed}</div><div class="lbl">已平仓</div></div>
<div class="stat" style="color:#3fb950"><div class="val">${d.win_rate}%</div><div class="lbl">胜率</div></div>
<div class="stat" style="color:#d29922"><div class="val">${d.total_commission.toFixed(0)}</div><div class="lbl">手续费</div></div>`;
    
    let ph = '<table><tr><th>代码</th><th>数量</th><th>成本</th><th>现价</th><th>市值</th><th>盈亏%</th><th>SL</th><th>状态</th></tr>';
    for (let p of d.positions) {
        let pc = p.pnl_pct>=0?'#3fb950':'#f85149';
        ph += `<tr><td class=mono><a href="/kline?s=${p.symbol}" style="color:var(--blue)">${p.symbol}</a></td>
        <td class=mono>${p.shares}</td><td class=mono>${p.avg_cost}</td><td class=mono>${p.current_price}</td>
        <td class=mono>${p.market_value.toLocaleString()}</td>
        <td class=mono style="color:${pc};font-weight:bold">${p.pnl_pct>=0?'+':''}${p.pnl_pct}%</td>
        <td class=mono style="color:#f85149">${p.sl_price}</td>
        <td class=mono>${p.status}</td></tr>`;}
    ph += '</table>';
    if (d.positions.length===0) ph='<p style="color:#8b949e">无持仓</p>';
    document.getElementById('positions').innerHTML = ph;
    
    let oh = '<table><tr><th>ID</th><th>代码</th><th>方向</th><th>数量</th><th>价格</th><th>原因</th><th>盈亏</th></tr>';
    for (let o of d.recent_orders.slice(-10)) {
        let oc = o.side==='BUY'?'#3fb950':(o.pnl_pct>=0?'#3fb950':'#f85149');
        oh += `<tr><td class=mono>${o.id}</td><td class=mono>${o.symbol}</td>
        <td style="color:${o.side==='BUY'?'#3fb950':'#f85149'}">${o.side}</td>
        <td class=mono>${o.quantity}</td><td class=mono>${o.filled||o.price}</td>
        <td style="font-size:10px">${o.reason}</td>
        <td class=mono style="color:${oc}">${o.pnl_pct||''}</td></tr>`;}
    oh += '</table>';
    document.getElementById('orders').innerHTML = oh;
}
async function scanPicks() {
    document.getElementById('scan-result').innerHTML = '<p style="color:#d29922">⏳ 扫描中...</p>';
    let r = await fetch('/api/trade/scan'); let d = await r.json();
    let h = `<p>扫描: ${d.orders?.length||0}笔订单 | 跳过: 停牌${d.skipped?.suspended||0} 涨停${d.skipped?.limit_up||0}</p>`;
    if (d.orders) for (let o of d.orders) h += `<p style="font-size:11px;color:${o.status==='FILLED'?'#3fb950':'#d29922'}">${o.symbol} ${o.status} @${o.filled||o.price} ${o.reason||''}</p>`;
    document.getElementById('scan-result').innerHTML = h;
    loadStatus();
}
async function checkPositions() {
    let r = await fetch('/api/trade/check'); let d = await r.json();
    if (d.orders?.length) { for (let o of d.orders) alert(o.symbol+' '+o.reason+' PnL:'+(o.pnl_pct||0)+'%'); }
    loadStatus();
}
loadStatus();
setInterval(loadStatus, 30000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    # ── Live Price Fetch ──
    HUBBLE_BASE = "http://43.167.234.49:3101"
    HUBBLE_HEADERS = {"X-API-Key": "123456", "Content-Type": "application/json"}
    
    @classmethod
    def fetch_live_prices(cls, codes):
        """Batch fetch real-time prices from Tencent (Hubble fallback if down). codes: list of pure numbers."""
        if not codes: return {}
        result = {}
        # Try Tencent first (more reliable)
        try:
            import urllib.request, urllib.parse
            # Build Tencent format: sz000019,sh600519
            tc_codes = []
            for c in codes:
                c = str(c)
                if c.startswith(('0','3')): tc_codes.append(f'sz{c}')
                elif c.startswith('6'): tc_codes.append(f'sh{c}')
                elif c.startswith(('8','4','9')): tc_codes.append(f'bj{c}')
            if tc_codes:
                url = f"http://qt.gtimg.cn/q={','.join(tc_codes[:500])}"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    raw = resp.read().decode('gbk', errors='replace')
                for line in raw.strip().split('\n'):
                    if '="' not in line: continue
                    try:
                        code_part = line.split('="')[0].split('_')[-1]  # sz000019
                        parts = line.split('"')[1].split('~')
                        if len(parts) < 33: continue
                        pure_code = code_part[2:]  # 000019
                        result[pure_code] = {
                            'price': float(parts[3]) if parts[3] else 0,
                            'chgPct': float(parts[32]) if parts[32] else 0,
                            'name': parts[1],
                            'open': float(parts[5]) if parts[5] else 0,
                            'high': float(parts[33]) if len(parts) > 33 and parts[33] else 0,
                            'low': float(parts[34]) if len(parts) > 34 and parts[34] else 0,
                        }
                    except (ValueError, IndexError):
                        continue
        except Exception:
            pass
        
        # Fallback to Hubble if Tencent returned nothing
        if not result:
            try:
                url = f"{cls.HUBBLE_BASE}/api/v2/cnstock/securities?codes={','.join(codes[:500])}&fields=code,name,price,chgPct,open,high,low,volume"
                req = urllib.request.Request(url, headers=cls.HUBBLE_HEADERS)
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read())
                for item in data.get('data', data if isinstance(data, list) else []):
                    code = str(item.get('code', ''))
                    result[code] = {
                        'price': float(item.get('price', 0)),
                        'chgPct': float(item.get('chgPct', 0)),
                        'name': item.get('name', ''),
                        'open': float(item.get('open', 0)),
                        'high': float(item.get('high', 0)),
                        'low': float(item.get('low', 0)),
                    }
            except Exception:
                pass
        return result
    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()

    def do_GET(self):
        self._route()

    def do_POST(self):
        self._route()

    def _post_qs(self):
        try:
            length = int(self.headers.get('Content-Length') or 0)
        except Exception:
            length = 0
        if length <= 0:
            return {}
        try:
            raw = self.rfile.read(length).decode('utf-8', 'ignore')
            ctype = (self.headers.get('Content-Type') or '').lower()
            if 'application/json' in ctype:
                obj = json.loads(raw or '{}')
                if isinstance(obj, dict):
                    return {str(k): [str(v)] for k, v in obj.items() if v is not None}
            return parse_qs(raw)
        except Exception:
            return {}

    def _route(self):
        p = urlparse(self.path)
        path = p.path
        qs = parse_qs(p.query)
        if self.command == 'POST':
            for k, v in self._post_qs().items():
                qs[k] = v
        self._last_qs = qs

        if path == '/':
            self._html(build_dashboard(qs))
        elif path == '/echarts.js':
            self._static_file(Path('/root/.hermes/scripts/echarts.min.js'), 'application/javascript')
        elif path == '/kline':
            ver = qs.get('ver', qs.get('version', [ACTIVE_VERSION]))[0]
            requested_symbol = qs.get('symbol', qs.get('s', ['']))[0]
            if not requested_symbol and str(ver).upper() in ('V517', 'V517_EFFORT_RESULT'):
                sample = v517_frontend.trades()
                requested_symbol = sample[0].get('symbol', '') if sample else ''
            sym = requested_symbol or '600519.SH'
            self._html(build_kline(sym, ver))
        elif path == '/backtest':
            self._html(build_backtest(qs.get('start', [''])[0], qs.get('end', [''])[0]))
        elif path == '/monitor':
            self._html(build_monitor(qs.get('start', [''])[0], qs.get('end', [''])[0]))
        elif path == '/historical-artifacts':
            self._html(build_historical_artifacts())
        elif path == '/combo':
            self._html(build_combo())
        elif path == '/v144-preview':
            self._html(build_v144_preview())
        elif path == '/analysis':
            self._html(build_analysis(qs.get('start', [''])[0], qs.get('end', [''])[0]))
        elif path == '/stoploss':
            self._html(build_stoploss())
        elif path == '/v45':
            self._html(build_v45_page(qs.get('ver', ['v45_5'])[0]))
        elif path == '/autopsy':
            self._html(build_autopsy(qs.get('start', [''])[0], qs.get('end', [''])[0]))
        elif path == '/effort-result':
            self._html(build_effort_result())
        elif path == '/docs':
            self._html(build_docs())
        elif path == '/uzi':
            import sys as _uzi_sys
            _uzi_sys.path.insert(0, r'E:\test\smc_project\uzi')
            from build_uzi import build_uzi
            self._html(build_uzi())
        elif path == '/compare':
            self._html(build_compare())
        elif path == '/live':
            self._html(build_live())
        elif path == '/logs':
            self._html(build_logs())
        elif path == '/api/logs':
            self._json(_v526_log_snapshot() if (_v526_live_production() or _production_empty_book()) else _load_ops_latest())
        elif path == '/api/scheduler/status':
            state = _scheduler_load_state()
            state['jobs_config'] = {k: {'time': v.get('time'), 'desc': v.get('desc'), 'cmd': ' '.join(v.get('cmd', []))} for k, v in _SCHEDULER_JOBS.items()}
            state['internal_scheduler'] = _internal_scheduler_enabled()
            self._json(state)
        elif path == '/api/scheduler/manual-run':
            job = qs.get('job', ['v517_shadow_observer'])[0]
            if job not in _SCHEDULER_JOBS:
                self._json({'ok': False, 'error': f'unknown job: {job}', 'available_jobs': list(_SCHEDULER_JOBS)})
                return
            force = qs.get('force', ['1'])[0] in ('1', 'true', 'yes')
            run_date = qs.get('date', [datetime.now().strftime('%Y%m%d')])[0]
            threading.Thread(target=_scheduler_run_job, args=(job, _SCHEDULER_JOBS[job], run_date, force, 'manual'), daemon=True).start()
            self._json({'ok': True, 'job': job, 'run_date': run_date, 'force': force, 'mode': 'background'})
        elif path in ('/api/live-prices', '/api/live_prices'):
            self._api_live_prices()
        elif path == '/api/live-combo':
            self._json(self._api_live_combo())
        elif path == '/trade':
            self._html(build_trade())
        elif path == '/api/trade/status':
            self._api_trade_status()
        elif path == '/api/trade/scan':
            self._api_trade_scan(qs)
        elif path == '/api/trade/check':
            self._api_trade_check()
        elif path == '/api/effort-result':
            self._json(v517_frontend.bundle())
        elif path == '/api/kline_full':
            self._api_kline_full(qs)
        elif path == '/api/kline':
            self._api_kline_full(qs)  # backward compat
        elif path == '/api/picks':
            include_reject = (qs.get('include_reject', ['0'])[0] in ('1','true','yes'))
            ver = qs.get('ver', [ACTIVE_VERSION])[0]
            registry = _production_registry()
            if not qs.get('ver') and registry.get('production_strategy') == 'COMBO_SMC_EVENT':
                # FIX(2026-08-18): COMBO 准生产下 picks = 纸面持仓（OPEN）列表
                try:
                    ledger = json.loads(Path('/root/.hermes/smc_monitor/paper_ledger.json').read_text(encoding='utf-8'))
                except Exception:
                    ledger = []
                picks = []
                for p in ledger:
                    if p.get('status') == 'OPEN':
                        picks.append({
                            'symbol': p.get('code') + ('.SH' if str(p.get('code','')).startswith('6') else '.SZ'),
                            'name': p.get('name'), 'pick_date': p.get('entry_date'),
                            'entry_date': p.get('entry_date'), 'entry_price': p.get('entry_price'),
                            'engine': 'COMBO_SMC_EVENT', 'source': p.get('source') or 'EVENT',
                            'disclose_date': p.get('disclose_date'), 'monitor_status': 'OPEN',
                            'mark_pnl_pct': p.get('mark_pnl_pct'), 'paper': True,
                        })
            elif not qs.get('ver') and registry.get('production_strategy') == 'V526_V517_DAILY_EFFORT_RESULT_ABSORPTION':
                strategy = registry.get('production_strategy')
                picks = []
                for pos in load_positions() if load_positions else []:
                    raw = dict(pos.get('raw_pick') or {})
                    if str(raw.get('engine') or '') == strategy:
                        picks.append({**raw, 'monitor_status': pos.get('status'), 'entry_price': pos.get('entry_price'), 'sl': pos.get('sl_price'), 'tp1': pos.get('tp1_price'), 'filled_at': pos.get('filled_at')})
            else:
                picks = get_active_picks(include_reject=include_reject, version=ver)
            if ver == ACTIVE_VERSION and load_positions:
                join_dates = {}
                pos_status = {}
                for x in load_positions():
                    k = (x.get('symbol'), _date_key(x.get('pick_date')))
                    if k[0] and k[1] and k not in join_dates:
                        join_dates[k] = _date_key(x.get('join_date') or x.get('joined_at') or x.get('created_at'))
                    if k[0] and k[1] and k not in pos_status:
                        pos_status[k] = x.get('status') or ''
                picks = [dict(p, join_date=p.get('join_date') or join_dates.get((p.get('symbol'), _date_key(p.get('pick_date') or p.get('entry_date'))), ''), joined_at=p.get('joined_at') or p.get('join_date') or join_dates.get((p.get('symbol'), _date_key(p.get('pick_date') or p.get('entry_date'))), ''), select_date=p.get('select_date') or p.get('pick_date') or p.get('entry_date'), zone_type=p.get('zone_type') or p.get('signal_type') or '', engine=p.get('engine') or ACTIVE_VERSION, monitor_status=pos_status.get((p.get('symbol'), _date_key(p.get('pick_date') or p.get('entry_date'))), '')) for p in picks]
            data_date = _latest_data_date() if ver == ACTIVE_VERSION else ''
            if data_date:
                picks = [dict(p, data_date=data_date) for p in picks]
            picks = [_apply_smc_field_contract(p, default_engine=ver) for p in picks]
            if ver == ACTIVE_VERSION:
                picks = _apply_current_price_live_guard(picks)
            self._json(picks)
        elif path == '/api/v144-dry-run-preview':
            scope = qs.get('scope', ['latest_per_symbol'])[0]
            preview_files = {
                'all': Path('/root/.hermes/smc_audit/v144_v143_ui_api_dry_run_mapping_20260621/v144_ui_api_dry_run_all.json'),
                'recent45': Path('/root/.hermes/smc_audit/v144_v143_ui_api_dry_run_mapping_20260621/v144_ui_api_dry_run_recent45.json'),
                'latest_per_symbol': Path('/root/.hermes/smc_audit/v144_v143_ui_api_dry_run_mapping_20260621/v144_ui_api_dry_run_latest_per_symbol.json'),
            }
            fp = preview_files.get(scope, preview_files['latest_per_symbol'])
            data = _load_json_dict(fp, {})
            rows = data.get('rows') if isinstance(data, dict) else []
            rows = [_apply_smc_field_contract(r, default_engine='V144_DRY_RUN') for r in (rows or [])]
            status_counts = Counter(r.get('v144_status') or r.get('lifecycle_status') or r.get('v143_lifecycle_status') or 'UNKNOWN' for r in rows)
            bad_buy_like = sum(1 for r in rows if r.get('tradable') is True or r.get('buy_enabled') is True or str(r.get('trade_action') or '') != 'NO_BUY')
            v147 = _load_json_dict(Path('/root/.hermes/smc_audit/v147_v144_preview_integrity_replay_20260621/summary.json'), {})
            v147_scope = {}
            for s in v147.get('scope_summaries', []) if isinstance(v147, dict) else []:
                if s.get('scope') == (scope if scope in preview_files else 'latest_per_symbol'):
                    v147_scope = s
                    break
            self._json({
                'ok': True,
                'scope': scope if scope in preview_files else 'latest_per_symbol',
                'rows': rows,
                'summary': data.get('summary', {}) if isinstance(data, dict) else {},
                'contract': {
                    'version': 'V148_READONLY_LIFECYCLE_CONTRACT',
                    'shadow_only': True,
                    'display_only': True,
                    'production_write': False,
                    'buy_enabled': False,
                    'trade_action': 'NO_BUY',
                    'row_count': len(rows),
                    'bad_buy_like': bad_buy_like,
                    'all_rows_no_buy': bad_buy_like == 0,
                    'status_counts': dict(status_counts),
                    'v147_kline_mismatch_count': v147_scope.get('mismatch_count'),
                    'v147_missing_kline': v147_scope.get('missing_kline'),
                    'v147_checked': bool(v147_scope),
                }
            })
        elif path == '/api/picks/rejects':
            ver = qs.get('ver', [ACTIVE_VERSION])[0]
            self._json(get_reject_picks(version=ver))
        elif path == '/api/picks/history':
            ver = qs.get('ver', [ACTIVE_VERSION])[0]
            self._json([p for p in get_all_picks_scoped(ver) if p.get('pick_scope') == 'HISTORICAL_BEST'])
        elif path == '/api/picks/contract':
            ver = qs.get('ver', [ACTIVE_VERSION])[0]
            self._json(get_pick_contract_summary(version=ver))
        elif path == '/api/monitor/ingest-daily':
            if _production_empty_book():
                self._json({'ok': False, 'state': 'EMPTY_BOOK_NO_PRODUCTION_WRITE', 'error': '无已晋级生产策略；禁止将候选写入监控/仓位'}); return
            if not ingest_daily_picks:
                self._json({'ok': False, 'error': 'monitor state module unavailable'}); return
            res = ingest_daily_picks(get_active_picks(), source='manual_daily')
            self._json({'ok': True, 'added': res.get('added',0), 'buy_added': res.get('buy_added',0), 'pending_count': res.get('pending_count',0), 'validation_only': res.get('validation_only',0), 'rejected_count': res.get('rejected_count',0), 'rejected': res.get('rejected', [])[:20], 'existing_pending_count': res.get('existing_pending_count',0), 'active_count': res.get('active_count',0), 'date': res.get('date')})
        elif path == '/api/monitor/manual':
            if _production_empty_book():
                self._json({'ok': False, 'state': 'EMPTY_BOOK_NO_PRODUCTION_WRITE', 'error': '无已晋级生产策略；禁止手工创建监控/仓位'}); return
            if not add_manual_pick:
                self._json({'ok': False, 'error': 'monitor state module unavailable'}); return
            try:
                pos = add_manual_pick(qs.get('symbol',[''])[0], qs.get('entry',['0'])[0], qs.get('sl',['0'])[0], qs.get('tp1',['0'])[0], qs.get('note',[''])[0])
                self._json({'ok': True, 'position': pos})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})
        elif path == '/api/monitor/state':
            self._json({'summary': monitor_state_summary() if monitor_state_summary else {}, 'positions': load_positions() if load_positions else [], 'ledger': load_trade_ledger() if load_trade_ledger else [], 'reviews': monitor_load_json(MONITOR_REVIEW, []) if monitor_load_json and MONITOR_REVIEW else []})
        elif path == '/api/trade-ledger':
            self._json(load_trade_ledger() if load_trade_ledger else [])
        elif path == '/api/autopsy/closed-loop':
            self._json(_load_v49_closed_loop_review())
        elif path == '/api/research/v517/periods':
            period = v517_frontend.period_metrics()
            self._json({
                **period,
                'research_only': True,
                'production_write': False,
                'watchlist_write': False,
                'buy_enabled': False,
                'trade_action': 'REPLAY_ONLY',
            })
        elif path == '/api/summary':
            self._api_summary()
        elif path == '/api/stoploss/audit':
            self._json(_load_json_dict(V44_STOPLOSS_AUDIT, {}))
        elif path == '/api/v45/report':
            self._json(load_v45_bundle(qs.get('ver', ['v45_5'])[0], limit_events=1000, limit_rows=500))
        elif path == '/api/v45/validation':
            self._json(load_v45_bundle(qs.get('ver', ['v45_5'])[0], limit_events=0, limit_rows=0).get('validation', {}))
        elif path == '/api/v45/events':
            self._json(load_v45_bundle(qs.get('ver', ['v45_5'])[0], limit_events=int(qs.get('limit', ['5000'])[0]), limit_rows=0).get('events', []))
        elif path == '/api/v45/setups':
            self._json(load_v45_bundle(qs.get('ver', ['v45_5'])[0], limit_events=0, limit_rows=int(qs.get('limit', ['1000'])[0])).get('setups', []))
        elif path == '/api/v45/trades':
            self._json(load_v45_bundle(qs.get('ver', ['v45_5'])[0], limit_events=0, limit_rows=int(qs.get('limit', ['1000'])[0])).get('trades', []))
        elif path == '/api/v45/picks':
            self._json(load_v45_bundle(qs.get('ver', ['v45_5'])[0], limit_events=0, limit_rows=int(qs.get('limit', ['1000'])[0])).get('picks', []))
        elif path == '/api/v45/watchlist':
            self._json(load_v45_bundle(qs.get('ver', ['v45_5'])[0], limit_events=0, limit_rows=int(qs.get('limit', ['1000'])[0])).get('watchlist', []))
        elif path == '/api/equity_curve':
            self._json(build_equity_curve_data())
        elif path == '/api/backtest/run':
            self._api_reselect(qs)
        elif path == '/api/reselect':
            self._api_reselect(qs)
        elif path == '/api/history':
            self._api_history()
        elif path == '/api/history/load':
            self._api_history_load(qs)
        elif path == '/api/reload':
            # Force reload all data from disk, not stale in-memory cache.
            try:
                _invalidate_cache()
                trades = reload_trades()
                picks = reload_picks()
                self._json({'status': 'reloaded', 'trades': len(trades) if trades else 0, 'picks': len(picks) if picks else 0, 'contract': get_pick_contract_summary()})
            except Exception as e:
                self._json({'status': 'error', 'message': str(e)})
        elif path == '/resonance':
            self._html(build_resonance())
        elif path == '/api/resonance':
            _api_resonance(self)
        elif path == '/diagnostics':
            self._html(build_diagnostics())
        elif path == '/api/diagnostics':
            self._api_diagnostics()
        else:
            self.send_response(404); self.end_headers()

    def _html(self, content):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        # The dashboard is current-epoch operational state; stale browser/proxy
        # responses would hide the daily funnel and misstate what actually ran.
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.end_headers()
        self.wfile.write(content.encode())

    def _json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _api_live_combo(self):
        """FIX(2026-08-26): COMBO 模拟持仓实时价 + TP/SL 状态（/live AJAX 每 5 秒调用）"""
        try:
            led = json.loads(Path('/root/.hermes/smc_monitor/paper_ledger.json').read_text(encoding='utf-8'))
        except Exception:
            led = []
        active = [t for t in led if t.get('status') != 'CLOSED']
        active.sort(key=lambda t: (int(t.get('rank_score', 0) or 0), str(t.get('signal_date', ''))), reverse=True)
        # 实时价（新浪批量）
        import urllib.request, io as _io
        px = {}
        codes = [t['code'] for t in active][:80]
        syms = []
        for c in codes:
            ex = 'sh' if c.startswith('6') else 'sz'
            syms.append(ex + c)
        try:
            url = 'https://hq.sinajs.cn/list=' + ','.join(syms)
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn'})
            with urllib.request.urlopen(req, timeout=10) as r:
                b = r.read().decode('gbk', errors='replace')
            for line in b.strip().split('\n'):
                if 'hq_str_' not in line:
                    continue
                parts = line.split('="', 1)
                sym = parts[0].split('_')[-1]
                vals = parts[1].rstrip('";').split(',')
                if len(vals) > 3 and vals[3]:
                    try:
                        _p = float(vals[3])
                        if _p > 0:
                            px[sym[2:]] = _p
                    except Exception:
                        pass
        except Exception:
            pass
        items = []
        for t in active:
            code = t.get('code')
            ep = t.get('filled_price') or t.get('entry_price') or 0
            cur = px.get(code) or t.get('mark_price') or ep
            pnl = round((cur / ep - 1) * 100, 2) if ep else 0
            items.append({
                'code': code, 'name': t.get('name', ''), 'status': t.get('status', ''),
                'entry_price': ep, 'price': round(cur, 3), 'pnl_pct': pnl,
                'tp1': t.get('tp1'), 'tp2': t.get('tp2'), 'tp3': t.get('tp3'), 'tp4': t.get('tp4', t.get('tp_price')),
                'sl1': t.get('sl1', t.get('sl_price')), 'sl2': t.get('sl2'),
                't1_locked': bool(t.get('t1_locked')), 'tp1_hit': bool(t.get('tp1_hit')),
                'signal_date': t.get('signal_date', ''),
            })
        return {'ok': True, 'ts': datetime.now().strftime('%H:%M:%S'), 'count': len(items), 'items': items}

    def _api_live_prices(self):
        """返回实时价格+SL/TP状态"""
        import datetime
        # Check A-share trading hours (Mon-Fri 9:30-11:30, 13:00-15:00 CST)
        now = dtmod.datetime.now(dtmod.timezone(dtmod.timedelta(hours=8)))
        latest_data_date = _latest_data_date()
        registry = _production_registry()
        if _production_empty_book():
            epoch = _current_committed_data_epoch(registry.get('data_epoch') or {})
            latest_data_date = _date_key(epoch.get('market_date')) or latest_data_date
        scan_meta = _ops_scan_meta()
        weekday = now.weekday()  # 0=Mon..6=Sun
        t = now.hour * 60 + now.minute
        market_open = weekday < 5 and ((570 <= t < 690) or (780 <= t < 900))  # 9:30-11:30 or 13:00-15:00
        
        positions_all = load_positions() if load_positions else []
        def _position_engine(pos):
            raw = pos.get('raw_pick') if isinstance(pos.get('raw_pick'), dict) else {}
            return str(raw.get('engine') or pos.get('engine') or '')
        promoted_prefix = FRONTEND_VERSION if FRONTEND_VERSION != ACTIVE_VERSION else ''
        # Realtime page must be same-source with the active/promoted production engine.
        # Older clean monitor positions remain in state/history, but are not mixed
        # into live rows; if no matching monitor positions exist, fall back to picks.
        production_strategy = _production_registry().get('production_strategy') or ''
        positions = [p for p in positions_all if _position_engine(p).startswith(ACTIVE_VERSION) or (promoted_prefix and _position_engine(p).startswith(promoted_prefix)) or _position_engine(p) == production_strategy]
        use_monitor_positions = bool(positions) and ACTIVE_VERSION != 'V68'
        pending_fill_pre = fill_pending_orders() if (fill_pending_orders and use_monitor_positions) else {'changed': 0}
        if pending_fill_pre.get('changed') and load_positions:
            positions = load_positions()
        open_positions = [p for p in positions if p.get('status') == 'OPEN'] if use_monitor_positions else []
        pending_positions = [p for p in positions if p.get('status') == 'NEXT_DAY_PENDING'] if use_monitor_positions else []
        picks = []
        for pos in open_positions + pending_positions:
            raw = dict(pos.get('raw_pick') or {})
            raw.setdefault('symbol', pos.get('symbol'))
            raw.setdefault('pick_date', pos.get('pick_date'))
            raw['select_date'] = raw.get('select_date') or pos.get('pick_date')
            raw['entry_date'] = raw.get('entry_date') if pos.get('status') == 'NEXT_DAY_PENDING' else (monitor_date_key(pos.get('created_at')) if monitor_date_key else pos.get('created_at'))
            raw['buy_date'] = monitor_date_key(pos.get('created_at')) if (monitor_date_key and pos.get('status') == 'OPEN') else ''
            raw['join_date'] = monitor_date_key(pos.get('join_date') or pos.get('joined_at') or pos.get('created_at')) if monitor_date_key else (pos.get('join_date') or '')
            raw['_monitor_status'] = pos.get('status')
            raw['entry_price'] = pos.get('entry_price')
            raw['price'] = pos.get('entry_price')
            raw['sl'] = pos.get('sl_price')
            raw['tp1'] = pos.get('tp1_price')
            raw['risk_pct'] = pos.get('risk_pct')
            raw['v25_sl_price'] = pos.get('sl_price')
            raw['v25_sl_pct'] = pos.get('risk_pct')
            raw['v25_tp_tiers'] = [{'price': pos.get('tp1_price'), 'pct': round((float(pos.get('tp1_price') or 0) - float(pos.get('entry_price') or 0)) / float(pos.get('entry_price') or 1) * 100, 1)}]
            if not raw.get('zone_type'):
                raw['zone_type'] = pos.get('zone_type') or pos.get('signal_type') or raw.get('engine') or ''
            if not raw.get('signal_type'):
                raw['signal_type'] = raw.get('zone_type') or pos.get('signal_type') or ''
            if not raw.get('conf_type'):
                raw['conf_type'] = pos.get('conf_type')
            if not raw.get('zone_low'):
                raw['zone_low'] = pos.get('zone_low') or pos.get('raw_zone_low') or (pos.get('production_gate') or {}).get('zone_low')
            if not raw.get('zone_high'):
                raw['zone_high'] = pos.get('zone_high') or pos.get('raw_zone_high') or (pos.get('production_gate') or {}).get('zone_high')
            if not raw.get('raw_zone_low'):
                raw['raw_zone_low'] = raw.get('zone_low')
            if not raw.get('raw_zone_high'):
                raw['raw_zone_high'] = raw.get('zone_high')
            raw['smart_money_cost'] = raw.get('smart_money_cost') or pos.get('cost_line') or pos.get('smart_money_cost') or ((float(raw.get('zone_low') or 0) + float(raw.get('zone_high') or 0)) / 2 if raw.get('zone_low') and raw.get('zone_high') else pos.get('entry_price'))
            raw['cost_line'] = raw.get('cost_line') or raw.get('smart_money_cost') or pos.get('entry_price')
            raw['v25_cost_line'] = raw.get('v25_cost_line') or pos.get('cost_line') or raw.get('smart_money_cost') or raw.get('cost_line')
            raw['volatility_pct'] = raw.get('volatility_pct') or pos.get('volatility_pct') or pos.get('risk_pct') or raw.get('risk_pct') or 0
            raw['v25_vol_class'] = raw.get('v25_vol_class') or pos.get('vol_class') or raw.get('market_state') or raw.get('quality_tier') or (f"RISK {float(raw.get('volatility_pct') or 0):.1f}%" if raw.get('volatility_pct') else raw.get('zone_type') or '')
            raw['production_gate'] = pos.get('production_gate_current') or pos.get('production_gate') or {}
            raw['entry_zone_relation'] = pos.get('entry_zone_relation') or (raw.get('production_gate') or {}).get('entry_zone_relation') or ''
            raw['entry_zone_distance_pct'] = pos.get('entry_zone_distance_pct') or (raw.get('production_gate') or {}).get('entry_zone_distance_pct') or 0
            raw['_monitor_position_id'] = pos.get('id')
            raw['_monitor_created_at'] = pos.get('created_at')
            picks.append(raw)
        if not picks:
            picks = get_active_picks()
        if not picks:
            registry = _production_registry()
            current = _load_json_dict(Path('/root/.hermes/smc_audit/v700_pure_smc_ssl_reclaim_current_scanner_latest.json'), {})
            funnel = ((current.get('diagnostic_funnel') or {}).get('counts') or {})
            self._json({
                'error': '无实时监控持仓',
                'picks': [],
                'market_open': market_open,
                'dataDate': latest_data_date,
                'scanMeta': scan_meta,
                'currentScanner': {
                    'generated_at': current.get('generated_at', ''),
                    'epoch_id': current.get('epoch_id', ''),
                    'market_date': current.get('market_date', ''),
                    'decision': current.get('decision', ''),
                    'pending_next_open_count': current.get('pending_next_open_count', 0),
                    'buy_valid_count': current.get('buy_valid_count', 0),
                    'funnel': funnel,
                    'production_admission': False,
                    'reason': 'EMPTY_BOOK_BLOCKS_PRODUCTION_ADMISSION',
                },
                'production_state': registry.get('state'),
                'production_strategy': registry.get('production_strategy'),
                'shadow_challenger': registry.get('shadow_challenger'),
                'buy_enabled': registry.get('buy_enabled', False),
                'active_buy_valid_count': registry.get('active_buy_valid_count', 0),
                'forbidden_fallback': registry.get('forbidden_fallback', True),
            })
            return
        
        # Filter fallback pick-file candidates only; durable monitor positions are the realtime source of truth.
        from datetime import timedelta
        cutoff = (now - timedelta(days=45)).strftime('%Y%m%d')
        def pick_recent_date(p):
            return _date_key(p.get('pick_date') or p.get('conf_date') or p.get('retrace_date') or p.get('entry_date') or p.get('signal_date') or p.get('date'))
        if not open_positions and ACTIVE_VERSION != 'V68':
            picks = [p for p in picks if pick_recent_date(p) >= cutoff]
            if not picks:
                self._json({'error': '无近期选股(45天内)', 'picks': [], 'market_open': market_open, 'dataDate': latest_data_date, 'scanMeta': scan_meta, 'cutoff': cutoff, 'active_count': len(get_active_picks())}); return
        
        # Convert symbols to pure codes
        code_map = {}
        for p in picks:
            sym = p['symbol']
            code = sym.replace('.SH','').replace('.SZ','').replace('.BJ','')
            code_map[code] = p
        
        # Batch fetch (max 500 per call; only when market open)
        codes = list(code_map.keys())
        all_prices = {}
        if market_open:
            for i in range(0, len(codes), 500):
                batch = codes[i:i+500]
                all_prices.update(Handler.fetch_live_prices(batch))

        def _last_cached_bar(symbol):
            sym_file = symbol.replace('.SH','_SH').replace('.SZ','_SZ').replace('.BJ','_BJ')
            for fp in (CACHE / f'{sym_file}_daily_750.json', CACHE / f'{sym_file}_daily_300.json'):
                if fp.exists():
                    try:
                        arr = json.loads(fp.read_text())
                        if arr:
                            b = arr[-1]
                            price = float(b.get('c') or 0)
                            high = float(b.get('h') or 0)
                            low = float(b.get('l') or 0)
                            prev = float(arr[-2].get('c') or 0) if len(arr) > 1 else 0
                            d = str(b.get('t') or b.get('date') or '')[:8]
                            return {'price': price, 'high': high, 'low': low, 'prev_close': prev, 'date': d}
                    except Exception:
                        pass
            return {'price': 0, 'high': 0, 'low': 0, 'prev_close': 0, 'date': ''}
        
        result_picks = []
        open_positions = load_positions() if (load_positions and use_monitor_positions) else []
        open_by_symbol = {}
        for pos in open_positions:
            if pos.get('status') == 'OPEN':
                open_by_symbol.setdefault(pos.get('symbol'), []).append(pos)
        for p in picks:
            p = _apply_smc_field_contract(p, default_engine=ACTIVE_VERSION)
            sym = p['symbol']
            code = sym.replace('.SH','').replace('.SZ','').replace('.BJ','')
            quote = all_prices.get(code, {})
            last_bar = _last_cached_bar(sym)
            live_price = float(quote.get('price') or 0)
            last_price = live_price or float(last_bar.get('price') or 0)
            current_price = last_price
            if live_price > 0:
                price_status = '实时'
            elif not market_open and last_price > 0:
                price_status = '休市-最后K线'
            elif market_open and last_price > 0:
                price_status = '停牌/无实时-最后K线'
            else:
                price_status = '无价格'
            entry_price = p.get('price', 0) or p.get('entry_price', 0)
            
            # Prefer V25 dynamic SL/TP if available
            if 'v25_sl_price' in p:
                sl_price = p['v25_sl_price']
                sl_pct = p['v25_sl_pct']
                tp_tiers_list = p.get('v25_tp_tiers', [])
                tp_pct = tp_tiers_list[0]['pct'] if tp_tiers_list else 0
                tp_price = tp_tiers_list[0]['price'] if tp_tiers_list else 0
                cost_line = p.get('v25_cost_line') or p.get('smart_money_cost') or p.get('cost_line') or entry_price
                vol_class = p.get('v25_vol_class') or p.get('market_state') or p.get('regime') or p.get('quality_tier') or (f"RISK {float(sl_pct):.1f}%" if sl_pct else p.get('zone_type', ''))
            else:
                # V28/V27: use flat fields + tiers
                sl_pct = float(p.get('risk_pct') or p.get('sl_initial_pct') or 0)
                if not sl_pct and entry_price and p.get('sl', 0):
                    sl_pct = round((entry_price - float(p['sl'])) / entry_price * 100, 1)
                sl_price = float(p.get('sl') or 0) or (entry_price * (1 - float(sl_pct) / 100) if entry_price and sl_pct else 0)
                # TP from flat fields or tiers
                tp1_raw = p.get('tp1', 0) or (p.get('tp_tiers', [{}])[0].get('price', 0) if p.get('tp_tiers') else 0)
                tp1 = float(tp1_raw or 0)
                tp_pct = round((tp1 - entry_price) / entry_price * 100, 1) if tp1 and entry_price else 0
                tp_price = tp1
                # Cost line from smart_money_cost
                cost_line = p.get('smart_money_cost') or p.get('cost_line') or entry_price
                vol_class = p.get('market_state') or p.get('regime') or p.get('quality_tier') or (f"RISK {float(sl_pct):.1f}%" if sl_pct else p.get('zone_type', ''))
            if not cost_line:
                zl = float(p.get('zone_low') or p.get('raw_zone_low') or 0)
                zh = float(p.get('zone_high') or p.get('raw_zone_high') or 0)
                cost_line = ((zl + zh) / 2) if zl and zh else entry_price
            if not vol_class:
                vol_class = f"RISK {float(sl_pct or 0):.1f}%" if sl_pct else (p.get('zone_type') or p.get('signal_type') or 'UNKNOWN')
            zone_type_out = p.get('zone_type') or p.get('signal_type') or p.get('v59_setup_family') or p.get('engine') or 'UNKNOWN'
            
            is_monitor_row = bool(p.get('_monitor_status'))
            active_candidate = bool(p.get('pick_scope') == 'ACTIVE_CANDIDATE' and p.get('is_active_pick'))
            registry_buy_enabled = _production_registry().get('buy_enabled') is True
            is_tradable_row = is_monitor_row or (active_candidate and registry_buy_enabled)
            # Live guard must be evaluated against the current/live price, not just
            # the scanner-time cached price used when the watchlist artifact was built.
            live_guard_threshold = float(p.get('live_guard_threshold_pct') or 1.5)
            live_guard_status = p.get('live_guard_status') or ''
            live_guard_reason = p.get('live_guard_reason') or ''
            if active_candidate and not is_monitor_row and not registry_buy_enabled:
                live_guard_status = 'WATCH_ONLY_PRODUCTION_REGISTRY_BLOCKED'
                live_guard_reason = 'PRODUCTION_REGISTRY_BUY_DISABLED'
            current_entry_gap_pct = ((current_price - entry_price) / entry_price * 100) if current_price and entry_price else None
            if is_tradable_row and not is_monitor_row and current_price and entry_price:
                if sl_price and current_price <= sl_price:
                    live_guard_status = 'WATCH_ONLY_SL_ALREADY_HIT'
                    live_guard_reason = 'CURRENT_LIVE_PRICE_BELOW_OR_EQUAL_SL'
                    is_tradable_row = False
                elif tp_price and current_price >= tp_price:
                    live_guard_status = 'WATCH_ONLY_TP_ALREADY_HIT'
                    live_guard_reason = 'CURRENT_LIVE_PRICE_ABOVE_OR_EQUAL_TP'
                    is_tradable_row = False
                elif abs(current_entry_gap_pct or 0) > live_guard_threshold:
                    live_guard_status = 'WATCH_ONLY_PRICE_NOT_NEAR_ENTRY'
                    live_guard_reason = 'CURRENT_LIVE_PRICE_NOT_WITHIN_ENTRY_GAP'
                    is_tradable_row = False
                else:
                    live_guard_status = 'BUY_VALID'
                    live_guard_reason = 'CURRENT_LIVE_PRICE_WITHIN_ENTRY_GAP_AND_NOT_TP_SL'

            # Determine status. Fallback pick-file WATCH_ONLY rows are context only:
            # do not compute live PnL/SL/TP states as if they were held positions.
            if not is_tradable_row:
                pnl_pct = 0
                status = 'WATCH_ONLY_CONTEXT' if p.get('pick_scope') == 'WATCH_ONLY' else 'NON_TRADABLE_CONTEXT'
            elif p.get('_monitor_status') == 'NEXT_DAY_PENDING':
                pnl_pct = 0
                status = 'NEXT_DAY_PENDING'
            elif current_price > 0 and entry_price > 0:
                pnl_pct = (current_price - entry_price) / entry_price * 100
                if live_price <= 0:
                    status = 'NO_LIVE_LAST_PRICE'
                elif current_price <= sl_price:
                    status = 'SL_HIT'
                elif current_price >= tp_price:
                    status = 'TP_HIT'
                elif current_price <= entry_price * (1 - float(sl_pct) * 0.7 / 100):
                    status = 'SL_CLOSE'
                elif current_price >= entry_price * (1 + tp_pct * 0.8 / 100):
                    status = 'TP_CLOSE'
                else:
                    status = 'HOLDING'
                if status in ('SL_HIT', 'TP_HIT') and t1_exit_allowed:
                    same_day_pos = next((pos for pos in open_by_symbol.get(sym, []) if not t1_exit_allowed(pos)), None)
                    if same_day_pos:
                        status = 'T1_LOCKED'
            else:
                pnl_pct = 0
                status = 'NO_DATA'
            
            result_picks.append({
                'symbol': sym,
                'name': quote.get('name', ''),
                'entryPrice': round(entry_price, 2),
                'entry_price': round(entry_price, 2),
                'currentPrice': round(current_price, 2) if current_price else 0,
                'lastPrice': round(last_price, 2) if last_price else 0,
                'livePrice': round(live_price, 2) if live_price else 0,
                'priceStatus': price_status,
                'lastPriceDate': last_bar.get('date', ''),
                'chgPct': round(quote.get('chgPct', 0), 2),
                'pnlPct': round(pnl_pct, 2),
                'slPct': round(sl_pct, 1),
                'slPrice': round(sl_price, 2),
                'sl': round(sl_price, 2),
                'tpTiers': [round(tp_pct, 1)] if tp_pct else [],
                'tpPrice': round(tp_price, 2),
                'tp1': round(tp_price, 2),
                'tp2': round(float(p.get('tp2') or 0), 2) if p.get('tp2') else 0,
                'tp3': round(float(p.get('tp3') or 0), 2) if p.get('tp3') else 0,
                'rr': round(((tp_price - entry_price) / (entry_price - sl_price)), 4) if tp_price and entry_price and sl_price and entry_price > sl_price else (float(p.get('rr') or 0) if p.get('rr') else 0),
                'status': status,
                'entryDate': p.get('buy_date') or p.get('entry_date', ''),
                'pickDate': p.get('select_date') or p.get('pick_date', ''),
                'joinDate': p.get('join_date', ''),
                'entry_date': p.get('buy_date') or p.get('entry_date', ''),
                'select_date': p.get('select_date') or p.get('pick_date', ''),
                'selectDate': p.get('selectDate') or p.get('select_date') or p.get('pick_date', ''),
                'pick_date': p.get('select_date') or p.get('pick_date', ''),
                'join_date': p.get('join_date', ''),
                '选股日期': p.get('select_date') or p.get('pick_date', ''),
                '加入日期': p.get('join_date', ''),
                'engine': p.get('engine') or ACTIVE_VERSION,
                'pickScope': p.get('pick_scope') or '',
                'isActivePick': bool(p.get('is_active_pick')),
                'isTradableLive': bool(is_tradable_row),
                'tradable': bool(is_tradable_row),
                'monitorStatus': p.get('_monitor_status', ''),
                'dataDate': latest_data_date,
                'signalSeq': p.get('seq', p.get('ctx_seq', p.get('detail', ''))),
                'event_type': p.get('event_type') or '',
                'original_event_type': p.get('original_event_type') or '',
                'semantic_contract_key': p.get('semantic_contract_key') or '',
                'classical_structure_status': p.get('classical_structure_status') or '',
                'classical_sweep_choch_claim': p.get('classical_sweep_choch_claim') or '',
                'signal_type': p.get('signal_type') or zone_type_out,
                'zoneType': zone_type_out,
                'zone_type': zone_type_out,
                'zone': (f"{float(p.get('zone_low') or 0):.2f}~{float(p.get('zone_high') or 0):.2f}" if p.get('zone_low') and p.get('zone_high') else zone_type_out),
                'confType': p.get('conf_type', ''),
                'conf_type': p.get('conf_type', ''),
                'signal_price': round(float(p.get('signal_price') or p.get('break_level') or p.get('price') or entry_price or 0), 3),
                'signal_date': p.get('signal_date') or p.get('pick_date') or p.get('select_date') or p.get('entry_date') or '',
                'risk_pct': round(float(p.get('risk_pct') or sl_pct or 0), 4),
                'riskPct': round(float(p.get('risk_pct') or sl_pct or 0), 4),
                'sl_pct': round(float(sl_pct or p.get('risk_pct') or 0), 4),
                'pnl_pct': round(pnl_pct, 2),
                'hold_bars': (p.get('hold_bars_realized') or p.get('hold_bars') or 0) if is_tradable_row else 0,
                'exit_reason': (p.get('exit_reason') or status) if is_tradable_row else status,
                'costLine': round(cost_line, 2) if cost_line else 0,
                'cost_line': round(cost_line, 2) if cost_line else 0,
                'smart_money_cost': round(cost_line, 2) if cost_line else 0,
                'volClass': vol_class,
                'vol_class': vol_class,
                'volatility_pct': round(float(p.get('volatility_pct') or sl_pct or 0), 2),
                'volatilityPct': round(float(p.get('volatility_pct') or sl_pct or 0), 2),
                'volatility': round(float(p.get('volatility_pct') or sl_pct or 0), 2),
                'zoneLow': round(float(p.get('zone_low') or 0), 2) if p.get('zone_low') else 0,
                'zoneHigh': round(float(p.get('zone_high') or 0), 2) if p.get('zone_high') else 0,
                'zone_low': round(float(p.get('zone_low') or 0), 2) if p.get('zone_low') else 0,
                'zone_high': round(float(p.get('zone_high') or 0), 2) if p.get('zone_high') else 0,
                'entryZoneRelation': p.get('entry_zone_relation', ''),
                'entryZoneDistancePct': round(float(p.get('entry_zone_distance_pct') or 0), 2),
                'semanticLayer': p.get('semantic_layer') or 'UNAUDITED',
                'semantic_layer': p.get('semantic_layer') or 'UNAUDITED',
                'strictAuditStatus': p.get('strict_audit_status') or 'UNAUDITED',
                'strict_audit_status': p.get('strict_audit_status') or 'UNAUDITED',
                'signalCorrectnessClaim': p.get('signal_correctness_claim') or 'PENDING_REPLAY',
                'signal_correctness_claim': p.get('signal_correctness_claim') or 'PENDING_REPLAY',
                'entryMode': p.get('entry_mode') or '',
                'entry_mode': p.get('entry_mode') or '',
                'v91_gate_reason': p.get('v91_gate_reason') or '',
                'v91_entry_layer': p.get('v91_entry_layer') or '',
                'marketState': p.get('market_state') or p.get('regime') or '',
                'market_state': p.get('market_state') or p.get('regime') or '',
                'semanticIssues': p.get('semantic_issues') or [],
                'semantic_issues': p.get('semantic_issues') or [],
                'entry_zone_position': p.get('entry_zone_position'),
                'trend_tf': p.get('trend_tf'),
                'signal_tf': p.get('signal_tf'),
                'entry_tf': p.get('entry_tf'),
                'weekly_state': p.get('weekly_state'),
                'daily_state': p.get('daily_state'),
                'm60_state': p.get('m60_state'),
                'weekly_trend_state': p.get('weekly_trend_state'),
                'daily_trend_state': p.get('daily_trend_state'),
                'm60_trend_state': p.get('m60_trend_state'),
                'weekly_phase': p.get('weekly_phase'),
                'daily_phase': p.get('daily_phase'),
                'm60_phase': p.get('m60_phase'),
                'weekly_permission': p.get('weekly_permission'),
                'daily_permission': p.get('daily_permission'),
                'm60_permission': p.get('m60_permission'),
                'weekly_conflict': p.get('weekly_conflict'),
                'daily_conflict': p.get('daily_conflict'),
                'm60_conflict': p.get('m60_conflict'),
                'weekly_structure_state': p.get('weekly_structure_state'),
                'daily_structure_state': p.get('daily_structure_state'),
                'm60_structure_state': p.get('m60_structure_state'),
                'mtf_stage': p.get('mtf_stage'),
                'mtf_trend_permission': p.get('mtf_trend_permission'),
                'mtf_conflict_state': p.get('mtf_conflict_state'),
                'smc_dna': p.get('smc_dna') or {},
                'dna_preferred_behavior': p.get('dna_preferred_behavior'),
                'dna_effective_entry_mode': p.get('dna_effective_entry_mode'),
                'dna_effective_combo': p.get('dna_effective_combo'),
                'combo_contract_key': p.get('combo_contract_key'),
                'combo_family': p.get('combo_family'),
                'combo_contract': p.get('combo_contract') or {},
                'combo_entry_rule': p.get('combo_entry_rule'),
                'combo_wait_rule': p.get('combo_wait_rule'),
                'combo_sl_rule': p.get('combo_sl_rule'),
                'combo_tp_rule': p.get('combo_tp_rule'),
                'combo_production_gate': p.get('combo_production_gate'),
                'production_whitelist_v101': p.get('production_whitelist_v101'),
                'production_eligible_v101': p.get('production_eligible_v101'),
                'v102_balanced_volume_gate': p.get('v102_balanced_volume_gate'),
                'production_eligible_v102': p.get('production_eligible_v102'),
                'production_grade_v101': p.get('production_grade_v101'),
                'combo_candidate_whitelist_v101': p.get('combo_candidate_whitelist_v101'),
                'combo_candidate_eligible_v101': p.get('combo_candidate_eligible_v101'),
                'combo_candidate_gate_reason_v101': p.get('combo_candidate_gate_reason_v101') or '',
                'productionGate': p.get('production_gate') or {},
                'live_guard_status': live_guard_status,
                'live_guard_reason': live_guard_reason,
                'live_guard_price_gap_pct': p.get('live_guard_price_gap_pct'),
                'current_entry_gap_pct': round(current_entry_gap_pct, 2) if current_entry_gap_pct is not None else None,
                'tradeAction': 'BUY' if is_tradable_row else 'WATCH_ONLY',
                'trade_action': 'BUY' if is_tradable_row else 'WATCH_ONLY',
            })
        
        # Sort: SL/TP hit first, then by PnL
        status_order = {'SL_HIT': 0, 'TP_HIT': 1, 'T1_LOCKED': 2, 'SL_CLOSE': 3, 'TP_CLOSE': 4, 'HOLDING': 5, 'NO_LIVE_LAST_PRICE': 6, 'NEXT_DAY_PENDING': 7, 'NO_DATA': 8}
        result_picks.sort(key=lambda x: (status_order.get(x['status'], 9), -(x['pnlPct'] or 0)))
        tradable_live_count = sum(1 for p in result_picks if p.get('isTradableLive'))
        watch_context_count = sum(1 for p in result_picks if not p.get('isTradableLive'))
        
        error_msg = ''
        if not market_open:
            error_msg = '休市 (交易时间: 周一至周五 9:30-11:30, 13:00-15:00)'
        elif not all_prices:
            error_msg = 'Hubble API无数据 (API故障或网络问题)'
        
        monitor_update = update_with_live_results(result_picks) if update_with_live_results else {'changed': 0}
        if pending_fill_pre.get('changed'):
            monitor_update['pending_fill_pre'] = pending_fill_pre
        ledger = [r for r in (load_trade_ledger() if load_trade_ledger else []) if str(r.get('engine') or '').startswith(ACTIVE_VERSION)]
        live_by_symbol = {p.get('symbol'): p for p in result_picks}
        pos_by_id = {p.get('id'): p for p in positions if p.get('id')}
        today_key = now.strftime('%Y%m%d')
        ledger_out = []
        for r in ledger:
            if r.get('invalidated'):
                continue
            rr = dict(r)
            live = live_by_symbol.get(rr.get('symbol'), {})
            pos = pos_by_id.get(rr.get('position_id'), {})
            raw_pick = pos.get('raw_pick') or {}
            if not rr.get('engine'):
                rr['engine'] = raw_pick.get('engine') or pos.get('engine') or ACTIVE_VERSION
            if not rr.get('zone'):
                zl = pos.get('zone_low') or raw_pick.get('zone_low') or raw_pick.get('dz_low')
                zh = pos.get('zone_high') or raw_pick.get('zone_high') or raw_pick.get('dz_high')
                rr['zone'] = (f"[{float(zl):.2f}~{float(zh):.2f}]" if zl and zh else (pos.get('zone_type') or raw_pick.get('zone_type') or raw_pick.get('signal_type') or '-'))
            contracted = _apply_smc_field_contract({**raw_pick, **pos, **rr}, default_engine=rr.get('engine') or ACTIVE_VERSION)
            rr['select_date'] = rr.get('select_date') or contracted.get('select_date') or contracted.get('pick_date')
            rr['join_date'] = rr.get('join_date') or contracted.get('join_date') or rr.get('buy_date') or rr.get('event_date')
            rr['zone_type'] = rr.get('zone_type') or contracted.get('zone_type') or rr.get('zone')
            rr['cost_line'] = rr.get('cost_line') or contracted.get('cost_line')
            rr['smart_money_cost'] = rr.get('smart_money_cost') or contracted.get('smart_money_cost')
            rr['volatility_pct'] = rr.get('volatility_pct') or contracted.get('volatility_pct')
            rr['volClass'] = rr.get('volClass') or contracted.get('v25_vol_class')
            rr['vol_class'] = rr.get('vol_class') or contracted.get('v25_vol_class')
            if rr.get('action') == 'BUY' and live:
                rr['current_price'] = live.get('currentPrice') or rr.get('current_price')
                rr['pnl_pct'] = live.get('pnlPct') if live.get('currentPrice') else rr.get('pnl_pct')
            rr['is_today'] = rr.get('event_date') == today_key
            ledger_out.append(rr)
        ledger_out.sort(key=lambda x: (x.get('event_date',''), x.get('created_at','')), reverse=True)
        self._json({'picks': result_picks, 'total': len(result_picks), 'tradableLiveCount': tradable_live_count, 'watchContextCount': watch_context_count, 'error': error_msg, 'market_open': market_open, 'dataDate': latest_data_date, 'scanMeta': scan_meta, 'lastScanAt': scan_meta.get('last_scan_at'), 'latestScanDate': scan_meta.get('latest_scan_date'), 'monitor_update': monitor_update, 'tradeLedger': ledger_out})

    # ═══ Trading Simulator API ═══
    def _api_trade_status(self):
        import sys; sys.path.insert(0, '/tmp')
        from trading_sim import TradingSimulator
        sim = TradingSimulator()
        self._json(sim.summary())
    
    def _api_trade_scan(self, qs):
        import sys; sys.path.insert(0, '/tmp')
        from trading_sim import TradingSimulator, auto_scan_and_trade
        sim = TradingSimulator()
        dry = qs.get('dry', ['0'])[0] == '1'
        result = auto_scan_and_trade(sim, '/root/.hermes/smc_opt_v19/v19_picks.json', dry_run=dry)
        self._json(result)
    
    def _api_trade_check(self):
        import sys; sys.path.insert(0, '/tmp')
        from trading_sim import TradingSimulator
        sim = TradingSimulator()
        orders = sim.check_positions()
        self._json({'orders': [o.__dict__ for o in orders]})

    def _static_file(self, path, mime):
        if path.exists():
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.end_headers()
            self.wfile.write(path.read_bytes())
        else:
            self.send_response(404); self.end_headers()

    def _api_kline_full(self, qs):
        symbol = qs.get('symbol', ['600519.SH'])[0]
        # FIX(2026-08-20): support no-suffix symbols (603629 -> 603629.SH)
        if '.' not in symbol:
            symbol = symbol + ('.SH' if symbol.startswith(('6', '9')) else '.SZ')
        tf = qs.get('tf', ['daily'])[0]
        ver = qs.get('ver', [ACTIVE_VERSION])[0]
        if str(ver).upper() in ('V517', 'V517_EFFORT_RESULT'):
            if tf != 'daily':
                self._json({'error': 'V517 effort-result is a frozen daily OHLCV ontology; only tf=daily is valid', 'version': 'V517_EFFORT_RESULT'})
            else:
                _v517 = v517_frontend.kline(symbol)
                # FIX(2026-08-20): inject v20c backtest trades into every version view
                if isinstance(_v517, dict):
                    try:
                        _v517_klines = _v517.get('klines') or []
                        _v517_idx = {}
                        for _ki, _kb in enumerate(_v517_klines):
                            _kd = str(_kb.get('date', ''))[:8]
                            _v517_idx[_kd] = _ki
                        _v517_trades = _load_v20c_trades_for(symbol, _v517_klines, _v517_idx)
                        if _v517_trades:
                            # set chart indices so frontend buy/sell markers plot correctly
                            for _vt in _v517_trades:
                                _ve = str(_vt.get('entry_date', ''))
                                _vi = _v517_idx.get(_ve, _v517_idx.get(_ve.replace('-', ''), -1))
                                _vt['_chart_idx'] = int(_vi)
                                _xe = str(_vt.get('exit_date', ''))
                                _xi = _v517_idx.get(_xe, _v517_idx.get(_xe.replace('-', ''), -1))
                                _vt['_exit_idx'] = int(_xi) if _xi >= 0 else int(_vi) + 5
                                _vt['engine'] = 'V517'
                            _v517['trades'] = _v517_trades
                            _v517['trade_count'] = len(_v517_trades)
                    except Exception:
                        pass
                self._json(_v517)
            return
        # FIX(2026-08-20): in-memory cache — kline data frozen at 8-19, result unchanged between pulls.
        _ckey = f"{symbol}|{tf}|{ver}|{qs.get('seq',[''])[0]}"
        _cached = _KLINE_FULL_CACHE.get(_ckey)
        if _cached is not None:
            self._json(_cached)
            return
        try:
            fp = None
            if tf == '60min':
                for c in [500, 200]:
                    fp = CACHE_60 / (symbol.replace('.','_') + f'_60min_{c}.json')
                    if fp.exists(): break
            elif tf == 'weekly':
                sym_file = symbol.replace('.SH','_SH').replace('.SZ','_SZ').replace('.BJ','_BJ')
                candidates = [
                    CACHE / f'{sym_file}_weekly_200.json',
                    CACHE / f'{sym_file}_weekly_300.json',
                    CACHE / f'{symbol}_weekly_200.json',
                    CACHE / f'{symbol}_weekly_300.json',
                ]
                fp = next((c for c in candidates if c.exists()), None)
            else:
                sym_file = symbol.replace('.SH','_SH').replace('.SZ','_SZ').replace('.BJ','_BJ')
                # FIX(2026-08-20): prefer refreshed tencent 800-bar cache (contains 8-19)
                # so sim markers / signal dates map to the current date universe.
                candidates = [
                    Path(r'E:\test\smc_project\hermes\kline_cache_tencent') / f'{sym_file}_daily_800.json',
                    CACHE / f'{sym_file}_daily_750.json',
                    CACHE / f'{sym_file}_daily_300.json',
                    CACHE / f'{symbol}_daily_750.json',
                    CACHE / f'{symbol}_daily_300.json',
                ]
                fp = next((c for c in candidates if c.exists()), None)

            if not fp or not fp.exists():
                self._json({'error': f'No data: {symbol}'}); return

            data = json.loads(fp.read_bytes())
            klines = []
            for b in data:
                d = str(b.get('t', b.get('date', '')))
                klines.append({'date': d[:16] if d else '', 'o': float(b['o']), 'h': float(b['h']), 'l': float(b['l']), 'c': float(b['c'])})
            chart_date_idx = {}
            for i, k in enumerate(klines):
                d = str(k.get('date', ''))[:10]
                if d:
                    chart_date_idx[d] = i
                    chart_date_idx[d.replace('-', '')] = i

            # V36/V34D chart markers must use the same mixed signal source as
            # the trading engine: LuxAlgo leg/displayStructure for
            # BOS/CHOCH/MSS + Sweep + OB, and Pine-like only for FVG/BPR/EQL/LV/OTE
            # display. Previously the Kline page rendered all raw markers from
            # smc_core_pine_like, so trade highlights and zone markers could
            # disagree with V34D/V36 backtest entries.
            if ver in ('V50', 'V51', 'V52', 'V53', 'V54', 'V55', 'V56', 'V57', 'V58', 'V59', 'V60', 'V61', 'V62', 'V63', 'V64', 'V65', 'V66'):
                signals_list = load_v50_signal_snapshot(symbol)
                if signals_list:
                    signals_list = [dict(s) for s in signals_list]
                    signals_list.sort(key=lambda s: (int(s.get('idx', 0) or 0), str(s.get('family', '')), str(s.get('type', ''))))
                    for s in signals_list:
                        if s.get('family') == 'structure':
                            typ = str(s.get('type', ''))
                            if typ.startswith('BOS_'):
                                s['family'] = 'bos'
                            elif typ.startswith('CHOCH_'):
                                s['family'] = 'choch'
                            elif typ.startswith('MSS_'):
                                s['family'] = 'mss'
                            prov = s.get('provenance') or {}
                            if prov:
                                s.setdefault('pivot_idx', prov.get('pivot_idx'))
                                s.setdefault('pivot_date', prov.get('pivot_date'))
                                s.setdefault('pivot_price', prov.get('pivot_price'))
                                s.setdefault('pivot_label', prov.get('pivot_label'))
                                s.setdefault('line_start_idx', prov.get('line_start_idx', prov.get('pivot_idx')))
                                s.setdefault('line_end_idx', prov.get('line_end_idx', s.get('idx')))
                                s.setdefault('line_start_price', prov.get('pivot_price', s.get('price')))
                                s.setdefault('line_end_price', prov.get('pivot_price', s.get('price')))
                                s.setdefault('source_level', prov.get('source_level'))
                                s.setdefault('sweep_date', prov.get('sweep_date'))
                            s.setdefault('line_semantics', 'LuxAlgo currentLevel: previous confirmed swing/internal level -> first close break')
                            s.setdefault('line_direction', s.get('direction'))
                            s.setdefault('from_left', 'confirmed pivot/currentLevel')
                            s.setdefault('to_right', 'first close crossover/crossunder')
                            s.setdefault('pine_rule', 'LuxAlgo displayStructure + internal MSS snapshot')
                    # Snapshot indices were generated on a confirmation-window coordinate system.
                    # The `date` fields are the auditable anchor dates used by the engine/UI.
                    # Plot by date→current kline index, otherwise every SMC marker is shifted right.
                    def _snap_idx_from_date(v):
                        d = str(v or '')[:10]
                        return chart_date_idx.get(d) if d else None
                    for s in signals_list:
                        old_idx = s.get('idx')
                        has_date = bool(str(s.get('date') or '').strip())
                        new_idx = _snap_idx_from_date(s.get('date'))
                        if new_idx is not None:
                            s['_raw_idx'] = old_idx
                            s['idx'] = new_idx
                        elif has_date:
                            # Out-of-window snapshot signal; do not plot it at a stale numeric idx.
                            s['_skip_chart'] = True
                            continue
                        p_idx = _snap_idx_from_date(s.get('pivot_date'))
                        if p_idx is not None:
                            s['_raw_pivot_idx'] = s.get('pivot_idx')
                            s['pivot_idx'] = p_idx
                            s['line_start_idx'] = p_idx
                        le_idx = _snap_idx_from_date(s.get('line_end_date') or s.get('date'))
                        if le_idx is not None and s.get('line_end_idx') is not None:
                            s['_raw_line_end_idx'] = s.get('line_end_idx')
                            s['line_end_idx'] = le_idx
                        wt_idx = _snap_idx_from_date(s.get('wave_turn_date'))
                        if wt_idx is not None:
                            s['_raw_wave_turn_idx'] = s.get('wave_turn_idx')
                            s['wave_turn_idx'] = wt_idx
                        ev_idx = _snap_idx_from_date(s.get('created_by_event_date'))
                        if ev_idx is not None:
                            s['_raw_created_by_event_index'] = s.get('created_by_event_index')
                            s['created_by_event_index'] = ev_idx
                    signals_list = [s for s in signals_list if not s.get('_skip_chart') and 0 <= int(s.get('idx', -1) or -1) < len(klines)]
                    signals_list.sort(key=lambda s: (int(s.get('idx', 0) or 0), str(s.get('family', '')), str(s.get('type', ''))))
                    swings_list = []
                    for s in signals_list:
                        if s.get('family') == 'swing':
                            swings_list.append({'bar': int(s.get('idx', -1)), 'type': s.get('direction', '').upper(), 'price': s.get('price', 0), 'label': str(s.get('type', 'SWING')).replace('SWING_', ''), 'rule': 'V50 snapshot'})
                    wave_swings_list = list(swings_list)
                    sig_data = {}
                    snapshot_signals_list = list(signals_list)
                else:
                    sig_data = None
                    snapshot_signals_list = None
            else:
                sig_data = None
                snapshot_signals_list = None

            if sig_data is None:
                import smc_core_pine_like as _pine_core
                core_sigs = _pine_core.detect_all_signals_pine_like(data, timeframe=tf)
                sig_data = core_sigs['signals']
            if ver in ('V41', 'V40', 'V39', 'V38', 'V37', 'V36', 'V34D', 'V46_1', 'V47_2', 'V48_1', 'V49', 'V50', 'V51', 'V52', 'V53', 'V54', 'V55', 'V56', 'V57', 'V58', 'V59', 'V60', 'V61', 'V62', 'V63', 'V64', 'V65', 'V66'):
                import smc_core_luxalgo_v34 as _lux_core
                lux_sigs = _lux_core.detect_all_signals_lux_v34(data)['signals']
                sig_data['structure'] = lux_sigs.get('structure', [])
                sig_data['sweeps'] = lux_sigs.get('sweeps', [])
                sig_data['obs'] = lux_sigs.get('obs', [])
                # Draw the wave-reference HH/HL/LH/LL layer, not only Lux currentLevel pivots.
                sig_data['swings'] = lux_sigs.get('wave_swings') or lux_sigs.get('swings', (sig_data or {}).get('swings', {}))
                sig_data['lux_swings'] = lux_sigs.get('swings', {})
                sig_data['wave_swings'] = lux_sigs.get('wave_swings', {})
                sig_data['swing_structure'] = lux_sigs.get('swing_structure', [])
                sig_data['internal_structure'] = lux_sigs.get('internal_structure', [])
            signals_list = snapshot_signals_list if snapshot_signals_list is not None else []
            wave_refs = []
            _wave_src = (sig_data or {}).get('wave_swings')
            if isinstance(_wave_src, dict):
                _wave_iter = list(_wave_src.get('highs', [])) + list(_wave_src.get('lows', []))
            elif isinstance(_wave_src, list):
                _wave_iter = _wave_src
            else:
                _wave_iter = []
            for _w in _wave_iter:
                _wi = _w.get('idx') if _w.get('idx') is not None else (_w.get('index') if _w.get('index') is not None else _w.get('bar'))
                if _wi is not None:
                    wave_refs.append({**_w, '_idx': int(_wi)})
            def _nearest_wave_ref(ev):
                try:
                    pidx = int(ev.get('pivot_bar_index') if ev.get('pivot_bar_index') is not None else ev.get('index'))
                    direction = ev.get('direction')
                    cands = []
                    for w in wave_refs:
                        lab = w.get('label')
                        side_ok = (direction == 'bull' and lab in ('HH','LH','H')) or (direction == 'bear' and lab in ('LL','HL','L'))
                        if side_ok and w['_idx'] <= int(ev.get('index', pidx)) + 1:
                            cands.append((abs(w['_idx'] - pidx), w))
                    return min(cands, key=lambda x: x[0])[1] if cands else None
                except Exception:
                    return None
            # Structure events: BOS, CHOCH, MSS
            struct_map = {'BOS': 'bos', 'CHOCH': 'choch', 'MSS': 'mss'}
            for ev in (sig_data or {}).get('structure', []):
                idx = ev['index']
                if idx >= len(data): continue
                d = str(data[idx].get('t', data[idx].get('date', '')))[:16]
                base_type = ev.get('type', 'BOS')
                wref = _nearest_wave_ref(ev) if ver in ('V47_2','V48_1','V49','V50','V51','V52','V53','V54','V55','V56','V57','V58','V59','V60','V61','V62','V63','V64','V65','V66') else None
                structure_row = {
                    'seq': len(signals_list)+1, 'type': f"{base_type}_{ev['direction'].capitalize()}",
                    'idx': idx, 'date': d,
                    'price': round(ev['price'], 4), 'upper': ev['price'], 'lower': ev['price'],
                    'direction': ev['direction'], 'strength': 0.8,
                    'confidence': 0.85, 'family': struct_map.get(base_type, 'bos'),
                    'pivot_idx': ev.get('pivot_bar_index'), 'pivot_date': ev.get('pivot_bar_time'),
                    'pivot_price': round(float(ev.get('swing_price', ev.get('price', 0)) or 0), 4), 'pivot_label': ev.get('swing_label', ''),
                    'break_price': round(float(ev.get('break_price', 0) or 0), 4),
                    'old_trend': ev.get('old_trend', ''), 'source_level': ev.get('source_level', ''),
                    'line_start_idx': ev.get('line_start_idx', ev.get('pivot_bar_index')),
                    'line_start_date': ev.get('line_start_date', ev.get('pivot_bar_time')),
                    'line_start_price': round(float(ev.get('line_start_price', ev.get('swing_price', ev.get('price', 0))) or 0), 4),
                    'line_end_idx': ev.get('line_end_idx', ev.get('index')),
                    'line_end_date': ev.get('line_end_date', ev.get('date')),
                    'line_end_price': round(float(ev.get('line_end_price', ev.get('swing_price', ev.get('price', 0))) or 0), 4),
                    'line_semantics': ev.get('line_semantics', ''),
                    'line_direction': ev.get('line_direction', ''),
                    'from_left': ev.get('from_left', ''),
                    'to_right': ev.get('to_right', ''),
                    'sweep_date': ev.get('sweep_date', ''), 'sweep_price': ev.get('sweep_price', ''),
                    'displacement_ratio': ev.get('displacement_ratio', ''), 'body_ratio': ev.get('body_ratio', ''),
                    'pine_rule': ev.get('pine_rule', '')
                }
                if wref:
                    structure_row.update({
                        'wave_ref_idx': wref.get('_idx'), 'wave_ref_date': wref.get('date'),
                        'wave_ref_label': wref.get('label'), 'wave_ref_price': wref.get('price'),
                        'wave_ref_distance': abs(int(wref.get('_idx')) - int(ev.get('pivot_bar_index', idx))),
                        'structure_layer': 'lux_currentLevel_with_wave_ref'
                    })
                elif ver in ('V47_2','V48_1','V49','V50','V51','V52','V53','V54','V55','V56','V57','V58','V59','V60','V61','V62','V63','V64','V65','V66'):
                    structure_row['structure_layer'] = 'lux_currentLevel_no_wave_ref'
                signals_list.append(structure_row)
                # MSS is now an independent internal structure event. Do not render
                # CHOCH-attached duplicate MSS markers here.
                if False and ev.get('is_mss') and base_type != 'MSS':
                    signals_list.append({
                        'seq': len(signals_list)+1, 'type': f"MSS_{ev['direction'].capitalize()}",
                        'idx': idx, 'date': d,
                        'price': round(ev['price'], 4), 'upper': ev['price'], 'lower': ev['price'],
                        'direction': ev['direction'], 'strength': 0.85,
                        'confidence': 0.85, 'family': 'mss'
                    })
            # FVGs
            for fv in (sig_data or {}).get('fvgs', []):
                idx = fv['index']
                if idx >= len(data): continue
                d = str(data[idx].get('t', data[idx].get('date', '')))[:16]
                signals_list.append({
                    'seq': len(signals_list)+1, 'type': f"FVG_{fv['direction'].capitalize()}",
                    'idx': idx, 'date': d,
                    'price': round(fv['mid'], 4), 'upper': round(fv['gap_high'], 4),
                    'lower': round(fv['gap_low'], 4),
                    'direction': fv['direction'], 'strength': 0.6,
                    'confidence': 0.7, 'family': 'fvg'
                })
            # OBs
            for ob in (sig_data or {}).get('obs', []):
                idx = ob['index']
                if idx >= len(data): continue
                d = str(data[idx].get('t', data[idx].get('date', '')))[:16]
                zl = ob.get('zone_low', ob.get('invalidation', 0))
                zh = ob.get('zone_high', 0)
                mid = (zl + zh) / 2 if zl and zh else zl
                signals_list.append({
                    'seq': len(signals_list)+1, 'type': f"OB_{ob['direction'].capitalize()}",
                    'idx': idx, 'date': d,
                    'price': round(mid, 4),
                    'upper': round(zh, 4),
                    'lower': round(zl, 4),
                    'direction': ob['direction'], 'strength': 0.75,
                    'confidence': 0.75, 'family': 'ob',
                    'created_by_event_index': ob.get('created_by_event_index'),
                    'created_by_event_date': ob.get('created_by_event_date'),
                    'created_by_event_type': ob.get('created_by_event_type'),
                    'created_by_pivot_label': ob.get('created_by_pivot_label'),
                    'created_by_pivot_price': ob.get('created_by_pivot_price'),
                    'bars_before_break': ob.get('bars_before_break'),
                    'anchor_method': ob.get('anchor_method'),
                    'wave_turn_idx': ob.get('wave_turn_idx'),
                    'wave_turn_date': ob.get('wave_turn_date'),
                    'wave_turn_label': ob.get('wave_turn_label'),
                    'wave_turn_price': ob.get('wave_turn_price'),
                    'wave_turn_distance': ob.get('wave_turn_distance'),
                    'displacement_ratio': ob.get('displacement_ratio'),
                    'body_ratio': ob.get('body_ratio'),
                    'pine_rule': ob.get('pine_rule', '')
                })
            # OTE
            for ot in (sig_data or {}).get('otes', []):
                idx = ot['index']
                if idx >= len(data): continue
                d = str(data[idx].get('t', data[idx].get('date', '')))[:16]
                zl = ot.get('zone_low', 0)
                zh = ot.get('zone_high', 0)
                mid = (zl + zh) / 2 if zl and zh else zl
                signals_list.append({
                    'seq': len(signals_list)+1, 'type': f"OTE_{ot['direction'].capitalize()}",
                    'idx': idx, 'date': d,
                    'price': round(mid, 4),
                    'upper': round(zh, 4),
                    'lower': round(zl, 4),
                    'direction': ot['direction'], 'strength': 0.65,
                    'confidence': 0.7, 'family': 'ote'
                })
            # BPRs
            for bp in (sig_data or {}).get('bprs', []):
                idx = bp['index']
                if idx >= len(data): continue
                d = str(data[idx].get('t', data[idx].get('date', '')))[:16]
                signals_list.append({
                    'seq': len(signals_list)+1, 'type': f"BPR_{bp['direction'].capitalize()}",
                    'idx': idx, 'date': d,
                    'price': round(bp.get('mid', 0), 4),
                    'upper': round(bp.get('zone_high', 0), 4),
                    'lower': round(bp.get('zone_low', 0), 4),
                    'direction': bp['direction'], 'strength': 0.5,
                    'confidence': 0.6, 'family': 'bpr'
                })
            # EQH/EQL liquidity pools (V32A)
            for eq in (sig_data or {}).get('eqh_eql', []):
                idx = eq['index']
                if idx >= len(data): continue
                d = str(data[idx].get('t', data[idx].get('date', '')))[:16]
                typ = 'EQL_Low' if eq.get('type') == 'EQL' else 'EQL_High'
                signals_list.append({
                    'seq': len(signals_list)+1, 'type': typ,
                    'idx': idx, 'date': d,
                    'price': round(eq.get('level', eq.get('price', 0)), 4),
                    'upper': round(eq.get('level', eq.get('price', 0)), 4),
                    'lower': round(eq.get('level', eq.get('price', 0)), 4),
                    'direction': eq.get('direction', 'bull'), 'strength': 0.6,
                    'confidence': eq.get('confidence', 0.7), 'family': 'eql'
                })
            # Liquidity voids (V32A)
            for lv in (sig_data or {}).get('liquidity_voids', []):
                idx = lv['index']
                if idx >= len(data): continue
                d = str(data[idx].get('t', data[idx].get('date', '')))[:16]
                signals_list.append({
                    'seq': len(signals_list)+1, 'type': f"LiquidityVoid_{lv.get('direction','bull').capitalize()}",
                    'idx': idx, 'date': d,
                    'price': round(lv.get('mid', 0), 4),
                    'upper': round(lv.get('zone_high', 0), 4),
                    'lower': round(lv.get('zone_low', 0), 4),
                    'direction': lv.get('direction','bull'), 'strength': 0.5,
                    'confidence': lv.get('confidence', 0.55), 'family': 'lv'
                })
            # Breaker blocks (V38)
            for br in (sig_data or {}).get('breakers', []):
                idx = br['index']
                if idx >= len(data): continue
                d = str(data[idx].get('t', data[idx].get('date', '')))[:16]
                signals_list.append({
                    'seq': len(signals_list)+1, 'type': f"BreakerBlock_{br.get('direction','bull').capitalize()}",
                    'idx': idx, 'date': d,
                    'price': round(br.get('mid', 0), 4),
                    'upper': round(br.get('zone_high', 0), 4),
                    'lower': round(br.get('zone_low', 0), 4),
                    'direction': br.get('direction','bull'), 'strength': 0.55,
                    'confidence': br.get('confidence', 0.60), 'family': 'brk'
                })
            # Rejection blocks (V38)
            for rb in (sig_data or {}).get('rejection_blocks', []):
                idx = rb['index']
                if idx >= len(data): continue
                d = str(data[idx].get('t', data[idx].get('date', '')))[:16]
                typ = 'Rejection_Support' if rb.get('direction') == 'bull' else 'Rejection_Resistance'
                signals_list.append({
                    'seq': len(signals_list)+1, 'type': typ,
                    'idx': idx, 'date': d,
                    'price': round(rb.get('mid', 0), 4),
                    'upper': round(rb.get('zone_high', 0), 4),
                    'lower': round(rb.get('zone_low', 0), 4),
                    'direction': rb.get('direction','bull'), 'strength': 0.55,
                    'confidence': rb.get('confidence', 0.60), 'family': 'rb'
                })
            # Sweeps — use proper subtype names (SSL/BSL)
            for sw in (sig_data or {}).get('sweeps', []):
                idx = sw['index']
                if idx >= len(data): continue
                d = str(data[idx].get('t', data[idx].get('date', '')))[:16]
                subtype = sw.get('subtype', 'SSL' if sw['direction'] == 'bull' else 'BSL')
                sig_type = f"Sweep_{subtype}"
                sw_price = sw.get('wick_low' if sw['direction']=='bull' else 'wick_high', sw.get('close', 0))
                signals_list.append({
                    'seq': len(signals_list)+1, 'type': sig_type,
                    'idx': idx, 'date': d,
                    'price': round(sw_price, 4), 'upper': round(sw_price, 4),
                    'lower': round(min(sw_price, sw.get('close', 0)), 4),
                    'direction': sw['direction'], 'strength': 0.7,
                    'confidence': sw.get('confidence', 0.7), 'family': 'sweep'
                })
            # Swings for display
            swings_list = []
            for h in (sig_data or {}).get('swings', {}).get('highs', []):
                swings_list.append({'bar': h['idx'], 'type': 'HIGH', 'price': h['price'], 'label': h.get('label', 'H'), 'confirm_bar': h.get('confirm_idx'), 'confirm_date': h.get('confirm_date'), 'rule': h.get('pine_rule', '')})
            for lo in (sig_data or {}).get('swings', {}).get('lows', []):
                swings_list.append({'bar': lo['idx'], 'type': 'LOW', 'price': lo['price'], 'label': lo.get('label', 'L'), 'confirm_bar': lo.get('confirm_idx'), 'confirm_date': lo.get('confirm_date'), 'rule': lo.get('pine_rule', '')})
            swings_list.sort(key=lambda s: s['bar'])
            # Sort all signals by index
            signals_list.sort(key=lambda s: s['idx'])
            for s in signals_list:
                s.update(_apply_smc_field_contract({
                    **s,
                    'signal_type': s.get('type'),
                    'zone_type': s.get('zone_type') or s.get('type'),
                    'signal_date': s.get('signal_date') or s.get('date'),
                    'entry_price': s.get('price'),
                    'price': s.get('price'),
                }, default_engine=ver))
                s['signal_date'] = s.get('signal_date') or s.get('date')
            wave_swings_list = list(swings_list)

            # Filter by sequence if requested

            if ver in ('V44', ACTIVE_VERSION, 'V47_2', 'V48_1', 'V49', 'V50', 'V51'):
                ver_map = {'V44': get_trades_cached(lite=True), ACTIVE_VERSION: get_trades_cached(lite=True), 'V47_2': get_version_trades('V47_2', lite=True), 'V48_1': get_version_trades('V48_1', lite=True), 'V49': get_version_trades('V49', lite=True), 'V50': get_version_trades('V50', lite=True), 'V51': get_version_trades('V51', lite=True), 'V52': get_version_trades('V52', lite=True), 'V53': get_version_trades('V53', lite=True), 'V54': get_version_trades('V54', lite=True)}
                _ver_paths = {}
            elif str(ver).upper() in ('V20C',) or (_production_registry().get('production_strategy') == 'COMBO_SMC_EVENT' and str(ver).upper() == 'V88'):
                # FIX(2026-08-20): v20c/COMBO — trades come from v20c CSV; skip legacy ver_map load (5s+).
                ver_map = {}
                _ver_paths = {}
            else:
                ver_map = {
                    'V41': get_trades_cached(lite=True),
                    'V40': get_trades_cached(lite=True),
                    'V39': get_trades_cached(lite=True),
                    'V38': get_trades_cached(lite=True),
                    'V37': get_trades_cached(lite=True),
                    'V36': get_trades_cached(lite=True),
                    'V34D': get_trades_cached(lite=True),
                    'V33': get_trades_cached(lite=True),
                    'V32D': get_trades_cached(lite=True),
                    'V32C': get_trades_cached(lite=True),
                    'V32B': get_trades_cached(lite=True),
                    'V32A': get_trades_cached(lite=True),  # signal-core view uses active trades for trade overlays
                    'V31': get_trades_cached(lite=True),  # default
                    'V30': None,
                    'V29': None,
                    'V28': None, 'V27': None, 'V25': None, 'V24': None, 'V23': None, 'V22': None, 'V21': None,
                    'V19': None, 'V18': None, 'V17': None, 'V16.2': None, 'V16.1': None,
                    'V16': None, 'V15': None, 'V13': None, 'V12': None,
                }
                _ver_paths = {
                'V41': '/root/.hermes/smc_opt_v41/v41_trades.json',
                'V40': '/root/.hermes/smc_opt_v40/v40_trades.json',
                'V39': '/root/.hermes/smc_opt_v39/v39_trades.json',
                'V38': '/root/.hermes/smc_opt_v38/v38_trades.json',
                'V37': '/root/.hermes/smc_opt_v37/v37_trades.json',
                'V36': '/root/.hermes/smc_opt_v36/v36_trades.json',
                'V34D': '/root/.hermes/smc_opt_v34d_final/v34_trades.json',
                'V33': '/root/.hermes/smc_opt_v33/v33_trades.json',
                'V32D': '/root/.hermes/smc_opt_v32d/v32d_trades.json',
                'V32C': '/root/.hermes/smc_opt_v32c/v32c_trades.json',
                'V32B': '/root/.hermes/smc_opt_v32b/v32b_trades.json',
                'V31': '/root/.hermes/smc_opt_v31/v31_trades.json',
                'V30': '/root/.hermes/smc_opt_v30/v30_trades.json',
                'V29': '/root/.hermes/smc_opt_v29/v29_trades.json',
                'V28': '/root/.hermes/smc_opt_v28/v28_trades.json',
                'V27': '/root/.hermes/smc_opt_v27/v27_trades.json',
                'V25': '/root/.hermes/smc_opt_v25/v25_trades.json',
                'V24': '/root/.hermes/smc_opt_v24/v24_trades.json',
                'V19': '/root/.hermes/smc_opt_v19/v19_i1.json',
                'V18': '/root/.hermes/smc_opt_v18/v18_autopsy.json',
                'V17': '/root/.hermes/smc_opt_v17/v17_complete.json',
                'V16': '/root/.hermes/smc_opt_v16/v16_complete.json',
            }
            v45_aliases = {
                'V45.5': '/root/.hermes/smc_opt_v45_5/v45_5_trades.json',
                'V45_5': '/root/.hermes/smc_opt_v45_5/v45_5_trades.json',
                'v45_5': '/root/.hermes/smc_opt_v45_5/v45_5_trades.json',
                'V45.4': '/root/.hermes/smc_opt_v45_4/v45_4_trades.json',
                'V45_4': '/root/.hermes/smc_opt_v45_4/v45_4_trades.json',
                'v45_4': '/root/.hermes/smc_opt_v45_4/v45_4_trades.json',
                'V45.3': '/root/.hermes/smc_opt_v45_3/v45_3_trades.json',
                'V45_3': '/root/.hermes/smc_opt_v45_3/v45_3_trades.json',
                'v45_3': '/root/.hermes/smc_opt_v45_3/v45_3_trades.json',
                'V45.2': '/root/.hermes/smc_opt_v45_2/v45_2_trades.json',
                'V45_2': '/root/.hermes/smc_opt_v45_2/v45_2_trades.json',
                'v45_2': '/root/.hermes/smc_opt_v45_2/v45_2_trades.json',
                'V45.1': '/root/.hermes/smc_opt_v45_1/v45_1_trades.json',
                'V45_1': '/root/.hermes/smc_opt_v45_1/v45_1_trades.json',
                'v45_1': '/root/.hermes/smc_opt_v45_1/v45_1_trades.json',
                'V45': '/root/.hermes/smc_opt_v45_native/v45_trades.json',
            }
            if ver in v45_aliases:
                ver_map[ver] = _vdata(v45_aliases[ver])
            elif ver == 'V47_2':
                ver_map[ver] = get_version_trades('V47_2', lite=True)
            elif ver == 'V48_1':
                ver_map[ver] = get_version_trades('V48_1', lite=True)
            elif ver == 'V49':
                ver_map[ver] = get_version_trades('V49', lite=True)
            elif ver == 'V50':
                ver_map[ver] = get_version_trades('V50', lite=True)
            elif ver == 'V51':
                ver_map[ver] = get_version_trades('V51', lite=True)
            elif ver == 'V52':
                ver_map[ver] = get_version_trades('V52', lite=True)
            elif ver == 'V53':
                ver_map[ver] = get_version_trades('V53', lite=True)
            elif ver == 'V54':
                ver_map[ver] = get_version_trades('V54', lite=True)
            elif ver == 'V55':
                ver_map[ver] = get_version_trades('V55', lite=True)
            elif ver == 'V56':
                ver_map[ver] = get_version_trades('V56', lite=True)
            elif ver == 'V57':
                ver_map[ver] = get_version_trades('V57', lite=True)
            elif ver == 'V58':
                ver_map[ver] = get_version_trades('V58', lite=True)
            elif ver == 'V59':
                ver_map[ver] = get_version_trades('V59', lite=True)
            elif ver == 'V60':
                ver_map[ver] = get_version_trades('V60', lite=True)
            elif ver == 'V61':
                ver_map[ver] = get_version_trades('V61', lite=True)
            elif ver == 'V62':
                ver_map[ver] = get_version_trades('V62', lite=True)
            elif ver == 'V63':
                ver_map[ver] = get_version_trades('V63', lite=True)
            elif ver == 'V64':
                ver_map[ver] = get_version_trades('V64', lite=True)
            elif ver == 'V65':
                ver_map[ver] = get_version_trades('V65', lite=True)
            elif ver == 'V66':
                ver_map[ver] = get_version_trades('V66', lite=True)
            elif ver not in (ACTIVE_VERSION,):  # active version already cached
                ver_map[ver] = _vdata(_ver_paths.get(ver, '')) if ver in _ver_paths else ver_map.get(ACTIVE_VERSION, [])

            # 🔴 Signal highlighting: current active zone (from picks) + historical trades
            highlight = []
            seq_raw = qs.get('seq', [''])[0]
            
            # FIRST: highlight current active zone from picks (most recent unbreached zone)
            # FIX(2026-08-20): production COMBO — v20c markers from sim_markers; skip V88 picks load.
            if _production_registry().get('production_strategy') == 'COMBO_SMC_EVENT' and str(ver).upper() == 'V88':
                picks = []
                stock_pick = None
            else:
                picks = get_version_picks(ver) if ver != ACTIVE_VERSION else reload_picks()
                stock_pick = next((p for p in picks if p.get('symbol', '') == symbol and p.get('pick_scope') == 'ACTIVE_CANDIDATE'), None)
                if not stock_pick:
                    stock_pick = next((p for p in picks if p.get('symbol', '') == symbol), None)
            if not stock_pick and load_positions:
                for pos in load_positions():
                    raw = pos.get('raw_pick') or {}
                    if pos.get('symbol') == symbol or raw.get('symbol') == symbol:
                        stock_pick = dict(raw)
                        stock_pick.setdefault('symbol', pos.get('symbol'))
                        stock_pick.setdefault('pick_date', pos.get('pick_date'))
                        break
            if stock_pick:
                generic_idx_keys = [
                    ('sweep_idx', '1', 'LIQ'),
                    ('event_idx', '2', str(stock_pick.get('source_event','STRUCT'))),
                    ('source_event_idx', '2', str(stock_pick.get('source_event','STRUCT'))),
                    ('zone_idx', '3', f"Z:{stock_pick.get('zone_type','OB')}"),
                    ('touch_idx', '4', 'TOUCH'),
                    ('reclaim_idx', '5', 'RECLAIM'),
                    ('conf_index', '6', str(stock_pick.get('conf_type') or stock_pick.get('entry_mode') or 'CONF')),
                    ('entry_idx', '7', 'ENTRY'),
                ]
                if any(int(stock_pick.get(k, -1) or -1) >= 0 for k, _, _ in generic_idx_keys):
                    seen_chain_bars = set()
                    for key, num, label in generic_idx_keys:
                        bi = int(stock_pick.get(key, -1) or -1)
                        if 0 <= bi < len(klines) and bi not in seen_chain_bars:
                            highlight.append({'bar': bi, 'num': int(num), 'type': label.replace('TWO_BAR_REJECTION_HOLD','2BAR')})
                            seen_chain_bars.add(bi)
                    seq = stock_pick.get('ctx_seq', stock_pick.get('detail', '')) or f"{stock_pick.get('source_event','')}→{stock_pick.get('zone_type','')}→{stock_pick.get('conf_type','')}"
                # V30/V31 strict sequence picks carry exact chain indices.
                # Render the actual auditable chain on K-line: Sweep → CHOCH/MSS → Zone → Confirm → Entry.
                # V32A is a raw signal-correctness view; use active V31 trade/pick overlays if present.
                elif stock_pick.get('source') == 'daily_scan_after_kline_refresh' and int(stock_pick.get('zone_bar', -1) or -1) >= 0:
                    chain = [
                        ('zone_bar', '1', f"Z:{stock_pick.get('zone_type','OB')}"),
                        ('entry_idx', '2', str(stock_pick.get('conf_type','ENTRY')).replace('PINBAR_ENTRY','PINBAR')),
                    ]
                    seen_chain_bars = set()
                    for key, num, label in chain:
                        bi = int(stock_pick.get(key, -1) or -1)
                        if 0 <= bi < len(klines) and bi not in seen_chain_bars:
                            highlight.append({'bar': bi, 'num': int(num), 'type': label})
                            seen_chain_bars.add(bi)
                    seq = stock_pick.get('ctx_seq', stock_pick.get('detail', '')) or f"{stock_pick.get('zone_type','OB')}→{stock_pick.get('conf_type','ENTRY')}"
                elif ver in ('V46_1', 'V47_2', 'V48_1', 'V49', 'V50', 'V51', 'V52', 'V53', 'V54', 'V55', 'V56', 'V57', 'V58', 'V59', 'V60', 'V61', 'V62', 'V63', 'V64', 'V65', 'V66') and int(stock_pick.get('zone_idx', -1) or -1) >= 0:
                    chain = [
                        ('source_event_idx', '1', str(stock_pick.get('source_event','STRUCT'))),
                        ('zone_idx', '2', f"Z:{stock_pick.get('zone_type','OB')}"),
                        ('retrace_index', '3', 'RETEST'),
                        ('conf_index', '4', str(stock_pick.get('conf_type','CONF')).replace('TWO_BAR_REJECTION_HOLD','2BAR')),
                    ]
                    seen_chain_bars = set()
                    for key, num, label in chain:
                        bi = int(stock_pick.get(key, -1) or -1)
                        if 0 <= bi < len(klines) and bi not in seen_chain_bars:
                            highlight.append({'bar': bi, 'num': int(num), 'type': label})
                            seen_chain_bars.add(bi)
                    seq = stock_pick.get('ctx_seq', stock_pick.get('detail', '')) or f"{stock_pick.get('zone_type','')}→{stock_pick.get('source_event','')}→{stock_pick.get('conf_type','')}"
                elif ver in ('V32A','V32B','V32C','V32D','V33'):
                    ver_map[ver] = get_trades_cached(lite=True)
                    seq = stock_pick.get('ctx_seq', stock_pick.get('detail', ''))
                elif ver in ('V30','V31') and int(stock_pick.get('sweep_idx', -1) or -1) >= 0:
                    chain = [
                        ('sweep_idx', '1', f"LIQ:{stock_pick.get('sweep_type','SSL')}"),
                        ('source_event_idx', '2', str(stock_pick.get('source_event','MSS'))),
                        ('zone_idx', '3', f"Z:{stock_pick.get('zone_type','OB')}"),
                        ('conf_index', '4', str(stock_pick.get('conf_type','CONF')).replace('BULLISH_REJECTION','REJ')),
                        ('entry_index', '5', 'ENTRY'),
                    ]
                    seen_chain_bars = set()
                    for key, num, label in chain:
                        bi = int(stock_pick.get(key, -1) or -1)
                        if 0 <= bi < len(klines) and bi not in seen_chain_bars:
                            highlight.append({'bar': bi, 'num': int(num), 'type': label})
                            seen_chain_bars.add(bi)
                    seq = stock_pick.get('ctx_seq', stock_pick.get('detail', ''))
                # V27/V28/V29/V30/V31/V31 picks have signal_date; older picks have zone_bar
                elif ver in ('V27','V28','V29','V30','V31') and stock_pick.get('signal_date'):
                    sig_date = str(stock_pick.get('signal_date', ''))
                    seq = stock_pick.get('ctx_seq', stock_pick.get('detail', ''))
                    # Map date to bar index
                    for i, k in enumerate(klines):
                        if k['date'][:8] == sig_date[:8]:
                            highlight.append({
                                'bar': i, 'num': 1,
                                'type': f"Z:{stock_pick.get('zone_type','')}+{stock_pick.get('source_event','')}"
                            })
                            break
                else:
                    # Older pick format with zone_bar
                    stock_trade = next((t for t in (ver_map.get('V19', []) or [])
                                        if t.get('symbol', '') == symbol), None)
                    zb = (stock_pick.get('zone_bar') or
                          (stock_trade.get('zone_bar') if stock_trade else None) or -1)
                    zb = int(zb) if zb is not None else -1
                    seq = ''
                    if zb >= 0 and zb < len(klines):
                        seq = stock_pick.get('seq', stock_pick.get('detail', ''))
                        highlight.append({
                            'bar': zb, 'num': 1, 'type': f'Z:{seq}'
                        })
                # 2) Also find recent signals near END of chart (last 50 bars)
                #    that match the pick's sequence pattern — showing why it's still active
                last_n = len(klines)
                seq_parts = set(seq.replace('→','-').split('-')) if seq else set()
                bar_map = {}
                for s in signals_list:
                    bar_map.setdefault(s['idx'], []).append(s['type'])
                short_map = {'OB_Bull':'OB','OB_Bear':'OB','Sweep_SSL':'LIQ','Sweep_BSL':'LIQ',
                             'CHOCH_Bull':'CH','CHOCH_Bear':'CH','FVG_Bull':'FVG','FVG_Bear':'FVG',
                             'BreakerBlock_Bull':'BRK','MSS_Bull':'MSS','Pinbar_Bull':'PB',
                        'IFVG_Bull':'IF','OTE_Bull':'OT','BPR_Bull':'BPR',
                             'EQL_High':'EQH','EQL_Low':'EQL','LiquidityVoid_Bull':'LV','LiquidityVoid_Bear':'LV'}
                sig_seen = set()
                n = max([int(h.get('num', 0) or 0) for h in highlight] or [1]) + 1
                for bi in range(max(0, last_n - 50), last_n):
                    if bi not in bar_map:
                        continue
                    for st in bar_map[bi]:
                        if st in sig_seen:
                            continue
                        short = short_map.get(st, '')
                        if not short:
                            continue
                        sig_seen.add(st)
                        highlight.append({
                            'bar': bi, 'num': n, 'type': short
                        })
                        n += 1
                        if n > 8:
                            break
                    if n > 8:
                        break
            else:
                # FALLBACK: highlight actual trade signal bars from backtest
                stock_trades = [t for t in (ver_map.get(ver, ver_map.get('V19', [])) or []) if t.get('symbol', '') == symbol]
                if stock_trades:
                    bar_idx = {}
                    for i, k in enumerate(klines):
                        bar_idx[k['date'][:10]] = i
                    seen_bars = set()
                    for ti, t in enumerate(stock_trades[:20]):
                        sig_date = (str(t.get('signal_date', '') or t.get('entry_date', '')))[:10]
                        if not sig_date or sig_date not in bar_idx:
                            continue
                        sig_type = t.get('signal_type', '')
                        if not sig_type:
                            ctx = t.get('ctx_seq', '')
                            sig_type = ctx.split('→')[0].strip() if ctx else 'OB'
                        bi = bar_idx[sig_date]
                        if bi in seen_bars:
                            continue
                        seen_bars.add(bi)
                        sl = {'OB_Bull':'OB','OB_Bear':'OB','OB':'OB','Sweep_SSL':'LIQ',
                              'BREAK':'BRK'}.get(sig_type, sig_type[:3])
                        highlight.append({
                            'bar': bi, 'num': ti + 1, 'type': f'T{ti+1}:{sl}'
                        })
            # End highlight
            # Swings already built from V27 signals above
            for sw in swings_list:
                if 'bar' in sw:
                    sw['bar'] = int(sw['bar'])
                    sw['price'] = round(float(sw['price']), 2)

            # Trades for this symbol — filter from ver_map
            # FIX(2026-08-20): inject v20c backtest trades for EVERY version view
            # (buy/sell points, signal, trigger, sub-signals) + merge version-native trades.
            all_trades = ver_map.get(ver) or ver_map.get(ACTIVE_VERSION) or []
            trades = [dict(t) for t in all_trades if t.get('symbol', '') == symbol]
            _v20c_trades = _load_v20c_trades_for(symbol, klines, chart_date_idx)
            if _v20c_trades:
                trades = _v20c_trades + trades
            # Overlay the active watchlist/candidate row as an open BUY marker. V88 active picks
            # include V90/V91 scanner rows that are not historical backtest trades; without this
            # the K-line chart shows no buy point, SL/TP, or sequence for current candidates.
            if stock_pick:
                sp = _apply_smc_field_contract(dict(stock_pick), default_engine=ver)
                sp_entry_date = sp.get('entry_date') or sp.get('join_date') or sp.get('pick_date') or sp.get('select_date') or sp.get('signal_date')
                sp_entry_price = float(sp.get('entry_price') or sp.get('price') or sp.get('cost_line') or sp.get('smart_money_cost') or 0)
                already_represented = any(_date_key(t.get('entry_date')) == _date_key(sp_entry_date) and abs(float(t.get('entry_price') or 0) - sp_entry_price) < 0.005 for t in trades)
                if sp_entry_date and sp_entry_price > 0 and not already_represented:
                    sp['entry_date'] = sp_entry_date
                    sp['exit_date'] = ''
                    sp['entry_price'] = sp_entry_price
                    sp['price'] = sp_entry_price
                    sp['exit_price'] = 0
                    sp['pnl_pct'] = 0
                    sp['rr'] = sp.get('rr') or 0
                    sp['conf_type'] = sp.get('conf_type') or sp.get('entry_mode') or 'ACTIVE_PICK'
                    sp['signal_type'] = sp.get('signal_type') or sp.get('zone_type') or 'ACTIVE_ZONE'
                    sp['entry_detail'] = 'kline_active_pick_overlay'
                    sp['exit_reason'] = sp.get('state') or sp.get('setup_status') or 'ACTIVE_CANDIDATE'
                    sp['hold_bars'] = 0
                    sp['combo'] = 'ACTIVE'
                    trades.append(sp)
            # Overlay durable monitor positions as live BUY markers. Backtest trades may end before
            # current holdings, so K-line must still show actual simulated BUY + SL/TP.
            if load_positions:
                for pos in load_positions():
                    if pos.get('symbol') != symbol or pos.get('status') not in ('OPEN', 'NEXT_DAY_PENDING'):
                        continue
                    raw = pos.get('raw_pick') or {}
                    buy_date = monitor_date_key(pos.get('created_at')) if monitor_date_key else _date_key(pos.get('created_at'))
                    if pos.get('status') == 'NEXT_DAY_PENDING':
                        buy_date = _date_key(pos.get('pick_date') or raw.get('pick_date') or raw.get('entry_date'))
                    ep = float(pos.get('entry_price') or raw.get('entry_price') or raw.get('price') or 0)
                    slp = float(pos.get('sl_price') or raw.get('sl') or 0)
                    tpp = float(pos.get('tp1_price') or raw.get('tp1') or 0)
                    # Carry zone/cost/volatility/dates from monitor position
                    raw_zl = float(pos.get('zone_low') or pos.get('raw_zone_low') or raw.get('zone_low') or raw.get('dz_low') or 0)
                    raw_zh = float(pos.get('zone_high') or pos.get('raw_zone_high') or raw.get('zone_high') or raw.get('dz_high') or 0)
                    raw_cost = float(pos.get('cost_line') or pos.get('smart_money_cost') or raw.get('cost_line') or raw.get('smart_money_cost') or ((raw_zl + raw_zh) / 2 if raw_zl and raw_zh else ep))
                    raw_vol = float(pos.get('volatility_pct') or pos.get('risk_pct') or raw.get('volatility_pct') or raw.get('risk_pct') or 0)
                    raw_pick_date = raw.get('pick_date') or pos.get('pick_date') or raw.get('select_date') or raw.get('signal_date') or buy_date
                    raw_select_date = raw.get('select_date') or raw_pick_date
                    raw_join_date = pos.get('joined_at') or pos.get('created_at') or buy_date
                    trades.append({
                        'symbol': symbol,
                        'entry_date': buy_date,
                        'exit_date': '',
                        'entry_price': ep,
                        'exit_price': 0,
                        'sl_price': slp,
                        'sl_pct': float(pos.get('risk_pct') or raw.get('risk_pct') or ((ep - slp) / ep * 100 if ep and slp else 0)),
                        'tp1': tpp,
                        'tp_pct': ((tpp / ep - 1) * 100 if ep and tpp else 0),
                        'pnl_pct': 0,
                        'rr': 0,
                        'conf_type': pos.get('conf_type') or raw.get('conf_type') or 'MONITOR_BUY',
                        'zone_type': pos.get('zone_type') or raw.get('zone_type') or raw.get('signal_type') or '',
                        'signal_type': pos.get('zone_type') or raw.get('zone_type') or raw.get('signal_type') or '',
                        'signal_date': raw.get('signal_date') or raw.get('pick_date') or pos.get('pick_date'),
                        'signal_price': raw.get('signal_price') or raw.get('entry_price') or ep,
                        'zone_low': raw_zl,
                        'zone_high': raw_zh,
                        'cost_line': raw_cost,
                        'smart_money_cost': raw_cost,
                        'volatility_pct': raw_vol,
                        'pick_date': raw_pick_date,
                        'select_date': raw_select_date,
                        'join_date': raw_join_date,
                        'entry_detail': 'durable_monitor_position',
                        'exit_reason': pos.get('status'),
                        'hold_bars': 0,
                        'combo': 'BUY' if pos.get('status') == 'OPEN' else 'PENDING',
                        'market_state': raw.get('market_state') or raw.get('regime') or '',
                        'quality_score': raw.get('score') or raw.get('quality_score') or 0,
                        'engine': pos.get('engine') or raw.get('engine') or ACTIVE_VERSION,
                    })

            # Map trades to chart indices + build combo labels
            date_map = {}
            date_keys_sorted = []
            for i, k in enumerate(klines):
                d_raw = str(k.get('date', k.get('t', '')))[:10]
                # Normalize: strip hyphens for matching with trade dates
                d_norm = d_raw.replace('-', '')
                date_map[d_raw] = i
                if d_norm != d_raw:
                    date_map[d_norm] = i
                if len(d_norm) == 8 and d_norm.isdigit():
                    date_keys_sorted.append((d_norm, i))

            def _chart_idx_for_date(v):
                d = _date_key(v)
                if not d:
                    return -1
                if d in date_map:
                    return date_map[d]
                # Weekly bars use week-end dates; map a daily buy date to the first weekly bar >= buy date,
                # otherwise the last available bar before it.
                for dk, ii in date_keys_sorted:
                    if dk >= d:
                        return ii
                return date_keys_sorted[-1][1] if date_keys_sorted else -1

            trade_list = []
            for ti, t in enumerate(trades):
                t = _apply_smc_field_contract(t, default_engine=ver)
                ed = str(t.get('entry_date', ''))[:10]
                ci = _chart_idx_for_date(ed)
                if ci < 0:
                    ed_norm = ed.replace('-', '')
                    ci = date_map.get(ed_norm, -1)
                # Map V28/V27 fields
                entry_price = float(t.get('entry_price', 0))
                exit_price = float(t.get('exit_price', 0))
                sl_price = float(t.get('sl_price', t.get('sl', 0)))
                sl_pct = float(t.get('sl_pct', t.get('risk_pct', 0)))
                tp_abs = float(t.get('tp_price') or t.get('tp') or t.get('tp1') or t.get('target_price') or 0)
                # V66 structural exits do not always persist a planned TP field. For winning
                # historical trades, use the realized exit price as the auditable TP/target line
                # so the K-line shows both the BUY point and the profit-taking level.
                if not tp_abs and float(t.get('pnl_pct', 0) or 0) > 0 and float(t.get('exit_price', 0) or 0) > entry_price:
                    tp_abs = float(t.get('exit_price') or 0)
                tp_pct = float(t.get('tp_pct', ((tp_abs / entry_price - 1) * 100 if entry_price and tp_abs else 0)))
                pnl = float(t.get('pnl_pct', 0))
                rr = float(t.get('rr', 0))
                conf_type = t.get('conf_type', '')
                zone_type = t.get('zone_type', t.get('signal_type', ''))
                is_monitor_trade = t.get('entry_detail') == 'durable_monitor_position'
                combo = t.get('combo') if is_monitor_trade else t.get('combo') or f"BT{ti+1}"
                if len(combo) > 60: combo = combo[:57]+'...'
                signal_date = t.get('signal_date', '')
                signal_price = float(t.get('signal_price', ((float(t.get('zone_low', 0) or 0) + float(t.get('zone_high', 0) or 0)) / 2 if t.get('zone_low') and t.get('zone_high') else t.get('entry_price', 0))))
                retrace_pct = float(t.get('retrace_pct', t.get('risk_pct', 0)))
                entry_detail = t.get('entry_detail', '')
                exit_reason = t.get('exit_reason', t.get('exit_type', ''))
                exit_detail = t.get('exit_detail', '')

                # Build tooltip
                tt = f"Trade #{ti+1}: {conf_type or combo}<br/>" \
                     f"Entry: {ed} @ {entry_price:.2f}<br/>" \
                     f"Zone: {zone_type} sig={signal_price:.2f}<br/>" \
                     f"Conf: {conf_type}<br/>" \
                     f"Exit: {t.get('exit_date','')} @ {exit_price:.2f} ({exit_reason})<br/>" \
                     f"PnL: {pnl:+.2f}% | RR: {rr:.1f}x | Hold: {t.get('hold_bars',0)}b<br/>" \
                     f"SL: {sl_price:.2f} ({sl_pct:.2f}%) | TP: {tp_pct:.1f}%<br/>" \
                     f"State: {t.get('market_state','?')} | Q: {t.get('quality_score','?')}"

                tp_price = tp_abs or (entry_price * (1 + tp_pct/100))

                trade_list.append({
                    'symbol': t.get('symbol',''),
                    'entry_date': ed,
                    'exit_date': t.get('exit_date', ''),
                    'signal_date': signal_date,
                    'signal_type': zone_type,
                    'signal_price': round(signal_price, 2),
                    'entry_price': round(entry_price, 2),
                    'exit_price': round(exit_price, 2),
                    'entry_type': conf_type,
                    'conf_type': conf_type,
                    'zone_type': zone_type,
                    'zone_low': t.get('zone_low', 0),
                    'zone_high': t.get('zone_high', 0),
                    'select_date': t.get('select_date') or t.get('pick_date') or '',
                    'pick_date': t.get('pick_date') or t.get('select_date') or '',
                    'join_date': t.get('join_date') or '',
                    'cost_line': t.get('cost_line') or t.get('smart_money_cost') or 0,
                    'smart_money_cost': t.get('smart_money_cost') or t.get('cost_line') or 0,
                    'volatility_pct': t.get('volatility_pct') or 0,
                    'semantic_layer': t.get('semantic_layer') or 'UNAUDITED',
                    'strict_audit_status': t.get('strict_audit_status') or 'UNAUDITED',
                    'signal_correctness_claim': t.get('signal_correctness_claim') or 'PENDING_REPLAY',
                    'semantic_issues': t.get('semantic_issues') or [],
                    'dna_preferred_behavior': t.get('dna_preferred_behavior') or '',
                    'symbol_dna_mode': t.get('symbol_dna_mode') or '',
                    'combo_contract_key': t.get('combo_contract_key') or '',
                    'combo_role': t.get('combo_role') or '',
                    'combo_mtf_permission': t.get('combo_mtf_permission') or '',
                    'mtf_permission': t.get('mtf_permission') or '',
                    'daily_structure_state': t.get('daily_structure_state') or '',
                    'production_eligible_v102': t.get('production_eligible_v102', False),
                    'v102_balanced_volume_gate': t.get('v102_balanced_volume_gate', False),
                    'entry_mode': t.get('entry_mode') or '',
                    'entry_zone_position': t.get('entry_zone_position'),
                    'retrace_pct': round(retrace_pct, 1),
                    'pnl_pct': pnl,
                    'won': t.get('won', t.get('pnl_pct', 0) > 0),
                    'rr': rr,
                    'hold_bars': t.get('hold_bars', 0),
                    'sl': sl_price,
                    'sl_pct': sl_pct,
                    'tp_pct': tp_pct,
                    'tp_price': round(tp_price, 2),
                    '_chart_idx': ci,
                    '_combo': combo,
                    '_exit_idx': _chart_idx_for_date(t.get('exit_date')) if t.get('exit_date') else ci+1,
                    '_tt': tt,
                    'entry_detail': entry_detail,
                    'exit_reason': exit_reason,
                    'exit_detail': exit_detail,
                    'market_state': t.get('market_state',''),
                    'weekly_bull': t.get('weekly_bull', False),
                    'quality_score': t.get('quality_score', 0),
                    'engine': t.get('engine', ''),
                    'definition_version': t.get('definition_version', ''),
                    'source_event': t.get('source_event', ''),
                    'source_event_idx': t.get('source_event_idx', t.get('signal_index', None)),
                    'sweep_idx': t.get('sweep_idx', None),
                    'zone_idx': t.get('zone_idx', None),
                    'sub_signals': t.get('sub_signals') or [],
                    'hold_bars': t.get('hold_bars', 0),
                })
            trade_list.sort(key=lambda x: x['_chart_idx'])

            # FIX(2026-08-19): 模拟持仓/挂单的 K 线信号标注（选股信号链 + 挂单/TP/SL）
            sim_markers = {'points': [], 'lines': [], 'conditions': ''}
            try:
                _sim_code = symbol.split('.')[0]
                _sim_led = json.loads(Path('/root/.hermes/smc_monitor/paper_ledger.json').read_text(encoding='utf-8'))
                _sim_rec = next((t for t in _sim_led if str(t.get('code', '')) == _sim_code), None)
                if _sim_rec:
                    _sig_d = str(_sim_rec.get('signal_date') or _sim_rec.get('disclose_date') or '').replace('-', '')
                    _fill_d = str(_sim_rec.get('filled_at') or '')[:10].replace('-', '') or None
                    _entry = _sim_rec.get('entry_price')
                    _tp = _sim_rec.get('tp_price')
                    _sl = _sim_rec.get('sl_price')
                    _st = _sim_rec.get('status', '')
                    _combo = str(_sim_rec.get('signal_combo', ''))
                    _c = {
                        'PENDING_ORDER': '#d29922', 'FILLED': '#3fb950',
                        'OPEN': '#58a6ff', 'CLOSED': '#8b949e',
                    }.get(_st, '#8b949e')
                    # signal-specific reason & TP/SL condition text
                    _reason = ''
                    _tp_cond = ''
                    _sl_cond = ''
                    if 'BUYBACK' in _combo or 'HOLDER' in _combo:
                        _reason = '内部人底部确认：增持/回购（ACCUM/DOWNTREND 吸筹阶段 + ADX≥20 趋势确认）'
                        _tp_cond = f'TP {_tp} = 60日结构前高（大资金拉升目标）' if _tp else 'TP = 结构前高'
                        _sl_cond = f'SL {_sl} = 事件前结构低点×0.99（大资金否定位）' if _sl else 'SL = 结构低点'
                    elif 'CONTINUATION' in _combo:
                        _reason = '大资金趋势维护：MARKUP 放量拉升阶段回踩结构支撑（VWAP≥5% 强趋势 + 低波动健康）'
                        _tp_cond = f'TP {_tp} = 入场×1.15（趋势延续目标）' if _tp else 'TP = 1.15x'
                        _sl_cond = f'SL {_sl} = 回踩支撑×0.99（趋势否定位）' if _sl else 'SL = 支撑'
                    else:
                        _reason = 'SMC 结构信号：SSL 扫损吸筹 + 三周期链确认'
                        _tp_cond = f'TP {_tp} = 结构目标' if _tp else 'TP = 结构目标'
                        _sl_cond = f'SL {_sl} = 扫损低点×0.99' if _sl else 'SL = 扫损低点'
                    # point 1: signal date (事件/信号发生 + 策略原因)
                    if _sig_d and _sig_d in chart_date_idx:
                        _sig_i = chart_date_idx[_sig_d]
                        sim_markers['points'].append({
                            'idx': _sig_i, 'date': _sig_d, 'price': klines[_sig_i]['c'],
                            'label': f"①信号 {_combo}", 'order': 1, 'color': '#58a6ff',
                            'tt': f"① 信号日 {_sig_d} | 组合: {_combo}<br>策略原因: {_reason}<br>触发: {_sim_rec.get('trigger','')}"
                        })
                    # point 2: entry/filled
                    if _fill_d and _fill_d in chart_date_idx:
                        _f_i = chart_date_idx[_fill_d]
                        sim_markers['points'].append({
                            'idx': _f_i, 'date': _fill_d, 'price': klines[_f_i]['c'],
                            'label': '②买入', 'order': 2, 'color': _c,
                            'tt': f"② 买入日 {_fill_d} | 买入价 {_sim_rec.get('filled_price','-')}<br>买入依据: {_reason}"
                        })
                    # point 3: exit (if closed)
                    if _sim_rec.get('status') == 'CLOSED' and _sim_rec.get('exit_reason'):
                        _exit_d = str(_sim_rec.get('filled_at') or '')[:10].replace('-', '')
                        if _exit_d and _exit_d in chart_date_idx:
                            _e_i = chart_date_idx[_exit_d]
                            sim_markers['points'].append({
                                'idx': _e_i, 'date': _exit_d, 'price': klines[_e_i]['c'],
                                'label': '③卖出', 'order': 3, 'color': '#f85149',
                                'tt': f"③ 卖出 | 原因: {_sim_rec.get('exit_reason')} | PnL: {_sim_rec.get('pnl_pct','')}%"
                            })
                    # sub-signals: each condition with its occurrence date (ordered markers)
                    _subs = _sim_rec.get('sub_signals') or []
                    for _si, _s in enumerate(_subs):
                        _sd = str(_s.get('date', '')).replace('-', '')
                        if not _sd or _sd not in chart_date_idx:
                            continue
                        _s_i = chart_date_idx[_sd]
                        _s_colors = ['#58a6ff', '#d29922', '#3fb950', '#bc8cff', '#f0883e']
                        sim_markers['points'].append({
                            'idx': _s_i, 'date': _sd, 'price': klines[_s_i]['c'],
                            'label': f"S{_si+1} {_s.get('name','')[:6]}", 'order': 10 + _si,
                            'color': _s_colors[_si % len(_s_colors)],
                            'tt': f"S{_si+1} {_s.get('name','')}<br>日期 {_s.get('date','')}<br>{_s.get('detail','')}"
                        })
                    # lines: entry / tiered TP (TP1-TP4) / tiered SL (SL1/SL2) — FIX(2026-08-22) multi-tier display
                    if _entry:
                        sim_markers['lines'].append({'price': _entry, 'label': f"入场/挂单 {_entry}", 'color': '#d29922', 'tt': '买入价（挂单成交/开盘买入）'})
                    _tp1 = _sim_rec.get('tp1')
                    _tp2 = _sim_rec.get('tp2')
                    _tp3 = _sim_rec.get('tp3')
                    _tp4 = _sim_rec.get('tp4') or _sim_rec.get('tp_price')
                    _sl1 = _sim_rec.get('sl1') or _sim_rec.get('sl_price')
                    _sl2 = _sim_rec.get('sl2')
                    if _tp1:
                        sim_markers['lines'].append({'price': _tp1, 'label': f"TP1 {_tp1}", 'color': '#3fb950', 'tt': 'TP1 = 最近 swing high（第一结构目标）'})
                    if _tp2:
                        sim_markers['lines'].append({'price': _tp2, 'label': f"TP2 {_tp2}", 'color': '#2ea043', 'tt': 'TP2 = FVG 上沿 / 次近 swing high'})
                    if _tp3:
                        sim_markers['lines'].append({'price': _tp3, 'label': f"TP3 {_tp3}", 'color': '#1f883d', 'tt': 'TP3 = 前高 / 流动性池 BSL'})
                    if _tp4 and _tp4 != _tp3:
                        sim_markers['lines'].append({'price': _tp4, 'label': f"TP4 {_tp4}", 'color': '#56d364', 'tt': 'TP4 = 60日结构前高（runner 远端流动性）'})
                    if _sl1:
                        sim_markers['lines'].append({'price': _sl1, 'label': f"SL1 {_sl1}", 'color': '#f85149', 'tt': 'SL1 = 最近 swing low×0.99（结构止损）'})
                    if _sl2:
                        sim_markers['lines'].append({'price': _sl2, 'label': f"SL2 {_sl2}", 'color': '#ff6b6b', 'tt': 'SL2 = FVG 下沿 / 深层 swing low（深止损）'})
                    _tp_conds = []
                    if _tp1: _tp_conds.append(f"TP1 {_tp1}=最近swing high")
                    if _tp2: _tp_conds.append(f"TP2 {_tp2}=FVG/次近swing")
                    if _tp3: _tp_conds.append(f"TP3 {_tp3}=流动性池")
                    if _tp4: _tp_conds.append(f"TP4 {_tp4}=60日前高(runner)")
                    _sl_conds = []
                    if _sl1: _sl_conds.append(f"SL1 {_sl1}=最近swing low")
                    if _sl2: _sl_conds.append(f"SL2 {_sl2}=FVG下沿/深层")
                    sim_markers['conditions'] = (f"状态:{_st} | 组合:{_combo} | 信号日:{_sim_rec.get('signal_date','')} | 选股日:{_sim_rec.get('pick_date','-')}"
                                                 f"<br>策略原因: {_reason}"
                                                 f"<br>锚点策略: {_sim_rec.get('anchor_note','-')}"
                                                 f"<br>分层TP: {' → '.join(_tp_conds) or '-'}"
                                                 f"<br>分层SL: {' / '.join(_sl_conds) or '-'}"
                                                 f"<br>子信号链: " + " → ".join(f"S{si+1}{_s.get('name','')}({_s.get('date','')})" for si, _s in enumerate(_subs))
                                                 + f"<br>顺序: ①信号({_sig_d}) → ②买入({_fill_d or '-'}) → ③分层TP/SL")
            except Exception:
                pass

            self._json({
                'klines': klines, 'count': len(klines),
                'signals_list': signals_list, 'signal_count': len(signals_list),
                'swings': swings_list, 'wave_swings': wave_swings_list, 'swing_count': len(swings_list),
                'trades': trade_list, 'trade_count': len(trade_list),
                'sim_markers': sim_markers,
                'highlight': highlight, 'seq': seq_raw,
                'symbol': symbol, 'tf': tf, 'version': ver, 'frontend_version': FRONTEND_VERSION
            })
            _KLINE_FULL_CACHE[_ckey] = {
                'klines': klines, 'count': len(klines),
                'signals_list': signals_list, 'signal_count': len(signals_list),
                'swings': swings_list, 'wave_swings': wave_swings_list, 'swing_count': len(swings_list),
                'trades': trade_list, 'trade_count': len(trade_list),
                'sim_markers': sim_markers,
                'highlight': highlight, 'seq': seq_raw,
                'symbol': symbol, 'tf': tf, 'version': ver, 'frontend_version': FRONTEND_VERSION
            }
        except Exception as e:
            import traceback
            self._json({'error': f'{e}', 'trace': traceback.format_exc()[:500]})

    def _api_reselect(self, qs=None):
        """触发手动重新选股/自定义回测 — 支持 start/end/update_kline 参数。"""
        import subprocess, datetime, os, json as _json
        qs = qs or {}
        registry = _production_registry()
        # EMPTY_BOOK blocks production writes, not a user-requested no-write research replay.
        # This must never fall back to historical V88/V175 materializers.
        if registry.get('state') != 'LIVE_READY' or registry.get('production_strategy') == 'V526_V517_DAILY_EFFORT_RESULT_ABSORPTION':
            t0 = __import__('time').time()
            replay_run = subprocess.run(['python3', '/root/.hermes/scripts/v25/v519_daily_effort_result_absorption_frozen_t1_replay.py'], capture_output=True, text=True, timeout=900, cwd='/root/.hermes/scripts/v25')
            if replay_run.returncode != 0:
                self._json({'ok': False, 'version': 'V517', 'error': 'V517 frozen T+1 replay execution failed', 'stderr': replay_run.stderr[-1200:], 'stdout': replay_run.stdout[-1200:]})
                return
            latest = _load_json_dict(Path('/root/.hermes/smc_audit/v519_daily_effort_result_absorption_frozen_t1_replay_latest.json'), {})
            overall = latest.get('overall') or {}
            gate_pass = latest.get('promotion_gate_pass') is True
            audit_pass = None
            if gate_pass:
                audit = subprocess.run(['python3', '/root/.hermes/scripts/v25/v520_daily_effort_result_absorption_independent_metric_audit.py'], capture_output=True, text=True, timeout=180, cwd='/root/.hermes/scripts/v25')
                if audit.returncode != 0:
                    self._json({'ok': False, 'version': 'V517', 'error': 'V517 independent metric audit execution failed', 'stderr': audit.stderr[-1200:], 'stdout': audit.stdout[-1200:]})
                    return
                audit_pass = _load_json_dict(Path('/root/.hermes/smc_audit/v520_daily_effort_result_absorption_independent_metric_audit_latest.json'), {}).get('audit_pass')
            self._json({
                'ok': True,
                'version': 'V517',
                'engine': 'V519_FROZEN_STRICT_T1_REPLAY',
                'state': registry.get('state') or 'NO_LIVE_PRODUCTION_STRATEGY',
                'trades': overall.get('n', 0),
                'stocks': latest.get('closed_trade_count', 0),
                'wr': overall.get('gross_wr_pct', 0),
                'avg_net_pnl_pct': overall.get('avg_net_pnl_pct', 0),
                'profit_factor': overall.get('profit_factor', 0),
                't1_violations': (latest.get('invariants') or {}).get('t1_violations'),
                'production_gate_pass': gate_pass,
                'independent_audit_pass': audit_pass,
                'replay_decision': latest.get('decision'),
                'yearly': latest.get('yearly', {}),
                'production_write': False,
                'watchlist_write': False,
                'time': round(__import__('time').time() - t0, 1),
                'note': 'V517 no-write frozen replay complete. Production remains EMPTY_BOOK when promotion_gate_pass is false.'
            })
            return
        try:
            global _CACHE_MTIME, _TRADES_CACHE, _TRADES_LITE_CACHE, _PICKS_CACHE, _SUMMARY_CACHE, _SUMMARY_MTIME
            t0 = __import__('time').time()
            today = dtmod.datetime.now().strftime('%Y%m%d')
            # V32+ active engine rerun. Older V31-only guard caused manual rerun failure after ACTIVE_VERSION moved forward.
            engine_map = {
                'V185': ('/root/.hermes/scripts/v25/v185_daily_rematerialize.py', '/root/.hermes/smc_opt_v185_combined_production_candidate', 'v185', 'V185_COMBINED_V175_PLUS_TRUE_TAKEOVER_CHILD'),
                'V175': ('/root/.hermes/scripts/v25/v175_semantic_split_materialize.py', '/root/.hermes/smc_opt_v175_semantic_split', 'v175', 'V175_DEMAND_OB_TRUE_TAKEOVER_SEMANTIC_SPLIT'),
                'V88': ('/root/.hermes/scripts/v25/v88_apply_production_contract.py', '/root/.hermes/smc_opt_v88_production_contract', 'v88', 'V88_PRODUCTION_CONTRACT'),
                'V66': ('/root/.hermes/scripts/v25/v66_engine.py', '/root/.hermes/smc_opt_v66', 'v66', 'V66_RECENT_REENTRY_RISK_OVERLAY'),
                'V65': ('/root/.hermes/scripts/v25/v65_engine.py', '/root/.hermes/smc_opt_v65', 'v65', 'V65_LOSS_REVIEW_GATE'),
                'V64': ('/root/.hermes/scripts/v25/v64_engine.py', '/root/.hermes/smc_opt_v64', 'v64', 'V64_CONTINUATION_SPECIALIST_GATE'),
                'V63': ('/root/.hermes/scripts/v25/v63_engine.py', '/root/.hermes/smc_opt_v63', 'v63', 'V63_REENTRY_SPECIALIST_GATE'),
                'V62': ('/root/.hermes/scripts/v25/v62_engine.py', '/root/.hermes/smc_opt_v62', 'v62', 'V62_FALSE_BREAK_RETEST_GATE'),
                'V61': ('/root/.hermes/scripts/v25/v61_engine.py', '/root/.hermes/smc_opt_v61', 'v61', 'V61_EXIT_LAYER_REPAIR'),
                'V60': ('/root/.hermes/scripts/v25/v60_engine.py', '/root/.hermes/smc_opt_v60', 'v60', 'V60_FAMILY_QUALITY_GATES'),
                'V59': ('/root/.hermes/scripts/v25/v59_engine.py', '/root/.hermes/smc_opt_v59', 'v59', 'V59_FULL_MARKET_GENERATOR'),
                'V58': ('/root/.hermes/scripts/v25/v58_engine.py', '/root/.hermes/smc_opt_v58', 'v58', 'V58_CONTINUATION_SETUP'),
                'V57': ('/root/.hermes/scripts/v25/v57_engine.py', '/root/.hermes/smc_opt_v57', 'v57', 'V57_SELECTIVE_GRADED_STRUCTURE_EXIT'),
                'V56': ('/root/.hermes/scripts/v25/v56_engine.py', '/root/.hermes/smc_opt_v56', 'v56', 'V56_BREAKOUT_QUALITY_TIERS'),
                'V55': ('/root/.hermes/scripts/v25/v55_engine.py', '/root/.hermes/smc_opt_v55', 'v55', 'V55_PRETRADE_GATE_ADAPTIVE_TP'),
                'V54': ('/root/.hermes/scripts/v25/v54_engine.py', '/root/.hermes/smc_opt_v54', 'v54', 'V54_REENTRY_AWARE'),
                'V53': ('/root/.hermes/scripts/v25/v53_engine.py', '/root/.hermes/smc_opt_v53', 'v53', 'V53_SIGNAL_SNAPSHOT_TREND_LAYERED_RUNNER'),
                'V52': ('/root/.hermes/scripts/v25/v52_engine.py', '/root/.hermes/smc_opt_v52', 'v52', 'V52_SIGNAL_SNAPSHOT_4R_CONFIRM_RECLAIM_EXIT'),
                'V51': ('/root/.hermes/scripts/v25/v51_engine.py', '/root/.hermes/smc_opt_v51', 'v51', 'V51_SIGNAL_SNAPSHOT_4R_STRUCT_EXIT'),
                'V50': ('/root/.hermes/scripts/v25/v50_engine.py', '/root/.hermes/smc_opt_v50', 'v50', 'V50_SIGNAL_SNAPSHOT_STRUCT_EXIT'),
                'V49': ('/root/.hermes/scripts/v25/v49_exit_optimized.py', '/root/.hermes/smc_opt_v49_exit_optimized', 'v49', 'V49_EXIT_OPTIMIZED_PRODUCTION'),
                'V48_1': ('/root/.hermes/scripts/v25/v48_1_production.py', '/root/.hermes/smc_opt_v48_1_production', 'v48_1', 'V48_1_PRODUCTION'),
                'V47_2': ('/root/.hermes/scripts/v25/v47_2_high_quality.py', '/root/.hermes/smc_opt_v47_2_candidate', 'v47_2', 'V47_2_HIGH_QUALITY_PRODUCTION'),
                'V46_1': ('/root/.hermes/scripts/v25/v46_1_layered_3y.py', '/root/.hermes/smc_opt_v46_1_layered_3y', 'v46_1', 'V46_1_LAYERED_SMC2026_3Y'),
                'V41': ('/root/.hermes/scripts/v25/v41_final_engine.py', '/root/.hermes/smc_opt_v41', 'v41', 'V41_REPLAY_ENTRY_EXIT'),
                'V40': ('/root/.hermes/scripts/v25/v40_final_engine.py', '/root/.hermes/smc_opt_v40', 'v40', 'V40_REPLAY_EXIT'),
                'V39': ('/root/.hermes/scripts/v25/v39_final_engine.py', '/root/.hermes/smc_opt_v39', 'v39', 'V39_CHOCH_QUALITY'),
                'V38': ('/root/.hermes/scripts/v25/v38_final_engine.py', '/root/.hermes/smc_opt_v38', 'v38', 'V38_PINE_GAP_CLOSED'),
                'V37': ('/root/.hermes/scripts/v25/v37_engine.py', '/root/.hermes/smc_opt_v37', 'v37', 'V37_PAYOFF_REPAIRED'),
                'V36': ('/root/.hermes/scripts/v25/v36_engine.py', '/root/.hermes/smc_opt_v36', 'v36', 'V36_OVERLAP_FILTERED'),
                'V34D': ('/root/.hermes/scripts/v25/v34d_final.py', '/root/.hermes/smc_opt_v34d_final', 'v34', 'V34D_LUX_OB_QUALITY'),
                'V33': ('/root/.hermes/scripts/v25/v33_engine.py', '/root/.hermes/smc_opt_v33', 'v33', 'V33_MSS_RTO'),
                'V32D': ('/root/.hermes/scripts/v25/v32d_engine.py', '/root/.hermes/smc_opt_v32d', 'v32d', 'V32D_FILTERED_RTO'),
                'V32C': ('/root/.hermes/scripts/v25/v32c_engine.py', '/root/.hermes/smc_opt_v32c', 'v32c', 'V32C_LIMIT_RTO'),
                'V32B': ('/root/.hermes/scripts/v25/v32b_engine.py', '/root/.hermes/smc_opt_v32b', 'v32b', 'V32B_STRICT_ENTRY'),
                'V31': ('/root/.hermes/scripts/v25/v31_full_scan.py', '/root/.hermes/smc_opt_v31', 'v31', 'V31_ICT_ARCH'),
            }
            requested_version = (qs.get('ver') or qs.get('version') or [None])[0]
            run_version = str(requested_version or ('V185' if ACTIVE_VERSION == 'V88' and (V185_DIR / 'v185_report.json').exists() else 'V175' if ACTIVE_VERSION == 'V88' and (V175_DIR / 'v175_report.json').exists() else ACTIVE_VERSION)).upper()
            if run_version not in engine_map:
                self._json({'ok': False, 'error': f'当前版本暂不支持重跑，version={run_version}, ACTIVE_VERSION={ACTIVE_VERSION}'})
                return

            engine_script, out_dir_s, prefix, engine_name = engine_map[run_version]
            out_dir = Path(out_dir_s)
            hist_dir = out_dir / 'history'
            hist_dir.mkdir(parents=True, exist_ok=True)

            start = (qs.get('start', ['20260101'])[0] or '20260101').replace('-', '')[:8]
            end = (qs.get('end', [today])[0] or today).replace('-', '')[:8]
            update_kline = qs.get('update_kline', ['0'])[0] in ('1','true','yes','on')
            note_filter_only = False
            if run_version == 'V31':
                cmd = ['python3', engine_script, '--start', start, '--end', end]
                if update_kline:
                    cmd.append('--update-kline')
            elif run_version in ('V185', 'V175', 'V88', 'V86', 'V85', 'V46_1', 'V47_2', 'V48_1', 'V49', 'V50', 'V51', 'V52', 'V53', 'V54', 'V55', 'V56', 'V57', 'V58', 'V59', 'V60', 'V61', 'V62', 'V63', 'V64', 'V65', 'V66', 'V68', 'V72'):
                cmd = ['python3', engine_script]
                if run_version == 'V46_1' and qs.get('rebuild_base', ['0'])[0] in ('1','true','yes','on'):
                    cmd.append('--rebuild-base')
                note_filter_only = True
            else:
                cmd = ['python3', engine_script, '--start-date', start]
            # Release in-memory frontend caches before full-market subprocess scan to avoid parent+child memory OOM.
            _TRADES_CACHE = None
            _TRADES_LITE_CACHE = None
            _PICKS_CACHE = None
            _CACHE_MTIME = 0
            _SUMMARY_CACHE = None
            _SUMMARY_MTIME = 0
            import gc
            gc.collect()
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=900, cwd='/root/.hermes/scripts')
            if r.returncode != 0:
                self._json({'ok': False, 'error': f'{ACTIVE_VERSION}引擎失败', 'stderr': r.stderr[-1000:], 'stdout': r.stdout[-1000:]})
                return

            trades_path = out_dir / f'{prefix}_trades.json'
            paths = _active_version_paths(run_version) or {}
            picks_path = paths.get('watchlist') if run_version in ('V46_1', 'V47_2', 'V48_1', 'V49', 'V50', 'V51', 'V52', 'V53', 'V54', 'V55', 'V56', 'V57', 'V58', 'V59', 'V60', 'V61', 'V62', 'V63', 'V64', 'V65', 'V66') else out_dir / f'{prefix}_picks.json'
            metrics_path = out_dir / f'{prefix}_report.json' if run_version in ('V185', 'V175') else (paths.get('metrics') if run_version in ('V46_1', 'V47_2', 'V48_1', 'V49', 'V50', 'V51', 'V52', 'V53', 'V54', 'V55', 'V56', 'V57', 'V58', 'V59', 'V60', 'V61', 'V62', 'V63', 'V64', 'V65', 'V66') else out_dir / f'{prefix}_metrics.json')
            if not trades_path.exists() or not picks_path.exists():
                self._json({'ok': False, 'error': f'{ACTIVE_VERSION}引擎未生成trades/picks输出', 'stdout': r.stdout[-1000:]})
                return

            trades = _json.loads(trades_path.read_text())
            picks = _json.loads(picks_path.read_text())
            metrics = _json.loads(metrics_path.read_text()) if metrics_path.exists() else {}

            hist_file = hist_dir / f'{prefix}_watchlist_{today}.json' if ACTIVE_VERSION == 'V46_1' else hist_dir / f'{prefix}_picks_{today}.json'
            _json.dump(picks, open(hist_file, 'w'), ensure_ascii=False)

            # Force next request to reload active trade/pick caches from disk.
            _CACHE_MTIME = 0
            _SUMMARY_CACHE = None
            _SUMMARY_MTIME = 0
            elapsed = __import__('time').time() - t0
            n_all = len(trades)
            trades_in_window = _filter_trades_by_window(trades, start, end)
            n = len(trades_in_window); w = sum(1 for t in trades_in_window if is_winner(t))
            self._json({
                'ok': True, 'engine': engine_name, 'trades': n, 'stocks': len(picks),
                'active_candidates': sum(1 for p in picks if p.get('pick_scope') == 'ACTIVE_CANDIDATE' and p.get('is_active_pick')),
                'wr': round(w/n*100, 1) if n else 0, 'time': round(elapsed, 1),
                'date': today, 'history_file': str(hist_file),
                'version': run_version,
                'scan_date': metrics.get('scan_date') or metrics.get('generated_at'), 'cutoff_date': metrics.get('cutoff_date'),
                'window_start': start, 'window_end': end, 'all_trades': n_all,
                'note': 'Active production engines generate full active universe; start/end are applied by frontend/API window filter.' if note_filter_only else '',
                'update_kline': update_kline
            })
        except subprocess.TimeoutExpired:
            self._json({'ok': False, 'error': f'{ACTIVE_VERSION}引擎超时(900s)'})
        except Exception as e:
            self._json({'ok': False, 'error': str(e)})
    
    def _api_history(self):
        """列出所有历史选股记录"""
        import os, datetime
        hist_dir = Path('/root/.hermes/smc_opt_v31/history')
        files = []
        if hist_dir.exists():
            for f in sorted(hist_dir.glob('v31_picks_*.json'), reverse=True):
                date_str = f.stem.replace('v31_picks_', '')
                try:
                    dt = dtmod.datetime.strptime(date_str, '%Y%m%d')
                    label = f"{dt.strftime('%m-%d')} ({f.stat().st_size//1024}KB)"
                except:
                    label = date_str
                files.append({'date': date_str, 'label': label, 'size': f.stat().st_size})
        self._json({'files': files})
    
    def _api_history_load(self, qs):
        """加载指定日期的历史选股"""
        date = qs.get('date', [''])[0]
        if not date:
            self._json({'error': '需要date参数'}); return
        hist_file = Path(f'/root/.hermes/smc_opt_v31/history/v31_picks_{date}.json')
        if not hist_file.exists():
            self._json({'error': f'记录{date}不存在'}); return
        import json as _json
        picks = _json.loads(hist_file.read_text())
        # Update current picks and invalidate in-memory cache.
        global _CACHE_MTIME
        _json.dump(picks, open('/root/.hermes/smc_opt_v31/v31_picks.json', 'w'), ensure_ascii=False)
        _CACHE_MTIME = 0
        _SUMMARY_CACHE = None
        _SUMMARY_MTIME = 0
        self.send_response(302)
        self.send_header('Location', '/monitor')
        self.end_headers()

    def _api_diagnostics(self):
        """Return active-version diagnostics JSON."""
        diag_path = Path('/root/.hermes/smc_opt_v31/v31_diagnostics.json') if ACTIVE_VERSION == 'V31' else (Path('/root/.hermes/smc_opt_v30/v30_diagnostics.json') if ACTIVE_VERSION == 'V30' else (Path('/root/.hermes/smc_opt_v29/v29_diagnostics.json') if ACTIVE_VERSION == 'V29' else Path('/root/.hermes/smc_opt_v28/v28_diagnostics.json')))
        if diag_path.exists():
            try:
                data = json.loads(diag_path.read_text())
                self._json(data)
                return
            except: pass
        self._json({'error': 'Diagnostics not available. Run v31_full_scan.py first.'})

    def _api_summary(self):
        from collections import Counter
        from datetime import datetime
        qs = getattr(self, '_last_qs', {}) or {}
        req_ver = qs.get('ver', [ACTIVE_VERSION])[0]
        registry = _production_registry()
        if _v526_live_production() and not qs.get('ver'):
            strategy = registry.get('production_strategy')
            positions = [p for p in (load_positions() if load_positions else []) if str((p.get('raw_pick') or {}).get('engine') or '') == strategy]
            pending = _load_json_list(Path('/root/.hermes/smc_monitor/v526_pending_orders.json'), [])
            scanner = _load_json_dict(Path('/root/.hermes/smc_audit/v700_pure_smc_ssl_reclaim_current_scanner_latest.json'), {})
            self._json({
                'version': 'V526',
                'engine': 'V517_DAILY_EFFORT_RESULT_ABSORPTION',
                'frontend_version': 'V526',
                'production_state': registry.get('state'),
                'production_strategy': strategy,
                'production_write': registry.get('buy_enabled') is True,
                'new_admissions_enabled': registry.get('buy_enabled') is True,
                'pending_execution_enabled': registry.get('pending_execution_enabled') is True,
                'pending_execution_count': registry.get('pending_execution_count', 0),
                'buy_enabled': registry.get('buy_enabled') is True,
                'active_buy_valid_count': sum(p.get('status') == 'OPEN' for p in positions),
                'pending_next_open_count': sum(p.get('status') == 'PENDING_NEXT_OPEN' for p in pending),
                'forbidden_fallback': True,
                'total_trades': 0, 'win_rate': 0, 'avg_pnl': 0, 'total_pnl': 0,
                'stocks': 0, 'signals': {},
                'data_status': registry.get('data_epoch', {}),
                'scanner': {'generated_at': scanner.get('generated_at'), 'decision': scanner.get('decision'), 'market_date': scanner.get('market_date')},
                'lineages': registry.get('lineages', {}),
            })
            return
        if _production_empty_book() and not qs.get('ver'):
            self._json({
                'version': None,
                'frontend_version': 'EMPTY_BOOK',
                'production_state': registry.get('state') or 'EMPTY_BOOK',
                'production_strategy': None,
                'shadow_challenger': None,
                'production_write': False,
                'buy_enabled': False,
                'active_buy_valid_count': 0,
                'forbidden_fallback': True,
                'production_blocker': registry.get('reason') or 'NO_PROMOTED_PRODUCTION_STRATEGY',
                'total_trades': 0, 'win_rate': 0, 'avg_pnl': 0, 'total_pnl': 0,
                'stocks': 0, 'signals': {},
                'data_status': _current_committed_data_epoch(registry.get('data_epoch', {})),
                'lineages': registry.get('lineages', {}),
                'research_program': registry.get('research_program', {}),
                'next_ontology': registry.get('next_ontology'),
            })
            return
        # FIX(2026-08-17): COMBO 组合策略准生产（纸面）分支
        if registry.get('production_strategy') == 'COMBO_SMC_EVENT' and not qs.get('ver'):
            combo = _load_json_dict(Path('/root/.hermes/smc_monitor/combo_dashboard.json'), {})
            paper = combo.get('paper_production') or {}
            self._json({
                'version': 'COMBO_SMC_EVENT',
                'frontend_version': 'COMBO_PAPER_PRODUCTION',
                'production_state': registry.get('state') or 'PAPER_PRODUCTION_COMBO',
                'production_strategy': 'COMBO_SMC_EVENT',
                'production_write': False,
                'buy_enabled': registry.get('buy_enabled') is True,
                'active_buy_valid_count': paper.get('buy_valid_count', 0),
                'paper_open_positions': paper.get('open_positions', 0),
                'paper_closed_trades': paper.get('closed_trades', 0),
                'paper_closed_wr': paper.get('closed_wr', 0),
                'paper_closed_avg_pnl': paper.get('closed_avg_pnl', 0),
                'forbidden_fallback': True,
                'mode': 'PAPER_PRODUCTION (纸面跟踪，非真实资金)',
                'total_trades': 0, 'win_rate': 0, 'avg_pnl': 0, 'total_pnl': 0,
                'stocks': 0, 'signals': {},
                'data_status': _current_committed_data_epoch(registry.get('data_epoch', {})),
                'lineages': registry.get('lineages', {}),
            })
            return
        v185_state = _load_json_dict(V185_DIR / 'v185_report.json', {})
        if v185_state.get('version') == 'V185' and v185_state.get('production_write') is False:
            refresh = _load_json_dict(V185_DIR.parent / 'smc_monitor/kline_refresh_latest.json', {})
            self._json({
                'version': 'V185',
                'engine': v185_state.get('engine') or 'V185_CAUSAL_REBUILD_PENDING',
                'production_state': 'EMPTY_BOOK_FAIL_CLOSED',
                'production_write': False,
                'decision': v185_state.get('decision') or 'V185_REJECTED_CAUSALITY',
                'production_blocker': v185_state.get('production_blocker') or 'V185_CAUSAL_CURRENT_SCANNER_NOT_APPROVED',
                'total_trades': 0, 'win_rate': 0, 'avg_pnl': 0, 'total_pnl': 0,
                'stocks': 0, 'signals': {},
                'pick_contract': get_pick_contract_summary(version='V185'),
                'research_history': v185_state.get('production_stats') or v185_state.get('metrics') or {},
                'data_status': {
                    'last_kline_date': refresh.get('observed_latest_date') or _v88_latest_market_date(),
                    'refresh_gate_pass': refresh.get('gate_pass') is True,
                    'note': 'V185 historical advantage rejected by causality audit; production stays empty until a raw current scanner passes independent verification.',
                },
            })
            return
        if req_ver in ('V47_2','V48_1','V49','V50','V51','V52','V53','V54','V55','V56','V57','V58','V59','V60','V61','V62','V63','V64','V65','V66'):
            dir_map = {'V47_2': V47_2_DIR, 'V48_1': V48_1_DIR, 'V49': V49_DIR, 'V50': V50_DIR, 'V51': V51_DIR, 'V52': V52_DIR, 'V53': V53_DIR, 'V54': V54_DIR, 'V55': V55_DIR, 'V56': V56_DIR, 'V57': V57_DIR, 'V58': V58_DIR, 'V59': V59_DIR, 'V60': V60_DIR, 'V61': V61_DIR, 'V62': V62_DIR, 'V63': V63_DIR, 'V64': V64_DIR, 'V65': V65_DIR, 'V66': V66_DIR}
            prefix_map = {'V47_2': 'v47_2', 'V48_1': 'v48_1', 'V49': 'v49', 'V50': 'v50', 'V51': 'v51', 'V52': 'v52', 'V53': 'v53', 'V54': 'v54', 'V55': 'v55', 'V56': 'v56', 'V57': 'v57', 'V58': 'v58', 'V59': 'v59', 'V60': 'v60', 'V61': 'v61', 'V62': 'v62', 'V63': 'v63', 'V64': 'v64', 'V65': 'v65', 'V66': 'v66'}
            v = get_version_trades(req_ver, lite=False)
            if not v:
                self._json({'error': f'no {req_ver} data'}); return
            rep = _load_json_dict(dir_map[req_ver]/f"{prefix_map[req_ver]}_report.json", {})
            won = sum(1 for t in v if _float_or_zero(t.get('pnl_pct')) > 0)
            self._json({
                'version': req_ver, 'active_default': ACTIVE_VERSION,
                'total_trades': len(v),
                'win_rate': round(won/len(v)*100, 1) if v else 0,
                'avg_pnl': round(sum(_float_or_zero(t.get('pnl_pct')) for t in v)/len(v), 2) if v else 0,
                'stocks': len(set(t.get('symbol','') for t in v)),
                'signals': dict(Counter(t.get('signal_type', t.get('zone_type', '?')) for t in v)),
                'pick_contract': get_pick_contract_summary(version=req_ver),
                'candidate_report': rep.get('metrics', {}),
                'candidate_autopsy': rep.get('autopsy_summary', {}),
                'data_status': {'note': f'{req_ver} is current default production' if ACTIVE_VERSION == req_ver else f'{req_ver} available through ver parameter'}
            }); return
        # Fast path: avoid loading 216MB V44 full trades just for health summary.
        if ACTIVE_VERSION == 'V44':
            fast = get_v44_summary_fast()
            if fast:
                data_status = {'note': 'fast summary path; detailed trade pages lazy-load full cache'}
                self._json({
                    'total_trades': fast.get('total_trades', 0),
                    'win_rate': fast.get('win_rate', 0),
                    'avg_pnl': fast.get('avg_pnl', 0),
                    'stocks': fast.get('stocks', 0),
                    'signals': fast.get('signals', {}),
                    'pick_contract': {'active_pick_count': 0, 'historical_best_count': len(_load_json_list(ACTIVE_PICK_FILE, [])), 'watch_only_count': 0, 'raw_pick_file_count': len(_load_json_list(ACTIVE_PICK_FILE, [])), 'active_picks_not_historical_all_market': True, 'contract_note': 'fast summary path; V44 historical picks isolated'},
                    'equity_curve_contract': {'definition': 'lazy on /api/equity_curve'},
                    'data_status': data_status,
                    'v45_native_status': _load_json_dict(V45_NATIVE_DIR/'v45_validation_summary.json', {}).get('production_acceptance', {}),
                    'v45_1_status': _load_json_dict(V45_1_DIR/'v45_1_validation_summary.json', {}).get('production_acceptance', {}),
                            'v45_2_status': _load_json_dict(V45_2_DIR/'v45_2_validation_summary.json', {}).get('production_acceptance', {}),
                    'v45_3_status': _load_json_dict(V45_3_DIR/'v45_3_validation_summary.json', {}).get('production_acceptance', {}),
                    'v45_4_status': _load_json_dict(V45_4_DIR/'v45_4_validation_summary.json', {}).get('production_acceptance', {}),
                    'v45_3_status': _load_json_dict(V45_3_DIR/'v45_3_validation_summary.json', {}).get('production_acceptance', {}),
                    'v45_4_status': _load_json_dict(V45_4_DIR/'v45_4_validation_summary.json', {}).get('production_acceptance', {})
                }); return
        v = get_default_trades()
        if not v:
            self._json({'error': 'no data'}); return
        sigs = Counter(t.get('signal_type', t.get('zone_type', '?')) for t in v)
        pnl_values = []
        for t in v:
            try:
                pnl_values.append(float(t.get('pnl_pct') or 0))
            except Exception:
                pnl_values.append(0.0)
        won = sum(1 for x in pnl_values if x > 0)
        
        # Data status: trace last kline date and last trade date
        try:
            # Check kline cache for latest date
            cache = Path('/root/.hermes/kline_cache')
            latest_kline = None
            if cache.exists():
                latest_files = sorted(cache.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:10]
                for f in latest_files:
                    if f.name.endswith('.json'):
                        import json
                        try:
                            data = json.load(f.open())
                            if data:
                                last_date = str(data[-1].get('t', data[-1].get('date', '')))
                                if last_date:
                                    latest_kline = last_date
                                    break
                        except: pass
            
            last_trade_date = max((t.get('entry_date', '') for t in v), default='')
            data_status = {
                'last_kline_date': latest_kline or 'unknown',
                'last_trade_date': last_trade_date,
                'data_age_days': (datetime.strptime(latest_kline, '%Y%m%d') - datetime.strptime(last_trade_date, '%Y%m%d')).days if latest_kline and last_trade_date else None,
                'note': '5月信号稀少: bear sweep on 2026-05-14 suppresses bull signals (normal SMC behavior)'
            }
        except:
            data_status = {'error': 'could not compute data status'}
        
        report_stats = _active_report_stats('production_A_only')
        if report_stats.get('version') in ('V100', 'V101', 'V102', 'V185') and report_stats.get('total_trades'):
            total_trades = report_stats['total_trades']
            win_rate = round(report_stats['win_rate'], 1)
            avg_pnl = round(report_stats['avg_pnl'], 2)
            total_pnl = round(report_stats['total_pnl'], 2)
            metric_contract = report_stats
        else:
            total_trades = len(v)
            win_rate = round(won/len(v)*100, 1) if v else 0
            avg_pnl = round(sum(pnl_values)/len(v), 2) if v else 0
            total_pnl = round(sum(pnl_values), 2) if v else 0
            metric_contract = {'engine': ACTIVE_VERSION, 'win_definition': 'legacy gross pnl_pct > 0'}
        self._json({
            'version': report_stats.get('version') or ACTIVE_VERSION,
            'engine': report_stats.get('engine') or ACTIVE_VERSION,
            'total_trades': total_trades,
            'win_rate': win_rate,
            'net_win_rate_ge_0_8': win_rate,
            'gross_win_rate': round(report_stats.get('gross_win_rate', win_rate), 1) if report_stats else win_rate,
            'avg_pnl': avg_pnl,
            'total_pnl': total_pnl,
            'stocks': len(set(t.get('symbol','') for t in v)),
            'signals': dict(sigs),
            'metric_contract': metric_contract,
            'pick_contract': get_pick_contract_summary(),
            'equity_curve_contract': build_equity_curve_data(v).get('checks', {}),
            'data_status': data_status,
            'v45_native_status': _load_json_dict(V45_NATIVE_DIR/'v45_validation_summary.json', {}).get('production_acceptance', {}),
            'v45_1_status': _load_json_dict(V45_1_DIR/'v45_1_validation_summary.json', {}).get('production_acceptance', {}),
                    'v45_2_status': _load_json_dict(V45_2_DIR/'v45_2_validation_summary.json', {}).get('production_acceptance', {}),
                    'v45_3_status': _load_json_dict(V45_3_DIR/'v45_3_validation_summary.json', {}).get('production_acceptance', {}),
                    'v45_4_status': _load_json_dict(V45_4_DIR/'v45_4_validation_summary.json', {}).get('production_acceptance', {})
        })


_SCHEDULER_STATE = Path('/root/.hermes/smc_monitor/internal_scheduler_state.json')
_SCHEDULER_LOG = Path('/root/.hermes/logs/smc_internal_scheduler.log')
_SCHEDULER_LOCK = threading.Lock()
_SCHEDULER_JOBS = {
    'v517_shadow_observer': {
        'time': '18:10',
        'cmd': ['python3', 'v523_post_close_shadow_observer.py'],
        'timeout': 1500,
        'desc': 'V517量价吸收：刷新K线+当前epoch scanner+严格next-open shadow（只读）',
    },
}


def _scheduler_load_state():
    try:
        state = json.loads(_SCHEDULER_STATE.read_text())
    except Exception:
        return {'jobs': {}, 'enabled': True}
    changed = False
    now = datetime.now()
    for job in (state.get('jobs') or {}).values():
        if not job.get('running'):
            continue
        stamp = job.get('started_at') or job.get('last_run_at') or ''
        try:
            stale = (now - datetime.fromisoformat(stamp)).total_seconds() > 86400
        except (TypeError, ValueError):
            stale = True
        if stale:
            job['running'] = False
            job['stale_running_recovered_at'] = now.isoformat(timespec='seconds')
            changed = True
    if changed:
        _SCHEDULER_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    return state


def _scheduler_save_state(state):
    _SCHEDULER_STATE.parent.mkdir(parents=True, exist_ok=True)
    _SCHEDULER_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def _scheduler_log(msg):
    _SCHEDULER_LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}\n"
    with _SCHEDULER_LOG.open('a') as fp:
        fp.write(line)
    print(line.rstrip(), flush=True)


def _scheduler_due(now, hhmm):
    hour, minute = [int(x) for x in hhmm.split(':')]
    return now >= now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _scheduler_run_job(name, cfg, run_date, force=False, trigger='schedule'):
    with _SCHEDULER_LOCK:
        state = _scheduler_load_state()
        prev = (state.get('jobs') or {}).get(name, {})
        if (not force and prev.get('last_success_date') == run_date) or prev.get('running'):
            return
        jobs = state.setdefault('jobs', {})
        jobs[name] = {**prev, 'running': True, 'started_at': datetime.now().isoformat(timespec='seconds'), 'desc': cfg.get('desc'), 'time': cfg.get('time'), 'trigger': trigger}
        _scheduler_save_state(state)
    _scheduler_log(f"START {name}: {cfg.get('desc')} trigger={trigger} force={force}")
    rc = -1
    stdout = ''
    stderr = ''
    try:
        r = subprocess.run(cfg['cmd'], cwd='/root/.hermes/scripts/v25', capture_output=True, text=True, timeout=cfg.get('timeout', 3600))
        rc = r.returncode
        stdout = (r.stdout or '')[-4000:]
        stderr = (r.stderr or '')[-4000:]
    except subprocess.TimeoutExpired as e:
        rc = -2
        stdout = (e.stdout or '')[-4000:] if isinstance(e.stdout, str) else ''
        stderr = f'TIMEOUT {cfg.get("timeout")}s'
    except Exception as e:
        rc = -3
        stderr = repr(e)
    with _SCHEDULER_LOCK:
        state = _scheduler_load_state()
        jobs = state.setdefault('jobs', {})
        jobs[name] = {
            'running': False,
            'time': cfg.get('time'),
            'desc': cfg.get('desc'),
            'last_run_date': run_date,
            'last_run_at': datetime.now().isoformat(timespec='seconds'),
            'last_returncode': rc,
            'last_success_date': run_date if rc == 0 else jobs.get(name, {}).get('last_success_date', ''),
            'trigger': trigger,
            'manual_force': bool(force),
            'stdout_tail': stdout,
            'stderr_tail': stderr,
        }
        _scheduler_save_state(state)
    _scheduler_log(f"END {name}: rc={rc}")


def _internal_scheduler_enabled():
    """Only an explicit truthy value may enable the in-process scheduler.

    System cron owns the production post-close observer by default; strings such
    as '0' must be a real disable, not merely non-empty values.
    """
    return os.environ.get('SMC_INTERNAL_SCHEDULER', '').strip().lower() in ('1', 'true', 'yes', 'on')


def _scheduler_loop():
    _scheduler_log('SMC internal scheduler enabled: no system cron required')
    while True:
        try:
            if _internal_scheduler_enabled():
                now = datetime.now()
                if now.weekday() < 5:
                    run_date = now.strftime('%Y%m%d')
                    for name, cfg in _SCHEDULER_JOBS.items():
                        if _scheduler_due(now, cfg['time']):
                            threading.Thread(target=_scheduler_run_job, args=(name, cfg, run_date), daemon=True).start()
            time.sleep(60)
        except Exception as e:
            _scheduler_log(f'ERROR scheduler_loop {e!r}')
            time.sleep(60)


def start_internal_scheduler():
    t = threading.Thread(target=_scheduler_loop, daemon=True, name='smc-internal-scheduler')
    t.start()
    return t


if __name__ == '__main__':
    print(f"SMC Full Dashboard: http://0.0.0.0:{PORT}", flush=True)
    # Do not eager-load the 216MB V44 full trade cache on startup. First request will lazy-load.
    print(f"  Active: {ACTIVE_VERSION}", flush=True)
    print(f"  TradeFile: {ACTIVE_TRADE_FILE}", flush=True)
    print(f"  PickFile: {ACTIVE_PICK_FILE}", flush=True)
    print(f"  Pages: / | /kline | /backtest | /monitor | /analysis | /autopsy | /stoploss | /v45 | /docs", flush=True)
    if _internal_scheduler_enabled():
        start_internal_scheduler()
    else:
        print('SMC internal scheduler disabled; system cron remains authoritative', flush=True)
    server = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    server.serve_forever()
