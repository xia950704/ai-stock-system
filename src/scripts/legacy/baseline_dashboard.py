#!/usr/bin/env python3
"""
baseline_dashboard.py — 基准线可视化报告生成器
生成纯 HTML 报告（ECharts CDN + 自定义 CSS），无需依赖。
"""

import json
import os
from datetime import datetime, timedelta, timezone
from string import Template

WORKSPACE = os.environ.get("HERMES_WORKSPACE", "/Users/xiashuang/harness/stock_daily")
INPUT_FILE = os.path.join(WORKSPACE, "baseline_ml_results.json")
OUTPUT_FILE = os.path.join(WORKSPACE, "baseline_dashboard.html")

def main():
    with open(INPUT_FILE) as f:
        data = json.load(f)

    bs = data["71_stocks"]["baselines"]
    benchmarks = data["71_stocks"]["sector_benchmarks"]
    clusters = data["3000_stocks"]

    with_signal = [b for b in bs if "signal" in b and "level" in b["signal"]]

    sig_counts = {}
    for b in with_signal:
        sig_counts[b["signal"]["level"]] = sig_counts.get(b["signal"]["level"], 0) + 1

    sector_names = list(benchmarks.keys())
    rsi_means = [benchmarks[s]["rsi_mean"] for s in sector_names]
    score_means = [benchmarks[s]["score_mean"] for s in sector_names]
    stock_counts = [benchmarks[s]["stock_count"] for s in sector_names]

    cluster_names = []
    cluster_counts = []
    cluster_outliers = []
    for cs in clusters["cluster_summary"]:
        cluster_names.append(f"聚类{cs['cluster_id']}")
        cluster_counts.append(cs["stock_count"])
        cluster_outliers.append(cs["outlier_count"])

    buy_stocks = sorted(
        [b for b in with_signal if b["signal"]["level"] == "强买入"],
        key=lambda x: x["signal_score"],
        reverse=True,
    )[:20]

    outliers = clusters["outliers"][:20]

    generated_at = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")

    # Build JS data
    scatter_js = json.dumps(with_signal, ensure_ascii=False)
    sector_bubble_js = json.dumps(
        [[r, s, n, c] for r, s, n, c in zip(rsi_means, score_means, sector_names, stock_counts)],
        ensure_ascii=False,
    )
    pie_js = json.dumps(sig_counts)
    cluster_names_js = json.dumps(cluster_names)
    cluster_counts_js = json.dumps(cluster_counts)
    cluster_outliers_js = json.dumps(cluster_outliers)

    buy_rows = ""
    for i, b in enumerate(buy_stocks):
        reasons = ", ".join(b["signal"]["reasons"][:3])
        buy_rows += f"<tr><td>{i+1}</td><td>{b['stock_name']}</td><td>{b['stock_code']}</td><td><span class='badge badge-strong'>{b['signal']['score']}</span></td><td>{b['rsi']}</td><td>{b['chg_20d']}%</td><td>{b['bollinger_position']}%</td><td>{reasons}</td></tr>\n"

    cluster_rows = ""
    for cs in clusters["cluster_summary"]:
        cluster_rows += f"<tr><td>{cs['cluster_id']}</td><td>{cs['stock_count']}</td><td>{cs['description']}</td><td>{cs['outlier_count']}</td></tr>\n"

    outlier_rows = ""
    for i, o in enumerate(outliers):
        outlier_rows += f"<tr><td>{i+1}</td><td>{o['stock_code']}</td><td>{o['cluster_id']}</td><td>{o['outlier_ratio']}</td><td>{o['chg_1d']}%</td><td>{o['chg_5d']}%</td><td>{o['chg_20d']}%</td><td>{o['turnover']:.1f}%</td></tr>\n"

    template = Template("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>股票基准线报告</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", sans-serif; margin: 0; background: #fafafa; color: #333; }
  .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px 40px; }
  .header h1 { margin: 0; font-size: 28px; }
  .header p { margin: 8px 0 0; opacity: 0.85; font-size: 14px; }
  .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
  .card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
  .card h3 { margin: 0 0 16px; font-size: 16px; color: #444; border-bottom: 2px solid #f0f0f0; padding-bottom: 8px; }
  .chart { height: 360px; width: 100%; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { background: #f5f5f5; padding: 10px 8px; text-align: left; font-weight: 600; }
  td { padding: 8px; border-bottom: 1px solid #f0f0f0; }
  tr:hover td { background: #f9f9ff; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; font-weight: 600; background: #c8e6c9; color: #1b5e20; }
  .section { margin-bottom: 30px; }
  .section-title { font-size: 20px; font-weight: 600; margin-bottom: 16px; padding-left: 12px; border-left: 4px solid #667eea; }
</style>
</head>
<body>
<div class="header">
  <h1>📊 股票基准线机器学习报告</h1>
  <p>生成时间: $generated_at | 71只长线 + 3000只短线聚类 | KMeans + 技术指标分位</p>
</div>
<div class="container">

<div class="section">
  <div class="section-title">71只长线 — 信号分布</div>
  <div class="grid">
    <div class="card"><h3>信号分布</h3><div id="chart-pie" class="chart"></div></div>
    <div class="card"><h3>RSI vs 评分散点</h3><div id="chart-scatter" class="chart"></div></div>
  </div>
</div>

<div class="section">
  <div class="section-title">行业基准对比</div>
  <div class="card"><h3>行业 RSI 均值 vs 评分均值（气泡=股票数）</h3><div id="chart-sector" class="chart" style="height:420px"></div></div>
</div>

<div class="section">
  <div class="section-title">3000只短线 — 聚类分布</div>
  <div class="grid">
    <div class="card"><h3>聚类股票数量</h3><div id="chart-cluster" class="chart"></div></div>
    <div class="card"><h3>各聚类异常候选数</h3><div id="chart-outlier" class="chart"></div></div>
  </div>
  <div class="card" style="margin-top:16px"><h3>聚类描述</h3>
    <table>
      <tr><th>聚类</th><th>股票数</th><th>描述</th><th>异常候选</th></tr>
      $cluster_rows
    </table>
  </div>
</div>

<div class="section">
  <div class="section-title">TOP20 强买入（按评分排序）</div>
  <div class="card">
    <table>
      <tr><th>排名</th><th>股票</th><th>代码</th><th>评分</th><th>RSI</th><th>20日涨跌</th><th>布林位置</th><th>理由</th></tr>
      $buy_rows
    </table>
  </div>
</div>

<div class="section">
  <div class="section-title">异常候选（偏离聚类 > 2.5σ）</div>
  <div class="card">
    <table>
      <tr><th>排名</th><th>代码</th><th>聚类</th><th>偏离倍数</th><th>1日涨跌</th><th>5日涨跌</th><th>20日涨跌</th><th>换手率</th></tr>
      $outlier_rows
    </table>
  </div>
</div>

</div>

<script>
// Pie
var pieChart = echarts.init(document.getElementById('chart-pie'));
pieChart.setOption({
  title: { text: '信号分布', left: 'center', top: 10 },
  tooltip: { trigger: 'item', formatter: '{b}: {c}只 ({d}%)' },
  legend: { bottom: 0 },
  series: [{
    type: 'pie', radius: ['40%', '70%'],
    data: $pie_js.map(function(d) { return { name: d.name, value: d.value, itemStyle: { color: d.name === '强买入' ? '#2e7d32' : d.name === '买入' ? '#66bb6a' : d.name === '观望' ? '#ffa726' : '#ef5350' } }; })
  }]
});

// Scatter
var scatterChart = echarts.init(document.getElementById('chart-scatter'));
scatterChart.setOption({
  title: { text: 'RSI vs 评分', left: 'center', top: 10 },
  tooltip: { trigger: 'item', formatter: function(p) { return p.data.stock_name + ': RSI=' + p.data.rsi + ', 评分=' + p.data.signal_score; } },
  xAxis: { name: 'RSI', min: 0, max: 100 },
  yAxis: { name: '评分', min: 0, max: 100 },
  series: [{ type: 'scatter', data: $scatter_js.map(function(d) { return [d.rsi, d.signal_score, d.stock_name]; }), symbolSize: 8 }]
});

// Sector bubble
var sectorChart = echarts.init(document.getElementById('chart-sector'));
sectorChart.setOption({
  title: { text: '行业基准', left: 'center', top: 10 },
  tooltip: { formatter: function(p) { return p.data[2] + ': RSI=' + p.data[0] + ', 评分=' + p.data[1] + ', 股票数=' + p.data[3]; } },
  xAxis: { name: 'RSI均值', min: 0, max: 100 },
  yAxis: { name: '评分均值', min: 0, max: 100 },
  series: [{ type: 'scatter', symbolSize: function(d) { return Math.max(12, d[3] * 4); }, data: $sector_bubble_js }]
});

// Cluster bar
var clusterChart = echarts.init(document.getElementById('chart-cluster'));
clusterChart.setOption({
  title: { text: '各聚类股票数量', left: 'center' },
  xAxis: { type: 'category', data: $cluster_names_js },
  yAxis: { name: '股票数' },
  series: [{ type: 'bar', data: $cluster_counts_js, itemStyle: { color: '#667eea' } }]
});

// Outlier bar
var outlierChart = echarts.init(document.getElementById('chart-outlier'));
outlierChart.setOption({
  title: { text: '各聚类异常候选数', left: 'center' },
  xAxis: { type: 'category', data: $cluster_names_js },
  yAxis: { name: '异常数' },
  series: [{ type: 'bar', data: $cluster_outliers_js, itemStyle: { color: '#ef5350' } }]
});

window.addEventListener('resize', function() {
  pieChart.resize(); scatterChart.resize(); sectorChart.resize();
  clusterChart.resize(); outlierChart.resize();
});
</script>
</body>
</html>""")

    html = template.safe_substitute(
        generated_at=generated_at,
        buy_rows=buy_rows,
        cluster_rows=cluster_rows,
        outlier_rows=outlier_rows,
        pie_js=pie_js,
        scatter_js=scatter_js,
        sector_bubble_js=sector_bubble_js,
        cluster_names_js=cluster_names_js,
        cluster_counts_js=cluster_counts_js,
        cluster_outliers_js=cluster_outliers_js,
    )

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard saved: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()