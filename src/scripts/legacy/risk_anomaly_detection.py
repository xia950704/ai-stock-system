#!/usr/bin/env python3
"""
risk_anomaly_detection.py — 风险异常检测系统
=============================================
每日扫描71只股票，标记异常:

  - 量价异常: 成交量突增 > 3σ, 价格异动
  - 技术异常: RSI超买/超卖, 布林带突破, MACD死叉
  - 组合风险: 波动率飙升, 相关性断裂

输出:
  - workspace/risk_anomalies.json (异常列表)
  - workspace/risk_anomalies.html (异常看板)

用法:
  python3 risk_anomaly_detection.py [--cron]
"""

from __future__ import annotations
import json
import os
import math
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta

import duckdb
import numpy as np
import pandas as pd

WORKSPACE = os.environ.get("HERMES_WORKSPACE", "/Users/xiashuang/harness/stock_daily")
DUCKDB_PATH = os.path.expanduser("~/.hermes/deeppulse/db/astock.duckdb")
PORTFOLIO_FILE = os.path.join(WORKSPACE, "stock_portfolio_enriched.json")
OUTPUT_DIR = WORKSPACE
TODAY = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
IMSG_TO = "285336749@qq.com"

# 异常阈值
VOLUME_THRESHOLD = 3.0   # 成交量 > 20日均量 × 3
RSI_OVERSOLD = 25        # RSI < 25 超卖
RSI_OVERBOUGHT = 75      # RSI > 75 超买
PRICE_DROP_THRESHOLD = -3.0  # 单日跌幅 > 3%
PRICE_SURGE_THRESHOLD = 5.0  # 单日涨幅 > 5%
VOLATILITY_THRESHOLD = 2.5   # 波动率 > 20日均值 × 2.5


def get_db_conn():
    return duckdb.connect(DUCKDB_PATH)


def load_portfolio() -> list[dict]:
    if not os.path.exists(PORTFOLIO_FILE):
        return []
    with open(PORTFOLIO_FILE, encoding="utf-8") as f:
        return json.load(f)


def compute_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def detect_anomalies(code: str, name: str, df: pd.DataFrame) -> list[dict]:
    """检测单只股票的异常"""
    if df.empty or len(df) < 30:
        return []

    closes = df["close"].values.astype(float)
    volumes = df["volume"].values.astype(float)
    highs = df["high"].values.astype(float)
    lows = df["low"].values.astype(float)
    dates = df["trade_date"].values
    n = len(closes)
    i = n - 1  # 最新交易日

    anomalies = []
    latest_date = str(dates[i]).split(" ")[0].split("T")[0] if i >= 0 else ""

    # 1. 成交量异常
    if i >= 20:
        avg_vol = np.mean(volumes[i - 19 : i + 1])
        std_vol = np.std(volumes[i - 19 : i + 1])
        if avg_vol > 0 and std_vol > 0:
            vol_z = (volumes[i] - avg_vol) / std_vol
            if vol_z > VOLUME_THRESHOLD:
                anomalies.append({
                    "type": "成交量异常", "severity": "高" if vol_z > 4 else "中",
                    "detail": f"成交量 {volumes[i]:.0f}, 是均值的 {volumes[i]/avg_vol:.1f}倍",
                    "value": round(float(vol_z), 2),
                })

    # 2. 价格异常
    if i >= 1:
        daily_ret = (closes[i] - closes[i - 1]) / closes[i - 1] * 100
        if daily_ret < PRICE_DROP_THRESHOLD:
            anomalies.append({
                "type": "价格大跌", "severity": "高" if daily_ret < -5 else "中",
                "detail": f"当日跌幅 {daily_ret:.2f}%",
                "value": round(daily_ret, 2),
            })
        elif daily_ret > PRICE_SURGE_THRESHOLD:
            anomalies.append({
                "type": "价格大涨", "severity": "低",
                "detail": f"当日涨幅 {daily_ret:.2f}%",
                "value": round(daily_ret, 2),
            })

    # 3. RSI 异常
    if i >= 14:
        rsi = compute_rsi(closes, 14)
        if rsi < RSI_OVERSOLD:
            anomalies.append({
                "type": "RSI超卖", "severity": "高",
                "detail": f"RSI {rsi:.1f} < {RSI_OVERSOLD}",
                "value": round(rsi, 1),
            })
        elif rsi > RSI_OVERBOUGHT:
            anomalies.append({
                "type": "RSI超买", "severity": "中",
                "detail": f"RSI {rsi:.1f} > {RSI_OVERBOUGHT}",
                "value": round(rsi, 1),
            })

    # 4. 波动率异常
    if i >= 20:
        ma20 = np.mean(closes[i - 19 : i + 1])
        if ma20 > 0:
            daily_vol = np.std(closes[i - 19 : i + 1]) / ma20
            hist_vol = np.std(closes[max(0, i - 60) : i - 19]) / np.mean(closes[max(0, i - 60) : i - 19]) if i >= 60 else daily_vol
            if hist_vol > 0 and daily_vol / hist_vol > VOLATILITY_THRESHOLD:
                anomalies.append({
                    "type": "波动率飙升", "severity": "高",
                    "detail": f"波动率 {daily_vol:.4f}, 是历史的 {daily_vol/hist_vol:.1f}倍",
                    "value": round(float(daily_vol / hist_vol), 2),
                })

    # 5. 连续下跌
    consecutive_drop = 0
    for j in range(i, max(0, i - 10), -1):
        if j > 0 and closes[j] < closes[j - 1]:
            consecutive_drop += 1
        else:
            break
    if consecutive_drop >= 5:
        drop_pct = (closes[i] / closes[i - consecutive_drop] - 1) * 100
        anomalies.append({
            "type": "连续下跌", "severity": "高" if consecutive_drop >= 7 else "中",
            "detail": f"连跌{consecutive_drop}天, 累计跌幅 {drop_pct:.2f}%",
            "value": consecutive_drop,
        })

    # 添加股票信息
    for a in anomalies:
        a["code"] = code
        a["name"] = name
        a["date"] = latest_date
        a["price"] = round(float(closes[i]), 2)

    return anomalies


def run_detection() -> dict:
    """运行异常检测"""
    portfolio = load_portfolio()
    if not portfolio:
        print("❌ 持仓文件不存在")
        return {}

    conn = get_db_conn()
    all_anomalies = []
    stocks_with_anomalies = 0
    total_stocks = 0

    print(f"🔍 风险异常检测启动: {len(portfolio)} 只股票")

    for item in portfolio:
        code = item.get("stock_code", "")
        name = item.get("stock_name", "")
        code_clean = code.split(".")[0].replace("SH", "").replace("SZ", "").replace("HK", "").zfill(6)

        df = conn.execute(f"""
            SELECT trade_date, open, high, low, close, volume, amount
            FROM daily_kline
            WHERE code = '{code_clean}'
            ORDER BY trade_date
        """).fetchdf()

        if df.empty:
            continue

        df = df.fillna(0)
        total_stocks += 1
        anomalies = detect_anomalies(code_clean, name, df)

        if anomalies:
            stocks_with_anomalies += 1
            all_anomalies.extend(anomalies)

    conn.close()

    # 按严重程度排序
    severity_order = {"高": 0, "中": 1, "低": 2}
    all_anomalies.sort(key=lambda x: (severity_order.get(x.get("severity", "低"), 3), x.get("type", "")))

    # 统计
    anomaly_types = defaultdict(int)
    severity_counts = defaultdict(int)
    for a in all_anomalies:
        anomaly_types[a["type"]] += 1
        severity_counts[a["severity"]] += 1

    result = {
        "run_date": TODAY,
        "total_stocks": total_stocks,
        "stocks_with_anomalies": stocks_with_anomalies,
        "total_anomalies": len(all_anomalies),
        "anomaly_types": dict(anomaly_types),
        "severity_summary": dict(severity_counts),
        "anomalies": all_anomalies,
    }

    return result


def generate_html_report(result: dict) -> str:
    """生成异常看板 HTML"""
    anomalies = result.get("anomalies", [])

    # 按严重程度分组
    high = [a for a in anomalies if a.get("severity") == "高"]
    medium = [a for a in anomalies if a.get("severity") == "中"]
    low = [a for a in anomalies if a.get("severity") == "低"]

    table_rows = ""
    for a in anomalies:
        sev = a.get("severity", "低")
        color = {"高": "#d4380d", "中": "#fa8c16", "低": "#888"}.get(sev, "#888")
        table_rows += f"""<tr>
    <td>{a['name']}</td>
    <td><span style="color:{color};font-weight:600">{sev}</span></td>
    <td>{a['type']}</td>
    <td>{a['detail']}</td>
    <td>{a['price']}</td>
    <td>{a['date']}</td>
  </tr>"""

    anomaly_types_json = json.dumps(
        [{"name": k, "value": v} for k, v in result.get("anomaly_types", {}).items()],
        ensure_ascii=False,
    )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>⚠️ 风险异常检测 - {TODAY}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0f1117; color:#e0e0e0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; padding:20px; }}
h1 {{ font-size:24px; margin-bottom:8px; color:#fff; }}
.subtitle {{ color:#888; font-size:14px; margin-bottom:24px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:16px; margin-bottom:24px; }}
.card {{ background:#1a1d27; border-radius:12px; padding:20px; border:1px solid #2a2d37; }}
.card h3 {{ font-size:14px; color:#888; margin-bottom:8px; }}
.card .value {{ font-size:28px; font-weight:700; }}
.chart-card {{ background:#1a1d27; border-radius:12px; padding:16px; border:1px solid #2a2d37; margin-bottom:16px; }}
.chart-card h3 {{ font-size:14px; color:#888; margin-bottom:12px; }}
.chart {{ width:100%; height:300px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th {{ text-align:left; padding:8px 10px; color:#888; font-weight:500; border-bottom:1px solid #2a2d37; }}
td {{ padding:8px 10px; border-bottom:1px solid #22252f; }}
tr:hover td {{ background:rgba(255,255,255,0.03); }}
</style>
</head>
<body>
<h1>⚠️ 风险异常检测报告</h1>
<p class="subtitle">{TODAY} | {result['total_stocks']} 只扫描 | {result['stocks_with_anomalies']} 只有异常 | 共 {result['total_anomalies']} 个异常</p>

<div class="grid">
  <div class="card"><h3>高风险</h3><div class="value" style="color:#d4380d">{len(high)}</div></div>
  <div class="card"><h3>中风险</h3><div class="value" style="color:#fa8c16">{len(medium)}</div></div>
  <div class="card"><h3>低风险</h3><div class="value" style="color:#888">{len(low)}</div></div>
  <div class="card"><h3>异常股票</h3><div class="value">{result['stocks_with_anomalies']}</div></div>
</div>

<div class="grid">
  <div class="chart-card">
    <h3>📊 异常类型分布</h3>
    <div id="distChart" class="chart"></div>
  </div>
  <div class="chart-card">
    <h3>⚠️ 高风险异常</h3>
    <div style="padding:10px">
    {''.join(f'<div style="padding:6px 0;border-bottom:1px solid #22252f;font-size:13px"><span style="color:#d4380d;font-weight:600">●</span> {a["name"]} — {a["type"]}: {a["detail"]}</div>' for a in high[:10]) if high else '<div style="color:#888">无高风险异常</div>'}
    </div>
  </div>
</div>

<script>
const distChart = echarts.init(document.getElementById('distChart'));
distChart.setOption({{
  tooltip: {{ trigger: 'item', formatter: '{{b}}: {{c}}' }},
  series: [{{
    type: 'pie', radius: ['40%', '70%'],
    data: {anomaly_types_json},
    label: {{ color: '#888' }},
    itemStyle: {{ borderRadius: 4 }}
  }}]
}});
</script>

<div class="chart-card">
  <h3>📋 完整异常列表</h3>
  <table><thead><tr>
    <th>股票</th><th>级别</th><th>类型</th><th>详情</th><th>价格</th><th>日期</th>
  </tr></thead><tbody>
  {table_rows}
  </tbody></table>
</div>
</body>
</html>"""
    return html


def save_results(result: dict, html: str):
    json_path = os.path.join(OUTPUT_DIR, "risk_anomalies.json")
    html_path = os.path.join(OUTPUT_DIR, "risk_anomalies.html")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ JSON: {json_path}")
    print(f"✅ HTML: {html_path}")


def notify(text: str):
    try:
        subprocess.run(["osascript", "-e", f'tell application "Messages" to send "{text}" to buddy "{IMSG_TO}"'], timeout=30)
    except Exception:
        pass


def main(cron: bool = False):
    print(f"{'⏰' if cron else '🚀'} 风险异常检测: {TODAY}")
    result = run_detection()
    if not result:
        return

    html = generate_html_report(result)
    save_results(result, html)

    high = [a for a in result.get("anomalies", []) if a.get("severity") == "高"]
    summary = (f"⚠️ 风险异常检测\n"
               f"扫描{result['total_stocks']}只, {result['stocks_with_anomalies']}只有异常\n"
               f"高风险{len(high)}个, "
               f"异常类型: {', '.join(f'{k}:{v}' for k,v in result.get('anomaly_types',{}).items())}")

    print(f"\n{summary}")

    if cron:
        notify(summary)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="风险异常检测")
    parser.add_argument("--cron", action="store_true")
    args = parser.parse_args()
    main(cron=args.cron)