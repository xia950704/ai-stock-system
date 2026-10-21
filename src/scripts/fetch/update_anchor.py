#!/usr/bin/env python3
"""更新 anchor_status.json 到最新收盘（P0 6 只 + 512400，腾讯 API）。
只更新 current/prev_close/change_pct/pe；anchor 锚价不动（动态值，由用户维护）。
用法: python3 update_anchor.py [--dry-run]
"""
import json
import os
import shutil
import sys
import urllib.request

# 数据根目录：默认 ~/harness（本机布局），可用 DATA_ROOT 覆盖（如 P3 容器化部署）
DATA_ROOT = os.path.expanduser(os.environ.get("DATA_ROOT", "~/harness"))
ANCHOR_PATH = os.path.join(DATA_ROOT, "anchor_status.json")
BACKUP_PATH = os.path.join(DATA_ROOT, "backup_phase1", "anchor_status.pre_update.json")

# key=腾讯API代码, value=显示名
P0 = {
    "sh600276": "恒瑞医药",
    "sz000963": "华东医药",
    "sz002262": "恩华药业",
    "sz002422": "科伦药业",
    "sh603259": "药明康德",
    "sh688506": "百利天恒",
    "sh512400": "有色金属ETF南方",
}


def norm(code):
    """sh600276 / 600276 / sh.600276 -> 600276"""
    c = str(code).replace("sh.", "").replace("sz.", "")
    if c.startswith("sh") or c.startswith("sz"):
        c = c[2:]
    return c


def deviation_status(deviation):
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


def fetch():
    url = "https://qt.gtimg.cn/q=" + ",".join(P0)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        raw = r.read().decode("gbk", errors="replace")
    out = {}
    for line in raw.strip().split("\n"):
        if "=" not in line:
            continue
        var, val = line.split("=", 1)
        sym = var.strip().lstrip("v_")
        if sym not in P0:
            continue
        fields = val.strip().strip('"').split("~")
        if len(fields) < 4:
            continue
        out[sym] = {
            "name": fields[1],
            "price": float(fields[3]),
            "prev_close": float(fields[4]) if fields[4] else None,
            "change_pct": float(fields[32]) if len(fields) > 32 and fields[32] else None,
            "timestamp": fields[30] if len(fields) > 30 else None,
        }
    return out


def main():
    dry = "--dry-run" in sys.argv
    with open(ANCHOR_PATH) as f:
        asd = json.load(f)
    idx = {norm(d["code"]): d for d in asd}

    prices = fetch()
    print("fetched:", {k: v["price"] for k, v in prices.items()})

    changes = []
    for sym, name in P0.items():
        p = prices.get(sym)
        if not p:
            print("SKIP (no price):", sym); continue
        key = norm(sym)
        d = idx.get(key)
        if not d:
            print("SKIP (not in anchor_status):", sym, "key", key); continue
        old = dict(d)
        d["current"] = p["price"]
        d["prev_close"] = p["prev_close"]
        d["change_pct"] = p["change_pct"]
        if d.get("pe") is None:
            d["pe"] = old.get("pe")
        a = d.get("anchor")
        if a:
            d["deviation"] = round((p["price"] - a) / a * 100, 2)
        else:
            d["deviation"] = None
        d["status"] = deviation_status(d["deviation"])
        changes.append((sym, old, d))
        print(f"  {sym} {name}: current {old.get('current')} -> {p['price']} "
              f"anchor={a} dev={d['deviation']} status={d['status']}")

    if dry:
        print("DRY-RUN: no write")
        return

    shutil.copy2(ANCHOR_PATH, BACKUP_PATH)
    print("backup:", BACKUP_PATH)
    with open(ANCHOR_PATH, "w") as f:
        json.dump(asd, f, ensure_ascii=False, indent=2)
    print("wrote", ANCHOR_PATH, "total", len(asd))


if __name__ == "__main__":
    main()
