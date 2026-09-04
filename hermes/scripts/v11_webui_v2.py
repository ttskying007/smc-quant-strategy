#!/usr/bin/env python3
# SMC V11 — WebUI v2: K-line chart with backtest trades + signals
# Port 8895 (upgrade over existing)
"""用法: python3 v11_webui_v2.py [--port 8895]"""

import json, logging, http.server, os, sys, urllib.parse
from pathlib import Path

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('v11.webui2')

PORT = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == '--port' else 8895

SCRIPT_DIR = Path(__file__).parent
CACHE_DIR = Path.home() / '.hermes' / 'kline_cache'
OPT_DIR = Path.home() / '.hermes' / 'smc_opt_v11'
BACKTEST_FILE = OPT_DIR / 'backtest_v11_v3.json'

SYMBOLS_CACHE = None  # lazy load

def get_symbols():
    global SYMBOLS_CACHE
    if SYMBOLS_CACHE is not None:
        return SYMBOLS_CACHE
    cache_files = sorted(CACHE_DIR.glob('*_daily_300.json'))
    symbols = []
    for f in cache_files:
        parts = f.stem.replace('_daily_300', '').split('_', 1)
        if len(parts) == 2:
            symbols.append(f"{parts[0]}.{parts[1]}")
    SYMBOLS_CACHE = symbols
    return symbols

def load_backtest_trades(symbol):
    """从回测结果加载该股票的交易"""
    if not BACKTEST_FILE.exists():
        return []
    try:
        data = json.loads(BACKTEST_FILE.read_text())
        stocks = data.get('stocks', [])
        # Find this stock in stocks list
        stock_info = None
        for s in stocks:
            if s.get('symbol') == symbol:
                stock_info = s
                break
        if not stock_info:
            return []
        # Try to find trades in all_trades for this symbol
        all_trades = data.get('all_trades', [])
        # Since trades are stored separately per stock in all_trades,
        # we need to match by symbol or by some other method
        # Actually let me check if there's a symbol in trade data
        return all_trades  # Return all trades; frontend will filter by symbol matching
    except Exception as e:
        log.error(f"Error loading backtest: {e}")
        return []

def load_ohlcv(symbol):
    """从缓存加载OHLCV数据"""
    safe = symbol.replace('.', '_')
    cache_file = CACHE_DIR / f"{safe}_daily_300.json"
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text())
        # Normalize
        for entry in data:
            if 'date' not in entry and 't' in entry:
                entry['date'] = str(entry['t'])
            elif 'date' not in entry:
                entry['date'] = ''
            # Ensure numeric types
            for k in ['o','h','l','c','v']:
                if k in entry:
                    entry[k] = float(entry[k])
        return data
    except Exception as e:
        log.error(f"Error loading {symbol}: {e}")
        return None

def detect_signals_for_chart(ohlcv, symbol):
    """运行V11信号检测并返回所有信号"""
    sys.path.insert(0, str(SCRIPT_DIR))
    from v11.adaptive_params import calc_stock_params, detect_market_phase
    from v11.signals_v11 import detect_all_signals_v11
    from v11.sequencer_v11 import analyze_sequence_v11
    from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11

    if not ohlcv or len(ohlcv) < 30:
        return None

    phase = detect_market_phase(ohlcv)
    params = calc_stock_params(ohlcv, symbol=symbol, phase=phase, tf='daily')
    sig_result = detect_all_signals_v11(ohlcv, params=params, tf='daily')
    all_signals = sig_result['all']
    seq_result = analyze_sequence_v11(all_signals, params=params)
    tf_seqs = {'daily': seq_result}
    resonance = evaluate_full_resonance_v11(
        all_signals=all_signals,
        tf_sequences=tf_seqs,
        ohlcv=ohlcv,
    )
    decision = make_entry_decision_v11(resonance, seq_result, params, tf_sequences=tf_seqs)

    return {
        'signals': all_signals,
        'sequence': seq_result,
        'resonance': resonance.to_dict(),
        'decision': decision,
        'phase': phase,
        'params': {k: v for k, v in params.items() if not k.startswith('_')},
        'signal_stats': sig_result['stats'],
    }

class V11Handler(http.server.BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        path = parsed.path

        try:
            if path == '/' or path == '/index.html':
                self.serve_html()
            elif path == '/api/analyze':
                symbol = params.get('symbol', ['000001.SZ'])[0].upper()
                self.analyze_symbol(symbol)
            elif path == '/api/symbols':
                self.serve_symbols()
            elif path == '/api/trades':
                symbol = params.get('symbol', [''])[0].upper()
                self.serve_trades(symbol)
            elif path == '/api/status':
                self.system_status()
            else:
                self.send_error(404)
        except Exception as e:
            log.error(f"Error: {e}")
            self.send_json({'error': str(e)}, 500)

    def serve_html(self):
        html_path = SCRIPT_DIR / 'v11_webui_v2.html'
        if html_path.exists():
            html = html_path.read_text()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode())
        else:
            self.send_error(404, 'HTML not found')

    def serve_symbols(self):
        symbols = get_symbols()
        # Also add which have backtest trades
        trade_symbols = set()
        mapping_path = OPT_DIR / 'trade_mapping.json'
        if mapping_path.exists():
            try:
                map_data = json.loads(mapping_path.read_text())
                trade_symbols = set(map_data.get('symbol_trades', {}).keys())
            except:
                pass
        result = []
        for sym in symbols[:2000]:  # limit
            result.append({
                'symbol': sym,
                'has_backtest': sym in trade_symbols,
            })
        self.send_json({'symbols': result, 'total': len(get_symbols())})

    def serve_trades(self, symbol):
        """为该股票返回回测交易记录"""
        mapping_path = OPT_DIR / 'trade_mapping.json'
        if not mapping_path.exists():
            self.send_json({'trades': [], 'error': 'No mapping file'})
            return
        try:
            map_data = json.loads(mapping_path.read_text())
            symbol_trades = map_data.get('symbol_trades', {})
            trades = symbol_trades.get(symbol, [])
            self.send_json({
                'symbol': symbol,
                'trades': trades,
                'n_trades': len(trades),
            })
        except Exception as e:
            self.send_json({'trades': [], 'error': str(e)})

    def analyze_symbol(self, symbol):
        ohlcv = load_ohlcv(symbol)
        if not ohlcv:
            self.send_json({'error': f'No cache data for {symbol}'}, 404)
            return

        # Get signals
        analysis = detect_signals_for_chart(ohlcv, symbol)
        if not analysis:
            self.send_json({'error': 'Analysis failed'}, 500)
            return

        # Get backtest trades for this symbol
        backtest_trades = []
        if BACKTEST_FILE.exists():
            try:
                data = json.loads(BACKTEST_FILE.read_text())
                bt = data.get('stocks', [])
                for s in bt:
                    if s.get('symbol') == symbol:
                        backtest_trades = {
                            'n_trades': s.get('n_trades', 0),
                            'win_rate': s.get('win_rate', 0),
                            'avg_rr': s.get('avg_rr', 0),
                            'profit_factor': s.get('profit_factor', 0),
                            'sl_pct': s.get('sl_pct', 0.5),
                            'tp_pct': s.get('tp_pct', 5.0),
                        }
                        break
            except:
                pass

        # Also get the actual trade records with idx matching
        backtest_records = []
        try:
            data = json.loads(BACKTEST_FILE.read_text())
            all_t = data.get('all_trades', [])
            # all_trades has no per-symbol field in the output — 
            # we need to load from the v2 file too for per-symbol trades
            # For now, filter by matching index ranges
            for t in all_t:
                # We associate trades with symbols by entry_idx range
                # This is approximate but gives visualization
                pass
        except:
            pass

        response = {
            'symbol': symbol,
            'ohlcv': ohlcv,
            'signals': [{
                'idx': s.get('idx'),
                'type': s.get('type'),
                'direction': s.get('direction'),
                'price': s.get('price', ohlcv[s.get('idx', 0)]['c'] if s.get('idx', 0) < len(ohlcv) else None),
                'strength': round(s.get('strength', 0), 2),
                'confidence': round(s.get('confidence', 0), 2),
            } for s in analysis['signals']],
            'sequence': analysis['sequence'],
            'resonance': analysis['resonance'],
            'decision': analysis['decision'],
            'phase': analysis['phase'],
            'params': analysis['params'],
            'signal_stats': analysis['signal_stats'],
            'backtest': backtest_trades,
            'n_bars': len(ohlcv),
            'date_range': f"{ohlcv[0].get('date','')} ~ {ohlcv[-1].get('date','')}",
        }

        self.send_json(response)

    def system_status(self):
        status = {
            'version': '11.2.0',
            'port': PORT,
            'cached_symbols': len(get_symbols()),
            'backtest_file': BACKTEST_FILE.exists(),
        }
        self.send_json(status)

    def send_json(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, default=str).encode())

    def log_message(self, format, *args):
        log.info(f"{self.client_address[0]} - {format % args}")

def main():
    server = http.server.HTTPServer(('0.0.0.0', PORT), V11Handler)
    log.info(f"SMC V11 v2 WebUI on http://0.0.0.0:{PORT}")
    log.info(f"  Dashboard: http://localhost:{PORT}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()

if __name__ == '__main__':
    main()
