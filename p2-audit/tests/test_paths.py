#!/usr/bin/env python3
"""P2 路径测试：验证环境变量注入与降级行为。
不触发任何网络调用；仅验证模块级路径解析。
"""
import importlib.util
import os
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

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

WS = Path("/Users/xiashuang/AI-股票系统")

# T-P01/T-P03: DATA_ROOT env var respected by update_anchor & fetch_realtime
env_backup = dict(os.environ)
try:
    with tempfile.TemporaryDirectory() as tmp:
        fake_anchor = Path(tmp) / "anchor_status.json"
        fake_anchor.write_text('[]', encoding="utf-8")
        os.environ["DATA_ROOT"] = tmp

        ua = load_module("ua_p2", WS / "src/scripts/fetch/update_anchor.py")
        check("T-P01", "DATA_ROOT 生效: update_anchor.ANCHOR_PATH 指向 DATA_ROOT",
              ua.ANCHOR_PATH == str(fake_anchor), f"got {ua.ANCHOR_PATH}")
        check("T-P03", "DATA_ROOT 生效: BACKUP_PATH 位于 DATA_ROOT/backup_phase1",
              ua.BACKUP_PATH == str(Path(tmp) / "backup_phase1" / "anchor_status.pre_update.json"),
              f"got {ua.BACKUP_PATH}")

        fr = load_module("fr_p2", WS / "src/scripts/fetch/fetch_realtime.py")
        check("T-P01b", "DATA_ROOT 生效: fetch_realtime.ANCHOR_PATH 指向 DATA_ROOT",
              fr.ANCHOR_PATH == str(fake_anchor), f"got {fr.ANCHOR_PATH}")
finally:
    os.environ.clear(); os.environ.update(env_backup)

# T-P02: 环境变量缺失时降级到 ~/harness/stock_daily
try:
    os.environ.pop("STOCK_DAILY_DIR", None)
    sr = load_module("sr_p2", WS / "src/scripts/legacy/stock_signal_extractor.py")
    expected = os.path.expanduser("~/harness/stock_daily")
    check("T-P02", "STOCK_DAILY_DIR 缺失时降级到 ~/harness/stock_daily",
          sr.REPORT_DIR == expected, f"got {sr.REPORT_DIR}")
    # 且旧失效路径不再出现
    src_text = (WS / "src/scripts/legacy/stock_signal_extractor.py").read_text(encoding="utf-8")
    check("T-P02b", "失效路径 ~/.hermes/workspace/stock_daily 已从运行时代码移除",
          "hermes/workspace/stock_daily" not in src_text)
finally:
    os.environ.clear(); os.environ.update(env_backup)

# T-P04: 数据文件不存在时应清晰报错（load_anchors 直接 open 会抛 FileNotFoundError）
try:
    os.environ["DATA_ROOT"] = "/nonexistent/p2_audit_root"
    fr2 = load_module("fr_p2b", WS / "src/scripts/fetch/fetch_realtime.py")
    try:
        fr2.load_anchors()
        check("T-P04", "源文件不存在时报错", False, "未抛出异常")
    except FileNotFoundError as e:
        check("T-P04", "源文件不存在时抛出 FileNotFoundError（清晰报错，不静默）", True)
finally:
    os.environ.clear(); os.environ.update(env_backup)

# T-P05: stock_ranking WORKSPACE 跟随环境变量
try:
    os.environ["STOCK_DAILY_DIR"] = "/tmp/p2_fake_ws"
    # stock_ranking 导入 duckdb/pandas，若缺失则跳过
    try:
        srk = load_module("srk_p2", WS / "src/scripts/core/stock_ranking.py")
        check("T-P05", "stock_ranking.WORKSPACE 跟随 STOCK_DAILY_DIR",
              srk.WORKSPACE == "/tmp/p2_fake_ws", f"got {srk.WORKSPACE}")
    except ImportError as e:
        print(f"[SKIP] T-P05 依赖缺失（{e}），仅验证源码包含环境变量读取")
        txt = (WS / "src/scripts/core/stock_ranking.py").read_text(encoding="utf-8")
        check("T-P05", "stock_ranking.WORKSPACE 源码使用 STOCK_DAILY_DIR 环境变量",
              'os.environ.get("STOCK_DAILY_DIR"' in txt)
finally:
    os.environ.clear(); os.environ.update(env_backup)

print(f"\n=== test_paths: {PASS} passed, {FAIL} failed ===")
sys.exit(1 if FAIL else 0)
