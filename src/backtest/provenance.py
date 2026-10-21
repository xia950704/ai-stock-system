#!/usr/bin/env python3
"""P4 数据源溯源与反前视验证 (P4-1, P4-4)。

核心原则：所有输入必须在回放日期(as_of)当日或之前已可获得。
任何日期 > as_of 的数据引入均属前视偏差，必须拒绝并记录。
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---- 配置路径 ----
DB_PATH = os.environ.get("ASTOCK_DB", os.path.expanduser("~/harness/deeppulse/db/astock.duckdb"))
ANCHOR_DIR = os.path.expanduser("~/harness/stock_daily")
OBS_VAULT = os.path.expanduser("~/obsidian/all about xia")
OBS_STOCK_DIR = os.path.join(OBS_VAULT, "01-股票投研", "股票")

# 当前锚价文件已知数据日期（由 P3.5 报告确认）

# P0 + P2 池
POOL_CODES = [
    "600276", "000963", "002262", "002422",
    "603259", "688506", "512400", "688331",
]

# ---- 通用工具 ----
def _connect_db():
    import duckdb
    return duckdb.connect(DB_PATH, read_only=True)

def _norm_code(code: str) -> str:
    """标准化为纯数字代码（duckdb 格式）。"""
    c = str(code).strip().upper()
    if c.startswith("SH"): return c[2:]
    if c.startswith("SZ"): return c[2:]
    if c.startswith("HK"): return c[2:]
    return c

def _parse_date(s: str) -> Optional[date]:
    """解析 YYYY-MM-DD 或 YYYYMMDD。"""
    if not s: return None
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        s = f"{s[:4]}-{s[4:6]}-{s[6:]}"
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None

def _date_le(d1: Optional[date], d2: Optional[date]) -> bool:
    """d1 <= d2（None 视为不满足）。"""
    return d1 is not None and d2 is not None and d1 <= d2

# ---- 1. K线数据源 (duckdb) ----
def kline_available() -> bool:
    """duckdb 是否可用。"""
    try:
        with _connect_db() as conn:
            conn.execute("SELECT 1 FROM daily_kline LIMIT 1")
        return True
    except Exception:
        return False

def kline_trading_dates(start: Optional[date] = None, end: Optional[date] = None) -> List[str]:
    """获取交易日列表（权威来源：duckdb actual trade dates）。"""
    with _connect_db() as conn:
        q = "SELECT DISTINCT trade_date FROM daily_kline WHERE 1=1"
        params = []
        if start:
            q += " AND trade_date >= ?"
            params.append(start.isoformat())
        if end:
            q += " AND trade_date <= ?"
            params.append(end.isoformat())
        q += " ORDER BY trade_date"
        rows = conn.execute(q, params).fetchall()
    return [r[0].isoformat() if hasattr(r[0], 'isoformat') else str(r[0]) for r in rows]

def kline_prices_asof(codes: List[str], as_of: date, lookback_days: Optional[int] = None) -> Dict[str, List[Dict]]:
    """
    仅返回 trade_date <= as_of 的行情。
    反前视：严格断言 max(trade_date) <= as_of。
    """
    if not codes:
        return {}
    placeholders = ",".join(["?"] * len(codes))
    with _connect_db() as conn:
        q = f"""
            SELECT code, trade_date, open, high, low, close, volume, amount, turnover
            FROM daily_kline
            WHERE code IN ({placeholders}) AND trade_date <= ?
        """
        params = [_norm_code(c) for c in codes] + [as_of.isoformat()]
        if lookback_days:
            q += " AND trade_date >= ?"
            params.append((as_of - timedelta(days=lookback_days)).isoformat())
        q += " ORDER BY code, trade_date"
        rows = conn.execute(q, params).fetchall()
    result = {}
    for r in rows:
        code = r[0]
        td = r[1]
        td_date = td if isinstance(td, date) else datetime.fromisoformat(str(td)).date()
        # 反前视断言
        assert td_date <= as_of, f"前视偏差: {code} {td_date} > {as_of}"
        result.setdefault(code, []).append({
            "trade_date": td.isoformat() if hasattr(td, 'isoformat') else str(td),
            "open": r[2], "high": r[3], "low": r[4], "close": r[5],
            "volume": r[6], "amount": r[7], "turnover": r[8],
        })
    return result

def kline_latest_price(codes: List[str], as_of: date) -> Dict[str, Optional[float]]:
    """获取 as_of 或之前的最近收盘价。"""
    prices = kline_prices_asof(codes, as_of, lookback_days=5)
    return {c: (prices[c][-1]["close"] if prices.get(c) else None) for c in codes}

# ---- 2. 锚价快照源 ----
def _list_anchor_snapshots() -> List[Tuple[date, str]]:
    """列出所有锚价快照文件及其数据日期。
    
    仅使用显式日期命名的快照文件 (anchor_status_YYYY-MM-DD.json)。
    不假设 anchor_status.json 存在或包含当前数据。
    """
    snaps = []
    if not os.path.isdir(ANCHOR_DIR):
        return snaps
    for f in os.listdir(ANCHOR_DIR):
        if f.startswith("anchor_status_") and f.endswith(".json"):
            m = re.search(r"(\d{4}-\d{2}-\d{2})", f)
            if m:
                d = _parse_date(m.group(1))
                if d:
                    snaps.append((d, os.path.join(ANCHOR_DIR, f)))
    return sorted(snaps, key=lambda x: x[0])

def anchor_snapshot_asof(as_of: date) -> Dict[str, Any]:
    """
    找到数据日期 <= as_of 的最新锚价快照。
    返回: {"available": bool, "as_of": date, "path": str, "reason": str, "data": list|None}
    """
    snaps = _list_anchor_snapshots()
    chosen = None
    for d, path in snaps:
        if d <= as_of:
            chosen = (d, path)
        else:
            break
    if not chosen:
        return {"available": False, "as_of": None, "path": None,
                "reason": f"无锚价快照可用于 {as_of}", "data": None}
    d, path = chosen
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {"available": True, "as_of": d.isoformat(), "path": path,
                "reason": f"锚价快照 {d} 可用", "data": data}
    except Exception as e:
        return {"available": False, "as_of": d.isoformat(), "path": path,
                "reason": f"读取失败: {e}", "data": None}

# ---- 3. 排名数据源 ----
def _list_ranking_snapshots() -> List[Tuple[date, str]]:
    """列出排名快照。仅使用显式日期命名的文件。"""
    snaps = []
    if not os.path.isdir(ANCHOR_DIR):
        return snaps
    for f in os.listdir(ANCHOR_DIR):
        if f.startswith("stock_ranking_") and f.endswith(".json"):
            m = re.search(r"(\d{4}-\d{2}-\d{2})", f)
            if m:
                d = _parse_date(m.group(1))
                if d:
                    snaps.append((d, os.path.join(ANCHOR_DIR, f)))
    return sorted(snaps, key=lambda x: x[0])

def ranking_snapshot_asof(as_of: date) -> Dict[str, Any]:
    snaps = _list_ranking_snapshots()
    chosen = None
    for d, path in snaps:
        if d <= as_of:
            chosen = (d, path)
        else:
            break
    if not chosen:
        return {"available": False, "as_of": None, "path": None,
                "reason": f"无排名快照可用于 {as_of}", "data": None}
    d, path = chosen
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {"available": True, "as_of": d.isoformat(), "path": path,
                "reason": f"排名快照 {d} 可用", "data": data}
    except Exception as e:
        return {"available": False, "as_of": d.isoformat(), "path": path,
                "reason": f"读取失败: {e}", "data": None}

# ---- 4. 实时价格快照源 ----
def _list_realtime_snapshots() -> List[Tuple[date, str]]:
    snaps = []
    if not os.path.isdir(ANCHOR_DIR):
        return snaps
    for f in os.listdir(ANCHOR_DIR):
        if f.startswith("realtime_prices_") and f.endswith(".json"):
            m = re.search(r"(\d{8})", f)
            if m:
                d = _parse_date(m.group(1))
                if d:
                    snaps.append((d, os.path.join(ANCHOR_DIR, f)))
    return sorted(snaps, key=lambda x: x[0])

def realtime_snapshot_asof(as_of: date) -> Dict[str, Any]:
    snaps = _list_realtime_snapshots()
    chosen = None
    for d, path in snaps:
        if d <= as_of:
            chosen = (d, path)
        else:
            break
    if not chosen:
        return {"available": False, "as_of": None, "path": None,
                "reason": f"无实时价格快照可用于 {as_of}", "data": None}
    d, path = chosen
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {"available": True, "as_of": d.isoformat(), "path": path,
                "reason": f"实时价格 {d} 可用", "data": data}
    except Exception as e:
        return {"available": False, "as_of": d.isoformat(), "path": path,
                "reason": f"读取失败: {e}", "data": None}

# ---- 5. 研究笔记源 (Obsidian Vault git history) ----
def _obs_git_latest_commit_before(as_of: date) -> Optional[str]:
    """找到提交日期 <= as_of 23:59:59 的最新提交 hash。"""
    dt = datetime.combine(as_of, datetime.max.time()).strftime("%Y-%m-%d %H:%M:%S")
    try:
        out = subprocess.run(
            ["git", "rev-list", "-1", "--before", dt, "HEAD"],
            cwd=OBS_VAULT, capture_output=True, text=True, timeout=10
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return None

def _obs_git_show(commit: str, path: str) -> Optional[str]:
    """读取某次提交下的文件内容。"""
    try:
        out = subprocess.run(
            ["git", "show", f"{commit}:{path}"],
            cwd=OBS_VAULT, capture_output=True, text=True, timeout=10
        )
        if out.returncode == 0:
            return out.stdout
    except Exception:
        pass
    return None

def _find_note_path_in_vault(code: str) -> Optional[str]:
    """在 Vault 中按 stock 目录找笔记路径。"""
    # 先按名称匹配（需要 code->name 映射）
    name_map = {
        "600276": "恒瑞医药", "000963": "华东医药", "002262": "恩华药业",
        "002422": "科伦药业", "603259": "药明康德", "688506": "百利天恒",
        "512400": "512400有色金属ETF", "688331": "荣昌生物",
    }
    name = name_map.get(code)
    if not name:
        return None
    stock_dir = os.path.join(OBS_STOCK_DIR, name)
    if not os.path.isdir(stock_dir):
        return None
    for f in os.listdir(stock_dir):
        if "投资笔记" in f and f.endswith(".md"):
            # 返回相对 Vault 根的路径
            return os.path.join("01-股票投研", "股票", name, f)
    return None

def research_note_asof(code: str, as_of: date) -> Dict[str, Any]:
    """
    通过 git history 读取 as_of 当日可见的研究笔记内容。
    返回: {"available": bool, "commit": str, "commit_date": str, "content": str|None, "reason": str}
    """
    commit = _obs_git_latest_commit_before(as_of)
    if not commit:
        return {"available": False, "commit": None, "commit_date": None,
                "content": None, "reason": f"Obsidian 无提交早于 {as_of}"}
    # 获取提交日期
    try:
        out = subprocess.run(
            ["git", "show", "-s", "--format=%ad", "--date=short", commit],
            cwd=OBS_VAULT, capture_output=True, text=True, timeout=5
        )
        commit_date = out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        commit_date = None
    note_path = _find_note_path_in_vault(code)
    if not note_path:
        return {"available": False, "commit": commit, "commit_date": commit_date,
                "content": None, "reason": f"无匹配笔记路径: {code}"}
    content = _obs_git_show(commit, note_path)
    if not content:
        return {"available": False, "commit": commit, "commit_date": commit_date,
                "content": None, "reason": f"git show 失败: {note_path}@{commit}"}
    return {"available": True, "commit": commit, "commit_date": commit_date,
            "content": content, "reason": f"笔记可用 (commit {commit[:8]}, {commit_date})"}

# ---- 6. 综合溯源检查 ----
def provenance_check(as_of: date, codes: List[str]) -> Dict[str, Any]:
    """对指定日期和代码池，检查各数据源的可用性。"""
    return {
        "as_of": as_of.isoformat(),
        "kline": {"available": kline_available()},
        "anchor": anchor_snapshot_asof(as_of),
        "ranking": ranking_snapshot_asof(as_of),
        "realtime": realtime_snapshot_asof(as_of),
        "research": {c: research_note_asof(c, as_of) for c in codes},
        "search": {"available": False, "reason": "无历史 Search 记录"},
        "jev": {"available": False, "reason": "无历史 JEV 记录"},
    }

# ---- 7. 前视偏差检查 ----
def check_lookahead(as_of: date, prices: Dict[str, List[Dict]],
                    anchor_data: Optional[List], ranking_data: Optional[Dict],
                    realtime_data: Optional[List]) -> Dict[str, Any]:
    """检查输入是否包含 > as_of 的数据（前视偏差）。"""
    violations = []
    # K线
    for code, rows in prices.items():
        for r in rows:
            td = _parse_date(r["trade_date"])
            if td and td > as_of:
                violations.append(f"K线前视: {code} {td} > {as_of}")
    # 锚价/排名/实时快照已通过 asof 选择器，理论不应违规
    if anchor_data and isinstance(anchor_data, list):
        for item in anchor_data:
            ld = item.get("latest_date")
            if ld and _parse_date(ld) and _parse_date(ld) > as_of:
                violations.append(f"锚价 latest_date 前视: {ld} > {as_of}")
    if ranking_data and isinstance(ranking_data, dict):
        rd = ranking_data.get("run_date")
        if rd and _parse_date(rd) and _parse_date(rd) > as_of:
            violations.append(f"排名 run_date 前视: {rd} > {as_of}")
        for item in ranking_data.get("rankings", []):
            ld = item.get("latest_date")
            if ld and _parse_date(ld) and _parse_date(ld) > as_of:
                violations.append(f"排名 latest_date 前视: {ld} > {as_of}")
    if realtime_data and isinstance(realtime_data, list):
        for item in realtime_data:
            # realtime 没有显式日期，由文件名控制
            pass
    return {"clean": len(violations) == 0, "violations": violations, "check_time": datetime.now().isoformat()}

