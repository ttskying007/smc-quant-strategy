"""T+1修正版trailing函数 — 替换calc_v38_trailing"""
from pathlib import Path
import re

engine_path = Path('/root/.hermes/scripts/v11/v477_engine.py')
content = engine_path.read_text()

# Find where calc_v38_trailing starts
old_func_start = """def calc_v38_trailing(ohlcv, entry_idx, entry_price, initial_sl,
                       structural_tp, n, max_hold, direction,
                       be_lock=2.0, look_lock=4.0):
    \"\"\"
    V465 60min trailing — 5x宽松阈值, 允许多K线持仓
    3-profile: loose (bull+tp), bear (bear+tp), tight (noTP)
    60min: be_lock~2%, look_lock~4% (from stock_params)
    \"\"\"
    sl = initial_sl
    extreme = entry_price
    tp_price = structural_tp[0] if structural_tp and structural_tp[0] else None
    tp_pct = structural_tp[2] if structural_tp and structural_tp[2] else None

    is_bear = (direction == 'bear')
    has_tp = tp_price is not None

    if not has_tp:
        profile = 'tight'
    elif is_bear:
        profile = 'bear'
    else:
        profile = 'loose'

    be_gain = be_lock
    lk_gain = look_lock

    for j in range(entry_idx + 1, min(entry_idx + max_hold + 1, n)):
        bar = ohlcv[j]

        if is_bear:
            if bar['l'] < extreme:
                extreme = bar['l']
            gain_pct = (entry_price - extreme) / entry_price * 100

            if tp_price and extreme <= tp_price * 1.05:
                sl_tight = min(entry_price * (1 - max(0.8, tp_pct * 0.5) / 100), sl) if sl else entry_price * (1 - max(0.8, tp_pct * 0.5) / 100)
                sl = sl_tight
                if extreme <= tp_price * 1.02:
                    return j, tp_price, True
            else:
                if profile == 'tight':
                    if gain_pct >= 12.0:
                        sl = min(sl, extreme * (1 + 5.0/100))
                    elif gain_pct >= 6.0:
                        sl = min(sl, extreme * (1 + 2.5/100))
                    elif gain_pct >= 3.5:
                        sl = min(sl, entry_price * (1 + 1.0/100))
                    elif gain_pct >= lk_gain:
                        sl = min(sl, entry_price * (1 + 0.3/100))
                    elif gain_pct >= be_gain:
                        sl = min(sl, entry_price * 1.0)
                elif profile == 'bear':
                    if gain_pct >= 20.0:
                        sl = min(sl, extreme * (1 + 10.0/100))
                    elif gain_pct >= 10.0:
                        sl = min(sl, extreme * (1 + 5.0/100))
                    elif gain_pct >= 5.0:
                        sl = min(sl, entry_price * (1 + 1.5/100))
                    elif gain_pct >= 3.0:
                        sl = min(sl, entry_price * (1 + 0.5/100))
                    elif gain_pct >= be_gain:
                        sl = min(sl, entry_price * 1.0)
                else:  # loose
                    if gain_pct >= 20.0:
                        sl = min(sl, extreme * (1 + 10.0/100))
                    elif gain_pct >= 10.0:
                        sl = min(sl, extreme * (1 + 5.0/100))
                    elif gain_pct >= 5.0:
                        sl = min(sl, entry_price * (1 + 1.5/100))
                    elif gain_pct >= 3.0:
                        sl = min(sl, entry_price * (1 + 0.5/100))
                    elif gain_pct >= be_gain:
                        sl = min(sl, entry_price * 1.0)

            if bar['h'] >= sl:
                exit_price = min(sl, bar['h'])
                return j, round(exit_price, 2), exit_price > entry_price

        else:  # bull — 我们实际使用的方向
            if bar['h'] > extreme:
                extreme = bar['h']
            gain_pct = (extreme - entry_price) / entry_price * 100

            if tp_price and extreme >= tp_price * 0.90:
                sl = max(sl, entry_price * (1 + tp_pct * 0.6 / 100))
                if extreme >= tp_price * 0.98:
                    j_sl = j
                    while j_sl < min(j + 3, n):
                        if ohlcv[j_sl]['l'] <= sl:
                            return j_sl, sl, True
                        j_sl += 1
                    return j, sl, True

            # ── V467 渐进式BE锁 ──
            # 可靠TP (<=12%): hold>=3无利润→BE, hold>=5微利→BE
            # 不可靠TP (>12%): 给更多空间
            if tp_price and tp_pct and tp_pct > TP_RELIABLE_MAX:
                # 远TP: 宽松, 仅hold>=5无利润才BE
                if j >= entry_idx + 5 and gain_pct < 0:
                    sl = max(sl, entry_price)
            else:
                for min_hold, min_gain in PROGRESSIVE_BE:
                    if j >= entry_idx + min_hold and gain_pct < min_gain:
                        sl = max(sl, entry_price)
                        break

            if profile == 'tight':
                if gain_pct >= 12.0:
                    sl = max(sl, extreme * (1 - 5.0/100))
                elif gain_pct >= 6.0:
                    sl = max(sl, extreme * (1 - 2.5/100))
                elif gain_pct >= 3.5:
                    sl = max(sl, entry_price * (1 - 1.0/100))
                elif gain_pct >= lk_gain:
                    sl = max(sl, entry_price * (1 - 0.3/100))
                elif gain_pct >= be_gain:
                    sl = max(sl, entry_price)
            elif profile == 'bear':
                if gain_pct >= 20.0:
                    sl = max(sl, extreme * (1 - 10.0/100))
                elif gain_pct >= 10.0:
                    sl = max(sl, extreme * (1 - 5.0/100))
                elif gain_pct >= 5.0:
                    sl = max(sl, entry_price * (1 - 1.5/100))
                elif gain_pct >= 3.0:
                    sl = max(sl, entry_price * (1 - 0.5/100))
                elif gain_pct >= be_gain:
                    sl = max(sl, entry_price)
            else:  # loose
                if gain_pct >= 20.0:
                    sl = max(sl, extreme * (1 - 10.0/100))
                elif gain_pct >= 10.0:
                    sl = max(sl, extreme * (1 - 5.0/100))
                elif gain_pct >= 5.0:
                    sl = max(sl, entry_price * (1 - 1.5/100))
                elif gain_pct >= 3.0:
                    sl = max(sl, entry_price * (1 - 0.5/100))
                elif gain_pct >= be_gain:
                    sl = max(sl, entry_price)

            if bar['l'] <= sl:
                exit_price = max(sl, bar['l'])
                return j, round(exit_price, 2), exit_price > entry_price

    # 达到max_hold未exit
    if sl is not None:
        return min(entry_idx + max_hold, n-1), sl, sl > entry_price
    return min(entry_idx + max_hold, n-1), entry_price * 0.95, False"""

new_func = """def calc_v38_trailing(ohlcv, entry_idx, entry_price, initial_sl,
                       structural_tp, n, max_hold, direction,
                       be_lock=2.0, look_lock=4.0):
    \"\"\"
    V477 T+1-aware trailing — A股无法当日卖出
    跳过同日exit, 强制到下一交易日  (但继续更新extreme/SL)
    V476 trailing + T+1强制
    \"\"\"
    sl = initial_sl
    extreme = entry_price
    tp_price = structural_tp[0] if structural_tp and structural_tp[0] else None
    tp_pct = structural_tp[2] if structural_tp and structural_tp[2] else None

    is_bear = (direction == 'bear')
    has_tp = tp_price is not None

    if not has_tp:
        profile = 'tight'
    elif is_bear:
        profile = 'bear'
    else:
        profile = 'loose'

    be_gain = be_lock
    lk_gain = look_lock
    entry_date = ohlcv[entry_idx].get('date', '')[:10]  # T+1: entry日期

    for j in range(entry_idx + 1, min(entry_idx + max_hold + 1, n)):
        bar = ohlcv[j]
        bar_date = bar.get('date', '')[:10]
        is_same_day = (bar_date == entry_date and bar_date != '')

        if is_bear:
            if bar['l'] < extreme:
                extreme = bar['l']
            gain_pct = (entry_price - extreme) / entry_price * 100

            if tp_price and extreme <= tp_price * 1.05:
                sl_tight = min(entry_price * (1 - max(0.8, tp_pct * 0.5) / 100), sl) if sl else entry_price * (1 - max(0.8, tp_pct * 0.5) / 100)
                sl = sl_tight
                if extreme <= tp_price * 1.02:
                    if is_same_day:
                        continue  # T+1: 同日不退出
                    return j, tp_price, True
            else:
                if profile == 'tight':
                    if gain_pct >= 12.0:
                        sl = min(sl, extreme * (1 + 5.0/100))
                    elif gain_pct >= 6.0:
                        sl = min(sl, extreme * (1 + 2.5/100))
                    elif gain_pct >= 3.5:
                        sl = min(sl, entry_price * (1 + 1.0/100))
                    elif gain_pct >= lk_gain:
                        sl = min(sl, entry_price * (1 + 0.3/100))
                    elif gain_pct >= be_gain:
                        sl = min(sl, entry_price * 1.0)
                elif profile == 'bear':
                    if gain_pct >= 20.0:
                        sl = min(sl, extreme * (1 + 10.0/100))
                    elif gain_pct >= 10.0:
                        sl = min(sl, extreme * (1 + 5.0/100))
                    elif gain_pct >= 5.0:
                        sl = min(sl, entry_price * (1 + 1.5/100))
                    elif gain_pct >= 3.0:
                        sl = min(sl, entry_price * (1 + 0.5/100))
                    elif gain_pct >= be_gain:
                        sl = min(sl, entry_price * 1.0)
                else:  # loose
                    if gain_pct >= 20.0:
                        sl = min(sl, extreme * (1 + 10.0/100))
                    elif gain_pct >= 10.0:
                        sl = min(sl, extreme * (1 + 5.0/100))
                    elif gain_pct >= 5.0:
                        sl = min(sl, entry_price * (1 + 1.5/100))
                    elif gain_pct >= 3.0:
                        sl = min(sl, entry_price * (1 + 0.5/100))
                    elif gain_pct >= be_gain:
                        sl = min(sl, entry_price * 1.0)

            if bar['h'] >= sl:
                if is_same_day:
                    continue  # T+1: 同日不退出
                exit_price = min(sl, bar['h'])
                return j, round(exit_price, 2), exit_price > entry_price

        else:  # bull — 我们实际使用的方向
            if bar['h'] > extreme:
                extreme = bar['h']
            gain_pct = (extreme - entry_price) / entry_price * 100

            if tp_price and extreme >= tp_price * 0.90:
                sl = max(sl, entry_price * (1 + tp_pct * 0.6 / 100))
                if extreme >= tp_price * 0.98:
                    if is_same_day:
                        continue  # T+1: 同日不退出
                    j_sl = j
                    while j_sl < min(j + 3, n):
                        if ohlcv[j_sl]['l'] <= sl:
                            return j_sl, sl, True
                        j_sl += 1
                    return j, sl, True

            # ── V467 渐进式BE锁 ──
            if tp_price and tp_pct and tp_pct > TP_RELIABLE_MAX:
                if j >= entry_idx + 5 and gain_pct < 0:
                    sl = max(sl, entry_price)
            else:
                for min_hold, min_gain in PROGRESSIVE_BE:
                    if j >= entry_idx + min_hold and gain_pct < min_gain:
                        sl = max(sl, entry_price)
                        break

            if profile == 'tight':
                if gain_pct >= 12.0:
                    sl = max(sl, extreme * (1 - 5.0/100))
                elif gain_pct >= 6.0:
                    sl = max(sl, extreme * (1 - 2.5/100))
                elif gain_pct >= 3.5:
                    sl = max(sl, entry_price * (1 - 1.0/100))
                elif gain_pct >= lk_gain:
                    sl = max(sl, entry_price * (1 - 0.3/100))
                elif gain_pct >= be_gain:
                    sl = max(sl, entry_price)
            elif profile == 'bear':
                if gain_pct >= 20.0:
                    sl = max(sl, extreme * (1 - 10.0/100))
                elif gain_pct >= 10.0:
                    sl = max(sl, extreme * (1 - 5.0/100))
                elif gain_pct >= 5.0:
                    sl = max(sl, entry_price * (1 - 1.5/100))
                elif gain_pct >= 3.0:
                    sl = max(sl, entry_price * (1 - 0.5/100))
                elif gain_pct >= be_gain:
                    sl = max(sl, entry_price)
            else:  # loose
                if gain_pct >= 20.0:
                    sl = max(sl, extreme * (1 - 10.0/100))
                elif gain_pct >= 10.0:
                    sl = max(sl, extreme * (1 - 5.0/100))
                elif gain_pct >= 5.0:
                    sl = max(sl, entry_price * (1 - 1.5/100))
                elif gain_pct >= 3.0:
                    sl = max(sl, entry_price * (1 - 0.5/100))
                elif gain_pct >= be_gain:
                    sl = max(sl, entry_price)

            if bar['l'] <= sl:
                if is_same_day:
                    continue  # T+1: 同日不退出
                exit_price = max(sl, bar['l'])
                return j, round(exit_price, 2), exit_price > entry_price

    # 达到max_hold未exit
    if sl is not None:
        return min(entry_idx + max_hold, n-1), sl, sl > entry_price
    return min(entry_idx + max_hold, n-1), entry_price * 0.95, False"""

if old_func_start in content:
    content = content.replace(old_func_start, new_func)
    engine_path.write_text(content)
    print("SUCCESS: calc_v38_trailing replaced with T+1 version")
else:
    print("FAIL: old function not found")
    # Debug: find where the function is
    idx = content.find('def calc_v38_trailing')
    if idx >= 0:
        print(f"Found at position {idx}")
        print(content[idx:idx+500])
