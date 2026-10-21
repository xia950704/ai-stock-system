"""
报告生成器
============
生成每日信号日报(.md) + HTML仪表盘 + EdgeOne部署
"""

import os, json
from datetime import datetime

# ==================== 路径 ====================
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_DIR = os.path.join(PROJECT_ROOT, 'reports')
DAILY_DIR = os.path.join(REPORTS_DIR, 'daily')
HTML_DIR = os.path.join(REPORTS_DIR, 'html')
WEEKLY_DIR = os.path.join(REPORTS_DIR, 'weekly')

# Obsidian vault 路径
OBSIDIAN_STOCK_DIR = os.path.expanduser(
    '~/obsidian/all about xia/01-股票投研/日更'
)

for d in [DAILY_DIR, HTML_DIR, WEEKLY_DIR]:
    os.makedirs(d, exist_ok=True)


def fmt_pct(v):
    """格式化百分比"""
    if v is None:
        return '-'
    return f"{v:+.2%}" if isinstance(v, float) else str(v)


def fmt_signal(signal_type, z):
    """格式化信号标记"""
    if signal_type == 'buy':
        return f"🟢 买入"
    elif signal_type == 'overvalued':
        return f"🔴 偏高"
    elif signal_type == 'undervalued':
        return f"🟢 低估"
    else:
        return "⚪ 观望"


def get_signal_type(z, z_entry=2.0):
    """判断信号类型"""
    z = float(z)
    if z < -z_entry:
        return 'buy'
    elif z > z_entry:
        return 'overvalued'
    else:
        return 'neutral'


def collect_signals(pairs_data):
    """
    从pairs回测/信号数据中提取结构化结果
    pairs_data: 由 step4_signal_check 生成的数据列表
    """
    buy_signals = []
    overvalued_signals = []
    neutral_signals = []

    for p in pairs_data:
        sig = get_signal_type(p['z'])
        entry = {
            'label': p['label'],
            'symbol_a': p.get('symbol_a', ''),
            'symbol_b': p.get('symbol_b', ''),
            'z': p['z'],
            'price': p.get('price_a', 0),
            'ratio': p.get('ratio', 0),
            'name_a': p.get('name_a', ''),
            'name_b': p.get('name_b', ''),
        }
        if sig == 'buy':
            buy_signals.append(entry)
        elif sig == 'overvalued':
            overvalued_signals.append(entry)
        else:
            neutral_signals.append(entry)

    return buy_signals, overvalued_signals, neutral_signals


def generate_daily_md(pairs_data, backtest_summary=None, output_dir=None):
    """
    生成每日信号日报（Markdown格式）
    写入: reports/daily/ + Obsidian vault 日更/
    """
    if output_dir is None:
        output_dir = DAILY_DIR

    today = datetime.now().strftime('%Y-%m-%d')
    buy_sigs, over_sigs, neutral_sigs = collect_signals(pairs_data)

    # --- 构建 Markdown ---
    lines = []
    lines.append(f"# 📊 配对交易信号日报 {today}")
    lines.append("")
    lines.append(f"> 自动生成 | 策略: 统计套利均值回归 | 开仓|z|>2.0")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 🟢 开仓信号
    lines.append("## 🟢 开仓信号（低估买入）")
    lines.append("")
    if buy_sigs:
        lines.append("| 配对 | z-score | 价格 | 说明 |")
        lines.append("|:----|:------:|:----:|:----|")
        for s in buy_sigs:
            lines.append(
                f"| {s['label']} | **{s['z']:+.1f}** | ¥{s['price']:.0f} | "
                f"{s['name_a']}相对{s['name_b']}偏低估，关注回归 |"
            )
        lines.append("")
    else:
        lines.append("_当前无触发开仓条件的配对_")
        lines.append("")

    # 🔴 偏离监控
    lines.append("## 🔴 偏离监控（高估/待回归）")
    lines.append("")
    if over_sigs:
        lines.append("| 配对 | z-score | 价格 | 说明 |")
        lines.append("|:----|:------:|:----:|:----|")
        for s in over_sigs:
            lines.append(
                f"| {s['label']} | **{s['z']:+.1f}** | ¥{s['price']:.0f} | "
                f"{s['name_a']}相对{s['name_b']}偏贵，或考虑买入{s['name_b']} |"
            )
        lines.append("")
    else:
        lines.append("_当前无显著偏离配對_")
        lines.append("")

    # ⚪ 均值附近
    lines.append("## ⚪ 均值附近（观望）")
    lines.append("")
    if neutral_sigs:
        cols = 4
        for i in range(0, len(neutral_sigs), cols):
            row = " | ".join([f"{s['label']}(z={s['z']:+.1f})" for s in neutral_sigs[i:i+cols]])
            lines.append(f"| {row} |")
        lines.append("")
    else:
        lines.append("_所有配对均有信号_")
        lines.append("")

    # 📈 策略表现
    if backtest_summary:
        lines.append("---")
        lines.append("")
        lines.append("## 📈 策略表现排名")
        lines.append("")
        lines.append("| 排名 | 配对 | 收益 | 胜率 | 交易 | 夏普 |")
        lines.append("|:---:|:----|:----:|:----:|:----:|:----:|")
        for i, r in enumerate(backtest_summary, 1):
            if 'error' in r:
                continue
            marker = "✅" if r.get('total_return', 0) > 0 else "❌"
            lines.append(
                f"| {i} | {marker} {r.get('label','')} | "
                f"{r.get('total_return', 0):+.2%} | "
                f"{r.get('win_rate', 0):.0%} | "
                f"{r.get('total_trades', 0)} | "
                f"{r.get('sharpe', 0):.1f} |"
            )
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"*报告时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append("")

    content = "\n".join(lines)

    # --- 写入文件 ---
    # 写到 reports/daily/
    local_path = os.path.join(output_dir, f"{today}.md")
    with open(local_path, 'w', encoding='utf-8') as f:
        f.write(content)

    # 写到 Obsidian vault
    os.makedirs(OBSIDIAN_STOCK_DIR, exist_ok=True)
    vault_path = os.path.join(OBSIDIAN_STOCK_DIR, f"配对信号_{today}.md")
    with open(vault_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"  📝 日报已生成:")
    print(f"    - {local_path}")
    print(f"    - {vault_path}")

    return local_path, vault_path


def generate_html_dashboard(backtest_results, title="配对交易策略仪表盘"):
    """
    生成HTML仪表盘
    用完整内联HTML（无需外部依赖）
    """
    today = datetime.now().strftime('%Y-%m-%d')

    # 表格行
    table_rows = []
    for r in sorted(backtest_results, key=lambda x: x.get('total_return', 0), reverse=True):
        if 'error' in r:
            continue
        ret = r.get('total_return', 0)
        ret_class = "positive" if ret > 0 else "negative"
        marker = "🟢" if ret > 0 else "🔴"
        table_rows.append(f"""
        <tr>
            <td>{marker} {r.get('label','')}</td>
            <td>{r.get('sector','')}</td>
            <td class="{ret_class}">{ret:+.2%}</td>
            <td>{r.get('total_trades',0)}</td>
            <td>{r.get('win_rate',0):.0%}</td>
            <td>{r.get('sharpe',0):.1f}</td>
            <td class="{ret_class}">{r.get('max_drawdown',0):.2%}</td>
            <td>{r.get('correlation',0):.3f}</td>
        </tr>""")

    # 汇总
    valid = [r for r in backtest_results if 'error' not in r]
    avg_ret = sum(r.get('total_return', 0) for r in valid) / len(valid) if valid else 0
    avg_win = sum(r.get('win_rate', 0) for r in valid) / len(valid) if valid else 0
    total_trades = sum(r.get('total_trades', 0) for r in valid)
    winners = sum(1 for r in valid if r.get('total_return', 0) > 0)
    losers = sum(1 for r in valid if r.get('total_return', 0) <= 0)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} - {today}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         background: #0f172a; color: #e2e8f0; padding: 24px; }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  h1 {{ font-size: 1.8em; margin-bottom: 8px; color: #f1f5f9; }}
  .subtitle {{ color: #94a3b8; margin-bottom: 24px; }}
  .stats-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
               gap: 16px; margin-bottom: 24px; }}
  .stat-card {{ background: #1e293b; border-radius: 12px; padding: 16px; text-align: center; }}
  .stat-card .value {{ font-size: 1.6em; font-weight: 700; }}
  .stat-card .label {{ font-size: 0.8em; color: #94a3b8; margin-top: 4px; }}
  .positive {{ color: #22c55e; }}
  .negative {{ color: #ef4444; }}
  .table-wrap {{ overflow-x: auto; background: #1e293b; border-radius: 12px; padding: 16px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.9em; }}
  th {{ text-align: left; padding: 10px 8px; border-bottom: 2px solid #334155;
        color: #94a3b8; font-weight: 600; white-space: nowrap; }}
  td {{ padding: 10px 8px; border-bottom: 1px solid #1e293b; }}
  tr:hover td {{ background: #334155; }}
  .signal-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                  gap: 16px; margin: 24px 0; }}
  .signal-card {{ background: #1e293b; border-radius: 12px; padding: 16px;
                  border-left: 4px solid #64748b; }}
  .signal-card.buy {{ border-left-color: #22c55e; }}
  .signal-card.over {{ border-left-color: #ef4444; }}
  .signal-card h3 {{ font-size: 1em; margin-bottom: 8px; }}
  .signal-card .meta {{ font-size: 0.85em; color: #94a3b8; }}
  .z-score {{ font-size: 1.8em; font-weight: 700; }}
  footer {{ text-align: center; color: #64748b; font-size: 0.8em; margin-top: 32px; }}
</style>
</head>
<body>
<div class="container">
  <h1>📊 {title}</h1>
  <p class="subtitle">更新于 {today} | 统计套利均值回归策略 | 开仓|z|>2.0</p>

  <div class="stats-row">
    <div class="stat-card">
      <div class="value {'positive' if avg_ret > 0 else 'negative'}">{avg_ret:+.2%}</div>
      <div class="label">平均收益</div>
    </div>
    <div class="stat-card">
      <div class="value">{sum(r.get('final_capital', 0) for r in valid):,.0f}</div>
      <div class="label">总资产({len(valid)}份)</div>
    </div>
    <div class="stat-card">
      <div class="value">{total_trades}</div>
      <div class="label">总交易</div>
    </div>
    <div class="stat-card">
      <div class="value positive">{avg_win:.0%}</div>
      <div class="label">平均胜率({winners}盈/{losers}亏)</div>
    </div>
    <div class="stat-card">
      <div class="value">{len(valid)}</div>
      <div class="label">活跃配对</div>
    </div>
  </div>

  <h2>📋 全配对排名</h2>
  <div class="table-wrap">
  <table>
    <thead>
      <tr><th>配对</th><th>行业</th><th>收益</th><th>交易</th><th>胜率</th><th>夏普</th><th>回撤</th><th>相关性</th></tr>
    </thead>
    <tbody>
      {''.join(table_rows)}
    </tbody>
  </table>
  </div>

  <footer>生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')} | 不构成投资建议</footer>
</div>
</body>
</html>"""

    # 写入
    index_path = os.path.join(HTML_DIR, 'index.html')
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  🖥️  HTML仪表盘: {index_path}")

    return index_path


def deploy_to_edgeone(html_path=None, project_name='pairs-trading-dashboard'):
    """部署HTML到EdgeOne Makers（用文件夹方式）"""
    import subprocess, tempfile, shutil

    if html_path is None:
        html_path = os.path.join(HTML_DIR, 'index.html')

    if not os.path.exists(html_path):
        print(f"  ❌ HTML文件不存在: {html_path}")
        return None

    print(f"  🚀 部署到 EdgeOne...")

    try:
        # EdgeOne CLI 要求传入文件夹，创建临时目录
        tmp_dir = tempfile.mkdtemp(prefix='pairs-dashboard-')
        shutil.copy2(html_path, os.path.join(tmp_dir, 'index.html'))

        result = subprocess.run(
            ['edgeone', 'makers', 'deploy', tmp_dir, '-n', project_name],
            capture_output=True, text=True, timeout=120
        )

        # 清理
        shutil.rmtree(tmp_dir, ignore_errors=True)

        if result.returncode == 0:
            # 从输出中提取URL
            for line in result.stdout.split('\n'):
                if 'https://' in line and '.edgeone.cool' in line:
                    url = line.strip()
                    print(f"  ✅ 已部署: {url}")
                    # 保存URL到文件
                    url_file = os.path.join(HTML_DIR, 'deploy_url.txt')
                    with open(url_file, 'w') as f:
                        f.write(url)
                    return url
            print(f"  ✅ 部署完成（URL未提取到，请查看控制台）")
            print(result.stdout[:500])
            return None
        else:
            print(f"  ⚠️  EdgeOne 部署失败: {result.stderr[:300]}")
            return None

    except subprocess.TimeoutExpired:
        print(f"  ⚠️  EdgeOne 部署超时（>120s），可能仍在后台运行")
        return None
    except Exception as e:
        print(f"  ⚠️  EdgeOne 部署异常: {e}")
        return None