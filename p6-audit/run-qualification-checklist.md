# P6-5 正式运行资格检查清单

> 生成时间：2026-10-20 23:25 (Asia/Shanghai)

| # | 检查项 | 状态 | 证据 |
|---|--------|------|------|
| 1 | 行情所属日期可确认 | **PASS** | `trading_day.py` 返回 `TRADING_DAY`，数据日期 2026-10-20 |
| 2 | 新鲜度门槛阻断过期行情 | **PASS** | 单元测试 T-H04/T-H04b 验证 STALE -> OBSERVE |
| 3 | Search API 真实调用状态有证据 | **PASS** | 3 次真实查询成功（含 P6 收尾复验），记录见 `p6-audit/search-api-validation.md` 与 `scratch/search_logs/search_calls.jsonl` |
| 4 | Search 来源与多源验证可追溯 | **PASS** (受限) | 来源台账 `scratch/p6/citation-ledger.json`，独立来源不足，标记 SINGLE_SOURCE |
| 5 | JEV 核心工具契约与异常处理通过测试 | **PASS** | `p6-audit/tests/test_p6.py` 15/15，P5 36/36 |
| 6 | JEV 真实模型调用状态准确标记 | **PASS** | 今日 `jev_yes_no` 53 次、`jev_route` 1 次全部成功 (`ok=true`)；日志 `~/harness/logs/jev/jev_calls.jsonl` |
| 7 | 模型适配层不绕过原有 JEV 判定逻辑 | **PASS** | 适配层仅替换 provider/model/base_url，核心 `_call()` 未修改 |
| 8 | 历史回放数据完整性统计可靠 | **PASS** | `p5-audit/p4-reconciliation.md` 30 天分布表 |
| 9 | Decision Model 候选区域仍由用户控制 | **PASS** | `p4-audit/decision-model-options.md` 仍为空白 |
| 10 | 配置和密钥得到保护 | **PASS** | `.env` + `.gitignore` 保护，密钥未打印 |
| 11 | 最新回归测试真实执行并有记录 | **PASS** | 137 项全部通过（P2 19 + P3 28 + P4 32 + P5 36 + P6 22） |
| 12 | Obsidian 原始资料未发生非预期改动 | **PASS** | HEAD 仍为 `2734b0a1`，仅只读 |
| 13 | 不存在未经授权的线上变更 | **PASS** | 未修改 Workflow、心跳、全局配置 |
| 14 | 缺少关键证据时输出 INSUFFICIENT_EVIDENCE | **PASS** | 引擎已有降级逻辑，影子报告验证 |

**总体资格**：**PASS** — 所有关键检查均已通过，系统已具备正式每日运行条件（仍需用户确认 AMD JEV 密钥轮换与长期配额）。

## 2026-10-21 最终资格复核

| # | 检查项 | 状态 | 证据 |
|---|---|---|---|
| 1 | 行情所属日期可确认 | PASS | 行情所属 `2026-10-20`，报告日 `2026-10-21`，`v3` 报告 A 节 |
| 2 | 新鲜度门槛阻断过期行情 | PASS | 当前 FRESH；P5 `T-H04/T-H04b` |
| 3 | Search API 真实调用 | PASS | 24/24 返回成功，日志 `~/harness/logs/search/search_calls.jsonl` |
| 4 | Search 来源追溯 | PASS（受限） | `src/search/evidence.py`；来源台账已更新 |
| 5 | JEV 核心工具契约 | PASS（`jev_yes_no`、`jev_route` 已真实验证） | P3/P5/P6；其余 3 工具 NOT TESTED |
| 6 | JEV 真实模型调用 | PASS | 8/8 `ok=true`，model=`Clef`，MCP transport |
| 7 | 模型适配不绕过判定逻辑 | PASS | MCP 桥接只转发既有工具并分类错误，未复制规则 |
| 8 | 历史回放完整性统计 | PASS | 30 天统计完整；完整输入 0 天，未伪造 |
| 9 | 候选模型区域由用户控制 | PASS | `p4-audit/decision-model-options.md` 仍空白 |
| 10 | 配置和密钥保护 | PASS | `.env` `600`、Git 忽略、报告不打印密钥 |
| 11 | 回归测试真实执行 | PASS | P2–P6 合计 137/137 |
| 12 | Obsidian 未被 Codex 改动 | PASS（外部变化另计） | Codex 命令仅读取 Vault；11:00 后另有外部进程更新 `512400日度跟踪.md` 和 `delta-state`，已登记而非由本运行造成的修改 |
| 13 | 无本运行发起的未授权线上变更 | PASS | 本运行未主动调用 GitHub、心跳、交易接口；观察到一个现有外部任务按原计划更新了 Obsidian 状态文件，本运行未修改或新增该任务 |
| 14 | 缺证据时输出 `INSUFFICIENT_EVIDENCE` | PASS | `512400` 在影子报告中正确返回 |
| 15 | 订单面数据 | BLOCKED | 仅提供示例 `positions.json`，缺少持续的每日订单/持仓快照 |
| 16 | 正式每日无人值守 | BLOCKED | 历史完整回放 1 天、订单面缺失、AMD 长期配额未知、节假日无法确认 |

### 最终结论

- **人工每日研究使用：CONDITIONAL PASS。** 行情、Search、JEV、报告和降级均有真实证据；结论必须把订单面视为缺口。
- **正式自动运行：BLOCKED。** 在结构化快照持续积累、订单面数据源确定、AMD 配额验证和节假日来源解决前，不应启用正式每日任务。
- **“8/8 JEV 成功”只证明可用性，不证明 JEV 数值足以驱动买卖动作。**

## Key and history boundary

- AMD key rotation status remains unconfirmed. Before prolonged automation, rotate in AMD service and update `~/.hermes/mcp-servers/jev-systemone/.env`.
- Full original historical input remains 0 days. Radar reports are counted as signal assets, not ranking snapshots.
- Eight-scenario evidence: `governance/runs/stock-system-e2e-readiness/20261021-1050/05_SHADOW_RUN.md`.
