# Baseline before final integration

## Code and configuration

- Workspace: `/Users/xiashuang/AI-股票系统`
- No Git repository in the workspace, so rollback uses explicit file hashes and the backup directory `scratch/p6-20261021-backup/`.
- `src/decision/contract.py` and `src/decision/registry.py` already existed. Their status is `COMPLETE`; no rebuild was performed.
- `p4-audit/decision-model-options.md` was already blank and remains blank.
- `src/engine/jev_adapter.py` already had an MCP-first path, but prior audit reports still described the older bynara chain.
- Search configuration:
  - file: `/Users/xiashuang/AI-股票系统/.env`
  - fields: `SEARCH_API_BASE_URL`, `SEARCH_API_KEY`
  - Base URL: `http://127.0.0.1:31415/v1/search`
  - key value: present but not printed.

## Data baseline

- Anchor rows: 56.
- Ranking run date: `2026-10-20`.
- Realtime snapshot: `20261020`.
- Report run date: `2026-10-21`.
- Full original historical input dates before this run: 0.

## Test baseline

Existing suites: P2 through P6, 133 tests. P6 contained five stale assertions expecting a bynara default.

## Baseline hashes

`scratch/p6-20261021-postchange-hashes.txt` records the final modified hashes. The directory `scratch/p6-20261021-backup/` contains final backups. The workspace is not a Git repository, so this is the approved rollback source.
