#!/usr/bin/env python3
"""
fetch_kline_tencent_incremental.py -- 腾讯 K 线增量追加
===========================================================
只拉最近 60 个交易日，按日期去重 upsert。替代 baostock/东财每日增量。
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime

import duckdb

DB_PATH = os.path.expanduser("~/.hermes/deeppulse/db/astock.duckdb")

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "*/*",
    "Referer": "https://quote.eastmoney.com/",
    "Connection": "close",
}

def sym_of(code):
    c = str(code).zfill(6)
    if c[0] in ("5", "6", "9"):
        return "sh" + c
    return "sz" + c

def em_kline(sym, count=60, retries=5, timeout=10):
    """腾讯 fqkline：最近 N 条"""
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,,,{count},qfq"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*", "Referer": "https://quote.eastmoney.com/", "Connection": "close"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
            if d.get("code") != 0:
                raise RuntimeError(f"tencent code={d.get('code')} msg={d.get('msg')}")
            data = (d.get("data") or {}).get(sym, {})
            return data.get("qfqday") or data.get("day") or []
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(1.0 * (attempt + 1))

def parse_kline(kl):
    p = kl if isinstance(kl, list) else str(kl).split(",")
    if len(p) < 6:
        return None
    return {
        "trade_date": p[0],
        "open": float(p[1]),
        "close": float(p[2]),
        "high": float(p[3]),
        "low": float(p[4]),
        "volume": float(p[5]),
        "amount": None,
        "turnover": None,
    }

def main():
    dry = "--dry-run" in sys.argv

    con = duckdb.connect(os.path.expanduser("~/.hermes/deeppulse/db/astock.duckdb"))
    codes = [r[0] for r in con.execute("SELECT DISTINCT code FROM daily_kline ORDER BY code").fetchall()]
    print(f"target codes: {len(codes)}")

    total_rows = 0
    failed = []
    for idx, code in enumerate(codes, 1):
        sym = "sh" + code.zfill(6) if code[0] in "569" else "sz" + code.zfill(6)
        # 取 DB 最大日期
        max_date = con.execute(f"SELECT max(trade_date) FROM daily_kline WHERE code = '{code}'").fetchone()[0]
        if max_date is None:
            max_date = "2020-01-01"
        print(f"[{idx}/{len(codes)}] {code} max_date={max_date}", end=" ")

        try:
            klines = em_kline(sym, count=90)  # 90 条够覆盖到 max_date
        except Exception as e:
            print(f" ERR {e}")
            failed.append(code)
            continue

        if not klines:
            failed.append(code)
            continue

        rows = []
        for k in klines:
            d = parse_kline(k)
            if d:
                d["code"] = code
                rows.append(d)

        # 只保留 > max_date 的
        if max_date:
            max_date_str = str(max_date)
            rows = [r for r in rows if r["trade_date"] > max_date_str]

        if not rows:
            print(f" 无新数据")
            continue

        seen = {}
        for r in rows:
            key = (r["code"], r["trade_date"])
            seen[key] = r
        rows = list(seen.values())

        if not rows:
            print(f" 无新数据")
            continue

        if not dry:
            params = [(r["code"], r["trade_date"], r["open"], r["close"], r["high"],
                       r["low"], r["volume"], r["amount"], r["turnover"]) for r in rows]
            con.executemany(
                "INSERT INTO daily_kline (code, trade_date, open, close, high, low, "
                "volume, amount, turnover) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                params,
            )
            con.commit()
        total_rows += len(rows)
        print(f" +{len(rows)} rows, latest={rows[-1]['trade_date']}")

    con.close()
    print(f"\nDONE: +{total_rows} rows, failed={failed}")

if __name__ == "__main__":
    main()
