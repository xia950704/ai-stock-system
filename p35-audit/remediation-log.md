# P3.5 修复与修改日志

> 生成时间：2026-10-20

---

## 一、新增文件

| 文件 | 用途 | 行数 |
|---|---|---|
| `src/engine/trading_day.py` (追加) | 数据日期推断 `data_asof_date`、交易日计数 `trading_days_between`、新鲜度门槛 `data_staleness_gate`、动作降级 `apply_staleness_gate` | ~80 |
| `src/search/__init__.py` | 包初始化 | 1 |
| `src/search/client.py` | Search API 客户端（真实 POST、超时/重试、错误分类、日志脱敏、Mock 支持） | ~120 |
| `src/search/evidence.py` | 证据层：来源分级、转载去重、claim 状态机、多源确认、报告摘要 | ~150 |
| `src/search/probe.py` | 探查层：3 面查询模板、DEFAULT_MOCK_RESULTS、池级聚合、Mock 分发 | ~130 |
| `src/scripts/fetch/generate_realtime_snapshot.py` (线上目录) | 生成 `realtime_prices_YYYYMMDD.json` 快照 | ~40 |
| `p35-audit/data-pipeline-fix-report.md` | 行情管道修复报告 | ~120 |
| `p35-audit/search-api-validation-report.md` | Search API 验证报告 | ~100 |
| `p35-audit/test-report.md` | 测试执行汇总 | ~150 |
| `p35-audit/shadow-run-report.md` | 影子运行报告 | ~150 |
| `p35-audit/remediation-log.md` | 本文件 | ~80 |
| `p35-audit/p35-acceptance.md` | 验收清单 | ~100 |

---

## 二、修改文件

| 文件 | 修改点 | 行数 |
|---|---|---|
| `src/engine/trading_day.py` | 修复 `data_asof_date` 优先使用 realtime 快照日期；移除 `_add_day` 辅助函数 | ~20 |
| `src/engine/stock_judge.py` | 引入 `trading_day`；新增 `apply_staleness_to_analysis` 应用 stale gate | ~25 |
| `src/engine/daily_judge.py` | 新增 `--search`/`--mock-search` 参数；集成 `probe_pool`；附加 `search_layer`；run_result 新增 `search_status` | ~40 |
| `src/engine/report.py` | 新增 "外部证据（Search API）" 渲染节 | ~20 |
| `~/harness/stock_daily/update_anchor.py` | 同步 workspace 版本（支持 DATA_ROOT 环境变量） | 备份于 `backup_phase1/p35_pre_sync/` |
| `~/harness/stock_daily/fetch_realtime.py` | 同步 workspace 版本（支持 DATA_ROOT 环境变量） | 同上 |
| `~/harness/stock_daily/generate_realtime_snapshot.py` | 新增落盘脚本（线上目录） | 新增 |

---

## 三、修改原因与验收依据

| 修改 | 原因 | 验收依据 |
|---|---|---|
| duckdb K 线更新 | 排名 latest_date 卡在 09-30 | 运行 fetch_kline_tencent_incremental.py，+495 行，latest_date=10-20 |
| 排名重跑 | run_date 为 10-19 | 运行 stock_ranking.py，run_date=10-20，latest_date=10-20 |
| 实时快照落盘 | 无 realtime_prices_*.json | 新增 generate_realtime_snapshot.py，产出 20261020.json |
| anchor 价格更新 | current 停留在 09-30 | 运行 update_anchor.py，current=47.45 (恒瑞) |
| 线上脚本同步 | 线上版本硬编码路径 | cp workspace 版本到 ~/harness/stock_daily/，备份旧版 |
| 新鲜度门槛 | 无数据过期阻断 | trading_day.py 新增 data_staleness_gate，stale 时 CONSIDER_ENTRY -> OBSERVE |
| Search API 集成 | 无外部证据层 | client/evidence/probe + daily_judge --mock-search + report 渲染 |
| 真实调用 BLOCKED 标记 | JEV/Search 真实不可用 | jev_validation_report / search-api-validation-report 明确记录 BLOCKED |

---

## 四、回滚步骤

### 4.1 删除新增引擎/搜索代码
```bash
cd /Users/xiashuang/AI-股票系统
rm -rf src/search
# 恢复 trading_day.py (删除 data_asof_date / trading_days_between / data_staleness_gate / apply_staleness_gate / BLOCKING_ACTIONS / apply_staleness_to_analysis)
# 恢复 stock_judge.py (删除 import trading_day, apply_staleness_to_analysis 调用)
# 恢复 daily_judge.py (删除 --search/--mock-search, probe_pool 调用, search_layer 附加, run_result.search_status)
# 恢复 report.py (删除 "外部证据（Search API）" 节)
```

### 4.2 恢复线上脚本
```bash
cd /Users/xiashuang/harness/stock_daily
cp /Users/xiashuang/harness/backup_phase1/p35_pre_sync/* .
rm /Users/xiashuang/harness/stock_daily/generate_realtime_snapshot.py
rm /Users/xiashuang/harness/stock_daily/realtime_prices_20261020.json
```

### 4.3 删除 p35-audit 目录（可选）
```bash
rm -rf /Users/xiashuang/AI-股票系统/p35-audit
```

### 4.4 不影响项
- Obsidian 原始文件：未修改
- 真实行情数据：仅 duckdb 累积新增（无害）
- 全局配置（~/.codex/config.toml, ~/.hermes/config.yaml）：未修改
- GitHub Workflow：未修改
- JEV MCP 配置：未修改

---

## 五、副作用检查

| 检查项 | 结果 |
|---|---|
| 原始文件修改 | 无 |
| 敏感数据泄漏 | 无（未打印密钥，日志脱敏） |
| 真实交易调用 | 无 |
| 线上 Workflow 修改 | 无 |
| 全局配置修改 | 无 |
| 依赖安装 | 无（仅使用标准库 + duckdb/httpx 已存在） |

---

## 六、遗留问题

| ID | 问题 | 状态 | 建议 |
|---|---|---|---|
| U-01 | JEV 真实调用 BLOCKED | 未解决 | 用户需充值积分或指定可用模型 |
| U-02 | Search 真实调用 BLOCKED | 未解决 | 用户需在 relay 侧配置搜索提供者 key |
| U-03 | 实时快照自动化 | 非阻塞 | 需写入 wrapper 或 systemd timer（需用户批准） |
| U-04 | anchor 无 data_date 字段 | 非阻塞 | 后续版本加字段 |
| U-05 | 节假日表缺失 | 非阻塞 | 接入可信节假日源或人工维护表 |
