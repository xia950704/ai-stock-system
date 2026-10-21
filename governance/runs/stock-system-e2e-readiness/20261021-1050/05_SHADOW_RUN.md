# Shadow scenarios

All scenario outputs are separate files; the engine refuses silent overwrite by default.

| # | Scenario | Artifact or test | State | Result |
|---|---|---|---|---|
| 1 | Real market, real Search, real JEV | `reports/shadow/e2e_test_20261021_v3.md` and JSON | PASS | JEV 8/8, Search 24/24, report generated |
| 2 | Real Search, JEV unavailable | `reports/shadow/e2e_s2_jev_unavailable_20261021_v2.md` | PASS | Controlled `model_na`; JEV excluded and recorded as a gap |
| 3 | Stale market, Search available | `reports/shadow/e2e_s3_stale_prices_20261130_v2.md` | PASS | 29-day stale lag downgraded CONSIDER_ENTRY to OBSERVE |
| 4 | Search unavailable | `reports/shadow/e2e_s4_search_unavailable_20261021_v2.md` | PASS | transport failure preserved as search gap |
| 5 | Missing market/ranking data | `reports/shadow/e2e_s5_data_missing_20261021.md` | PASS | all stocks output INSUFFICIENT_EVIDENCE |
| 6 | Single source and conflict preservation | `scenario-6-evidence-status.json` | PARTIAL | one reliable source becomes single_source; two independent sources become multi_source_confirmed; manual conflict survives sanitization. Automatic semantic conflict detection is not implemented |
| 7 | Malformed JEV response | `scenario-7-jev-malformed.json` | PASS after fix | malformed ok response becomes parse_error and INSUFFICIENT_EVIDENCE |
| 8 | Duplicate run | `scenario-8-duplicate-run.json` | PASS | existing MD and JSON detected; default overwrite=false |

## Important caveat

Scenario 1 passed in this session, but real JEV key-rotation confirmation was not completed before execution; see `02_JEV_INTEGRATION.md`. This is a process finding, not evidence that the call itself failed.

## Report limitations

- Order/commercialization facet has no data source and remains unavailable.
- Market breadth and actual index data are absent; market judgment is local-pool only.
- Holiday calendar is not authoritative; weekday logic is conservative but not a complete trading calendar.
