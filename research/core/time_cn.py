# -*- coding: utf-8 -*-
"""core/time_cn.py —— 上海时区时间单源(R21, 第八轮审计 P1-11)。

审计 P1-11: "监控使用服务器本地 time.strftime(), 没有显式 Asia/Shanghai 时区。
这会造成公告可见日、信号日、T+1 日和监控日不一致。"

本模块提供唯一时区感知时间源:
- shanghai_now(): tz-aware datetime(Asia/Shanghai);
- cn_now(fmt): 按上海时区格式化字符串(time.strftime 的时区正确替代);
- cn_today(): 上海时区 YYYYMMDD(交易日/挂单日判定基准);
- cn_time(): time.gmtime 等价物(上海时区 struct_time)。

所有生产时间戳(账本 created_at/submitted_at/filled_at/日开仓计数)应改用本模块。
服务器部署在本地时区恰好为 UTC+8 的机器上时行为不变(向后兼容), 但跨时区
部署(CI/Linux UTC)不再漂移。

降级: zoneinfo 不可用(无 tzdata)时回退本地时间并打 WARN —— 仅研究级容忍,
生产部署应保证 tzdata 存在(validate_paths 不覆盖此处, tz 检查在测试锁)。
"""
import time as _time
from datetime import datetime as _dt

_TZ = None
_TZ_SRC = "local_fallback"

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Asia/Shanghai")
    _TZ_SRC = "zoneinfo:Asia/Shanghai"
except Exception:  # no tzdata
    _TZ = None


def shanghai_now():
    """tz-aware 当前时间(上海)。zoneinfo 不可用时返回本地 naive 时间。"""
    if _TZ is not None:
        return _dt.now(_TZ)
    return _dt.now()


def cn_time():
    """上海时区 struct_time(time.strftime 可直接消费)。"""
    return shanghai_now().timetuple()


def cn_now(fmt="%Y-%m-%d %H:%M:%S"):
    """按上海时区格式化当前时间 —— time.strftime(fmt) 的时区正确替代。"""
    return shanghai_now().strftime(fmt)


def cn_today():
    """上海时区当日 YYYYMMDD(交易日/挂单日/日开仓计数基准)。"""
    return shanghai_now().strftime("%Y%m%d")


def tz_source():
    """时区来源诊断(测试锁/运维检查用)。"""
    return _TZ_SRC