#!/usr/bin/env python3
"""监测用大盘环境：真实指数行情 + 本地池聚合。

指数来源：腾讯行情 qt.gtimg.cn（公开接口，只读）
  - sh000001 上证指数
  - sz399001 深证成指
  - sh000300 沪深300
  - sz399006 创业板指

本地池聚合：复用 src/engine/market_judge.py 的判断逻辑。
本模块不写文件。
"""
import json
import os
import subprocess
import sys
import urllib.request
from typing import Any, Dict, List, Optional

_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

INDEX_SYMBOLS = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sh000300": "沪深300",
    "sz399006": "创业板指",
}


def fetch_indices() -> List[Dict[str, Any]]:
    """抓取四个主要指数的实时行情。"""
    url = "https://qt.gtimg.cn/q=" + ",".join(INDEX_SYMBOLS)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read().decode("gbk", errors="replace")
    except Exception as e:
        return [{"code": "ALL", "name": "指数抓取失败", "error": str(e)[:120]}]

    out: List[Dict[str, Any]] = []
    for line in raw.strip().split("\n"):
        if "=" not in line:
            continue
        var, val = line.split("=", 1)
        sym = var.strip().lstrip("v_")
        fields = val.strip().strip('"').split("~")
        if len(fields) < 33:
            continue
        try:
            out.append({
                "code": sym,
                "name": fields[1],
                "price": float(fields[3]),
                "prev_close": float(fields[4]) if fields[4] else None,
                "change_pct": float(fields[32]) if fields[32] else None,
                "timestamp": fields[30] if len(fields) > 30 else None,
            })
        except (ValueError, TypeError):
            continue
    return out


def _load_ranking() -> Optional[Dict[str, Any]]:
    path = os.path.join(
        os.path.expanduser(os.environ.get("STOCK_DAILY_DIR", "~/harness/stock_daily")),
        "stock_ranking.json",
    )
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _load_anchors() -> List[Dict[str, Any]]:
    path = os.path.join(
        os.path.expanduser(os.environ.get("DATA_ROOT", "~/harness")),
        "anchor_status.json",
    )
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def build_market_context(quotes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """构造大盘环境：真实指数 + 本地池聚合判断。"""
    from engine import market_judge

    indices = fetch_indices()
    index_rows = [i for i in indices if i.get("code") != "ALL"]
    index_error = next((i for i in indices if i.get("code") == "ALL"), None)

    anchors = _load_anchors()
    ranking = _load_ranking()
    local = market_judge.judge_market(anchors, ranking, {})

    # 指数涨跌 → 大盘方向事实
    index_chg = [i["change_pct"] for i in index_rows if i.get("change_pct") is not None]
    avg_index_chg = round(sum(index_chg) / len(index_chg), 2) if index_chg else None
    all_down = bool(index_chg) and all(c < 0 for c in index_chg)
    all_up = bool(index_chg) and all(c > 0 for c in index_chg)

    if avg_index_chg is None:
        index_bias = "unknown"
    elif all_down:
        index_bias = "普跌"
    elif all_up:
        index_bias = "普涨"
    elif avg_index_chg < -0.5:
        index_bias = "偏弱"
    elif avg_index_chg > 0.5:
        index_bias = "偏强"
    else:
        index_bias = "震荡"

    # 池内涨跌家数
    pool_chg = [q.get("change_pct") for q in quotes
                if q.get("change_pct") is not None and q.get("code") != "ALL"]
    pool_up = sum(1 for c in pool_chg if c > 0)
    pool_down = sum(1 for c in pool_chg if c < 0)

    summary_parts = []
    if index_rows:
        summary_parts.append("四大指数均%s，均值 %+.2f%%" % (index_bias, avg_index_chg))
    else:
        summary_parts.append("指数行情不可用")
    if pool_chg:
        summary_parts.append("关注池 %d 涨 / %d 跌" % (pool_up, pool_down))
    summary_parts.append("本地池锚价聚合判断：%s" % local.get("verdict", "无法判断"))

    return {
        "verdict": local.get("verdict", "无法判断"),
        "confidence": local.get("confidence", "low"),
        "index_bias": index_bias,
        "avg_index_change_pct": avg_index_chg,
        "indices": index_rows,
        "index_error": index_error.get("error") if index_error else None,
        "pool_up": pool_up,
        "pool_down": pool_down,
        "local_verdict": local.get("verdict"),
        "local_evidence": local.get("evidence", []),
        "local_counter_evidence": local.get("counter_evidence", []),
        "local_limitations": _scoped_limitations(
            local.get("limitations", []), bool(index_rows)),
        "monitor_limitations": _monitor_limitations(bool(index_rows)),
        "summary": "；".join(summary_parts),
        "fact_vs_inference": {
            "facts": [
                "四大指数实时涨跌幅（腾讯行情公开接口）",
                "关注池 %d 只个股实时涨跌幅" % len(pool_chg),
                "各股锚价与锚价偏离（~/harness/anchor_status.json）",
            ],
            "inferences": [
                "「%s」的大盘方向判断" % index_bias,
                "本地池聚合的「%s」结论" % local.get("verdict"),
            ],
        },
    }


def _scoped_limitations(limitations: List[str], has_index: bool) -> List[str]:
    """收窄数据局限的适用范围，并剔除在监测层已不成立的条目。

    src/engine/market_judge.py 的 limitations 是为「无外部指数行情」场景写的，
    直接搬到监测报告会与已抓到的真实指数行情自相矛盾。
    这里保留仍然成立的局限，并明确限定它只约束「本地池锚价聚合判断」，
    不约束基于真实指数行情得出的大盘方向。

    """
    # 监测层已通过 session_guard 依 2026-2027 静态节假日表确认交易日，
    # 该条局限在监测报告中不成立。
    out = [l for l in limitations if "法定节假日无法确认" not in l]
    if has_index:
        out = [l for l in out if "无外部指数行情数据" not in l]
    return out


def _monitor_limitations(has_index: bool) -> List[str]:
    """监测层自身的数据局限（与引擎层通用局限区分开）。

    交易日由 session_guard 依据 src/engine/trading_day.py 的
    2026-2027 静态节假日表判定，已确认，不再列为局限。
    """
    out = []
    if not has_index:
        out.append("未抓到真实指数行情，大盘方向仅由本地池聚合推断")
    out.append("无成交额与市场级涨跌家数，池内涨跌统计不等于全市场广度")
    return out
