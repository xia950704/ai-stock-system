# Remediation log

## Source changes

| File | Change | Reason |
|---|---|---|
| `src/engine/daily_judge.py` | Compute report-aware data as-of/gate, pass report_date to stale logic, aggregate real JEV success, add controlled mock-failure path | Correct stale actions and distinguish real from Mock/controlled unavailable |
| `src/engine/report.py` | Show actual data date and freshness gate; show JEV model/transport/answers; warn when JEV unavailable | Make run status and evidence auditable |
| `src/engine/stock_judge.py` | Keep structured JEV result and clarify JEV as one evidence layer | Expose actual result without mapping it to an action |
| `src/engine/jev_adapter.py` | Validate non-empty structured answers and classify malformed `ok=true` as `parse_error` | Prevent malformed output from being treated as valid judgment |
| `p6-audit/tests/test_p6.py` | Replace stale bynara expectations; isolate local env for no-key test | Tests now match current AMD/Clef configuration |
| `p6-audit/tests/test_radar_inventory.py` | New coverage inventory tests | Validate historical coverage counts |
| `src/backtest/radar_inventory.py` | New read-only inventory | Make radar-history claim reproducible |

## Local configuration

- `.env` permission: `644` to `600`.
- No key value was printed.
- Workspace `.env` contents were not rewritten, only permissions tightened.

## Rollback

1. Stop using new reports; old files remain unchanged.
2. Restore the four engine files and two test files from `scratch/p6-20261021-backup/`.
3. Delete new files listed in the table.
4. Restore `.env` permission to `644` if desired.
5. Verify against `scratch/p6-20261021-postchange-hashes.txt`.
6. Re-run P2-P6 suites.

## Non-changes

- Obsidian: read-only. An unrelated existing external task updated 512400 state during the session; Codex did not trigger or modify it.
- GitHub workflows, heartbeat, trading code, global MCP, and remote secrets were not changed.
- AMD/MCP external configuration was not changed.
- `p4-audit/decision-model-options.md` was not filled.
