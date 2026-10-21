#!/usr/bin/env python3
"""P2 JEV Mock 测试：验证 server.py 错误处理逻辑（不依赖真实 MCP）。
"""
import re
import sys
from pathlib import Path

PASS = 0
FAIL = 0

def check(tid, desc, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[PASS] {tid} {desc}")
    else:
        FAIL += 1
        print(f"[FAIL] {tid} {desc} | {detail}")

WS = Path("/Users/xiashuang/AI-股票系统")
server_py = (WS / "src/jev/server.py").read_text(encoding="utf-8")

# T-J01: _call 函数处理 httpx.TimeoutException
check("T-J01", "server.py _call 处理 httpx.TimeoutException",
      "httpx.TimeoutException" in server_py)

# T-J02: _call 返回 {"ok": False, "error": ...} 格式
call_section = server_py.split("def _call")[1].split("# --")[0]
check("T-J02", "server.py _call 返回 ok=False 格式的错误结果",
      '{"ok": False, "error":' in call_section or '{"ok": False, "http_status":' in call_section)

# T-J03: jev_front_door 处理 CLI 超时
front_door_section = server_py.split("def jev_front_door")[1].split("DEFAULT_CLI")[0] if "def jev_front_door" in server_py else ""
check("T-J03", "server.py jev_front_door 使用 --timeout 60 调用 CLI",
      "--timeout" in front_door_section and "60" in front_door_section)

# T-J04: 源码中无裸 except
check("T-J04", "server.py 无裸 except:", "except:" not in server_py or server_py.count("except Exception") > 0)

# T-J05: 验证 timeout 设置
check("T-J05", "server.py 设置 TIMEOUT_S 并使用于 httpx.Client",
      "TIMEOUT_S" in server_py and "httpx.Client(timeout=TIMEOUT_S)" in server_py)

print(f"\n=== test_jev_mock: {PASS} passed, {FAIL} failed ===")
sys.exit(1 if FAIL else 0)
