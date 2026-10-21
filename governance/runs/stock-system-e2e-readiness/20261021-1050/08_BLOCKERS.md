# Remaining blockers

| Item | State | Minimum user action | Exact location |
|---|---|---|---|
| AMD JEV key rotation confirmation | BLOCKED for automated/prolonged use | Rotate key in AMD service and update existing MCP config | `~/.hermes/mcp-servers/jev-systemone/.env` keys `JEV_API_KEY`, `JEV_API_KEY_FALLBACK` |
| AMD quota and error behavior over time | NOT TESTED | Monitor after controlled use; do not enable unattended automation yet | `~/harness/logs/jev/jev_calls.jsonl` Logs already record failures without secrets |
| Order/commercialization data | BLOCKED | Choose a data source or export format | Workspace data contract not yet defined |
| Reliable holiday calendar | BLOCKED | Approve a trusted calendar source | `src/engine/trading_day.py` |
| Complete historical input | BLOCKED by data | Allow daily structured snapshot archival over time; optionally approve external provider | `~/harness/stock_daily/` |
| Alternative Decision Model selection | USER-CONTROLLED | Fill fields only if desired | `p4-audit/decision-model-options.md` |
| Formal scheduler | NOT ENABLED | Explicitly approve after blockers clear | not created |
| Live trading | NOT AUTHORIZED | none | not implemented |

## Already unblocked

- Search API real calls: working.
- JEV MCP/AMD/Clef real calls for `jev_yes_no` and `jev_route`: working in this controlled session.
- Market date and freshness gate: corrected and tested.
- Search unavailable / JEV unavailable / stale data / missing data degradation: tested.
- Report duplicate protection: working.
- Historical coverage inventory: reproducible.

Do not send keys in chat. Rotate or update secrets only in the referenced local file or the external provider’s console.
