#!/usr/bin/env python3
"""
ETF/指数数据获取与V38.4信号检测
使用Tencent API获取数据, 覆盖ETF和主要指数
"""
import json, sys, time, math
from pathlib import Path
from collections import Counter

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v11 import detect_all_signals_v11
from v11.structure_tree_v38 import StructureTree
from v11.wyckoff_phases_v38 import detect_wyckoff_phases

# ── Tencent API ──
def get_tencent_kline(symbol, period='day', count=500):
    """获取Tencent K线数据.
    symbol: sh510050, sz159915, sh000001
    period: day, week, month
    """
    import urllib.request
    if period == 'day':
        url = f'http://ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,{count},qfq'
    elif period == 'week':
        url = f'http://ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},week,,,{count},qfq'
    elif period == '60min':
        url = f'http://ifzq.gtimg.cn/appstock/app/kline/mkline?param={symbol},m60,,{count}'
    elif period == '5min':
        url = f'http://ifzq.gtimg.cn/appstock/app/kline/mkline?param={symbol},m5,,{count}'
    else:
        return None
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        return data
    except Exception as e:
        print(f"  API error for {symbol} {period}: {e}")
        return None


def parse_tencent_kline(raw, period='day'):
    """Parse Tencent K-line JSON to standard format."""
    ohlcv = []
    try:
        if period == 'day':
            # qfqday format: [[date, open, close, high, low, volume], ...]
            data_key = 'data'
            for k in raw.get('data', {}):
                kline = raw['data'][k].get('qfqday', raw['data'][k].get('day', []))
                for bar in kline:
                    if isinstance(bar, list) and len(bar) >= 6:
                        ohlcv.append({
                            'date': str(bar[0]),
                            'o': float(bar[1]),
                            'c': float(bar[2]),
                            'h': float(bar[3]),
                            'l': float(bar[4]),
                            'v': float(bar[5]),
                        })
        elif period == '60min':
            data_key = 'data'
            for k in raw.get('data', {}):
                kline = raw['data'][k].get('m60', [])
                for bar in kline:
                    if isinstance(bar, list) and len(bar) >= 6:
                        ohlcv.append({
                            'date': str(bar[0]),
                            'o': float(bar[1]),
                            'c': float(bar[2]),
                            'h': float(bar[3]),
                            'l': float(bar[4]),
                            'v': float(bar[5]),
                        })
    except Exception as e:
        print(f"  Parse error: {e}")
    
    return ohlcv


# ── Targets ──
TARGETS = [
    # ETFs
    ('510050.SH', 'sh510050', '50ETF'),
    ('510300.SH', 'sh510300', '300ETF'),
    ('510500.SH', 'sh510500', '500ETF'),
    ('588000.SH', 'sh588000', '科创50ETF'),
    ('159915.SZ', 'sz159915', '创业板ETF'),
    ('159845.SZ', 'sz159845', '中证1000ETF'),
    ('512100.SH', 'sh512100', '中证1000ETF'),
    ('510880.SH', 'sh510880', '红利ETF'),
    ('159949.SZ', 'sz159949', '创业板50ETF'),
    ('513100.SH', 'sh513100', '纳指ETF'),
    ('513050.SH', 'sh513050', '中概互联ETF'),
    ('518880.SH', 'sh518880', '黄金ETF'),
    # Indices
    ('000001.SH', 'sh000001', '上证指数'),
    ('399001.SZ', 'sz399001', '深证成指'),
    ('000300.SH', 'sh000300', '沪深300'),
    ('000016.SH', 'sh000016', '上证50'),
    ('399006.SZ', 'sz399006', '创业板指'),
    ('000688.SH', 'sh000688', '科创50'),
    ('399005.SZ', 'sz399005', '中小板指'),
]

CACHE = Path('/root/.hermes/kline_cache_etf')
CACHE.mkdir(exist_ok=True)


def load_or_fetch_tencent(symbol, tencent_code, period='day'):
    """Load from cache or fetch from Tencent API."""
    fname = f"{symbol.replace('.', '_')}_{period}.json"
    fpath = CACHE / fname
    if fpath.exists():
        data = json.loads(fpath.read_text())
        if len(data) >= 100:
            return data
    
    print(f"  Fetching {symbol} ({tencent_code}) {period}...")
    raw = get_tencent_kline(tencent_code, period)
    if not raw:
        return None
    
    ohlcv = parse_tencent_kline(raw, period)
    if not ohlcv or len(ohlcv) < 60:
        print(f"  {symbol}: Only {len(ohlcv) if ohlcv else 0} bars, skipping")
        return None
    
    fpath.write_text(json.dumps(ohlcv, ensure_ascii=False))
    print(f"  {symbol}: {len(ohlcv)} bars saved")
    return ohlcv


def detect_signals(ohlcv, symbol, label=''):
    """Run V11 signal detection on OHLCV data."""
    n = len(ohlcv)
    if n < 100:
        return None
    
    tree = StructureTree(ohlcv)
    wyckoff = detect_wyckoff_phases(ohlcv, tree)
    phase = wyckoff.get('primary_phase', 'unknown')
    
    params = {
        'fvg_min_consecutive': 2, 'sweep_lookback': 20,
        'max_fvg_gap_pct': 5.0, 'min_fvg_gap_pct': 0.15,
        'swing_window': 5, 'enable_bear': True,
    }
    
    result = detect_all_signals_v11(ohlcv, params=params, tf='daily')
    all_sigs = result.get('all', [])
    stats = result.get('stats', {})
    
    # Summary
    fvg_count = sum(1 for s in all_sigs if 'FVG' in s['type'] and 'Bear' in s['type'])
    fvg_bull = sum(1 for s in all_sigs if 'FVG_Bull' == s['type'])
    fvg_bear = sum(1 for s in all_sigs if 'FVG_Bear' == s['type'])
    ob_count = sum(1 for s in all_sigs if 'OB' in s['type'])
    ob_bull = sum(1 for s in all_sigs if 'OB_Bull' == s['type'])
    ob_bear = sum(1 for s in all_sigs if 'OB_Bear' == s['type'])
    sweep_count = sum(1 for s in all_sigs if 'Sweep' in s['type'])
    choch_count = sum(1 for s in all_sigs if 'CHOCH' in s['type'])
    
    # Last 60 bars signal summary
    recent_sigs = [s for s in all_sigs if s.get('idx', 0) >= n - 60]
    recent_fvg = sum(1 for s in recent_sigs if 'FVG' in s['type'] and 'Mitigated' not in s['type'])
    recent_ob = sum(1 for s in recent_sigs if 'OB' in s['type'])
    recent_sweep = sum(1 for s in recent_sigs if 'Sweep' in s['type'])
    recent_choch = sum(1 for s in recent_sigs if 'CHOCH' in s['type'])
    
    return {
        'symbol': symbol,
        'label': label,
        'n_bars': n,
        'phase': phase,
        'wyckoff_conf': wyckoff.get('confidence', 0),
        'total_signals': len(all_sigs),
        'signals': {
            'FVG': fvg_count, 'FVG_Bull': fvg_bull, 'FVG_Bear': fvg_bear,
            'OB': ob_count, 'OB_Bull': ob_bull, 'OB_Bear': ob_bear,
            'Sweep': sweep_count, 'CHOCH': choch_count,
        },
        'recent_60': {
            'FVG': recent_fvg, 'OB': recent_ob,
            'Sweep': recent_sweep, 'CHOCH': recent_choch,
        },
        'current_price': ohlcv[-1]['c'] if ohlcv else 0,
        'atr_pct': round((max(b['h'] for b in ohlcv[-20:]) - min(b['l'] for b in ohlcv[-20:])) / ohlcv[-1]['c'] * 100, 2) if ohlcv else 0,
        'trend_20d': round((ohlcv[-1]['c'] - ohlcv[-20]['c']) / ohlcv[-20]['c'] * 100, 2) if len(ohlcv) >= 20 else 0,
    }


def main():
    print("=" * 70)
    print("ETF/指数 V38.4 信号检测")
    print("=" * 70)
    print()
    
    all_results = []
    
    for symbol, tencent_code, label in TARGETS:
        print(f"\n{'─'*50}")
        print(f"{label} ({symbol})")
        print(f"{'─'*50}")
        
        # Fetch daily data
        ohlcv = load_or_fetch_tencent(symbol, tencent_code, 'day')
        if not ohlcv:
            print(f"  FAILED: No daily data")
            continue
        
        # Detect signals
        result = detect_signals(ohlcv, symbol, label)
        if result:
            all_results.append(result)
            print(f"  Signals: {result['total_signals']} total")
            print(f"  Recent 60d: FVG={result['recent_60']['FVG']}, OB={result['recent_60']['OB']}, "
                  f"Sweep={result['recent_60']['Sweep']}, CHOCH={result['recent_60']['CHOCH']}")
            print(f"  Phase: {result['phase']} (conf={result['wyckoff_conf']})")
            print(f"  Trend 20d: {result['trend_20d']:+.2f}%")
            print(f"  ATR%: {result['atr_pct']:.2f}%")
        
        # Also fetch 60min if daily succeeded
        if ohlcv and len(ohlcv) >= 100:
            ohlcv_60 = load_or_fetch_tencent(f"{symbol}_60min", tencent_code, '60min')
            if ohlcv_60 and len(ohlcv_60) >= 100:
                result_60 = detect_signals(ohlcv_60, f"{symbol}_60min", f"{label} 60min")
                if result_60:
                    print(f"  60min: {result_60['total_signals']} signals, {result_60['phase']}")
    
    print(f"\n{'='*70}")
    print(f"SUMMARY — {len(all_results)}/{len(TARGETS)} ETFs/Indices with data")
    print(f"{'='*70}")
    
    for r in sorted(all_results, key=lambda x: x['total_signals'], reverse=True):
        s = r['signals']
        r60 = r['recent_60']
        print(f"  {r['label']:16s} ({r['symbol']:10s}): "
              f"FVG={s['FVG']:3d} OB={s['OB']:3d} Sweep={s['Sweep']:3d} "
              f"CHOCH={s['CHOCH']:2d} | "
              f"Recent60: FVG={r60['FVG']:2d} OB={r60['OB']:2d} | "
              f"Phase={r['phase']:12s} | Trend={r['trend_20d']:+.1f}%")
    
    # Save to V38 results dir
    outpath = Path('/root/.hermes/smc_opt_v38') / 'v39_etf_signals.json'
    outpath.write_text(json.dumps(all_results, ensure_ascii=False, indent=1))
    print(f"\nSaved: {outpath}")


if __name__ == '__main__':
    main()
