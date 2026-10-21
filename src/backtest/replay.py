#!/usr/bin/env python3
"""P4 多日历史回放引擎 (P4-1)。

特性：
- 按交易日时间顺序逐日重放
- 严格反前视：所有输入通过 provenance.asof 选择器
- 历史日期 research 通过 git history 还原
- 缺失 snapshot 自动降级并记录
- 输出写入 reports/backtest/<task_id>/
"""
import json
import os
import sys
import hashlib
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 加载本地引擎模块
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from engine import data_loader, trading_day, market_judge, stock_judge, report
from . import provenance

# ---- 配置 ----
REPORTS_DIR = os.path.join(os.path.dirname(_ROOT), "reports", "backtest")
TZ = datetime.now().astimezone().tzinfo

def _now_str() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

def _date_str() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")

def _task_id(as_of_start: date, as_of_end: date) -> str:
    s = f"backtest_{as_of_start.isoformat()}_{as_of_end.isoformat()}_{_now_str()}"
    return hashlib.md5(s.encode()).hexdigest()[:12]

# ---- 核心：逐日重放 ----
def build_pool_status_from_provenance(
    as_of: date,
    kline_prices: Dict[str, List[Dict]],
    anchor_snap: Dict[str, Any],
    ranking_snap: Dict[str, Any],
    realtime_snap: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    从 provenance 数据构建 pool_status（供 stock_judge 使用）。
    返回 (anchor_idx, ranking_idx, pool_status, snapshot_info)
    """
    # 1) anchor_idx
    anchor_data = anchor_snap.get("data") if anchor_snap.get("available") else None
    anchor_idx = data_loader.build_anchor_index(anchor_data or [])

    # 2) ranking_idx
    ranking_data = ranking_snap.get("data") if ranking_snap.get("available") else None
    ranking_idx = data_loader.build_ranking_index(ranking_data or {})

    # 3) portfolio（无历史快照，仅当前）
    portfolio_idx = {}  # 无历史 portfolio

    # 4) 用历史价格填补当前价（当无锚价快照时）
    # 取 as_of 的收盘价作为 current
    latest_prices = {c: rows[-1]["close"] for c, rows in kline_prices.items() if rows}

    # 5) 构建 pool_status
    pool_status = {}
    for stock in data_loader.P0_POOL + data_loader.P2_POOL:
        code = stock["code"]
        num_code = data_loader._norm_code(code).replace("sh", "").replace("sz", "").replace("hk", "")
        a = anchor_idx.get(code, {})
        r = ranking_idx.get(code, {})
        curr_price = latest_prices.get(num_code)  # 历史收盘价
        pool_status[code] = {
            "name": a.get("name", code),
            "market": a.get("market", ""),
            "pool": "P0" if code in [s["code"] for s in data_loader.P0_POOL] else "P2",
            "current": curr_price,  # 历史价格，非实时
            "anchor": a.get("anchor"),
            "deviation": a.get("deviation"),
            "status": a.get("status"),
            "pe": a.get("pe"),
            "prev_close": a.get("prev_close"),
            "change_pct": None,  # 历史无实时涨跌
            "composite_score": r.get("composite_score"),
            "tech_score": r.get("tech_score"),
            "ml_boost": r.get("ml_boost"),
            "latest_date": r.get("latest_date"),
            "position": None,
            "portfolio_status": None,
            "days_since_update": None,
        }

    snapshot_info = {
        "anchor_available": anchor_snap.get("available", False),
        "anchor_asof": anchor_snap.get("as_of"),
        "ranking_available": ranking_snap.get("available", False),
        "ranking_asof": ranking_snap.get("as_of"),
        "realtime_available": realtime_snap.get("available", False),
        "realtime_asof": realtime_snap.get("as_of"),
    }
    return pool_status, snapshot_info

def replay_day(as_of: date, task_id: str, historical_mode: bool = True) -> Dict[str, Any]:
    """
    执行单个交易日的重放。
    historical_mode=True: 标记缺失 snapshot 为 unavailable，research 使用 git history。
    """
    codes = [data_loader._norm_code(s["code"]).replace("sh", "").replace("sz", "").replace("hk", "")
             for s in data_loader.P0_POOL + data_loader.P2_POOL]

    # 1) 加载历史价格（严格 <= as_of）
    kline_prices = provenance.kline_prices_asof(codes, as_of, lookback_days=200)

    # 2) provenance: 获取各源快照
    anchor_snap = provenance.anchor_snapshot_asof(as_of)
    ranking_snap = provenance.ranking_snapshot_asof(as_of)
    realtime_snap = provenance.realtime_snapshot_asof(as_of)

    # 3) 构建 pool_status
    pool_status, snap_info = build_pool_status_from_provenance(
        as_of, kline_prices, anchor_snap, ranking_snap, realtime_snap
    )

    # 4) 交易日判断（使用 as_of 作为基准）
    trading_status = trading_day.trading_day_status(datetime.combine(as_of, datetime.min.time()))
    # freshness 使用实时快照日期（或 ranking 日期）
    freshness = {
        "check_time": _now_str(),
        "realtime_date": realtime_snap.get("as_of"),
        "ranking_run_date": ranking_snap.get("as_of"),
        "issues": [],
    }
    effective = trading_day.effective_trading_day(trading_status, freshness)

    # 5) 大盘研判（基于可用锚价/排名）
    market = market_judge.judge_market(anchor_snap.get("data") or [], ranking_snap.get("data"), freshness)

    # 6) JEV & Search 状态：历史模式下标记为不可用（无记录）
    jev_status = "historical_unavailable"
    search_status = "historical_unavailable"

    # 7) 股票逐只分析
    # 准备 research_override（历史模式）
    research_override = {}
    if historical_mode:
        for code in codes:
            rn = provenance.research_note_asof(code, as_of)
            if rn.get("available"):
                # 转换为 stock_judge 期望的结构
                content = rn["content"]
                import re
                fm = {}
                fm_match = re.search(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
                if fm_match:
                    for line in fm_match.group(1).split('\n'):
                        if ':' in line:
                            k, v = line.split(':', 1)
                            fm[k.strip()] = v.strip().strip("'\"")
                research_override[code] = {
                    "exists": True,
                    "meta": None,
                    "note_summary": fm,
                    "last_update": fm.get("update_time") or rn["commit_date"],
                    "raw_note": content[:8000],
                    "provenance": {"commit": rn["commit"], "commit_date": rn["commit_date"]},
                }
            else:
                research_override[code] = {"exists": False, "reason": rn["reason"]}

    stock_analyses = []
    for stock in data_loader.P0_POOL + data_loader.P2_POOL:
        code = stock["code"]
        jev_result = None  # 历史无 JEV
        # 修改：stock_judge 支持 research_override
        analysis = stock_judge.judge_stock(code, pool_status, jev_result,
                                           research_override=research_override.get(code))
        # 新鲜度门槛（历史模式下用 ranking_asof 或 realtime_asof）
        ranking_data = ranking_snap.get("data")
        realtime_date = realtime_snap.get("as_of")
        analysis = stock_judge.apply_staleness_to_analysis(analysis, ranking_data or {}, realtime_date, report_date=as_of.isoformat())
        stock_analyses.append(analysis)

    # 8) 重点关注
    focus = {"top_stocks": [a["name"] for a in stock_analyses
                            if a.get("action", {}).get("action") in ("CONSIDER_ENTRY", "CONSIDER_ADD")]}

    # 9) 组装结果
    run_result = {
        "generated_at": _now_str(),
        "report_date": as_of.isoformat(),
        "replay_task_id": task_id,
        "historical_mode": historical_mode,
        "trading_day": effective,
        "freshness": freshness,
        "config_status": "HISTORICAL_REPLAY",
        "jev_status": jev_status,
        "search_status": search_status,
        "snapshot_info": snap_info,
        "market": market,
        "stocks": stock_analyses,
        "focus": focus,
        "provenance": provenance.provenance_check(as_of, codes),
        "lookahead_check": provenance.check_lookahead(
            as_of, kline_prices,
            anchor_snap.get("data"), ranking_snap.get("data"), realtime_snap.get("data")
        ),
    }
    return run_result

def run_replay(as_of_start: date, as_of_end: date,
               out_dir: Optional[str] = None, historical_mode: bool = True) -> Dict[str, Any]:
    """
    批量回放：as_of_start 到 as_of_end（含）的所有交易日。
    """
    dates = provenance.kline_trading_dates(as_of_start, as_of_end)
    if not dates:
        return {"error": "无交易日"}

    task_id = _task_id(as_of_start, as_of_end)
    run_dir = Path(out_dir or REPORTS_DIR) / task_id
    run_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "task_id": task_id,
        "start": as_of_start.isoformat(),
        "end": as_of_end.isoformat(),
        "total_days": len(dates),
        "success_days": 0,
        "failed_days": 0,
        "errors": [],
        "output_dir": str(run_dir),
    }

    for i, d_str in enumerate(dates):
        d = _parse_date(d_str)
        print(f"[{i+1}/{len(dates)}] 回放 {d_str}...")
        try:
            result = replay_day(d, task_id, historical_mode)
            # 写入 JSON
            out_file = run_dir / f"{d_str}.json"
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2, default=str)
            # 生成报告
            report_content = report.generate_report(result)
            report_file = run_dir / f"{d_str}.md"
            with open(report_file, "w", encoding="utf-8") as f:
                f.write(report_content)
            summary["success_days"] += 1
        except Exception as e:
            summary["failed_days"] += 1
            summary["errors"].append({"date": d_str, "error": str(e)})
            print(f"  ❌ 失败: {e}")

    # 写汇总
    summary_file = run_dir / "summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n回放完成: {summary['success_days']}/{summary['total_days']} 成功")
    print(f"输出目录: {run_dir}")
    return summary

def _parse_date(s: str) -> Optional[date]:
    if not s: return None
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        s = f"{s[:4]}-{s[4:6]}-{s[6:]}"
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None

# CLI
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="P4 多日历史回放")
    parser.add_argument("--start", required=True, help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--out", help="输出目录")
    parser.add_argument("--no-historical", action="store_true", help="关闭历史模式（不建议）")
    args = parser.parse_args()

    start = _parse_date(args.start)
    end = _parse_date(args.end)
    if not start or not end:
        print("错误: 日期格式需 YYYY-MM-DD")
        sys.exit(1)

    run_replay(start, end, args.out, historical_mode=not args.no_historical)

