#!/usr/bin/env python3
"""
最小抓取入口（阶段 1 · 方案 C 骨架）
抓 P0 6 只 + ETF 512400 实时价（腾讯 API qt.gtimg.cn）。
输出：现价 / 前收 / 涨跌幅 / 时间戳 / 锚价偏离 / 状态。
只读抓取，不写任何文件；写盘由调用方决定。
"""
import json
import os
import sys
import urllib.request
from datetime import datetime

# P0 6 只 + ETF 512400（口径来源：00-系统/个人上下文卡.md 场景 1）
SYMBOLS = {
    "sh600276": "恒瑞医药",
    "sz000963": "华东医药",
    "sz002262": "恩华药业",
    "sz002422": "科伦药业",
    "sh603259": "药明康德",
    "sh688506": "百利天恒",
    "sh512400": "512400ETF",
}

# 锚价权威源：默认 ~/harness/anchor_status.json，可用 DATA_ROOT 覆盖
DATA_ROOT = os.path.expanduser(os.environ.get("DATA_ROOT", "~/harness"))
ANCHOR_PATH = os.path.join(DATA_ROOT, "anchor_status.json")


def fetch(symbols):
    url = "https://qt.gtimg.cn/q=" + ",".join(symbols)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        raw = r.read().decode("gbk", errors="replace")
    out = {}
    for line in raw.strip().split("\n"):
        if "=" not in line:
            continue
        var, val = line.split("=", 1)
        sym = var.strip().lstrip("v_")
        if sym not in symbols:
            continue
        fields = val.strip().strip('"').split("~")
        if len(fields) < 4:
            continue
        out[sym] = {
            "name": fields[1],
            "code": fields[2],
            "price": float(fields[3]),
            "prev_close": float(fields[4]) if fields[4] else None,
            "timestamp": fields[30] if len(fields) > 30 and fields[30] else None,
            "change_pct": float(fields[32]) if len(fields) > 32 and fields[32] else None,
        }
    return out


def deviation_status(deviation):
    """锚价偏离判断规则（阶段 1 拍板口径）"""
    if deviation is None:
        return "无锚价"
    if deviation < -5:
        return "买入区间"
    if deviation < 0:
        return "偏低估"
    if deviation <= 5:
        return "合理"
    if deviation <= 10:
        return "偏高"
    return "超买"


def load_anchors():
    with open(ANCHOR_PATH) as f:
        data = json.load(f)
    return {d["code"]: d for d in data}


def main():
    anchors = load_anchors()
    prices = fetch(SYMBOLS)
    rows = []
    for sym, name in SYMBOLS.items():
        p = prices.get(sym)
        if not p:
            rows.append({"code": sym, "name": name, "error": "未抓到"})
            continue
        a = anchors.get(sym)
        anchor = a.get("anchor") if a else None
        deviation = None
        if anchor and p["price"]:
            deviation = round((p["price"] - anchor) / anchor * 100, 2)
        rows.append({
            "code": sym,
            "name": p["name"],
            "price": p["price"],
            "prev_close": p["prev_close"],
            "change_pct": p["change_pct"],
            "timestamp": p["timestamp"],
            "anchor": anchor,
            "deviation": deviation,
            "status": deviation_status(deviation),
        })
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
