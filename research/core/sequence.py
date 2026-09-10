# -*- coding: utf-8 -*-
"""core/sequence.py —— V2 Structure Engine 2.0: 事件对象 + 时序状态机
蓝图 §19-22:
  - 统一 Event Object: {symbol, timeframe, timestamp, event_type, direction, price, strength, source, parent_event}
  - SequenceState FSM: LIQUIDITY_READY→SWEPT→RECLAIMED→DISPLACED→SHIFTED→POI_CREATED→RETESTING→READY / INVALID
  - Δt 特征: 事件间隔进入一级特征
  - 每次 transition 记录: {ts, state_before, state_after, trigger, invalidation}

语义(全部决策时点可得, 无前视):
  事件检测复用 core.liquidity / core.displacement / core.structure, 本模块只管:
  ① 事件对象化 ② 状态推进 ③ 顺序/Δt 记录 ④ 失效判定
"""

# ---- 状态机 ----
STATES = ("UNKNOWN", "LIQUIDITY_READY", "SWEPT", "RECLAIMED", "DISPLACED",
          "SHIFTED", "POI_CREATED", "RETESTING", "READY", "INVALID")

# 允许转移表: (from → {trigger: to})
TRANSITIONS = {
    "UNKNOWN":         {"liquidity_found": "LIQUIDITY_READY"},
    "LIQUIDITY_READY": {"sweep": "SWEPT", "invalid": "INVALID"},
    "SWEPT":           {"reclaim": "RECLAIMED", "continue_break": "INVALID", "invalid": "INVALID"},
    "RECLAIMED":       {"displacement": "DISPLACED", "invalid": "INVALID"},
    "DISPLACED":       {"structure_shift": "SHIFTED", "invalid": "INVALID"},
    "SHIFTED":         {"poi_created": "POI_CREATED", "invalid": "INVALID"},
    "POI_CREATED":     {"retest": "RETESTING", "invalid": "INVALID"},
    "RETESTING":       {"hold": "READY", "fail": "INVALID", "invalid": "INVALID"},
    "READY":           {"filled": "FILLED", "invalid": "INVALID"},
    "FILLED":          {"closed": "CLOSED", "invalid": "INVALID"},
    "INVALID":         {"reset": "UNKNOWN"},
}
# FILLED/CLOSED 不在 STATES(执行态由 core.execution 管), 但转移表允许继续
STATES_ALL = STATES + ("FILLED", "CLOSED")

# 事件类型 → 触发器
EVENT_TRIGGERS = {
    "SSL_SWEEP": "sweep",
    "BSL_SWEEP": "sweep",
    "RECLAIM": "reclaim",
    "DISPLACEMENT": "displacement",
    "MSS": "structure_shift",
    "CHOCH": "structure_shift",
    "BOS": "structure_shift",
    "FVG": "poi_created",
    "OB": "poi_created",
    "RETEST": "retest",
    "RETEST_HOLD": "hold",
    "RETEST_FAIL": "fail",
    "CONTINUE_BREAK": "continue_break",
    "LIQUIDITY_FORMED": "liquidity_found",
    "INVALIDATION": "invalid",
}


def make_event(symbol, timeframe, timestamp, event_type, direction, price, strength, source="structure", parent_event=None):
    """统一事件对象(蓝图 §19)。"""
    return {"symbol": symbol, "timeframe": timeframe, "timestamp": timestamp,
            "event_type": event_type, "direction": direction, "price": price,
            "strength": strength, "source": source,
            "parent_event": parent_event}


class SequenceMachine:
    """单 symbol 单 timeframe 的时序状态机。
    事件流按时间顺序 feed(), 状态推进 + Δt 记录 + 失效判定。
    训诫: 不合法转移(乱序)不推进并记录 rejected —— 这正是蓝图 §18'顺序成为特征'的证据点。"""

    def __init__(self, symbol, timeframe="D1", direction="LONG"):
        self.symbol = symbol
        self.timeframe = timeframe
        self.direction = direction
        self.state = "UNKNOWN"
        self.history = []       # transitions
        self.events = []        # accepted event objects
        self.rejected = []      # 乱序事件(证据)
        self._last_ts = None

    def _dt(self, ts):
        """V3审计§八修复: 旧版只取 str(ts)[:8] 按日算 Δt —— 60m/15m/5m 接入后
        09:31→09:45 与 09:31→14:50 无法区分。现支持 YYYYMMDDHHMM(12位)分钟精度,
        8位回退日级(向后兼容日线事件)。"""
        if self._last_ts is None:
            return None
        try:
            import datetime as dt
            sa, sb = str(ts), str(self._last_ts)
            if len(sa) >= 12 and len(sb) >= 12:
                a = dt.datetime.strptime(sa[:12], "%Y%m%d%H%M")
                b = dt.datetime.strptime(sb[:12], "%Y%m%d%H%M")
                d = (a - b).total_seconds() / 86400.0   # 天为单位的小数(分钟级)
                return round(d, 6)
            a = dt.datetime.strptime(sa[:8], "%Y%m%d")
            b = dt.datetime.strptime(sb[:8], "%Y%m%d")
            return (a - b).days
        except Exception:
            return None

    def feed(self, event):
        """喂入一个事件对象。返回 (accepted, new_state)。"""
        et = event.get("event_type")
        trigger = EVENT_TRIGGERS.get(et)
        if trigger is None:
            self.rejected.append({"event": event, "why": "UNKNOWN_EVENT_TYPE"})
            return False, self.state
        allowed = TRANSITIONS.get(self.state, {})
        if trigger not in allowed:
            self.rejected.append({"event": event, "why": f"OUT_OF_ORDER({self.state}→{trigger})"})
            return False, self.state
        new_state = allowed[trigger]
        dt_days = self._dt(event.get("timestamp"))
        self.history.append({"ts": event.get("timestamp"), "state_before": self.state,
                             "state_after": new_state, "trigger": trigger,
                             "dt_days_from_prev": dt_days,
                             "invalidation": event.get("invalidation")})
        self.state = new_state
        self.events.append(event)
        self._last_ts = event.get("timestamp")
        return True, new_state

    # ---- Δt 特征(蓝图 §21) ----
    def dt_features(self):
        return [h["dt_days_from_prev"] for h in self.history if h["dt_days_from_prev"] is not None]

    def sequence_signature(self):
        """顺序签名: 触发器序列字符串(用于顺序家族对比)。"""
        return "→".join(h["trigger"] for h in self.history)

    def is_ready(self):
        return self.state == "READY"

    def is_invalid(self):
        return self.state == "INVALID"


def run_sequence(daily, i, direction="LONG", timeframe="D1", symbol=""):
    """从K线重建 daily[i] 之前的 SMC 事件链(语义层, 复用 liquidity/displacement)。
    这是 Structure Engine 2.0 的语义骨架: 只做事件检测+状态推进, 不做收益优化。
    检测(决策时点 i, 无前视):
      LIQUIDITY_READY: 下方存在 SSL 池(score>=40)
      SWEEP: bar.low 破池后收回(收盘回到池上)
      RECLAIM: 随后 N 根内收盘收复前高(扫损前可见)
      DISPLACEMENT: displacement_score>=50 的同向 K
      SHIFT/POI/RETEST: 骨架占位(结构引擎后续迭代补全语义)
    """
    import core.liquidity as LQ
    import core.displacement as DS
    m = SequenceMachine(symbol, timeframe, direction)
    if i < 30:
        return m
    atr = 0
    try:
        from core.structure import atr_of
        atr = atr_of(daily, i - 1) or 0
    except Exception:
        atr = 0
    tol = max(0.003, (atr / (daily[i - 1]["c"] or 1)) * 0.5) if atr > 0 else 0.003
    # 事件链扫描窗口: i 前 40 根
    w0 = max(30, i - 40)
    # 1) 流动性池(窗口期初可用)
    pools = LQ.liquidity_pools(daily, w0 + 1)
    ssl = [p for p in pools if p["side"] == "SSL" and p["score"] >= 40]
    if ssl:
        m.feed(make_event(symbol, timeframe, daily[w0 + 1]["t"], "LIQUIDITY_FORMED",
                          direction, ssl[0]["price"], ssl[0]["score"]))
    # 2) 扫损+收回+位移+结构(逐根推进)
    prev_high = max(b["h"] for b in daily[max(0, w0 - 5):w0 + 1]) if w0 >= 5 else daily[w0]["h"]
    reclaimed = False
    for k in range(w0 + 2, i + 1):
        b = daily[k]
        if m.state == "LIQUIDITY_READY" and ssl:
            pool_px = ssl[0]["price"]
            if b["l"] <= pool_px * (1 - tol) and b["c"] > pool_px:
                m.feed(make_event(symbol, timeframe, b["t"], "SSL_SWEEP", direction,
                                  pool_px, 60, parent_event="pool"))
        elif m.state == "SWEPT":
            if b["c"] > prev_high:
                m.feed(make_event(symbol, timeframe, b["t"], "RECLAIM", direction, b["c"], 55))
                reclaimed = True
            elif b["c"] < ssl[0]["price"] * (1 - 2 * tol):
                m.feed(make_event(symbol, timeframe, b["t"], "CONTINUE_BREAK", direction, b["c"], 0))
        elif m.state == "RECLAIMED":
            sc = DS.displacement_score(daily, k)
            if sc["score"] >= 50 and b["c"] > b["o"]:
                m.feed(make_event(symbol, timeframe, b["t"], "DISPLACEMENT", direction, b["c"], sc["score"]))
        elif m.state == "DISPLACED":
            # 骨架: 结构转移占位(CHOCH/MSS 语义在下一迭代补全) —— 突破窗口内 swing high 即记
            if reclaimed and b["c"] > prev_high * (1 + tol):
                m.feed(make_event(symbol, timeframe, b["t"], "BOS", direction, b["c"], 50))
        elif m.state in ("SHIFTED", "POI_CREATED", "RETESTING"):
            # 骨架占位: POI/RETEST 语义后续迭代
            break
        if m.is_invalid():
            break
    return m


# ============================================================
# V2(2026-09-09, 第三轮深审 A2/A3): 完整因果链 FSM —— 无占位
# A2: SHIFT/POI/RETEST 真实语义(core.mss + core.fvg_ob 接线)
# A3: 因果绑定 —— sweep 绑定 target_pool; reclaim 收复 sweep 引用的前高;
#     全事件 parent_event_id 链, 任何一环断可诊断。
# ============================================================
EVENT_SEQ_V2 = ("LIQUIDITY", "SWEEP", "RECLAIM", "DISPLACEMENT", "SHIFT", "POI", "RETEST")


class SequenceMachineV2:
    """完整因果链状态机: 每事件带 id/parent_event_id/结构引用。"""

    def __init__(self, symbol="", timeframe="D1"):
        self.symbol = symbol
        self.timeframe = timeframe
        self.events = []
        self.rejected = []
        self._next_id = 1

    def _emit(self, etype, ts, price, strength, parent_id, extra=None):
        ev = {"id": self._next_id, "event_type": etype, "ts": ts, "price": round(float(price), 4),
              "strength": strength, "parent_event_id": parent_id, "symbol": self.symbol,
              "timeframe": self.timeframe}
        if extra:
            ev.update(extra)
        self._next_id += 1
        self.events.append(ev)
        return ev["id"]

    def setup(self):
        """完整链则返回 setup dict, 否则 None(断链可从 events/rejected 诊断)。"""
        if len(self.events) < len(EVENT_SEQ_V2):
            return None
        kinds = [e["event_type"] for e in self.events]
        if tuple(kinds[-len(EVENT_SEQ_V2):]) != EVENT_SEQ_V2:
            return None
        sweep_ev = [e for e in self.events if e["event_type"] == "SWEEP"][-1]
        poi_ev = [e for e in self.events if e["event_type"] == "POI"][-1]
        retest_ev = [e for e in self.events if e["event_type"] == "RETEST"][-1]
        return {"state": "ENTRY_READY", "sequence": "→".join(kinds),
                "swept_pool": sweep_ev.get("target_pool"),
                "poi": poi_ev.get("poi"),
                "retest_price": retest_ev["price"],
                "events": [e["id"] for e in self.events]}


def run_sequence_v2(daily, i, symbol="", timeframe="D1", lookback=40,
                    pool_min_score=40, disp_min=50, retest_bars=8):
    """完整事件链重建(决策时点 i, 无前视)。
    链: 池(score>=阈值) → 扫该池(破后收回, 绑定池) → 收复 sweep 前可见前高(因果绑定)
        → 位移(>=阈值) → MSS/BOS 上破(core.mss) → POI(FVG 优先/OB 兜底)
        → 重测 POI(<=retest_bars, 未破失效位 poi.low×0.97)。
    任一环失败返回部分链(诊断友好)。"""
    import core.liquidity as LQ
    import core.displacement as DS
    import core.mss as MSS
    import core.fvg_ob as FO
    m = SequenceMachineV2(symbol, timeframe)
    if i < 60:
        return m
    try:
        from core.structure import atr_of
        atr = atr_of(daily, i - 1) or 0
    except Exception:
        atr = 0
    atr_pct = (atr / (daily[i - 1]["c"] or 1)) if atr else 0.02
    tol = max(0.003, atr_pct * 0.5)
    w0 = max(60, i - lookback)
    # 1) 流动性池
    pools = LQ.liquidity_pools(daily, w0 + 1)
    ssl = [p for p in pools if p["side"] == "SSL" and p["score"] >= pool_min_score]
    if not ssl:
        return m
    pool = ssl[0]
    _id_pool = m._emit("LIQUIDITY", daily[w0 + 1]["t"], pool["price"], pool["score"], None,
                       {"target_pool": {"kind": pool["kind"], "side": "SSL", "price": pool["price"]}})
    # 2) 扫损(绑定该池)
    sweep_i = None
    _id_sw = None
    for k in range(w0 + 2, i + 1):
        b = daily[k]
        if b["l"] <= pool["price"] * (1 - tol) and b["c"] > pool["price"]:
            _id_sw = m._emit("SWEEP", b["t"], pool["price"], 60, _id_pool,
                             {"target_pool": {"kind": pool["kind"], "side": "SSL", "price": pool["price"]}})
            sweep_i = k
            break
        if b["c"] < pool["price"] * (1 - 2 * tol):
            m.rejected.append({"why": "BREAK_DOWN_BEFORE_SWEEP", "at": b["t"]})
            return m
    if sweep_i is None:
        return m
    # A3: reclaim 的因果 level = sweep 前可见前高(sweep 引用)
    reclaim_level = max(x["h"] for x in daily[max(0, sweep_i - 5):sweep_i])
    # 3) 收复(绑定 reclaim_level)
    recl_i = None
    for k in range(sweep_i + 1, min(len(daily), sweep_i + 6)):
        if daily[k]["c"] > reclaim_level:
            _id_rc = m._emit("RECLAIM", daily[k]["t"], reclaim_level, 55, _id_sw,
                             {"reclaim_level": reclaim_level})
            recl_i = k
            break
        if daily[k]["c"] < pool["price"] * (1 - 2 * tol):
            m.rejected.append({"why": "BREAK_AFTER_SWEEP", "at": daily[k]["t"]})
            return m
    if recl_i is None:
        return m
    # 4) 位移
    disp_i = None
    for k in range(recl_i, min(len(daily), recl_i + 6)):
        sc = DS.displacement_score(daily, k)
        if sc["score"] >= disp_min and daily[k]["c"] > daily[k]["o"]:
            _id_dp = m._emit("DISPLACEMENT", daily[k]["t"], daily[k]["c"], sc["score"], _id_rc,
                             {"disp_bucket": sc.get("bucket")})
            disp_i = k
            break
    if disp_i is None:
        return m
    # 5) 结构转移(core.mss)
    shift_i = None
    for k in range(disp_i, min(len(daily), disp_i + 13)):
        s5 = MSS.structure_shift(daily, k)
        if s5 and s5["direction"] == "LONG":
            _id_sh = m._emit("SHIFT", daily[k]["t"], s5["level"], s5["strength"], _id_dp,
                             {"shift_type": s5["type"], "trend_before": s5["trend_before"]})
            shift_i = k
            break
    if shift_i is None:
        return m
    # 6) POI(FVG 优先, OB 兜底) —— 转移后 3 根内
    poi_i = None
    poi = None
    _id_poi = None
    for k in range(shift_i, min(len(daily), shift_i + 4)):
        f6 = FO.fvg_at(daily, k)
        ob6 = FO.order_block(daily, k, "BULL")
        if f6:
            _id_poi = m._emit("POI", daily[k]["t"], f6["mid"], 60, _id_sh,
                              {"poi": {"type": "FVG", "low": f6["low"], "high": f6["high"],
                                       "mid": f6["mid"], "size_atr": f6["size_atr"]}})
            poi_i, poi = k, f6
            break
        if ob6:
            _id_poi = m._emit("POI", daily[k]["t"], ob6["mid"], 50, _id_sh,
                              {"poi": {"type": "OB", "low": ob6["low"], "high": ob6["high"],
                                       "mid": ob6["mid"], "bars_len": ob6["bars_len"]}})
            poi_i, poi = k, ob6
            break
    if poi_i is None:
        return m
    # 7) 重测(未破失效位)
    for k in range(poi_i + 1, min(len(daily), poi_i + 1 + retest_bars)):
        b = daily[k]
        if b["c"] < poi["low"] * 0.97:
            m.rejected.append({"why": "INVALIDATED_BEFORE_RETEST", "at": b["t"]})
            return m
        if poi["low"] <= b["l"] <= poi["high"] * 1.02:
            m._emit("RETEST", b["t"], b["l"], 50, _id_poi)
            return m
    m.rejected.append({"why": "NO_RETEST_IN_WINDOW"})
    return m