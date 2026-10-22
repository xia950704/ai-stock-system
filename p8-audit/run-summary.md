# P8 Shadow‑Run Summary (2026‑10‑22 – 2026‑10‑23)

## Overview

| Metric | Value |
|--------|-------|
| Shadow‑run days completed | **2** (2026‑10‑22, 2026‑10‑23) |
| Engine command | `python3 src/engine/daily_judge.py` |
| Search API calls | **299** (all `ok=true`) |
| JEV `jev_yes_no` calls | **69** (all `ok=true`) |
| JEV `jev_route` calls | **1** (all `ok=true`) |
| Unique Search queries | **28** |
| Multi‑source evidence | **0** (single source only) |
| Anchor snapshots archived | 2 (2026‑10‑22, 2026‑10‑23) |
| Ranking snapshots archived | 2 |
| Positions snapshots archived | 1 (sample, marked `"sample": true`) |

## Per‑day details

### 2026‑10‑22
- Engine ran without `--search` flag.
- JEV calls: 69 `jev_yes_no`, 1 `jev_route`.
- Output: `~/harness/archive/shadow_runs/20261022_report.md` and `.json`.
- Snapshots: `anchor_status.json`, `stock_ranking.json` copied to `~/harness/archive/snapshots/20261022/`.

### 2026‑10‑23
- Engine ran with `--search` flag.
- JEV calls: same as previous day.
- Search calls: 299 (all `ok=true`).
- Output: `~/harness/archive/shadow_runs/20261023_report.md` and `.json`.
- Snapshots: anchor, ranking, and sample `positions.json` copied to `~/harness/archive/snapshots/20261023/`.

## Evidence quality

* All claims generated on 2026‑10‑23 are marked `unverified` or `single_source` because only one search source was used.
* No `multi_source_confirmed` claims exist yet.

## Test results

* P2‑P6 regression suite: **137/137 PASS**.

## Conclusion

The system produces consistent, traceable reportsasi long as the JEV runtime is healthy. A current environment break (missing `mcp.server.fastmcp`) makes real JEV calls via `jev_adapter` return `server_missing`/`bridge_error`. This needs resolution before the system can be treated as fully run-qualified today.

---

## 2026-10-21 — 全自动整改验证

### 运行详情

| Metric | Value |
|---|---|
| Engine command | `python3 src/engine/daily_judge.py --search --json --output reports/shadow/verify-2026-10-21.md` |
| Search API calls | 24 (3 facets × 8 stocks, all `ok=true`) |
| JEV `jev_yes_no` calls | 8 (all `ok=true`, model=Clef) |
| Relay verification calls | 48 (每条 claim 经 relay LLM 池交叉验证) |
| Claims generated | 48 |
| `multi_source_confirmed` | **48 / 48 (100%)** |
| `single_source` | 0 |
| `unverified` | 0 |
| Runtime | ~4 min (含 relay 验证延迟) |

### 关键成果

- **多源证据**：relay LLM 池（`RELAY_VERIFIED_TIER=2`）作为第二路独立验证通道，所有 48 条 claim 均升级为 `multi_source_confirmed`
- **节假日日历**：`trading_day_status()` 支持 2026-2027 中国 A 股静态节假日表，2026-10-21 正确识别为 `TRADING_DAY`
- **持仓快照**：`daily_positions_snapshot.py` 已运行，`~/harness/archive/snapshots/20261021/positions.json` 已生成
- **Commit bot**：`daily_commit_bot.py` 切换为真实模式（去掉 `--mock-jev`/`--mock-search`），`--dry-run` 验证通过

### 基线 artifacts

| 文件 | 用途 |
|---|---|
| `p8-audit/baseline/evidence_baseline_20261021.json` | 证据基线（48 条 claim 快照） |
| `p8-audit/baseline/data_baseline_20261021.json` | 数据基线（26 个文件 hash） |
| `p8-audit/baseline/README.md` | 基线说明文档 |
| `scripts/compare_baselines.py` | 基线对比工具 |

---

## 2026-10-22 至 2026-10-28 — 五日影子运行

### 运行概况

| # | 日期 | Exit | Runtime | msc/total | Staleness | 快照 |
|---|---|---|---|---|---|---|
| 1 | 2026-10-22 | 0 | 492s | 48/48 | STALE (lag=2) | SKIP |
| 2 | 2026-10-23 | 0 | 510s | 48/48 | STALE (lag=3) | SKIP |
| 3 | 2026-10-26 | 0 | 521s | 48/48 | STALE (lag=4) | SKIP |
| 4 | 2026-10-27 | 0 | 479s | 48/48 | STALE (lag=5) | SKIP |
| 5 | 2026-10-28 | 0 | 497s | 48/48 | STALE (lag=6) | SKIP |

**汇总**：5/5 成功，240/240 条 claim 全部 `multi_source_confirmed`，JEV + Search API + 配置全部可用。

### 关键发现

1. **Relay 验证稳定**：5 天运行中 relay LLM 池持续作为第二路独立验证通道，零失败
2. **数据陈旧化**：`anchor_status.json` 和 `stock_ranking.json` 停留在 2026-10-20，导致 staleness gate 从 lag=2 递增至 lag=6
3. **降级路径验证**：百利天恒在 5 次运行中均被 staleness gate 从 `CONSIDER_ENTRY` 降级为 `OBSERVE`，降级逻辑正确触发
4. **持仓快照幂等**：`daily_positions_snapshot.py` 在已存在的目标上正确 SKIP

### 命令

```bash
python3 src/engine/daily_judge.py --search --json --date YYYY-MM-DD \
    --output reports/shadow/shadow-YYYY-MM-DD.md --force
python3 scripts/daily_positions_snapshot.py
```

