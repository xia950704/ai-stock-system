# P6-0 基线与当前状态核查

> 生成时间：2026-10-20 23:00 (Asia/Shanghai)

## 一、Decision Model 构建状态：COMPLETE

证据：
- `src/decision/contract.py` 与 `src/decision/registry.py` 完整存在，无锁文件或未完成标记。
- P4 回归测试 `test_backtest.py` 中 9 项 Decision Model 契约/注册表测试（C1‑C4、R1‑R5）全部 PASS。
- `p4-audit/decision-model-contract.md` 已定义统一输入输出契约，`decision-model-options.md` 候选模型区域保持空白。
- 无其他并发任务修改 `src/decision/` 或 `src/jev/` 的证据（文件 mtime 均早于 2026-10-20 18:33，无 `.lock/.tmp`）。

结论：Decision Model 框架已完成，本阶段不重建该框架，仅在其外部评估 JEV 适配层。

## 二、Search API 状态

- 配置文件：`/Users/xiashuang/AI-股票系统/.env`
- 已填字段：`SEARCH_API_BASE_URL=http://127.0.0.1:31415/v1/search`、`SEARCH_API_KEY`（长度 59，未打印）
- 代码读取方式：`src/search/client.py` 在导入时调用 `_load_dotenv()`，从 Workspace 根目录 `.env` 加载配置（环境变量优先）
- 真实调用：累计执行 3 次只读查询（含 P6 收尾复验 1 次），均返回 5 条结果，状态 `ok=True`
- 来源追溯：返回包含 `title`、`url`、`content`、`score`；`published_at` 未提供，保持 `None`
- 新增测试：T-P6-16/17/18 验证 `.env` 加载、环境变量优先、无 key 降级

## 三、JEV 状态

- 本地 key 文件存在：`~/.hermes/mcp-servers/jev-systemone/.key`（51 字节）
- 环境变量 `JEV_API_KEY` / `BYNARA_API_KEY` 未设置（使用 MCP `.env` 中的 AMD key）
- 代码默认后端：`transport=mcp`、`provider=amd`、`model=Clef`
- **真实调用**：在本次 P6 执行期间，`jev_yes_no` 共计 **53** 次，`jev_route` **1** 次，全部返回 `ok=true`（其中 109 条 `ok=true` 包括其他工具调用），未出现解析错误或超时。日志位于 `~/harness/logs/jev/jev_calls.jsonl`，记录显示模型 `Clef` 正常响应。
- 因此 JEV 调用状态为 **PASS**，满足运行资格检查中的第 5、6 项要求。
- 本地 `/v1/decisions`（FreeLLMAPI）与每日引擎 JEV 适配器是两条独立链路，互不影响。

## 四、历史数据状态

- 锚价快照：仅 `2026-09-23` 一个日期
- 排名快照：无历史版本，仅当前 `stock_ranking.json`（run_date=2026-10-20）
- 完整输入（PRICE+ANCHOR+RANKING）：**0 天**

## 五、本阶段新增/修改文件（含回滚基线）

| 文件 | 操作 | 前置 SHA‑256 | 后置 SHA‑256 |
|------|------|-------------|-------------|
| `src/engine/jev_adapter.py` | 修改 | `3d1c88ee4b15e5fc8227b5a6af4abf1aa77936daea0309a08e0ecf3b0aed1eac` | 见 `scratch/p6-prechange-hashes.txt` |
| `p6-audit/tests/test_p6.py` | 新增 | — | — |
| `scratch/p6/citation-ledger.json` | 新增 | — | — |

基线记录：`scratch/p6-prechange-hashes.txt`

## 六、2026-10-21 最终运行复核

本节覆盖上文 2026-10-20 的静态基线，以当前文件和真实调用日志为准。

| 项目 | 当前状态 | 证据 |
|---|---|---|
| Decision Model | COMPLETE；候选模型文件保持空白 | `p4-audit/tests/test_backtest.py` 32/32；`p4-audit/decision-model-options.md` |
| JEV 架构 | 每日引擎优先走 MCP stdio，不再直接走 bynara | `src/engine/jev_adapter.py`；`src/jev/mcp_bridge.py` |
| 当前 JEV 后端 | `transport=mcp`、`provider=amd`、`model=Clef` | `jev_adapter.provider_config()` 实跑输出 |
| JEV 真实调用 | PASS；`jev_yes_no` 8/8、`jev_route` 1/1 成功，`ok=true` | `~/harness/logs/jev/jev_calls.jsonl` 2026-10-21 记录 |
| Search API | PASS；真实配置来自 Workspace `.env` | `src/search/client.py`；`~/harness/logs/search/search_calls.jsonl` |
| 行情日期 | 行情所属日 `2026-10-20`，报告日 `2026-10-21`，新鲜度 FRESH | `reports/shadow/e2e_test_20261021_v3.md` |
| 历史完整输入 | 仍为 0 天；新增发现每日雷达报告可补充部分锚价/价格，但不是完整排名快照 | `~/harness/bandwidth_radar/` 25 份报告 |

运行后文件哈希见 `scratch/p6-20261021-postchange-hashes.txt`；备份位于 `scratch/p6-20261021-backup/`。

总体资格：日常研究使用为 **CONDITIONAL PASS**；正式无人值守自动化仍为 **BLOCKED**，原因见 `run-qualification-checklist.md`。
