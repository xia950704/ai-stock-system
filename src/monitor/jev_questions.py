#!/usr/bin/env python3
"""JEV 问题构造与调用层（监测用）。

每个股票做三个二值判断（jev_adapter.jev_yes_no, mode=choice）：
  1. entry   -> 是否建仓/买入
  2. add     -> 是否加仓
  3. reduce  -> 是否卖出/减仓

AMD choice 模式的标定（实测确认）：
  - `probabilities.yes/no` 是两侧概率，之和为 1
  - `confidence` **不是**概率，而是两侧概率的差值（margin）
    例：yes=0.535 / no=0.465 -> confidence=0.070（实质是抛硬币）
  - 因此「yes」只有在 margin 足够大时才算方向性结论
"""
import os
import sys
import time
from typing import Any, Dict, Optional

_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from engine import jev_adapter

# ---- JEV 调用重试与限速配置（与 src/decision/adapter.py 同口径）----
JEV_MAX_RETRIES = int(os.environ.get("JEV_MAX_RETRIES", "5"))
JEV_BACKOFF_BASE_S = float(os.environ.get("JEV_BACKOFF_BASE_S", "4.0"))
JEV_INTER_CALL_DELAY_S = float(os.environ.get("JEV_INTER_CALL_DELAY_S", "3.0"))

_JEV_RETRYABLE_ERROR_CODES = {"timeout", "transport", "bridge_error",
                              "rate_limit", "server_error"}


def _classify_result_error(result: Dict[str, Any]) -> str:
    """把 jev_adapter 原始返回归一化为 error_code。

    MCP bridge 透传的 429 响应只有 http_status 字段、没有 error_code，
    不在此处归一化会被 _parse_choice 误判为 unknown。
    """
    if result.get("ok"):
        return "ok"
    ec = result.get("error_code")
    if ec:
        return ec
    hs = result.get("http_status")
    if hs == 429:
        return "rate_limit"
    if hs is not None:
        if 500 <= hs < 600:
            return "server_error"
        if hs == 401:
            return "auth"
        if hs == 402:
            return "insufficient"
        if hs == 403:
            return "forbidden"
        if hs == 404:
            return "not_found"
    return "unknown"


def _is_retryable(result: Dict[str, Any]) -> bool:
    """判断 JEV 调用失败是否可重试（429 / transport / bridge 瞬时错误）。"""
    if result.get("ok"):
        return False
    if result.get("http_status") == 429:
        return True
    if result.get("error_code") in _JEV_RETRYABLE_ERROR_CODES:
        return True
    detail = (result.get("error_message") or result.get("detail") or "")
    d = detail.lower()
    if "rate limit" in d or "429" in d:
        return True
    return False


def build_state(quote: Dict[str, Any], news: Dict[str, Any],
                market: Dict[str, Any]) -> Dict[str, Any]:
    """构造送入 JEV 的标准化 state（不含持仓与成本价）。"""
    news_titles = [it.get("title", "") for it in news.get("items", []) if it.get("title")]
    return {
        "code": quote.get("code"),
        "name": quote.get("name"),
        "price": quote.get("price"),
        "prev_close": quote.get("prev_close"),
        "change_pct": quote.get("change_pct"),
        "anchor_price": quote.get("anchor"),
        "anchor_deviation_pct": quote.get("deviation"),
        "anchor_status": quote.get("status"),
        "pe": quote.get("pe"),
        "news_titles": news_titles,
        "market_verdict": market.get("verdict"),
        "market_context": market.get("summary"),
        "data_asof": quote.get("timestamp"),
    }



def _question_text(kind: str, quote: Dict[str, Any], news: Dict[str, Any],
                   market: Dict[str, Any]) -> str:
    """生成判断问题（choice 模式 instructions）。"""
    name = quote.get("name", "")
    price = quote.get("price")
    anchor = quote.get("anchor")
    dev = quote.get("deviation")
    chg = quote.get("change_pct")
    status = quote.get("status")
    news_titles = [it.get("title", "") for it in news.get("items", []) if it.get("title")]
    news_text = "；".join(news_titles[:3]) if news_titles else "（未抓到最新新闻）"
    mkt = market.get("summary", "无外部指数数据")

    facts = (
        "%s（%s）当前价 %s 元，锚价 %s 元，偏离锚价 %s%%（%s），今日涨跌 %s%%。"
        "最新公开消息：%s。大盘环境：%s。"
    ) % (
        name, quote.get("code"), price,
        anchor if anchor is not None else "无",
        dev if dev is not None else "N/A",
        status, chg if chg is not None else "N/A",
        news_text, mkt,
    )

    if kind == "entry":
        return facts + "基于以上事实，此时是否值得建仓买入该标的？"
    if kind == "add":
        return facts + "基于以上事实，此时是否值得对已有仓位加仓？"
    return facts + "基于以上事实，此时是否应当卖出或减仓该标的？"


def _no_text(kind: str, quote: Dict[str, Any]) -> str:
    """choice 模式的 no 侧说明。"""
    name = quote.get("name", "")
    if kind == "entry":
        return "%s 当前的锚价偏离、消息面与大盘环境不支持此时建仓。" % name
    if kind == "add":
        return "%s 当前的锚价偏离、消息面与大盘环境不支持此时加仓。" % name
    return "%s 当前的锚价偏离、消息面与大盘环境不支持此时卖出或减仓。" % name


def _parse_choice(result: Dict[str, Any]) -> Dict[str, Any]:
    """解析 jev_yes_no 返回的 choice 结果。"""
    if not result.get("ok"):
        return {
            "ok": False,
            "error_code": _classify_result_error(result),
            "error_message": (
                result.get("error_message") or result.get("detail") or ""
            )[:150],
        }
    answers = result.get("answers") or {}
    ans = answers.get("answer") or {}
    choice = ans.get("choice")
    if choice is None:
        noul = ans.get("noul")
        if noul is None:
            return {"ok": False, "error_code": "parse_error",
                    "error_message": "answers.answer 无 choice/noul 字段"}
        choice = "yes" if noul >= 0.5 else "no"
    probs = ans.get("probabilities") or {}
    yes_p = probs.get("yes")
    no_p = probs.get("no")
    margin = ans.get("confidence")
    if margin is None and yes_p is not None and no_p is not None:
        margin = abs(yes_p - no_p)
    return {
        "ok": True,
        "answer": choice,
        "confidence": ans.get("confidence"),
        "margin": margin,
        "probabilities": probs,
        "yes_prob": yes_p,
        "no_prob": no_p,
    }


def run_jev(state: Dict[str, Any], kind: str, quote: Dict[str, Any],
             news: Dict[str, Any], market: Dict[str, Any],
             use_mock: bool = False) -> Dict[str, Any]:
    """执行一次 JEV 二值判断。

    内置重试/退避：对 429 / transport / bridge_error 等瞬时错误按
    4s / 8s / 12s / 16s / 20s 退避重试（与 src/decision/adapter.py 同口径）。
    真实调用之间额外加 JEV_INTER_CALL_DELAY_S 间隔，避免触发 AMD
    global_concurrency_rate_limit。
    """
    q = _question_text(kind, quote, news, market)
    nt = _no_text(kind, quote)
    mock_response = None
    if use_mock:
        mock_response = {
            "ok": True,
            "model": "mock",
            "answers": {
                "answer": {
                    "type": "choice",
                    "choice": "no",
                    "confidence": 0.5,
                    "probabilities": {"yes": 0.5, "no": 0.5},
                }
            },
        }
    last_result = None
    for attempt in range(JEV_MAX_RETRIES):
        r = jev_adapter.jev_yes_no(state=state, question=q, no_text=nt,
                                   mode="choice", use_mock=use_mock,
                                   mock_response=mock_response)
        last_result = r
        if r.get("ok"):
            break
        if _is_retryable(r) and attempt < JEV_MAX_RETRIES - 1:
            wait = JEV_BACKOFF_BASE_S * (attempt + 1)
            print("  JEV retry %d/%d for %s [%s] in %.0fs: %s" % (
                attempt + 1, JEV_MAX_RETRIES, quote.get("code"), kind,
                wait, (r.get("error_message") or r.get("detail") or "")[:80]))
            time.sleep(wait)
            continue
        break

    if not use_mock:
        time.sleep(JEV_INTER_CALL_DELAY_S)

    parsed = _parse_choice(last_result)
    parsed["question"] = q
    return parsed
