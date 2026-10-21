#!/usr/bin/env python3
"""
backtest_signals.py — 信号历史回测系统
========================================
对现有技术指标信号做历史回测验证：

信号类型:
  1. MA 金叉/死叉 (MA5×MA10, MA10×MA20)
  2. RSI 超买/超卖 (RSI<30买入, RSI>70卖出)
  3. MACD 金叉/死叉
  4. 布林带突破 (price>上轨卖出, price<下轨买入)
  5. ATR 波动率突破 (ATR>2σ)

输出:
  - workspace/backtest_signals.json (完整回测结果)
  - workspace/backtest_dashboard.html (交互式 ECharts 报告)
  - iMessage 摘要推送

用法:
  python3 backtest_signals.py [--cron] [--days 365]
"""

from __future__ import annotations
import argparse
import json
import math
import os
import subprocess
import sys
import time
import warnings
from collections import defaultdict
from datetime import datetime, timedelta, timezone, date

import duckdb
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=RuntimeWarning)

# ============================================================
# 配置
# ============================================================
WORKSPACE = os.environ.get("HERMES_WORKSPACE", "/Users/xiashuang/harness/stock_daily")
DUCKDB_PATH = os.path.expanduser("~/.hermes/deeppulse/db/astock.duckdb")
PORTFOLIO_FILE = os.path.join(WORKSPACE, "stock_portfolio_enriched.json")
OUTPUT_DIR = WORKSPACE

TODAY = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
IMSG_TO = "285336749@qq.com"

# 回测参数
MIN_DATA_DAYS = 60       # 最少需要60天数据才能回测
FORWARD_DAYS = [1, 3, 5, 10, 20]  # 信号后查看N天收益

# 信号定义
SIGNAL_MA_CROSS = "MA金叉死叉"
SIGNAL_RSI = "RSI超买超卖"
SIGNAL_MACD = "MACD金叉死叉"
SIGNAL_BOLL = "布林带突破"
SIGNAL_ATR = "ATR波动率突破"


def get_db_conn():
    """获取 DuckDB 连接"""
    if not os.path.exists(DUCKDB_PATH):
        raise FileNotFoundError(f"DuckDB not found: {DUCKDB_PATH}")
    return duckdb.connect(DUCKDB_PATH)


def load_portfolio_stocks() -> list[str]:
    """从持仓文件加载股票代码"""
    if not os.path.exists(PORTFOLIO_FILE):
        print(f"⚠️ 持仓文件不存在: {PORTFOLIO_FILE}")
        # 回退：从 DuckDB 取前71只
        conn = get_db_conn()
        codes = [r[0] for r in conn.execute(
            "SELECT DISTINCT code FROM daily_kline ORDER BY code LIMIT 71"
        ).fetchall()]
        conn.close()
        return codes

    with open(PORTFOLIO_FILE, encoding="utf-8") as f:
        portfolio = json.load(f)

    codes = []
    for item in portfolio:
        code = item.get("stock_code", "")
        if code:
            # 标准化: 去掉 .SH/.HK 后缀
            code = code.split(".")[0].replace("SH", "").replace("SZ", "").replace("HK", "")
            code = code.zfill(6)
            codes.append(code)
    return codes


def compute_ma(prices: np.ndarray, period: int) -> np.ndarray:
    """计算移动平均线"""
    if len(prices) < period:
        return np.full_like(prices, np.nan)
    ret = np.full_like(prices, np.nan)
    for i in range(period - 1, len(prices)):
        ret[i] = np.mean(prices[i - period + 1 : i + 1])
    return ret


def compute_rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
    """计算 RSI"""
    if len(prices) < period + 1:
        return np.full_like(prices, np.nan)
    deltas = np.diff(prices)
    ret = np.full_like(prices, np.nan)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    if avg_loss == 0:
        ret[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        ret[period] = 100.0 - (100.0 / (1.0 + rs))
    for i in range(period + 1, len(prices)):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        if avg_loss == 0:
            ret[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            ret[i] = 100.0 - (100.0 / (1.0 + rs))
    return ret


def compute_macd(prices: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """计算 MACD"""
    ema12 = compute_ema(prices, 12)
    ema26 = compute_ema(prices, 26)
    macd_line = ema12 - ema26
    signal_line = compute_ema(macd_line, 9)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def compute_ema(data: np.ndarray, period: int) -> np.ndarray:
    """计算指数移动平均"""
    result = np.full_like(data, np.nan)
    if len(data) < period:
        return result
    multiplier = 2.0 / (period + 1)
    result[period - 1] = np.mean(data[:period])
    for i in range(period, len(data)):
        result[i] = (data[i] - result[i - 1]) * multiplier + result[i - 1]
    return result


def compute_bollinger(prices: np.ndarray, period: int = 20, std_mult: float = 2.0
                      ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """计算布林带"""
    ma = compute_ma(prices, period)
    upper = np.full_like(prices, np.nan)
    lower = np.full_like(prices, np.nan)
    for i in range(period - 1, len(prices)):
        std = np.std(prices[i - period + 1 : i + 1])
        upper[i] = ma[i] + std_mult * std
        lower[i] = ma[i] - std_mult * std
    return upper, ma, lower


def compute_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    """计算 ATR"""
    if len(closes) < period + 1:
        return np.full_like(closes, np.nan)
    tr = np.full_like(closes, np.nan)
    for i in range(1, len(closes)):
        tr[i] = max(highs[i] - lows[i],
                    abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1]))
    atr = np.full_like(closes, np.nan)
    atr[period] = np.mean(tr[1 : period + 1])
    for i in range(period + 1, len(closes)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def detect_signals(code: str, df: pd.DataFrame) -> list[dict]:
    """检测历史信号，返回信号事件列表"""
    signals = []
    closes = df["close"].values.astype(float)
    highs = df["high"].values.astype(float)
    lows = df["low"].values.astype(float)
    volumes = df["volume"].values.astype(float)
    dates = df["trade_date"].values

    n = len(closes)
    if n < MIN_DATA_DAYS:
        return signals

    # 统一日期格式 (从 datetime64 转为 "YYYY-MM-DD")
    clean_dates = [str(d).split(" ")[0].split("T")[0] for d in dates]

    # --- 计算指标 ---
    ma5 = compute_ma(closes, 5)
    ma10 = compute_ma(closes, 10)
    ma20 = compute_ma(closes, 20)
    rsi = compute_rsi(closes)
    macd_line, signal_line, histogram = compute_macd(closes)
    upper, mid, lower = compute_bollinger(closes)
    atr = compute_atr(highs, lows, closes)

    # --- 1. MA 金叉/死叉 (MA5×MA10) ---
    for i in range(1, n):
        if np.isnan(ma5[i]) or np.isnan(ma10[i]) or np.isnan(ma5[i-1]) or np.isnan(ma10[i-1]):
            continue
        # 金叉: MA5 上穿 MA10
        if ma5[i-1] <= ma10[i-1] and ma5[i] > ma10[i]:
            signals.append({
                "code": code, "date": clean_dates[i],
                "signal_type": SIGNAL_MA_CROSS, "direction": "golden_cross",
                "price_at_signal": float(closes[i]),
                "ma5": float(ma5[i]), "ma10": float(ma10[i]),
            })
        # 死叉: MA5 下穿 MA10
        elif ma5[i-1] >= ma10[i-1] and ma5[i] < ma10[i]:
            signals.append({
                "code": code, "date": clean_dates[i],
                "signal_type": SIGNAL_MA_CROSS, "direction": "death_cross",
                "price_at_signal": float(closes[i]),
                "ma5": float(ma5[i]), "ma10": float(ma10[i]),
            })

    # --- 2. RSI 超买/超卖 ---
    for i in range(1, n):
        if np.isnan(rsi[i]) or np.isnan(rsi[i-1]):
            continue
        # 超卖后回升: RSI 从 <30 回到 >30
        if rsi[i-1] <= 30 and rsi[i] > 30:
            signals.append({
                "code": code, "date": clean_dates[i],
                "signal_type": SIGNAL_RSI, "direction": "oversold_recovery",
                "price_at_signal": float(closes[i]),
                "rsi": float(rsi[i]),
            })
        # 超买后回落: RSI 从 >70 回到 <70
        elif rsi[i-1] >= 70 and rsi[i] < 70:
            signals.append({
                "code": code, "date": clean_dates[i],
                "signal_type": SIGNAL_RSI, "direction": "overbought_fall",
                "price_at_signal": float(closes[i]),
                "rsi": float(rsi[i]),
            })

    # --- 3. MACD 金叉/死叉 ---
    for i in range(1, n):
        if np.isnan(histogram[i]) or np.isnan(histogram[i-1]):
            continue
        # 金叉: MACD 上穿信号线 (histogram 由负转正)
        if histogram[i-1] <= 0 and histogram[i] > 0:
            signals.append({
                "code": code, "date": clean_dates[i],
                "signal_type": SIGNAL_MACD, "direction": "golden_cross",
                "price_at_signal": float(closes[i]),
                "macd": float(macd_line[i]),
                "signal": float(signal_line[i]),
            })
        # 死叉: MACD 下穿信号线 (histogram 由正转负)
        elif histogram[i-1] >= 0 and histogram[i] < 0:
            signals.append({
                "code": code, "date": clean_dates[i],
                "signal_type": SIGNAL_MACD, "direction": "death_cross",
                "price_at_signal": float(closes[i]),
                "macd": float(macd_line[i]),
                "signal": float(signal_line[i]),
            })

    # --- 4. 布林带突破 ---
    for i in range(1, n):
        if np.isnan(upper[i]) or np.isnan(lower[i]) or np.isnan(mid[i]):
            continue
        # 突破上轨 (超买，看跌信号)
        if closes[i-1] <= upper[i-1] and closes[i] > upper[i]:
            signals.append({
                "code": code, "date": clean_dates[i],
                "signal_type": SIGNAL_BOLL, "direction": "break_upper",
                "price_at_signal": float(closes[i]),
                "upper": float(upper[i]), "mid": float(mid[i]),
            })
        # 突破下轨 (超卖，看涨信号)
        elif closes[i-1] >= lower[i-1] and closes[i] < lower[i]:
            signals.append({
                "code": code, "date": clean_dates[i],
                "signal_type": SIGNAL_BOLL, "direction": "break_lower",
                "price_at_signal": float(closes[i]),
                "lower": float(lower[i]), "mid": float(mid[i]),
            })

    # --- 5. ATR 波动率突破 (ATR 突然放大 > 2倍前值) ---
    for i in range(2, n):
        if np.isnan(atr[i]) or np.isnan(atr[i-1]):
            continue
        if atr[i-1] > 0 and atr[i] > atr[i-1] * 2.0:
            signals.append({
                "code": code, "date": clean_dates[i],
                "signal_type": SIGNAL_ATR, "direction": "volatility_surge",
                "price_at_signal": float(closes[i]),
                "atr": float(atr[i]), "atr_prev": float(atr[i-1]),
            })

    return signals


def evaluate_signals(signals: list[dict], df: pd.DataFrame) -> dict:
    """评估信号的历史表现

    对每个信号，查看信号后N天的收益表现。
    """
    # 建立日期→价格的映射
    date_map = {str(row["trade_date"]).split(" ")[0].split("T")[0]: {
        "close": float(row["close"]) if pd.notna(row["close"]) else 0,
        "volume": float(row["volume"]) if pd.notna(row["volume"]) else 0,
    } for _, row in df.iterrows()}
    all_dates = sorted(date_map.keys())

    # 按信号类型和方向分组
    grouped: dict[str, list[dict]] = defaultdict(list)
    for s in signals:
        key = f"{s['signal_type']}|{s['direction']}"
        grouped[key].append(s)

    results = {}
    for key, sig_list in grouped.items():
        signal_type, direction = key.split("|")

        # 对每个信号，找信号后N天的价格
        forward_returns = {d: [] for d in FORWARD_DAYS}
        signal_count = 0
        valid_count = 0

        for s in sig_list:
            signal_count += 1
            sig_date = s["date"]
            sig_price = s["price_at_signal"]

            # 找到信号日期在日期列表中的位置
            try:
                sig_idx = all_dates.index(sig_date)
            except ValueError:
                continue

            for fd in FORWARD_DAYS:
                target_idx = sig_idx + fd
                if target_idx < len(all_dates):
                    target_date = all_dates[target_idx]
                    target_price = date_map[target_date]["close"]
                    ret = (target_price - sig_price) / sig_price * 100
                    forward_returns[fd].append(ret)
                    valid_count += 1

        # 计算统计指标
        stats = {}
        for fd, returns in forward_returns.items():
            if len(returns) < 5:
                continue
            arr = np.array(returns)
            wins = np.sum(arr > 0)
            losses = np.sum(arr < 0)
            total = len(arr)
            win_rate = wins / total if total > 0 else 0
            avg_return = float(np.mean(arr))
            std_return = float(np.std(arr))
            # 夏普 (假设无风险利率 0)
            sharpe = avg_return / std_return if std_return > 0 else 0
            # 最大回撤
            cum = np.cumsum(arr)
            peak = np.maximum.accumulate(cum)
            drawdown = cum - peak
            max_dd = float(np.min(drawdown)) if len(drawdown) > 0 else 0
            # 收益风险比
            profit_factor = abs(np.sum(arr[arr > 0]) / np.sum(arr[arr < 0])) if np.sum(arr[arr < 0]) != 0 else float("inf")

            stats[str(fd)] = {
                "count": total,
                "wins": int(wins),
                "losses": int(losses),
                "win_rate": round(win_rate, 4),
                "avg_return_pct": round(avg_return, 4),
                "std_return_pct": round(std_return, 4),
                "sharpe": round(sharpe, 4),
                "max_drawdown_pct": round(max_dd, 4),
                "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else None,
                "best_return_pct": round(float(np.max(arr)), 4) if len(arr) > 0 else 0,
                "worst_return_pct": round(float(np.min(arr)), 4) if len(arr) > 0 else 0,
            }

        results[key] = stats

    return results


def run_backtest(codes: list[str] = None, max_stocks: int = None) -> dict:
    """运行完整回测"""
    conn = get_db_conn()
    portfolio = load_portfolio_stocks()

    if codes:
        test_codes = codes
    else:
        test_codes = portfolio

    if max_stocks:
        test_codes = test_codes[:max_stocks]

    print(f"📊 回测启动: {len(test_codes)} 只股票")
    print(f"  信号类型: {SIGNAL_MA_CROSS}, {SIGNAL_RSI}, {SIGNAL_MACD}, {SIGNAL_BOLL}, {SIGNAL_ATR}")
    print(f"  查看周期: {FORWARD_DAYS} 天")
    print()

    # 第1步：检测所有信号 + 缓存股票数据
    all_signals = []
    stock_data: dict[str, pd.DataFrame] = {}
    processed = 0
    errors = 0

    for code in test_codes:
        code = str(code).zfill(6)

        df = conn.execute(f"""
            SELECT trade_date, open, high, low, close, volume, amount
            FROM daily_kline
            WHERE code = '{code}'
            ORDER BY trade_date
        """).fetchdf()

        if df.empty or len(df) < MIN_DATA_DAYS:
            errors += 1
            continue

        df = df.fillna(0)
        stock_data[code] = df

        try:
            signals = detect_signals(code, df)
            all_signals.extend(signals)
            processed += 1
        except Exception as e:
            errors += 1

        if (processed + errors) % 20 == 0:
            print(f"  进度: {processed+errors}/{len(test_codes)} (信号: {len(all_signals)}个)")

    conn.close()

    print(f"\n✅ 完成: {processed} 只, 失败 {errors} 只")
    print(f"   共检测到 {len(all_signals)} 个信号")

    type_counts = defaultdict(int)
    for s in all_signals:
        type_counts[f"{s['signal_type']}|{s['direction']}"] += 1

    print(f"\n信号分布:")
    for key, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {key}: {count}")

    # 第2步：按信号类型评估表现
    signal_groups: dict[str, list[dict]] = defaultdict(list)
    for s in all_signals:
        key = f"{s['signal_type']}|{s['direction']}"
        signal_groups[key].append(s)

    evaluations = {}
    for sig_key, sig_list in signal_groups.items():
        fwd_ret: dict[int, list[float]] = {d: [] for d in FORWARD_DAYS}

        for s in sig_list:
            code = s["code"]
            df = stock_data.get(code)
            if df is None or df.empty:
                continue

            date_close = {}
            for _, row in df.iterrows():
                try:
                    d = str(row["trade_date"]).split(" ")[0].split("T")[0]
                    c = float(row["close"])
                    if pd.notna(c) and c > 0:
                        date_close[d] = c
                except (ValueError, TypeError):
                    continue

            all_dates = sorted(date_close.keys())
            sig_price = s["price_at_signal"]
            try:
                sig_idx = all_dates.index(s["date"])
            except (ValueError, IndexError):
                continue

            for fd in FORWARD_DAYS:
                target_idx = sig_idx + fd
                if target_idx < len(all_dates):
                    target_price = date_close[all_dates[target_idx]]
                    ret = (target_price - sig_price) / sig_price * 100
                    fwd_ret[fd].append(ret)

        merged = {}
        for fd, returns in fwd_ret.items():
            if len(returns) < 5:
                continue
            arr = np.array(returns)
            wins = np.sum(arr > 0)
            total = len(arr)
            win_rate = wins / total
            avg_ret = float(np.mean(arr))
            std_ret = float(np.std(arr))
            sharpe = avg_ret / std_ret if std_ret > 0 else 0
            cum = np.cumsum(arr)
            peak = np.maximum.accumulate(cum)
            dd = cum - peak
            max_dd = float(np.min(dd)) if len(dd) > 0 else 0
            pos_sum = np.sum(arr[arr > 0])
            neg_sum = np.sum(arr[arr < 0])
            pf = abs(pos_sum / neg_sum) if neg_sum != 0 else (None if pos_sum == 0 else float("inf"))

            merged[str(fd)] = {
                "count": total, "wins": int(wins), "losses": int(total - wins),
                "win_rate": round(win_rate, 4), "avg_return_pct": round(avg_ret, 4),
                "std_return_pct": round(std_ret, 4), "sharpe": round(sharpe, 4),
                "max_drawdown_pct": round(max_dd, 4),
                "profit_factor": round(pf, 2) if pf and pf != float("inf") else None,
                "best_return_pct": round(float(np.max(arr)), 4),
                "worst_return_pct": round(float(np.min(arr)), 4),
            }

        if merged:
            evaluations[sig_key] = merged

    return {
        "run_date": TODAY, "stocks_tested": processed, "stocks_failed": errors,
        "total_signals": len(all_signals),
        "signal_type_counts": {k: v for k, v in sorted(type_counts.items(), key=lambda x: -x[1])},
        "evaluations": evaluations,
    }


def generate_html_report(result: dict) -> str:
    """生成 ECharts HTML 报告"""
    evals = result.get("evaluations", {})

    # 准备图表数据
    signal_names = []
    win_rates_5d = []
    avg_returns_5d = []
    sharpes_5d = []
    signal_counts = []

    for sig_name, data in sorted(evals.items()):
        signal_names.append(sig_name)
        short_name = sig_name.replace("MA金叉死叉", "MA").replace("RSI超买超卖", "RSI") \
            .replace("MACD金叉死叉", "MACD").replace("布林带突破", "BOLL") \
            .replace("ATR波动率突破", "ATR")
        signal_names[-1] = short_name

        if "3" in data:
            win_rates_5d.append(data["3"]["win_rate"] * 100)
            avg_returns_5d.append(data["3"]["avg_return_pct"])
            sharpes_5d.append(data["3"]["sharpe"])
            signal_counts.append(data["3"]["count"])
        elif "5" in data:
            win_rates_5d.append(data["5"]["win_rate"] * 100)
            avg_returns_5d.append(data["5"]["avg_return_pct"])
            sharpes_5d.append(data["5"]["sharpe"])
            signal_counts.append(data["5"]["count"])
        else:
            win_rates_5d.append(0)
            avg_returns_5d.append(0)
            sharpes_5d.append(0)
            signal_counts.append(0)

    # 最佳信号排序
    best_signal = ""
    best_win_rate = 0
    for sig_name, data in evals.items():
        wr = 0
        if "5" in data:
            wr = data["5"]["win_rate"]
        if wr > best_win_rate and data.get("5", {}).get("count", 0) > 10:
            best_win_rate = wr
            best_signal = sig_name

    # 生成 HTML
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>📊 信号回测报告 - {TODAY}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0f1117; color:#e0e0e0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; padding:20px; }}
h1 {{ font-size:24px; margin-bottom:8px; color:#fff; }}
.subtitle {{ color:#888; font-size:14px; margin-bottom:24px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:16px; margin-bottom:24px; }}
.card {{ background:#1a1d27; border-radius:12px; padding:20px; border:1px solid #2a2d37; }}
.card h3 {{ font-size:14px; color:#888; margin-bottom:8px; }}
.card .value {{ font-size:28px; font-weight:700; color:#fff; }}
.card .sub {{ font-size:12px; color:#666; margin-top:4px; }}
.chart-card {{ background:#1a1d27; border-radius:12px; padding:16px; border:1px solid #2a2d37; margin-bottom:16px; }}
.chart-card h3 {{ font-size:14px; color:#888; margin-bottom:12px; }}
.chart {{ width:100%; height:400px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th {{ text-align:left; padding:8px 10px; color:#888; font-weight:500; border-bottom:1px solid #2a2d37; }}
td {{ padding:8px 10px; border-bottom:1px solid #22252f; }}
tr:hover td {{ background:rgba(255,255,255,0.03); }}
.badge-win {{ display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:600; background:#00a854; color:#fff; }}
.badge-lose {{ display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:600; background:#d4380d; color:#fff; }}
.badge-neutral {{ display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:600; background:#fa8c16; color:#fff; }}
</style>
</head>
<body>
<h1>📊 信号历史回测报告</h1>
<p class="subtitle">{TODAY} | 测试 {result['stocks_tested']} 只股票 | 共 {result['total_signals']} 个信号</p>

<div class="grid">
  <div class="card">
    <h3>测试股票</h3>
    <div class="value">{result['stocks_tested']}</div>
    <div class="sub">失败 {result['stocks_failed']} 只</div>
  </div>
  <div class="card">
    <h3>总信号数</h3>
    <div class="value">{result['total_signals']}</div>
    <div class="sub">{len(evals)} 种信号类型</div>
  </div>
  <div class="card">
    <h3>最佳信号 (5日胜率)</h3>
    <div class="value" style="color:{'#00a854' if best_win_rate > 0.5 else '#d4380d'}">{best_signal.split('|')[0] if best_signal else 'N/A'}</div>
    <div class="sub">{best_signal.split('|')[1] if best_signal else ''} | 胜率 {best_win_rate*100:.1f}%</div>
  </div>
  <div class="card">
    <h3>信号种类</h3>
    <div class="value">{len(evals)}</div>
    <div class="sub">MA / RSI / MACD / 布林带 / ATR</div>
  </div>
</div>
"""

    # 胜率图表
    html += """
<div class="chart-card">
  <h3>📈 各信号5日胜率对比</h3>
  <div id="winRateChart" class="chart"></div>
</div>
<script>
const winRateChart = echarts.init(document.getElementById('winRateChart'));
winRateChart.setOption({
  tooltip: { trigger: 'axis' },
  grid: { left: '12%', right: '8%', bottom: '15%' },
  xAxis: { type: 'category', data: """ + json.dumps(signal_names, ensure_ascii=False) + """,
    axisLabel: { color: '#888', rotate: 30 } },
  yAxis: { type: 'value', name: '胜率 (%)', axisLabel: { color: '#888' },
    splitLine: { lineStyle: { color: '#2a2d37' } } },
  series: [{
    type: 'bar',
    data: """ + json.dumps([round(w, 1) for w in win_rates_5d]) + """,
    itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1,
      [{ offset: 0, color: '#00a854' }, { offset: 1, color: '#004d2b' }]),
      borderRadius: [4, 4, 0, 0] },
    label: { show: true, position: 'top', formatter: '{c}%', color: '#888', fontSize: 11 }
  }]
});
</script>
"""

    # 详细数据表
    html += """
<div class="chart-card">
  <h3>📋 信号回测详细数据</h3>
  <table>
  <thead><tr>
    <th>信号类型</th><th>方向</th><th>样本数</th>
    <th>1日胜率</th><th>3日胜率</th><th>5日胜率</th><th>10日胜率</th>
    <th>3日收益</th><th>夏普</th><th>最大回撤</th>
  </tr></thead><tbody>
"""

    for sig_name in sorted(evals.keys()):
        data = evals[sig_name]
        stype, sdir = sig_name.split("|")
        wr1 = f"{data.get('1', {}).get('win_rate', 0)*100:.1f}%" if "1" in data else "-"
        wr3 = f"{data.get('3', {}).get('win_rate', 0)*100:.1f}%" if "3" in data else "-"
        wr5 = f"{data.get('5', {}).get('win_rate', 0)*100:.1f}%" if "5" in data else "-"
        wr10 = f"{data.get('10', {}).get('win_rate', 0)*100:.1f}%" if "10" in data else "-"
        ret3 = f"{data.get('3', {}).get('avg_return_pct', 0):.2f}%" if "3" in data else "-"
        sharpe = f"{data.get('3', {}).get('sharpe', 0):.2f}" if "3" in data else "-"
        mdd = f"{data.get('3', {}).get('max_drawdown_pct', 0):.2f}%" if "3" in data else "-"
        count = data.get("3", {}).get("count", data.get("5", {}).get("count", 0))

        wr3_val = data.get("3", {}).get("win_rate", 0) if "3" in data else 0
        badge = "badge-win" if wr3_val > 0.55 else ("badge-lose" if wr3_val < 0.45 else "badge-neutral")

        html += f"""<tr>
    <td>{stype}</td>
    <td><span class="{badge}">{sdir}</span></td>
    <td>{count}</td>
    <td>{wr1}</td>
    <td>{wr3}</td>
    <td>{wr5}</td>
    <td>{wr10}</td>
    <td>{ret3}</td>
    <td>{sharpe}</td>
    <td>{mdd}</td>
  </tr>"""

    html += """
  </tbody></table>
</div>
"""

    # 信号分布
    signal_dist = json.dumps(
        [{"name": k, "value": v} for k, v in result.get("signal_type_counts", {}).items()],
        ensure_ascii=False
    )

    html += f"""
<div class="chart-card">
  <h3>📊 信号分布</h3>
  <div id="distChart" class="chart" style="height:300px"></div>
</div>
<script>
const distChart = echarts.init(document.getElementById('distChart'));
distChart.setOption({{
  tooltip: {{ trigger: 'item', formatter: '{{b}}: {{c}} ({{d}}%)' }},
  series: [{{
    type: 'pie',
    radius: ['40%', '70%'],
    data: {signal_dist},
    label: {{ color: '#888', fontSize: 11 }},
    itemStyle: {{
      borderRadius: 4,
      color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        {{ offset: 0, color: '#5470c6' }}, {{ offset: 1, color: '#2a3d6b' }}
      ])
    }}
  }}]
}});
</script>
"""

    html += """
</body>
</html>"""

    return html


def save_results(result: dict, html: str):
    """保存结果"""
    json_path = os.path.join(OUTPUT_DIR, "backtest_signals.json")
    html_path = os.path.join(OUTPUT_DIR, "backtest_dashboard.html")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n✅ JSON: {json_path}")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ HTML: {html_path}")


def notify(text: str):
    """推送 iMessage"""
    try:
        subprocess.run(
            ["osascript", "-e",
             f'tell application "Messages" to send "{text}" to buddy "{IMSG_TO}"'],
            timeout=30,
        )
    except Exception:
        pass


def main(cron: bool = False):
    """主函数"""
    if cron:
        print(f"⏰ 定时运行: {TODAY}")
    else:
        print(f"🚀 手动运行: {TODAY}")

    start = time.time()
    result = run_backtest()
    elapsed = time.time() - start

    # 生成报告
    html = generate_html_report(result)
    save_results(result, html)

    # 摘要
    print(f"\n⏱ 耗时: {elapsed:.0f} 秒")

    summary = (
        f"📊 信号回测完成\n"
        f"测试{result['stocks_tested']}只股票，{result['total_signals']}个信号\n"
        f"最佳信号: {max(result['evaluations'].items(), key=lambda x: x[1].get('3',{}).get('win_rate',0))[0] if result['evaluations'] else 'N/A'}"
    )
    print(f"\n{summary}")

    if cron:
        notify(summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="信号历史回测系统")
    parser.add_argument("--cron", action="store_true", help="定时运行模式")
    parser.add_argument("--stocks", type=int, default=None, help="限制股票数量")
    args = parser.parse_args()
    main(cron=args.cron)