# 人工监督运行流程（可重复）

## 概述
本流程描述如何在不修改任何外部系统的情况下，重复执行每日研判引擎并生成报告与快照。

## 前置条件
- Workspace 根目录为 `/Users/xiashuang/AI-股票系统`
- 已配置 `.env`（Search API）
- 已配置 JEV MCP Server（AMD Clef）
- 已存在 `~/harness/stock_daily/` 数据目录

## 步骤

### 1. 准备数据
1. 确保当日行情已更新（运行 `update_anchor.py`）。
2. 确保 `stock_ranking.json` 已更新。
3. 如需持仓快照，将 `positions.json` 复制到 `~/harness/archive/snapshots/YYYYMMDD/`，并标记 `"sample": true`（若为示例）。

### 2. 运行研判引擎
```bash
python3 src/engine/daily_judge.py --search --output ~/harness/archive/shadow_runs/YYYYMMDD_report.md --json
```
若不启用 Search，可省略 `--search`。

### 3. 归档快照
```bash
mkdir -p ~/harness/archive/snapshots/YYYYMMDD
cp ~/harness/anchor_status.json ~/harness/archive/snapshots/YYYYMMDD/anchor_status.json
cp ~/harness/stock_daily/stock_ranking.json ~/harness/archive/snapshots/YYYYMMDD/stock_ranking.json
```

### 4. 记录证据
- 保存 `daily_judge` 控制台输出到日志。
- 将 `search_calls.jsonl` 和 `jev_calls.jsonl` 中的当日记录导出至 `p8-audit/` 目录。

### 5. 人工审核
检查报告中的：
- 行情日期与新鲜度
- JEV 调用状态
- Search 证据多源性
- 行动建议是否合理

### 6. 循环
重复步骤 1‑5，连续执行 5‑10 个工作日。

## 回滚
所有生成的文件均位于 `~/harness/archive/` 和 `p8-audit/`，不影响原始数据。若需回滚，删除对应日期的快照和报告即可。

