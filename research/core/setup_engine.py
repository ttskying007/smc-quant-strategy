# -*- coding: utf-8 -*-
"""core/setup_engine.py —— V3 P0-2: 统一 SetupEngine(单一真相源第一步)
V3审计§十一: current_scanner 仍依赖 wdh_engine/stage_and_deep 旧语义, Research Core 与
Production 链分叉。本模块定义统一 Setup 对象与生成入口, 目标: Scanner/Paper/Backtest/
Shadow/Portfolio 全部消费同一 setup_id 结构。

范围声明(V3阶段范围控制):
  本版(Phase A 第一条): SHADOW 实验链与 PAPER 台账接线(研究链先行), 生产 scanner 的
  切换待 PAPER 30+ closed 且七道晋级门(§十六)通过后执行 —— 不提前动生产。

统一 Setup 对象(蓝图 §90 + V3 P0-2):
  setup_id / sequence_id / symbol / signal_date / decision_idx
  family / sequence(签名) / poi{type,low,high,mid} / invalid_price
  zone(低/高/最优) / entry_limit / sl / tp(3R 结构位) / valid_from
  events(parent_event_id 链) / exit_version / engine_version
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ENGINE_VERSION = "setup_engine_v1"


def build_setup(daily, i, code, family="SMC_REVERSAL"):
    """决策点 i → 统一 Setup 对象(完整链 run_sequence_v2 + setup_exit 同源字段)。
    返回 dict 或 None(链未完成)。全部字段决策时点可得(无前视)。"""
    from core.sequence import run_sequence_v2
    from core.setup_exit import EXIT_VERSION
    m = run_sequence_v2(daily, i, symbol=code)
    s = m.setup()
    if s is None:
        return None
    poi = s["poi"]
    d8 = str(daily[i]["t"])[:8]
    seq_sig = s["sequence"]
    # V3-A P1(第五轮审计§十一): setup_id 粒度升级 —— code+date+poi_type 在同日
    # 双 sequence/双 pool/双 POI 时会碰撞。改 hash(symbol+decision_ts+sequence+
    # swept_pool+poi几何+engine_version) 前 12 位; 保留旧字段 setup_id_legacy
    # (兼容历史台账)。事件粒度不丢失: 不同链→不同 id。
    import hashlib as _hl
    _key = "|".join([str(code), d8, seq_sig,
                     str(round(s.get("swept_pool", {}).get("price", 0), 4)),
                     str(round(poi["low"], 4)), str(round(poi["high"], 4)),
                     ENGINE_VERSION])
    setup_id = "SU-" + _hl.md5(_key.encode("utf-8")).hexdigest()[:12]
    setup_id_legacy = f"{code}_{d8}_{poi['type']}_v1"
    # 3R 结构位与 SL 由 setup_exit 统一计算口径(此处先给决策时点已知的字段)
    return {
        "setup_id": setup_id,
        "setup_id_legacy": setup_id_legacy,     # P1: 旧格式保留(台账迁移期双写)
        "engine_version": ENGINE_VERSION,
        "exit_version": EXIT_VERSION,
        "symbol": code, "signal_date": d8, "decision_idx": i,
        "family": family, "sequence": seq_sig,
        "sequence_events": [dict(e) for e in m.events],
        "rejected": list(m.rejected),
        "poi": {"type": poi["type"], "low": poi["low"], "high": poi["high"], "mid": poi["mid"]},
        "invalid_price": round(poi["low"] * 0.97, 4),
        "zone": {"low": poi["low"], "high": poi["high"], "optimal": poi["mid"]},
        "entry_limit": round(poi["mid"], 4),          # 挂单价=POI 中值(研究起点)
        "order_type": "LIMIT_RETRACE",                # A5: 严格限价, 未触价 PENDING
        # V3-A P1(§十二): 时间语义显式化 —— signal_at=信号日; eligible_at=最早可撮合日
        # (A股 T+1 语义: 次日); expires_at=有效期(setup_exit 窗口); 废弃模糊的 valid_from
        "signal_at": d8,
        "eligible_at": d8,                             # 研究回测: 决策日即可试撮(次日撮合由消费方)
        "valid_from": d8,                              # 兼容字段(=signal_at, 勿再新增语义)
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def validate_setup(setup):
    """Setup 对象完整性校验(fail-closed): 缺任一必备字段 → (False, 缺项)。"""
    need = ("setup_id", "symbol", "signal_date", "family", "sequence",
            "poi", "invalid_price", "zone", "entry_limit", "order_type",
            "valid_from", "engine_version", "exit_version")
    for k in need:
        if setup.get(k) in (None, ""):
            return False, k
    if not (setup["poi"]["low"] < setup["poi"]["high"]):
        return False, "poi_geometry"
    if setup["invalid_price"] >= setup["poi"]["low"]:
        return False, "invalid_above_poi"
    return True, "OK"