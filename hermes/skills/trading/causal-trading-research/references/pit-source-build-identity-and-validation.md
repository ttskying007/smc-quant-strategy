# 机构调研 PIT 源资格：可续构建、身份粒度与独立验证（V670/V671 模式）

用于"从限流型数据商分页抓取多年公告类 PIT 源 → 事件身份建模 → 独立官方文档验证 →
结果盲种子"的完整可复用流程。V670 源门禁从 FAIL(99.09% URL) 经身份建模修复到 PASS，
V671 种子生成器沿用同一事件目录。

## 1. 限流型分页源的断点续建（Resumable Build）

东财 datacenter（RPT_ORG_SURVEY）实测约束：
- `pageSize>50` → 恒返回 `服务器繁忙`；50 是上限。
- 并发 >4 触发系统性限流；16/4 workers 都会累积失败，2/1 workers 稳定。
- 每次运行重试所有 missing 页（每页 6 次、指数退避 0.75*2^attempt），失败页不落库，下次运行自然重试。

工程模式：
- sqlite `pages(year,page)` 表做主键 + 每页原子 commit + `progress.json` 落盘。
- 每 worker 线程持有一个 `requests.Session`（HTTP keep-alive），避免每页新建 TLS。
- 并发数做成 `os.environ` 覆盖（`WORKERS=int(os.environ.get('V670_WORKERS','4'))`），
  收尾阶段降为 2→1 worker 串行跑剩余页，把限流失败从 79 次降到 1 次。
- 页面 shape 校验：`count/pages` 必须等于首页期望值；行 NOTICE_DATE 年份必须等于分区年份，
  否则整页拒绝（防止错分区污染）。
- 只重抓 missing，已提交页永不重写——中断可恢复，进度不会回退。

## 2. 供应商 canonical filter 从前端 JS 挖出（不是猜的）

东财网页版 `data.eastmoney.com/invest/invest/default.html` 引用
`/newstatic/js/invest/default.js`（线上版 default.js），内含供应商自己的过滤条件：

```js
filter: '(NUMBERNEW="1")(IS_SOURCE="1")'
```

- 不应用 canonical filter 时，26711 页是"参与机构明细行"级别的膨胀分母；
  应用后收敛为事件级：2023=26,272 / 2024=25,374 / 2025=24,566 行（1526 页）。
- 抓取前先下载前端 JS 找官方 filter，不要自己发明 `NUMBERNEW/IS_SOURCE`。

## 3. 事件身份粒度必须由源数据证明，不能拍脑袋

教训：初始事件键 = `SECUCODE+NOTICE_DATE+URL`，URL 缺失时把同股同日不同调研
错误合并。但**反过来用 receive 窗口键拆分也是错的**——603786.SH 2023-01-17 的
18 行是**同一次披露**（NOTICE_DATE）汇总的多次调研记录（2022-11..12 各机构），
不是 18 个独立事件。

正确判定方法（用源数据自证）：
- 对有 URL 的行统计 `distinct(secucode,notice_date)` vs `distinct(url)`：
  1:1（67228 vs 67230，仅 2 例同日双披露）→ 披露粒度 = (secucode, notice_date)。
- 事件键 = URL（有则用，可区分同日双披露）否则 `(secucode, notice_date)`。
- URL 是供应商固有缺失字段（2023 早期 520 条、2024 57、2025 43；直接 API 探测
  URL=None），不是抓取缺陷——**门禁目标应从字段完整性改为身份可解析性**：
  `identity_resolvable_pct==100`（URL 或降级键均可寻址），`url_identity_complete_pct`
  保留为报告项而非门禁。这是源语义修正，不是阈值放宽。

## 4. 列序重构的经典陷阱

给 `build_catalog` 的 SELECT 去掉首列（如 `event_key`）后，解包必须同步去掉
前导 `_`。残留 `_, secucode, _code, _name, notice, url, ... = row` 会让所有字段
错位一格，症状极其隐蔽：`events_by_notice_year` 出现 `"AN20"` 键（notice 取到了
URL 值）、`identity_modes` 全部变成 URL、`security_code_valid_pct=0`。
修法：解包改为 `secucode, _code, _name, notice, url, ... = row`。改列序后先跑
一行样本核对字段值再全量。

## 5. 独立官方文档验证（AN ID → 公告正文）

- AN ID（如 `AN202304061585185048`）可直接验证：
  - 详情页：`https://data.eastmoney.com/notices/detail/{code}/{AN}.html`（200 + 标题含公司名）
  - 正文 API：`https://np-cnotice-stock.eastmoney.com/api/content/ann?art_code={AN}&client_source=web&page_index=1`
    返回 `notice_content`，机构调研事件正文含"投资者关系活动记录表"字样。
  - 实测 20/20 页面解析、15/15 正文为调研记录；2 例"标题空"仅因 title 字段缺失，
    正文确认无误（含北交所 920139 华岭股份=旧代码 430139、688085 三友医疗）。
- 巨潮 cninfo `fulltextSearch/full` **不索引**调研记录表（标题不含股票代码），
  按代码+日期查命中率低是接口限制，不能据此判定事件不存在；`hisAnnouncement/query`
  需正确 orgId/参数格式，否则返回 0。独立验证以东财公告正文 API 为主、cninfo 为辅。

## 6. 结果盲种子（V671 合同要点）

- 事件优先：NOTICE_DATE → 严格更晚的 sweep（20 个已完成 session 窗口内）→ 首个链。
- 每个事件只取 first chain；`symbol+notice_date` canonical 化；多 URL 同日合并。
- 输出只含事件身份、结构事件日期、量排名、参与机构数（诊断字段）；
  断言 forbidden 字段（entry_price/exit/pnl/return/mfe/mae/stop/target/win）为 0。
- 支持门禁：identities>=1000、每可用年>=300、symbols>=300、时序违规=0，过了才进 Oracle。
