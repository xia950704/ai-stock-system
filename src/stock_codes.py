#!/usr/bin/env python3
"""集中式股票代码注册表（P0-1）。所有关注股票/ETF 的唯一真源。"""

from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass(frozen=True)
class StockEntry:
    code: str; name: str; market: str; pool: str; sector: str = ""
    @property
    def num(self) -> str: return self.code.lstrip("shzk")

P0_POOL = [
    StockEntry("sh600276", "恒瑞医药", "SH", "P0", "医药"),
    StockEntry("sz000963", "华东医药", "SZ", "P0", "医药"),
    StockEntry("sz002262", "恩华药业", "SZ", "P0", "化药"),
    StockEntry("sz002422", "科伦药业", "SZ", "P0", "医药"),
    StockEntry("sh603259", "药明康德", "SH", "P0", "医药外包"),
    StockEntry("sh688506", "百利天恒", "SH", "P0", "医药"),
    StockEntry("sh512400", "512400有色金属ETF", "SH", "P0", "ETF"),
]
P2_POOL = [StockEntry("sh688331", "荣昌生物", "SH", "P2", "医药")]
HK_POOL = [
    StockEntry("hk00570", "00570", "HK", "HK", ""),
    StockEntry("hk02162", "02162", "HK", "HK", ""),
    StockEntry("hk09926", "09926", "HK", "HK", ""),
]
ALL_POOL = P0_POOL + P2_POOL
ALL_STOCKS = P0_POOL + P2_POOL + HK_POOL
_BY_CODE = {s.code: s for s in ALL_STOCKS}

def get(code: str) -> Optional[StockEntry]:
    return _BY_CODE.get(_norm_code(code))

def _norm_code(code: str) -> str:
    c = str(code).strip().upper()
    if "." in c:
        prefix, num = c.split(".", 1)
        if prefix in ("SH","SZ","HK"): return prefix[:2].lower() + num
        if num in ("SH","SZ","HK"): return num[:2].lower() + prefix
    if c.startswith("SH"): return "sh" + c[2:]
    if c.startswith("SZ"): return "sz" + c[2:]
    if c.startswith("HK"): return "hk" + c[2:]
    if c.isdigit():
        if c.startswith(("6","9","5")): return "sh" + c
        if c.startswith(("0","3","2")): return "sz" + c
    return c

def all_judge_codes() -> List[str]: return [s.code for s in ALL_POOL]
def all_codes() -> List[str]: return [s.code for s in ALL_STOCKS]
P0_POOL_CODES = [s.code for s in P0_POOL]
P0_POOL_NAMES = {s.code: s.name for s in P0_POOL}
P2_POOL_CODES = [s.code for s in P2_POOL]
P2_POOL_NAMES = {s.code: s.name for s in P2_POOL}


def pool_codes(pool: str = "P0") -> list:
    pools = {"P0": P0_POOL, "P2": P2_POOL, "HK": HK_POOL}
    return [s.code for s in pools.get(pool, [])]


def all_judge_codes() -> list:
    return [s.code for s in ALL_POOL]


def all_codes() -> list:
    return [s.code for s in ALL_STOCKS]


def count_by_pool() -> dict:
    return {
        "P0": len(P0_POOL),
        "P2": len(P2_POOL),
        "HK": len(HK_POOL),
        "TOTAL": len(ALL_STOCKS),
    }
