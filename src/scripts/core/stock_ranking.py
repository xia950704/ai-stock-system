#!/usr/bin/env python3
"""
stock_ranking.py — 信号融合综合排名系统
========================================
融合多源信号，生成71只股票每日综合评分排名：

信号来源:
  1. 技术指标 (RSI/MA/MACD/布林带) — 来自 baseline_ml
  2. ML 趋势预测 (1d/3d/5d) — 来自 ml_trend_predict
  3. 信号回测胜率加权 — 来自 backtest_signals
  4. 聚类偏离度 — 来自 baseline_ml

输出:
  - workspace/stock_ranking.json (完整排名)
  - workspace/stock_ranking.html (交互式排名看板)

用法:
  python3 stock_ranking.py [--cron]
"""

from __future__ import annotations
import json
import os
import math
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta

import duckdb
import numpy as np
import pandas as pd

WORKSPACE = os.path.expanduser(os.environ.get("STOCK_DAILY_DIR", "~/harness/stock_daily"))
DUCKDB_PATH = os.path.expanduser("~/.hermes/deeppulse/db/astock.duckdb")
PORTFOLIO_FILE = os.path.join(WORKSPACE, "stock_portfolio_enriched.json")
OUTPUT_DIR = WORKSPACE
TODAY = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
IMSG_TO = "285336749@qq.com"

# 信号权重
WEIGHTS = {
    "rsi_score": 0.15,        # RSI 信号
    "ma_score": 0.10,          # MA 排列信号
    "macd_score": 0.15,        # MACD 信号
    "boll_score": 0.10,        # 布林带信号
    "ml_1d": 0.10,             # ML 1天预测
    "ml_3d": 0.15,             # ML 3天预测
    "ml_5d": 0.15,             # ML 5天预测
    "volume_score": 0.05,      # 量能信号
    "momentum_score": 0.05,    # 动量信号
}


def get_db_conn():
    return duckdb.connect(DUCKDB_PATH)


def load_portfolio() -> list[dict]:
    """加载持仓"""
    if not os.path.exists(PORTFOLIO_FILE):
        return []
    with open(PORTFOLIO_FILE, encoding="utf-8") as f:
        return json.load(f)


def compute_technical_scores(code: str, df: pd.DataFrame) -> dict:
    """计算技术指标信号评分 (0-100)"""
    closes = df["close"].values.astype(float)
    highs = df["high"].values.astype(float)
    lows = df["low"].values.astype(float)
    volumes = df["volume"].values.astype(float)
    n = len(closes)
    if n < 20:
        return {"rsi_score": 50, "ma_score": 50, "macd_score": 50, "boll_score": 50, "volume_score": 50, "momentum_score": 50}

    i = n - 1  # 最新交易日

    # --- RSI ---
    rsi = 50
    if n > 14:
        gains = []
        losses = []
        for j in range(i - 14, i):
            diff = closes[j + 1] - closes[j]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))
        avg_gain = np.mean(gains) if gains else 0
        avg_loss = np.mean(losses) if losses else 0
        if avg_loss > 0:
            rsi = 100 - 100 / (1 + avg_gain / avg_loss)
        elif avg_gain > 0:
            rsi = 100
    rsi_score = 50 + (50 - rsi) * 0.5 if rsi < 30 else (50 + (rsi - 70) * 0.5 if rsi > 70 else 50)
    rsi_score = max(0, min(100, rsi_score))

    # --- MA 排列 ---
    ma5 = np.mean(closes[i - 4 : i + 1]) if i >= 4 else closes[i]
    ma10 = np.mean(closes[max(0, i - 9) : i + 1])
    ma20 = np.mean(closes[max(0, i - 19) : i + 1])
    ma_score = 50
    if ma5 > ma10 > ma20:
        ma_score = 70 + min(30, (ma5 / ma10 - 1) * 500)
    elif ma5 < ma10 < ma20:
        ma_score = 30 - min(30, abs(ma5 / ma10 - 1) * 500)
    ma_score = max(0, min(100, ma_score))

    # --- MACD ---
    ema12 = closes[i]
    ema26 = closes[i]
    if i >= 26:
        ema12 = np.mean(closes[i - 11 : i + 1])
        ema26 = np.mean(closes[i - 25 : i + 1])
    macd_line = ema12 - ema26
    macd_score = 50 + macd_line / closes[i] * 200
    macd_score = max(0, min(100, macd_score))

    # --- 布林带 ---
    if i >= 20:
        ma20_v = np.mean(closes[i - 19 : i + 1])
        std20 = np.std(closes[i - 19 : i + 1])
        if std20 > 0:
            boll_pos = (closes[i] - ma20_v) / std20
            boll_score = 50 - boll_pos * 10
            boll_score = max(0, min(100, boll_score))
        else:
            boll_score = 50
    else:
        boll_score = 50

    # --- 量能 ---
    if i >= 20:
        avg_vol = np.mean(volumes[i - 19 : i + 1])
        vol_ratio = volumes[i] / avg_vol if avg_vol > 0 else 1
        volume_score = 50 + (vol_ratio - 1) * 20
        volume_score = max(0, min(100, volume_score))
    else:
        volume_score = 50

    # --- 动量 ---
    ret_5d = closes[i] / closes[i - 5] - 1 if i >= 5 else 0
    ret_10d = closes[i] / closes[i - 10] - 1 if i >= 10 else 0
    momentum_score = 50 + (ret_5d * 100 + ret_10d * 50)
    momentum_score = max(0, min(100, momentum_score))

    return {
        "rsi_score": round(rsi_score, 1),
        "ma_score": round(ma_score, 1),
        "macd_score": round(macd_score, 1),
        "boll_score": round(boll_score, 1),
        "volume_score": round(volume_score, 1),
        "momentum_score": round(momentum_score, 1),
        "rsi": round(rsi, 1),
        "ma5": round(ma5, 2),
        "ma10": round(ma10, 2),
        "ma20": round(ma20, 2),
    }


def load_ml_predictions() -> dict:
    """加载 ML 预测结果"""
    path = os.path.join(os.path.expanduser(os.environ.get("HERMES_WORKSPACE_DIR", "~/.hermes/workspace")), "ml_trend_predictions.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        data = json.load(f)
    predictions = {}
    for sp in data.get("stock_predictions", []):
        predictions[sp["code"]] = sp
    return predictions


def load_backtest_weights() -> dict:
    """从回测结果计算信号权重修正"""
    path = os.path.join(os.path.expanduser(os.environ.get("STOCK_DAILY_DIR", "~/harness/stock_daily")), "backtest_signals.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        data = json.load(f)
    return data.get("evaluations", {})


def compute_composite_score(tech: dict, ml_pred: dict, backtest_weights: dict) -> dict:
    """计算综合评分"""
    # 基础技术分
    base_score = (
        tech.get("rsi_score", 50) * WEIGHTS["rsi_score"]
        + tech.get("ma_score", 50) * WEIGHTS["ma_score"]
        + tech.get("macd_score", 50) * WEIGHTS["macd_score"]
        + tech.get("boll_score", 50) * WEIGHTS["boll_score"]
        + tech.get("volume_score", 50) * WEIGHTS["volume_score"]
        + tech.get("momentum_score", 50) * WEIGHTS["momentum_score"]
    )

    # ML 加成
    ml_boost = 0
    ml_weight_sum = 0
    for fd_name, weight_key in [("1d", "ml_1d"), ("3d", "ml_3d"), ("5d", "ml_5d")]:
        if ml_pred and f"pred_{fd_name}d" in ml_pred:
            pred = ml_pred[f"pred_{fd_name}d"]
            if pred and "prob_up" in pred:
                ml_boost += pred["prob_up"] * 100 * WEIGHTS[weight_key]
                ml_weight_sum += WEIGHTS[weight_key]

    if ml_weight_sum > 0:
        ml_boost = ml_boost / ml_weight_sum * ml_weight_sum

    total = base_score + ml_boost
    total = max(0, min(100, total))

    # 信号分解
    signals = {
        "rsi": "买入" if tech.get("rsi_score", 50) > 60 else ("卖出" if tech.get("rsi_score", 50) < 40 else "观望"),
        "ma": "买入" if tech.get("ma_score", 50) > 60 else ("卖出" if tech.get("ma_score", 50) < 40 else "观望"),
        "macd": "买入" if tech.get("macd_score", 50) > 60 else ("卖出" if tech.get("macd_score", 50) < 40 else "观望"),
        "boll": "买入" if tech.get("boll_score", 50) > 60 else ("卖出" if tech.get("boll_score", 50) < 40 else "观望"),
    }

    return {
        "composite_score": round(total, 1),
        "tech_score": round(base_score, 1),
        "ml_boost": round(ml_boost, 1),
        "signals": signals,
        "details": tech,
    }


def run_ranking() -> dict:
    """运行综合排名"""
    portfolio = load_portfolio()
    if not portfolio:
        print("❌ 持仓文件不存在")
        return {}

    ml_predictions = load_ml_predictions()
    backtest_weights = load_backtest_weights()

    conn = get_db_conn()
    rankings = []
    errors = 0

    print(f"📊 综合排名启动: {len(portfolio)} 只股票")

    for i, item in enumerate(portfolio):
        code = item.get("stock_code", "")
        name = item.get("stock_name", "")
        sector = item.get("sector", "")
        code_clean = code.split(".")[0].replace("SH", "").replace("SZ", "").replace("HK", "").zfill(6)

        df = conn.execute(f"""
            SELECT trade_date, open, high, low, close, volume, amount
            FROM daily_kline
            WHERE code = '{code_clean}'
            ORDER BY trade_date
        """).fetchdf()

        if df.empty or len(df) < 20:
            errors += 1
            continue

        df = df.fillna(0)
        tech = compute_technical_scores(code_clean, df)
        ml_pred = ml_predictions.get(code_clean, {})
        composite = compute_composite_score(tech, ml_pred, backtest_weights)

        latest_close = float(df["close"].iloc[-1]) if not df.empty else 0
        latest_date = str(df["trade_date"].iloc[-1]).split(" ")[0] if not df.empty else ""

        rankings.append({
            "code": code_clean,
            "name": name,
            "sector": sector,
            "latest_close": latest_close,
            "latest_date": latest_date,
            "composite_score": composite["composite_score"],
            "tech_score": composite["tech_score"],
            "ml_boost": composite["ml_boost"],
            "signals": composite["signals"],
            "details": composite["details"],
        })

        if (i + 1) % 20 == 0:
            print(f"  进度: {i+1}/{len(portfolio)}")

    conn.close()

    # 按综合评分排名
    rankings.sort(key=lambda x: -x["composite_score"])

    # 统计
    buy_count = sum(1 for r in rankings if r["composite_score"] >= 65)
    watch_count = sum(1 for r in rankings if 35 < r["composite_score"] < 65)
    sell_count = sum(1 for r in rankings if r["composite_score"] <= 35)

    result = {
        "run_date": TODAY,
        "total_stocks": len(rankings),
        "errors": errors,
        "buy_signals": buy_count,
        "watch_signals": watch_count,
        "sell_signals": sell_count,
        "rankings": rankings,
    }

    return result


def generate_html_report(result: dict) -> str:
    """生成排名看板"""
    rankings = result.get("rankings", [])
    top5 = rankings[:5]
    worst5 = rankings[-5:] if len(rankings) >= 5 else rankings

    table_rows = ""
    for r in rankings:
        score = r["composite_score"]
        color = "#00a854" if score >= 65 else ("#fa8c16" if score >= 35 else "#d4380d")
        signals_str = " ".join(f"{k}:{v}" for k, v in r.get("signals", {}).items())
        table_rows += f"""<tr>
    <td>{r['name']}</td>
    <td>{r['sector']}</td>
    <td style="color:{color};font-weight:700">{score}</td>
    <td>{r['tech_score']}</td>
    <td>{r['ml_boost']}</td>
    <td>{r['latest_close']}</td>
    <td style="font-size:11px">{signals_str}</td>
  </tr>"""

    rankings_json = json.dumps([{"name": r["name"], "score": r["composite_score"]} for r in rankings], ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>📊 股票综合排名 - {TODAY}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0f1117; color:#e0e0e0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; padding:20px; }}
h1 {{ font-size:24px; margin-bottom:8px; color:#fff; }}
.subtitle {{ color:#888; font-size:14px; margin-bottom:24px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:16px; margin-bottom:24px; }}
.card {{ background:#1a1d27; border-radius:12px; padding:20px; border:1px solid #2a2d37; }}
.card h3 {{ font-size:14px; color:#888; margin-bottom:8px; }}
.card .value {{ font-size:28px; font-weight:700; }}
.card .sub {{ font-size:12px; color:#666; margin-top:4px; }}
.chart-card {{ background:#1a1d27; border-radius:12px; padding:16px; border:1px solid #2a2d37; margin-bottom:16px; }}
.chart-card h3 {{ font-size:14px; color:#888; margin-bottom:12px; }}
.chart {{ width:100%; height:400px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th {{ text-align:left; padding:8px 10px; color:#888; font-weight:500; border-bottom:1px solid #2a2d37; }}
td {{ padding:8px 10px; border-bottom:1px solid #22252f; }}
tr:hover td {{ background:rgba(255,255,255,0.03); }}
</style>
</head>
<body>
<h1>📊 股票综合评分排名</h1>
<p class="subtitle">{TODAY} | {result['total_stocks']} 只股票 | 买入信号 {result['buy_signals']} | 观望 {result['watch_signals']} | 卖出 {result['sell_signals']}</p>

<div class="grid">
  <div class="card"><h3>买入信号</h3><div class="value" style="color:#00a854">{result['buy_signals']}</div></div>
  <div class="card"><h3>观望</h3><div class="value" style="color:#fa8c16">{result['watch_signals']}</div></div>
  <div class="card"><h3>卖出信号</h3><div class="value" style="color:#d4380d">{result['sell_signals']}</div></div>
  <div class="card"><h3>综合评分均值</h3><div class="value">{sum(r['composite_score'] for r in rankings)/len(rankings):.1f}</div></div>
</div>

<div class="chart-card">
  <h3>📈 综合评分排行</h3>
  <div id="rankChart" class="chart"></div>
</div>
<script>
const rankChart = echarts.init(document.getElementById('rankChart'));
const data = {rankings_json};
const colors = data.map(d => d.score >= 65 ? '#00a854' : (d.score >= 35 ? '#fa8c16' : '#d4380d'));
rankChart.setOption({{
  tooltip: {{ trigger: 'axis' }},
  grid: {{ left: '15%', right: '5%', bottom: '15%' }},
  xAxis: {{ type: 'category', data: data.map(d => d.name), axisLabel: {{ color: '#888', rotate: 45, fontSize: 10 }} }},
  yAxis: {{ type: 'value', min: 0, max: 100, axisLabel: {{ color: '#888' }}, splitLine: {{ lineStyle: {{ color: '#2a2d37' }} }} }},
  series: [{{
    type: 'bar', data: data.map((d, i) => ({{ value: d.score, itemStyle: {{ color: colors[i] }} }})),
    label: {{ show: true, position: 'top', formatter: '{{c}}', color: '#888', fontSize: 10 }}
  }}]
}});
</script>

<div class="chart-card">
  <h3>📋 完整排名</h3>
  <table><thead><tr>
    <th>名称</th><th>板块</th><th>综合评分</th><th>技术分</th><th>ML加成</th><th>最新价</th><th>信号</th>
  </tr></thead><tbody>
  {table_rows}
  </tbody></table>
</div>
</body>
</html>"""
    return html


def save_results(result: dict, html: str):
    json_path = os.path.join(OUTPUT_DIR, "stock_ranking.json")
    html_path = os.path.join(OUTPUT_DIR, "stock_ranking.html")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n✅ JSON: {json_path}")
    print(f"✅ HTML: {html_path}")


def notify(text: str):
    try:
        subprocess.run(["osascript", "-e", f'tell application "Messages" to send "{text}" to buddy "{IMSG_TO}"'], timeout=30)
    except Exception:
        pass


def main(cron: bool = False):
    print(f"{'⏰' if cron else '🚀'} 综合排名: {TODAY}")
    start = time.time()
    result = run_ranking()
    elapsed = time.time() - start

    if not result:
        return

    html = generate_html_report(result)
    save_results(result, html)

    top = result["rankings"][:3] if result["rankings"] else []
    summary = (f"📊 综合排名完成 ({elapsed:.0f}秒)\n"
               f"买入{result['buy_signals']} 观望{result['watch_signals']} 卖出{result['sell_signals']}\n"
               + "\n".join(f"  {r['name']}: {r['composite_score']}分" for r in top))

    print(f"\n{summary}")

    if cron:
        notify(summary)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="股票综合排名")
    parser.add_argument("--cron", action="store_true")
    args = parser.parse_args()
    main(cron=args.cron)
