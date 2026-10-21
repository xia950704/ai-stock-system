#!/bin/bash
# jev-systemone MCP server launcher. Key via env or .key file.
# Exposes 4 tools: jev_decide (native decide), jev_yes_no (noul/choice 是否判定),
# jev_guard_tool_call (allow/confirm/review/deny), jev_route (前置路由: 默认
# light/heavy/jev 三档选任务最短路径, 可传 options 自定义候选仲裁).
exec "$(dirname "$0")/.venv/bin/python" "$(dirname "$0")/server.py"
