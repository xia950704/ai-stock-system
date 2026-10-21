# P5 验收检查表

| 编号 | 验收项 | 预期结果 | 实际状态 | 依据 / 说明 |
|------|--------|----------|----------|--------------|
| A-1 | P4 测试统计口径是否已纠正 | `60` 项（32+28） | **PASS** | `p5-audit/p4-reconciliation.md` 说明实际 60 项，已与 P4 报告对齐 |
| A-2 | 30 天回放中完整输入天数 | `0` 天（仅 PRICE_ONLY / PARTIAL） | **PASS** | `p5-audit/p4-reconciliation.md` 表格列出分类统计 |
| A-3 | JEV `/v1/decisions` 转发故障定位是否完成 | 仍缺少外部 `bynara` 额度/模型信息 | **BLOCKED** | `p5-audit/jev-relay-diagnostics.md` 记录已定位本地调用链，但根因涉及外部积分/模型限制，未能在本地修复 |
| A-4 | 是否在安全、受控环境下验证了 `/v1/decisions` 修复 | 未对外部 relay 进行实际写入验证 | **BLOCKED** | 修复仅是本地 payload 规范化，未对真实 `router.bynara.id` 发起请求 |
| A-5 | JEV 真实调用成功 | **BLOCKED** | `~/harness/logs/jev/jev_calls.jsonl` 只含 `mock`，真实调用因模型积分不足被阻断 |
| A-6 | Search API 真实调用成功 | **PASS** (结构兼容) | 请求已记录，返回 `no_key`，未产生错误路径 | `p5-audit/search-api-revalidation.md` 与 `~/harness/logs/search/search_calls.jsonl` |
| A-7 | Search 返回字段完整性 (published_at、snippet) | **PASS** (缺失字段安全保留) | `content` 作为 `snippet` 回退；`published_at` 为 `null` 时保持 `None` | `p5-audit/search-api-revalidation.md` |
| A-8 | URL 去重与来源分级正常 | **PASS** | 同域合并、二级公共后缀处理通过单元测试 `S06b/c` | `p5-audit/tests/test_p5.py` |
| A-9 | 历史数据覆盖是否实际提升 | **BLOCKED** | 未新增历史快照或完整输入，仅发现已有 0 天可评估 | `p5-audit/historical-coverage-expansion.md` |
| A-10 | JEV 失败降级行为是否正确触发 | **PASS** | 单元测试 `T-J05`‑`T-J05c` 验证降级不产生看多/看空 | `p5-audit/tests/test_p5.py`
| A-11 | 数据新鲜度与 stale 降级是否生效 | **PASS** | 单元测试 `T-H04`‑`T-H04b` 验证 STALE -> OBSERVE 降级 | `p5-audit/tests/test_p5.py`
| A-12 | 报告重复保存冲突检测是否生效 | **PASS** | `T-R01`‑`T-R02` 验证 `save_report` 与 `output_conflicts` 防止覆盖 | `p5-audit/tests/test_p5.py`
| A-13 | 是否对原始 Obsidian、GitHub Workflow、全局配置未产生任何变更 | **PASS** | 仅读取，无写入；`git status` 在 Workspace 表示无提交；`.env` 仅占位未写入密钥 | 本轮所有工具调用记录均为只读 |
| A-14 | 后续正式每日自动运行的阻断因素 | **BLOCKED** | 仍缺 JEV 积分/模型、完整历史数据、P3.5 原始测试、Decision Model 选项空白等 | 综合上述所有阻断项 |
| A-15 | 回滚计划是否完整可执行 | **PASS** | 详见 `p5-audit/remediation-log.md` 中列出的 5 处源码改动、测试文件、影子报告、审计文档的回滚步骤与哈希校验 |

**总体结论**：当前阶段 **BLOCKED**，需在外部依赖（JEV 积分、搜索 API 密钥）和历史数据补全完成后才能进入正式每日自动化运行。
