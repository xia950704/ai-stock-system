# P0 架构提案（architecture-proposal）

> 生成时间：2026-10-20。P0 只读探查产物。
> 基于依赖地图与风险登记，提出 Workspace 内的目标目录结构与模块边界。

## 1. 总体原则

1. **只读副本**：所有从 Obsidian 复制的文件仅作参考，禁止在副本上编辑。
2. **数据流单向**：行情 → 清洗 → 机器产出 → 人工判断 → 报告，禁止逆向写回源数据。
3. **解耦绝对路径**：所有配置、脚本使用相对路径或环境变量，禁止硬编码 `/Volumes/夏爽` 或 `/Users/...` 绝对路径。
4. **模块内聚**：同一功能的脚本、配置、文档放在同一目录下。
5. **可追溯**：每个产出文件必须标注数据来源、生成时间、Git SHA（如适用）。

## 2. 目标目录结构（相对 Workspace 根）

```
AI-股票系统/
├── docs/                     # 架构、决策、会议记录
├── p0-audit/                 # 本次探查产物（只读）
├── src/
│   ├── data/                 # 数据湖：只存机器产出，不存原始笔记
│   │   ├── raw/              # 原始行情快照（来自 harness / websource）
│   │   │   ├── prices/       # realtime_prices_*.json
│   │   │   ├── anchor/       # anchor_status_*.json
│   │   │   └── fundamentals/ # 财务、PE、分红等
│   │   ├── processed/        # 清洗后、标准化后的数据
│   │   │   ├── portfolio/    # 股票组合快照
│   │   │   ├── rankings/     # 综合排名、GF-DMA 等
│   │   │   └── indicators/   # 技术指标、信号
│   │   └── archive/          # 按日期归档的历史快照（如 daily/2026/10/20）
│   │
│   ├── scripts/              # 可执行脚本（无副作用的数据处理）
│   │   ├── fetch/            # 行情抓取（腾讯、东财、雅虎等可插拔）
│   │   ├── transform/        # 数据清洗、标准化、合并
│   │   ├── analyze/          # 计算因子、得分、排名
│   │   ├── report/           # 生成 Markdown/HTML/JSON 报告
│   │   └── utils/            # 公共函数（日志、路径、日期）
│   │
│   ├── obsidian/             # 只读副本：Obsidian 笔记的镜像（只增不改）
│   │   ├── 01-股票投研/      # 镜像 Obsidian 对应目录
│   │   │   ├── 股票/         # 个股笔记（不编辑，仅作索引）
│   │   │   ├── ETF/
│   │   │   ├── data/         # 按日期子目录存机器产出（只读）
│   │   │   ├── 01-股票分析框架.md
│   │   │   ├── 04-医药股票跟踪池.md
│   │   │   └── ...
│   │   └── 99-归档/          # 镜像归档目录（只读）
│   │
│   ├── jev/                  # JVP 决策模块：仅调用 MCP，不修改状态
│   │   ├── client.py         # 轻量包装：jev_decide / jev_yes_no / jev_guard
│   │   └── cache/            # 判断结果缓存（可选）
│   │
│   ├── trading/              # 配对交易系统（只读镜像 + 可选回测）
│   │   ├── run.py            # 镜像 stock_ml_trading/run.py
│   │   ├── data/             # 只读：auto_trade_state.json、logs/
│   │   └── backtest/         # 回测脚本与结果（仅作分析）
│   │
│   └── workflows/            # 工作流定义与本地调度
│       ├── cron/             # 本地定时任务（可选，替代 Hermes cron）
│   │       ├── jobs.yaml     # 定时任务声明
│   │       └── wrappers/     # 包装脚本（如 email、notification）
│   │       └── scripts/      # 调度核心（如调用 src/scripts/*）
│   │
│   └── tests/                # 测试用例（P2 将补全）
│       ├── unit/             # 单元测试
│   │       ├── integration/  # 集成测试
│   │       └── fixtures/     # 测试数据样本
│
├── logs/                     # 本地运行日志（不写入 Obsidian）
├── reports/                  # 人工判断产出（Markdown 报告）
│   ├── daily/                # 每日大盘/个股判断
│   └── weekly/               # 每周复盘
│
└── tmp/                      # 临时目录，自动清理（不提交）
```

## 3. 模块职责划分

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| data.fetch | 从多来源抓取行情、基本面、新闻 | 配置（交易所/代码列表） | raw/ 中的时间戳文件 |
| data.transform | 清洗、去重、填补缺失、时对齐 | raw/ | processed/ 中的统一格式（JSON/CSV） |
| data.analyze | 计算因子（技术面、基本面、情绪面）、得分、排名 | processed/ | rankings/、indicators/ |
| data.report | 生成可阅读的报告（Markdown/HTML） | rankings/、indicators/、processed/ | reports/ 中的文件 |
| obsidian.mirror | 只读同步 Obsidian 笔记（增量） | Obsidian Vault | obsidian/ 目录（只读） |
| jev.client | 通过 MCP 调用 JEV 得到二值/概率判断 | state + question（来自分析模块） | 概率/选择 + 置信度 |
| trading.execution | 配对交易信号生成与回测（不下单） | 配对列表、历史价格 | 信号文件、回测报告 |
| workflow.scheduler | 本地定时调度（可替代 Hermes cron） | jobs.yaml | 调用 src/scripts/* 并记录日志 |
| docs.governance | 架构、决策、风险、迁移计划 | P0 产出 | docs/ 中的文档 |

## 4. 数据所有权与流动规则

- 原始数据权威源：Obsidian 笔记（只读）。
- 行情数据权威源：抓取脚本产出的 raw/（如腾讯价格），但需标注来源与时间。
- 机器产物权威源：processed/ 中的数据（已清洗、可溯源）。
- 人工判断权威源：reports/ 中的 Markdown（结论 + 数据日期/来源 + 文件链接三者齐全）。
- JEV 判断：仅作辅助，结论中必须标注“JEV 辅助：概率 X，置信度 Y”。
- 所有产出文件禁止写回 Obsidian 或原始数据路径。
- 所有产出文件必须包含生成时间戳（文件名或 frontmatter）。

## 5. 技术选项与迁移建议

- **脚本语言**：保持 Python 3.9+，避免 shell 脚本复杂逻辑。
- **依赖管理**：使用 requirements.txt 或 uv，禁止全局污染。
- **日志**：统一使用 Python logging，输出到 logs/ 与 stdout。
- **配置**：使用 yaml 或 toml，环境变量注入，禁止硬编码。
- **测试**：P2 阶段使用 pytest 编写单元与集成测试，覆盖数据清洗、因子计算、报告生成。
- **定时任务**：初期可保留 Hermes cron，逐步迁移至本地 workflow.scheduler（使用 APScheduler 或 cron + 包装）。
- **通知**：保留 iMessage、邮箱等渠道，但需在 wrapper 中统一错误处理与重试。

## 6. 与现有系统的映射（P1 迁移参考）

| 现有位置 | 建议目标位置 | 说明 |
|---|---|---|
| `~/harness/stock_daily/` | `src/data/raw/prices/`、`src/data/raw/anchor/`、`src/data/processed/portfolio/` | 按类型分层 |
| `~/obsidian/all about xia/01-股票投研/` | `src/obsidian/01-股票投研/`（镜像） | 只读增量同步 |
| `~/obsidian/all about xia/01-股票投研/data/gfdma/` | `src/data/processed/rankings/gfdma/` | 机器产出搬迁 |
| `~/harness/stock_daily/stock_ranking.json` | `src/data/processed/rankings/general/latest.json` | 按日期归档 |
| `~/harness/stock_daily/anchor_status.json` | `src/data/raw/anchor/latest.json` | 按日期子目录 |
| `/Volumes/夏爽/migration-20260922/hermes-scripts/` | `src/scripts/fetch/`、`src/scripts/transform/`、`src/scripts/analyze/` | 按功能拆分 |
| `~/stock_ml_trading/` | `src/trading/`（镜像 + backtest/） | 只读镜像，回测放在 backtest/ |
| `~/.hermes/mcp-servers/jev-systemone/` | `src/jev/client.py`（薄包装） | 仅保留调用逻辑，不复制服务器 |
| `~/.hermes/cron/wrappers/` | `src/workflows/wrappers/` | 本地通知与日志包装 |
| `~/.hermes/cron/jobs.yaml`（概念） | `src/workflows/cron/jobs.yaml` | 本地定时任务声明 |
| `~/agent-workspace/AGENTS.md` | `docs/rules/workspace-rules.md` | 工作区规则沉淀 |
| `~/obsidian/all about xia/AGENTS.md` | `docs/rules/vault-rules.md` | vault 规则沉淀 |

## 7. 风险与对策（摘自 risk-register，提出缓解措施）

- 风险 R-S01/H（明文 API Key） → P1 中使用环境变量或 secret manager，不写入仓库。
- 风险 R-DQ01/H（单一来源行情） → P2 中增加多源抓取与故障切换。
- 风险 R-T01/M（JEV 网络依赖） → 在分析中明确标注“JEV 辅助”，网络不可用时降级为仅基于规则判断。
- 风险 R-D04/M（硬编码绝对路径） → P1 中统一使用环境变量 `DATA_ROOT` 或相对路径。
- 风险 R-A02/H（GitHub secret 过期） → 增加监控与自动提醒工作流（可选）。

## 8. 下一步（P1 重点）

1. 在 Workspace 内创建上述目录结构（src/、docs/、logs/、reports/、tmp/）。
2. 编写数据抓取脚本（src/scripts/fetch/）实现多源行情与基本面下载（可选腾讯、东财、新浪）。
3. 编写数据清洗脚本（src/scripts/transform/）处理缺失、异常值、时对齐。
4. 编写因子计算与排名脚本（src/scripts/analyze/）实现 GF-DMA、锚价偏离等。
5. 编写报告生成脚本（src/scripts/report/）输出 Markdown 到 reports/。
6. 制作只读镜像：使用 rsync 或 cp --reflink 同步 Obsidian 笔记到 src/obsidian/（只读）。
7. 编写 JEV 轻量客户端（src/jev/client.py）仅调用 MCP，不做本地状态。
8. 编写本地定时任务声明（src/workflows/cron/jobs.yaml）逐步替换 Hermes cron。
9. 编写单元与集成测试（src/tests/）覆盖数据清洗与因子计算。
10. 撰写数据所有权与迁移手册（docs/migration-guide.md）。
11. 在 P1 完成后，提交审计并等待批准进入 P2。
