#!/usr/bin/env python3
# SMC V9 — 全市场选股 + 实时监测引擎
"""
全市场扫描引擎：覆盖A股(5400+)、ETF、行业板块、指数的信号扫描。
实时监测面板：选股列表、价格偏离监控、信号理由记录。

主要函数:
    scan_all_markets()  →  全市场信号扫描
    build_watchlist()   →  构建监测组
    check_deviations()  →  检查价格偏离度
"""

import json, time, logging, urllib.request, urllib.error
from datetime import datetime
from collections import defaultdict

log = logging.getLogger('smc_v9.watchlist')

# Hubble API 配置
HUBBLE_BASE = 'http://43.167.234.49:3101'
HUBBLE_HEADERS = {'X-API-Key': '123456', 'Content-Type': 'application/json'}

# ─── 信号检测引用 ─────────────────────────────────────────────────
from v9.smc_hubble import fetch_kline, kline_to_ohlcv, calc_atr_pct
from v9.smc_signals import detect_all_signals, score_signal, signal_summary


# ═══════════════════════════════════════════════════════════════════════
# 通用 Hubble 请求工具
# ═══════════════════════════════════════════════════════════════════════

def _hubble_get(endpoint, params=None, timeout=10):
    """Hubble API GET 请求。"""
    try:
        url = f"{HUBBLE_BASE}{endpoint}"
        if params:
            qs = '&'.join(f'{k}={v}' for k, v in params.items())
            url = f"{url}?{qs}"
        req = urllib.request.Request(url, headers=HUBBLE_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        log.warning(f"Hubble GET {endpoint}: {e}")
        return None


def _hubble_post(endpoint, body, timeout=15):
    """Hubble API POST 请求。"""
    try:
        req = urllib.request.Request(
            f"{HUBBLE_BASE}{endpoint}",
            data=json.dumps(body).encode(),
            headers=HUBBLE_HEADERS,
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        log.warning(f"Hubble POST {endpoint}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════
# PART 1: 股票/ETF/指数/板块 列表加载
# ═══════════════════════════════════════════════════════════════════════

def load_cnstock_list(limit=6000):
    """从Hubble加载全部A股列表。
    
    返回: [{'symbol':'600519.SH', 'name':'贵州茅台', 'area', 'industry', 'market'}, ...]
    """
    raw = _hubble_get('/api/v2/cnstock/symbols', {'listStatus': 'L'})
    if not raw:
        log.error("Failed to load A-stock list from Hubble")
        return []

    data = raw.get('data', raw) if isinstance(raw, dict) else raw
    if not isinstance(data, list):
        log.warning(f"Unexpected stock list format: {type(data)}")
        return []

    # 提取数据
    stocks = []
    for item in data:
        if isinstance(item, dict):
            ts = item.get('ts_code', '')
            name = item.get('name', '')
            if ts and name:
                # ts_code 格式: 600519.SH
                symbol = ts if '.' in ts else f"{ts}.SH"
                stocks.append({
                    'symbol': symbol,
                    'name': name,
                    'area': item.get('area', ''),
                    'industry': item.get('industry', ''),
                    'market': item.get('market', '主板'),
                })

    log.info(f"Loaded {len(stocks)} A-stock symbols")
    return stocks[:limit]


def load_etf_list(limit=2000):
    """从Hubble加载ETF列表。

    返回: [{'symbol':'510050.SH', 'name':'上证50ETF'}, ...]
    """
    raw = _hubble_get('/api/v2/fund/etf-basic', {'market': 'E', 'limit': limit})
    if not raw:
        log.warning("Failed to load ETF list")
        return []

    data = raw.get('data', raw) if isinstance(raw, dict) else raw
    if not isinstance(data, list):
        return []

    etfs = []
    for item in data:
        if isinstance(item, dict):
            ts = item.get('ts_code', '')
            name = item.get('name', '')
            if ts and name:
                symbol = ts if '.' in ts else f"{ts}.SH"
                etfs.append({
                    'symbol': symbol,
                    'name': name,
                })

    log.info(f"Loaded {len(etfs)} ETFs")
    return etfs


def load_index_list(limit=50):
    """加载主要指数列表。

    返回: [{'symbol':'000001.SH', 'name':'上证指数'}, ...]
    """
    raw = _hubble_get('/api/v2/cnstock/index/basic', {'market': 'MSCI'})
    if not raw:
        log.warning("Failed to load index list")
        return []

    data = raw.get('data', raw) if isinstance(raw, dict) else raw
    if not isinstance(data, list):
        return []

    indices = []
    for item in data[:limit]:
        if isinstance(item, dict):
            ts = item.get('ts_code', '')
            name = item.get('name', '')
            if ts and name:
                indices.append({
                    'symbol': ts if '.' in ts else f"{ts}.SH",
                    'name': name,
                })

    # 确保至少包含核心指数
    core = [
        {'symbol': '000001.SH', 'name': '上证指数'},
        {'symbol': '399001.SZ', 'name': '深证成指'},
        {'symbol': '000300.SH', 'name': '沪深300'},
        {'symbol': '000016.SH', 'name': '上证50'},
        {'symbol': '000688.SH', 'name': '科创50'},
        {'symbol': '399006.SZ', 'name': '创业板指'},
        {'symbol': '000852.SH', 'name': '中证1000'},
    ]
    seen = {i['symbol'] for i in indices}
    for c in core:
        if c['symbol'] not in seen:
            indices.append(c)

    log.info(f"Loaded {len(indices)} indices")
    return indices


def load_sector_list(limit=100):
    """加载申万行业板块列表。

    返回: [{'symbol':'sw_xxx', 'name':'银行'}, ...]
    (实际上板块没有独立K线，需要由ETF或指数来获取)
    """
    raw = _hubble_get('/api/v2/cnstock/index/classify', {'src': 'sw', 'limit': limit})
    if not raw:
        log.warning("Failed to load sector list")
        return []

    data = raw.get('data', raw) if isinstance(raw, dict) else raw
    if not isinstance(data, list):
        return []

    sectors = []
    for item in data:
        if isinstance(item, dict):
            idx = item.get('index_code', '')
            name = item.get('industry_name', item.get('name', ''))
            if idx and name:
                sectors.append({
                    'symbol': idx if '.' in idx else f"{idx}.SH",
                    'name': name,
                })

    log.info(f"Loaded {len(sectors)} sectors")
    return sectors[:limit]


# ═══════════════════════════════════════════════════════════════════════
# PART 2: 全市场信号扫描
# ═══════════════════════════════════════════════════════════════════════

def _scan_symbol(symbol, period='daily', count=200, params=None):
    """单只股票信号扫描(带错误处理)。"""
    try:
        ohlcv, atr_pct, n = kline_to_ohlcv(fetch_kline(symbol, period, count)), 0, 0
        raw = fetch_kline(symbol, period, count)
        if not raw or len(raw) < 30:
            return None

        ohlcv = kline_to_ohlcv(raw)
        atr_pct = calc_atr_pct(ohlcv)

        if not params:
            from v9.smc_config import get_param_space
            pspace = get_param_space()
            params = {k: pdef['default'] for k, pdef in pspace.items()}

        signals = detect_all_signals(ohlcv, params)
        if not signals:
            return None

        scored = [(score_signal(s, ohlcv), s) for s in signals]
        top_sc, top_sig = scored[0] if scored else (0, None)

        counts, dirs = signal_summary(signals)
        current_price = ohlcv[-1]['c']

        return {
            'symbol': symbol,
            'price': current_price,
            'atr_pct': round(atr_pct, 2),
            'bars': len(ohlcv),
            'signal_count': len(signals),
            'top_score': round(top_sc, 1),
            'top_signal': top_sig['type'] if top_sig else '',
            'top_idx': top_sig.get('idx', 0) if top_sig else 0,
            'top_direction': top_sig.get('direction', '') if top_sig else '',
            'summary': counts,
            'directions': dirs,
            'signals': [
                {'score': round(sc, 1), **sig}
                for sc, sig in scored[:15]
            ],
        }
    except Exception as e:
        log.debug(f"scan {symbol}: {e}")
        return None


def scan_all_markets(limit_stocks=100, limit_etfs=30, limit_indices=20, limit_sectors=20, callback=None):
    """全市场信号扫描。

    依次扫描A股、ETF、指数、板块。通过callback报告进度。

    Returns:
        {'stocks': [...], 'etfs': [...], 'indices': [...], 'sectors': [...], 
         'summary': {...}, 'timestamp': '...'}
    """
    total_planned = limit_stocks + limit_etfs + limit_indices + limit_sectors
    completed = 0

    def _progress(market, symbol, status):
        nonlocal completed
        completed += 1
        if callback:
            callback({
                'market': market, 'symbol': symbol,
                'status': status, 'progress': completed,
                'total': total_planned,
            })

    # 加载列表
    stocks_list = load_cnstock_list(limit_stocks)
    etf_list = load_etf_list(limit_etfs) if limit_etfs > 0 else []
    index_list = load_index_list(limit_indices) if limit_indices > 0 else []
    sector_list = load_sector_list(limit_sectors) if limit_sectors > 0 else []

    params = None

    # 扫描A股
    stock_results = []
    for item in stocks_list:
        symbol = item['symbol']
        name = item.get('name', '')
        r = _scan_symbol(symbol)
        if r:
            r['name'] = name
            stock_results.append(r)
        _progress('A股', symbol, 'ok' if r else 'skip')

    # 扫描ETF
    etf_results = []
    for item in etf_list:
        symbol = item['symbol']
        name = item.get('name', '')
        r = _scan_symbol(symbol)
        if r:
            r['name'] = name
            etf_results.append(r)
        _progress('ETF', symbol, 'ok' if r else 'skip')

    # 扫描指数
    index_results = []
    for item in index_list:
        symbol = item['symbol']
        name = item.get('name', '')
        r = _scan_symbol(symbol)
        if r:
            r['name'] = name
            index_results.append(r)
        _progress('指数', symbol, 'ok' if r else 'skip')

    # 扫描板块 (用板块指数ETF)
    sector_results = []
    for item in sector_list:
        symbol = item['symbol']
        name = item.get('name', '')
        r = _scan_symbol(symbol)
        if r:
            r['name'] = name
            sector_results.append(r)
        _progress('板块', symbol, 'ok' if r else 'skip')

    # 按top_score排序
    stock_results.sort(key=lambda x: -x['top_score'])
    etf_results.sort(key=lambda x: -x['top_score'])
    index_results.sort(key=lambda x: -x['top_score'])
    sector_results.sort(key=lambda x: -x['top_score'])

    # 汇总统计
    summary = {
        'stocks_scanned': len(stocks_list),
        'stocks_signaled': len(stock_results),
        'etfs_scanned': len(etf_list),
        'etfs_signaled': len(etf_results),
        'indices_scanned': len(index_list),
        'indices_signaled': len(index_results),
        'sectors_scanned': len(sector_list),
        'sectors_signaled': len(sector_results),
    }

    return {
        'stocks': stock_results,
        'etfs': etf_results,
        'indices': index_results,
        'sectors': sector_results,
        'summary': summary,
        'timestamp': datetime.now().isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════
# PART 3: Hubble 选股筛选 (screener)
# ═══════════════════════════════════════════════════════════════════════

def run_screen(conditions, page=1, limit=50):
    """使用Hubble A股选股筛选器。

    conditions: [{'field':'pe_ttm', 'op':'lte', 'value':20}, ...]
    op: lte/gte/eq/neq/btw (between)/in/like

    返回: [{'ts_code','name','pe_ttm','market_cap',...}, ...]
    """
    result = _hubble_post('/api/v2/stock/cnstock/screener', {
        'conditions': conditions,
        'page': page,
        'limit': limit,
    })
    if not result:
        log.warning("Screener returned no data")
        return []

    data = result.get('data', result)
    if isinstance(data, dict):
        items = data.get('list', data.get('items', []))
    elif isinstance(data, list):
        items = data
    else:
        items = []

    log.info(f"Screener returned {len(items)} results")
    return items


def run_smc_screen():
    """SMC专属选股筛选条件: 高换手+放量+Hubble可筛选的条件."""
    return run_screen([
        {'field': 'turnover_rate', 'op': 'gte', 'value': 1.0},
        {'field': 'volume_ratio', 'op': 'gte', 'value': 1.2},
        {'field': 'limit_status', 'op': 'in', 'value': ['', 'normal']},
    ], limit=100)


# ═══════════════════════════════════════════════════════════════════════
# PART 4: 选股监测 (Watchlist)
# ═══════════════════════════════════════════════════════════════════════

def build_watch_item(symbol, name, scan_result):
    """从扫描结果构建watchlist item。

    Args:
        symbol: 股票代码
        name: 股票名称
        scan_result: scan_symbol() 的输出

    Returns:
        {'symbol','name','price','signal_price','signal_date',
         'signal_type','signal_reason','signal_strength','deviation_pct',
         'atr','update_time'}
    """
    if not scan_result:
        return None

    price = scan_result.get('price', 0)
    signals = scan_result.get('signals', [])
    top_sig = signals[0] if signals else {}

    # 信号位置(价格)
    signal_price = top_sig.get('entry', top_sig.get('price',
                    top_sig.get('upper', top_sig.get('lower', price))))

    # 偏离度
    if price > 0 and signal_price > 0:
        deviation_pct = round((price - signal_price) / signal_price * 100, 2)
    else:
        deviation_pct = 0

    # 选股理由
    sig_type = top_sig.get('type', scan_result.get('top_signal', ''))
    sig_dir = top_sig.get('direction', scan_result.get('top_direction', ''))
    sig_idx = top_sig.get('idx', scan_result.get('top_idx', 0))
    sig_score = top_sig.get('score', scan_result.get('top_score', 0))

    if sig_type and sig_dir:
        reason_ch = {
            ('FVG', 'bull'): 'FVG买方缺口, 价格未回补',
            ('FVG', 'bear'): 'FVG卖方缺口, 价格未回补',
            ('OB_Bull', 'bull'): '机构订单块(买方)',
            ('OB_Bear', 'bear'): '机构订单块(卖方)',
            ('SweepDown', 'bull'): '流动性扫荡(下方), 空头陷阱',
            ('SweepUp', 'bear'): '流动性扫荡(上方), 多头陷阱',
            ('BPR_Bull', 'bull'): '平衡区突破(买方), 需求释放',
            ('BPR_Bear', 'bear'): '平衡区突破(卖方), 供应释放',
            ('MSB_Up', 'bull'): '市场结构向上突破',
            ('MSB_Down', 'bear'): '市场结构向下突破',
        }
        reason = reason_ch.get((sig_type, sig_dir), f'{sig_type}@{sig_idx} 信号')
        signal_reason = f'{name} {sig_dir}({sig_type}) {reason[:60]}'
    else:
        signal_reason = f'{name} SMC信号 得分{sig_score}'

    # 构建item
    return {
        'symbol': symbol,
        'name': name,
        'price': price,
        'signal_price': round(float(signal_price), 2) if signal_price else price,
        'signal_date': datetime.now().strftime('%Y-%m-%d'),
        'signal_type': sig_type,
        'signal_direction': sig_dir,
        'signal_score': sig_score,
        'signal_reason': signal_reason,
        'signal_idx': sig_idx,
        'deviation_pct': deviation_pct,
        'atr': scan_result.get('atr_pct', 0),
        'total_signals': scan_result.get('signal_count', 0),
        'price': price,
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }


def build_watchlist(market_results, min_score=2.0):
    """从全市场扫描结果构建Watchlist。

    Args:
        market_results: scan_all_markets() 的输出
        min_score: 最低信号评分门槛

    Returns:
        {'items': [...], 'summary': {...}}
    """
    items = []

    # A股
    for r in market_results.get('stocks', []):
        if r.get('top_score', 0) >= min_score:
            w = build_watch_item(r['symbol'], r.get('name', r['symbol']), r)
            if w:
                w['market'] = 'A股'
                items.append(w)

    # ETF
    for r in market_results.get('etfs', []):
        if r.get('top_score', 0) >= min_score:
            w = build_watch_item(r['symbol'], r.get('name', r['symbol']), r)
            if w:
                w['market'] = 'ETF'
                items.append(w)

    # 指数
    for r in market_results.get('indices', []):
        if r.get('top_score', 0) >= min_score:
            w = build_watch_item(r['symbol'], r.get('name', r['symbol']), r)
            if w:
                w['market'] = '指数'
                items.append(w)

    # 板块
    for r in market_results.get('sectors', []):
        if r.get('top_score', 0) >= min_score:
            w = build_watch_item(r['symbol'], r.get('name', r['symbol']), r)
            if w:
                w['market'] = '板块'
                items.append(w)

    # 按得分排序
    items.sort(key=lambda x: -x.get('signal_score', 0))

    # 统计
    summary = {
        'total': len(items),
        'by_market': dict(_count_by(items, 'market')),
        'by_direction': dict(_count_by(items, 'signal_direction')),
        'high_risk': len([i for i in items if abs(i.get('deviation_pct', 0)) > 5]),
        'avg_score': round(sum(i.get('signal_score', 0) for i in items) / max(len(items), 1), 1),
    }

    return {'items': items, 'summary': summary}


def _count_by(items, field):
    """按 field 计数。"""
    counts = defaultdict(int)
    for item in items:
        counts[item.get(field, '?')] += 1
    return counts


# ═══════════════════════════════════════════════════════════════════════
# PART 5: 偏离度检查
# ═══════════════════════════════════════════════════════════════════════

def check_deviations(watchlist_items, threshold_high=5.0, threshold_mod=3.0):
    """检查所有watchlist项的偏离度。

    Returns:
        {
            'normal': [...],   # 偏离 < threshold_mod
            'moderate': [...], # threshold_mod <= 偏离 < threshold_high
            'high_risk': [...],# 偏离 >= threshold_high
            'total': N,
        }
    """
    normal = []
    moderate = []
    high_risk = []

    for item in watchlist_items:
        deviation = abs(item.get('deviation_pct', 0))
        if deviation >= threshold_high:
            item['deviation_level'] = 'high_risk'
            high_risk.append(item)
        elif deviation >= threshold_mod:
            item['deviation_level'] = 'moderate'
            moderate.append(item)
        else:
            item['deviation_level'] = 'normal'
            normal.append(item)

    return {
        'normal': normal,
        'moderate': moderate,
        'high_risk': high_risk,
        'total': len(watchlist_items),
        'check_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }


def scan_and_build_watchlist(limit_stocks=100, limit_etfs=30, limit_indices=20,
                              limit_sectors=20, min_score=2.0, callback=None):
    """一键: 扫描全市场 → 构建Watchlist → 检查偏离。

    Returns:
        {'market_results': {...}, 'watchlist': {...}, 'deviations': {...}}
    """
    log.info(f"Scanning: stocks={limit_stocks} etfs={limit_etfs} "
             f"indices={limit_indices} sectors={limit_sectors}")

    # 阶段1: 全市场扫描
    t0 = time.time()
    market = scan_all_markets(
        limit_stocks=limit_stocks,
        limit_etfs=limit_etfs,
        limit_indices=limit_indices,
        limit_sectors=limit_sectors,
        callback=callback,
    )
    scan_time = time.time() - t0

    # 阶段2: 构建Watchlist
    watchlist = build_watchlist(market, min_score=min_score)

    # 阶段3: 偏离度检查
    deviations = check_deviations(watchlist.get('items', []))

    return {
        'market_results': market,
        'watchlist': watchlist,
        'deviations': deviations,
        'scan_time_sec': round(scan_time, 1),
    }


# ═══════════════════════════════════════════════════════════════════════
# 快捷测试
# ═══════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print("=== SMC Watchlist Module ===")
    print(f"Functions: {[n for n in dir() if n.startswith(('load_', 'scan_', 'build_', 'check_', 'run_', '_'))]}")
    
    # Quick test: load lists
    stocks = load_cnstock_list(5)
    print(f"\nA股 sample: {json.dumps(stocks[:2], indent=2, ensure_ascii=False)}")
    
    etfs = load_etf_list(5)
    print(f"ETF sample: {json.dumps(etfs[:2], indent=2, ensure_ascii=False)}")