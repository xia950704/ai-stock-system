#!/usr/bin/env python3
"""P4 研判质量评估 (P4-2)。

评估维度：
1. 数据质量：输入完整率、新鲜度合格率、无效记录
2. 系统可靠性：任务成功率、错误降级、重复运行一致性
3. 判断可追溯性：关键结论有来源比例、有反证/失效条件比例
4. 历史表现：信号与后续价格关系（样本量受限时明确标记）
"""
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

def load_backtest_results(run_dir: Path) -> List[Dict[str, Any]]:
    """加载回放目录下所有 JSON 结果。"""
    results = []
    for f in sorted(run_dir.glob("*.json")):
        if f.name == "summary.json":
            continue
        with open(f, encoding="utf-8") as fp:
            results.append(json.load(fp))
    return sorted(results, key=lambda x: x["report_date"])

def evaluate_data_quality(results: List[Dict]) -> Dict[str, Any]:
    """数据质量评估。"""
    if not results:
        return {"error": "无结果"}

    total = len(results)
    anchor_avail = sum(1 for r in results if r.get("snapshot_info", {}).get("anchor_available"))
    ranking_avail = sum(1 for r in results if r.get("snapshot_info", {}).get("ranking_available"))
    realtime_avail = sum(1 for r in results if r.get("snapshot_info", {}).get("realtime_available"))

    # 新鲜度：统计 FRESH / STALE / DATE_UNKNOWN
    fresh = stale = unknown = 0
    for r in results:
        gate = r.get("stocks", [{}])[0].get("staleness_gate", {})
        verdict = gate.get("verdict", "UNKNOWN")
        if verdict == "FRESH": fresh += 1
        elif verdict == "STALE": stale += 1
        elif verdict == "DATE_UNKNOWN": unknown += 1

    # 价格数据完整性（来自 provenance.lookahead_check）
    lookahead_clean = sum(1 for r in results if r.get("lookahead_check", {}).get("clean", False))
    lookahead_violations = sum(len(r.get("lookahead_check", {}).get("violations", [])) for r in results)

    return {
        "total_days": total,
        "anchor_availability": {"count": anchor_avail, "rate": round(anchor_avail/total, 3)},
        "ranking_availability": {"count": ranking_avail, "rate": round(ranking_avail/total, 3)},
        "realtime_availability": {"count": realtime_avail, "rate": round(realtime_avail/total, 3)},
        "freshness_distribution": {
            "fresh": fresh, "stale": stale, "date_unknown": unknown,
            "fresh_rate": round(fresh/total, 3) if total else 0
        },
        "lookahead_check": {"clean_days": lookahead_clean, "total_violations": lookahead_violations},
        "note": "ranking 仅 2026-10-20 有快照，其他日期不可用；anchor 仅 09-23 和 10-20 有快照"
    }

def evaluate_system_reliability(results: List[Dict]) -> Dict[str, Any]:
    """系统可靠性评估。"""
    if not results:
        return {"error": "无结果"}

    total = len(results)
    # 任务成功率（回放层面已保证 100%，这里看内部错误）
    errors = sum(1 for r in results if r.get("market", {}).get("verdict") == "ERROR")
    # 降级统计
    jev_unavail = sum(1 for r in results if r.get("jev_status") in ("historical_unavailable", "unavailable"))
    search_unavail = sum(1 for r in results if r.get("search_status") in ("historical_unavailable", "unavailable"))
    staleness_blocks = sum(1 for r in results for s in r.get("stocks", [])
                           if s.get("staleness_gate", {}).get("blocking"))

    return {
        "total_days": total,
        "internal_errors": errors,
        "jev_unavailable_days": jev_unavail,
        "search_unavailable_days": search_unavail,
        "staleness_gate_blocks": staleness_blocks,
        "note": "历史回放中 JEV/Search 标记为不可用，不计为系统故障"
    }

def evaluate_traceability(results: List[Dict]) -> Dict[str, Any]:
    """判断可追溯性评估。"""
    if not results:
        return {"error": "无结果"}

    total_stocks = 0
    has_evidence = 0
    has_counter = 0
    has_invalidation = 0
    action_dist = Counter()

    for r in results:
        for s in r.get("stocks", []):
            total_stocks += 1
            action = s.get("action", {}).get("action", "UNKNOWN")
            action_dist[action] += 1
            synthesis = s.get("synthesis", {})
            if synthesis.get("supports"):
                has_evidence += 1
            if synthesis.get("conflicts"):
                has_counter += 1
            if s.get("action", {}).get("invalidation"):
                has_invalidation += 1

    return {
        "total_stock_analyses": total_stocks,
        "with_supporting_evidence": {"count": has_evidence, "rate": round(has_evidence/total_stocks, 3) if total_stocks else 0},
        "with_counter_evidence": {"count": has_counter, "rate": round(has_counter/total_stocks, 3) if total_stocks else 0},
        "with_invalidation_conditions": {"count": has_invalidation, "rate": round(has_invalidation/total_stocks, 3) if total_stocks else 0},
        "action_distribution": dict(action_dist),
        "note": "历史模式下多数为 INSUFFICIENT_EVIDENCE/OBSERVE（缺锚价/排名快照），非引擎缺陷"
    }

def evaluate_repeatability(run_dir1: Path, run_dir2: Path) -> Dict[str, Any]:
    """重复运行一致性评估。"""
    r1 = load_backtest_results(run_dir1)
    r2 = load_backtest_results(run_dir2)
    if len(r1) != len(r2):
        return {"error": f"日期数不等: {len(r1)} vs {len(r2)}"}

    mismatches = 0
    for d1, d2 in zip(r1, r2):
        if d1["report_date"] != d2["report_date"]:
            mismatches += 1
            continue
        # 比较每只股票的 action
        for s1, s2 in zip(d1.get("stocks", []), d2.get("stocks", [])):
            a1 = s1.get("action", {}).get("action")
            a2 = s2.get("action", {}).get("action")
            if a1 != a2:
                mismatches += 1

    return {
        "run1_days": len(r1),
        "run2_days": len(r2),
        "action_mismatches": mismatches,
        "consistent": mismatches == 0,
        "note": "历史模式下应完全一致（确定性输入 -> 确定性输出）"
    }

def evaluate_forward_returns(results: List[Dict], price_db: str = None) -> Dict[str, Any]:
    """
    历史表现评估：判断方向 vs 后续价格变化。
    样本量极小时（如仅 2 天有完整 snapshot），明确标记不可计算。
    """
    # 这里需要后续价格数据。使用 duckdb 获取。
    try:
        import duckdb
        conn = duckdb.connect(price_db or os.path.expanduser("~/harness/deeppulse/db/astock.duckdb"), read_only=True)
    except Exception as e:
        return {"error": f"无法连接价格库: {e}", "computable": False}

    action_forward = {}  # action -> list of forward returns
    for r in results:
        r_date = date.fromisoformat(r["report_date"])
        for s in r.get("stocks", []):
            action = s.get("action", {}).get("action")
            code = s.get("code")
            if not code or action in ("INSUFFICIENT_EVIDENCE", "OBSERVE", "UNKNOWN"):
                continue
            num_code = code.replace("sh", "").replace("sz", "").replace("hk", "")
            # 获取未来 5/10/20 个交易日收益
            try:
                rows = conn.execute("""
                    SELECT trade_date, close FROM daily_kline
                    WHERE code = ? AND trade_date > ?
                    ORDER BY trade_date LIMIT 20
                """, [num_code, r_date.isoformat()]).fetchall()
                if len(rows) >= 5:
                    c0 = rows[0][1]
                    ret_5 = (rows[4][1] / c0 - 1) * 100 if rows[4][1] and c0 else None
                    ret_10 = (rows[9][1] / c0 - 1) * 100 if len(rows) >= 10 and rows[9][1] and c0 else None
                    ret_20 = (rows[19][1] / c0 - 1) * 100 if len(rows) >= 20 and rows[19][1] and c0 else None
                    action_forward.setdefault(action, []).append({
                        "code": code, "date": r_date.isoformat(),
                        "ret_5d": ret_5, "ret_10d": ret_10, "ret_20d": ret_20
                    })
            except Exception:
                pass

    # 统计
    summary = {}
    for action, samples in action_forward.items():
        vals_5 = [x["ret_5d"] for x in samples if x["ret_5d"] is not None]
        vals_10 = [x["ret_10d"] for x in samples if x["ret_10d"] is not None]
        vals_20 = [x["ret_20d"] for x in samples if x["ret_20d"] is not None]
        summary[action] = {
            "sample_count": len(samples),
            "ret_5d": {"mean": round(sum(vals_5)/len(vals_5), 2) if vals_5 else None,
                       "median": round(sorted(vals_5)[len(vals_5)//2], 2) if vals_5 else None,
                       "positive_rate": round(sum(1 for v in vals_5 if v > 0)/len(vals_5), 3) if vals_5 else None},
            "ret_10d": {"mean": round(sum(vals_10)/len(vals_10), 2) if vals_10 else None,
                        "median": round(sorted(vals_10)[len(vals_10)//2], 2) if vals_10 else None,
                        "positive_rate": round(sum(1 for v in vals_10 if v > 0)/len(vals_10), 3) if vals_10 else None},
            "ret_20d": {"mean": round(sum(vals_20)/len(vals_20), 2) if vals_20 else None,
                        "median": round(sorted(vals_20)[len(vals_20)//2], 2) if vals_20 else None,
                        "positive_rate": round(sum(1 for v in vals_20 if v > 0)/len(vals_20), 3) if vals_20 else None},
        }

    # 判断是否有足够样本
    total_samples = sum(v["sample_count"] for v in summary.values())
    computable = total_samples >= 20  # 经验阈值

    return {
        "by_action": summary,
        "total_samples": total_samples,
        "computable": computable,
        "note": f"样本量 {total_samples} {'足够' if computable else '不足'}，{'可计算统计量' if computable else '仅作参考，不可宣称稳定表现'}"
    }

def run_full_evaluation(run_dir: Path, price_db: str = None) -> Dict[str, Any]:
    """完整评估流程。"""
    results = load_backtest_results(run_dir)
    if not results:
        return {"error": "无回放结果"}

    # 尝试寻找第二次运行目录做重复性测试
    parent = run_dir.parent
    other_dirs = [d for d in parent.iterdir() if d.is_dir() and d != run_dir]
    repeatability = None
    if other_dirs:
        repeatability = evaluate_repeatability(run_dir, other_dirs[0])

    eval_result = {
        "run_dir": str(run_dir),
        "evaluated_at": datetime.now().isoformat(),
        "data_quality": evaluate_data_quality(results),
        "system_reliability": evaluate_system_reliability(results),
        "traceability": evaluate_traceability(results),
        "repeatability": repeatability,
        "forward_returns": evaluate_forward_returns(results, price_db),
    }
    return eval_result

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="P4 研判质量评估")
    parser.add_argument("--run-dir", required=True, help="回放输出目录（含 summary.json）")
    parser.add_argument("--price-db", help="DuckDB 路径（默认环境变量 ASTOCK_DB）")
    parser.add_argument("--output", help="评估结果输出路径")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    result = run_full_evaluation(run_dir, args.price_db)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        print(f"评估结果已写入: {args.output}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

