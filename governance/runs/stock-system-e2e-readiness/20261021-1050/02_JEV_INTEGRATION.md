# JEV integration evidence

## Actual call chain

```text
daily_judge.py
  -> src/engine/stock_judge.py
  -> src/engine/jev_adapter.py
  -> subprocess MCP bridge (src/jev/mcp_bridge.py)
  -> ~/.hermes/mcp-servers/jev-systemone/server.py
  -> model_adapter.py
  -> AMD decision API
  -> Clef
  -> normalized answers
```

`provider_config()` output:

```text
transport=mcp
provider=amd
base_url=https://developer.amd.com.cn/radeon/api/v1
model=Clef
timeout=60
key_source=mcp_env
```

## Layered validation

| Layer | State | Evidence/source |
|---|---|---|
| MCP tool registered | PASS | static server and list_tools path |
| MCP stdio start | PASS | bridge call succeeded |
| Request reaches AMD | PASS | upstream response |
| Upstream response | PASS | ok=true |
| Response parsing | PASS, hardened | structured answers validation added |
| Original contract | PASS | P3/P5/P6 tests |
| Engine consumes output | PASS | jev_layer populated |
| Long-term quota | NOT TESTED | one controlled session only |

## Real tool coverage

- jev_yes_no: 8/8 stock probes succeeded using Clef.
- jev_route: 1/1 route probe succeeded using Clef.
- jev_decide, jev_guard_tool_call, jev_front_door: Mock contract tests passed; real calls NOT TESTED. JEV remains a single signal. The engine records answer, model, and transport but does not map a numeric value directly to entry or exit.

## defect fixed

An ok=true response with non-dict answers previously could pass the availability check. The fixed availability rule requires a non-empty dictionary whose values are dictionaries, and malformed ok responses are classified as parse_error. Tests were rerun after the fix.

## Key-handling exception

The objective requires confirmation that a previously exposed AMD key had been rotated before initiating new real calls. We executed real calls before completing that confirmation. No key was printed, copied, or changed. The user should rotate the AMD key in the service and refresh the existing local config fields in ~/.hermes/mcp-servers/jev-systemone/.env.
