#!/usr/bin/env python3
"""
fetch_kline_tencent.py -- 腾讯 web.ifzq.gtimg.cn K 线全量重建
==============================================================
用腾讯 fqkline API 拉 A 股日 K 线（前复权），按年分段拉取，全量重建
DuckDB daily_kline 表。替换已停服的 baostock / 失效的东财 push2his。

字段：date, open, close, high, low, volume
- amount/turnover 缺失，保留 DB 旧值
- 科创板(688)只返回 day 键，用 day 代替 qfqday
- 分段：每年 1 次请求，每年 ~242 条，7 年 × 55 只 ≈ 385 请求
"""

import json
import os
import shutil
import sys
import time
import urllib.request
from datetime import datetime

import duckdb

DB_PATH = os.path.expanduser("~/.hermes/deeppulse/db/astock.duckdb")
BACKUP_PATH = os.path.expanduser("~/.hermes/deeppulse/db/astock.duckdb.bak_kline_tencent")

YEARS = [2020, 2021, 2022, 2023, 2024, 2025, 2026]

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "*/*",
    "Referer": "https://quote.eastmoney.com/",
    "Connection": "close",
}

def sym_of(code):
    """600276 -> sh600276, 000963 -> sz000963"""
    c = str(code).zfill(6)
    if c[0] in ("5", "6", "9"):
        return "sh" + c
    return "sz" + c

def em_kline(sym, beg, end, retries=5, timeout=10):
    """腾讯 fqkline：param=sym,day,beg,end,count,qfq"""
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?param={sym},day,{beg},{end},641,qfq")
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read().decode("utf-8", "replace")
            j = json.loads(raw)
            if j.get("code") != 0:
                raise RuntimeError(f"tencent code={j.get('code')} msg={j.get('msg')}")
            data = (j.get("data") or {}).get(sym, {})
            return data.get("qfqday") or data.get("day") or []
        except Exception as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last

def parse_kline(kl):
    """kline string -> dict matching daily_kline columns (no amount/turnover)."""
    p = kl.split(",")
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

    con = duckdb.connect(DB_PATH)
    codes = [r[0] for r in con.execute("SELECT DISTINCT code FROM daily_kline ORDER BY code").fetchall()]
    print(f"target codes: {len(codes)}")

    if not dry:
        shutil.copy2(DB_PATH, BACKUP_PATH)
        print("backup:", BACKUP_PATH)

    total_rows = 0
    failed = []
    for idx, code in enumerate(codes, 1):
        sym = sym_of(code)
        all_rows = []
        for year in YEARS:
            beg = f"{year}-01-01"
            end = f"{year}-12-31" if year < 2026 else datetime.now().strftime("%Y-%m-%d")
            try:
                klines = em_kline(sym, beg, end)
            except Exception as e:
                print(f"[ERR] {code} {sym} {year}: {e}")
                continue
            if not klines:
                continue
            for k in klines:
                d = parse_kline(k)
                if d:
                    d["code"] = code
                    all_rows.append(d)
            time.sleep(0.15)

        if not all_rows:
            failed.append((code, "no klines"))
            continue

        seen = {}
        for r in all_rows:
            key = (r["code"], r["trade_date"])
            seen[key] = r
        all_rows = list(seen.values())

        if not dry:
            con.execute("DELETE FROM daily_kline WHERE code = ?", [code])
            params = [(r["code"], r["trade_date"], r["open"], r["close"], r["high"],
                       r["low"], r["volume"], r["amount"], r["turnover"]) for r in all_rows]
            con.executemany(
                "INSERT INTO daily_kline (code, trade_date, open, close, high, low, "
                "volume, amount, turnover) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                params,
            )
        total_rows += len(all_rows)
        latest = max(r["trade_date"] for r in all_rows)
        print(f"[OK ] {code} {sym} n={len(all_rows)} latest={latest}")
        if idx % 10 == 0:
            print(f"      progress {idx}/{len(codes)} total_rows={total_rows}")

    if not dry:
        con.commit()
    con.close()
    print(f"\nDONE: {total_rows} rows upserted, {len(failed)} failed")
    if failed:
        print("failed:", failed)

if __name__ == "__main__":
    main()
