# Regression results

## Unit suites executed

```bash
for t in \
  p2-audit/tests/test_paths.py \
  p2-audit/tests/test_exceptions.py \
  p2-audit/tests/test_data_integrity.py \
  p2-audit/tests/test_jev_mock.py \
  p3-audit/tests/test_engine.py \
  p4-audit/tests/test_backtest.py \
  p5-audit/tests/test_p5.py \
  p6-audit/tests/test_p6.py \
  p6-audit/tests/test_radar_inventory.py; do
  python3 "$t"
done
```

| Suite | Passed | Failed |
|---|---:|---:|
| P2 | 19/19 | 0 |
| P3 | 28/28 | 0 |
| P4 | 32/32 | 0 |
| P5 | 36/36 | 0 |
| P6 adapter | 18/18 | 0 |
| Radar inventory | 4/4 | 0 |
| Total | 137/137 | 0 |

The suites were executed again after the final JEV availability and stale-report fixes.

## Real operational checks

- JEV `jev_yes_no`: executed real, 8/8 passed.
- JEV `jev_route`: executed real, 1/1 passed.
- Search: executed real, 24/24 queries returned results.
- Shadow scenarios: see `05_SHADOW_RUN.md`.
- Trading: not tested and not authorized.
- Remaining JEV tools: contract tests only; real calls NOT TESTED.
- AMD quota: NOT TESTED.

## Distinct versus repeated execution

The 137 number is a sum of distinct tests, not repeated attempts. A failed suite can count more than one suite execution, but every failure that appeared was corrected and re-executed until the final suite passed.
