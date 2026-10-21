#!/usr/bin/env python3
"""P4 回放与评估测试。"""
import sys
import json
import tempfile
from pathlib import Path
from datetime import date, datetime

# 加载模块
_ROOT = Path("/Users/xiashuang/AI-股票系统")
sys.path.insert(0, str(_ROOT / "src"))

from backtest import provenance, replay, evaluate
from decision import contract, registry

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

# ---- provenance tests ----
print("=== Provenance Tests ===")

# P0-1: kline 可用
check("P0-1", "duckdb kline 可用", provenance.kline_available())

# P0-2: 交易日列表
td = provenance.kline_trading_dates(date(2026, 10, 1), date(2026, 10, 20))
check("P0-2", f"交易日列表获取: {len(td)} 天", len(td) > 0)

# P0-3: K线价格仅返回 <= as_of
prices = provenance.kline_prices_asof(["600276"], date(2026, 10, 15), lookback_days=10)
max_d = max(date.fromisoformat(r["trade_date"]) for r in prices.get("600276", [])) if prices.get("600276") else None
check("P0-3", "K线无前视 (max <= as_of)", max_d is not None and max_d <= date(2026, 10, 15))

# P0-4: 锚价快照选择
as_of = date(2026, 10, 15)
anchor_snap = provenance.anchor_snapshot_asof(as_of)
check("P0-4", f"锚价快照 asof={as_of}: available={anchor_snap['available']}, as_of={anchor_snap['as_of']}", 
      anchor_snap["available"] and anchor_snap["as_of"] == "2026-09-23")

# P0-5: 当前日期仍用最新可用快照 (无当前文件，回退到 09-23)
anchor_snap2 = provenance.anchor_snapshot_asof(date(2026, 10, 20))
check("P0-5", f"当前日期回退到最新快照: available={anchor_snap2['available']}, as_of={anchor_snap2['as_of']}",
      anchor_snap2["available"] and anchor_snap2["as_of"] == "2026-09-23")

# P0-6: 排名快照
ranking_snap = provenance.ranking_snapshot_asof(as_of)
check("P0-6", "排名快照历史日期不可用", not ranking_snap["available"])

# P0-7: 实时快照选择
realtime_snap = provenance.realtime_snapshot_asof(as_of)
check("P0-7", f"实时快照 asof={as_of}: available={realtime_snap['available']}, as_of={realtime_snap['as_of']}",
      realtime_snap["available"] and realtime_snap["as_of"] == "2026-09-23")

# P0-8: 研究笔记 git history 还原
rn = provenance.research_note_asof("600276", date(2026, 10, 15))
check("P0-8", f"研究笔记还原: available={rn['available']}, commit={rn['commit'][:8] if rn['commit'] else None}",
      rn["available"] and rn["commit"] is not None)

# P0-9: 综合 provenance_check
prov = provenance.provenance_check(as_of, ["600276"])
check("P0-9", "provenance_check 结构完整", 
      all(k in prov for k in ("as_of", "kline", "anchor", "ranking", "realtime", "research", "search", "jev")))

# P0-10: 前视偏差检查
la = provenance.check_lookahead(as_of, prices, anchor_snap.get("data"), ranking_snap.get("data"), realtime_snap.get("data"))
check("P0-10", "前视偏差检查通过", la["clean"] and la["violations"] == [])

# ---- replay tests ----
print("\n=== Replay Tests ===")

# P1-1: 单日回放
result = replay.replay_day(date(2026, 10, 15), "test-replay")
check("P1-1", f"单日回放成功: report_date={result['report_date']}", 
      result["report_date"] == "2026-10-15" and "stocks" in result)

# P1-2: 回放含 provenance
check("P1-2", "回放含 provenance", "provenance" in result and "lookahead_check" in result)

# P1-3: 回放看涉检查
check("P1-3", "回放看涉检查 clean", result["lookahead_check"]["clean"])

# P1-4: 回放 JEV/Search 标记不可用
check("P1-4", "JEV 标记 historical_unavailable", result["jev_status"] == "historical_unavailable")
check("P1-4b", "Search 标记 historical_unavailable", result["search_status"] == "historical_unavailable")

# P1-5: 回放快照信息
check("P1-5", "回放快照信息包含可用性", all(k in result["snapshot_info"] for k in 
      ("anchor_available", "ranking_available", "realtime_available")))

# P1-6: 批量回放（小范围）
with tempfile.TemporaryDirectory() as tmpdir:
    summary = replay.run_replay(date(2026, 10, 15), date(2026, 10, 16), tmpdir)
    check("P1-6", f"批量回放 2 天: success={summary['success_days']}", summary["success_days"] == 2)

# ---- evaluate tests ----
print("\n=== Evaluate Tests ===")

# 使用已有的长回放结果
run_dir = Path("/tmp/backtest_long/1b4c4dcbe16c")
if run_dir.exists():
    eval_result = evaluate.run_full_evaluation(run_dir)
    check("E1", "评估完整运行", "data_quality" in eval_result and "traceability" in eval_result)
    check("E2", "数据质量: 无前视违规", eval_result["data_quality"]["lookahead_check"]["total_violations"] == 0)
    check("E3", "系统可靠性: 0 内部错误", eval_result["system_reliability"]["internal_errors"] == 0)
    check("E4", "可追溯性: action 分布有值", len(eval_result["traceability"]["action_distribution"]) > 0)
    check("E5", "前视收益: 可计算", eval_result["forward_returns"]["computable"])
    check("E6", "前视收益: 样本量>0", eval_result["forward_returns"]["total_samples"] > 0)

# ---- decision contract tests ----
print("\n=== Decision Contract Tests ===")

# C1: 合法输出通过
valid = {"model_id": "test", "report_date": "2026-10-20", "generated_at": "2026-10-20T18:00:00",
         "stocks": [{"code": "sh600276", "name": "恒瑞", "action": "HOLD", "confidence": 0.7,
                     "reasoning": "x", "supports": [], "conflicts": [], "gaps": [], "conditions": [],
                     "invalidation": [], "evidence_claims": [], "unknown_fields": [], "provenance": {}}]}
ok, errs = contract.validate_decision_output(valid)
check("C1", "合法输出通过", ok)

# C2: 非法 action 拒绝
invalid = dict(valid)
invalid["stocks"][0]["action"] = "BUY_NOW"
ok2, errs2 = contract.validate_decision_output(invalid)
check("C2", "非法 action 拒绝", not ok2 and any("无效" in e for e in errs2))

# C3: confidence 越界拒绝
invalid2 = dict(valid)
invalid2["stocks"][0]["confidence"] = 1.5
ok3, errs3 = contract.validate_decision_output(invalid2)
check("C3", "confidence 越界拒绝", not ok3)

# C4: 缺少必需字段拒绝
invalid3 = dict(valid)
del invalid3["model_id"]
ok4, errs4 = contract.validate_decision_output(invalid3)
check("C4", "缺 model_id 拒绝", not ok4)

# ---- decision registry tests ----
print("\n=== Decision Registry Tests ===")

# R1: 空注册表
reg = registry.load_registry()
check("R1", "空注册表加载", len(reg.models) == 0 and reg.primary_model_id is None)

# R2: 添加模型
spec = registry.DecisionModelSpec(
    model_id="test-model", display_name="Test", provider="test", base_url="http://x",
    api_key_env="TEST_KEY", api_key_location=".env"
)
reg2 = registry.DecisionModelRegistry()
added = reg2.add(spec)
check("R2", "添加模型成功", added and len(reg2.models) == 1)

# R3: 重复添加拒绝
added2 = reg2.add(spec)
check("R3", "重复添加拒绝", not added2 and len(reg2.models) == 1)

# R4: compare_outputs 同一
diff = registry.compare_outputs(valid, valid)
check("R4", "对比同一输出: identical=True", diff["identical"])

# R5: compare_outputs 不同
diff2 = registry.compare_outputs(valid, {"model_id": "t", "report_date": "2026-10-20", "generated_at": "2026-10-20T18:00:00",
    "stocks": [{"code": "sh600276", "name": "恒瑞", "action": "WAIT", "confidence": 0.7,
                "reasoning": "x", "supports": [], "conflicts": [], "gaps": [], "conditions": [],
                "invalidation": [], "evidence_claims": [], "unknown_fields": [], "provenance": {}}]})
check("R5", "对比不同输出: identical=False", not diff2["identical"])

# ---- summary ----
print(f"\n=== Summary: {PASS} passed, {FAIL} failed ===")
sys.exit(0 if FAIL == 0 else 1)
