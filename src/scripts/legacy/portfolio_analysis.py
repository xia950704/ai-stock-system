#!/usr/bin/env python3
"""
portfolio_analysis.py — 持仓分析报告系统
=========================================
计算组合级风险指标:

  - 组合 β 值 (vs 沪深300)
  - 夏普比率
  - 最大回撤
  - VaR (在险价值)
  - 行业集中度
  - 相关性矩阵
  - 个股贡献度

输出:
  - workspace/portfolio_analysis.json (完整分析)
  - workspace/portfolio_analysis.html (报告看板)

用法:
  python3 portfolio_analysis.py [--cron]
"""

from __future__ import annotations
import json
import os
import math
import subprocess
import sys
from collections import defaultdict, Counter
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

RISK_FREE_RATE = 0.02  # 无风险利率 2%


def get_db_conn():
    return duckdb.connect(DUCKDB_PATH)


def load_portfolio() -> list[dict]:
    if not os.path.exists(PORTFOLIO_FILE):
        return []
    with open(PORTFOLIO_FILE, encoding="utf-8") as f:
        return json.load(f)


def compute_returns(prices: np.ndarray) -> np.ndarray:
    """计算日收益率序列"""
    if len(prices) < 2:
        return np.array([])
    return np.diff(prices) / prices[:-1]


def compute_sharpe(returns: np.ndarray, rf: float = RISK_FREE_RATE) -> float:
    """计算年化夏普比率"""
    if len(returns) < 10:
        return 0
    daily_rf = rf / 252
    excess = returns - daily_rf
    if np.std(returns) == 0:
        return 0
    return float(np.mean(excess) / np.std(returns) * np.sqrt(252))


def compute_max_drawdown(prices: np.ndarray) -> float:
    """计算最大回撤"""
    if len(prices) < 2:
        return 0
    peak = np.maximum.accumulate(prices)
    drawdown = (prices - peak) / peak
    return float(np.min(drawdown))


def compute_var(returns: np.ndarray, confidence: float = 0.95) -> float:
    """计算 VaR (历史模拟法)"""
    if len(returns) < 20:
        return 0
    return float(np.percentile(returns, (1 - confidence) * 100))


def compute_beta(stock_returns: np.ndarray, market_returns: np.ndarray) -> float:
    """计算 β 值"""
    if len(stock_returns) < 20 or len(market_returns) < 20:
        return 1.0
    min_len = min(len(stock_returns), len(market_returns))
    sr = stock_returns[-min_len:]
    mr = market_returns[-min_len:]
    if np.std(mr) == 0:
        return 1.0
    cov = np.cov(sr, mr)[0, 1]
    return float(cov / np.var(mr))


def run_analysis() -> dict:
    """运行持仓分析"""
    portfolio = load_portfolio()
    if not portfolio:
        print("❌ 持仓文件不存在")
        return {}

    conn = get_db_conn()

    # 获取沪深300作为基准
    # DuckDB 中没有沪深300数据，用持仓股票等权组合代替
    stock_data = {}
    sectors = Counter()
    industry_allocation = {}

    for item in portfolio:
        code = item.get("stock_code", "")
        name = item.get("stock_name", "")
        sector = item.get("sector", "")
        code_clean = code.split(".")[0].replace("SH", "").replace("SZ", "").replace("HK", "").zfill(6)

        if sector:
            sectors[sector] += 1

        df = conn.execute(f"""
            SELECT trade_date, close
            FROM daily_kline
            WHERE code = '{code_clean}'
            ORDER BY trade_date
        """).fetchdf()

        if not df.empty:
            df = df.fillna(0)
            stock_data[code_clean] = {
                "name": name,
                "sector": sector,
                "prices": df["close"].values.astype(float),
                "dates": df["trade_date"].values,
            }

    conn.close()

    if not stock_data:
        return {}

    # 计算个股指标
    stock_metrics = []
    aligned_prices = []

    for code, data in stock_data.items():
        prices = data["prices"]
        if len(prices) < 20:
            continue

        returns = compute_returns(prices)
        if len(returns) < 10:
            continue

        sharpe = compute_sharpe(returns)
        mdd = compute_max_drawdown(prices)
        var_95 = compute_var(returns, 0.95)
        annual_ret = float(np.mean(returns) * 252 * 100)
        annual_vol = float(np.std(returns) * np.sqrt(252) * 100)
        latest_price = float(prices[-1])
        latest_date = str(data["dates"][-1]).split(" ")[0].split("T")[0]

        stock_metrics.append({
            "code": code,
            "name": data["name"],
            "sector": data["sector"],
            "latest_price": latest_price,
            "latest_date": latest_date,
            "annual_return_pct": round(annual_ret, 2),
            "annual_volatility_pct": round(annual_vol, 2),
            "sharpe_ratio": round(sharpe, 3),
            "max_drawdown_pct": round(mdd * 100, 2),
            "var_95_pct": round(var_95 * 100, 2),
        })

        aligned_prices.append(prices)

    # 组合等权收益
    min_len = min(len(p) for p in aligned_prices) if aligned_prices else 0
    if min_len < 2:
        return {}

    # 对齐到相同长度
    aligned = np.array([p[-min_len:] for p in aligned_prices])
    portfolio_prices = np.mean(aligned, axis=0)
    portfolio_returns = compute_returns(portfolio_prices)

    # 组合指标
    portfolio_sharpe = compute_sharpe(portfolio_returns)
    portfolio_mdd = compute_max_drawdown(portfolio_prices)
    portfolio_var = compute_var(portfolio_returns)
    portfolio_annual_ret = float(np.mean(portfolio_returns) * 252 * 100)
    portfolio_annual_vol = float(np.std(portfolio_returns) * np.sqrt(252) * 100)

    # 计算 β (用等权组合代替市场)
    betas = []
    for sm in stock_metrics:
        if sm["code"] in stock_data:
            sp = stock_data[sm["code"]]["prices"]
            sr = compute_returns(sp)
            beta = compute_beta(sr, portfolio_returns)
            sm["beta"] = round(beta, 3)
            betas.append(beta)

    # 相关性矩阵 (前10只)
    top_codes = [sm["code"] for sm in stock_metrics[:10]]
    top_names = [sm["name"] for sm in stock_metrics[:10]]
    corr_matrix = []
    if len(top_codes) >= 2:
        prices_matrix = []
        for code in top_codes:
            if code in stock_data:
                prices_matrix.append(stock_data[code]["prices"][-min_len:])
        if len(prices_matrix) >= 2:
            returns_matrix = np.array([compute_returns(p) for p in prices_matrix])
            corr_matrix = np.corrcoef(returns_matrix).tolist()

    # 行业集中度
    total = len(stock_metrics)
    sector_concentration = {}
    for sector, count in sectors.most_common():
        sector_concentration[sector] = {
            "count": count,
            "pct": round(count / total * 100, 1) if total > 0 else 0,
        }

    # 按夏普比率排名
    stock_metrics.sort(key=lambda x: -x["sharpe_ratio"])

    result = {
        "run_date": TODAY,
        "total_stocks": len(stock_metrics),
        "portfolio": {
            "annual_return_pct": round(portfolio_annual_ret, 2),
            "annual_volatility_pct": round(portfolio_annual_vol, 2),
            "sharpe_ratio": round(portfolio_sharpe, 3),
            "max_drawdown_pct": round(portfolio_mdd * 100, 2),
            "var_95_pct": round(portfolio_var * 100, 2),
            "avg_beta": round(float(np.mean(betas)), 3) if betas else 1.0,
            "positive_return_stocks": sum(1 for sm in stock_metrics if sm["annual_return_pct"] > 0),
            "negative_return_stocks": sum(1 for sm in stock_metrics if sm["annual_return_pct"] <= 0),
        },
        "sector_concentration": sector_concentration,
        "stock_metrics": stock_metrics,
        "correlation_matrix": {
            "stocks": top_names,
            "matrix": corr_matrix,
        },
    }

    return result


def generate_html_report(result: dict) -> str:
    """生成分析报告 HTML"""
    portfolio = result["portfolio"]
    sectors = result.get("sector_concentration", {})
    stock_metrics = result.get("stock_metrics", [])

    # 前5/后5
    top5 = stock_metrics[:5]
    bottom5 = stock_metrics[-5:] if len(stock_metrics) >= 5 else stock_metrics

    stock_table = ""
    for sm in stock_metrics:
        sharpe_color = "#00a854" if sm["sharpe_ratio"] > 0.5 else ("#fa8c16" if sm["sharpe_ratio"] > 0 else "#d4380d")
        stock_table += f"""<tr>
    <td>{sm['name']}</td>
    <td>{sm['sector']}</td>
    <td style="color:{sharpe_color};font-weight:600">{sm['sharpe_ratio']}</td>
    <td>{sm['annual_return_pct']}%</td>
    <td>{sm['annual_volatility_pct']}%</td>
    <td>{sm['max_drawdown_pct']}%</td>
    <td>{sm['var_95_pct']}%</td>
    <td>{sm.get('beta', '-')}</td>
  </tr>"""

    sectors_json = json.dumps(
        [{"name": k, "value": v["count"]} for k, v in sorted(sectors.items(), key=lambda x: -x[1]["count"])],
        ensure_ascii=False,
    )

    # Top5 夏普对比
    top_sharpes = json.dumps([{"name": sm["name"], "sharpe": sm["sharpe_ratio"]} for sm in top5], ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>📋 持仓分析报告 - {TODAY}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0f1117; color:#e0e0e0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; padding:20px; }}
h1 {{ font-size:24px; margin-bottom:8px; color:#fff; }}
.subtitle {{ color:#888; font-size:14px; margin-bottom:24px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:16px; margin-bottom:24px; }}
.card {{ background:#1a1d27; border-radius:12px; padding:20px; border:1px solid #2a2d37; }}
.card h3 {{ font-size:14px; color:#888; margin-bottom:8px; }}
.card .value {{ font-size:24px; font-weight:700; }}
.card .sub {{ font-size:12px; color:#666; margin-top:4px; }}
.chart-card {{ background:#1a1d27; border-radius:12px; padding:16px; border:1px solid #2a2d37; margin-bottom:16px; }}
.chart-card h3 {{ font-size:14px; color:#888; margin-bottom:12px; }}
.chart {{ width:100%; height:350px; }}
.chart-sm {{ height:250px; }}
table {{ width:100%; border-collapse:collapse; font-size:12px; }}
th {{ text-align:left; padding:6px 8px; color:#888; font-weight:500; border-bottom:1px solid #2a2d37; }}
td {{ padding:6px 8px; border-bottom:1px solid #22252f; }}
tr:hover td {{ background:rgba(255,255,255,0.03); }}
</style>
</head>
<body>
<h1>📋 持仓分析报告</h1>
<p class="subtitle">{TODAY} | {result['total_stocks']} 只股票</p>

<div class="grid">
  <div class="card"><h3>年化收益</h3><div class="value" style="color:{'#00a854' if portfolio['annual_return_pct'] > 0 else '#d4380d'}">{portfolio['annual_return_pct']}%</div></div>
  <div class="card"><h3>年化波动</h3><div class="value">{portfolio['annual_volatility_pct']}%</div></div>
  <div class="card"><h3>夏普比率</h3><div class="value" style="color:{'#00a854' if portfolio['sharpe_ratio'] > 0.5 else '#fa8c16' if portfolio['sharpe_ratio'] > 0 else '#d4380d'}">{portfolio['sharpe_ratio']}</div></div>
  <div class="card"><h3>最大回撤</h3><div class="value" style="color:#d4380d">{portfolio['max_drawdown_pct']}%</div></div>
  <div class="card"><h3>VaR(95%)</h3><div class="value">{portfolio['var_95_pct']}%</div></div>
  <div class="card"><h3>平均β</h3><div class="value">{portfolio['avg_beta']}</div></div>
</div>

<div class="grid">
  <div class="chart-card">
    <h3>🏭 行业分布</h3>
    <div id="sectorChart" class="chart-sm"></div>
  </div>
  <div class="chart-card">
    <h3>⭐ 最佳夏普 (Top 5)</h3>
    <div id="sharpeChart" class="chart-sm"></div>
  </div>
</div>

<script>
const sectorChart = echarts.init(document.getElementById('sectorChart'));
sectorChart.setOption({{
  tooltip: {{ trigger: 'item', formatter: '{{b}}: {{c}}只 ({{d}}%)' }},
  series: [{{
    type: 'pie', radius: ['40%', '70%'],
    data: {sectors_json},
    label: {{ color: '#888', fontSize: 10 }},
    itemStyle: {{ borderRadius: 4 }}
  }}]
}});

const sharpeChart = echarts.init(document.getElementById('sharpeChart'));
sharpeChart.setOption({{
  tooltip: {{ trigger: 'axis' }},
  grid: {{ left: '15%', right: '5%', bottom: '20%' }},
  xAxis: {{ type: 'category', data: {top_sharpes}.map(d => d.name), axisLabel: {{ color: '#888', rotate: 30, fontSize: 10 }} }},
  yAxis: {{ type: 'value', axisLabel: {{ color: '#888' }}, splitLine: {{ lineStyle: {{ color: '#2a2d37' }} }} }},
  series: [{{
    type: 'bar', data: {top_sharpes}.map(d => d.sharpe),
    itemStyle: {{ color: new echarts.graphic.LinearGradient(0,0,0,1, [{{offset:0,color:'#5470c6'}},{{offset:1,color:'#2a3d6b'}}]) }},
    label: {{ show: true, position: 'top', formatter: '{{c}}', color: '#888', fontSize: 10 }}
  }}]
}});
</script>

<div class="chart-card">
  <h3>📋 个股详细指标</h3>
  <table><thead><tr>
    <th>名称</th><th>板块</th><th>夏普</th><th>年化收益</th><th>年化波动</th><th>最大回撤</th><th>VaR(95%)</th><th>β</th>
  </tr></thead><tbody>
  {stock_table}
  </tbody></table>
</div>
</body>
</html>"""
    return html


def save_results(result: dict, html: str):
    json_path = os.path.join(OUTPUT_DIR, "portfolio_analysis.json")
    html_path = os.path.join(OUTPUT_DIR, "portfolio_analysis.html")
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
    print(f"{'⏰' if cron else '🚀'} 持仓分析: {TODAY}")
    result = run_analysis()
    if not result:
        return

    html = generate_html_report(result)
    save_results(result, html)

    p = result["portfolio"]
    summary = (f"📋 持仓分析\n"
               f"夏普{p['sharpe_ratio']} | 年化{p['annual_return_pct']}%\n"
               f"最大回撤{p['max_drawdown_pct']}% | VaR{p['var_95_pct']}%")

    print(f"\n{summary}")

    if cron:
        notify(summary)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="持仓分析")
    parser.add_argument("--cron", action="store_true")
    args = parser.parse_args()
    main(cron=args.cron)