#!/usr/bin/env python3
"""短期技术分析扫描工具 — 识别突破、超跌、放量候选股"""

import duckdb
import os
import json
import csv
import sys
import pandas as pd
from pathlib import Path
from collections import defaultdict

DB_PATH = "/Users/xiashuang/.hermes/deeppulse/db/astock.duckdb"
OUT_DIR = Path(os.environ.get("HERMES_WORKSPACE", "/Users/xiashuang/harness/stock_daily"))
SCAN_DATE = "2026-06-26"
JSONL_PATH = OUT_DIR / f"short_term_scan_{SCAN_DATE}.json"
CSV_PATH = OUT_DIR / f"short_term_scan_{SCAN_DATE}.csv"


def classify_sector(code: str) -> str:
    code = str(code).strip()
    if code.startswith("600") or code.startswith("601") or code.startswith("603") or code.startswith("605"):
        return "主板"
    elif code.startswith("000") or code.startswith("001") or code.startswith("002"):
        return "中小板"
    elif code.startswith("300") or code.startswith("301"):
        return "创业板"
    elif code.startswith("688"):
        return "科创板"
    else:
        return "其他"


def main():
    con = duckdb.connect(DB_PATH)

    # Determine latest trading date <= SCAN_DATE
    max_date = con.execute(
        "SELECT MAX(trade_date) FROM daily_kline WHERE trade_date <= ? AND close IS NOT NULL", [SCAN_DATE]
    ).fetchone()[0]
    print(f"[INFO] 最新交易日: {max_date}")
    if not max_date:
        print("[ERROR] 没有找到数据"); sys.exit(1)
    max_date = str(max_date)[:10]

    # One-pass query: compute per-stock 20d window (excluding today) + today's metrics
    sql = f"""
    WITH ranked AS (
        SELECT
            code, trade_date, close, high, low, volume,
            ROW_NUMBER() OVER (PARTITION BY code ORDER BY trade_date DESC) AS rn
        FROM daily_kline
        WHERE trade_date <= '{max_date}' AND close IS NOT NULL AND volume IS NOT NULL
    ),
    windows AS (
        SELECT
            code,
            -- 20d window EXCLUDING today: rows rn=2..21
            MAX(CASE WHEN rn BETWEEN 2 AND 21 THEN high END) AS h20,
            MIN(CASE WHEN rn BETWEEN 2 AND 21 THEN low END) AS l20,
            AVG(CASE WHEN rn BETWEEN 2 AND 21 THEN volume END) AS vol20,
            -- 5-day volume avg (yesterday + 4 days before = rn=2..6)
            AVG(CASE WHEN rn BETWEEN 2 AND 6 THEN volume END) AS vol5,
            -- max volume in last 10 days INCLUDING today
            MAX(CASE WHEN rn BETWEEN 1 AND 10 THEN volume END) AS vol10_max,
            -- today (rn=1)
            MAX(CASE WHEN rn = 1 THEN close END) AS close,
            MAX(CASE WHEN rn = 1 THEN volume END) AS tvol,
            MAX(CASE WHEN rn = 1 THEN trade_date END) AS dt,
            -- yesterday (rn=2)
            MAX(CASE WHEN rn = 2 THEN close END) AS prev_close,
            -- 5 days ago (rn=6) for trend
            MAX(CASE WHEN rn = 6 THEN close END) AS close_5ago
        FROM ranked
        GROUP BY code
        HAVING COUNT(CASE WHEN rn BETWEEN 2 AND 21 THEN 1 END) >= 20
    )
    SELECT *
    FROM windows
    WHERE dt = '{max_date}'
    """

    print("[INFO] 执行扫描查询...")
    df = con.execute(sql).fetchdf()
    print(f"[INFO] 共有 {len(df)} 只股票满足 20 日数据要求")

    candidates = []

    for _, r in df.iterrows():
        code = str(int(r['code'])) if not isinstance(r['code'], str) else str(r['code'])
        close = float(r['close'])
        prev_close = float(r['prev_close']) if pd.notna(r.get('prev_close')) else None
        h20 = float(r['h20'])
        l20 = float(r['l20'])
        vol20 = float(r['vol20'])
        vol5 = float(r['vol5']) if pd.notna(r.get('vol5')) else vol20
        vol10_max = float(r['vol10_max'])
        today_vol = float(r['tvol'])
        close_5ago = float(r['close_5ago']) if pd.notna(r.get('close_5ago')) else close

        # 5-day price trend
        if close_5ago > 0:
            trend_pct = (close / close_5ago - 1) * 100
            price_trend = 'up' if trend_pct > 2 else ('down' if trend_pct < -2 else 'flat')
        else:
            price_trend = 'flat'

        signals = []

        # 1. 突破 (Breakout): close > 20d_high * 1.02 AND volume > 2x 20d_avg_vol
        if h20 > 0 and close > h20 * 1.02:
            vol_ratio = today_vol / vol20 if vol20 > 0 else 0
            if vol_ratio > 2.0:
                pct = (close / h20 - 1) * 100
                signals.append({
                    "signal_type": "突破",
                    "close": close, "h20": round(h20, 2),
                    "pct_above_h20": round(pct, 2),
                    "vol_ratio": round(vol_ratio, 2),
                    "today_volume": int(today_vol), "vol20": round(vol20, 0),
                })

        # 2. 超跌反弹 (Oversold): close < 20d_low * 0.95 AND 5d_vol_avg > 20d_vol_avg
        if l20 > 0 and close < l20 * 0.95:
            vol5_ratio = vol5 / vol20 if vol20 > 0 else 0
            if vol5_ratio > 1.0:
                pct = (close / l20 - 1) * 100
                signals.append({
                    "signal_type": "超跌",
                    "close": close, "l20": round(l20, 2),
                    "pct_below_l20": round(pct, 2),
                    "vol5_ratio": round(vol5_ratio, 2),
                    "today_volume": int(today_vol), "vol5": round(vol5, 0), "vol20": round(vol20, 0),
                })

        # 3. 放量上涨 (Volume Surge): close > prev*1.05 AND vol > 1.5x*vol20 AND vol == max in 10d
        if prev_close and prev_close > 0:
            price_chg = (close / prev_close - 1) * 100
            vol_ratio = today_vol / vol20 if vol20 > 0 else 0
            if price_chg >= 5.0 and vol_ratio >= 1.5 and today_vol >= vol10_max:
                signals.append({
                    "signal_type": "放量",
                    "close": close, "prev_close": round(prev_close, 2),
                    "price_chg_pct": round(price_chg, 2),
                    "vol_ratio": round(vol_ratio, 2),
                    "today_volume": int(today_vol), "vol20": round(vol20, 0), "vol10_max": int(vol10_max),
                })

        for sig in signals:
            entry = {
                "stock_code": code,
                "latest_date": max_date,
                "latest_close": round(close, 2),
                "signal_type": sig["signal_type"],
                "price_trend_5d": price_trend,
                "sector": classify_sector(code),
                **sig
            }
            candidates.append(entry)

    # Write JSONL
    with open(JSONL_PATH, "w", encoding="utf-8") as f:
        for c in candidates:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"[INFO] JSONL 已保存: {JSONL_PATH} ({len(candidates)} 条)")

    # Normalize keys for CSV (union of all fields)
    all_keys = list(dict.fromkeys(k for c in candidates for k in c.keys())) if candidates else []
    # Canonical field order
    canonical = ["stock_code", "latest_date", "latest_close", "signal_type", "price_trend_5d", "sector",
                 "close", "h20", "pct_above_h20", "l20", "pct_below_l20", "prev_close", "price_chg_pct",
                 "vol_ratio", "vol5_ratio", "today_volume", "vol20", "vol5", "vol10_max"]
    used_keys = [k for k in canonical if k in all_keys]

    # Write CSV
    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        if candidates:
            writer = csv.DictWriter(f, fieldnames=used_keys, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(candidates)
        else:
            f.write("无候选股\n")
    print(f"[INFO] CSV 已保存: {CSV_PATH}")

    # Print top candidates
    by_type = defaultdict(list)
    for c in candidates:
        by_type[c["signal_type"]].append(c)

    print(f"\n{'='*80}")
    print(f"短期技术分析扫描结果 — 日期: {max_date}")
    print(f"总候选股: {len(candidates)} 只 (突破: {len(by_type['突破'])}, "
          f"超跌: {len(by_type['超跌'])}, 放量: {len(by_type['放量'])})")
    print(f"{'='*80}\n")

    for sig_type, label, sort_key in [
        ("突破", "🔺 突破候选", lambda x: -x.get("pct_above_h20", 0)),
        ("超跌", "🔻 超跌反弹候选", lambda x: x.get("pct_below_l20", 0)),
        ("放量", "🔥 放量上涨候选", lambda x: -x.get("price_chg_pct", 0)),
    ]:
        items = sorted(by_type.get(sig_type, []), key=sort_key)[:5]
        print(f"--- {label} (Top 5) ---")
        if not items:
            print("  (无)\n")
            continue
        for i, c in enumerate(items, 1):
            code = c["stock_code"]; sector = c["sector"]; trend = c["price_trend_5d"]
            close = c["latest_close"]
            if sig_type == "突破":
                detail = f"收盘{close} > 20日高{c['h20']:.2f} (+{c['pct_above_h20']}%), 量比{c['vol_ratio']}x"
            elif sig_type == "超跌":
                detail = f"收盘{close} < 20日低{c['l20']:.2f} ({c['pct_below_l20']}%), 5日量比{c['vol5_ratio']}x"
            else:
                detail = f"涨幅{c['price_chg_pct']}%, 量比{c['vol_ratio']}x (近10日最大)"
            print(f"  {i}. {code} ({sector}) 趋势:{trend} | {detail}")
        print()

    con.close()
    return candidates


if __name__ == "__main__":
    main()
