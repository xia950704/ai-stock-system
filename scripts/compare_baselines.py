#!/usr/bin/env python3
"""基线对比工具：对比当前运行结果与历史基线。

用法：
    python3 compare_baselines.py --baseline-dir p8-audit/baseline --current REPORTS_DIR
    python3 compare_baselines.py --baseline-dir p8-audit/baseline --current REPORTS_DIR --json
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def compare_evidence(baseline: dict, current: dict) -> dict:
    """对比证据基线，返回漂移报告。"""
    b_sum = baseline.get("summary", {})

    b_stocks = baseline.get("stocks", {})
    c_stocks = current.get("stocks", {})

    # Compute summary from current report if not present (daily_judge.py format)
    if not current.get("summary"):
        all_claims = []
        if isinstance(c_stocks, list):
            for s in c_stocks:
                all_claims.extend(s.get("search_layer", {}).get("claims", []))
        elif isinstance(c_stocks, dict):
            for s in c_stocks.values():
                all_claims.extend(s.get("claims", []))
        c_sum = {
            "total_claims": len(all_claims),
            "multi_source_confirmed": sum(1 for c in all_claims if c.get("status") == "multi_source_confirmed"),
            "single_source": sum(1 for c in all_claims if c.get("status") == "single_source"),
            "unverified": sum(1 for c in all_claims if c.get("status") == "unverified"),
        }
    else:
        c_sum = current.get("summary", {})

    # Normalize current report: daily_judge.py uses list with search_layer.claims
    if isinstance(c_stocks, list):
        c_stocks = {
            s.get("code", str(i)): {
                "name": s.get("name", ""),
                "claims": s.get("search_layer", {}).get("claims", [])
            }
            for i, s in enumerate(c_stocks)
        }
    if isinstance(b_stocks, list):
        b_stocks = {
            s.get("code", str(i)): {
                "name": s.get("name", ""),
                "claims": s.get("search_layer", {}).get("claims", [])
            }
            for i, s in enumerate(b_stocks)
        }

    stock_drifts = {}
    for code in sorted(set(b_stocks) | set(c_stocks)):
        b = b_stocks.get(code, {})
        c = c_stocks.get(code, {})
        b_claims = b.get("claims", [])
        c_claims = c.get("claims", [])

        drift = {
            "baseline_count": len(b_claims),
            "current_count": len(c_claims),
            "status_changes": [],
        }

        # Per-claim comparison
        b_by_id = {cl["claim_id"]: cl for cl in b_claims}
        c_by_id = {cl["claim_id"]: cl for cl in c_claims}

        for cid in sorted(set(b_by_id) | set(c_by_id)):
            old = b_by_id.get(cid)
            new = c_by_id.get(cid)
            if old and new:
                if old.get("status") != new.get("status"):
                    drift["status_changes"].append({
                        "claim_id": cid,
                        "from": old.get("status"),
                        "to": new.get("status"),
                    })
            elif old and not new:
                drift["status_changes"].append({
                    "claim_id": cid,
                    "from": old.get("status"),
                    "to": "MISSING",
                })
            elif new and not old:
                drift["status_changes"].append({
                    "claim_id": cid,
                    "from": "NEW",
                    "to": new.get("status"),
                })

        if drift["status_changes"]:
            stock_drifts[code] = drift

    return {
        "baseline_total": b_sum.get("total_claims", 0),
        "baseline_multi_source": b_sum.get("multi_source_confirmed", 0),
        "current_total": c_sum.get("total_claims", 0),
        "current_multi_source": c_sum.get("multi_source_confirmed", 0),
        "multi_source_ratio_baseline": (
            b_sum.get("multi_source_confirmed", 0) / b_sum.get("total_claims", 1)
            if b_sum.get("total_claims", 0) > 0 else 0
        ),
        "multi_source_ratio_current": (
            c_sum.get("multi_source_confirmed", 0) / c_sum.get("total_claims", 1)
            if c_sum.get("total_claims", 0) > 0 else 0
        ),
        "stock_drifts": stock_drifts,
        "has_drift": len(stock_drifts) > 0,
    }


def compare_data(baseline: dict, current: dict) -> dict:
    """对比数据基线，返回文件级漂移。"""
    b_files = {f["path"]: f for f in baseline.get("files", [])}
    c_files = {f["path"]: f for f in current.get("files", [])}

    changed = []
    added = []
    removed = []

    for path in sorted(set(b_files) | set(c_files)):
        b = b_files.get(path)
        c = c_files.get(path)
        if b and c:
            if b.get("sha256") != c.get("sha256"):
                changed.append({
                    "path": path,
                    "baseline_sha256": b.get("sha256"),
                    "current_sha256": c.get("sha256"),
                    "baseline_size": b.get("size_bytes"),
                    "current_size": c.get("size_bytes"),
                    "baseline_mtime": b.get("mtime"),
                    "current_mtime": c.get("mtime"),
                })
        elif c and not b:
            added.append({"path": path, "sha256": c.get("sha256"), "size": c.get("size_bytes")})
        elif b and not c:
            removed.append({"path": path, "baseline_sha256": b.get("sha256")})

    return {
        "baseline_file_count": len(b_files),
        "current_file_count": len(c_files),
        "changed": changed,
        "added": added,
        "removed": removed,
        "has_drift": len(changed) > 0 or len(added) > 0 or len(removed) > 0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline-dir", default="p8-audit/baseline")
    ap.add_argument("--current", required=True, help="当前报告目录或 JSON 文件路径")
    ap.add_argument("--json", action="store_true", help="输出 JSON 格式")
    args = ap.parse_args()

    bdir = Path(args.baseline_dir)
    ev_b = load_json(str(bdir / "evidence_baseline_20261021.json"))
    da_b = load_json(str(bdir / "data_baseline_20261021.json"))

    # 当前证据：从 reports/shadow/ 下的 JSON 报告提取
    cur_path = Path(args.current)
    if cur_path.is_dir():
        jsons = sorted(cur_path.glob("*.json"))
        if not jsons:
            print("ERROR: 当前目录下没有 JSON 报告", file=sys.stderr)
            sys.exit(1)
        ev_c = load_json(str(jsons[-1]))
    else:
        ev_c = load_json(str(cur_path))

    # 当前数据基线：需要先生成
    # 这里读取 data_baseline_current.json（如果存在）
    da_c_path = bdir / "data_baseline_current.json"
    if da_c_path.exists():
        da_c = load_json(str(da_c_path))
    else:
        da_c = {"files": []}

    ev_report = compare_evidence(ev_b, ev_c)
    da_report = compare_data(da_b, da_c)

    report = {
        "generated_at": datetime.now().isoformat(),
        "baseline_date": ev_b.get("baseline_date"),
        "evidence": ev_report,
        "data": da_report,
        "verdict": "PASS" if not ev_report["has_drift"] and not da_report["has_drift"] else "DRIFT_DETECTED",
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"基线对比报告 — {report['generated_at']}")
        print(f"判定: {report['verdict']}")
        print()
        print("=== 证据漂移 ===")
        print(f"  multi_source 比例: {ev_report['multi_source_ratio_baseline']:.1%} → {ev_report['multi_source_ratio_current']:.1%}")
        if ev_report["has_drift"]:
            for code, d in ev_report["stock_drifts"].items():
                print(f"  {code}: {len(d['status_changes'])} 条状态变化")
                for sc in d["status_changes"]:
                    print(f"    {sc['claim_id']}: {sc['from']} → {sc['to']}")
        else:
            print("  无漂移")
        print()
        print("=== 数据漂移 ===")
        print(f"  文件数: {da_report['baseline_file_count']} → {da_report['current_file_count']}")
        if da_report["changed"]:
            print(f"  {len(da_report['changed'])} 个文件 hash 变化:")
            for c in da_report["changed"]:
                print(f"    {c['path']}")
        if da_report["added"]:
            print(f"  {len(da_report['added'])} 个新增文件")
        if da_report["removed"]:
            print(f"  {len(da_report['removed'])} 个删除文件")
        if not da_report["has_drift"]:
            print("  无漂移")


if __name__ == "__main__":
    main()
