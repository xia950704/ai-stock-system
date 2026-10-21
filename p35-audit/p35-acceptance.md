# P3.5 验收清单

> 生成时间：2026-10-20 17:45
> 验收范围：行情管道修复、数据新鲜度门槛、Search API 接入、影子运行重跑

---

## 一、行情管道修复 (优先级 1)

| ID | 要求 | 状态 | 证据 |
|---|---|---|---|
| A-01 | duckdb daily_kline 更新至最新交易日 | PASS | `+495 rows, latest=2026-10-20` |
| A-02 | stock_ranking.json run_date 更新至最新 | PASS | `run_date=2026-10-20` |
| A-03 | ranking latest_date (P0 池) 更新至最新 | PASS | `latest_date=2026-10-20` |
| A-04 | realtime_prices_YYYYMMDD.json 生成落盘 | PASS | `realtime_prices_20261020.json` 7 行 |
| A-05 | anchor_status.json current 价格更新至实时 | PASS | 恒瑞 46.08 -> 47.45 |
| A-06 | 线上脚本同步 (update_anchor/fetch_realtime) | PASS | 备份旧版，覆盖为 env-var 版本 |

---

## 二、数据新鲜度门槛 (优先级 2)

| ID | 要求 | 状态 | 证据 |
|---|---|---|---|
| B-01 | 数据日期推断 `data_asof_date` 优先使用 realtime 快照 | PASS | 返回 2026-10-20 (realtime 日期 > ranking run_date) |
| B-02 | 新鲜度门槛 `data_staleness_gate` 分级 FRESH/STALE/DATE_UNKNOWN | PASS | FRESH/STALE/DATE_UNKNOWN 三态正确 |
| B-03 | STALE (落后≥2 交易日) 阻断 blocking=True | PASS | asof=09-30 -> STALE, lag=14, blocking=True |
| B-04 | DATE_UNKNOWN 阻断 blocking=True | PASS | asof=None -> DATE_UNKNOWN, blocking=True |
| B-05 | 动作降级 `apply_staleness_gate`：CONSIDER_ENTRY/ADD/REDUCE/EXIT -> OBSERVE | PASS | CONSIDER_ENTRY -> OBSERVE + staleness_blocked=True |
| B-06 | 非交易类建议 (HOLD/WAIT/OBSERVE/INSUFFICIENT_EVIDENCE) 不受影响 | PASS | HOLD 保持 HOLD |

---

## 三、Search API 接入 (优先级 3)

| ID | 要求 | 状态 | 证据 |
|---|---|---|---|
| C-01 | 客户端 `client.py`：真实 POST、超时、重试、错误分类、日志脱敏 | PASS | 4/4 测试通过 |
| C-02 | 证据层 `evidence.py`：来源分级、转载去重、claim 状态机、多源确认 | PASS | 5/5 测试通过 |
| C-03 | 探查层 `probe.py`：3 面查询、DEFAULT_MOCK、Mock 分发、池级聚合 | PASS | 4/4 测试通过 |
| C-04 | 引擎集成 `--mock-search` 标志 | PASS | daily_judge.py 参数解析、probe_pool 调用、search_layer 附加 |
| C-05 | 报告渲染 "外部证据（Search API）" | PASS | report.py 新增节，显示 claim 状态/来源/独立来源数 |
| C-06 | 真实调用 BLOCKED 明确记录 | PASS | search-api-validation-report.md: BLOCKED (no_search_keys) |
| C-07 | Mock 模式完整可用 | PASS | `--mock-search` 端到端运行，report 渲染 claims |

---

## 四、影子运行重跑

| ID | 要求 | 状态 | 证据 |
|---|---|---|---|
| D-01 | Fresh data 运行生成报告 | PASS | `reports/shadow/2026-10-20-fresh.md` |
| D-02 | 报告标注数据日期 2026-10-20，新鲜度正常 | PASS | A 节 "数据新鲜度：正常" |
| D-03 | Stale gate 演示：模拟 09-30 数据触发降级 | PASS | `reports/shadow/2026-10-20-gated.md` |
| D-04 | Search mock 运行生成外部证据层 | PASS | `reports/shadow/2026-10-20-search4.md` |
| D-04 | 原始文件保护：Obsidian HEAD 仍为 2734b0a1 | PASS | git status 无 P3.5 导致变更 |

---

## 五、测试验收

| ID | 要求 | 状态 | 证据 |
|---|---|---|---|
| E-01 | trading_day 测试 5/5 通过 | PASS | FRESH/STALE/DATE_UNKNOWN/边界/动作降级 |
| E-02 | search/client 测试 4/4 通过 | PASS | Mock OK / no_key / 真实 BLOCKED 记录 |
| E-03 | search/evidence 测试 5/5 通过 | PASS | 来源分级/去重/claim 状态/多源确认/报告摘要 |
| E-04 | search/probe 测试 4/4 通过 | PASS | 3 面查询/DEFAULT_MOCK/Mock 分发/池级聚合 |
| E-05 | 引擎集成端到端 1/1 通过 | PASS | `--mock-jev --mock-search` 完整运行 |
| E-06 | 影子运行 3/3 场景通过 | PASS | fresh / stale-gate / search-mock |

---

## 六、交付物完整性

| ID | 交付物 | 状态 | 路径 |
|---|---|---|---|
| F-01 | data-pipeline-fix-report.md | PASS | `p35-audit/data-pipeline-fix-report.md` |
| F-02 | search-api-validation-report.md | PASS | `p35-audit/search-api-validation-report.md` |
| F-03 | test-report.md | PASS | `p35-audit/test-report.md` |
| F-04 | shadow-run-report.md | PASS | `p35-audit/shadow-run-report.md` |
| F-05 | remediation-log.md | PASS | `p35-audit/remediation-log.md` |
| F-06 | p35-acceptance.md | PASS | 本文件 |

---

## 七、遗留问题

| ID | 问题 | 等级 | 说明 |
|---|---|---|---|
| H-01 | JEV 真实调用 BLOCKED | BLOCKED | 用户需在 bynara 充值或指定可用模型 |
| H-02 | Search 真实调用 BLOCKED | BLOCKED | 用户需在 relay 侧配置 Tavily/Exa/Firecrawl/Linkup key |
| H-03 | 实时快照自动化 | M | 需写入 wrapper 或 systemd timer（需用户批准） |
| H-04 | anchor 无 data_date 字段 | L | 后续版本加字段，便于精确新鲜度校验 |
| H-05 | 节假日表缺失 | L | 接入可信节假日源或人工维护表 |

---

## 八、验收结论

**P3.5 有条件通过**

条件：
1. JEV 真实调用因账户积分不足被 BLOCKED，但 Mock 验证通过，降级逻辑正确
2. Search 真实调用因 relay 无搜索 key 被 BLOCKED，但 Mock 验证通过，集成链路完整
3. 行情管道已修复，所有关键数据文件更新至 2026-10-20
4. 数据新鲜度门槛生效，STALE/DATE_UNKNOWN 时阻断交易类建议
5. 所有测试实际执行 (21/21 通过)，无失败项
6. Obsidian 原始文件、线上 Workflow、全局配置均未被修改

**建议下一步**：
- 用户决策：是否充值 bynara 积分（JEV）或配置搜索提供者 key（Search）
- 将实时快照生成加入自动化（wrapper 或 systemd timer，需用户批准）
- P4 多交易日影子回测（需数据新鲜度连续稳定）

---

## 九、回滚步骤

见 `remediation-log.md` 第 4 节。删除 `src/search`、恢复 `trading_day.py`/`stock_judge.py`/`daily_judge.py`/`report.py` 至 P3 版本，恢复线上脚本至 `backup_phase1/p35_pre_sync/`。

---

## 十、签字确认

| 角色 | 姓名 | 日期 | 签字 |
|---|---|---|---|
| 项目负责人 | 夏爽 | 2026-10-20 | （待用户确认） |
| 执行 Agent | Codex | 2026-10-20 | ✅ |
