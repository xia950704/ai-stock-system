#!/usr/bin/env python3
"""JEV 结论 -> 动作建议映射（监测用）。

动作映射（与 src/engine/stock_judge.py 的价格分档口径一致）：
  1. JEV 方向性结论（margin >= MIN_MARGIN）优先：
     reduce=yes -> CONSIDER_REDUCE / CONSIDER_EXIT
     entry=yes  -> CONSIDER_ENTRY
     add=yes    -> CONSIDER_ADD
  2. JEV 无方向性结论时，回落到锚价分档：
     dev < -5  -> CONSIDER_ENTRY（买入区间）
     dev < 0   -> WAIT
     dev > 10  -> CONSIDER_REDUCE
     dev > 5   -> HOLD
     其余      -> HOLD
     dev 为 None -> INSUFFICIENT_EVIDENCE
  3. 价格分档与 JEV 方向相反时，保留 JEV 方向但写明分歧。

失败降级：JEV 不可用时返回 INSUFFICIENT_EVIDENCE，不静默降级为中性。
"""
import os
import sys
from typing import Any, Dict, Optional

_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

ACTION_ENTRY = "CONSIDER_ENTRY"
ACTION_ADD = "CONSIDER_ADD"
ACTION_HOLD = "HOLD"
ACTION_WAIT = "WAIT"
ACTION_REDUCE = "CONSIDER_REDUCE"
ACTION_EXIT = "CONSIDER_EXIT"
ACTION_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"

HIGHLIGHT_ACTIONS = {ACTION_ENTRY, ACTION_REDUCE, ACTION_EXIT}

# AMD choice 模式：confidence 即 margin，需达到该阈值才算方向性结论
MIN_MARGIN = 0.20


def _directional(j: Dict[str, Any]) -> bool:
    """JEV 结论是否具备方向性（yes 且 margin 达标）。"""
    if not j.get("ok") or j.get("answer") != "yes":
        return False
    margin = j.get("margin")
    if margin is None:
        return False
    return float(margin) >= MIN_MARGIN


def _price_band_action(quote: Dict[str, Any]) -> Dict[str, Any]:
    """锚价分档兜底（与 src/engine/stock_judge.py 口径一致）。"""
    dev = quote.get("deviation")
    if dev is None:
        return {
            "action": ACTION_INSUFFICIENT,
            "reason": "无锚价（ETF 未维护锚价）",
            "basis": "no_anchor",
        }
    if dev < -5:
        return {
            "action": ACTION_ENTRY,
            "reason": "股价低于锚价 %.1f%%，处于买入区间" % abs(dev),
            "basis": "price_band",
        }
    if dev < 0:
        return {
            "action": ACTION_WAIT,
            "reason": "股价略低于锚价 %.1f%%，偏离有限，等待进一步回调" % abs(dev),
            "basis": "price_band",
        }
    if dev > 10:
        return {
            "action": ACTION_REDUCE,
            "reason": "股价高于锚价 %.1f%%，显著偏高" % dev,
            "basis": "price_band",
        }
    if dev > 5:
        return {
            "action": ACTION_HOLD,
            "reason": "股价高于锚价 %.1f%%，偏高但未到减仓区间" % dev,
            "basis": "price_band",
        }
    return {
        "action": ACTION_HOLD,
        "reason": "股价接近锚价（偏离 %.1f%%）" % dev,
        "basis": "price_band",
    }


def map_action(jev: Dict[str, Any], quote: Dict[str, Any]) -> Dict[str, Any]:
    """把 JEV 三问结果映射为动作建议。"""
    entry_j = jev.get("entry", {})
    if not entry_j.get("ok"):
        return {
            "action": ACTION_INSUFFICIENT,
            "reason": "JEV 不可用：%s" % entry_j.get("error_code", "unknown"),
            "basis": "jev_unavailable",
        }
    add_j = jev.get("add", {})
    reduce_j = jev.get("reduce", {})
    dev = quote.get("deviation")

    if _directional(reduce_j):
        action = ACTION_EXIT if (dev is not None and dev > 10) else ACTION_REDUCE
        reason = "JEV 判断应卖出/减仓（yes 概率 %.2f，margin %.2f）" % (
            reduce_j.get("yes_prob") or 0.0, reduce_j.get("margin") or 0.0)
        if dev is not None and dev < 0:
            reason += "；注意：当前价格仍低于锚价 %.1f%%，与减仓信号存在分歧" % abs(dev)
        return {"action": action, "reason": reason, "basis": "jev_reduce"}

    if _directional(entry_j):
        reason = "JEV 判断可建仓（yes 概率 %.2f，margin %.2f）" % (
            entry_j.get("yes_prob") or 0.0, entry_j.get("margin") or 0.0)
        if dev is not None and dev > 5:
            reason += "；注意：当前价格高于锚价 %.1f%%，与建仓信号存在分歧" % dev
        return {"action": ACTION_ENTRY, "reason": reason, "basis": "jev_entry"}

    if _directional(add_j):
        return {
            "action": ACTION_ADD,
            "reason": "JEV 判断可加仓（yes 概率 %.2f，margin %.2f）" % (
                add_j.get("yes_prob") or 0.0, add_j.get("margin") or 0.0),
            "basis": "jev_add",
        }

    # JEV 无方向性「yes」结论 → 回落锚价分档
    band = _price_band_action(quote)
    yes_margins = []
    no_margins = []
    for j in (entry_j, add_j, reduce_j):
        if not j.get("ok"):
            continue
        m = _margin_of(j)
        if m is None:
            continue
        if j.get("answer") == "yes":
            yes_margins.append(m)
        else:
            no_margins.append(m)

    if yes_margins:
        # 有 yes 但 margin 不足：方向弱，不足以单独触发动作
        band["reason"] += "；JEV 出现 yes 但 margin 仅 %.2f，低于阈值 %.2f，不作为触发依据" % (
            max(yes_margins), MIN_MARGIN)
    elif no_margins:
        # 三问全部为 no：高 margin 表示「明确不支持操作」
        band["reason"] += "；JEV 三问均为 no（最大 margin %.2f），未支持建仓/加仓/减仓" % (
            max(no_margins))
    else:
        band["reason"] += "；JEV 未给出可用结论"
    return band


def _margin_of(j: Dict[str, Any]) -> Optional[float]:
    """取 choice 结果的 margin（|yes-no|），缺失时由概率推导。"""
    m = j.get("margin")
    if m is not None:
        return float(m)
    yp, np_ = j.get("yes_prob"), j.get("no_prob")
    if yp is not None and np_ is not None:
        return abs(float(yp) - float(np_))
    return None
