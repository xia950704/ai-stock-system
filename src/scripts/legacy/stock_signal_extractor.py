#!/usr/bin/env python3
"""
stock_signal_extractor.py — 从日报中提取结构化信号，存入 DuckDB
===================================
用法：
    python stock_signal_extractor.py [--date 2026-07-07]
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DB_PATH = os.path.expanduser("~/.hermes/deeppulse/db/astock.duckdb")
REPORT_DIR = os.path.expanduser(os.environ.get("STOCK_DAILY_DIR", "~/harness/stock_daily"))


def parse_signals(content):
    """从报告文本中提取所有信号条目"""
    # 匹配：🟡 百济神州(688235): 持有 | 评分 78 | 看多
    # 关键：([^()]+) 会匹配到换行，用 [^\n()] 限制单行
    pattern = r'([🟢🟡🔴⚪])\s*([^\n()]*)\((\d{6})\):\s*(.+?)\s*\|\s*评分\s*(\d+)\s*\|\s*(看多|看空|震荡|强烈看空|强烈看多)'
    signals = []
    for m in re.finditer(pattern, content):
        emoji, name, code, action_raw, score, direction = m.groups()
        # 从 action_raw 提取动作（去掉多余文字）
        action = action_raw.split("|")[0].strip()
        # 标准化动作
        action_map = {"持有": "hold", "观望": "watch", "买入": "buy", "卖出": "sell", "持有观察": "hold", "持有观察": "hold"}
        action_std = action_map.get(action, action.lower())
        signals.append({
            "stock_code": code,
            "stock_name": name.strip(),
            "action": action_std,
            "score": int(score),
            "direction": direction,
        })
    return signals


def extract_date(filename):
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', filename)
    if m:
        return m.group(0)
    m = re.search(r'(\d{8})', filename)
    if m:
        return f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}"
    return None


def process(filepath, dry_run=False):
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    date_str = extract_date(os.path.basename(filepath))
    signals = parse_signals(content)

    print(f"📄 {os.path.basename(filepath)}")
    print(f"   日期: {date_str} | 信号数: {len(signals)}")
    for s in signals[:3]:
        print(f"   - {s['stock_code']} {s['stock_name']}: {s['action']} | score={s['score']} | {s['direction']}")
    if len(signals) > 3:
        print(f"   ... 共 {len(signals)} 只")

    if dry_run:
        return signals, date_str

    # 写入 DuckDB
    import duckdb
    con = duckdb.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS stock_signals (
            signal_date VARCHAR NOT NULL,
            stock_code VARCHAR(6) NOT NULL,
            stock_name VARCHAR(64),
            action VARCHAR(16),
            score INTEGER,
            direction VARCHAR(16),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    for s in signals:
        con.execute("""
            INSERT INTO stock_signals (signal_date, stock_code, stock_name, action, score, direction)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [date_str, s["stock_code"], s["stock_name"], s["action"], s["score"], s["direction"]])

    # 统计
    row_count = con.execute("SELECT COUNT(*) FROM stock_signals").fetchone()[0]
    date_count = con.execute("SELECT COUNT(DISTINCT signal_date) FROM stock_signals").fetchone()[0]
    print(f"   ✅ 已入库，累计 {row_count} 条信号 / {date_count} 天")
    con.close()

    return signals, date_str


def main():
    parser = argparse.ArgumentParser(description="提取日报信号到DuckDB")
    parser.add_argument("--date", help="指定日期，如 2026-07-07")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    files = sorted([
        f for f in os.listdir(REPORT_DIR)
        if f.startswith("stock_report_") and f.endswith(".md")
    ])

    if args.date:
        files = [f for f in files if args.date.replace("-", "") in f or args.date in f]

    if not files:
        print(f"❌ 未找到报告文件 (dir={REPORT_DIR})")
        sys.exit(1)

    for f in files:
        process(os.path.join(REPORT_DIR, f), args.dry_run)


if __name__ == "__main__":
    main()
