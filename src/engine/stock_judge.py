#!/usr/bin/env python3
"""关注股票逐只分析（P3-2 第 4 层）。

分析顺序（沿用既有框架）：
  1. 行情与数据质量
  2. 资金面
  3. 研发面
  4. 订单面与商业化兑现
  5. JEV 探查
  6. 证据综合

重要声明：
  - 资金面：无可核实的主力资金/北向资金数据，仅使用价格与排名信号
  - 研发面：仅使用 Obsidian 镜像中的既有研究记录（只读）
  - 订单面：当前无订单/销量数据源
  - JEV：当前环境不可用（见 jev_adapter）
  - 不得编造任何数据、来源或精确概率
"""
import json
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from . import data_loader, jev_adapter, trading_day

TZ = timezone(timedelta(hours=8))
OBS_STOCK_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "obsidian", "01-股票投研", "股票")


def _read_research_note(code: str) -> Dict[str, Any]:
    """读取 Obsidian 镜像中的个股研究笔记（只读）。

    返回：
      - exists: 是否存在研究目录
      - meta: meta.json 内容（若有）
      - note_summary: 投资笔记关键字段摘要
      - last_update: 笔记中最近的更新日期（若有）
    """
    result = {"exists": False, "meta": None, "note_summary": {}, "last_update": None, "raw_note": None}
    stock_dir = os.path.join(OBS_STOCK_DIR, data_loader._norm_code(code).replace("sh", "").replace("sz", "").replace("hk", ""))
    if not os.path.isdir(stock_dir):
        for stock in data_loader.P0_POOL + data_loader.P2_POOL:
            if stock["code"] == code:
                stock_dir = os.path.join(OBS_STOCK_DIR, stock["name"])
                break
    if not os.path.isdir(stock_dir):
        return result

    result["exists"] = True
    meta_path = os.path.join(stock_dir, "meta.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                result["meta"] = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    note_path = None
    if os.path.isdir(stock_dir):
        for f in os.listdir(stock_dir):
            if "投资笔记" in f and f.endswith(".md"):
                note_path = os.path.join(stock_dir, f)
                break
    if note_path and os.path.exists(note_path):
        try:
            with open(note_path, encoding="utf-8") as f:
                content = f.read()
            result["raw_note"] = content[:8000]
            result["note_summary"] = _extract_note_summary(content)
            result["last_update"] = _extract_last_update(content)
        except OSError:
            pass

    return result


def _extract_note_summary(content: str) -> Dict[str, Any]:
    """从投资笔记中提取关键字段。"""
    summary = {}
    fm_match = re.search(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if fm_match:
        fm = fm_match.group(1)
        for key in ("current_price", "anchor_price", "deviation", "pe_ttm",
                    "status", "update_time", "hist_percentile", "hist_range"):
            m = re.search(rf'^{key}:\s*(.+)$', fm, re.MULTILINE)
            if m:
                val = m.group(1).strip().strip("'\"")
                summary[key] = val
    return summary


def _extract_last_update(content: str) -> Optional[str]:
    """提取笔记中最近的更新日期。"""
    dates = re.findall(r'### (\d{4}-\d{2}-\d{2})', content)
    if dates:
        return max(dates)
    m = re.search(r'^update_time:\s*(\d{4}-\d{2}-\d{2})', content, re.MULTILINE)
    if m:
        return m.group(1)
    return None


def judge_stock(code: str, pool_status: Dict[str, Any],
                jev_result: Optional[Dict[str, Any]] = None,
                research_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """对单只股票进行综合分析。"""
    status = pool_status.get(code, {})
    name = status.get("name", code)
    # P4: 历史回放注入 research_override（git history 还原），优先使用
    if research_override is not None:
        research = research_override
    else:
        research = _read_research_note(code)

    price_layer = {
        "current": status.get("current"),
        "anchor": status.get("anchor"),
        "deviation": status.get("deviation"),
        "status": status.get("status"),
        "pe": status.get("pe"),
        "prev_close": status.get("prev_close"),
        "change_pct": status.get("change_pct"),
        "composite_score": status.get("composite_score"),
        "latest_date": status.get("latest_date"),
        "data_quality": _assess_price_quality(status, research),
    }

    fund_layer = {
        "available_data": ["价格", "涨跌幅", "锚价偏离", "综合评分", "技术信号"],
        "unavailable_data": ["主力资金流向", "北向资金", "融资融券", "大单成交"],
        "signals": _extract_fund_signals(status),
        "note": "无可核实的主力资金数据，仅使用价格与排名信号；不得将单一价格信号等同于资金意图",
    }

    rd_layer = {
        "research_exists": research["exists"],
        "last_update": research.get("last_update"),
        "note_summary": research.get("note_summary", {}),
        "note": "研发信息仅来自 Obsidian 既有研究记录；若记录日期陈旧，标记为待核实",
    }

    order_layer = {
        "available_data": [],
        "unavailable_data": ["订单数据", "销量数据", "收入明细", "商业化兑现指标"],
        "note": "当前无订单/销量数据源，订单面无法分析",
    }

    jev_layer = {
        "called": jev_result is not None,
        "available": jev_adapter.is_available(jev_result) if jev_result else False,
        "status": jev_adapter.failure_status(jev_result) if jev_result else "not_called",
        "result": jev_result,
        "note": "JEV 输出仅作为单项探查证据，不得替代资金/研发/订单核验，也不得把调用失败解释为中性或任何方向信号",
    }
    if jev_layer["available"]:
        answers = (jev_result or {}).get("answers", {})
        jev_layer["answer_keys"] = sorted(answers.keys())
        jev_layer["probe_answers"] = answers
        jev_layer["model"] = (jev_result or {}).get("model")
        jev_layer["transport"] = (jev_result or {}).get("transport", "http")

    synthesis = _synthesize(price_layer, fund_layer, rd_layer, order_layer, jev_layer)
    action = _recommend_action(status, synthesis)

    return {
        "code": code,
        "name": name,
        "pool": status.get("pool"),
        "price_layer": price_layer,
        "fund_layer": fund_layer,
        "rd_layer": rd_layer,
        "order_layer": order_layer,
        "jev_layer": jev_layer,
        "synthesis": synthesis,
        "action": action,
    }


def _assess_price_quality(status: Dict[str, Any], research: Dict[str, Any]) -> str:
    """评估价格数据质量。"""
    issues = []
    if status.get("current") is None:
        issues.append("无当前价")
    if status.get("anchor") is None:
        issues.append("无锚价")
    if status.get("deviation") is None:
        issues.append("无偏离")
    if status.get("status") == "锚价失效":
        issues.append("锚价失效")
    if issues:
        return "数据不完整: " + "; ".join(issues)
    return "数据完整"


def _extract_fund_signals(status: Dict[str, Any]) -> List[str]:
    """从可用数据提取资金面信号。"""
    signals = []
    dev = status.get("deviation")
    if dev is not None:
        if dev < -5:
            signals.append(f"股价低于锚价 {abs(dev):.1f}%，可能反映悲观情绪或超跌")
        elif dev < 0:
            signals.append(f"股价略低于锚价 {abs(dev):.1f}%")
        elif dev > 10:
            signals.append(f"股价高于锚价 {dev:.1f}%，锚价可能失效")
        elif dev > 5:
            signals.append(f"股价高于锚价 {dev:.1f}%，偏高")
        else:
            signals.append(f"股价接近锚价（偏离 {dev:.1f}%）")
    ch = status.get("change_pct")
    if ch is not None:
        if ch > 5:
            signals.append(f"当日涨跌幅 +{ch:.1f}%，涨幅较大")
        elif ch < -5:
            signals.append(f"当日涨跌幅 {ch:.1f}%，跌幅较大")
    score = status.get("composite_score")
    if score is not None:
        if score >= 65:
            signals.append(f"综合评分 {score:.1f}，技术面偏强")
        elif score <= 35:
            signals.append(f"综合评分 {score:.1f}，技术面偏弱")
    return signals


def _synthesize(price_layer: Dict, fund_layer: Dict, rd_layer: Dict,
                order_layer: Dict, jev_layer: Dict) -> Dict[str, Any]:
    """证据综合：判断证据之间是支持、冲突还是不足。"""
    supports = []
    conflicts = []
    gaps = []

    dev = price_layer.get("deviation")
    status = price_layer.get("status")
    if dev is not None and status:
        if "买入区间" in str(status):
            supports.append("价格低于锚价，与买入区间状态一致")
        elif "超买入区间" in str(status) or "锚价失效" in str(status):
            conflicts.append("价格远高于锚价，锚价状态可能已失效")

    score = price_layer.get("composite_score")
    if score is not None and dev is not None:
        if score >= 65 and dev < 0:
            supports.append("技术面偏强但价格低于锚价，信号一致看多")
        elif score <= 35 and dev > 5:
            conflicts.append("技术面偏弱但价格高于锚价，信号冲突")

    if jev_layer.get("available"):
        supports.append("JEV 探查可用")
    elif jev_layer.get("called"):
        gaps.append(f"JEV 调用失败（{jev_layer.get('status')}），不参与证据综合")
    else:
        gaps.append("JEV 未调用")

    if order_layer.get("unavailable_data"):
        gaps.append("订单面数据缺失")

    if not rd_layer.get("research_exists"):
        gaps.append("无研究笔记")
    elif rd_layer.get("last_update"):
        gaps.append(f"研究笔记最后更新：{rd_layer['last_update']}")

    if conflicts:
        relation = "存在冲突"
    elif supports and not gaps:
        relation = "相互支持"
    elif supports:
        relation = "部分支持，存在数据缺口"
    else:
        relation = "证据不足"

    return {
        "relation": relation,
        "supports": supports,
        "conflicts": conflicts,
        "gaps": gaps,
    }


def _recommend_action(status: Dict[str, Any], synthesis: Dict[str, Any]) -> Dict[str, Any]:
    """给出行动建议。"""
    dev = status.get("deviation")
    score = status.get("composite_score")
    status_str = str(status.get("status", ""))

    if dev is None and score is None:
        return {
            "action": "INSUFFICIENT_EVIDENCE",
            "reason": "无可用价格或评分数据",
            "conditions": [],
            "invalidation": [],
        }

    if "锚价失效" in status_str:
        return {
            "action": "OBSERVE",
            "reason": "锚价失效，需重新评估锚价有效性",
            "conditions": ["锚价重新确认后可重新评估"],
            "invalidation": ["锚价确认有效"],
        }

    if dev is not None and dev < -5:
        action = "CONSIDER_ENTRY"
        reason = f"股价低于锚价 {abs(dev):.1f}%，处于买入区间"
        conditions = ["锚价有效", "无重大负面事件", "估值合理"]
        invalidation = ["股价回升至锚价以上", "锚价失效", "出现重大利空"]
    elif dev is not None and dev < 0:
        action = "WAIT"
        reason = f"股价略低于锚价 {abs(dev):.1f}%，偏离有限"
        conditions = ["股价进一步回调至买入区间"]
        invalidation = ["股价回升超过锚价"]
    elif dev is not None and dev > 10:
        action = "CONSIDER_REDUCE"
        reason = f"股价高于锚价 {dev:.1f}%，显著偏高"
        conditions = ["估值过高", "技术面超买"]
        invalidation = ["股价回调至合理区间"]
    elif dev is not None and dev > 5:
        action = "HOLD"
        reason = f"股价高于锚价 {dev:.1f}%，偏高但未到减仓区间"
        conditions = []
        invalidation = ["股价继续大幅上涨"]
    else:
        action = "HOLD"
        reason = f"股价接近锚价（偏离 {dev:.1f}%）"
        conditions = []
        invalidation = []

    return {
        "action": action,
        "reason": reason,
        "conditions": conditions,
        "invalidation": invalidation,
    }

# ---- 数据新鲜度门槛（P3.5 第 3.4 节） ----
from .trading_day import data_asof_date, data_staleness_gate, apply_staleness_gate, BLOCKING_ACTIONS

def apply_staleness_to_analysis(analysis: Dict[str, Any],
                                 ranking_data: Dict, realtime_date: Optional[str],
                                 report_date: Optional[str] = None) -> Dict[str, Any]:
    """对股票分析结果应用数据新鲜度门槛。

    若数据过期/日期不明，将交易类行动建议降级为 OBSERVE。
    P4: 支持历史回放传入 report_date（默认当前日期）。
    """
    if report_date is None:
        report_date = datetime.now(TZ).strftime("%Y-%m-%d")
    asof = data_asof_date(analysis.get("price_layer", {}).get("current") and [],
                          ranking_data, realtime_date)
    # 简化：用排名 run_date 作为 asof（实际应由引擎传入）
    asof = ranking_data.get("run_date") if ranking_data else None
    gate = data_staleness_gate(asof, report_date, max_lag_trading_days=2)
    action = analysis.get("action", {})
    gated_action = apply_staleness_gate(action, gate)
    if gated_action != action:
        analysis["action"] = gated_action
        analysis["staleness_gate"] = gate
    return analysis
