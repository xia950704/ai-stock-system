#!/usr/bin/env python3
"""每日研判引擎 CLI（P3-2 编排层）。

用法：
    python3 daily_judge.py [--date YYYY-MM-DD] [--mock-jev] [--output PATH]

流程：
  1. 配置验证
  2. 数据读取与校验
  3. 交易日与新鲜度判断
  4. 大盘研判
  5. 关注股票逐只分析
  6. JEV 探查（真实或 Mock）
  7. 证据综合与行动建议
  8. 报告生成

重要：本引擎不执行任何交易，不修改任何原始文件。
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, timedelta
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from engine import data_loader, trading_day, market_judge, stock_judge, jev_adapter, report
    from decision import adapter as decision_adapter
    from stock_codes import P0_POOL, P2_POOL, all_judge_codes
except ImportError:
    from . import data_loader, trading_day, market_judge, stock_judge, jev_adapter, report
    from decision import adapter as decision_adapter
    from stock_codes import P0_POOL, P2_POOL, all_judge_codes

TZ = timezone(timedelta(hours=8))


def run_config_check() -> str:
    """运行配置验证，返回状态字符串。

    通过 subprocess 调用 scripts/validate_stock_config.py，隔离执行环境：
    - capture_output=True：不污染主进程 stdout
    - shell=False：命令以列表形式传入，避免 shell 注入
    - timeout=30：防止验证脚本死循环
    - 显式 returncode 判断：0=PASS，1=FAIL，其余=ERROR
    """
    vsc_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "scripts", "validate_stock_config.py")
    if not os.path.exists(vsc_path):
        return "配置验证脚本不存在"
    try:
        proc = subprocess.run(
            [sys.executable, vsc_path],
            capture_output=True, text=True,
            timeout=30,
        )
        if proc.returncode == 0:
            return "PASS"
        return "FAIL (exit=%d): %s" % (proc.returncode, (proc.stderr or proc.stdout)[-300:])
    except subprocess.TimeoutExpired:
        return "ERROR: 配置验证超时（30s）"
    except Exception as e:
        return f"ERROR: {e}"


def run_jev_probe(codes: list, use_mock: bool = False,
                  force_mock_failure: bool = False) -> Dict[str, Any]:
    """对每只股票运行 JEV 探查。"""
    results = {}
    for code in codes:
        state = {
            "code": code,
            "description": "P3 daily research probe, no position or cost data"
        }
        if force_mock_failure:
            r = jev_adapter.jev_yes_no(
                state=state,
                question="Is this stock's current price above its anchor price?",
                mode="noul",
                use_mock=True,
                mock_response={
                    "ok": False,
                    "error_code": "model_na",
                    "error_message": "controlled shadow-run failure",
                },
            )
        elif use_mock:
            r = jev_adapter.jev_yes_no(
                state=state,
                question="Is this stock's current price above its anchor price?",
                mode="noul",
                use_mock=True,
                mock_response={"ok": True, "model": "mock", "answers": {"answer": {"noul": 0.5}}},
            )
        else:
            r = jev_adapter.jev_yes_no(
                state=state,
                question="Is this stock's current price above its anchor price?",
                mode="noul",
            )
        results[code] = r
    return results


def main():
    parser = argparse.ArgumentParser(description="每日研判引擎（P3-2）")
    parser.add_argument("--date", help="指定报告日期 YYYY-MM-DD（默认今天）")
    parser.add_argument("--mock-jev", action="store_true", help="使用 Mock JEV（不触发真实调用）")
    parser.add_argument("--mock-jev-fail", action="store_true", help="使用固定失败的 Mock JEV，验证降级路径")
    parser.add_argument("--search", action="store_true",
                        help="启用 Search API 外部证据探查（真实调用，需 SEARCH_API_KEY）")
    parser.add_argument("--mock-search", action="store_true",
                        help="使用 Mock Search API（不触发真实调用）")
    parser.add_argument("--output", help="指定报告输出路径")
    parser.add_argument("--json", action="store_true", help="同时输出 JSON 结果")
    parser.add_argument("--force", action="store_true",
                        help="显式允许覆盖指定的报告输出文件")
    parser.add_argument("--decision-model", action="store_true",
                        help="启用 AMD Decision Model 替代纯规则判断")
    parser.add_argument("--decision-model-name", default=None,
                        help="指定 AMD 决策模型名（默认 Clef）")
    args = parser.parse_args()

    now = datetime.now(TZ)
    report_date = args.date or now.strftime("%Y-%m-%d")
    generated_at = now.strftime("%Y-%m-%d %H:%M:%S")

    print("=" * 60)
    print("每日研判引擎（P3-2）")
    print(f"报告日期：{report_date}")
    print(f"生成时间：{generated_at}")
    print("=" * 60)
    print()

    print("[1/8] 配置验证...")
    config_status = run_config_check()
    print(f"  配置状态：{config_status}")
    print()

    # [1.5/8] 数据源健康检查（P3-2 基础设施）
    print("[1.5/8] 数据源健康检查...")
    try:
        from data_provider import run_health_check, format_health_report
        health = run_health_check()
        for s in health.sources:
            status = "✅" if s.available else "❌"
            print(f"  {status} {s.name}: {s.detail}")
        if not health.all_available:
            print(f"  ⚠️  共 {len(health.unavailable_source_names())} 个数据源不可用: "
                  f"{', '.join(health.unavailable_source_names())}")
    except Exception as e:
        print(f"  ⚠️  健康检查异常: {e}")
    print()

    print("[2/8] 数据读取...")
    anchor_data, anchor_err = data_loader.load_anchor_status()
    ranking_data, ranking_err = data_loader.load_ranking()
    portfolio_data, portfolio_err = data_loader.load_portfolio()
    realtime_date, realtime_data, realtime_err = data_loader.find_latest_realtime()

    if anchor_err:
        print(f"  ❌ 锚价数据：{anchor_err}")
    else:
        print(f"  ✅ 锚价数据：{len(anchor_data)} 条")

    if ranking_err:
        print(f"  ❌ 排名数据：{ranking_err}")
    else:
        print(f"  ✅ 排名数据：run_date={ranking_data.get('run_date')}")

    if realtime_err:
        print(f"  ⚠️ 实时价格：{realtime_err}")
    else:
        print(f"  ✅ 实时价格：{realtime_date}")

    missing_data = []
    if anchor_err:
        missing_data.append(f"anchor_status.json: {anchor_err}")
    if ranking_err:
        missing_data.append(f"stock_ranking.json: {ranking_err}")
    print()

    print("[3/8] 交易日判断...")
    trading_status = trading_day.trading_day_status()
    freshness = trading_day.data_freshness()
    effective = trading_day.effective_trading_day(trading_status, freshness)
    print(f"  日期：{trading_status['date']} ({trading_status['weekday']})")
    print(f"  交易日状态：{effective['verdict']} - {effective['reason']}")
    data_asof = trading_day.data_asof_date(anchor_data, ranking_data, realtime_date)
    staleness_gate = trading_day.data_staleness_gate(data_asof, report_date)
    print(f"  行情所属日期：{data_asof or 'N/A'}（相对报告日落后 {staleness_gate.get('lag_trading_days', '?')} 个交易日）")
    print()

    print("[4/8] 大盘研判...")
    market = market_judge.judge_market(anchor_data or [], ranking_data, freshness)
    print(f"  判断：{market['verdict']}（置信度：{market['confidence']}）")
    print()

    print("[5/8] JEV 探查...")
    pool_codes = [s.code for s in P0_POOL + P2_POOL]
    jev_results = run_jev_probe(pool_codes, use_mock=args.mock_jev, force_mock_failure=args.mock_jev_fail)
    jev_ok = sum(1 for r in jev_results.values() if r.get("ok"))
    jev_total = len(jev_results)
    if args.mock_jev_fail:
        jev_status = "mock_unavailable"
    elif args.mock_jev:
        jev_status = "mock"
    elif jev_total and jev_ok == jev_total:
        jev_status = "available"
    elif jev_ok > 0:
        jev_status = "partial"
    else:
        jev_status = "unavailable"
    for code, r in jev_results.items():
        status = jev_adapter.failure_status(r)
        if r.get("ok"):
            print(f"  ✅ {code}: JEV 可用")
        else:
            print(f"  ❌ {code}: JEV 不可用 ({status})")
    if jev_status in ("unavailable", "partial"):
        error_codes = sorted({
            jev_adapter.failure_status(r)
            for r in jev_results.values() if not r.get("ok")
        })
        print(f"  JEV 汇总：{jev_status} {jev_ok}/{jev_total}（错误码：{error_codes}）")
    print()

    # [5.25/8] AMD Decision Model 探查（可选）
    decision_status = "skipped"
    search_status = "skipped"
    decision_results = {}
    if args.decision_model:
        print("[5.25/8] AMD Decision Model...")
        model_name = args.decision_model_name or "Clef"
        try:
            from decision.contract import DecisionInput
            from decision.adapter import decide as decision_decide

            # Build DecisionInput from collected data
            di = DecisionInput(
                report_date=report_date,
                market_context={
                    "verdict": market.get("verdict", "中性"),
                    "confidence": market.get("confidence", "low"),
                    "supporting_evidence": market.get("supports", []),
                    "conflicting_evidence": market.get("conflicts", []),
                    "limitations": market.get("limitations", []),
                },
                stocks=[],  # filled below
                data_provenance={
                    "anchor": "ok" if not anchor_err else "error",
                    "ranking": "ok" if not ranking_err else "error",
                    "jev": jev_status,
                    "search": search_status if "search_status" in dir() else "skipped",
                },
                freshness_gate=staleness_gate or {},
                constraints={"max_position_pct": 10},
            )

            # Fill stocks from pool_status
            pool_status_local = data_loader.get_pool_status(
                data_loader.build_anchor_index(anchor_data or []),
                data_loader.build_ranking_index(ranking_data or {}),
                data_loader.build_portfolio_index(portfolio_data or []),
            )
            for code in pool_codes:
                ps = pool_status_local.get(code, {})
                jev_r = jev_results.get(code, {})
                di.stocks.append({
                    "code": code,
                    "name": ps.get("name", code),
                    "price": ps.get("current"),
                    "anchor": ps.get("anchor"),
                    "deviation_pct": ps.get("deviation"),
                    "pe": ps.get("pe"),
                    "composite_score": ps.get("composite_score"),
                    "tech_score": ps.get("tech_score"),
                    "ml_boost": ps.get("ml_boost"),
                    "jev_answer": jev_r.get("answers", {}).get("answer", {}).get("noul"),
                    "jev_ok": jev_r.get("ok", False),
                })

            decision_output = decision_decide(di, model=model_name)
            decision_results["market"] = {
                "verdict": decision_output.market_verdict,
                "confidence": decision_output.market_confidence,
                "reasoning": decision_output.market_reasoning,
            }
            for s in decision_output.stocks:
                decision_results[s.code] = {
                    "action": s.action.value if hasattr(s.action, "value") else str(s.action),
                    "confidence": s.confidence,
                    "reasoning": s.reasoning,
                }
            decision_status = "available" if decision_output.stocks else "empty"
            print("  ✅ AMD Decision Model: %s (%d stocks, %s)" % (model_name, len(decision_output.stocks), decision_status))
            if decision_output.market_verdict:
                print("  大盘判断: %s (conf=%s)" % (decision_output.market_verdict, decision_output.market_confidence))
        except Exception as e:
            decision_status = "error: %s" % str(e)[:120]
            print("  ❌ AMD Decision Model 异常: %s" % str(e)[:120])
    else:
        print("[5.25/8] AMD Decision Model 未启用（使用 --decision-model 启用）")
    print()

    print("[5.5/8] 外部证据探查（Search API）...")
    search_status = "skipped"
    search_results = {}
    if args.search or args.mock_search:
        _SEARCH_DIR = os.path.join(_ROOT, "search")
        if _SEARCH_DIR not in sys.path:
            sys.path.insert(0, _SEARCH_DIR)
        try:
            from probe import probe_pool
            use_mock = bool(args.mock_search)
            pool_stocks = [{"code": s.code, "name": s.name} for s in P0_POOL + P2_POOL]
            search_results = probe_pool(pool_stocks, use_mock=use_mock, max_queries=3)
            search_status = "mock" if use_mock else search_results.get("status", "ok")
            for code, r in search_results.get("stocks", {}).items():
                n_claims = len(r.get("claims", []))
                print(f"  {'✅' if r['available'] else '❌'} {code}: {n_claims} claims ({r['status']})")
        except Exception as e:
            search_status = f"error: {e}"
            print(f"  ❌ Search 探查异常: {e}")
    else:
        print("  未启用（使用 --search / --mock-search 启用）")
    print()

    print("[6/8] 股票分析...")
    anchor_idx = data_loader.build_anchor_index(anchor_data or [])
    ranking_idx = data_loader.build_ranking_index(ranking_data or {})
    portfolio_idx = data_loader.build_portfolio_index(portfolio_data or [])
    pool_status = data_loader.get_pool_status(anchor_idx, ranking_idx, portfolio_idx)

    stock_analyses = []
    for code in pool_codes:
        analysis = stock_judge.judge_stock(code, pool_status, jev_results.get(code))
        # Apply staleness gate (P3.5)
        analysis = stock_judge.apply_staleness_to_analysis(
            analysis, ranking_data or {}, realtime_date, report_date=report_date
        )
        # Attach search evidence (P3.5)
        if search_results.get("stocks"):
            sr = search_results["stocks"].get(code)
            if sr:
                from search.evidence import sanitize_for_report
                analysis["search_layer"] = {
                    "status": sr["status"],
                    "available": sr["available"],
                    "queries_executed": sr["queries_executed"],
                    "claims": [sanitize_for_report(c) for c in sr.get("claims", [])][:6],
                    "summary": {k: v for k, v in sr.get("summary", {}).items() if k != "claims"},
                    "notes": sr.get("notes", []),
                }
        stock_analyses.append(analysis)
        act = analysis.get("action", {})
        print(f"  {analysis['name']}: {act.get('action', 'N/A')} ({act.get('reason', '')})")
    print()

    print("[7/8] 证据综合...")
    focus = _build_focus(stock_analyses)
    print(f"  重点关注：{focus.get('top_stocks', [])}")
    print()

    print("[8/8] 报告生成...")
    # Attach decision model results if available
    if decision_results:
        run_result_decision = {"market": decision_results.get("market"), "stocks": {k: v for k, v in decision_results.items() if k != "market"}}
        decision_status_str = "available"
    else:
        run_result_decision = None
        decision_status_str = "skipped"

    run_result = {
        "generated_at": generated_at,
        "report_date": report_date,
        "trading_day": effective,
        "freshness": freshness,
        "data_asof": data_asof,
        "staleness_gate": staleness_gate,
        "config_status": config_status,
        "jev_status": jev_status,
        "search_status": search_status,
        "decision_status": decision_status_str,
        "decision_results": run_result_decision,
        "missing_data": missing_data,
        "market": market,
        "stocks": stock_analyses,
        "focus": focus,
        "traces": _build_traces(anchor_data, ranking_data, pool_status, jev_status, jev_results),
    }

    content = report.generate_report(run_result)
    if args.output:
        output_path = args.output
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        conflicts = report.output_conflicts(output_path)
        if conflicts and not args.force:
            print(f"  ❌ 输出文件已存在，拒绝覆盖：{', '.join(conflicts)}")
            print("     使用新的 --output 路径，或在明确需要时使用 --force。")
            return 2
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
    else:
        output_path = report.save_report(content, report_date)
    print(f"  ✅ 报告已保存：{output_path}")
    print()

    if args.json:
        json_path = output_path.replace(".md", ".json")
        if json_path != output_path and os.path.exists(json_path) and not args.force:
            print(f"  ❌ JSON 输出文件已存在，拒绝覆盖：{json_path}")
            return 2
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(run_result, f, ensure_ascii=False, indent=2, default=str)
        print(f"  ✅ JSON 已保存：{json_path}")

    print("=" * 60)
    print("完成")
    return 0


def _build_focus(stock_analyses: list) -> dict:
    """构建重点跟踪事项。"""
    top_stocks = []
    risks = []
    events = []
    gaps = []

    for s in stock_analyses:
        act = s.get("action", {})
        if act.get("action") in ("CONSIDER_ENTRY", "CONSIDER_REDUCE"):
            top_stocks.append(f"{s['name']} ({s['code']}): {act.get('action')}")
        if act.get("action") == "OBSERVE":
            risks.append(f"{s['name']}: 锚价失效，需重新评估")
        syn = s.get("synthesis", {})
        for gap in syn.get("gaps", []):
            gaps.append(f"{s['name']}: {gap}")

    events.append("无已知即将发生的事件（当前无外部事件数据源）")

    return {
        "top_stocks": top_stocks or ["无"],
        "risks": risks or ["无"],
        "events": events,
        "gaps": gaps or ["无"],
    }


def _build_traces(anchor_data, ranking_data, pool_status,
                  jev_status: str = "unknown",
                  jev_results: dict | None = None) -> list:
    """构建审计追溯链。"""
    traces = []
    traces.append({
        "claim": f"锚价池共 {len(anchor_data or [])} 只股票",
        "source": "~/harness/anchor_status.json",
    })
    if ranking_data:
        traces.append({
            "claim": f"排名数据 run_date={ranking_data.get('run_date')}",
            "source": "~/harness/stock_daily/stock_ranking.json",
        })
    jev_results = jev_results or {}
    if jev_status == "available":
        traces.append({
            "claim": "JEV 已通过 MCP 桥接完成真实调用（AMD / Clef）",
            "source": f"jev_adapter.provider_config(); 调用日志 {jev_adapter.LOG_FILE}",
        })
    elif jev_status == "partial":
        traces.append({
            "claim": f"JEV 仅部分标的调用成功（{sum(1 for r in jev_results.values() if r.get('ok'))}/{len(jev_results)}）",
            "source": "src/engine/jev_adapter.py 调用日志",
        })
    elif jev_status == "mock":
        traces.append({
            "claim": "JEV 本次使用 Mock，不代表真实模型可用",
            "source": "daily_judge.py --mock-jev",
        })
    else:
        traces.append({
            "claim": "JEV 当前环境不可用",
            "source": "src/engine/jev_adapter.py 调用日志",
        })
    traces.append({
        "claim": "大盘判断仅基于本地股票池聚合统计，无外部指数数据",
        "source": "market_judge.py limitations",
    })
    return traces


if __name__ == "__main__":
    sys.exit(main())
