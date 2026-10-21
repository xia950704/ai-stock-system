#!/usr/bin/env python3
"""每日持仓快照：把 positions.json 按日期归档。

用法：
    python3 daily_positions_snapshot.py [--portfolio PATH] [--archive DIR]

默认读取 ~/harness/portfolio/positions.json，
写入 ~/harness/archive/snapshots/YYYYMMDD/positions.json。
文件已存在则跳过（幂等）。
"""
import argparse
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

def snapshot(portfolio_path: str, archive_dir: str, date_str: str = None) -> str:
    src = Path(portfolio_path).expanduser()
    if not src.exists():
        return f"SKIP: {src} 不存在"
    date_str = date_str or datetime.now().strftime("%Y%m%d")
    dst_dir = Path(archive_dir).expanduser() / date_str
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / "positions.json"
    if dst.exists():
        return f"SKIP: {dst} 已存在"
    shutil.copy2(src, dst)
    return f"OK: {src} -> {dst}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--portfolio", default="~/harness/portfolio/positions.json")
    ap.add_argument("--archive", default="~/harness/archive/snapshots")
    ap.add_argument("--date", default=None)
    args = ap.parse_args()
    result = snapshot(args.portfolio, args.archive, args.date)
    print(result)
    if result.startswith("SKIP"):
        sys.exit(0)

if __name__ == "__main__":
    main()
