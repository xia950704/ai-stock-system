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

