#!/usr/bin/env python3
"""
SMC 信号验证器 — 对单个信号进行5维验证

用法:
  python3 scripts/smc_verify.py --market us --symbol AAPL --direction long --timeframe 1d
  python3 scripts/smc_verify.py --market crypto --symbol BTCUSDT --direction short --exchange binance
"""

import json, sys, math, urllib.request, argparse
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent / 'smc-signal-scanner' / 'scripts'))
from smc_scanner import fetch_data, normalize_klines, detect_fvg, detect_liquidity_sweep, detect_market_structure, detect_order_blocks

BASE = "http://43.167.234.49:3101"
HEADERS = {"X-API-Key": "123456", "Content-Type": "application/json"}


def verify_signal(market, symbol, direction, timeframe='1d', exchange='binance'):
    print(f"\n{'═'*60}")
    print(f"  SMC 信号验证 | {symbol} | {direction.upper()} | {timeframe}")
    print(f"{'═'*60}\n")

    # 获取多TF数据
    tf_map = {'1w': 'weekly', '1d': 'daily', '4h': '60min', '1h': '30min', '15min': '15min'}
    tf_api = {'1w': 'weekly', '1d': 'daily', '4h': '4h', '1h': '1h', '15min': '15m'}

    tf_data = {}
    for tf in ['1d', '4h', '1h']:
        try:
            raw = fetch_data(market, symbol, tf_api.get(tf, tf), 200, exchange)
            tf_data[tf] = normalize_klines(raw, market)
        except:
            pass

    current_price = tf_data.get('1d', [{}])[-1].get('c', 0) if tf_data.get('1d') else 0
    scores = {}
    total = 0

    # ─── ① 趋势一致性 (30分) ─────────────────────
    print("① 趋势一致性 [____/30]")
    trend_score = 0
    daily = tf_data.get('1d', [])
    if daily and len(daily) > 20:
        daily_struct = detect_market_structure(daily, 20)
        trend_ok = daily_struct.get('direction') == direction
        if trend_ok:
            trend_score += 15
            print(f"  ✓ Daily趋势一致 (+15)")
        else:
            print(f"  ✗ Daily趋势不一致 (Daily方向: {daily_struct.get('direction')})")

        # CHOCH 检查
        if daily_struct.get('choch'):
            trend_score += 7
            print(f"  ✓ CHOCH已确认: {daily_struct['choch_type']} (+7)")
        else:
            print(f"  ✗ 无CHOCH")

        # 折扣区检查 (简化: 用最近 swing 的 0.618-0.79)
        swing_high = max(k['h'] for k in daily[-30:])
        swing_low = min(k['l'] for k in daily[-30:])
        discount_top = swing_low + (swing_high - swing_low) * 0.618
        discount_bot = swing_low + (swing_high - swing_low) * 0.79
        in_discount = discount_bot <= current_price <= discount_top
        if in_discount:
            trend_score += 8
            print(f"  ✓ 在折扣区 {discount_bot:.2f}-{discount_top:.2f} (+8)")
        else:
            print(f"  ✗ 不在折扣区 (折扣区: {discount_bot:.2f}-{discount_top:.2f})")
    total += trend_score
    scores['trend'] = trend_score
    print(f"  小计: {trend_score}/30\n")

    # ─── ② 流动性检查 (20分) ─────────────────────
    print("② 流动性检查 [____/20]")
    liq_score = 0
    daily = tf_data.get('1d', [])
    if daily:
        sweep = detect_liquidity_sweep(daily, 15)
        recent_sweep = [s for s in sweep if s['index'] > len(daily) - 5]
        if recent_sweep:
            last = recent_sweep[-1]
            is_correct_direction = (last['direction'] == direction)
            if is_correct_direction:
                liq_score += 10
                print(f"  ✓ 有流动性猎杀: {last['type']} (+10)")
                if last['wick_ratio'] >= 2.0:
                    liq_score += 5
                    print(f"  ✓ 影线比 {last['wick_ratio']} ≥ 2.0 (+5)")
                else:
                    print(f"  △ 影线比 {last['wick_ratio']} < 2.0")
            else:
                print(f"  ✗ Sweep方向 ({last['type']}) ≠ 信号方向 ({direction})")
        else:
            print(f"  ✗ 无最近的流动性猎杀")

        # 上方无未触流动性
        highs = [k['h'] for k in daily[-10:]]
        lows = [k['l'] for k in daily[-10:]]
        if max(highs) == highs[-1] or min(lows) == lows[-1]:
            liq_score += 5
            print(f"  ✓ 最新K线已测试高/低 (+5)")
        else:
            print(f"  △ 上方有更高的高点/更低的低点未触及")
    total += liq_score
    scores['liquidity'] = liq_score
    print(f"  小计: {liq_score}/20\n")

    # ─── ③ 价格区域验证 (25分) ───────────────────
    print("③ 价格区域 [____/25]")
    zone_score = 0
    if daily:
        fvg = detect_fvg(daily)
        recent_fvg = [f for f in fvg if f['index'] > len(daily) - 10]
        if recent_fvg:
            best = max(recent_fvg, key=lambda x: x['strength'])
            # 检查价格是否尚未进入FVG (Unmitigated)
            if direction == 'long' and current_price < best['top'] and current_price > best['bottom']:
                zone_score += 10
                print(f"  ✓ FVG {best['type']} ({best['bottom']:.2f}-{best['top']:.2f}) 未填补 (+10)")
            elif direction == 'short' and current_price < best['top'] and current_price > best['bottom']:
                zone_score += 10
                print(f"  ✓ FVG {best['type']} ({best['bottom']:.2f}-{best['top']:.2f}) 未填补 (+10)")
            else:
                print(f"  △ FVG在 {best['bottom']:.2f}-{best['top']:.2f}, 当前价格 {current_price:.2f}")

            if best['strength'] >= 2:
                zone_score += 5
                print(f"  ✓ FVG强度 {best['strength']} ≥ 2 (+5)")

        ob = detect_order_blocks(daily)
        recent_ob = [o for o in ob if o['index'] > len(daily) - 10]
        if recent_ob and recent_ob[-1]['direction'] == direction:
            zone_score += 5
            print(f"  ✓ 附近有OB ({recent_ob[-1]['bottom']:.2f}-{recent_ob[-1]['top']:.2f}) (+5)")

        # OTE折扣区检查
        swing_high = max(k['h'] for k in daily[-30:])
        swing_low = min(k['l'] for k in daily[-30:])
        discount_top = swing_low + (swing_high - swing_low) * 0.618
        discount_bot = swing_low + (swing_high - swing_low) * 0.79
        premium_top = swing_high - (swing_high - swing_low) * 0.382
        premium_bot = swing_high - (swing_high - swing_low) * 0.618
        if direction == 'long' and discount_bot <= current_price <= discount_top:
            zone_score += 5
            print(f"  ✓ 在折扣区 (OTE 0.618-0.79) (+5)")
        elif direction == 'short' and premium_top >= current_price >= premium_bot:
            zone_score += 5
            print(f"  ✓ 在溢价区 (OTE 0.618-0.79) (+5)")
    total += zone_score
    scores['zone'] = zone_score
    print(f"  小计: {zone_score}/25\n")

    # ─── ④ 时间验证 (10分) ───────────────────────
    print("④ 时间检查 [____/10]")
    time_score = 0
    import datetime
    from datetime import timezone

    now = datetime.datetime.now(timezone.utc)
    et_now = now - datetime.timedelta(hours=4)  # 美东夏令时估算

    # 美东时间Killzone检查
    h = et_now.hour
    m = et_now.minute
    killzones = []
    if 7 <= h < 10 or (h == 10 and m < 30):
        killzones.append("NY AM Open")
    if (h == 9 and m >= 30) or (h == 10):
        killzones.append("Silver Bullet")
    if 13 <= h < 16:
        killzones.append("Afternoon/NY Close")
    if 2 <= h < 5:
        killzones.append("London Open")
    if 20 <= h or h < 1:
        killzones.append("Asian Killzone")

    if killzones:
        time_score += 6
        print(f"  ✓ 当前在Killzone: {', '.join(killzones)} (+6)")
    else:
        print(f"  ✗ 不在Killzone内")

    # 周末检查
    if now.weekday() >= 5:
        print(f"  ⚠ 周末 (市场关闭或低流动性)")
    total += time_score
    scores['time'] = time_score
    print(f"  小计: {time_score}/10\n")

    # ─── ⑤ 多TF对齐 (15分) ───────────────────────
    print("⑤ 多时间框架对齐 [____/15]")
    mtf_score = 0

    for tf in ['1d', '4h']:
        data = tf_data.get(tf, [])
        if not data or len(data) < 20:
            continue
        struct = detect_market_structure(data, 15)
        if struct.get('direction') == direction:
            mtf_score += 5 if tf == '1d' else 4
            print(f"  ✓ {tf} 方向一致 ({struct['trend']}) (+{5 if tf == '1d' else 4})")
        elif struct.get('choch'):
            mtf_score += 3
            print(f"  △ {tf} 正在结构转换中 ({struct.get('choch_type')}) (+3)")
        else:
            print(f"  ✗ {tf} 方向不一致 ({struct.get('direction')})")

    if mtf_score >= 9:
        mtf_score += 1  # 额外加分

    total += mtf_score
    scores['mtf'] = mtf_score
    print(f"  小计: {mtf_score}/15\n")

    # ─── 综合评分 ────────────────────────────────
    grade = 'S' if total >= 90 else 'A+' if total >= 80 else 'A' if total >= 70 else 'B+' if total >= 60 else 'B' if total >= 50 else 'C+' if total >= 40 else 'C' if total >= 30 else 'D'

    verdict = '🚀 全力入场' if total >= 80 else \
              '✅ 入场' if total >= 70 else \
              '👀 等待更佳入场点（等确认K线或更深的回撤）' if total >= 55 else \
              '⏸ 观望' if total >= 40 else \
              '❌ 放弃'

    print(f"{'═'*60}")
    print(f"  综合评分: {total}/100 → {grade}级")
    print(f"  建议: {verdict}")
    print(f"{'═'*60}")
    print(f"\n  得分明细:")
    print(f"    趋势一致性: {scores.get('trend', 0)}/30")
    print(f"    流动性检查: {scores.get('liquidity', 0)}/20")
    print(f"    价格区域:   {scores.get('zone', 0)}/25")
    print(f"    时间检查:   {scores.get('time', 0)}/10")
    print(f"    多TF对齐:   {scores.get('mtf', 0)}/15")
    print(f"{'═'*60}\n")


def main():
    parser = argparse.ArgumentParser(description='SMC 信号验证器')
    parser.add_argument('--market', choices=['cn', 'hk', 'us', 'crypto'], default='us')
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--direction', choices=['long', 'short'], default='long')
    parser.add_argument('--timeframe', default='1d')
    parser.add_argument('--exchange', default='binance')
    args = parser.parse_args()

    verify_signal(args.market, args.symbol, args.direction, args.timeframe, args.exchange)


if __name__ == '__main__':
    main()