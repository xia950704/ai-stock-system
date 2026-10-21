# P0 资产清单（asset-inventory）

> 生成时间：2026-10-20。P0 只读探查产物。
> 范围：股票追踪、行情采集、投研脚本、JEV 系统、GitHub Workflow、相关配置。
> 说明：本文件记录已确认与待核实资产，不含凭猜测补全的路径。

## 1. 当前环境

| 项 | 值 |
|---|---|
| 当前 Workspace | `/Users/xiashuang/AI-股票系统` |
| Git 状态 | 非 Git 仓库，目录为空 |
| Obsidian Vault | `/Users/xiashuang/obsidian/all about xia`（Git 仓库，remote=`https://github.com/xia950704/obsidian-vault.git`） |
| 移动硬盘 | `/Volumes/夏爽`（exfat，已挂载） |
| 统一 Agent Workspace | `/Users/xiashuang/agent-workspace` |
| 本机 relay | `http://127.0.0.1:57321/v1` |
| 当前时区 | `Asia/Shanghai` |

## 2. 权威数据源（Obsidian 股票投研目录）

### 2.1 核心目录

| 路径 | 用途 | 状态 |
|---|---|---|
| `/Users/xiashuang/obsidian/all about xia/01-股票投研` | 股票投研主目录，272 个 md / 261 个 csv / 333 个 json | 权威来源，Git 仓库 |
| `01-股票投研/04-医药股票跟踪池.md` | P0 股票池（6 只 + 512400 ETF） | 权威跟踪池索引 |
| `01-股票投研/01-股票分析框架.md` | 分析方法与框架 | 权威方法 |
| `01-股票投研/05-股票更新清单.md` | 更新清单 | 权威清单 |
| `01-股票投研/06-Agent命令清单-股票数据更新.md` | Agent 命令入口 | 权威命令清单 |
| `01-股票投研/股票/` | 个股笔记（约 68 家公司目录） | 权威个股笔记 |
| `01-股票投研/ETF/` | ETF 跟踪与口径说明 | 权威 ETF 资料 |
| `01-股票投研/data/` | 机器产出：daily_check、gfdma、bayesian、verification、standardized 等 | 机器数据，需要核验日期 |
| `01-股票投研/日更/` | 每日报告（存在少量配对信号报告） | 报告产物 |
| `01-股票投研/分析报告/` | 历史分析报告 | 参考 |
| `01-股票投研/tools/` | 工具目录 | 待核实内容 |
| `01-股票投研/scripts/valuation_update.py` | 估值更新脚本 | 待核实运行状态 |

### 2.2 已知重复/归档资产（不修改）

| 路径 | 说明 |
|---|---|
| `~/obsidian/all about xia/99-归档/股票投研_已归档/` | 大量历史个股笔记、报告、旧数据，多与 01-股票投研 重复 |
| `~/obsidian/all about xia/99-归档/股票散件_20260911/` | 2026-09-11 归档的股票散件 |
| `~/obsidian/all about xia/99-归档/AI对话日志-20260721/` | 2026-07-15 股票/ETF/cron 相关对话日志 |
| `~/obsidian/all about xia/99-归档/2026-09前_已迁移/投研-2026-09/stock_ml_trading/` | stock_ml_trading 旧快照 |
| `~/obsidian/all about xia/99-归档/股票占位骨架_202609/` | 股票占位骨架 |

## 3. 数据与行情资产

### 3.1 `~/harness/stock_daily/`

| 文件 | 用途 | 最近日期 |
|---|---|---|
| `anchor_status_2026-09-23.json` | 每日锚价状态（日期版） | 2026-09-23 |
| `realtime_prices_20260923.json` | 实时价（日期版） | 2026-09-23 |
| `stock_portfolio_enriched.json` | 合并投资组合（56 条记录，非 P0 6 只） | 2026-09-24 |
| `stock_ranking.json` | 多信号综合排名 | 2026-10-19 |
| `stock_ranking.html` | 排名 HTML 看板 | 2026-10-19 |
| `fetch_realtime.py` | 实时价抓取 | - |
| `fetch_kline_tencent.py` | 腾讯 K 线 | - |
| `fetch_kline_tencent_incremental.py` | 增量 K 线 | - |
| `update_anchor.py` | 锚价更新 | - |

### 3.2 `~/harness/anchor_status.json`

- 权威锚价状态，结构为 **list**（56 项），包含 `name/code/current/anchor/deviation/status/pe/prev_close/change_pct`。
- 最近修改 2026-10-19。

### 3.3 `/Volumes/夏爽/20_Library_图书馆/03_金融投研/`

- 201 个 md / 233 个 csv，含实时行情、价格触发日志、估值追踪汇总、个股分析等。
- 疑为移动硬盘侧的投研资料库，**是否属于当前系统权威数据待核实**。

### 3.4 `/Volumes/夏爽/stock_daily/`

- 仅 2 个 md：`index_20260911.txt`、`raw_quote_20260911.txt`（txt 被 ls 显示为 md？实为 txt）。
- 是历史快照，不是当前行情权威源。

## 4. 脚本与 Skills

### 4.1 stock-research Skill（Codex 侧）

- 路径：`~/.codex/skills/stock-research/SKILL.md`
- 用途：医药股票投研助手，P0/P1/P2 分级策略。
- 登记了约 30+ 个脚本入口，真实脚本源主要位于：
  - `/Volumes/夏爽/migration-20260922/hermes-scripts/`
  - `~/stock_ml_trading/`
  - `~/harness/stock_daily/`
- 脚本引用存在绝对路径，依赖 `HERMES_WORKSPACE=/Users/xiashuang/harness/stock_daily`。
- **注意**：Skill 中登记的部分状态路径（如 `~/.hermes/workspace/stock_daily/...`）在当前环境不存在，实际数据在 `~/harness/stock_daily/`。

### 4.2 Hermes 脚本

| 路径 | 用途 | 状态 |
|---|---|---|
| `~/.hermes/scripts/investment_pipeline.py` | 收盘后统一数据处理 | 被 cron wrapper 调用 |
| `~/.hermes/scripts/stock_ranking.py` | 股票综合排名 | 被 cron wrapper 调用 |
| `~/.hermes/scripts/wrappers/investment_pipeline.sh` | 投资流水线 wrapper | 已确认 |
| `~/.hermes/scripts/wrappers/stock_daily_fetch.sh` | 每日数据抓取 wrapper（update_anchor.py） | 已确认 |
| `~/.hermes/scripts/wrappers/github_stock_heartbeat.sh` | GitHub 行情 workflow 心跳触发 | 已确认 |
| `~/.hermes/mcp-servers/jev-systemone/server.py` | JEV MCP 服务 | 已确认 |

### 4.3 `/Volumes/夏爽/migration-20260922/hermes-scripts/`

- 是 stock-research Skill 登记的主要脚本源。
- 包含 `stock_price_alert.py`、`stock_ranking.py`、`anchor_valuation.py`、`gfdma_scorer.py`、`fetch_finance_and_pe.py`、`merge_stock_portfolio.py` 等。
- 存在大量 `._*.py`（macOS 元数据文件），不影响运行。
- **待核实**：脚本当前是否可运行、依赖是否完整、是否仍被 Hermes cron 引用。

### 4.4 `~/stock_ml_trading/`

- 配对交易/ML 交易系统，**独立于投研 Skill**，入口 `run.py`。
- 含 `auto_trade_state.json`、`discovered_pairs_v2.json`、`logs/auto_trade_log.csv` 等。
- **非 Git 仓库**，`run.py pairs trade` 可执行自动交易，当前系统约束禁止 P0 触发。
- 系统 crontab 已注册 5 条交易日任务（15:17 signal / 15:20 report / 15:22 trade / 周六 09:17 backtest / 09:30 ml signal）。

## 5. JEV 系统

| 资产 | 路径 | 状态 |
|---|---|---|
| JEV MCP server | `~/.hermes/mcp-servers/jev-systemone/` | 已确认，5 个工具 |
| JEV MCP key | `~/.hermes/mcp-servers/jev-systemone/.key` | 存在（不打印值） |
| JEV Skill | `~/.codex/skills/jev-systemone/SKILL.md` 与 `~/.hermes/skills/jev-systemone/SKILL.md` | 已确认 |
| JEV CLI checkout | `~/.hermes/jev-skills/` | Git 仓库，remote=`https://github.com/kerpopule/hermes-jev-skills.git` |
| Hermes 路由池 | `~/.hermes/jev/routing.json` | 已确认，仍是 `openrouter:*` 模型 |
| Codex 路由池 | `~/.codex/jev-routing.json` | 已确认，relay 实拉 699 模型 |
| 生成脚本 | `/tmp/build_codex_routing.py` | **不存在**（与 AGENTS.md 描述不符，待核实） |
| 验证脚本 | `/tmp/verify_routing.py` | **不存在**（同上） |

JEV MCP 工具定义（来自 server.py 和 Skill，已核实）：

| 工具 | 输入 | 输出 | 副作用 |
|---|---|---|---|
| `jev_decide` | `state`, `questions`, `model="jev"` | `{ok, model, answers, usage, request}` | 只读网络调用 |
| `jev_yes_no` | `state`, `question`, `no_text`, `mode`, `model` | 同上 | 只读网络调用 |
| `jev_guard_tool_call` | `tool`, `action`, 等 | 同上 | 只读建议，不执行工具 |
| `jev_route` | `task`, `options`, `model` | 同上 | 只读网络调用 |
| `jev_front_door` | `task`, `model` | `{gate, gate_raw, route, hint}` | 只读，可能 shell 调 CLI |

## 6. GitHub 行情采集 Workflow

### 6.1 上游仓库

| 项 | 值 |
|---|---|
| 上游仓库 | `ZhuLinsen/daily_stock_analysis` |
| 默认分支 | `main` |
| 可见性 | public |
| 每日 Workflow | `.github/workflows/00-daily-analysis.yml`，名称「每日股票分析」 |
| 触发 | `schedule: 0 10 * * 1-5`（UTC）= 北京 18:00 工作日；workflow_dispatch 手动 |
| 最近运行 | 2026-10-19 10:12 成功（run #110） |
| 并发控制 | `concurrency: stock-analysis`，cancel-in-progress false |
| 超时 | `ANALYSIS_TIMEOUT_MINUTES`，默认 30 |
| 权限 | workflow 未显式声明 `permissions`（在文件头部未见）；上传 artifact 使用 `actions/upload-artifact@v6` |
| 输入 | `STOCK_LIST` 通过 Repository variable/Secret 或 Environment variable 注入 |

### 6.2 用户 fork

| 项 | 值 |
|---|---|
| Fork | `xia950704/daily_stock_analysis` |
| 默认分支 | `main` |
| 可见性 | public |
| 每日 Workflow ID | `301272192`，state active |
| 最近运行 | 2026-10-20 00:00 成功（每 4 小时由 heartbeat 触发） |
| Heartbeat wrapper | `~/.hermes/scripts/wrappers/github_stock_heartbeat.sh` |
| Heartbeat cron | Hermes cron `github-stock-heartbeat`，每 4 小时工作日触发，last_status=ok |

## 7. Hermes Cron（股票相关）

| Job | 时间（Asia/Shanghai） | 状态 | 最近状态 |
|---|---|---|---|
| 投研每日任务 v3 | 工作日 08:03 | enabled | - |
| investment-pipeline-daily | 工作日 15:15 | enabled | 2026-10-19 ok |
| stock-daily-data-fetch | 工作日 15:30 | enabled | 2026-10-19 ok |
| stock-ranking-daily | 工作日 16:30 | enabled | 2026-10-19 ok |
| risk-anomaly-daily | 工作日 16:35 | enabled | - |
| stock-price-alert | 工作日 21:35 | enabled | 2026-10-19 ok |
| stock-mail-router | 工作日 21:30 | enabled | 2026-10-19 ok |
| 每日收盘-全量行情 | 工作日 15:30 | **disabled/paused** | 曾依赖 data-science skill 批量更新，待核实是否应恢复 |
| 模拟投资每日监控 | 工作日 16:00 | disabled | - |
| 512400-price-alert | 工作日 11:00 | enabled | - |
| 512400-price-alert-afternoon | 工作日 14:30 | enabled | - |
| etf-weekly-tracking | 周六 11:00 | disabled | - |
| github-stock-heartbeat | 工作日每 4 小时 | enabled | 2026-10-20 08:00 ok |
| 投研周检执行 v2 | 周日 11:00 | enabled | - |

## 8. 待核实 / 风险项

- `/tmp/build_codex_routing.py` 与 `/tmp/verify_routing.py` 不存在，AGENTS.md 描述的生成脚本路径已失效。
- `~/.hermes/workspace/stock_daily/` 在 Skill 中仍被引用，但实际数据在 `~/harness/stock_daily/`。
- `stock-research/SKILL.md` 引用的部分脚本（如 `~/stock_ml_trading` 内）未逐文件验证可运行。
- `01-股票投研/scripts/` 仅有 `valuation_update.py`，其余脚本入口在 Hermes 和移动硬盘脚本目录。
- Obsidian Vault 有未提交变更（2026-10-19/20 新增的每日检查、gfdma、ETF 等），不在本 P0 处理范围。
- 上游 GitHub 仓库每日分析每天 18:00 运行，fork 每日分析工作流被 heartbeat 每 4 小时触发，两者运行状态需后续健康检查。
