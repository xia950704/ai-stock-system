# Search API validation

## Configuration

- Absolute config file: `/Users/xiashuang/AI-股票系统/.env`
- Fields: `SEARCH_API_BASE_URL`, `SEARCH_API_KEY`
- Loaded by: `src/search/client.py::_load_dotenv()`
- Environment variables take precedence over the file.
- The config file is ignored by Git and its permission was tightened from `644` to `600`.
- No secret value is printed by the client or reports.

## Real calls

- 2026-10-21 daily engine: 24 real read-only queries, 24 successes.
- Log: `~/harness/logs/search/search_calls.jsonl`
- Each success returned 5 results.
- Fields preserved: `title`, `url`, `content`/`snippet`, `score`.
- `published_at` is not inferred when absent.

## Real fact example

Proposition checked: Hengrui’s 2026 semi-annual report was published on 2026-08-19, and media reported revenue of 15.456 billion yuan and net profit attributable to shareholders of 4.465 billion yuan.

Sources:

1. cninfo PDF, primary disclosure.
2. CLS report republished by Sina.
3. Beijing News report republished by Sina.

State: `CONFIRMED_PRIMARY_SOURCE_AVAILABLE`. The numeric wording appears in multiple secondary reports, but all derive from the same company filing, so this is not treated as fully independent confirmation. Ledger: `scratch/p6/citation-ledger.json`.

## Boundary

Search is evidence supplementation only. A single-source news item does not create a trade action. Conflicting and single-source states remain explicit.
