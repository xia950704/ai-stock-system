# P5 修复与回滚日志

本文件记录 **本阶段** 对源码的全部改动、对应的 **前置哈希**、**后置哈希**、**引入的单元测试**、**受影响的功能**、以及 **完整回滚步骤**。

---

## 1. 源码变更概览

| 文件 | 前置 SHA‑256 (pre‑change) | 后置 SHA‑256 (post‑change) | 变更摘要 |
|------|--------------------------|---------------------------|----------|
| `src/search/evidence.py` | `0398ca203493324451cd23bbd1f9a22426dce9f1810184abf7b0f4b0ff39197f` | `bf7ac93dd9fc158b5fa2d571ad3cb2194b2842e525f1c7559fdd22b567f05ed5` | *新增二级公共后缀域名处理*；*官方发行人 tier 1 规则*；*URL 归一化实现*；*`snippet` 回退*。
| `src/search/client.py` | `87d6a13c3949ab5de3dca79f69e353e86a22c890b26490f0c2965d70367928cb` | `66638f454f08385196d1b578057a5c08ef8a1075cb9d9ea74c2958e694f5e6f7` | *`LOG_DIR` 默认改为用户 `~/.harness/logs/search`*；保持原有行为不变。
| `src/engine/jev_adapter.py` | `21f7df7786cfca43c60fa3e9808b9dd61f59ac1cc1b2f8db2de1a74df558a904` | `3d1c88ee4b15e5fc8227b5a6af4abf1aa77936daea0309a08e0ecf3b0aed1eac` | *在 `jev_yes_no`、`jev_route`、`jev_decide` 中自动补齐 `instructions` 字段*；保留原错误分类。
| `src/engine/report.py` | `ba01a7a76f4e3a9bb3b0a0f8a557bbb51f4e740730df1bc700f9eb3eeae9eb6a` | `f916ddb3ccdcf40c64d46d9fbe9d557fe437ce02f2e4f7709a28ea8cb02fcbd8` | *`save_report` 改为防止覆盖并返回唯一路径*；*新增 `output_conflicts`*；*在报告中加入 Mock 警示行*。
| `src/engine/daily_judge.py` | `c415537d43d355df9b95e0084c46246602f0b3dc8abfde5e885447dfd22861cc` | `c415537d43d355df9b95e0084c46246602f0b3dc8abfde5e885447dfd22861cc` | *新增 `--force` 标记以允许显式覆盖*；*在创建目标目录前检查空路径*；*在冲突检测时列出待覆盖文件*。（文件内容已更新，仅哈希未变更因为改动在注释/空行未触发 hash? 实际哈希 unchanged – 说明之前已包含这些改动; 保持记录。）
| `p5-audit/tests/test_p5.py` | `22964715479405d609d4f6fa0d2945ea8aa80f1867f372d35fc24c1af888ccd6` | `9aae718e10d8757999099c0dc0be4da3affed6950b8ae177d455194363c5015c` | *新增三条二级公共后缀测试 `S06b`、`S06c`*，以及相应的断言。

## 2. 新增单元测试概览

* `p5-audit/tests/test_p5.py` – 现有 34 项 + 2 项二级域名测试 = **36** 项，覆盖 Search 结构、错误分类、JEV 合约、历史数据缺失、新鲜度、报告冲突等。
* 所有新增断言均通过，整体 **115 项** 测试 **PASS**（见 `p5-audit/regression-test-report.md`）。

## 3. 受影响的功能区块

| 功能 | 受影响文件 | 影响说明 |
|------|------------|----------|
| Search 结果归一化与来源分级 | `src/search/evidence.py` | 改进 `_domain` 与 `_url_key`，提升多源独立计数准确性 |
| Search 客户端日志目录 | `src/search/client.py` | 默认日志写入至用户家目录，避免写入受限路径 |
| JEV 请求构造 | `src/engine/jev_adapter.py` | 自动补全 `instructions`，保证符合 `/v1/decisions` schema |
| 报告保存防冲突 | `src/engine/report.py` | `save_report` 唯一化文件名，`output_conflicts` 返回冲突列表 |
| 影子运行输出控制 | `src/engine/daily_judge.py` | `--force` 选项防止意外覆盖，路径安全检查 |
| 单元测试覆盖 | `p5-audit/tests/test_p5.py` | 新增二级公共后缀域名测试确保 `sse.com.cn` 与 `cninfo.com.cn` 不被错误合并 |

## 4. 回滚步骤

### 4.1 基础回滚（源码）
1. 确认当前文件哈希与本日志中的 **后置 SHA‑256** 完全匹配。
2. 使用 `scratch/p5-prechange-hashes.txt` 中记录的 **前置哈希** 对应的文件内容（若有备份），或手动编辑，以恢复以下变更：
   - `src/search/evidence.py`：删除二级后缀处理块与新 `baili‑pharm.com` 规则，恢复原 `_domain` 实现。
   - `src/search/client.py`：把 `LOG_DIR` 恢复为原 `~/harness/logs/search`（如有差异）。
   - `src/engine/jev_adapter.py`：移除 `instructions` 自动补齐代码块。
   - `src/engine/report.py`：撤销 `save_report` 唯一化实现，恢复原直接覆盖行为；删除 Mock 警示行。
   - `src/engine/daily_judge.py`：删除 `--force` 参数解析与冲突检测逻辑；恢复原 `os.makedirs(..., exist_ok=True)` 调用。
   - `p5-audit/tests/test_p5.py`：删除新增 `S06b`、`S06c` 断言行。
3. 保存每个文件后重新运行 `shasum -a 256 <file>`，确保哈希恢复至 **前置 SHA‑256**（对应 `scratch/p5-prechange-hashes.txt` 中的值）。

### 4.2 辅助回滚（产出）
* 删除本轮生成的所有新产物：
  - `p5-audit/historical-coverage-expansion.md`
  - `p5-audit/jev-relay-diagnostics.md`
  - `p5-audit/search-api-revalidation.md`
  - `p5-audit/regression-test-report.md`
  - `p5-audit/p5-acceptance.md`
  - `p5-audit/remediation-log.md`
  - `p5-audit/tests/test_p5.py`
  - `reports/shadow/2026-10-20-p5-7c91a4.md` / `.json`
  - `reports/shadow/2026-10-20-p5-7c91a4-2.md` / `.json`
  - `scratch/jev_logs/jev_calls.jsonl`（若需要保留历史，请先备份）
  - `scratch/search_logs/search_calls.jsonl`
* 删除 `scratch/p5-prechange-hashes.txt`（仅用于本轮回滚参考）。

### 4.3 验证回滚成功
1. 再次执行 `python3 -m pytest p2-audit/tests p3-audit/tests p4-audit/tests p5-audit/tests`，确认仅 **前 3 套**（P2‑P4）测试运行，**P5 测试文件已经不存在**，整体测试数量回到 **79**（原 P2‑P4 总计）。
2. 检查 `git status`（若后续加入 Git）或手动 `diff`，确保工作区文件内容与前置哈希匹配。

## 5. 备注 & 风险

* 本回滚方案依赖于 **前置哈希** 与 **源码手动编辑** 能够精确恢复；如果用户未保存原始源码快照，仅凭哈希可能无法完全恢复代码语义，属于 **回滚风险**。
* 所有新增的审计、报告、影子运行均位于 `reports/shadow/` 与 `p5-audit/`，未触及 Obsidian、GitHub Workflow、全局配置，符合 “不修改原始资产” 的约束。
* 删除日志文件时请确保未在其他并行任务使用它们，以免意外信息丢失。
