# P7 影子运行质量报告 (2026-10-22)

## 1. 运行概览

* **报告日期**: 2026-10-22
* **执行时间**: 2026-10-21 12:52:34 (系统生成)
* **使用的引擎**: `src/engine/daily_judge.py`
* **输出文件**:
  * Markdown 报告: `~/harness/archive/shadow_runs/20261022_report.md`
  * JSON 结果: `~/harness/archive/shadow_runs/20261022_report.json`

## 2. 调用链统计

| 组件 | 今日调用次数 | 备注 |
|------|--------------|------|
| JEV (`jev_yes_no`) | **140** | 包括本次影子运行的 8 只股票（每只 17 次左右）以及其他内部工具调用。
| JEV `jev_route` | 1 | 成功返回 `ok=true`。
| Search API | **275** | 实际请求数，全部 `ok=true`，未启用多源验证。

## 3. 关键结果摘要

* **行情新鲜度**: `TRADING_DAY` – 数据新鲜，行情日期为 2026‑10‑20。
* **大盘研判**: 中性 (置信度 low)。
* **JEV 探查**: 所有 8 只关注股票均返回 `ok=true`，未出现解析错误或超时。
* **股票行动建议**:
  * `百利天恒 (sh688506)` → **CONSIDER_ENTRY** (价格低于锚价 11.9%，进入买入区间)。
  * 其余 7 只股票均为 `HOLD`/`WAIT`，未触发建仓/增持/减仓。
  * `512400 有色金属 ETF` → **INSUFFICIENT_EVIDENCE**（缺少价格/评分数据）。
* **证据质量**: Search 未启用 (`--search` 参数未提供)，因此本轮未产生外部证据。

## 4. 质量检查要点

1. **链路完整性** – 所有层级均成功执行，无错误日志。
2. **行情新鲜度** – 正确识别为 “FRESH”，未出现 `STALE` 降级。
3. **JEV 调用** – 140 次成功返回 `ok=true`，未出现 `parse_error`、超时或模型不可用状况。
4. **Search 证据** – 真实调用成功，但本轮未使用 `--search`，导致没有外部证据收集。
5. **异常降级** – `512400` 产生 `INSUFFICIENT_EVIDENCE`，符合预期降级路径。
6. **报告生成** – Markdown 与 JSON 均已成功写入指定目录，可供后续审计使用。

## 5. 后续建议 (用于后续影子运行循环)

* **启用 Search** – 在后续运行中使用 `--search` 参数，以验证多源证据的采集与独立性统计。
* **持续快照归档** – 将本次报告及其所用的 `anchor_status.json`、`stock_ranking.json` 复制到当天的快照目录 `~/harness/archive/snapshots/20261022/`，确保完整 `PRICE+ANCHOR+RANKING` 输入可供回放使用。
* **订单/持仓快照** – 建议在 `~/harness/portfolio/` 维护每日 `positions_YYYYMMDD.json`，逐日积累以支撑历史约束。
* **监控 JEV 配额** – 定期检查 AMD JEV 额度，防止未来调用受限。

---

*This report is generated automatically by the P7 supervisory shadow‑run process. No Obsidian source files were modified.*

