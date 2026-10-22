#!/usr/bin/env python3
"""每日监测 CLI 入口。

流程：
  1. 抓价格与锚价偏离（fetch_realtime + anchor_status）
  2. 抓每只股票 2-3 条新闻（Search API）
  3. 构造 state，调用 JEV decision（jev_adapter.jev_yes_no）
  4. 生成 reports/monitor/YYYY-MM-DD.md

用法：
    python3 src/monitor/run.py                  # 真实运行
    python3 src/monitor/run.py --dry-run        # 只跑数据采集，不写报告
    python3 src/monitor/run.py --mock-jev       # JEV 用 mock
    python3 src/monitor/run.py --no-search      # 跳过新闻抓取
    python3 src/monitor/run.py --date 2026-10-22

不执行任何交易，只输出判断。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from monitor import data_collect, decide, market, report_writer, session_guard
from stock_codes import ALL_POOL

TZ = timezone(timedelta(hours=8))


def _now():
    return datetime.now(TZ)


def _print_step(n, total, title):
    print("[%d/%d] %s..." % (n, total, title))


def _dev_text(q):
    dev = q.get("deviation")
    if dev is None:
        return "N/A"
    return "%+.2f%%" % dev


def run(dry_run=False, mock_jev=False, no_search=False, report_date=None,
        update_anchor=True):
    """执行完整监测流程，返回结果字典。"""
    now = _now()
    report_date = report_date or now.strftime("%Y-%m-%d")
    total = 5

    _print_step(1, total, "抓取价格与锚价偏离")
    quotes = data_collect.collect_quotes(include_anchor_update=update_anchor)
    quotes = [q for q in quotes if q.get("code") != "ALL"]
    for q in quotes:
        print("  %s %s: %s (dev %s, %s)" % (
            q.get("code"), q.get("name"), q.get("price"),
            _dev_text(q), q.get("status")))

    _print_step(2, total, "构造大盘环境")
    mkt = market.build_market_context(quotes)
    print("  %s" % mkt.get("summary"))

    _print_step(3, total, "抓取新闻（Search API）")
    news_map = {}
    if no_search:
        for s in ALL_POOL:
            news_map[s.code] = {"code": s.code, "available": False,
                                 "status": "skipped", "items": [], "query": ""}
    else:
        for s in ALL_POOL:
            n = data_collect.fetch_news(s, limit=3)
            news_map[s.code] = n
            print("  %s %s: %d 条 (%s)" % (
                s.code, s.name, len(n.get("items", [])), n.get("status")))

    _print_step(4, total, "JEV 决策（AMD Clef）")
    stocks = []
    for s in ALL_POOL:
        q = next((x for x in quotes if x.get("code") == s.code), None)
        if q is None:
            q = {"code": s.code, "name": s.name, "price": None, "anchor": None,
                 "deviation": None, "status": "未抓到行情", "has_anchor": False}
        n = news_map.get(s.code, {"items": [], "status": "skipped"})
        d = decide.judge_stock(q, n, mkt, use_mock=mock_jev)
        stocks.append(d)
        entry = d["jev"]["entry"]
        print("  %s %s: %s (entry=%s)" % (
            s.code, s.name, d["action"],
            entry.get("answer") or entry.get("error_code")))

    _print_step(5, total, "生成监测报告")
    ts = next((q.get("timestamp") for q in quotes if q.get("timestamp")), None)
    result = {
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "report_date": report_date,
        "quote_timestamp": ts,
        "market": mkt,
        "stocks": stocks,
    }
    if dry_run:
        print("  [dry-run] 不写文件")
        return result

    content = report_writer.render(result)
    path = report_writer.save(content, report_date)
    print("  报告已保存：%s" % path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="A股医药池 + ETF 每日监测")
    parser.add_argument("--date", help="报告日期 YYYY-MM-DD（默认今天）")
    parser.add_argument("--dry-run", action="store_true", help="只跑采集，不写报告")
    parser.add_argument("--mock-jev", action="store_true", help="JEV 用 mock")
    parser.add_argument("--no-search", action="store_true", help="跳过新闻抓取")
    parser.add_argument("--no-anchor-update", action="store_true",
                        help="不更新 anchor_status.json 的 current/prev_close")
    parser.add_argument("--json", help="把结果 JSON 写到指定路径")
    parser.add_argument("--force", action="store_true",
                        help="交易时段内也强制运行（默认跳过）")
    parser.add_argument("--install-cron", action="store_true",
                        help="安装每日收盘后 crontab 条目")
    parser.add_argument("--yes", action="store_true",
                        help="配合 --install-cron 真正写入 crontab（默认仅预览）")
    args = parser.parse_args()

    print("=" * 60)
    print("A股医药持仓池 + ETF 每日监测")
    print("=" * 60)

    if args.install_cron:
        return install_cron(confirm=args.yes)

    status = session_guard.session_status()
    print("时段：%s（%s）" % (status["phase"], status["note"]))
    if status["in_trading_session"] and not args.force:
        print("处于连续竞价时段，按约定跳过监测（用 --force 可强制运行）。")
        return 0

    result = run(
        dry_run=args.dry_run,
        mock_jev=args.mock_jev,
        no_search=args.no_search,
        report_date=args.date,
        update_anchor=not args.no_anchor_update,
    )

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        print("JSON 已保存：%s" % args.json)

    print("=" * 60)
    print("完成（不执行任何交易）")
    return 0


CRON_MARKER = "# ── AI股票系统 daily monitor ──"
CRON_LINE = ("30 15 * * 1-5 cd /Users/xiashuang/AI-股票系统 && "
             "/usr/bin/python3 /Users/xiashuang/AI-股票系统/src/monitor/run.py "
             ">> /Users/xiashuang/AI-股票系统/scratch/daily_monitor.log 2>&1")


def install_cron(confirm: bool = False) -> int:
    """安装每日 15:30（交易日）收盘后 crontab 条目，幂等。

    注意：Codex heartbeat 自动化（automation a）已在收盘后执行同一流程。
    两者并跑会重复消耗 AMD JEV 额度并覆盖同一份报告，
    因此需要显式加 --yes 才真正写入 crontab。
    """
    import subprocess

    proc = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    current = proc.stdout if proc.returncode == 0 else ""
    if CRON_MARKER in current and CRON_LINE in current:
        print("Crontab 条目已存在。")
        return 0
    if not confirm:
        print("将安装 crontab（每交易日 15:30）：")
        print("  " + CRON_LINE)
        print("注意：Codex heartbeat 自动化已在收盘后执行同一流程，并跑会重复消耗 "
              "AMD JEV 额度。确认需要系统级兜底时再加 --yes。")
        return 0

    lines = current.rstrip("\n").splitlines()
    if CRON_MARKER not in lines:
        lines.append(CRON_MARKER)
    lines.append(CRON_LINE)
    new_cron = "\n".join(lines) + "\n"
    proc = subprocess.run(["crontab"], input=new_cron, text=True, capture_output=True)
    if proc.returncode != 0:
        print("安装 crontab 失败：%s" % proc.stderr, file=sys.stderr)
        return 1
    print("已安装 crontab：每交易日 15:30 运行监测")
    return 0


if __name__ == "__main__":
    sys.exit(main())
