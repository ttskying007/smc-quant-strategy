# easy_tdx 集成说明（第八轮/数据源适配器）

> 集成日期：2026-09-08 | 目的：把 easy_tdx（通达信本地数据）/ pytdx（通达信网络）集成进 smc_project

## 一、环境可行性实测结论（tdx_feasibility.py）

| 数据源 | 可行性 | 证据 |
|---|---|---|
| **pytdx 网络** | ❌ 网络受限 | TCP 可达 7709 端口（4 个服务器均 True），但 TDX 协议握手失败（`ResponseRecvFails: 服务器断开连接`）→ 被防火墙/代理拦截 |
| **easy_tdx 本地** | ❌ 无通达信客户端 | 本机未装通达信；仅同花顺 `.day` 带 `hd1.0` 头（非标准通达信格式）+ 仅 24-45 只（覆盖极不全） |
| **腾讯 kline_cache（现行）** | ✅ 可靠 | 4662 只 K 线，600519 等正常读取 |

**结论**：本网络环境当前无法直接接入通达信数据（网络协议被拦截，本地无通达信安装）。easy_tdx 的完整接入需先安装通达信客户端或打通网络。

## 二、已交付：统一数据源适配器 core/tdx_feed.py

为让"集成"结构性就位（而非强行连通不可达的源），交付了统一数据源抽象：

```
from core import tdx_feed as TF
TF.backend_status()            # 后端状态: active/tencent/pytdx/easy_tdx + 不可用原因
TF.get_daily("600519")         # 统一日线 bars [{t,o,h,l,c,v}] —— 自动回退腾讯
TF.get_realtime(["600519"])    # 实时报价（TDX 可用时；当前安全降级空dict）
TF.get_fundflow("600519")      # 资金/财务（TDX 可用时；当前安全降级）
```

- **单一 bars schema**（`{t:YYYYMMDD, o,h,l,c,v}`）与 kline_cache_tencent 完全一致
- **自动后端回退**：pytdx 连上自动接管，否则回退腾讯；easy_tdx 探测到本地 .day 目录自动接管
- **安全降级**：实时/资金接口在后端不可用时返回空 dict，不抛异常
- 后端探测结果缓存 5 分钟（避免每次 6-8s 连接超时成本）

## 三、前端 /tdx 数据源状态页（已上线）

- 导航新增"**数据源**"链接 → `/tdx` 页
- 展示三后端可用性 + 激活后端 + 接入方式示例代码
- 120 秒自动刷新
- 实测：`/tdx` 200（5813 字节），含三后端状态

## 四、测试

- `tests_tdx_feed.py`：12 项（后端状态结构 / 腾讯回退 / bars schema / 安全降级 / easy探测）
- 全量 **196 PASS / 0 FAIL**（184 原有 + 12 新）
- `/tdx` `/funnel` `/` 全部 200，镜像同步

## 五、后续（待环境就绪）

1. 安装通达信客户端（vipdoc 目录有 .day）→ easy_tdx 后端自动激活
2. 打通网络/代理到通达信服务器 → pytdx 后端自动激活，实时/资金数据启用
3. 届时 tdx_feed 的 get_realtime/get_fundflow 直接可用，paper_sim realtime_monitor 可切换