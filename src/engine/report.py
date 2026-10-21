#!/usr/bin/env python3
"""报告生成（P3-2 第 7 层）。

输出位置：reports/shadow/YYYY-MM-DD.md
格式：A 运行状态 / B 大盘研判 / C 股票分析 / D 重点跟踪事项 / E 审计与追溯
"""
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

TZ = timezone(timedelta(hours=8))
REPORTS_DIR = os.path.expanduser(os.environ.get("REPORTS_DIR", "reports/shadow"))


def _now_str() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def _date_str() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def generate_report(run_result: Dict[str, Any]) -> str:
    """生成每日研判报告。"""
    lines = []
    lines.append("# 每日研判报告（影子运行）")
    lines.append("")
    lines.append(f"> 生成时间：{_now_str()}（Asia/Shanghai）")
    lines.append(f"> 报告日期：{_date_str()}")
    lines.append("")

    lines.append("## A. 运行状态")
    lines.append("")
    lines.append(f"- 报告生成时间：{run_result.get('generated_at', _now_str())}")
    lines.append(f"- 运行时区：Asia/Shanghai (UTC+8)")
    data_asof = run_result.get("data_asof") or run_result.get("trading_day", {}).get("data_date")
    lines.append(f"- 行情所属交易日：{data_asof or 'N/A'}")
    lines.append(f"- 数据新鲜度：{run_result.get('freshness', {}).get('issues', []) or '正常'}")
    gate = run_result.get("staleness_gate") or {}
    if gate:
        lines.append(
            f"- 新鲜度门槛：{gate.get('verdict', 'N/A')}"
            + (f"｜{gate.get('reason')}" if gate.get("reason") else "")
        )
    lines.append(f"- 配置验证：{run_result.get('config_status', 'N/A')}")
    lines.append(f"- JEV 状态：{run_result.get('jev_status', 'N/A')}")
    jev_status = run_result.get("jev_status")
    if jev_status == "mock":
        lines.append("- **注意：JEV 使用 Mock 模式，影子运行结果不构成真实 JEV 调用。**")
    elif jev_status == "unavailable":
        lines.append("- **注意：JEV 真实调用失败，个股判断缺少 JEV 证据，不得据此生成交易类建议。**")
    if run_result.get("search_status") == "mock":
        lines.append("- **注意：Search API 使用 Mock 模式，外部证据不构成真实检索结果。**")
    lines.append(f"- 缺失数据：{run_result.get('missing_data', []) or '无'}")
    lines.append("")

    lines.append("## B. 大盘研判")
    lines.append("")
    market = run_result.get("market", {})
    lines.append(f"**判断：{market.get('verdict', '无法判断')}**（置信度：{market.get('confidence', 'N/A')}）")
    lines.append("")
    if market.get("evidence"):
        lines.append("**支持证据：**")
        for e in market["evidence"]:
            lines.append(f"- {e}")
        lines.append("")
    if market.get("counter_evidence"):
        lines.append("**反证：**")
        for c in market["counter_evidence"]:
            lines.append(f"- {c}")
        lines.append("")
    if market.get("scenarios"):
        lines.append("**情景分析：**")
        for name, sc in market["scenarios"].items():
            lines.append(f"- **{name}**：{sc.get('condition', '')}")
            lines.append(f"  - 成立条件：{sc.get('support', '')}")
            lines.append(f"  - 失效条件：{sc.get('invalidation', '')}")
        lines.append("")
    if market.get("limitations"):
        lines.append("**数据局限：**")
        for l in market["limitations"]:
            lines.append(f"- {l}")
        lines.append("")

    lines.append("## C. 股票分析")
    lines.append("")
    stocks = run_result.get("stocks", [])
    for s in stocks:
        lines.append(f"### {s.get('name', s.get('code'))}（{s.get('code')}）")
        lines.append("")
        lines.append(f"- 所属池：{s.get('pool', 'N/A')}")
        pl = s.get("price_layer", {})
        lines.append(f"- 行情日期：{pl.get('latest_date', 'N/A')}，数据质量：{pl.get('data_quality', 'N/A')}")
        lines.append(f"- 当前价：{pl.get('current', 'N/A')}，锚价：{pl.get('anchor', 'N/A')}")
        lines.append(f"- 偏离：{pl.get('deviation', 'N/A')}%，状态：{pl.get('status', 'N/A')}")
        lines.append(f"- 涨跌幅：{pl.get('change_pct', 'N/A')}%，PE：{pl.get('pe', 'N/A')}")
        lines.append(f"- 综合评分：{pl.get('composite_score', 'N/A')}")
        lines.append("")

        fl = s.get("fund_layer", {})
        lines.append("**资金面：**")
        if fl.get("signals"):
            for sig in fl["signals"]:
                lines.append(f"- {sig}")
        else:
            lines.append("- 无可用信号")
        lines.append(f"- 数据局限：{fl.get('note', '')}")
        lines.append("")

        rd = s.get("rd_layer", {})
        lines.append("**研发面：**")
        if rd.get("research_exists"):
            lines.append(f"- 研究笔记存在，最后更新：{rd.get('last_update', 'N/A')}")
        else:
            lines.append("- 无研究笔记")
        lines.append("")

        od = s.get("order_layer", {})
        lines.append("**订单面：**")
        lines.append(f"- {od.get('note', '')}")
        lines.append("")

        jl = s.get("jev_layer", {})
        lines.append("**JEV 探查：**")
        if jl.get("available"):
            lines.append(f"- JEV 可用｜model={jl.get('model', 'N/A')}｜transport={jl.get('transport', 'N/A')}")
            answers = jl.get("probe_answers") or {}
            if isinstance(answers, dict) and answers:
                for k, v in sorted(answers.items()):
                    if isinstance(v, dict):
                        answer = v.get("choice", v.get("noul", v.get("score", v)))
                        conf = v.get("confidence")
                        extra = f"｜confidence={conf}" if conf is not None else ""
                        lines.append(f"  - {k}: {answer}{extra}")
                    else:
                        lines.append(f"  - _: {v}")
            else:
                lines.append("  - 返回成功但无可展示答案")
        elif jl.get("called"):
            lines.append(f"- JEV 调用失败（{jl.get('status')}），不参与判断")
        else:
            lines.append("- JEV 未调用（当前环境不可用）")
        lines.append(f"- 注：{jl.get('note', '')}")
        lines.append("")

        sl = s.get("search_layer", {})
        lines.append("**外部证据（Search API）：**")
        if sl:
            lines.append(f"- 状态：{sl.get('status')}")
            if sl.get("available"):
                lines.append(f"- 可用：{sl.get('available')}，查询数：{sl.get('queries_executed')}")
                for c in sl.get("claims", [])[:3]:
                    lines.append(f"  - [{c['status']}] {c['claim'][:50]}... ({c['independent_sources']} 独立来源，tier={c['best_tier']})")
            else:
                lines.append(f"- 不可用（{sl.get('status')}）")
            for n in sl.get("notes", [])[:2]:
                lines.append(f"- 注：{n[:80]}")
        else:
            lines.append("- 未启用（使用 --search / --mock-search 启用）")
        lines.append("")

        syn = s.get("synthesis", {})
        lines.append("**证据综合：**")
        lines.append(f"- 关系：{syn.get('relation', 'N/A')}")
        if syn.get("supports"):
            for sup in syn["supports"]:
                lines.append(f"- 支持：{sup}")
        if syn.get("conflicts"):
            for con in syn["conflicts"]:
                lines.append(f"- 冲突：{con}")
        if syn.get("gaps"):
            for gap in syn["gaps"]:
                lines.append(f"- 缺口：{gap}")
        lines.append("")

        act = s.get("action", {})
        lines.append(f"**行动建议：{act.get('action', 'N/A')}**")
        lines.append(f"- 依据：{act.get('reason', 'N/A')}")
        if act.get("conditions"):
            lines.append("- 成立条件：")
            for c in act["conditions"]:
                lines.append(f"  - {c}")
        if act.get("invalidation"):
            lines.append("- 失效条件：")
            for c in act["invalidation"]:
                lines.append(f"  - {c}")
        lines.append("")

    lines.append("## D. 重点跟踪事项")
    lines.append("")
    focus = run_result.get("focus", {})
    if focus.get("top_stocks"):
        lines.append("**最值得继续研究的标的：**")
        for s in focus["top_stocks"]:
            lines.append(f"- {s}")
        lines.append("")
    if focus.get("risks"):
        lines.append("**需要重点监控的风险：**")
        for r in focus["risks"]:
            lines.append(f"- {r}")
        lines.append("")
    if focus.get("events"):
        lines.append("**接下来可能影响判断的事件：**")
        for e in focus["events"]:
            lines.append(f"- {e}")
        lines.append("")
    if focus.get("gaps"):
        lines.append("**仍缺乏足够证据的结论：**")
        for g in focus["gaps"]:
            lines.append(f"- {g}")
        lines.append("")

    lines.append("## E. 审计与追溯")
    lines.append("")
    lines.append("| 结论 | 来源 |")
    lines.append("|---|---|")
    for trace in run_result.get("traces", []):
        lines.append(f"| {trace.get('claim', '')} | {trace.get('source', '')} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"报告生成时间：{_now_str()}")
    lines.append(f"引擎版本：P3-2 daily_judge")
    lines.append(f"数据来源：~/harness/anchor_status.json, ~/harness/stock_daily/")
    lines.append("")

    return "\n".join(lines)


def save_report(content: str, date_str: Optional[str] = None) -> str:
    """保存报告到 reports/shadow/，默认拒绝覆盖已有 Markdown/JSON。"""
    date_str = date_str or _date_str()
    os.makedirs(REPORTS_DIR, exist_ok=True)
    base = Path(REPORTS_DIR) / date_str
    path = base.with_suffix(".md")
    json_path = base.with_suffix(".json")
    suffix = 2
    while path.exists() or json_path.exists():
        path = Path(f"{base}-{suffix}.md")
        json_path = Path(f"{base}-{suffix}.json")
        suffix += 1
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return str(path)

def output_conflicts(path: str) -> list:
    """返回显式输出路径可能覆盖的 Markdown/JSON 文件。"""
    p = Path(path)
    json_path = p.with_suffix(".json") if p.suffix else Path(str(p) + ".json")
    return [str(x) for x in (p, json_path) if x.exists()]
