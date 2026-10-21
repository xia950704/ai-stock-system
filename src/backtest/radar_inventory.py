#!/usr/bin/env python3
"""Inventory historical radar reports without mutating them."""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import date
from typing import Any, Dict, List

RADAR_DIR = os.path.expanduser("~/harness/bandwidth_radar")
POOL_NAMES = {
    "sh600276": "恒瑞医药",
    "sz000963": "华东医药",
    "sz002262": "恩华药业",
    "sz002422": "科伦药业",
    "sh603259": "药明康德",
    "sh688506": "百利天恒",
    "sh512400": "512400有色金属ETF",
    "sh688331": "荣昌生物",
}
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

def build_inventory(radar_dir: str = RADAR_DIR) -> Dict[str, Any]:
    reports: List[Dict[str, Any]] = []
    coverage = {code: 0 for code in POOL_NAMES}
    if os.path.isdir(radar_dir):
        for filename in sorted(os.listdir(radar_dir)):
            if not filename.startswith("radar_report_") or not filename.endswith(".md"):
                continue
            m = DATE_RE.search(filename)
            if not m:
                continue
            report_date = date.fromisoformat(m.group(1))
            path = os.path.join(radar_dir, filename)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            rows = [line for line in text.splitlines() if line.startswith("| ")]
            present = {}
            for code, name in POOL_NAMES.items():
                hit = any(f"| {name} " in line for line in rows)
                present[code] = hit
                if hit:
                    coverage[code] += 1
            reports.append({
                "date": report_date.isoformat(),
                "path": path,
                "table_row_count": len(rows),
                "pool_present": present,
            })
    complete_days = [
        item["date"] for item in reports
        if all(item["pool_present"].values())
    ]
    return {
        "source_dir": radar_dir,
        "report_count": len(reports),
        "date_range": {
            "start": reports[0]["date"] if reports else None,
            "end": reports[-1]["date"] if reports else None,
        },
        "coverage_days": coverage,
        "complete_pool_days": len(complete_days),
        "complete_pool_dates": complete_days,
        "reports": reports,
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--radar-dir", default=RADAR_DIR)
    parser.add_argument("--output", help="write inventory JSON")
    args = parser.parse_args()
    inventory = build_inventory(args.radar_dir)
    rendered = json.dumps(inventory, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(rendered + "\n")
    else:
        print(rendered)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
