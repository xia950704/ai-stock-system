#!/usr/bin/env python3
"""P3 引擎测试（离线，不触发真实 JEV / 真实网络）。"""
import json, os, sys, tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

WS = Path("/Users/xiashuang/AI-股票系统")
sys.path.insert(0, str(WS / "src"))
from engine import data_loader, trading_day, market_judge, stock_judge, jev_adapter, report

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

# T-D01: 数据加载正常
try:
    anchor, err = data_loader.load_anchor_status()
    check("T-D01", "anchor_status.json 加载成功", anchor is not None and err is None, str(err))
except Exception as e:
    check("T-D01", "anchor_status.json 加载成功", False, str(e))

# T-D02: 缺失文件
try:
    data, err = data_loader._load_json("/nonexistent/path/file.json")
    check("T-D02", "缺失文件返回 None + 错误", data is None and err is not None, str(err))
except Exception as e:
    check("T-D02", "缺失文件返回 None + 错误", False, str(e))

# T-D03: 无效 JSON
with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
    f.write("{invalid json")
    f.flush()
    data, err = data_loader._load_json(f.name)
    check("T-D03", "无效 JSON 返回错误", data is None and err is not None, str(err))

# T-D04: 代码标准化
check("T-D04", "代码标准化 sh600276", data_loader._norm_code("600276.SH") == "sh600276")
check("T-D04b", "代码标准化 sz000963", data_loader._norm_code("000963.SZ") == "sz000963")
check("T-D04c", "代码标准化纯数字", data_loader._norm_code("600276") == "sh600276")

# T-T01: 周末判断
TZ = timezone(timedelta(hours=8))
sat = datetime(2026, 10, 24, tzinfo=TZ)
sun = datetime(2026, 10, 25, tzinfo=TZ)
wed = datetime(2026, 10, 21, tzinfo=TZ)
check("T-T01", "周六为非交易日", trading_day.is_weekend(sat) is True)
check("T-T01b", "周日为非交易日", trading_day.is_weekend(sun) is True)
check("T-T01c", "周三为交易日", trading_day.is_weekend(wed) is False)

# T-T02: 交易日状态
status = trading_day.trading_day_status(sat)
check("T-T02", "周六 likely_trading_day=False", status["likely_trading_day"] is False)
status = trading_day.trading_day_status(wed)
check("T-T02b", "周三 likely_trading_day=True", status["likely_trading_day"] is True)

# T-M01: 大盘研判有数据
try:
    anchor_data, _ = data_loader.load_anchor_status()
    ranking_data, _ = data_loader.load_ranking()
    freshness = trading_day.data_freshness()
    market = market_judge.judge_market(anchor_data or [], ranking_data, freshness)
    check("T-M01", "大盘研判返回 verdict", market.get("verdict") in ("偏多", "偏空", "中性", "无法判断"))
    check("T-M01b", "大盘研判有局限说明", len(market.get("limitations", [])) > 0)
except Exception as e:
    check("T-M01", "大盘研判返回 verdict", False, str(e))

# T-M02: 大盘研判无数据
market = market_judge.judge_market([], None, {"issues": []})
check("T-M02", "无数据时无法判断", market.get("verdict") == "无法判断")

# T-J01: JEV Mock 正常
r = jev_adapter.jev_yes_no({"x": 1}, "1 < 2", use_mock=True,
                            mock_response={"ok": True, "model": "mock", "answers": {"answer": {"noul": 0.99}}})
check("T-J01", "Mock JEV 正常返回", r.get("ok") is True and jev_adapter.is_available(r))

# T-J02: JEV Mock 失败
r = jev_adapter.jev_yes_no({"x": 1}, "1 < 2", use_mock=True,
                            mock_response={"ok": False, "error_code": "timeout", "error_message": "timeout"})
check("T-J02", "Mock JEV 失败不等于中性", r.get("ok") is False and jev_adapter.is_available(r) is False)
check("T-J02b", "失败状态可追溯", jev_adapter.failure_status(r) == "timeout")

# T-J03: JEV 错误码分类
check("T-J03", "401 -> auth", jev_adapter._classify_error(401, "") == "auth")
check("T-J03b", "402 -> insufficient", jev_adapter._classify_error(402, "") == "insufficient")
check("T-J03c", "403 -> forbidden", jev_adapter._classify_error(403, "") == "forbidden")
check("T-J03d", "404 -> not_found", jev_adapter._classify_error(404, "") == "not_found")
check("T-J03e", "400 model_na", jev_adapter._classify_error(400, "model is not available") == "model_na")
check("T-J03f", "500 -> server_error", jev_adapter._classify_error(500, "") == "server_error")

# T-S01: 股票分析正常
try:
    anchor_data, _ = data_loader.load_anchor_status()
    ranking_data, _ = data_loader.load_ranking()
    portfolio_data, _ = data_loader.load_portfolio()
    anchor_idx = data_loader.build_anchor_index(anchor_data or [])
    ranking_idx = data_loader.build_ranking_index(ranking_data or {})
    portfolio_idx = data_loader.build_portfolio_index(portfolio_data or [])
    pool_status = data_loader.get_pool_status(anchor_idx, ranking_idx, portfolio_idx)
    analysis = stock_judge.judge_stock("sh600276", pool_status, None)
    check("T-S01", "股票分析返回完整结构", all(k in analysis for k in
          ["price_layer", "fund_layer", "rd_layer", "order_layer", "jev_layer", "synthesis", "action"]))
    check("T-S01b", "行动建议有效", analysis["action"].get("action") in
          ["OBSERVE", "WAIT", "CONSIDER_ENTRY", "HOLD", "CONSIDER_ADD", "CONSIDER_REDUCE", "CONSIDER_EXIT", "INSUFFICIENT_EVIDENCE"])
except Exception as e:
    check("T-S01", "股票分析返回完整结构", False, str(e))

# T-S02: 锚价失效股票（直接测试 _recommend_action）
try:
    action = stock_judge._recommend_action({"status": "锚价失效", "deviation": 20}, {})
    check("T-S02", "锚价失效股票行动为 OBSERVE", action.get("action") == "OBSERVE")
except Exception as e:
    check("T-S02", "锚价失效股票行动为 OBSERVE", False, str(e))

# T-R01: 报告生成
try:
    run_result = {
        "generated_at": "2026-10-20 14:00:00",
        "report_date": "2026-10-20",
        "trading_day": {"effective_date": "2026-10-20", "verdict": "TRADING_DAY", "reason": "test", "confidence": "medium"},
        "freshness": {"issues": []},
        "config_status": "PASS",
        "jev_status": "mock",
        "missing_data": [],
        "market": {"verdict": "中性", "confidence": "low", "evidence": ["test"], "counter_evidence": [], "scenarios": {}, "limitations": ["test"]},
        "stocks": [],
        "focus": {"top_stocks": [], "risks": [], "events": [], "gaps": []},
        "traces": [],
    }
    content = report.generate_report(run_result)
    check("T-R01", "报告生成非空", len(content) > 100)
    check("T-R01b", "报告包含必要章节", all(s in content for s in ["A. 运行状态", "B. 大盘研判", "C. 股票分析", "D. 重点跟踪事项", "E. 审计与追溯"]))
except Exception as e:
    check("T-R01", "报告生成非空", False, str(e))

print(f"\n=== test_engine: {PASS} passed, {FAIL} failed ===")
sys.exit(1 if FAIL else 0)
