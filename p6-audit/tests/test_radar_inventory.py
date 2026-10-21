# Radar inventory regression（只使用临时样本，不读取或修改历史雷达）。
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path("/Users/xiashuang/AI-股票系统/src")))
from backtest.radar_inventory import build_inventory

PASS = 0
FAIL = 0

def check(tid, desc, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[PASS] {tid} {desc}")
    else:
        FAIL += 1
        print(f"[FAIL] {tid} {desc}")

with tempfile.TemporaryDirectory() as td:
    p1 = Path(td) / "radar_report_2026-01-01.md"
    p1.write_text("""# test
\n| 股票 | 现价 |\n| 华东医药 | 10 |\n| 恩华药业 | 10 |\n| 药明康德 | 10 |\n| 恒瑞医药 | 10 |\n| 科伦药业 | 10 |\n| 百利天恒 | 10 |\n| 512400有色金属ETF | 10 |\n| 荣昌生物 | 10 |\n""", encoding="utf-8")
    inv = build_inventory(td)
    check("T-RADAR-INVENTORY-01", "单日完整覆盖", inv["complete_pool_days"] == 1)
    check("T-RADAR-INVENTORY-02", "日期范围正确", inv["date_range"]["start"] == "2026-01-01")

    p2 = Path(td) / "radar_report_2026-01-02.md"
    p2.write_text("| 股票 |\n| 华东医药 | 10 |\n", encoding="utf-8")
    inv = build_inventory(td)
    check("T-RADAR-INVENTORY-03", "缺失标的不计入完整日期", inv["complete_pool_days"] == 1)
    check("T-RADAR-INVENTORY-04", "逐标的覆盖天数正确", inv["coverage_days"]["sz000963"] == 2 and inv["coverage_days"]["sh688331"] == 1)

print(f"\n=== test_radar_inventory: {PASS} passed, {FAIL} failed ===")
raise SystemExit(1 if FAIL else 0)
