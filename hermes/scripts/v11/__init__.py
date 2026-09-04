#!/usr/bin/env python3
# SMC V11 — 自适应多维共振交易系统
"""
V11 核心创新:
1. API限流器 (Rate Limiter) — 令牌桶+并发控制+429退避
2. 增强信号检测 — 修正FVG/OB/Sweep/CHOCH, 新增BPR/LiquidityVoid/RejectionBlock
3. 真实多周期数据 — Daily/4H/1H/15min 独立获取+缓存
4. 信号时间顺序共振 — 信号间距离+顺序+时间衰减+部分匹配
5. 多周期摆动点对齐 — Micro/Meso/Macro/Mega 跨TF验证
6. 自适应参数 — 基于ATR/波动率/阶段/周期的动态参数
7. 每股票+每阶段+每周期独立优化 — 三维参数空间
8. 全量验证 — 全A股+全板块+全指数+全ETF

目标: WR>80%, RR>1.5, PF>8 全市场稳健
"""

__version__ = '11.5.0'

V11_SIGNAL_TYPES = [
    # 基础信号
    'FVG', 'IFVG', 'Sweep', 'OB', 'CHOCH', 'BPR', 'MSB',
    # 增强信号 (V11新增)
    'LiquidityVoid',      # 流动性真空区 — 大幅跳空无交易区域
    'RejectionBlock',     # 拒绝块 — 长影线+实体反转
    'BreakerBlock',       # 破坏块 — 失效OB转为支撑/阻力
    'MitigationBlock',    # 缓解块 — 价格回到失衡区域的首次反应
    # 组合信号
    'Sweep_CHOCH',        # Sweep → CHOCH 序列
    'Sweep_FVG',          # Sweep → FVG 序列
    'FVG_OB_Stack',       # FVG与OB重叠
    'MultiTF_Resonance',  # 多周期方向共振
]

# 多周期配置
TIMEFRAMES = {
    'daily':   {'interval': 'daily',   'weight': 0.40, 'bars': 300},
    '4h':      {'interval': '60min',   'weight': 0.30, 'bars': 200},  # API用60min近似
    '1h':      {'interval': '30min',   'weight': 0.20, 'bars': 200},  # API用30min近似
    '15min':   {'interval': '15min',   'weight': 0.10, 'bars': 200},
}

# 共振权重 (V11调整: 增加序列和时间顺序的权重)
V11_RESONANCE_WEIGHTS = {
    'tf_resonance': 0.25,        # 多周期方向对齐
    'indicator_resonance': 0.20, # 多指标同时出现
    'swing_resonance': 0.20,     # 摆动点层级对齐
    'sequence_resonance': 0.20,  # 信号发生顺序
    'temporal_proximity': 0.15,  # 信号间时间距离(越近越强)
}

# 信号时间窗口 (bars) — 超出窗口的序列不加分
SEQUENCE_WINDOWS = {
    'Sweep_to_CHOCH': 8,    # Sweep后8根K线内出现CHOCH
    'CHOCH_to_FVG': 12,     # CHOCH后12根K线内出现FVG
    'FVG_to_OB': 10,        # FVG后10根K线内出现OB
    'Sweep_to_FVG': 15,     # Sweep后15根K线内出现FVG(跳过CHOCH)
}

# 市场阶段定义
PHASE_TRENDING_UP = 'trending_up'
PHASE_TRENDING_DOWN = 'trending_down'
PHASE_RANGING = 'ranging'
PHASE_VOLATILE = 'volatile'
PHASE_BREAKOUT = 'breakout'
