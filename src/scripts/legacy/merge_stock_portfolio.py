#!/usr/bin/env python3
"""
merge_stock_portfolio.py
Merge 71 monitored stocks (JSONL) with DuckDB daily_kline data.
Output: enriched DuckDB table `stock_portfolio` + JSON export.
"""

import json
import re
import os
from datetime import date, timedelta
from collections import Counter

import duckdb

# ── Paths ──────────────────────────────────────────────────────────────────
JSONL_PATH = "/Users/xiashuang/obsidian/all about xia/01-股票投研/data/standardized/stocks.jsonl"
DB_PATH = "/Users/xiashuang/.hermes/deeppulse/db/astock.duckdb"
JSON_OUT = os.environ.get("HERMES_WORKSPACE", "/Users/xiashuang/harness/stock_daily") + "/stock_portfolio_enriched.json"

# ── Helpers ────────────────────────────────────────────────────────────────
def parse_range(s):
    """Parse '45-47元' / '55-60' → (45.0, 47.0), or None."""
    if not s:
        return None
    nums = re.findall(r"[\d.]+", s)
    if len(nums) >= 2:
        return float(nums[0]), float(nums[1])
    return None


def strip_suffix(code):
    """'603392.SH' → '603392', None → None"""
    if code is None:
        return None
    return code.split(".")[0].strip()


def load_jsonl(path):
    stocks = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                stocks.append(json.loads(line))
    return stocks


def today_str():
    return date.today().isoformat()


# ── Main ───────────────────────────────────────────────────────────────────
def main():
    stocks = load_jsonl(JSONL_PATH)
    print(f"Loaded {len(stocks)} stocks from JSONL")

    con = duckdb.connect(DB_PATH)

    # Latest reference date in daily_kline
    max_date = con.execute("SELECT MAX(trade_date) FROM daily_kline").fetchone()[0]
    print(f"Latest trade_date in daily_kline: {max_date}")

    # Build lookup dict: code → latest row + stats
    latest = {}
    for row in con.execute(
        "SELECT code, trade_date, open, high, low, close, volume, amount, turnover "
        "FROM daily_kline WHERE trade_date = (SELECT MAX(trade_date) FROM daily_kline) "
        "ORDER BY code"
    ).fetchall():
        code = row[0]
        latest[code] = {
            "trade_date": row[1],
            "latest_open": row[2],
            "latest_high": row[3],
            "latest_low": row[4],
            "latest_close": row[5],
            "latest_volume": row[6],
            "latest_amount": row[7],
            "latest_turnover": row[8],
        }

    print(f"Found {len(latest)} unique codes at latest date ({max_date})")

    # Pre-compute per-code stats: 5-day avg volume, 20-day range, price change 5/10/20d
    def pct(a, b):
        """(b - a) / a * 100"""
        if a is None or a == 0:
            return None
        return round((b - a) / a * 100, 2)

    stats = {}
    for row in con.execute(
        """
        WITH ranked AS (
            SELECT code, trade_date, close, volume, high, low,
                   ROW_NUMBER() OVER (PARTITION BY code ORDER BY trade_date DESC) AS rn
            FROM daily_kline
        )
        SELECT code,
               AVG(volume) FILTER (WHERE rn <= 5) AS vol5_avg,
               MIN(low) FILTER (WHERE rn <= 20) AS r20_low,
               MAX(high) FILTER (WHERE rn <= 20) AS r20_high,
               MAX(close) FILTER (WHERE rn = 1) AS c1,
               MAX(close) FILTER (WHERE rn = 2) AS c2,
               MAX(close) FILTER (WHERE rn = 6) AS c6,
               MAX(close) FILTER (WHERE rn = 11) AS c11,
               MAX(close) FILTER (WHERE rn = 21) AS c21
        FROM ranked
        GROUP BY code
        """
    ).fetchall():
        code = row[0]
        c1, c6, c11, c21 = row[5], row[6], row[7], row[8]
        stats[code] = {
            "vol5_avg": row[1],
            "r20_low": row[2],
            "r20_high": row[3],
            "chg_5d_pct": pct(c6, c1),
            "chg_10d_pct": pct(c11, c1),
            "chg_20d_pct": pct(c21, c1),
        }

    # ── Build portfolio rows ─────────────────────────────────────────────
    merged_count = 0
    missing_count = 0
    portfolio = []

    for s in stocks:
        code_full = s.get("stock_code", "")
        code = strip_suffix(code_full)
        exchange = s.get("exchange", "")

        d = latest.get(code)
        if d:
            merged_count += 1
        else:
            missing_count += 1

        buy_r = parse_range(s.get("buy_range"))
        sell_r = parse_range(s.get("sell_range"))
        cp = d["latest_close"] if d else s.get("current_price")

        # Range position
        buy_in = None
        sell_in = None
        if buy_r and cp is not None:
            buy_in = buy_r[0] <= cp <= buy_r[1]
        if sell_r and cp is not None:
            sell_in = sell_r[0] <= cp <= sell_r[1]

        # Days since last update (in JSONL `updated` field)
        days_since = None
        upd = s.get("updated")
        if upd:
            try:
                u = date.fromisoformat(upd)
                days_since = (date.today() - u).days
            except Exception:
                pass

        port = {
            "stock_name": s.get("stock_name"),
            "stock_code": code_full,
            "exchange": exchange,
            "sector": s.get("sector"),
            "status": s.get("status"),
            "position": s.get("position"),
            "jsonl_current_price": s.get("current_price"),
            "pe_ttm": s.get("pe_ttm"),
            "pb": s.get("pb"),
            "buy_range_raw": s.get("buy_range"),
            "sell_range_raw": s.get("sell_range"),
            "buy_low": buy_r[0] if buy_r else None,
            "buy_high": buy_r[1] if buy_r else None,
            "sell_low": sell_r[0] if sell_r else None,
            "sell_high": sell_r[1] if sell_r else None,
            "in_buy_range": buy_in,
            "in_sell_range": sell_in,
            "event_count": s.get("event_count"),
            "days_since_update": days_since,
            "has_kline_data": bool(d),
            # K-line fields (null if no data)
            "trade_date": d.get("trade_date") if d else None,
            "latest_open": d.get("latest_open") if d else None,
            "latest_high": d.get("latest_high") if d else None,
            "latest_low": d.get("latest_low") if d else None,
            "latest_close": d.get("latest_close") if d else None,
            "latest_volume": d.get("latest_volume") if d else None,
            "latest_amount": d.get("latest_amount") if d else None,
            "latest_turnover": d.get("latest_turnover") if d else None,
            # Stats
            "vol5_avg": stats.get(code, {}).get("vol5_avg"),
            "r20_low": stats.get(code, {}).get("r20_low"),
            "r20_high": stats.get(code, {}).get("r20_high"),
            "chg_5d_pct": stats.get(code, {}).get("chg_5d_pct"),
            "chg_10d_pct": stats.get(code, {}).get("chg_10d_pct"),
            "chg_20d_pct": stats.get(code, {}).get("chg_20d_pct"),
        }
        portfolio.append(port)

    print(f"\nMerge summary: {merged_count} matched, {missing_count} missing K-line data (total {len(stocks)})")

    # ── Write DuckDB table ────────────────────────────────────────────────────
    # Build schema: all fields as VARCHAR for flexibility (mix of str/int/float/None)
    columns = list(portfolio[0].keys())
    cols_schema = ", ".join(f"{c} VARCHAR" for c in columns)
    cols_str = ", ".join(columns)
    ph_str = ", ".join(["?"] * len(columns))
    con.execute(f"DROP TABLE IF EXISTS stock_portfolio")
    con.execute(f"CREATE TABLE stock_portfolio ({cols_schema})")
    for row in portfolio:
        vals = [str(row[c]) if row[c] is not None else None for c in columns]
        con.execute(f"INSERT INTO stock_portfolio ({cols_str}) VALUES ({ph_str})", vals)
    cnt = con.execute("SELECT COUNT(*) FROM stock_portfolio").fetchone()[0]
    print(f"Created DuckDB table `stock_portfolio` with {cnt} rows")

    # ── JSON export ───────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(JSON_OUT), exist_ok=True)
    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump(portfolio, f, ensure_ascii=False, indent=2, default=str)
    print(f"Wrote enriched JSON: {JSON_OUT}")

    # ── Sample output ─────────────────────────────────────────────────────
    print("\n─── Sample rows (matched with K-line data) ───")
    shown = 0
    for p in portfolio:
        if p["has_kline_data"]:
            show = {
                "name": p["stock_name"],
                "code": p["stock_code"],
                "close": p["latest_close"],
                "chg_5d": p["chg_5d_pct"],
                "chg_10d": p["chg_10d_pct"],
                "chg_20d": p["chg_20d_pct"],
                "vol5_avg": round(p["vol5_avg"], 0) if p.get("vol5_avg") else None,
                "in_buy": p["in_buy_range"],
                "in_sell": p["in_sell_range"],
                "sector": p["sector"],
            }
            print(f"  {show}")
            shown += 1
            if shown >= 5:
                break

    print("\n─── Missing stocks (no K-line data) ───")
    miss_shown = 0
    for p in portfolio:
        if not p["has_kline_data"]:
            print(f"  {p['stock_name']} ({p['stock_code']}, {p['exchange']}) — jsonl price={p['jsonl_current_price']}")
            miss_shown += 1
            if miss_shown >= 5:
                print("  ...")
                break

    # ── Sector breakdown ──────────────────────────────────────────────────
    sec = Counter(p["sector"] for p in portfolio)
    print(f"\nSector breakdown: {dict(sec.most_common())}")

    con.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
