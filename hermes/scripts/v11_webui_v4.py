#!/usr/bin/env python3
# SMC V11 — WebUI v4: SMC Navigator (全量市场 + 实时信号 + 参数优化)
# Port 8896 (upgrade over v3)
"""用法: python3 v11_webui_v4.py [--port 8896]"""

import json, logging, http.server, os, sys, urllib.parse, importlib, math
from pathlib import Path
from collections import Counter, defaultdict

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('v11.webui4')

PORT = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == '--port' else 8896

SCRIPT_DIR = Path(__file__).parent
CACHE_DIR = Path.home() / '.hermes' / 'kline_cache'
V11_DIR = Path.home() / '.hermes' / 'smc_opt_v11'
V13_DIR = Path.home() / '.hermes' / 'smc_opt_v13'
V14_DIR = Path.home() / '.hermes' / 'smc_opt_v14'

# 加载所有回测结果
CACHE_V11 = {}
CACHE_V13 = {}
CACHE_V14 = {}
STOCK_LIST = []

def load_all_backtests():
    global CACHE_V11, CACHE_V13, CACHE_V14, STOCK_LIST
    
    # V11 V7 (V11.3 Scout-only)
    v7path = V11_DIR / 'backtest_v11_v7.json'
    if v7path.exists():
        CACHE_V11['v7'] = json.loads(v7path.read_text())
    
    # V11 V116 (V11.6 摆动点)
    v116path = V11_DIR / 'backtest_v11_v116.json'
    if v116path.exists():
        CACHE_V11['v116'] = json.loads(v116path.read_text())
    
    # V11 V117 (V11.7 摆动点黄金约束)
    v117path = V11_DIR / 'backtest_v11_v117.json'
    if v117path.exists():
        CACHE_V11['v117'] = json.loads(v117path.read_text())
    
    # V13 全量
    v13path = V13_DIR / 'v13_merged_summary.json'
    if v13path.exists():
        CACHE_V13 = json.loads(v13path.read_text())
    
    # V14 全量
    v14path = V14_DIR / 'v14_full_analysis.json'
    if v14path.exists():
        CACHE_V14 = json.loads(v14path.read_text())
    elif (V14_DIR / 'v14_full.json').exists():
        raw = json.loads((V14_DIR / 'v14_full.json').read_text())
        stocks = raw.get('stocks', [])
        CACHE_V14 = {
            'stocks': stocks,
            'tradable': sum(1 for s in stocks if s.get('n_trades', 0) >= 3),
            'total_trades': sum(s.get('n_trades', 0) for s in stocks),
        }
    
    # 股票列表
    cache_files = sorted(CACHE_DIR.glob('*_daily_300.json'))
    STOCK_LIST = []
    for f in cache_files:
        parts = f.stem.replace('_daily_300', '').split('_', 1)
        if len(parts) == 2:
            sym = f"{parts[0]}.{parts[1]}"
            has_v13 = False
            has_v14 = False
            v14_params = {}
            if CACHE_V13 and 'stocks' in CACHE_V13:
                for s in CACHE_V13.get('stocks', []):
                    if s.get('symbol') == sym and s.get('n_trades', 0) >= 3:
                        has_v13 = True
                        break
            if CACHE_V14 and 'stocks' in CACHE_V14:
                for s in CACHE_V14.get('stocks', []):
                    if s.get('symbol') == sym:
                        has_v14 = s.get('n_trades', 0) >= 3
                        if has_v14:
                            perf = s.get('perf', {})
                            v14_params = {
                                'sl_pct': perf.get('sl_pct', 0.3),
                                'tp_pct': perf.get('tp_pct', 5.0),
                                'wr': perf.get('win_rate', 0),
                                'rr': perf.get('avg_rr', 0),
                                'n_trades': s.get('n_trades', 0),
                            }
                        break
            
            STOCK_LIST.append({
                'symbol': sym,
                'has_v13': has_v13,
                'has_v14': has_v14,
                'v14_params': v14_params,
            })
    
    log.info(f"Loaded {len(STOCK_LIST)} stocks, V13 tradable={sum(1 for s in STOCK_LIST if s['has_v13'])}, V14={sum(1 for s in STOCK_LIST if s['has_v14'])}")

load_all_backtests()

def load_ohlcv(symbol):
    safe = symbol.replace('.', '_')
    cache_file = CACHE_DIR / f"{safe}_daily_300.json"
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text())
        for entry in data:
            if 'date' not in entry and 't' in entry:
                entry['date'] = str(entry['t'])
            for k in ['o','h','l','c','v']:
                if k in entry:
                    entry[k] = float(entry[k])
        return data
    except Exception as e:
        log.error(f"Error loading {symbol}: {e}")
        return None


def detect_signals_live(ohlcv, symbol):
    """实时信号检测"""
    sys.path.insert(0, str(SCRIPT_DIR))
    from v11.adaptive_params import calc_stock_params, detect_market_phase
    from v11.signals_v11 import detect_all_signals_v11
    from v11.sequencer_v11 import analyze_sequence_v11
    from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
    from v11.weekly_trend import synthesize_weekly, weekly_trend
    
    if not ohlcv or len(ohlcv) < 30:
        return None
    
    phase = detect_market_phase(ohlcv)
    params = calc_stock_params(ohlcv, symbol=symbol, phase=phase, tf='daily')
    sig_result = detect_all_signals_v11(ohlcv, params=params, tf='daily')
    all_signals = sig_result['all']
    
    # 最近60根信号
    recent_sigs = [s for s in all_signals if s.get('idx', 0) >= len(ohlcv) - 60]
    
    seq_result = analyze_sequence_v11(all_signals, params=params)
    tf_seqs = {'daily': seq_result}
    resonance = evaluate_full_resonance_v11(
        all_signals=all_signals,
        tf_sequences=tf_seqs,
        ohlcv=ohlcv,
    )
    decision = make_entry_decision_v11(resonance, seq_result, params, tf_sequences=tf_seqs)
    
    # V11.6 摆动点SL/TP (如果decision是enter)
    swing_info = None
    if decision.get('action') == 'enter' and decision.get('entry_price'):
        entry = decision['entry_price']
        # 简单摆动点计算
        for i in range(len(ohlcv)-2, max(0, len(ohlcv)-20)-1, -1):
            bar = ohlcv[i]
            left = ohlcv[i-1]['l']
            right = ohlcv[i+1]['l']
            if bar['l'] < left and bar['l'] < right:
                sl_pct = (entry - bar['l']) / entry * 100
                if 0.25 <= sl_pct <= 0.6:
                    swing_info = {'sl': round(bar['l'], 2), 'sl_pct': round(sl_pct, 2)}
                    break
    
    # 周线趋势
    weekly = synthesize_weekly(ohlcv)
    wt = weekly_trend(weekly, lookback=min(5, len(weekly))) if len(weekly) >= 3 else 'unknown'
    
    # 最近信号汇总
    latest_sig_types = Counter(s.get('type', '?') for s in recent_sigs[-20:])
    
    return {
        'symbol': symbol,
        'ohlcv_latest': ohlcv[-30:],  # 最近30根
        'signals': [{
            'idx': s.get('idx'), 'type': s.get('type'),
            'direction': s.get('direction'),
            'price': s.get('price', 0),
            'confidence': round(s.get('confidence', 0), 2),
        } for s in recent_sigs[-50:]],
        'sequence': seq_result,
        'resonance': resonance.to_dict() if hasattr(resonance, 'to_dict') else {},
        'decision': decision,
        'phase': phase,
        'weekly_trend': wt,
        'latest_signal_types': dict(latest_sig_types.most_common(5)),
        'swing_info': swing_info,
        'n_total_signals': len(all_signals),
        'n_recent_signals': len(recent_sigs),
        'params': {k: v for k, v in params.items() if not k.startswith('_')},
    }


class V4Handler(http.server.BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        path = parsed.path
        
        try:
            if path == '/':
                self.serve_html('v11_webui_v4.html')
            elif path == '/api/status':
                self.api_status()
            elif path == '/api/symbols':
                self.api_symbols(params)
            elif path == '/api/analyze':
                symbol = params.get('symbol', ['000001.SZ'])[0].upper()
                self.api_analyze(symbol)
            elif path == '/api/market':
                self.api_market_overview()
            elif path == '/api/versions':
                self.api_versions()
            elif path == '/api/trade-history':
                symbol = params.get('symbol', [''])[0].upper()
                version = params.get('version', ['v7'])[0]
                self.api_trade_history(symbol, version)
            elif path == '/api/multi-param':
                self.api_multi_param()
            else:
                self.send_error(404)
        except Exception as e:
            log.error(f"Error: {e}")
            self.send_json({'error': str(e)}, 500)

    def serve_html(self, name):
        html_path = SCRIPT_DIR / name
        if html_path.exists():
            html = html_path.read_text()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode())
        else:
            self.send_error(404, f'{name} not found')

    def api_status(self):
        n_v13 = sum(1 for s in STOCK_LIST if s['has_v13'])
        n_v14 = sum(1 for s in STOCK_LIST if s['has_v14'])
        self.send_json({
            'version': 'V11.7 Navigator v4',
            'port': PORT,
            'cached_symbols': len(STOCK_LIST),
            'v13_tradable': n_v13,
            'v14_tradable': n_v14,
            'v14_avg_rr': CACHE_V14.get('avg_rr', CACHE_V14.get('summary', {}).get('avg_rr', 0)),
            'v13_avg_wr': CACHE_V13.get('avg_wr', 0),
        })

    def api_symbols(self, params):
        page = int(params.get('page', ['0'])[0])
        per_page = int(params.get('per_page', ['50'])[0])
        filter_v13 = 'v13' in params.get('filter', [''])[0]
        filter_v14 = 'v14' in params.get('filter', [''])[0]
        search = params.get('search', [''])[0].upper()
        
        filtered = STOCK_LIST
        if filter_v13:
            filtered = [s for s in filtered if s['has_v13']]
        if filter_v14:
            filtered = [s for s in filtered if s['has_v14']]
        if search:
            filtered = [s for s in filtered if search in s['symbol']]
        
        start = page * per_page
        end = start + per_page
        page_items = filtered[start:end]
        
        self.send_json({
            'total': len(filtered),
            'page': page,
            'per_page': per_page,
            'symbols': page_items,
        })

    def api_analyze(self, symbol):
        ohlcv = load_ohlcv(symbol)
        if not ohlcv:
            self.send_json({'error': f'No data for {symbol}'}, 404)
            return
        
        analysis = detect_signals_live(ohlcv, symbol)
        if not analysis:
            self.send_json({'error': 'Analysis failed'}, 500)
            return
        
        # 附加V14参数信息
        v14_info = {}
        for s in STOCK_LIST:
            if s['symbol'] == symbol:
                v14_info = s.get('v14_params', {})
                break
        
        response = {
            **analysis,
            'v14_params': v14_info,
            'n_bars': len(ohlcv),
            'date_range': f"{ohlcv[0].get('date','')} ~ {ohlcv[-1].get('date','')}",
        }
        self.send_json(response)

    def api_market_overview(self):
        """全量市场概览"""
        v13_data = CACHE_V13.get('stocks', [])
        v14_data = CACHE_V14.get('stocks', [])
        
        # V13 阶段分布
        v13_phase = Counter(s.get('phase', '?') for s in v13_data if s.get('n_trades', 0) >= 3)
        
        # V14 参数分布
        v14_sl = Counter()
        v14_tp = Counter()
        v14_wr_bands = Counter()
        for s in v14_data:
            perf = s.get('perf', {})
            n = s.get('n_trades', 0)
            if n >= 3:
                v14_sl[perf.get('sl_pct', 0)] += 1
                v14_tp[perf.get('tp_pct', 0)] += 1
                wr = perf.get('win_rate', 0)
                if wr >= 90: v14_wr_bands['90-100%'] += 1
                elif wr >= 80: v14_wr_bands['80-90%'] += 1
                elif wr >= 70: v14_wr_bands['70-80%'] += 1
                elif wr >= 60: v14_wr_bands['60-70%'] += 1
                elif wr >= 50: v14_wr_bands['50-60%'] += 1
                else: v14_wr_bands['<50%'] += 1
        
        # V11.6 摆动点指标
        v116_data = CACHE_V11.get('v116', {})
        v116_summary = v116_data.get('summary', {})
        
        self.send_json({
            'v13': {
                'tradable': len(v13_data),
                'total_trades': CACHE_V13.get('total_trades', 0),
                'avg_wr': CACHE_V13.get('avg_wr', 0),
                'avg_rr': CACHE_V13.get('avg_rr', 0),
                'avg_pf': CACHE_V13.get('avg_pf', 0),
                'phase_dist': dict(v13_phase.most_common(5)),
            },
            'v14': {
                'tradable': len(v14_data),
                'total_trades': CACHE_V14.get('total_trades', 0),
                'avg_wr': CACHE_V14.get('avg_wr', CACHE_V14.get('summary', {}).get('avg_wr', 0)),
                'avg_rr': CACHE_V14.get('avg_rr', CACHE_V14.get('summary', {}).get('avg_rr', 0)),
                'sl_dist': dict(v14_sl.most_common(5)),
                'tp_dist': dict(v14_tp.most_common(5)),
                'wr_dist': dict(v14_wr_bands.most_common(5)),
            },
            'v116': {
                'tradable': v116_summary.get('tradable', 0),
                'total_trades': v116_summary.get('total_trades', 0),
                'win_rate': v116_summary.get('win_rate', 0),
                'avg_rr': v116_summary.get('avg_rr', 0),
                'profit_factor': v116_summary.get('profit_factor', 0),
                'swing_pct': v116_summary.get('swing_pct', 0),
            } if v116_summary else {},
        })

    def api_versions(self):
        """全版本对比"""
        versions = {}
        
        # V11.3 (v7)
        v7 = CACHE_V11.get('v7', {})
        if v7.get('summary'):
            s = v7['summary']
            versions['V11.3 Scout-only'] = {
                'trades': s['total_trades'], 'wr': s['win_rate'],
                'rr': s['avg_rr'], 'pf': s['profit_factor'],
                'tradable': s['tradable'],
            }
        
        # V11.6 摆动点
        v116 = CACHE_V11.get('v116', {})
        if v116.get('summary'):
            s = v116['summary']
            versions['V11.6 摆动SL/TP'] = {
                'trades': s['total_trades'], 'wr': s['win_rate'],
                'rr': s['avg_rr'], 'pf': s['profit_factor'],
                'tradable': s['tradable'],
            }
        
        # V11.7
        v117 = CACHE_V11.get('v117', {})
        if v117.get('summary'):
            s = v117['summary']
            versions['V11.7 黄金约束SL'] = {
                'trades': s['total_trades'], 'wr': s['win_rate'],
                'rr': s['avg_rr'], 'pf': s['profit_factor'],
                'tradable': s['tradable'],
            }
        
        # V13
        versions['V13 全量4800'] = {
            'trades': CACHE_V13.get('total_trades', 0),
            'wr': CACHE_V13.get('avg_wr', 0),
            'rr': CACHE_V13.get('avg_rr', 0),
            'pf': CACHE_V13.get('avg_pf', 0),
            'tradable': len(CACHE_V13.get('stocks', [])),
        }
        
        # V14
        v14_s = CACHE_V14.get('summary', {})
        versions['V14 每股参数'] = {
            'trades': CACHE_V14.get('total_trades', 0),
            'wr': v14_s.get('avg_wr', 0) or CACHE_V14.get('avg_wr', 0),
            'rr': v14_s.get('avg_rr', 0) or CACHE_V14.get('avg_rr', 0),
            'pf': v14_s.get('avg_pf', 0) or CACHE_V14.get('avg_pf', 0),
            'tradable': len(CACHE_V14.get('stocks', [])),
        }
        
        self.send_json({'versions': versions})

    def api_trade_history(self, symbol, version):
        data = CACHE_V11.get(version, {})
        all_trades = data.get('all_trades', [])
        stocks = data.get('stocks', [])
        
        # 找到该股票的trade范围
        offset = 0
        stock_trades = []
        for s in stocks:
            n = s.get('n_trades', 0)
            if s.get('symbol') == symbol:
                stock_trades = all_trades[offset:offset + n]
                break
            offset += n
        
        self.send_json({
            'symbol': symbol,
            'version': version,
            'n_trades': len(stock_trades),
            'trades': stock_trades,
        })

    def api_multi_param(self):
        mp_path = V14_DIR / 'v14_multiopt_100.json'
        if not mp_path.exists():
            self.send_json({'error': 'No multi-param data yet'})
            return
        data = json.loads(mp_path.read_text())
        self.send_json(data)

    def send_json(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, default=str).encode())

    def log_message(self, format, *args):
        log.info(f"{self.client_address[0]} - {format % args}")


def main():
    server = http.server.HTTPServer(('0.0.0.0', PORT), V4Handler)
    log.info(f"SMC Navigator v4 on http://0.0.0.0:{PORT}")
    log.info(f"  Dashboard: http://localhost:{PORT}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()

if __name__ == '__main__':
    main()
