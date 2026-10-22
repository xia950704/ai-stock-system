#!/usr/bin/env python3
"""监测报告渲染：输出 reports/monitor/YYYY-MM-DD.md。

约定：
  - CONSIDER_ENTRY / CONSIDER_REDUCE / CONSIDER_EXIT 用加粗标注
  - 明确区分「已验证事实」与「推断」
  - 不含任何交易执行建议，只给动作建议
"""
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

TZ = timezone(timedelta(hours=8))
REPORTS_DIR = os.path.expanduser(
    os.environ.get("MONITOR_REPORTS_DIR", "reports/monitor")
)

ACTION_LABELS = {
    "CONSIDER_ENTRY": "建仓",
    "CONSIDER_ADD": "加仓",
    "HOLD": "持有观望",
    "WAIT": "等待",
    "OBSERVE": "观察",
    "CONSIDER_REDUCE": "减仓",
    "CONSIDER_EXIT": "退出",
    "INSUFFICIENT_EVIDENCE": "证据不足",
}


def _fmt_num(v: Any) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, (int, float)):
        return "%.2f" % v
    return str(v)


def _fmt_conf(j: Dict[str, Any]) -> str:
    c = j.get("confidence")
    if c is None:
        return "N/A"
    try:
        return "%.2f" % float(c)
    except (TypeError, ValueError):
        return "N/A"


def _action_line(action: str) -> str:
    label = ACTION_LABELS.get(action, action)
    if action in ("CONSIDER_ENTRY", "CONSIDER_REDUCE", "CONSIDER_EXIT"):
        return "**%s（%s）**" % (action, label)
    return "%s（%s）" % (action, label)


def _render_market(lines: List[str], market: Dict[str, Any]) -> None:
    lines.append("## A. 大盘环境")
    lines.append("")
    lines.append("**已验证事实：**")
    lines.append("")
    for idx in market.get("indices", []):
        lines.append("- %s（%s）：%.2f，涨跌 %+.2f%%" % (
            idx.get("name"), idx.get("code"),
            idx.get("price") or 0, idx.get("change_pct") or 0))
    if not market.get("indices"):
        lines.append("- 指数行情不可用：%s" % (market.get("index_error") or "未知原因"))
    lines.append("- 关注池：%d 只上涨 / %d 只下跌" % (
        market.get("pool_up", 0), market.get("pool_down", 0)))
    lines.append("")
    lines.append("**推断：**")
    lines.append("")
    lines.append("- 大盘方向：%s" % market.get("index_bias", "未知"))
    lines.append("- 本地池锚价聚合判断：%s（置信度 %s）" % (
        market.get("local_verdict", "无法判断"), market.get("confidence", "low")))
    local_lims = market.get("local_limitations", [])
    if local_lims:
        lines.append("  - 数据局限（仅约束本地池锚价聚合判断，不约束大盘方向）：")
        for lim in local_lims:
            lines.append("    - %s" % lim)
    monitor_lims = market.get("monitor_limitations", [])
    if monitor_lims:
        lines.append("  - 数据局限（监测层）：")
        for lim in monitor_lims:
            lines.append("    - %s" % lim)
    lines.append("")


def _render_summary(lines: List[str], rows: List[Dict[str, Any]]) -> None:
    lines.append("## B. 汇总表")
    lines.append("")
    lines.append("| 标的 | 现价 | 涨跌 | 锚价 | 偏离 | JEV(建仓) | 动作 |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in rows:
        jev = r.get("jev", {}).get("entry", {})
        if jev.get("ok"):
            jev_txt = "%s / %s" % (jev.get("answer", "?"), _fmt_conf(jev))
        else:
            jev_txt = "不可用(%s)" % jev.get("error_code", "?")
        q = r.get("quote", {})
        dev = q.get("deviation")
        dev_txt = ("%+.2f%%" % dev) if dev is not None else "N/A"
        chg = q.get("change_pct")
        chg_txt = ("%+.2f%%" % chg) if chg is not None else "N/A"
        lines.append("| %s（%s） | %s | %s | %s | %s | %s | %s |" % (
            r.get("name"), r.get("code"), _fmt_num(q.get("price")), chg_txt,
            _fmt_num(q.get("anchor")), dev_txt, jev_txt,
            _action_line(r.get("action", "")),
        ))
    lines.append("")


def _render_jev_lines(lines: List[str], jev: Dict[str, Any]) -> None:
    for kind, label in (("entry", "是否建仓"),
                        ("add", "是否加仓"),
                        ("reduce", "是否卖出/减仓")):
        j = jev.get(kind, {})
        if j.get("ok"):
            probs = j.get("probabilities") or {}
            yes_p = probs.get("yes")
            no_p = probs.get("no")
            margin = j.get("margin")
            prob_txt = ""
            if yes_p is not None and no_p is not None:
                prob_txt = "（yes %.2f / no %.2f，margin %.2f）" % (
                    yes_p, no_p, margin if margin is not None else 0.0)
            directional = _directional_label(j)
            lines.append("- %s：**%s**｜%s%s" % (
                label, j.get("answer", "?"), directional, prob_txt))
        else:
            lines.append("- %s：不可用（%s）" % (
                label, j.get("error_code", "unknown")))


def _directional_label(j: Dict[str, Any]) -> str:
    """标注该结论的方向性强弱。"""
    from monitor.action_map import MIN_MARGIN

    margin = j.get("margin")
    strong = margin is not None and float(margin) >= MIN_MARGIN
    if j.get("answer") == "yes":
        return "方向性（可触发动作）" if strong else "方向弱（margin 不足，不触发）"
    return "明确否定" if strong else "倾向否定（margin 不足）"


def _is_directional(j: Dict[str, Any]) -> bool:
    """JEV 结论是否有方向性（yes 且 margin 达标）。"""
    from monitor.action_map import MIN_MARGIN

    if not j.get("ok") or j.get("answer") != "yes":
        return False
    m = j.get("margin")
    return m is not None and float(m) >= MIN_MARGIN


def _render_stock(lines: List[str], r: Dict[str, Any]) -> None:
    q = r.get("quote", {})
    news = r.get("news", {})
    lines.append("### %s（%s）" % (r.get("name"), r.get("code")))
    lines.append("")
    chg = q.get("change_pct")
    chg_txt = ("涨跌 %+.2f%%" % chg) if chg is not None else "涨跌 N/A"
    lines.append("- 当前价格：%s 元（%s）" % (_fmt_num(q.get("price")), chg_txt))
    dev = q.get("deviation")
    dev_txt = ("%+.2f%%" % dev) if dev is not None else "N/A（无锚价）"
    lines.append("- 锚价：%s；偏离：%s；状态：%s；PE：%s" % (
        _fmt_num(q.get("anchor")), dev_txt,
        q.get("status", "N/A"), _fmt_num(q.get("pe"))))
    lines.append("")
    lines.append("**新闻摘要（Search API 检索结果，尚未逐条人工核实）：**")
    lines.append("")
    if news.get("items"):
        for it in news["items"]:
            date = it.get("published_at") or "日期未知"
            lines.append("- [%s] %s" % (date, it.get("title", "")))
            if it.get("snippet"):
                lines.append("  - %s" % it["snippet"][:180])
    else:
        lines.append("- 未抓到可用新闻（%s）" % (news.get("status") or "unknown"))
    lines.append("")
    lines.append("**JEV 决策（AMD Clef 决策模型，mode=choice）：**")
    lines.append("")
    lines.append("> 说明：choice 模式的 `confidence` 实测为两侧概率之差（margin），"
                 "非概率本身。margin ≥ 0.20 才视为方向性结论，"
                 "否则回落到锚价分档（与 src/engine/stock_judge.py 同口径）。")
    lines.append("")
    _render_jev_lines(lines, r.get("jev", {}))
    lines.append("")
    lines.append("**动作建议：** %s" % _action_line(r.get("action", "")))
    lines.append("")
    lines.append("- 理由：%s" % r.get("action_reason", "N/A"))
    lines.append("- 依据：%s" % r.get("action_basis", "N/A"))
    lines.append("")


def _render_focus(lines: List[str], rows: List[Dict[str, Any]]) -> None:
    lines.append("## D. 需重点关注")
    lines.append("")
    highlighted = [r for r in rows if r.get("highlight")]
    if highlighted:
        for r in highlighted:
            lines.append("- %s（%s）：%s — %s" % (
                r.get("name"), r.get("code"),
                _action_line(r.get("action", "")), r.get("action_reason", "")))
    else:
        lines.append("- 本次无 CONSIDER_ENTRY / CONSIDER_REDUCE / CONSIDER_EXIT 标的")
    lines.append("")


def _render_footer(lines: List[str]) -> None:
    lines.append("## E. 口径与免责")
    lines.append("")
    lines.append("- 本报告不执行任何交易，只输出判断。")
    lines.append("- 事实层：价格/涨跌/锚价偏离来自腾讯行情公开接口与 ~/harness/anchor_status.json；新闻标题来自 Search API 检索结果，尚未逐条人工核实。")
    lines.append("- 推断层：JEV 置信度、动作建议、大盘方向均为模型输出，不是事实。")
    lines.append("- JEV 不可用时标记为 INSUFFICIENT_EVIDENCE，不解释为中性。")
    lines.append("- 锚价由用户维护，脚本只更新 current/prev_close，不改锚价本身。")
    lines.append("")
    lines.append("---")
    lines.append("")


def render(result: Dict[str, Any]) -> str:
    """渲染完整监测报告。"""
    market = result.get("market", {})
    rows: List[Dict[str, Any]] = result.get("stocks", [])
    lines: List[str] = []

    lines.append("# A股医药持仓池 + ETF 每日监测")
    lines.append("")
    lines.append("> 生成时间：%s（Asia/Shanghai）" % result.get("generated_at", ""))
    lines.append("> 报告日期：%s" % result.get("report_date", ""))
    lines.append("> 行情时间戳：%s" % (result.get("quote_timestamp") or "N/A"))
    lines.append("")
    _render_market(lines, market)
    _render_summary(lines, rows)
    lines.append("## C. 逐股明细")
    lines.append("")
    for r in rows:
        _render_stock(lines, r)
    _render_focus(lines, rows)
    _render_footer(lines)
    return "\n".join(lines)


def save(content: str, report_date: str, reports_dir: str = REPORTS_DIR) -> str:
    """写入 reports/monitor/YYYY-MM-DD.md。"""
    os.makedirs(reports_dir, exist_ok=True)
    path = os.path.join(reports_dir, "%s.md" % report_date)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path
