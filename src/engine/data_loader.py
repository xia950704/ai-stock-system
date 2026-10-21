#!/usr/bin/env python3
"""输入数据读取与校验（P3-2 第 1 层）。

数据来源（只读）：
  - ~/harness/anchor_status.json          : 锚价权威源（56 条）
  - ~/harness/stock_daily/stock_ranking.json : 综合排名（26 条）
  - ~/harness/stock_daily/stock_portfolio_enriched.json : 投资组合（35 条）
  - ~/harness/stock_daily/realtime_prices_YYYYMMDD.json : 实时价格快照
  - src/obsidian/01-股票投研/              : 原始研究资料（只读镜像）

所有读取均为只读；不写入任何原始文件。
"""
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---- 路径解析（与 validate_stock_config.py 同契约）----
DATA_ROOT = os.path.expanduser(os.environ.get("DATA_ROOT", "~/harness"))
STOCK_DAILY_DIR = os.path.expanduser(os.environ.get("STOCK_DAILY_DIR", "~/harness/stock_daily"))
OBS_MIRROR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "obsidian", "01-股票投研")

ANCHOR_PATH = os.path.join(DATA_ROOT, "anchor_status.json")
RANKING_PATH = os.path.join(STOCK_DAILY_DIR, "stock_ranking.json")
PORTFOLIO_PATH = os.path.join(STOCK_DAILY_DIR, "stock_portfolio_enriched.json")

# P0 关注池（来源：04-医药股票跟踪池.md，2026-09-23 口径）
P0_POOL = [
    {"code": "sh600276", "name": "恒瑞医药", "market": "SH"},
    {"code": "sz000963", "name": "华东医药", "market": "SZ"},
    {"code": "sz002262", "name": "恩华药业", "market": "SZ"},
    {"code": "sz002422", "name": "科伦药业", "market": "SZ"},
    {"code": "sh603259", "name": "药明康德", "market": "SH"},
    {"code": "sh688506", "name": "百利天恒", "market": "SH"},
    {"code": "sh512400", "name": "512400有色金属ETF", "market": "SH"},
]

# 观察池 / P2（原 P0 降级）
P2_POOL = [
    {"code": "sh688331", "name": "荣昌生物", "market": "SH"},
]


def _load_json(path: str) -> Tuple[Optional[Any], Optional[str]]:
    """加载 JSON，返回 (data, error)。"""
    if not os.path.exists(path):
        return None, f"文件不存在: {path}"
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f), None
    except json.JSONDecodeError as e:
        return None, f"JSON 解析失败 {path}: {e}"
    except OSError as e:
        return None, f"读取失败 {path}: {e}"


def _norm_code(code: str) -> str:
    """标准化股票代码：600276.SH -> sh600276, 600276 -> sh600276"""
    c = str(code).strip().upper()
    if "." in c:
        prefix, num = c.split(".", 1)
        if prefix in ("SH", "SZ", "HK"):
            return (prefix[:2].lower() + num)
        # 反向格式：600276.SH -> sh600276
        if num in ("SH", "SZ", "HK"):
            return (num[:2].lower() + prefix)
    if c.startswith("SH"):
        return "sh" + c[2:]
    if c.startswith("SZ"):
        return "sz" + c[2:]
    if c.startswith("HK"):
        return "hk" + c[2:]
    # 纯数字：默认 SH
    if c.isdigit():
        if c.startswith(("6", "9", "5")):
            return "sh" + c
        if c.startswith(("0", "3", "2")):
            return "sz" + c
    return c


def load_anchor_status() -> Tuple[Optional[List[Dict]], Optional[str]]:
    """加载锚价权威源。"""
    data, err = _load_json(ANCHOR_PATH)
    if err:
        return None, err
    if not isinstance(data, list):
        return None, f"anchor_status.json 应为数组，实际: {type(data).__name__}"
    return data, None


def load_ranking() -> Tuple[Optional[Dict], Optional[str]]:
    """加载综合排名。"""
    data, err = _load_json(RANKING_PATH)
    if err:
        return None, err
    if not isinstance(data, dict):
        return None, f"stock_ranking.json 应为对象，实际: {type(data).__name__}"
    return data, None


def load_portfolio() -> Tuple[Optional[List[Dict]], Optional[str]]:
    """加载投资组合。"""
    data, err = _load_json(PORTFOLIO_PATH)
    if err:
        return None, err
    if not isinstance(data, list):
        return None, f"stock_portfolio_enriched.json 应为数组，实际: {type(data).__name__}"
    return data, None


def load_realtime_prices(date_str: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
    """加载指定日期的实时价格快照。"""
    path = os.path.join(STOCK_DAILY_DIR, f"realtime_prices_{date_str}.json")
    if not os.path.exists(path):
        return None, f"实时价格文件不存在: {path}"
    data, err = _load_json(path)
    if err:
        return None, err
    # 兼容两种格式：数组 [{code, price, ...}] 或 对象 {code: {price, ...}}
    if isinstance(data, dict):
        rows = []
        for code, item in data.items():
            if isinstance(item, dict):
                row = dict(item)
                row.setdefault("code", code)
                rows.append(row)
        return rows, None
    if not isinstance(data, list):
        return None, f"realtime_prices 应为数组或对象，实际: {type(data).__name__}"
    return data, None


def find_latest_realtime() -> Tuple[Optional[str], Optional[List[Dict]], Optional[str]]:
    """查找最新的实时价格文件。"""
    if not os.path.isdir(STOCK_DAILY_DIR):
        return None, None, f"STOCK_DAILY_DIR 不存在: {STOCK_DAILY_DIR}"
    files = sorted([f for f in os.listdir(STOCK_DAILY_DIR)
                    if f.startswith("realtime_prices_") and f.endswith(".json")])
    if not files:
        return None, None, "未找到 realtime_prices_*.json 文件"
    latest = files[-1]
    date_str = latest[len("realtime_prices_"):-len(".json")]
    data, err = load_realtime_prices(date_str)
    return date_str, data, err


def build_anchor_index(anchor_list: List[Dict]) -> Dict[str, Dict]:
    """以标准化代码为键建立锚价索引。"""
    idx = {}
    for item in anchor_list:
        code = _norm_code(item.get("code", ""))
        if code:
            idx[code] = item
    return idx


def build_ranking_index(ranking_data: Dict) -> Dict[str, Dict]:
    """以标准化代码为键建立排名索引。"""
    idx = {}
    for item in ranking_data.get("rankings", []):
        code = _norm_code(item.get("code", ""))
        if code:
            idx[code] = item
    return idx


def build_portfolio_index(portfolio_list: List[Dict]) -> Dict[str, Dict]:
    """以标准化代码为键建立投资组合索引。"""
    idx = {}
    for item in portfolio_list:
        code = _norm_code(item.get("stock_code", ""))
        if code:
            idx[code] = item
    return idx


def validate_data_freshness(anchor_data: List[Dict], ranking_data: Dict,
                            realtime_date: Optional[str]) -> Dict[str, Any]:
    """校验数据新鲜度，返回状态报告。"""
    now = datetime.now(timezone(timedelta(hours=8)))
    today_str = now.strftime("%Y-%m-%d")

    report = {
        "check_time": now.isoformat(),
        "today": today_str,
        "anchor_count": len(anchor_data) if anchor_data else 0,
        "ranking_run_date": ranking_data.get("run_date") if ranking_data else None,
        "realtime_date": realtime_date,
        "issues": [],
    }

    # 锚价数据完整性
    if anchor_data is None:
        report["issues"].append("anchor_status.json 不可用")
        return report

    # 排名数据新鲜度
    if ranking_data is None:
        report["issues"].append("stock_ranking.json 不可用")
    else:
        run_date = ranking_data.get("run_date")
        if run_date and run_date != today_str:
            try:
                rd = datetime.strptime(run_date, "%Y-%m-%d").replace(tzinfo=timezone(timedelta(hours=8)))
                days = (now - rd).days
                report["ranking_age_days"] = days
                if days > 7:
                    report["issues"].append(f"排名数据过期: run_date={run_date}, 距今 {days} 天")
            except ValueError:
                pass

    # 实时价格新鲜度
    if realtime_date:
        try:
            rt_date = datetime.strptime(realtime_date, "%Y%m%d").replace(tzinfo=timezone(timedelta(hours=8)))
            days = (now - rt_date).days
            report["realtime_age_days"] = days
            if days > 3:
                report["issues"].append(f"实时价格过期: {realtime_date}, 距今 {days} 天")
        except ValueError:
            report["issues"].append(f"实时价格日期格式异常: {realtime_date}")

    return report


def get_pool_status(anchor_idx: Dict[str, Dict], ranking_idx: Dict[str, Dict],
                    portfolio_idx: Dict[str, Dict]) -> Dict[str, Any]:
    """获取 P0 池每只股票的状态快照。"""
    status = {}
    for stock in P0_POOL + P2_POOL:
        code = stock["code"]
        a = anchor_idx.get(code, {})
        r = ranking_idx.get(code, {})
        p = portfolio_idx.get(code, {})
        status[code] = {
            "name": stock["name"],
            "market": stock["market"],
            "pool": "P0" if stock in P0_POOL else "P2",
            "current": a.get("current"),
            "anchor": a.get("anchor"),
            "deviation": a.get("deviation"),
            "status": a.get("status"),
            "pe": a.get("pe"),
            "prev_close": a.get("prev_close"),
            "change_pct": a.get("change_pct"),
            "composite_score": r.get("composite_score"),
            "tech_score": r.get("tech_score"),
            "ml_boost": r.get("ml_boost"),
            "latest_date": r.get("latest_date"),
            "position": p.get("position"),
            "portfolio_status": p.get("status"),
            "days_since_update": p.get("days_since_update"),
        }
    return status
