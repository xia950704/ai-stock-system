# P0 依赖与引用地图（dependency-map）

> 生成时间：2026-10-20。P0 只读探查产物。
> 目标是还原“原始股票数据 → 数据读取与清洗 → 行情采集 → JEV 探查 → 每日分析 → 报告与历史记录”的模块关系。

## 1. 主链路（当前观测）

```text
Obsidian 01-股票投研（权威笔记/池/历史判断）
        │ 只读引用
        ▼
Hermes cron（investment-pipeline / stock-daily-fetch / stock-ranking / stock-price-alert）
        │ 产出
        ▼
~/harness/stock_daily（realtime_prices / anchor_status / stock_portfolio_enriched / stock_ranking）
        │
        ▼
Obsidian data/（daily_check / gfdma / bayesian / verification）
        │
        ▼
Codex/Hermes 分析 Agent（读取 Skill：stock-research、system-warmup-stock）
        │
        ▼
JEV MCP（jev_decide / jev_yes_no / jev_guard / jev_route / jev_front_door）做二值/概率判断
        │
        ▼
每日/周报输出到 Obsidian 01-股票投研/日更/、报告、历史记录
```

## 2. 文件与目录依赖

| 依赖方 | 被依赖 | 形式 | 状态 |
|---|---|---|---|
| stock-research Skill | `~/harness/stock_daily/` | 绝对路径 | 部分存在，SKILL 中旧路径失效 |
| stock-research Skill | `~/obsidian/all about xia/01-股票投研/` | 绝对路径 | 有效 |
| stock-research Skill | `/Volumes/夏爽/migration-20260922/hermes-scripts/` | 绝对路径 | 存在，但依赖移动硬盘挂载 |
| Hermes cron investment-pipeline | `~/.hermes/scripts/investment_pipeline.py` | wrapper 脚本 | 有效 |
| Hermes cron stock-daily-fetch | `~/harness/stock_daily/update_anchor.py` | wrapper 脚本 | 有效 |
| Hermes cron stock-ranking | `~/.hermes/scripts/stock_ranking.py` | cron yaml | 有效 |
| GitHub heartbeat | `xia950704/daily_stock_analysis` fork workflow 301272192 | gh API | 有效，last_status=ok |
| JEV MCP | `https://router.bynara.id/v1/systemone` | 网络 | 配置存在，运行状态 P0 未验证 |
| JEV MCP | `~/.hermes/mcp-servers/jev-systemone/.key` | 本地 key | 存在 |
| Codex relay | `http://127.0.0.1:57321/v1` | 本地 | config.toml 指向 |
| Obsidian Git | `https://github.com/xia950704/obsidian-vault.git` | 远程 | remote 存在 |
| jev-skills | `https://github.com/kerpopule/hermes-jev-skills.git` | 远程 | remote 存在 |

## 3. Skills 调用链

### 3.1 stock-research

- 数据源：`~/harness/stock_daily/`、`~/obsidian/all about xia/01-股票投研/data/`。
- 脚本源：`/Volumes/夏爽/migration-20260922/hermes-scripts/`、`~/stock_ml_trading/`、`~/harness/stock_daily/`。
- 依赖环境变量：`HERMES_WORKSPACE=/Users/xiashuang/harness/stock_daily`。

### 3.2 jev-systemone

- MCP 注册：`~/.codex/config.toml` 的 `[mcp_servers.jev-systemone]`。
- Server：`~/.hermes/mcp-servers/jev-systemone/server.py`。
- CLI：`~/.hermes/jev-skills/bin/jev`。
- 依赖环境变量：`TYPESAFE_BASE_URL`、`TYPESAFE_MODEL=jev`、`JEV_PROXY_API_KEY`。
- 路由池：Codex 侧 `~/.codex/jev-routing.json`，Hermes 侧 `~/.hermes/jev/routing.json`。

### 3.3 配对交易（stock_ml_trading）

- 独立系统，不入股票投研 Skill 的 P0 判断链。
- 依赖 `~/stock_ml_trading/` 内 `config.py`、`run.py`、`strategies/`、`auto_trade_state.json`、`logs/`。
- 系统 crontab 5 条。

## 4. GitHub 行情采集依赖

- 上游 `ZhuLinsen/daily_stock_analysis` 每日 18:00（北京）运行。
- fork `xia950704/daily_stock_analysis` workflow `301272192` 被本地 heartbeat 手动触发，避免 60 天禁用。
- workflow 依赖：`actions/checkout@v5`、`actions/setup-python@v6`、`actions/upload-artifact@v6`、大量 Secrets/Variables（GEMINI/OPENAI/DEEPSEEK/LITELLM 等）。
- `STOCK_LIST` 通过 Repository variable/secret 或 environment 注入。
- **风险**：workflow 显式引用的第三方 Action 版本较新，未审计固定 commit SHA。

## 5. 重复/分叉实现

| 模块 | 位置 | 重复情况 |
|---|---|---|
| 每日行情抓取 | `~/harness/stock_daily/`、`/Volumes/夏爽/migration-20260922/hermes-scripts/`、`~/harness/` 根 | 存在多个 fetch_kline_* 脚本，需 P2 去重 |
| 股票综合排名 | `~/.hermes/scripts/stock_ranking.py`、`/Volumes/夏爽/.../stock_ranking.py` | 两处，需确认唯一事实源 |
| 锚价状态 | `~/harness/anchor_status.json`、`~/harness/stock_daily/anchor_status_*.json` | 权威源在 `~/harness/anchor_status.json`，每日日期版为产物 |
| JEV 路由池 | `~/.hermes/jev/routing.json`（openrouter:*）、`~/.codex/jev-routing.json`（relay 模型） | 结构同构，模型来源不同；Hermes 侧不适用本机 relay |
| 股票笔记 | Obsidian `01-股票投研/股票/` 与 `99-归档/股票投研_已归档/股票/` | 存在大量重复/旧版，不能直接删除 |

## 6. 关键绝对路径 / 挂载依赖

- `/Volumes/夏爽/`：移动硬盘，依赖挂载；多个 Skill 脚本路径引用。
- `/Users/xiashuang/harness/stock_daily/`：Hermes 数据层。
- `/Users/xiashuang/obsidian/all about xia/01-股票投研/`：权威资料。
- `/Users/xiashuang/stock_ml_trading/`：配对交易独立目录。
- `/Users/xiashuang/.hermes/`：Hermes 配置、cron、JEV、MCP。

## 7. 旧工作目录风险

- `~/.hermes/workspace/stock_daily/` 出现在 Skill/日志中，但实际当前使用 `~/harness/stock_daily/`。
- `a-share-policy-alpha` 在 stock-research SKILL 中标记“已不存在”。
- `/tmp/build_codex_routing.py` 和 `/tmp/verify_routing.py` 不存在。

## 8. 未验证 / 待核实

- JEV MCP 实际调用是否可达（P0 未触发真实调用）。
- GitHub 每日分析工作流最近一次报告内容/数据质量。
- Hermes cron 各 job 的日志目录与失败原因（仅读取状态，未深挖日志）。
- `01-股票投研/tools/` 内工具清单。
