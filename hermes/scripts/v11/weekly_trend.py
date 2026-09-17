"""
V11.4 周线趋势过滤模块 — 从日线合成周线数据
不需要外部API, 直接从日线缓存合成

审计修复(2026-09, 审计§6.2 P1):
  ① synthesize_weekly 改为按**自然周(ISO YYYY-WW)对齐**, 不再按固定5根分组;
     最后一段未完成周**显式丢弃**(不能把半周当作完整周)。
  ② weekly_trend 的权重顺序修正: recent 为时间升序(旧->新),
     权重 [0.3,...,0.1] 应**倒序应用**使近期权重最高(0.3给最新周)。
"""
import json, math
from datetime import date, datetime
from pathlib import Path


def _iso_week_key(datestr):
    """从日期字符串提取 (year, iso_week)。支持 'YYYY-MM-DD' / 'YYYYMMDD' / 'YYYY-MM-DD HH:MM'。"""
    s = str(datestr or '')
    s = s.split(' ')[0].replace('-', '')
    if len(s) >= 8:
        try:
            d = datetime(int(s[:4]), int(s[4:6]), int(s[6:8]))
            iso = d.isocalendar()
            return (iso[0], iso[1])
        except Exception:
            return None
    return None


def synthesize_weekly(daily_ohlcv, bars_per_week=5):
    """从日线合成周线OHLCV

    Args:
        daily_ohlcv: 日线数据(按时间顺序)
        bars_per_week: 5根日线=1周(A股5天交易) —— 仅作为每日期望根数参考,
                       实际分组按**自然周(ISO YYYY-WW)**对齐

    Returns:
        周线OHLCV列表 [{o,h,l,c,v,date}, ...]
    """
    # 按自然周分组: {(year, week): [bars...]}
    weeks = {}
    order = []
    for bar in daily_ohlcv:
        key = _iso_week_key(bar.get('date') or bar.get('t'))
        if key is None:
            continue
        if key not in weeks:
            weeks[key] = []
            order.append(key)
        weeks[key].append(bar)

    weekly = []
    for key in order:
        chunk = weeks[key]
        # 未完成周: 最后一段不足 bars_per_week 根则**丢弃**(不能把半周当完整周)
        if len(chunk) < bars_per_week:
            continue
        week = {
            'o': chunk[0]['o'],
            'h': max(b.get('h', 0) for b in chunk),
            'l': min(b.get('l', 1e9) for b in chunk),
            'c': chunk[-1]['c'],
            'v': sum(b.get('v', b.get('vol', 0)) for b in chunk),
            'date': chunk[0].get('date', "week_%d_%d" % key),
        }
        weekly.append(week)
    return weekly


def weekly_trend(weekly_ohlcv, lookback=5):
    """计算周线趋势方向

    Args:
        weekly_ohlcv: 周线数据(时间升序)
        lookback: 检查最近N根周线

    Returns:
        'up' / 'down' / 'neutral'
    """
    if len(weekly_ohlcv) < lookback + 2:
        return 'neutral'

    recent = weekly_ohlcv[-lookback:]

    # 周线趋势: 最近lookback根周线的收盘变化
    start_c = recent[0]['c']
    end_c = recent[-1]['c']
    change_pct = (end_c - start_c) / start_c * 100

    # EMA趋势 —— 审计修复: recent 为时间升序(旧->新), 权重必须**倒序**
    # 应用使近期权重最高(0.3 给最新周)。原实现 0.3 给了最旧周, 与注释意图相反。
    weights = [0.3, 0.25, 0.2, 0.15, 0.1][:min(len(recent), 5)]
    weights = list(reversed(weights))  # 倒序: 最新周得最大权重
    total_w = sum(weights)
    ema = sum(r['c'] * w for r, w in zip(recent, weights)) / total_w
    ema_dist = (end_c - ema) / ema * 100

    # 连续收阳/收阴
    green_count = sum(1 for r in recent if r['c'] > r['o'])
    red_count = lookback - green_count

    if change_pct > 2 and ema_dist > -0.5 and green_count >= lookback * 0.6:
        return 'up'
    elif change_pct < -2 and ema_dist < 0.5 and red_count >= lookback * 0.6:
        return 'down'
    return 'neutral'


def weekly_volatility(weekly_ohlcv, lookback=5):
    """周线波动率(ATR百分比)"""
    if len(weekly_ohlcv) < lookback + 1:
        return 3.0  # 默认3%
    
    tr_sum = 0
    for i in range(-lookback, 0):
        h = weekly_ohlcv[i]['h']
        l = weekly_ohlcv[i]['l']
        pc = weekly_ohlcv[i-1]['c']
        tr = max(h - l, abs(h - pc), abs(l - pc))
        tr_pct = tr / pc * 100
        tr_sum += tr_pct
    
    return tr_sum / lookback


def weekly_daily_alignment(weekly_ohlcv, daily_ohlcv, end_idx, lookback=5):
    """检查周线和日线趋势是否对齐
    
    核心: 当周线趋势与日线交易方向一致时, 胜率最高
    """
    weekly = synthesize_weekly(daily_ohlcv[:end_idx+1])
    if len(weekly) < 2:
        return 'neutral', 0.0
    
    wt = weekly_trend(weekly, lookback=min(lookback, len(weekly)))
    wv = weekly_volatility(weekly, lookback=min(lookback, len(weekly)))
    
    return wt, wv


# 测试
if __name__ == '__main__':
    # 单只股票测试
    CACHE_DIR = Path('/root/.hermes/kline_cache')
    test_files = [
        '000001.SZ', '000036.SZ', '600519.SH',
    ]
    
    for sym in test_files:
        fname = f"{sym.replace('.', '_')}_daily_300.json"
        fpath = CACHE_DIR / fname
        if not fpath.exists():
            print(f"{sym}: no cache")
            continue
        
        daily = json.loads(fpath.read_text())
        weekly = synthesize_weekly(daily)
        if len(weekly) < 2:
            print(f"{sym}: not enough weekly bars ({len(weekly)})")
            continue
        
        trend = weekly_trend(weekly)
        vol = weekly_volatility(weekly)
        
        print(f"{sym:12s} weekly_bars={len(weekly):3d} trend={trend:8s} vol={vol:.1f}%")
        # 最后3根周线
        for w in weekly[-3:]:
            print(f"    o={w['o']:.2f} h={w['h']:.2f} l={w['l']:.2f} c={w['c']:.2f} v={w['v']:.0f}")
