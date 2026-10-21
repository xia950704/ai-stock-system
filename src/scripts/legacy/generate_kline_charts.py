#!/usr/bin/env python3
"""
generate_kline_charts.py — 个股K线图生成
为5只"图表待补充"的个股生成全历史K线图 + 近5年蜡烛图。
保存到 vault 图表/ 目录 + data/stocks/ 目录。

用法:
  python generate_kline_charts.py              # 全量生成5只
  python generate_kline_charts.py --stock 300896  # 指定单只
  python generate_kline_charts.py --dry-run     # 预览不走网络
"""

import os, sys, json, argparse
from datetime import datetime, timedelta

os.environ["MPLBACKEND"] = "Agg"
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import pandas as pd
import numpy as np

# 中文字体
plt.rcParams["font.sans-serif"] = ["PingFang SC", "Heiti SC", "STHeiti"]
plt.rcParams["axes.unicode_minus"] = False

import warnings
warnings.filterwarnings("ignore")

try:
    import akshare as ak
except ImportError:
    print("ERROR: pip install akshare"); sys.exit(1)

VAULT = os.path.expanduser("~/obsidian/all about xia")
CHART_DIR = os.path.join(VAULT, "01-股票投研", "图表")
DATA_DIR = os.path.join(VAULT, "01-股票投研", "data", "stocks")

# 待补图的5只股票
STOCKS = [
    {"code": "920566", "name": "梓橦宫", "exchange": "BJ", "market": "北交所"},
    {"code": "300896", "name": "爱美客", "exchange": "SZ", "market": "创业板"},
    {"code": "600196", "name": "复星医药", "exchange": "SH", "market": "主板"},
    {"code": "300759", "name": "康龙化成", "exchange": "SZ", "market": "创业板"},
    {"code": "300347", "name": "泰格医药", "exchange": "SZ", "market": "创业板"},
]


def safe_mkdir(path):
    os.makedirs(path, exist_ok=True)


def fetch_stock_data(code: str, name: str, exchange: str) -> pd.DataFrame:
    """从akshare获取个股日K线（三层降级）"""
    full_code = f"{code}.{exchange}"
    print(f"  [数据] {name}({full_code})...", end=" ", flush=True)
    
    # 三层降级: 1.有adjust → 2.无adjust → 3.stock_zh_a_daily
    strategies = [
        {"adjust": "qfq", "label": "前复权"},
        {"adjust": None, "label": "不复权"},
    ]
    
    for strat in strategies:
        try:
            kwargs = {
                "symbol": code,
                "period": "daily",
                "start_date": "20100101",
                "end_date": datetime.now().strftime("%Y%m%d"),
            }
            if strat["adjust"]:
                kwargs["adjust"] = strat["adjust"]
            
            df = ak.stock_zh_a_hist(**kwargs)
            
            if df.empty:
                continue
            
            df = df.rename(columns={
                "日期": "date", "开盘": "open", "收盘": "close",
                "最高": "high", "最低": "low", "成交量": "volume",
                "成交额": "amount", "振幅": "amplitude",
                "涨跌幅": "pct_chg", "涨跌额": "change",
                "换手率": "turnover"
            })
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)
            
            print(f"{len(df)} 行 ({df['date'].iloc[0].strftime('%Y-%m-%d')} ~ {df['date'].iloc[-1].strftime('%Y-%m-%d')}) [{strat['label']}]")
            return df
        except Exception as e:
            print(f"\r  [数据] {name}({full_code})... 层{strategies.index(strat)+1}失败({strat['label']}): {type(e).__name__}", end=" ")
            continue
    
    # 第三层: stock_zh_a_daily
    try:
        prefix = "sh" if exchange == "SH" else "sz"
        df = ak.stock_zh_a_daily(
            symbol=f"{prefix}{code}",
            adjust="qfq",
            start_date="20100101",
            end_date=datetime.now().strftime("%Y%m%d")
        )
        df = df.rename(columns={
            "date": "date", "open": "open", "close": "close",
            "high": "high", "low": "low", "volume": "volume",
            "amount": "amount"
        })
        df["date"] = pd.to_datetime(df["date"])
        df["pct_chg"] = df["close"].pct_change() * 100
        df = df.sort_values("date").reset_index(drop=True)
        print(f"{len(df)} 行 (第三层)")
        return df
    except Exception as e:
        print(f"\n  ⚠️ 全部失败: {e}")
        return pd.DataFrame()


def save_csv(df: pd.DataFrame, code: str, name: str):
    """保存CSV到data/stocks"""
    fname = f"{code}_{name}.csv"
    fpath = os.path.join(DATA_DIR, fname)
    df.to_csv(fpath, index=False, encoding="utf-8-sig")
    print(f"  [CSV] 已保存: {fpath}")
    return fpath


def plot_full_history(df: pd.DataFrame, code: str, name: str, market: str):
    """全历史K线图 — 三行子图：收盘价+成交量+均线"""
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(16, 10), 
                                         gridspec_kw={"height_ratios": [3, 1, 1]})
    fig.suptitle(f"{name}（{code}.{market}）全历史K线图", fontsize=16, fontweight="bold")
    
    dates = df["date"]
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]
    
    # ---- 子图1：收盘价折线 ----
    ax1.fill_between(dates, close, alpha=0.15, color="#1a73e8")
    ax1.plot(dates, close, color="#1a73e8", linewidth=1.2, label="收盘价")
    
    # MA均线
    for ma, color, label in [(20, "#e67300", "MA20"), (60, "#7cb342", "MA60"), (250, "#d32f2f", "MA250")]:
        if len(close) >= ma:
            ma_vals = close.rolling(ma).mean()
            ax1.plot(dates, ma_vals, color=color, linewidth=0.8, alpha=0.8, label=label)
    
    # 最高/最低点标注
    idx_max = close.idxmax()
    idx_min = close.idxmin()
    ax1.annotate(f"最高 {close[idx_max]:.2f}\n{dates[idx_max].strftime('%Y-%m-%d')}",
                 xy=(dates[idx_max], close[idx_max]),
                 xytext=(dates[idx_max], close[idx_max] * 1.15),
                 arrowprops=dict(arrowstyle="->", color="#d32f2f"),
                 fontsize=9, color="#d32f2f", ha="center")
    ax1.annotate(f"最低 {close[idx_min]:.2f}\n{dates[idx_min].strftime('%Y-%m-%d')}",
                 xy=(dates[idx_min], close[idx_min]),
                 xytext=(dates[idx_min], close[idx_min] * 0.82),
                 arrowprops=dict(arrowstyle="->", color="#2e7d32"),
                 fontsize=9, color="#2e7d32", ha="center")
    
    ax1.set_ylabel("价格", fontsize=11)
    ax1.legend(fontsize=9, loc="upper left")
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_locator(mdates.YearLocator(2))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    
    # ---- 子图2：成交量 ----
    colors = ["#d32f2f" if c >= o else "#2e7d32" 
              for c, o in zip(df["close"], df["open"])]
    ax2.bar(dates, volume, color=colors, alpha=0.6, width=1)
    ax2.set_ylabel("成交量", fontsize=11)
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_locator(mdates.YearLocator(2))
    
    # ---- 子图3：涨跌幅 ----
    pct = df["pct_chg"] if "pct_chg" in df.columns else close.pct_change() * 100
    bar_colors = ["#d32f2f" if v > 0 else "#2e7d32" if v < 0 else "#999" for v in pct]
    ax3.bar(dates, pct.abs(), color=bar_colors, alpha=0.6, width=1)
    ax3.axhline(y=0, color="#333", linewidth=0.5)
    ax3.set_ylabel("涨跌幅%", fontsize=11)
    ax3.grid(True, alpha=0.3)
    ax3.xaxis.set_major_locator(mdates.YearLocator(2))
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    
    plt.tight_layout()
    fname = f"{code}_全历史K线图.png"
    fpath = os.path.join(CHART_DIR, fname)
    fig.savefig(fpath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [图] 全历史: {fpath}")
    return fpath


def plot_candlestick_5y(df: pd.DataFrame, code: str, name: str, market: str):
    """近5年蜡烛图 — 含MACD"""
    cutoff = datetime.now() - timedelta(days=365 * 5)
    df_5y = df[df["date"] >= cutoff].copy()
    if len(df_5y) < 20:
        df_5y = df.tail(120)
    
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(16, 10),
                                         gridspec_kw={"height_ratios": [3, 1, 1]})
    fig.suptitle(f"{name}（{code}.{market}）近5年蜡烛图", fontsize=16, fontweight="bold")
    
    dates = df_5y["date"]
    o, c, h, l, v = [df_5y[col].values for col in ["open", "close", "high", "low", "volume"]]
    
    # ---- 子图1：蜡烛图（手动绘制） ----
    width = 0.6
    for i in range(len(df_5y)):
        color = "#d32f2f" if c[i] >= o[i] else "#2e7d32"
        # 影线
        ax1.plot([dates.iloc[i], dates.iloc[i]], [l[i], h[i]], color=color, linewidth=0.8)
        # 实体
        body_bottom = min(o[i], c[i])
        body_height = abs(c[i] - o[i])
        if body_height > 0:
            ax1.bar(dates.iloc[i], body_height, width, bottom=body_bottom, color=color, alpha=0.9)
        else:
            ax1.plot(dates.iloc[i], o[i], "o", color=color, markersize=3)
    
    # MA均线
    for ma, color, label in [(5, "#ff6f00", "MA5"), (20, "#e67300", "MA20"), (60, "#7cb342", "MA60")]:
        if len(df_5y) >= ma:
            ma_vals = df_5y["close"].rolling(ma).mean()
            ax1.plot(dates, ma_vals, color=color, linewidth=0.8, alpha=0.7, label=label)
    
    ax1.set_ylabel("价格", fontsize=11)
    ax1.legend(fontsize=9, loc="upper left")
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    
    # ---- 子图2：成交量 ----
    vol_colors = ["#d32f2f" if c[i] >= o[i] else "#2e7d32" for i in range(len(df_5y))]
    ax2.bar(dates, v, color=vol_colors, alpha=0.6, width=1)
    ax2.set_ylabel("成交量", fontsize=11)
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    
    # ---- 子图3：MACD ----
    close_arr = df_5y["close"].values
    ema12 = pd.Series(close_arr).ewm(span=12).mean().values
    ema26 = pd.Series(close_arr).ewm(span=26).mean().values
    dif = ema12 - ema26
    dea = pd.Series(dif).ewm(span=9).mean().values
    macd = 2 * (dif - dea)
    
    macd_colors = ["#d32f2f" if v >= 0 else "#2e7d32" for v in macd]
    ax3.bar(dates, macd, color=macd_colors, alpha=0.6, width=1)
    ax3.plot(dates, dif, color="#1a73e8", linewidth=0.8, label="DIF")
    ax3.plot(dates, dea, color="#e67300", linewidth=0.8, label="DEA")
    ax3.axhline(y=0, color="#333", linewidth=0.5)
    ax3.set_ylabel("MACD", fontsize=11)
    ax3.legend(fontsize=8, loc="upper left")
    ax3.grid(True, alpha=0.3)
    ax3.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    
    plt.tight_layout()
    fname = f"{code}_近5年蜡烛图.png"
    fpath = os.path.join(CHART_DIR, fname)
    fig.savefig(fpath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [图] 蜡烛图: {fpath}")
    return fpath


def update_stock_note(code: str, name: str, chart_paths: list[str]):
    """更新个股笔记的图表附件部分，加图片引用"""
    notes = [
        f"{name}({code}",
    ]
    note_dir = os.path.join(VAULT, "01-股票投研", "股票", name)
    if os.path.isdir(note_dir):
        for f in os.listdir(note_dir):
            if f.endswith(".md") and code in f:
                fpath = os.path.join(note_dir, f)
                with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
                
                # 找到图表附件部分或末尾
                chart_marker = "## 📎 图表附件"
                img_refs = "\n".join(
                    f"![{os.path.basename(p)}]({os.path.relpath(p, note_dir)})"
                    for p in chart_paths
                )
                
                if chart_marker in content:
                    # 替换已有内容
                    old = content[content.index(chart_marker):]
                    new = f"{chart_marker}\n\n{img_refs}\n"
                    content = content.replace(old, new)
                else:
                    content += f"\n\n{chart_marker}\n\n{img_refs}\n"
                
                with open(fpath, "w", encoding="utf-8") as fh:
                    fh.write(content)
                print(f"  [笔记] 已更新: {fpath}")
                return
    print(f"  [笔记] 未找到笔记文件: {note_dir}")


def main():
    ap = argparse.ArgumentParser(description="个股K线图生成")
    ap.add_argument("--stock", type=str, help="仅生成指定代码")
    ap.add_argument("--dry-run", action="store_true", help="预览不拉数据")
    a = ap.parse_args()
    
    safe_mkdir(CHART_DIR)
    safe_mkdir(DATA_DIR)
    
    stocks = [s for s in STOCKS if not a.stock or s["code"] == a.stock]
    if not stocks:
        print(f"未找到股票代码: {a.stock}"); sys.exit(1)
    
    print(f"📊 个股K线图生成器")
    print(f"   目标: {', '.join(s['name'] for s in stocks)}")
    print()
    
    for s in stocks:
        print(f"{'='*50}")
        print(f"  {s['name']}({s['code']}.{s['exchange']}) [{s['market']}]")
        print(f"{'='*50}")
        
        if a.dry_run:
            print("  [预览] 跳过数据获取")
            continue
        
        # 取数据
        df = fetch_stock_data(s["code"], s["name"], s["exchange"])
        if df.empty or len(df) < 10:
            print("  ⚠️ 数据不足，跳过")
            continue
        
        # 存CSV
        save_csv(df, s["code"], s["name"])
        
        # 生成图表
        charts = []
        charts.append(plot_full_history(df, s["code"], s["name"], s["market"]))
        charts.append(plot_candlestick_5y(df, s["code"], s["name"], s["market"]))
        
        # 更新笔记
        update_stock_note(s["code"], s["name"], charts)
        print()
    
    print("✅ 完成")


if __name__ == "__main__":
    main()