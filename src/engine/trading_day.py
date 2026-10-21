#!/usr/bin/env python3
"""交易日与行情新鲜度判断（P3-2 第 2 层）。

规则：
  - A 股交易日基准：Asia/Shanghai（UTC+8）
  - 周一至周五为潜在交易日；周末直接判定为非交易日
  - 法定节假日：当前无可信来源，标记为「无法确认」并降级
  - 数据新鲜度：以 anchor_status.json 的 mtime 与 realtime_prices 文件日期为准
  - 禁止仅凭系统当前日期认定当天存在有效行情
"""
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

DATA_ROOT = os.path.expanduser(os.environ.get("DATA_ROOT", "~/harness"))
STOCK_DAILY_DIR = os.path.expanduser(os.environ.get("STOCK_DAILY_DIR", "~/harness/stock_daily"))
ANCHOR_PATH = os.path.join(DATA_ROOT, "anchor_status.json")

TZ = timezone(timedelta(hours=8))

_CN_MARKET_HOLIDAYS = {
    # 2026
    "2026-01-01",                              # 元旦
    "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19",
    "2026-02-20", "2026-02-21", "2026-02-22",    # 春节（7 天）
    "2026-04-04", "2026-04-05", "2026-04-06",    # 清明节
    "2026-05-01", "2026-05-02", "2026-05-03",
    "2026-05-04", "2026-05-05",                  # 劳动节（5 天）
    "2026-06-19", "2026-06-20", "2026-06-21",    # 端午节
    "2026-09-24", "2026-09-25", "2026-09-26",    # 中秋节
    "2026-10-01", "2026-10-02", "2026-10-03",
    "2026-10-04", "2026-10-05", "2026-10-06",
    "2026-10-07",                                # 国庆节（7 天）
    # 2027
    "2027-01-01",                                # 元旦
    "2027-02-06", "2027-02-07", "2027-02-08",
    "2027-02-09", "2027-02-10", "2027-02-11",
    "2027-02-12",                                # 春节（7 天）
    "2027-04-05",                                # 清明节
    "2027-05-01", "2027-05-02", "2027-05-03",
    "2027-05-04", "2027-05-05", "2027-05-06",
    "2027-05-07",                                # 劳动节（7 天）
    "2027-05-29", "2027-05-30", "2027-05-31",    # 端午节
    "2027-09-15",                                # 中秋节
    "2027-10-01", "2027-10-02", "2027-10-03",
    "2027-10-04", "2027-10-05", "2027-10-06",
    "2027-10-07",                                # 国庆节（7 天）
}


def now_sh() -> datetime:
    """返回 Asia/Shanghai 当前时间。"""
    return datetime.now(TZ)


def is_weekend(d: datetime) -> bool:
    """判断是否为周末（周六=5, 周日=6）。"""
    return d.weekday() >= 5


def trading_day_status(reference_date: Optional[datetime] = None) -> Dict[str, Any]:
    """判断指定日期（默认今天）的交易日状态。

    返回：
      - date, weekday, is_weekend
      - likely_trading_day: 周末=False，工作日=True（节假日未确认）
      - confirmed: 是否可确认为交易日
      - note: 说明
    """
    d = reference_date or now_sh()
    weekend = is_weekend(d)
    date_str = d.strftime("%Y-%m-%d")
    if date_str in _CN_MARKET_HOLIDAYS:
        return {
            "date": date_str,
            "weekday": d.strftime("%A"),
            "is_weekend": weekend,
            "likely_trading_day": False,
            "confirmed": False,
            "note": "节假日",
        }
    return {
        "date": date_str,
        "weekday": d.strftime("%A"),
        "is_weekend": weekend,
        "likely_trading_day": not weekend,
        "confirmed": not weekend,
        "note": ("周末，非交易日" if weekend
                 else "工作日（节假日表已校验）"),
    }


def file_mtime(path: str) -> Optional[datetime]:
    """获取文件 mtime，返回 Asia/Shanghai 时间。"""
    try:
        mtime = os.path.getmtime(path)
        return datetime.fromtimestamp(mtime, tz=TZ)
    except OSError:
        return None


def data_freshness() -> Dict[str, Any]:
    """检查关键数据文件的新鲜度。"""
    now = now_sh()
    result = {
        "check_time": now.isoformat(),
        "anchor_mtime": None,
        "anchor_age_hours": None,
        "ranking_mtime": None,
        "ranking_age_hours": None,
        "issues": [],
    }

    # 锚价文件
    m = file_mtime(ANCHOR_PATH)
    if m:
        result["anchor_mtime"] = m.isoformat()
        result["anchor_age_hours"] = round((now - m).total_seconds() / 3600, 1)
        if result["anchor_age_hours"] > 48:
            result["issues"].append(f"anchor_status.json 超过 48 小时未更新")
    else:
        result["issues"].append("anchor_status.json 不存在或无法访问")

    # 排名文件
    rp = os.path.join(STOCK_DAILY_DIR, "stock_ranking.json")
    m = file_mtime(rp)
    if m:
        result["ranking_mtime"] = m.isoformat()
        result["ranking_age_hours"] = round((now - m).total_seconds() / 3600, 1)
        if result["ranking_age_hours"] > 48:
            result["issues"].append(f"stock_ranking.json 超过 48 小时未更新")
    else:
        result["issues"].append("stock_ranking.json 不存在或无法访问")

    return result


def effective_trading_day(trading_status: Dict[str, Any],
                          freshness: Dict[str, Any]) -> Dict[str, Any]:
    """综合交易日状态与数据新鲜度，给出有效交易日判断。"""
    if trading_status["is_weekend"]:
        return {
            "effective_date": None,
            "data_date": None,
            "verdict": "NON_TRADING_DAY",
            "reason": "当前为周末，无有效行情",
            "confidence": "high",
        }

    # 工作日：需确认数据新鲜度
    if freshness.get("issues"):
        return {
            "effective_date": None,
            "data_date": None,
            "verdict": "DATA_STALE",
            "reason": "; ".join(freshness["issues"]),
            "confidence": "medium",
        }

    return {
        "effective_date": trading_status["date"],
        "data_date": trading_status["date"],
        "verdict": "TRADING_DAY",
        "reason": "工作日且数据新鲜",
        "confidence": "medium",  # 节假日未确认，保守
    }

def data_asof_date(anchor_data, ranking_data, realtime_date) -> Optional[str]:
    """推断数据实际所属的最新交易日（区分"数据所属日期"与"文件修改时间"）。

    候选日期（取最新者，因为研判引擎读取的是"当前可得数据的最新截面"）：
      1. 实时价格快照的文件日期（realtime_prices_YYYYMMDD）
      2. 排名文件的 run_date
      3. 排名条目中 latest_date 的最大值（K 线库最新交易日）
    返回 None 表示无法确认数据所属日期。
    """
    candidates = []
    if realtime_date:
        try:
            candidates.append(datetime.strptime(realtime_date, "%Y%m%d").strftime("%Y-%m-%d"))
        except ValueError:
            candidates.append(None)
    if ranking_data:
        rd = ranking_data.get("run_date")
        if rd:
            candidates.append(rd)
        for item in ranking_data.get("rankings", []):
            ld = item.get("latest_date")
            if ld:
                candidates.append(ld)
    candidates = [c for c in candidates if c]
    return max(candidates) if candidates else None

def trading_days_between(earlier: str, later: str) -> int:
    """两个日期之间经过的工作日数（近似，不含节假日扣除）。"""
    try:
        d0 = datetime.strptime(earlier, "%Y-%m-%d")
        d1 = datetime.strptime(later, "%Y-%m-%d")
    except ValueError:
        return -1
    if d1 < d0:
        return 0
    count, d, step = 0, d0, timedelta(days=1)
    while d < d1:
        d += step
        if d.weekday() < 5:
            count += 1
    return count

def data_staleness_gate(asof_date: Optional[str], report_date: str,
                         max_lag_trading_days: int = 2) -> Dict[str, Any]:
    """行情新鲜度门槛（P3.5 第 3.4 节）。

    规则：
      - asof 无法确认 -> verdict=DATE_UNKNOWN，阻止基于价格的交易类建议
      - 落后 >= max_lag_trading_days 个交易日 -> verdict=STALE，阻止
        CONSIDER_ENTRY / CONSIDER_ADD / CONSIDER_REDUCE / CONSIDER_EXIT
      - 落后 1 个交易日以内 -> verdict=FRESH
    """
    if not asof_date:
        return {"verdict": "DATE_UNKNOWN", "asof_date": None, "report_date": report_date,
                "lag_trading_days": None, "blocking": True,
                "reason": "无法确认行情数据所属交易日，禁止基于价格产生交易类建议"}
    lag = trading_days_between(asof_date, report_date)
    if lag < 0:
        return {"verdict": "DATE_UNKNOWN", "asof_date": asof_date, "report_date": report_date,
                "lag_trading_days": None, "blocking": True,
                "reason": "日期解析失败，禁止基于价格产生交易类建议"}
    if lag >= max_lag_trading_days:
        return {"verdict": "STALE", "asof_date": asof_date, "report_date": report_date,
                "lag_trading_days": lag, "blocking": True,
                "reason": f"行情数据落后 {lag} 个交易日（数据所属 {asof_date}，报告日 {report_date}），"
                          f"禁止基于旧价格给出建仓/加仓/减仓/退出建议"}
    return {"verdict": "FRESH" if lag <= 1 else "FRESH", "asof_date": asof_date,
            "report_date": report_date, "lag_trading_days": lag, "blocking": False,
            "reason": f"行情数据所属 {asof_date}，落后 {lag} 个交易日，在可接受范围内"}

BLOCKING_ACTIONS = {"CONSIDER_ENTRY", "CONSIDER_ADD", "CONSIDER_REDUCE", "CONSIDER_EXIT"}

def apply_staleness_gate(action: Dict[str, Any], gate: Dict[str, Any]) -> Dict[str, Any]:
    """若数据过期/日期不明，将交易类行动建议降级为 OBSERVE 并记录原因。"""
    if not gate.get("blocking"):
        return action
    if action.get("action") not in BLOCKING_ACTIONS:
        return action
    gated = dict(action)
    gated["original_action"] = action.get("action")
    gated["action"] = "OBSERVE"
    gated["reason"] = (f"【数据新鲜度门槛】{gate.get('reason', '')}。"
                       f"原建议 {action.get('action')} 基于旧行情，降级为观察。")
    gated["staleness_blocked"] = True
    return gated
