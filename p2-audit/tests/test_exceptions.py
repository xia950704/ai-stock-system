#!/usr/bin/env python3
"""P2 错误处理测试：验证裸 except 修复。
"""
import io
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

# T-E01: alerts.py except Exception as e
txt = (WS / "src/trading/strategies/ml/alerts.py").read_text(encoding="utf-8")
check("T-E01", "alerts.py 使用 except Exception as e 而非裸 except",
      "except Exception as e:" in txt and "except:" not in txt.split("def check_performance_alert")[1].split("if max_dd < -0.15")[0])

# T-E02: optimizer.py except Exception as e
txt = (WS / "src/trading/strategies/ml/optimizer.py").read_text(encoding="utf-8")
check("T-E02", "optimizer.py 使用 except Exception as e 而非裸 except",
      "except Exception as e:" in txt)

# T-E03: daily_update.py except Exception as e
txt = (WS / "src/obsidian/01-股票投研/tools/daily_update.py").read_text(encoding="utf-8")
# 检查涨跌幅解析部分
parse_section = txt.split("尝试解析涨跌幅")[1].split("return {")[0]
check("T-E03", "daily_update.py 涨跌幅解析使用 except Exception as e",
      "except Exception as e:" in parse_section)

print(f"\n=== test_exceptions: {PASS} passed, {FAIL} failed ===")
sys.exit(1 if FAIL else 0)
