# V38 入口扩展 — Sweep→FVG + CHOCH→retest

## Sweep→FVG 入口

在评估FVG/OB入口时, 搜索过去5根K线内的Sweep信号:

```
Bull: SweepDown(SSL猎杀) + FVG_Bull/OB_Bull within 5 bars → Sweep→FVG
Bear: SweepUp(BSL猎杀) + FVG_Bear/OB_Bear within 5 bars → Sweep→FVG
```

实现位置: `rolling_backtest_v38.py -> evaluate_v38_entry()`

```python
SWEEP_LOOKBACK = 5
if (is_fvg or is_ob) and sig_idx > SWEEP_LOOKBACK:
    for ps in all_sigs_up_to_idx:
        ps_type = ps.get('type', '')
        ps_idx = ps.get('idx', 0)
        if direction == 'bull' and 'SweepDown' in ps_type:
            if 0 < sig_idx - ps_idx <= SWEEP_LOOKBACK:
                sweep_fvg_found = True
                break
        elif direction == 'bear' and 'SweepUp' in ps_type:
            if 0 < sig_idx - ps_idx <= SWEEP_LOOKBACK:
                sweep_fvg_found = True
                break
```

## CHOCH→retest 入口

在评估FVG/OB入口时, 检查价格是否回测到近期CHOCH的break_level:

```
Bull: FVG_Bull/OB_Bull在CHOCH_Bull break_level附近(±0.5%) → CHOCH→retest
Bear: FVG_Bear/OB_Bear在CHOCH_Bear break_level附近 → CHOCH→retest
```

实现位置: `rolling_backtest_v38.py -> evaluate_v38_entry()`

```python
RETEST_THRESHOLD = 0.5  # %
if (is_fvg or is_ob) and sig_idx > 5:
    for ps in all_sigs_up_to_idx:
        if 'CHOCH' not in ps.get('type', ''):
            continue
        bl = ps.get('metadata', {}).get('break_level', ...)
        if abs(entry_price - bl) / bl * 100 < RETEST_THRESHOLD:
            if 0 < sig_idx - ps_idx <= 20:
                choch_retest_found = True
                break
```

## 优先级

入口优先级: Sweep→FVG > CHOCH→retest > FVG > OB > BreakerBlock

## 结果

全量4800:
- Sweep→FVG: 1,533笔(2.3%), WR=92.0%, RR=5.16x — 高于纯FVG(88.4%)
- CHOCH→retest: 18笔(0.03%), WR=88.9% — ICT标准太严, 极罕见

## 注意

- Sweep→FVG不产生新交易, 只是将符合条件的FVG/OB重新标记
- 总交易数不变(67,002), WR/RR/PF完全不变
- 当FVG/OB信号已经过其他过滤器, Sweep只是额外加分
