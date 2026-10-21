# P5 回归测试报告

> 生成时间：2026-10-20 22:45:12 (Asia/Shanghai)
>
> **测试套件概览**

> | 套件 | 通过 | 失败 | 跳过 | 说明 |
> |------|------|------|------|------|
> | **P2** (19) | **19** | 0 | 0 | 环境变量、路径、异常安全 – 完全通过 |
> | **P3** (28) | **28** | 0 | 0 | 引擎、数据加载、交易日、报告生成 – 完全通过 |
> | **P4** (32) | **32** | 0 | 0 | 回放、评估、Decision Model 合约 – 完全通过 |
> | **P5** (36) | **36** | 0 | 0 | 新增 Search 结构兼容、URL 去重、来源分级、JEV 请求契约、历史数据缺失、新鲜度、重复报告保护等 |
> | **总计** | **115** | 0 | 0 | **所有 115 项测试通过** |
>
> **P3.5（搜索&新鲜度）**
>
> - *原始 21 项测试* 位于 `p35-audit`，该目录缺失完整测试源码，无法在本轮执行中复现。因此在本报告中标记为 **NOT TESTED**。
> - 本轮 **P5** 通过的 36 项单元测试已覆盖 **P3.5** 的核心功能块：
>   - Search API 实际返回结构兼容（`content` → `snippet` 备份）
>   - URL 归一化、百分号解码、同域合并（二级公共后缀）
>   - 官方发行人 `baili‑pharm.com` 归为 tier 1
>   - 多源独立计数及冲突检测
>   - 搜索错误码统一 (`no_key`、`auth`、`rate_limited`、`server_error`、`no_provider_key`)
>   - 数据新鲜度门槛 (`STALENESS`、`DATE_UNKNOWN`) 与对应降级
>   - 报告保存冲突检测 (`save_report`、`output_conflicts`)
>
> **真实 Search 调用**
>
> - 通过 `~/harness/logs/search/search_calls.jsonl` 观察到 3 次真实查询（`百利天恒 BL‑B01D1 …`）
> - 均因 `SEARCH_API_KEY` 为空返回 `no_key`，未产生任何检索结果。
> - 这 3 条记录已在 **P5‑2 Search‑API‑Revalidation** 中列出（见 `p5-audit/search-api-revalidation.md`），不计入本轮 115 项计数。
>
> **真实 JEV 调用**
>
> - `~/harness/logs/jev/jev_calls.jsonl` 仅记录 `mock` 模式调用；未出现 `real` 调用记录。
> - JEV 合约的错误分类与降级行为在 **P5‑1 JEV‑Relay‑Diagnostics** 中通过单元测试验证。
>
> **历史数据覆盖**
>
> - 通过 `p5-audit/historical-coverage-expansion.md` 核查，**未**新增任何历史快照或完整输入日期。
> - 仍只有 0 天具备 **PRICE + ANCHOR + RANKING** 完整输入（30 天中全为 `PRICE_ONLY` 或 `PARTIAL`）。
>
> **结论**
>
> - 所有 **本轮执行的 115 项测试全部通过**，且未出现意外错误或遗漏。
> - 仍有**未完成的外部依赖**（Search API Key、JEV 积分/模型）以及**历史回放数据缺口**，这些将在后续阶段解决。
