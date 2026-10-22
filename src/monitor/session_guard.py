#!/usr/bin/env python3
"""A 股交易时段守卫：只在收盘后（或非交易日）允许运行监测。

交易时段（Asia/Shanghai）：
  09:30-11:30  上午连续竞价
  13:00-15:00  下午连续竞价
  11:30-13:00  午休
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

TZ = timezone(timedelta(hours=8))

MORNING_OPEN = 9 * 60 + 30
MORNING_CLOSE = 11 * 60 + 30
AFTERNOON_OPEN = 13 * 60
AFTERNOON_CLOSE = 15 * 60


def _minutes(d: datetime) -> int:
    return d.hour * 60 + d.minute


def session_status(reference: datetime = None) -> Dict[str, Any]:
    """返回当前所处时段。"""
    from engine.trading_day import trading_day_status

    d = reference or datetime.now(TZ)
    if d.tzinfo is None:
        d = d.replace(tzinfo=TZ)
    else:
        d = d.astimezone(TZ)

    t = _minutes(d)
    day = trading_day_status(d)
    is_trading_day = bool(day.get("likely_trading_day"))

    if not is_trading_day:
        phase = "non_trading_day"
        note = "非交易日（%s）" % day.get("note", "")
        in_session = False
    elif MORNING_OPEN < t < MORNING_CLOSE:
        phase = "morning_session"
        note = "上午连续竞价 09:30-11:30"
        in_session = True
    elif AFTERNOON_OPEN < t < AFTERNOON_CLOSE:
        phase = "afternoon_session"
        note = "下午连续竞价 13:00-15:00"
        in_session = True
    elif MORNING_CLOSE <= t <= AFTERNOON_OPEN:
        phase = "lunch_break"
        note = "午休 11:30-13:00"
        in_session = False
    elif t <= MORNING_OPEN:
        phase = "pre_open"
        note = "盘前 09:30 开盘前"
        in_session = False
    else:
        phase = "post_close"
        note = "收盘后 15:00 之后"
        in_session = False

    return {
        "datetime": d.strftime("%Y-%m-%d %H:%M:%S"),
        "phase": phase,
        "note": note,
        "in_trading_session": in_session,
        "is_trading_day": is_trading_day,
        "allow_run": not in_session,
    }


def is_trading_session(reference: datetime = None) -> bool:
    """是否处于连续竞价时段。"""
    return session_status(reference)["in_trading_session"]


def allow_run(reference: datetime = None) -> bool:
    """是否允许运行监测。"""
    return session_status(reference)["allow_run"]
