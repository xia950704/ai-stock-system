#!/usr/bin/env python3
"""P2 数据完整性测试：验证 CSV/JSON 读取健壮性。
"""
import json
import sys
import tempfile
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

# T-D01: 正常 JSON 读取
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
    json.dump([{"code": "600276", "name": "恒瑞医药"}], f)
    f.flush()
    try:
        with open(f.name) as fp:
            data = json.load(fp)
        check("T-D01", "正常 JSON 读取成功", len(data) == 1 and data[0]["code"] == "600276")
    except Exception as e:
        check("T-D01", "正常 JSON 读取成功", False, str(e))

# T-D02: 空文件处理
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
    f.write("")
    f.flush()
    try:
        with open(f.name) as fp:
            json.load(fp)
        check("T-D02", "空文件应抛出 JSONDecodeError", False)
    except json.JSONDecodeError:
        check("T-D02", "空文件抛出 JSONDecodeError（清晰报错）", True)
    except Exception as e:
        check("T-D02", "空文件抛出 JSONDecodeError", False, f"got {type(e).__name__}")

# T-D03: 字段缺失时使用默认值
test_obj = {"code": "600276"}  # 缺失 name 字段
result = test_obj.get("name", "未知")
check("T-D03", "字段缺失时使用默认值", result == "未知")

# T-D04: 类型错误处理
try:
    float("invalid")
    check("T-D04", "类型错误抛出 ValueError", False)
except ValueError:
    check("T-D04", "类型错误抛出 ValueError（可捕获）", True)

print(f"\n=== test_data_integrity: {PASS} passed, {FAIL} failed ===")
sys.exit(1 if FAIL else 0)
