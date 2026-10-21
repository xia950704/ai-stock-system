# P6 Goal scope and constraints

Goal: make the stock research system operate end to end under explicit safety boundaries and produce an honest qualification decision.

In scope:

- Verify Decision Model status without rebuilding it.
- Trace and reuse the existing JEV MCP stack.
- Validate Search API real configuration and source handling.
- Fix data-date/freshness defects confirmed from execution.
- Inventory historical inputs without look-ahead reconstruction.
- Run controlled shadow scenarios and full regression.
- Produce final evidence and blockers.

Hard exclusions:

- No Obsidian writes from Codex.
- No GitHub workflow or four-hour heartbeat changes.
- No trades.
- No paid credits.
- No automatic Decision Model selection or model switching.
- No production daily scheduler.
- No printing secrets.
- No treating mock output as real output.

The final answer distinguishes real pass, mock pass, implemented but unverified, blocked, and data insufficient.
