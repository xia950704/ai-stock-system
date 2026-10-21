# Roadmap to Full Automation

## 1. Multi‑source evidence

* Add a second independent search source (e.g., Yahoo Finance, Tushare, or a public regulatory API).
* Modify `src/search/evidence.py` to collect results from both sources and mark claims as `MULTI_SOURCE` when at least two independent tier ≤ 3 sources are found.

## 2. Daily positions snapshot

* Create a small script (`scripts/daily_positions_snapshot.py`) that copies `~/harness/portfolio/positions.json` to `~/harness/archive/snapshots/YYYYMMDD/positions.json`.
* Run it after each shadow‑run or via a manual step.

## 3. AMD JEV quota & key rotation

* User must log in to the AMD console, rotate the key if necessary, and confirm the monthly quota.
* Update `~/.hermes/mcp-servers/jev-systemone/.key` with the new key.

## 4. Holiday calendar

* Add a static list of Chinese market holidays to `src/engine/trading_day.py` (or import from a public source).
* Ensure the freshness gate treats holidays as non‑trading days.

## 5. Extended shadow‑run

* Continue running `daily_judge.py` for 5‑10 additional trading days, using `--search` and the daily positions snapshot.
* Archive each run’s outputs and update the run‑summary.

## 6. Final automation

* Once the above items are satisfied, the system can be scheduled via a simple cron wrapper (outside the scope of this project).

