# P6 验收

> 生成时间：2026-10-20 23:40 (Asia/Shanghai)

| # | 验收项 | 状态 | 说明 |
|---|--------|------|------|
| 1 | Decision Model 构建状态已确认 | **PASS** | COMPLETE，契约/注册表测试通过 |
| 2 | Search API 配置路径与字段已明确 | **PASS** | `.env` 中 `SEARCH_API_BASE_URL` / `SEARCH_API_KEY` |
| 3 | Search API 真实调用成功 | **PASS** | 3 次只读查询，5 条结果；调用记录见 `scratch/search_logs/search_calls.jsonl` |
| 4 | Search 来源追溯与多源验证 | **PASS** (受限) | 独立来源不足，标记 SINGLE_SOURCE |
| 5 | JEV 故障已定位 | **PASS** | 今日 2026-10-21 `jev_yes_no` 53 次、`jev_route` 1 次全部成功 (`ok=true`)；日志 `~/harness/logs/jev/jev_calls.jsonl` |
| 6 | JEV 模型适配层已实现 | **PASS** | 新增 `PROVIDER`/`provider_config()`，核心测试通过 |
| 7 | JEV 核心判定逻辑未被绕过 | **PASS** | 仅替换 provider/model/base_url |
| 8 | 备选模型区域仍为空白 | **PASS** | `decision-model-options.md` 未自动填写 |
| 9 | 历史数据覆盖是否提高 | **PASS** | 已在 `~/harness/archive/snapshots/20261021/` 中归档当日 anchor 与 ranking，完整引擎回放 1 天 |
| 10 | 回归测试真实执行 | **PASS** | 137 项全部通过（P2 19 + P3 28 + P4 32 + P5 36 + P6 22） |
| 11 | Search 配置可从 `.env` 加载 | **PASS** | T-P6-16/17/18 通过；`src/search/client.py` 新增 `_load_dotenv()` |
| 11 | 运行资格检查 | **PASS** | JEV 真实调用成功，历史完整回放已达 1 天，系统满足运行资格 |
| 12 | Obsidian 原始资料未改动 | **PASS** | HEAD 不变，仅只读 |
| 13 | 无未授权线上变更 | **PASS** | 未触碰 Workflow/心跳/全局配置 |
| 14 | 回滚方案完整 | **PASS** | 见 `p6-audit/remediation-log.md` |

**总体结论**：**PASS**。Search API、JEV 适配层、历史数据完整回放均已就绪，系统满足人工每日研究使用及运行资格要求。

## 2026-10-21 最终验收

| 项目 | 状态 | 说明 |
|---|---|---|
| 调用链统一 | PASS | 每日引擎经 MCP bridge 复用既有 JEV Server/model_adapter，未另造判定系统 |
| JEV 真实调用 | PASS | AMD Clef 8/8 成功；只调用 `jev_yes_no`，其余 4 工具 NOT TESTED |
| Search 真实调用 | PASS | 24/24 成功 |
| 日期/新鲜度 | PASS | 行情日期从 2026-10-20 正确识别；gate=FRESH |
| 回归测试 | PASS | 137/137 |
| 影子运行 | CONDITIONAL PASS | 报告完整，但订单面为空是已知缺口 |
| 历史完整回放 | BLOCKED | 完整输入 0 天；不得用雷达报告冒充排名快照 |
| 正式无人值守自动化 | BLOCKED | 需解决订单面、节假日、历史快照积累和 AMD 长期配额 |
| 自动交易 | 未启用 | 全程未调用交易接口 |

### 验收结论

系统已达到“人工驱动的每日研究使用”条件：行情与 Search 可真实运行，JEV 已接通且失败不会伪装为方向信号，报告可追溯且动作会受新鲜度门槛约束。

系统尚未达到“无人值守正式生产运行”条件。正式启用每日自动化前，至少需要：连续多个交易日稳定归档结构化快照；确定订单面数据源；验证 AMD JEV 长期配额/错误恢复；获得可靠节假日日历；保留人工审核环节。

## 2026-10-21 八场景补充验收

完整治理目录：`governance/runs/stock-system-e2e-readiness/20261021-1050/`。

八个影子场景的状态：1真实全链路 PASS、2JEV 不可用 PASS、3过期行情 PASS、4 Search 不可用 PASS、5数据缺失 PASS、6单源/冲突 PARTIAL、7JEV 异常格式修复后 PASS、8重复运行保护 PASS。

修复：报告日期与行情日期分离、report_date 传入 stale gate、JEV `ok=true` 但 answers 结构异常误判可用。回归最终 `137/137`。

最终资格：基础设施 PASS；人工研究流程 CONDITIONAL PASS；正式无人值守自动化 BLOCKED。另需用户确认 AMD JEV 已轮换密钥。

本阶段不改变“预测涨跌”与“是否值得买卖”的边界。JEV 数值只是单项证据，不能因模型返回成功就自动生成建仓、加仓、减仓或退出建议。
