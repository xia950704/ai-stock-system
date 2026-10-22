#!/usr/bin/env python3
"""监测决策编排：state 构造 -> JEV 三问 -> 动作映射。

对外只暴露 judge_stock()，其余实现在 jev_questions.py 与 action_map.py。
"""
import os
import sys
from typing import Any, Dict

_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from monitor.action_map import (  # noqa: F401  (re-export)
    ACTION_ADD, ACTION_ENTRY, ACTION_EXIT, ACTION_HOLD, ACTION_INSUFFICIENT,
    ACTION_REDUCE, ACTION_WAIT, HIGHLIGHT_ACTIONS, MIN_MARGIN, map_action,
)
from monitor.jev_questions import build_state, run_jev


def judge_stock(quote: Dict[str, Any], news: Dict[str, Any],
                market: Dict[str, Any], use_mock: bool = False) -> Dict[str, Any]:
    """对单只股票做完整决策（state + 三问 + 动作映射）。"""
    state = build_state(quote, news, market)
    jev = {
        "entry": run_jev(state, "entry", quote, news, market, use_mock),
        "add": run_jev(state, "add", quote, news, market, use_mock),
        "reduce": run_jev(state, "reduce", quote, news, market, use_mock),
    }
    action = map_action(jev, quote)
    return {
        "code": quote.get("code"),
        "name": quote.get("name"),
        "quote": quote,
        "news": news,
        "state": state,
        "jev": jev,
        "action": action["action"],
        "action_reason": action["reason"],
        "action_basis": action["basis"],
        "highlight": action["action"] in HIGHLIGHT_ACTIONS,
    }
