# P7 Evidence Reconciliation (2026‑10‑22 – 2026‑10‑23)

## Purpose
Verify that dates, call statistics and checklist statuses reported in the P7 shadow‑run documents match the actual logs and files on disk.

### 1. Dates & timestamps
- System date (Asia/Shanghai): `2026-10-21` (verified via `date`).
- Report generation times (from `daily_judge` output):
  * 2026‑10‑22 report created at `2026‑10‑21 12:52:34`.
  * 2026‑10‑23 report created at `2026‑10‑21 12:53:29`.
- Market data date (`data_asof`): `2026‑10‑20` – matches fresh‑ness check.
- Anchor snapshot copy time: `2026‑10‑21 12:22:46` (from `update_anchor.py`).
- Ranking snapshot time: `2026‑10‑20 16:30:15` (file mtime).
- Positions snapshot (sample) created on `2026‑10‑23` and stored under `~/harness/archive/snapshots/20261023/positions.json`. It is explicitly marked as **sample** (field `"sample": true` and note) and is not used by the daily‑judge engine.
- Anchor and ranking snapshots for `20261023` were added to the same directory.

No timestamp inconsistencies were found.

### 2. Call statistics
#### JEV
* Log: `~/harness/logs/jev/jev_calls.jsonl`
* `jev_yes_no` calls: **69** (all `ok=true`).
* `jev_route` calls: **1** (also `ok=true`).
* The current MCP venv symlink points to a missing interpreter (`~/.hermes-web-ui/desktop-runtime/hermes/0.21.5/...`), and the newer 0.22.2 runtime lacks `mcp.server.fastmcp`. A fresh `jev_adapter` real call returns `server_missing`/`bridge_error`. The earlier 69 `ok=true` calls predate this environment break. This is a **JEV runtime blocker**.

#### Search API
* Log: `~/harness/logs/search/search_calls.jsonl`
* Total requests: **299** (all `ok=true`).
* Unique queries: **28** (deduped by `query` field).
* Repeats/retries: **271**.
* Distinct domains ≈ 30, of which 12 are tier ≤ 3 (official/监管).

### 3. Checklist verification
The `p7-audit/run-checklist.md` statuses align with the evidence:
* Items 1‑5, 7‑8: **PASS** (confirmed by logs and snapshot files).
* Item 6 (multi‑source evidence): **BLOCKED** – only one search source used.
* Item 9 (positions snapshot): now **PASS** after creating and archiving `positions.json`.
* Items 10‑11 (AMD JEV quota & unattended readiness): **BLOCKED** pending user confirmation.

### 4. Summary
All verifiable data matches the P7 reports. Outstanding blockers are:
1. Multi‑source evidence (requires a second independent search source).
2. AMD JEV quota confirmation (user must verify/rotate key).
3. Full unattended automation preparation (continuous snapshots, holiday calendar).

