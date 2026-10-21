# P0 权威来源与数据所有权定义（source-of-truth）

> 生成时间：2026-10-20。

## 1. 原则

1. Obsidian 中的原始文件是本项目当前阶段的权威来源，禁止修改、移动、删除、重命名或改写其内部链接/Frontmatter。
2. Workspace 仅允许创建只读副本、索引、来源映射和单向同步产物。
3. 行情/机器数据以 `~/harness/` 与 Obsidian `data/` 的机器产物为准，但引用时必须核对数据日期与来源。
4. JEV 只作决策辅助，不替代原始数据与人工判断。

## 2. 权威源表

| 领域 | 权威源 | 说明 |
|---|---|---|
| 股票跟踪池 | `~/obsidian/all about xia/01-股票投研/04-医药股票跟踪池.md` | P0 6 只 + ETF 512400，含荣昌降级说明 |
| 个股笔记 | `~/obsidian/all about xia/01-股票投研/股票/<公司>/` | 含 kline/events/meta.json/投资笔记 |
| 分析方法 | `~/obsidian/all about xia/01-股票投研/01-股票分析框架.md` | 政策→基本面→估值链、四维交叉验证 |
| 更新清单 | `~/obsidian/all about xia/01-股票投研/05-股票更新清单.md` | 每日/周更新状态 |
| 锚价状态 | `~/harness/anchor_status.json` | 最近 2026-10-19 更新，56 条 |
| 每日锚价快照 | `~/harness/stock_daily/anchor_status_YYYY-MM-DD.json` | 日期版产物 |
| 实时价快照 | `~/harness/stock_daily/realtime_prices_YYYYMMDD.json` | 日期版产物，最近 2026-09-23 |
| 合并投资组合 | `~/harness/stock_daily/stock_portfolio_enriched.json` | 56 条记录，注意包含观察池 |
| 股票综合排名 | `~/harness/stock_daily/stock_ranking.json` | 最近 2026-10-19 |
| GF-DMA 评分 | `~/obsidian/all about xia/01-股票投研/data/gfdma/` | 机器产物，引用前核对日期 |
| 每日检查 | `~/obsidian/all about xia/01-股票投研/data/daily_check/` | 机器产物 |
| 贝叶斯更新 | `~/obsidian/all about xia/01-股票投研/data/bayesian/` | 机器产物 |
| JEV MCP | `~/.hermes/mcp-servers/jev-systemone/server.py` + `~/.codex/skills/jev-systemone/SKILL.md` | 工具契约权威 |
| Hermes cron | `~/.hermes/cron/jobs.json` + `~/.hermes/cron/*.yaml` | 定时任务权威 |
| GitHub 上游行情 | `ZhuLinsen/daily_stock_analysis` | 每日分析工作流 |
| GitHub fork | `xia950704/daily_stock_analysis` | 本地 heartbeat 触发的工作流 |

## 3. 数据所有权

| 数据 | 属主 | 可写方 | 只读方 |
|---|---|---|---|
| Obsidian 原始资料 | 用户 | 用户/经批准流程 | 本系统只读 |
| 行情/机器产物 | 数据管道脚本 | 管道脚本、cron | 分析 Agent 只读 |
| Workspace 副本 | 项目 | 本项目 P1+ | 分析 Agent |
| JEV 判断记录 | 系统 | JEV/分析 Agent | 用户审阅 |
| GitHub workflow 运行数据 | GitHub 仓库 | workflow | 本地只读核查 |

## 4. 迁移所有权规则（P1 适用）

+- 所有从 Obsidian 复制到 Workspace 的文件必须保留来源绝对路径、相对路径、sha256、迁移状态。
+- 新复制文件不写入 Obsidian。
+- 若需要从 Obsidian 到 Workspace 单向同步，必须记录同步规则、频率、校验方式。
+- 不允许以 Workspace 副本为第二个权威源进行回写。
