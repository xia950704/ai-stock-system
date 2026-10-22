#!/usr/bin/env python3
"""监测数据采集层：价格 + 锚价偏离 + 新闻（只读）。

职责：
  - 复用 src/scripts/fetch/fetch_realtime.py 抓取实时价
  - 读取 ~/harness/anchor_status.json 权威锚价
  - 复用 src/search/client.py 抓取每只股票 2-3 条最新新闻

本模块不写任何原始数据文件，不做决策。
"""
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from stock_codes import ALL_POOL, StockEntry

DATA_ROOT = os.path.expanduser(os.environ.get("DATA_ROOT", "~/harness"))
ANCHOR_PATH = os.path.join(DATA_ROOT, "anchor_status.json")

_FETCH_SCRIPT = os.path.join(_SRC, "scripts", "fetch", "fetch_realtime.py")
_ANCHOR_SCRIPT = os.path.join(_SRC, "scripts", "fetch", "update_anchor.py")
_SEARCH_DIR = os.path.join(_SRC, "search")
if _SEARCH_DIR not in sys.path:
    sys.path.insert(0, _SEARCH_DIR)


def _load_anchors() -> Dict[str, Dict[str, Any]]:
    """读取锚价权威源，返回 code -> record。"""
    if not os.path.exists(ANCHOR_PATH):
        return {}
    try:
        with open(ANCHOR_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    # 用 stock_codes.normalize_code 归一化键，使裸码 512400 与 sh512400 对齐
    from stock_codes import normalize_code
    return {normalize_code(d.get("code", "")): d for d in data if isinstance(d, dict)}


def fetch_prices() -> List[Dict[str, Any]]:
    """调用 fetch_realtime.py 抓取关注池实时价（只读）。"""
    try:
        proc = subprocess.run(
            [sys.executable, _FETCH_SCRIPT],
            capture_output=True, text=True, timeout=60, cwd=_SRC,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return [{"code": "ALL", "name": "抓取失败", "error": str(e)[:120]}]
    if proc.returncode != 0:
        return [{"code": "ALL", "name": "抓取失败",
                 "error": (proc.stderr or proc.stdout)[-200:]}]
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        return [{"code": "ALL", "name": "解析失败", "error": str(e)[:120]}]


def _run_anchor_update() -> None:
    """更新 anchor_status.json 的 current/prev_close（锚价本身不动）。"""
    try:
        subprocess.run([sys.executable, _ANCHOR_SCRIPT], capture_output=True,
                       text=True, timeout=60, cwd=_SRC)
    except (subprocess.TimeoutExpired, OSError):
        pass


def deviation_status(deviation: Optional[float]) -> str:
    """锚价偏离状态（与 fetch_realtime.py 口径一致）。"""
    if deviation is None:
        return "无锚价"
    if deviation < -5:
        return "买入区间"
    if deviation < 0:
        return "偏低估"
    if deviation <= 5:
        return "合理"
    if deviation <= 10:
        return "偏高"
    return "超买"


def collect_quotes(include_anchor_update: bool = False) -> List[Dict[str, Any]]:
    """采集每只股票的：现价 / 涨跌幅 / 锚价 / 偏离 / 状态。"""
    if include_anchor_update:
        _run_anchor_update()
    prices = fetch_prices()
    anchors = _load_anchors()
    rows: List[Dict[str, Any]] = []
    for p in prices:
        code = p.get("code", "")
        if code == "ALL":
            rows.append(p)
            continue
        a = anchors.get(code, {})
        anchor = a.get("anchor")
        deviation = p.get("deviation")
        if deviation is None and anchor and p.get("price"):
            deviation = round((p["price"] - anchor) / anchor * 100, 2)
        rows.append({
            "code": code,
            "name": p.get("name") or a.get("name") or code,
            "price": p.get("price"),
            "prev_close": p.get("prev_close"),
            "change_pct": p.get("change_pct"),
            "timestamp": p.get("timestamp"),
            "anchor": anchor,
            "deviation": deviation,
            "status": p.get("status") or deviation_status(deviation),
            "pe": a.get("pe"),
            "has_anchor": anchor is not None,
        })
    return rows


def build_news_query(stock: StockEntry) -> str:
    """构建新闻检索词（只含代码与名称，不含持仓/成本）。"""
    num = stock.code.lstrip("shzk")
    year, month = _current_month()
    return "%s %s 最新消息 公告 业绩 %d年%d月" % (stock.name, num, year, month)

def _current_month():
    """当前月份（用于检索词，避免写死年月导致检索词过期）。"""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone(timedelta(hours=8)))
    return now.year, now.month


def _domain_of(url: str) -> str:
    if not url:
        return ""
    return url.split("//", 1)[-1].split("/", 1)[0]


def _clean_text(text: str, limit: int = 200) -> str:
    """把检索到的整页正文压成可读摘要（去 markdown 表格行与多余空白）。"""
    if not text:
        return ""
    import re

    # 去掉 "Image 2 Image 3" 这类抓取噪声
    text = re.sub(r"(?:\bImage\s*\d+\b[\s,]*)+", " ", text)
    lines = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("|") or set(line) <= set("| -:"):
            continue
        lines.append(line)
        if sum(len(x) for x in lines) > limit * 2:
            break
    out = " ".join(lines)
    out = re.sub(r"\s+", " ", out).strip()
    if len(out) > limit:
        out = out[:limit].rstrip() + "…"
    return out


def _extract_date(text: str) -> Optional[str]:
    """从正文中尽力提取日期（YYYY-MM-DD / YYYY年MM月DD日 / MM月DD日）。"""
    import re

    if not text:
        return None
    m = re.search(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})", text)
    if m:
        return "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3)))
    m = re.search(r"(\d{1,2})月(\d{1,2})日", text)
    if m:
        return "%02d-%02d" % (int(m.group(1)), int(m.group(2)))
    return None


def fetch_news(stock: StockEntry, limit: int = 3) -> Dict[str, Any]:
    """抓取单只股票的最新新闻摘要。"""
    from client import search, failure_status

    query = build_news_query(stock)
    r = search(query, limit=limit)
    if not r.get("ok"):
        return {
            "code": stock.code,
            "available": False,
            "status": failure_status(r),
            "error": (r.get("error_message") or "")[:150],
            "items": [],
            "query": query,
        }
    items = []
    for res in r.get("results", [])[:limit]:
        content = res.get("content") or res.get("snippet") or ""
        items.append({
            "title": (res.get("title") or "")[:120],
            "url": res.get("url", ""),
            "snippet": _clean_text(content),
            "published_at": (res.get("published_at") or res.get("date")
                             or _extract_date(content)),
            "domain": _domain_of(res.get("url", "")),
        })
    return {
        "code": stock.code,
        "available": bool(items),
        "status": "ok" if items else "empty",
        "items": items,
        "query": query,
    }


def pool_by_code() -> Dict[str, StockEntry]:
    """code -> StockEntry。"""
    return {s.code: s for s in ALL_POOL}
