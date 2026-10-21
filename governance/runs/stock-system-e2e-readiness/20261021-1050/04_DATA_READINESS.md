# Data readiness

## Current trading data

- Report date: 2026-10-21 Asia/Shanghai.
- Data as-of date: 2026-10-20.
- Lag: 1 trading day.
- Gate: FRESH.
- File modification time is not treated as the data date.

## **■ verified

The corrected daily engine computes the data as-of date once and passes request report_date into stock-level freshness gates.
The report records that gate reason and preserves STALE and DATE_UNKNOWN blocking.

## Historical readiness

- Long daily price coverage exists in DuckDB.
- Only one structured anchor-date snapshot and one current ranking snapshot are available.
- Twenty-five radar reports cover 2026-09-02 through 2026-10-20, but they are unstructured and do not cover every pool stock on every date.
- Reproducible inventory: `src/backtest/radar_inventory.py` and `governance/runs/stock-system-e2e-readiness/20261021-1050/radar-historical-inventory.json
- Complete original PRICE plus ANCHOR plus RANKING days: 0.
- Reconstructed days: 0.
- Full engine replay days: 0.

## Boundary

Historical radar signals are not promoted to ranking snapshots. No current values were backfilled into past dates. Search and JEV history remain unavailable during replay.
