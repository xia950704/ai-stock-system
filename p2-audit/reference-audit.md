# P2 路径与引用审计报告（reference-audit）

> 生成时间：2026-10-20
> 方法：grep 静态扫描 + 逐文件上下文判断 + 修复后验证测试

---

## 一、路径引用审计表

| reference_id | file_path | line_or_section | old_reference | reference_type | intended_target | proposed_fix | verification_status |
|---|---|---|---|---|---|---|---|
| REF-01 | src/scripts/legacy/stock_signal_extractor.py | L18 | `~/.hermes/workspace/stock_daily` | 运行时代码（失效） | `~/harness/stock_daily` | 改为 `os.environ.get("STOCK_DAILY_DIR", "~/harness/stock_daily")` | FIXED + T-P02 PASS |
| REF-02 | src/scripts/core/stock_ranking.py | L35 | `~/harness/stock_daily` | 运行时代码（硬编码） | 环境变量注入 | 改为 `os.environ.get("STOCK_DAILY_DIR", "~/harness/stock_daily")` | FIXED + T-P05 PASS |
| REF-03 | src/scripts/core/stock_ranking.py | L163 | `~/.hermes/workspace/ml_trend_predictions.json` | 运行时代码（路径存在，文件真实位于该处） | 保持 | 改为 `HERMES_WORKSPACE_DIR` 环境变量，默认保持原值 | FIXED（源码验证） |
| REF-04 | src/scripts/core/stock_ranking.py | L176 | `~/harness/stock_daily` | 运行时代码（硬编码） | 环境变量注入 | 改为 `STOCK_DAILY_DIR` | FIXED（源码验证） |
| REF-05 | src/scripts/fetch/update_anchor.py | L11-12 | `/Users/xiashuang/harness/anchor_status.json` | 运行时代码（硬编码绝对路径） | `~/harness/anchor_status.json` | 改为 `DATA_ROOT` 环境变量 + `os.path.join` | FIXED + T-P01/T-P03/T-P04 PASS |
| REF-06 | src/scripts/fetch/fetch_realtime.py | L25 | `/Users/xiashuang/harness/anchor_status.json` | 运行时代码（硬编码绝对路径） | `~/harness/anchor_status.json` | 改为 `DATA_ROOT` 环境变量 | FIXED + T-P01b PASS |
| REF-07 | src/workflows/wrappers/stock_daily_fetch.sh | L6 | `cd /Users/xiashuang/harness/stock_daily` | Shell 包装器（硬编码） | 环境变量注入 | **保留原样**（见下文说明） | KEPT-BY-DESIGN |
| REF-08 | src/skills/stock-research/SKILL.md | L164 等 | `~/.hermes/workspace/stock_daily` | Skill 文档（历史执行日志） | 历史证据 | **保留原样**（顶部加注未执行，SKILL 本体禁改） | KEPT-BY-DESIGN |
| REF-09 | src/skills/system-warmup-stock/SKILL.md | L18-19 | `~/.hermes/workspace/stock_daily/` | Skill 文档（操作说明，当前失效） | 应指向 `~/harness/stock_daily/` | **保留原样**（加注未执行，待用户确认） | KEPT-PENDING-CONFIRM |
| REF-10 | src/scripts/legacy/*.py（10 个文件） | 各 L30-55 | `HERMES_WORKSPACE` env 默认值含硬编码路径 | 运行时代码（已有 env 机制） | 环境变量 | 已有 `os.environ.get(...)` 模式，P2 不重复改造 | KEPT（机制已存在） |
| REF-11 | src/scripts/legacy/full_market_ml_backtest.py | L35-36 | `~/harness/deeppulse/db/astock.duckdb`、`/Users/xiashuang/harness/stock_daily` | 运行时代码（DB 路径真实存在） | DuckDB 数据库 | **保留原样**并登记（DB 文件经核实存在，11MB） | KEPT-PENDING-CONFIRM |
| REF-12 | docs/rules/vault-rules.md | 多处 | `/Volumes/夏爽` 等 | 规则文档（引用 Vault 内路径） | 历史证据 | 保留 | KEPT-BY-DESIGN |
| REF-13 | src/obsidian/**（镜像） | 多处 | 各类绝对路径 | Obsidian 原始资料镜像 | 只读副本 | **不修改**（镜像保真原则） | KEPT-BY-DESIGN |

## 二、修复与保留决策理由

### 已修复（REF-01 ~ REF-06）
- 全部改为 `os.environ.get(变量名, 原默认值)` 模式：默认值保持原语义，行为零变化；部署时可用环境变量覆盖。
- REF-01 是唯一"失效路径"：`~/.hermes/workspace/stock_daily` 经核实存在目录但非 stock 数据所在地（stock 数据实际在 `~/harness/stock_daily/`），故默认值修正为新路径。
- REF-03 特别注意：`ml_trend_predictions.json` 实际就存放在 `~/.hermes/workspace/`（经 `ls` 核实，文件存在，10-18 更新），该路径**未失效**，仅做环境变量化，默认值不变。

### 保留原样
- **REF-07**（heartbeat 包装器）：该脚本是线上 cron 的调度入口，P2 约束明确禁止修改心跳脚本及其调度配置。Workspace 副本仅作为参考登记。
- **REF-08/13**（SKILL.md 与 Obsidian 镜像）：历史执行日志与镜像保真，改写会破坏证据链。SKILL 文档中的旧路径属于"操作说明引用失效路径"，但 SKILL 本体位于全局目录（`~/.codex/skills/`），P2 禁止修改全局 Skills——因此 Workspace 副本同样保留原样，问题登记待用户决策。
- **REF-11**（DuckDB 路径）：DB 文件真实存在且脚本为 legacy 回测脚本，改造收益低、风险高，登记待确认。

## 三、修复后验证证据

- `test_paths.py`：7/7 PASS，覆盖环境变量生效、缺失降级、失效路径移除、源文件缺失报错、跨模块一致性
- 全部修复文件通过 `python3 -m py_compile` 语法检查
- 修复过程发现并修复 1 个引入 bug：`update_anchor.py`/`fetch_realtime.py` 使用 `os` 但缺 `import os`（测试 T-P01 捕获）

## 四、无法确认的引用

| 引用 | 原因 | 处理 |
|---|---|---|
| `a-share-policy-alpha`（SKILL 中提及的原路径） | 目录已不存在，无法确定意图 | 保留原文，登记 |
| SKILL.md 中 `~/.hermes/workspace` 相关说明 | 是否应改为 `~/harness` 属用户决策 | 保留 + 待确认 |
