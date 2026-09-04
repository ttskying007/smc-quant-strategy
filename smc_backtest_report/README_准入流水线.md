# SMC 新本体准入流水线（固化版）使用说明

> 依据：V633 蓝图 + SMC 防再犯规则清单（R1-R7/R13-R15/R22）
> 位置：`E:\test\smc_project\smc_backtest_report\`

## 一、为什么需要这个流水线

- V88 教训：前视偏差（TP 用未来 20 根高点）制造 80% 虚假胜率，700+ 次迭代无人察觉
- 之前"新版本"由 hermes 自由生成、无统一准入 → 反复重测已关闭信息族
- **从现在起：任何新本体晋级生产前必须通过本流水线，否则一律保持 EMPTY_BOOK**

## 二、流水线五步（smc_reverify_runner.run_admission 强制执行）

```text
① outcome-free seed    seed_fn(symbol, bars, params) -> seeds
                        - 只读 entry 前数据（R13）
                        - TP/SL 锚点必须 entry 前可见（R2）
                        - entry_identity = symbol|entry_date|event_date（R15）
② 独立 oracle          oracle_fn(symbol, bars) -> identity set（R14）
                        - 不 import seed 代码，同语义不同实现
                        - 目标：intersection 高（<100% 须排查实现覆盖差异）
③ 冻结 T+1 回放        replay_fn(seed, bars, params) -> trade（R1/R3/R4）
                        - 入场=次日开盘（可成交，R1）；T+1（R3）
                        - 费用 0.20%、SL 优先、GAP_SL（R4）
④ 经济门槛            smc_gates.check_economic_gate（R6/R7）
                        - n≥1000、每年≥300、每月>4
                        - WR≥55%、AvgNet≥+0.5%、PF≥1.15、payoff≥0.70
                        - 每年 AvgNet>0、T+1=0
⑤ 报告                {ontology}_admission_report.json + trades.csv + seeds.csv
```

## 三、快速开始

```python
import sys
sys.path.insert(0, r'E:\test\smc_project\smc_backtest_report')
from smc_reverify_runner import run_admission

def my_seed(symbol, bars, params):
    # 你的 outcome-free 信号检测
    return [{"symbol": symbol, "entry_identity": f"{symbol}|...|...", ...}]

def my_oracle(symbol, bars):
    return set()  # 独立实现

def my_replay(seed, bars, params):
    return None  # 冻结回放

report = run_admission(
    name='MY_ONTOLOGY',
    kline_dir=r'E:\test\smc_project\hermes\kline_cache',
    seed_fn=my_seed, oracle_fn=my_oracle, replay_fn=my_replay,
    params={...},
    out_dir=r'E:\test\smc_project\smc_backtest_report\admission',
)
print(report['economic_gate']['gate_pass'])
```

## 四、门槛判定

- `gate_pass=True` → `PROMOTION_PASS`：可进入 scanner-time 重建 + 生产许可申请
- `gate_pass=False` → `ECONOMIC_GATE_FAIL__CLOSE_ONTOLOGY__NO_VARIANTS`：**本体关闭，禁止换阈值/窗口/SL/TP/年份重测**（R5）
- oracle coverage < 100%：先排查 oracle 实现覆盖差异（是缺陷还是覆盖范围）

## 五、参考实现

- 完整可运行示例：`v88_reverify.py`（V88 重验，修复前视偏差版）+ `v88_oracle.py`
- 门槛模块：`smc_gates.py`（自测通过）
- 框架：`smc_reverify_runner.py`
