# Security Readiness Report (P8)

## 1. AMD JEV Key & Configuration

| Item | Status | Evidence |
|------|--------|----------|
| Key file location | `~/.hermes/mcp-servers/jev-systemone/.key` | Exists, mode 600. |
| Key in `.env` | Not present; key is read from the `.key` file by the MCP server. | `server.py` reads `JEV_API_KEY` from `.key`. |
| Key rotation status | **UNCONFIRMED** – no recent rotation record. | User must rotate in AMD console and update `.key`. |
| Current provider/model | `provider=amd`, `model=Clef` (matches logs). | `jev_adapter.provider_config()` output. |
| Automatic model switching | **None** – only `Clef` is used. | Log analysis confirms no fallback. |
| Runtime health | **PASS (verified 2026-10-21)** – `jev_adapter` now selects `~/.local/bin/python3.12` when the default venv symlink is broken, and sets `PYTHONPATH` to the old `.venv/lib/python3.12/site-packages`, which contains `mcp.server.fastmcp`. A real `jev_yes_no` call returned `ok=True` with model `Clef`. | Console output: `ok: True, model: Clef`; regression suite all 9 test files pass. |

## 2. Search API Configuration

| Item | Status | Evidence |
|------|--------|----------|
| Config file | `/Users/xiashuang/AI-股票系统/.env` | Contains `SEARCH_API_BASE_URL` and `SEARCH_API_KEY`. |
| Loading mechanism | `src/search/client.py` calls `dotenv.load_dotenv()` with env‑var precedence. | Verified via code inspection. |
| Git protection | `.gitignore` includes `**/.env`. | File is not tracked. |
| Key leakage in logs | None – keys are never printed. | `search_calls.jsonl` contains only `ok` and result summaries. |

## 3. Unauthorized Actions Check

| Check | Status |
|-------|--------|
| Automated daily cron tasks created | **None** – no crontab entries added. |
| Real trading API calls | **None** – no trade instructions generated. |
| GitHub workflow triggers | **None** – no `workflow_dispatch` or schedule changes. |
| Global configuration changes | **None** – no modifications to `~/.codex/config.toml` or `~/.hermes/config.yaml`. |
| Model switching | **None** – only `Clef` is used. |
| Dependency installation | **None** – no `pip install` or `npm install` performed. |

## 4. Snapshot & Sample Data Isolation

* `positions.json` is explicitly labelled as **sample** (see file header) and is stored under `~/harness/archive/snapshots/20261023/positions.json`. It is **not** referenced by the daily‑judge engine.
* Real user holdings are **not** present in any workspace file.

## 5. Conclusion

The system is **secure for manual supervised research**. The only remaining security‑related action is **AMD JEV key rotation** and **quota verification**, which must be performed by the user.

