# P0 风险登记表（risk-register）

> 生成时间：2026-10-20。P0 只读探查产物。
> 风险等级：高（H）、中（M）、低（L）。

## 1. 安全风险

| ID | 描述 | 等级 | 状态 |
|---|---|---|---|
| R-S01 | Hermes .env 含明文 API Key（JEV_PROXY_API_KEY 等） | H | 已知（P0 未打印值，需确认是否已清空） |
| R-S02 | GitHub Actions workflow 中使用未固定版本的 Action（如 actions/checkout@v5 可能更新） | M | 需要审计固定 SHA |
| R-S03 | Jev MCP key 存放在 ~/.hermes/mcp-servers/jev-systemone/.key，文件权限 600，但可能被备份泄漏 | L | 需要检查备份策略 |
| R-S04 | 移动硬盘路径（/Volumes/夏爽）在 Skill 中硬编码，若未挂载导致脚本失效 | M | 依赖外部挂载 |

## 2. 数据质量风险

| ID | 描述 | 等级 | 状态 |
|---|---|---|---|
| R-DQ01 | 行情数据来源单一（腾讯 API），若失效无备源 | H | 缺少备用行情源 |
| R-DQ02 | 锚价状态依赖人工维护的 anchor_status.json，更新依赖脚本 | M | 无自动审计机制 |
| R-DQ03 | 股票综合排名依赖多因子，权重未在代码中显式给出（可能在脚本内硬编码） | M | 需要审计因子说明 |
| R-DQ04 | Obsidian 中个股笔记与跟踪池可能不同步（人工维护） | M | 无自动校验机制 |
| R-DQ05 | 日更/报告目录可能被人工误删或重命名 | L | 缺少防护 |

## 3. 风险与工具调用

| ID | 描述 | 等级 | 状态 |
|---|---|---|---|
| R-T01 | JEV MCP 调用依赖外部网络（bynara.id），超时设置 60s，可能受网络波动影响 | M | 未测试真实调用 |
| R-T02 | stock-research Skill 中登记的脚本路径（/Volumes/夏爽/migration-20260922/hermes-scripts/）依赖移动硬盘挂载 | M | 若硬盘未挂载则失效 |
| R-T03 | Hermes cron 中许多 job 使用包装脚本（wrappers/...sh），若 wrapper 路径错误导致静默失败 | L | 需要检查 wrapper 是否存在 |
| R-T04 | 某些脚本（如 update_anchor.py）可能依赖 Python 库未在 Skill 中声明 | L | 需要确认依赖隔离 |
| R-T05 | GitHub 工作流需要大量 Secret（GEMINI_API_KEY 等），若泄漏会导致滥用 | H | 已知风险，需确认是否使用最小权限 |

## 4. 风险与依赖/引用

| ID | 描述 | 等级 | 状态 |
|---|---|---|---|
| R-D01 | Obsidian 原始资料被误修改的风险（人工操作） | H | P0 禁止任何写回 |
| R-D02 | Workspace 副本与 Obsidian 源失效（如文件移动、重命名） | M | 需要来源映射与定期校验 |
| R-D03 | JEV 路由池（Hermes 侧）引用 openrouter:* 模型，但本机 relay 不服务这些 ID，可能导致 404 | H | 已知，Codex 侧有独立路由池 |
| R-D04 | 脚本中出现硬编码绝对路径（如 /Users/xiashuang/...），导致不可移植 | M | 大量存在 |
| R-D05 | 风险与数据留存：旧脚本、旧数据、备份未清理，可能混淆版本 | L | 需要梳理 |

## 5. 风险与自动化（Cron / Workflow）

| ID | 描述 | 等级 | 状态 |
|---|---|---|---|
| R-A01 | 每日收盘-全量行情 job 被标记为 disabled/paused，原因不明 | M | 需要确认是否应恢复 |
| R-A02 | GitHub workflow “每日股票分析” 依赖 secrets 大量注入，若过期将导致持续失败 | H | 需要监控 secret 有效期 |
| R-A03 | Hermes cron 中 investment-pipeline-daily 与 stock-daily-data-fetch 两个任务时间相近（15:15 / 15:30）可能竞争资源 | L | 建议错峰 |
| R-A04 | GitHub 行情 workflow 心跳（xia950704/daily_stock_analysis）每 4 小时触发，可能被 GitHub 视为滥用 | L | 当前间隔 4h，需确认策略 |
| R-A05 | 风险与并发：同一时间运行多个 Job（如 ranking、价格告警、邮件路由）可能导致 I/O 竞争 | L | 无锁机制 |

## 6. 风险与治理

| ID | 描述 | 等级 | 状态 |
|---|---|---|---|
| R-G01 | 缺少统一的数据校验标准（如价格、PE、锚价偏离） | M | 需要定义可接受范围 |
| R-G02 | 缺少异常告警机制（如数据缺失超过 N 天自动升级） | M | 需要定义阈值 |
| R-G03 | 缺少 P0 产物的审计追溯（如谁何时导出了什么数据） | L | 建议增加导出日志 |
| R-G04 | 风险与知识孤岛：只有部分人知道某些脚本的作用 | M | 需要文档化与交叉培训 |

## 7. 待验证 / 待核实项

- JEV MCP 在本机 relay 上的实际可达性（P0 未调用）。
- GitHub 每日分析工作流的最近一次运行产出是否符合预期（报告、数据）。
- Hermes cron 各 job 日志中是否有错误堆栈（仅看了 last_status=ok）。
- stock-research 中登记的脚本是否全部存在且可运行（未逐个测试）。
- 移动硬盘 /Volumes/夏爽 在极端情况下（未挂载、只读）对系统的影响。
