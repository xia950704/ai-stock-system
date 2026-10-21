#!/usr/bin/env python3
"""
模拟投资盈亏计算 - 精确版 v2
直接用投入金额计算盈亏，不模拟股数（模拟投资无需考虑100股最小单位）。
"""

# === 资金分类：独立试仓 ===
# 本模拟归入"短线试仓"分类，独立于投研长线体系核算。
# 规则：单笔≤5,000元，强制止盈止损，盈亏不影响投研持有判断。
# 与DeepPulse技术面信号系统联动，但结果不作为投研有效性评估依据。

import json
import urllib.request
import sys

# ===== 持仓配置 =====
HOLDINGS = [
    {"name": "TCL中环", "code": "002129", "symbol": "sz002129", "invested": 8000, "buy_price": 11.19, "target": 13.30, "stop_loss": 10.17},
    {"name": "广合科技", "code": "001389", "symbol": "sz001389", "invested": 7000, "buy_price": 220.88, "target": 245.00, "stop_loss": 190.00},
    {"name": "铖昌科技", "code": "001270", "symbol": "sz001270", "invested": 5000, "buy_price": 139.43, "target": 148.00, "stop_loss": 126.00},
]

TOTAL_INVESTED = sum(h["invested"] for h in HOLDINGS)


def fetch_price(symbol):
    """通过腾讯财经 API 获取实时/收盘价"""
    try:
        url = f"https://qt.gtimg.cn/q={symbol}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        # 格式: v=sz002129~TCL中环~10.37~...
        parts = text.split("~")
        if len(parts) > 3:
            return float(parts[3])
    except Exception as e:
        print(f"[WARN] 获取 {symbol} 价格失败: {e}", file=sys.stderr)
    return None


def main():
    print(f"📊 模拟投资监控 [精确版]")
    print("━" * 40)

    total_pnl = 0.0

    for h in HOLDINGS:
        price = fetch_price(h["symbol"])
        if price is None:
            print(f"{h['name']}: 数据获取失败")
            continue

        # 直接用投入金额计算盈亏（模拟投资，不考虑100股最小单位）
        pnl_pct = (price - h["buy_price"]) / h["buy_price"]
        pnl = h["invested"] * pnl_pct

        total_pnl += pnl

        # 信号判断
        signal = ""
        if price >= h["target"]:
            signal = " ✅目标已达标"
        elif price <= h["stop_loss"]:
            signal = " ⚠️已触止损"

        print(f"{h['name']}: {h['buy_price']} → {price:.2f} | 盈亏{pnl:+.2f}元 | {pnl_pct*100:+.1f}%{signal}")

    total_pct = total_pnl / TOTAL_INVESTED
    print("━" * 40)
    print(f"总投入: {TOTAL_INVESTED}元")
    print(f"总盈亏: {total_pnl:+.2f}元 | {total_pct*100:+.1f}%")
    print("━" * 40)

    # JSON 输出供 cron 解析
    result = {
        "total_invested": TOTAL_INVESTED,
        "total_pnl": round(total_pnl, 2),
        "total_pct": round(total_pct * 100, 2),
    }
    print(f"\n[JSON]{json.dumps(result, ensure_ascii=False)}")

    return total_pnl


if __name__ == "__main__":
    main()
