#!/usr/bin/env python3
"""大盘环境分析（P3-2 第 3 层）。

重要声明：
  - 当前环境**没有**可用的指数行情、成交额、市场广度等外部数据源。
  - 大盘判断仅基于可核实的本地数据（锚价池 56 只、排名池 26 只）的聚合统计。
  - 不得将此聚合统计等同于真实大盘指数表现。
  - 数据不足以支撑可靠大盘判断时，输出「无法判断」。
"""
from typing import Any, Dict, List, Optional, Tuple

from . import data_loader


def aggregate_anchor_stats(anchor_list: List[Dict]) -> Dict[str, Any]:
    """从锚价池计算聚合统计。"""
    if not anchor_list:
        return {"count": 0}

    deviations = []
    statuses = {}
    changes = []
    pes = []
    for item in anchor_list:
        dev = item.get("deviation")
        if dev is not None:
            deviations.append(dev)
        status = item.get("status")
        if status:
            statuses[status] = statuses.get(status, 0) + 1
        ch = item.get("change_pct")
        if ch is not None:
            changes.append(ch)
        pe = item.get("pe")
        if pe is not None:
            pes.append(pe)

    n = len(anchor_list)
    result = {
        "count": n,
        "status_distribution": statuses,
    }
    if deviations:
        result["avg_deviation"] = round(sum(deviations) / len(deviations), 2)
        result["min_deviation"] = round(min(deviations), 2)
        result["max_deviation"] = round(max(deviations), 2)
        result["pos_deviation_count"] = sum(1 for d in deviations if d > 0)
        result["neg_deviation_count"] = sum(1 for d in deviations if d < 0)
    if changes:
        result["avg_change_pct"] = round(sum(changes) / len(changes), 2)
    if pes:
        result["avg_pe"] = round(sum(pes) / len(pes), 1)
    return result


def aggregate_ranking_stats(ranking_data: Optional[Dict]) -> Dict[str, Any]:
    """从排名数据计算聚合统计。"""
    if not ranking_data:
        return {"count": 0}
    rankings = ranking_data.get("rankings", [])
    if not rankings:
        return {"count": 0}
    scores = [r.get("composite_score") for r in rankings if r.get("composite_score") is not None]
    result = {
        "count": len(rankings),
        "run_date": ranking_data.get("run_date"),
        "buy_signals": ranking_data.get("buy_signals"),
        "watch_signals": ranking_data.get("watch_signals"),
        "sell_signals": ranking_data.get("sell_signals"),
    }
    if scores:
        result["avg_composite"] = round(sum(scores) / len(scores), 1)
        result["max_composite"] = round(max(scores), 1)
        result["min_composite"] = round(min(scores), 1)
    return result


def judge_market(anchor_list: List[Dict], ranking_data: Optional[Dict],
                 freshness: Dict[str, Any]) -> Dict[str, Any]:
    """综合判断大盘环境。

    返回：
      - verdict: 偏多 / 偏空 / 中性 / 无法判断
      - evidence: 支持判断的事实
      - counter_evidence: 反证
      - scenarios: 偏多/基准/偏空情景及成立条件
      - confidence: 置信度
      - limitations: 数据局限
    """
    a_stats = aggregate_anchor_stats(anchor_list)
    r_stats = aggregate_ranking_stats(ranking_data)

    evidence = []
    counter = []
    limitations = [
        "无外部指数行情数据（无上证/沪深300等实际指数表现）",
        "无成交额、市场广度（涨跌家数）等外部数据",
        "大盘判断仅基于本地股票池聚合统计，不能等同于真实大盘",
        "法定节假日无法确认，交易日判断为保守估计",
    ]

    # 锚价偏离分析
    if a_stats.get("avg_deviation") is not None:
        avg_dev = a_stats["avg_deviation"]
        pos = a_stats.get("pos_deviation_count", 0)
        neg = a_stats.get("neg_deviation_count", 0)
        evidence.append(f"锚价池 {a_stats['count']} 只股票平均偏离 {avg_dev:+.2f}%")
        evidence.append(f"正偏离 {pos} 只，负偏离 {neg} 只")
        if avg_dev > 5:
            evidence.append("池内股票整体高于锚价，反映风险偏好偏高")
        elif avg_dev < -2:
            evidence.append("池内股票整体低于锚价，反映悲观情绪")
        else:
            evidence.append("池内股票整体接近锚价，偏离有限")

    # 排名信号分析
    if r_stats.get("count", 0) > 0:
        buy = r_stats.get("buy_signals", 0)
        watch = r_stats.get("watch_signals", 0)
        sell = r_stats.get("sell_signals", 0)
        evidence.append(f"排名池 {r_stats['count']} 只：买入信号 {buy}，观望 {watch}，卖出信号 {sell}")
        if r_stats.get("avg_composite") is not None:
            evidence.append(f"排名池平均综合评分 {r_stats['avg_composite']:.1f}/100")
        if buy > sell:
            evidence.append("买入信号多于卖出信号")
        elif sell > buy:
            counter.append("卖出信号多于买入信号")

    # 数据新鲜度
    if freshness.get("issues"):
        counter.append(f"数据新鲜度问题：{'；'.join(freshness['issues'])}")

    # 判断
    if a_stats.get("avg_deviation") is None and r_stats.get("count", 0) == 0:
        verdict = "无法判断"
        confidence = "high"
    else:
        avg_dev = a_stats.get("avg_deviation") or 0
        if avg_dev > 5 and (r_stats.get("buy_signals", 0) or 0) > (r_stats.get("sell_signals", 0) or 0):
            verdict = "偏多"
            confidence = "low"
        elif avg_dev < -2:
            verdict = "偏空"
            confidence = "low"
        else:
            verdict = "中性"
            confidence = "low"

    scenarios = {
        "偏多": {
            "condition": "池内平均偏离持续扩大且买入信号占优",
            "support": "正偏离股票数量多于负偏离，买入信号占优",
            "invalidation": "平均偏离回落至 0 附近或卖出信号反超",
        },
        "基准": {
            "condition": "池内股票围绕锚价波动，多空力量均衡",
            "support": "平均偏离在 -2% ~ +5% 区间，买卖信号接近",
            "invalidation": "偏离突破 ±5% 或排名信号出现单边倾斜",
        },
        "偏空": {
            "condition": "池内股票普遍低于锚价，卖出信号占优",
            "support": "平均偏离为负且持续扩大",
            "invalidation": "平均偏离转正且买入信号回暖",
        },
    }

    return {
        "verdict": verdict,
        "confidence": confidence,
        "evidence": evidence,
        "counter_evidence": counter,
        "scenarios": scenarios,
        "limitations": limitations,
        "aggregate_stats": {"anchor": a_stats, "ranking": r_stats},
    }
