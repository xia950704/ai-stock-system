#!/usr/bin/env python
"""Minimal MCP stdio bridge for the existing jev-systemone server.

This file is intended to run with the MCP server's existing virtualenv so no
new dependency is installed in the Workspace. It performs only:

  * MCP initialize / list_tools, or
  * one MCP tool call against the existing server.

It never implements JEV decision rules and never prints credentials.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict


DEFAULT_SERVER_DIR = os.path.expanduser(
    os.environ.get(
        "JEV_MCP_SERVER_DIR",
        "~/.hermes/mcp-servers/jev-systemone",
    )
)


def _emit(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _parse_tool_content(result: Any) -> Dict[str, Any]:
    content = getattr(result, "content", None) or []
    if not content:
        return {
            "ok": False,
            "error_code": "empty_result",
            "error_message": "MCP tool returned no content",
        }
    first = content[0]
    text = getattr(first, "text", None)
    if text is None:
        return {
            "ok": False,
            "error_code": "parse_error",
            "error_message": "MCP tool content has no text field",
        }
    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "error_code": "parse_error",
            "error_message": f"invalid MCP tool JSON: {exc}",
            "raw_prefix": str(text)[:300],
        }
    if not isinstance(parsed, dict):
        return {
            "ok": False,
            "error_code": "parse_error",
            "error_message": "MCP tool JSON must be an object",
        }
    return parsed


async def _run(request: Dict[str, Any], timeout_s: float) -> Dict[str, Any]:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as exc:
        return {
            "ok": False,
            "error_code": "no_mcp",
            "error_message": f"mcp package unavailable: {exc}",
        }

    server_dir = Path(
        request.get("server_dir") or DEFAULT_SERVER_DIR
    ).expanduser()
    python = request.get("python") or str(server_dir / ".venv" / "bin" / "python")
    server_py = request.get("server_py") or str(server_dir / "server.py")
    if not Path(python).is_file():
        return {
            "ok": False,
            "error_code": "server_missing",
            "error_message": f"MCP python not found: {python}",
        }
    if not Path(server_py).is_file():
        return {
            "ok": False,
            "error_code": "server_missing",
            "error_message": f"MCP server not found: {server_py}",
        }

    env = dict(os.environ)
    pythonpath = request.get("pythonpath")
    if pythonpath:
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = pythonpath + os.pathsep + existing if existing else pythonpath
    # Tests can safely force a fake credential without touching the real file.
    if request.get("fake_key"):
        env["JEV_API_KEY"] = str(request["fake_key"])
    params = StdioServerParameters(
        command=python,
        args=[server_py],
        env=env,
        cwd=str(server_dir),
    )

    async def _session_call() -> Dict[str, Any]:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                names = [tool.name for tool in listed.tools]
                action = request.get("action", "list_tools")
                if action == "list_tools":
                    return {
                        "ok": True,
                        "action": "list_tools",
                        "tools": names,
                        "server_dir": str(server_dir),
                    }
                tool = request.get("tool")
                if tool not in names:
                    return {
                        "ok": False,
                        "error_code": "not_found",
                        "error_message": f"MCP tool not found: {tool}",
                        "tools": names,
                    }
                arguments = request.get("arguments") or {}
                result = await session.call_tool(tool, arguments=arguments)
                parsed = _parse_tool_content(result)
                parsed.setdefault("transport", "mcp")
                parsed.setdefault("tool", tool)
                return parsed

    try:
        return await asyncio.wait_for(_session_call(), timeout=timeout_s)
    except asyncio.TimeoutError:
        return {
            "ok": False,
            "error_code": "timeout",
            "error_message": f"MCP bridge timeout after {timeout_s}s",
        }
    except Exception as exc:  # The bridge must classify and preserve failures.
        return {
            "ok": False,
            "error_code": "bridge_error",
            "error_message": f"{type(exc).__name__}: {exc}",
        }


def main() -> int:
    try:
        raw = sys.stdin.read()
        request = json.loads(raw) if raw.strip() else {}
        if not isinstance(request, dict):
            raise ValueError("request must be a JSON object")
    except Exception as exc:
        _emit({
            "ok": False,
            "error_code": "bad_request",
            "error_message": str(exc),
        })
        return 2

    timeout_s = float(request.get("timeout_s") or 60)
    result = asyncio.run(_run(request, timeout_s))
    _emit(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
