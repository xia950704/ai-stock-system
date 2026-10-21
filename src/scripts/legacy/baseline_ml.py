#!/usr/bin/env python3
"""
baseline_ml.py — 股票基准线机器学习系统
==========================================
模块1: 71只长线股票 — 技术指标分位数 + 行业对比
模块2: 3000只短线股票 — 聚类 + 异常检测

输出:
  - workspace/baseline_ml_results.json (完整结构化结果)
  - workspace/baseline_dashboard.html (交互式 ECharts 可视化)
"""

from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import math
import warnings
from contextlib import redirect_stdout, nullcontext
from datetime import datetime, timedelta, timezone, date
from collections import defaultdict

import duckdb
import numpy as np
import pandas as pd

# 抑制 sklearn 数值警告（内部 matmul 的浮点误差，不影响结果）
warnings.filterwarnings("ignore", category=RuntimeWarning, module="sklearn")

# ============================================================================
# 配置
# ============================================================================
WORKSPACE = os.environ.get("HERMES_WORKSPACE", "/Users/xiashuang/harness/stock_daily")
DUCKDB_PATH = os.path.expanduser("~/.hermes/deeppulse/db/astock.duckdb")
PORTFOLIO_FILE = os.path.join(WORKSPACE, "stock_portfolio_enriched.json")
OUTPUT_DIR = WORKSPACE

TODAY = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")

# 数据新鲜度
MAX_STALE_DAYS = 3  # 超过此天数报警

# iMessage 推送
IMSG_TO = "285336749@qq.com"

# 技术指标参数
MA_PERIODS = [5, 10, 20, 60]
RSI_PERIOD = 14
BOLL_PERIOD = 20
BOLL_STD = 2.0

# 聚类参数
N_CLUSTERS = 6
OUTLIER_THRESHOLD = 2.5  # 标准差


# ============================================================================
# 基础设施
# ============================================================================
def check_data_freshness() -> dict:
    """检查 DuckDB 数据最新日期"""
    if not os.path.exists(DUCKDB_PATH):
        return {"fresh": False, "msg": "❌ DuckDB 文件不存在"}
    try:
        con = duckdb.connect(DUCKDB_PATH)
        result = con.execute("SELECT MAX(trade_date) FROM daily_kline").fetchone()
        con.close()
    except Exception as e:
        return {"fresh": False, "msg": f"❌ DuckDB 查询失败: {e}"}

    latest = result[0] if result and result[0] else None
    if latest is None:
        return {"fresh": False, "msg": "❌ daily_kline 表无数据"}

    if isinstance(latest, (date, datetime)):
        today = datetime.now(timezone(timedelta(hours=8))).date()
        d = latest.date() if isinstance(latest, datetime) else latest
        stale = (today - d).days
    else:
        return {"fresh": False, "msg": f"❌ 数据日期格式异常: {latest}"}

    if stale > MAX_STALE_DAYS:
        # 周末/节假日容差：跳过非交易日
        # 周一且最新数据是周五（4天前）→ 只差1个交易日，算新鲜
        # 周日且最新数据是周五（2天前）→ 算新鲜
        # 周六且最新数据是周五（1天前）→ 算新鲜
        weekday = today.weekday()
        if not (weekday == 0 and stale <= 4 or weekday == 6 and stale <= 2 or weekday == 5 and stale <= 1):
            return {"fresh": False, "latest_date": str(latest), "stale_days": stale,
                    "msg": f"⚠️ 数据滞后 {stale} 天（最新: {latest}）"}
    return {"fresh": True, "latest_date": str(latest), "stale_days": stale,
            "msg": f"✅ 数据新鲜（最新: {latest}，滞后 {stale} 天）"}


def _notify(text: str):
    """通过 iMessage 推送通知"""
    try:
        subprocess.run(
            ["imsg", "send", "--to", IMSG_TO, "--text", text[:500],
             "--service", "imessage"],
            capture_output=True, timeout=30,
        )
    except Exception:
        pass  # 推送失败不阻塞主流程


# ============================================================================
# 工具函数
# ============================================================================
def safe_mean(lst):
    return sum(lst) / len(lst) if lst else 0.0


def safe_std(lst):
    if len(lst) < 2:
        return 0.0
    m = safe_mean(lst)
    return math.sqrt(sum((x - m) ** 2 for x in lst) / (len(lst) - 1))


def percentile(data, pct):
    if not data:
        return 0.0
    s = sorted(data)
    k = (len(s) - 1) * pct / 100.0
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return s[lo]
    return s[lo] * (hi - k) + s[hi] * (k - lo)


# ============================================================================
# 技术指标计算
# ============================================================================
def compute_ma(prices, period):
    """移动平均"""
    if len(prices) < period:
        return None
    return safe_mean(prices[-period:])


def compute_rsi(prices, period=RSI_PERIOD):
    """RSI (Relative Strength Index)"""
    if len(prices) < period + 1:
        return None
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas[-period:]]
    losses = [-d if d < 0 else 0 for d in deltas[-period:]]
    avg_gain = safe_mean(gains)
    avg_loss = safe_mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def compute_macd(prices, fast=12, slow=26, signal=9):
    """MACD (Moving Average Convergence Divergence)"""
    if len(prices) < slow + signal:
        return None, None, None
    # 计算完整MACD序列
    macd_series = []
    for i in range(slow - 1, len(prices)):
        ef = _ema(prices[:i + 1], fast)
        es = _ema(prices[:i + 1], slow)
        if ef is None or es is None:
            macd_series.append(None)
        else:
            macd_series.append(ef - es)
    valid = [x for x in macd_series if x is not None]
    if len(valid) < signal:
        return None, None, None
    macd_line = valid[-1]
    signal_line = safe_mean(valid[-signal:])
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _ema(data, period):
    if len(data) < period:
        return None
    multiplier = 2 / (period + 1)
    ema = safe_mean(data[:period])
    for price in data[period:]:
        ema = (price - ema) * multiplier + ema
    return ema


def compute_bollinger(prices, period=BOLL_PERIOD, std_mult=BOLL_STD):
    """布林带"""
    if len(prices) < period:
        return None, None, None
    window = prices[-period:]
    mid = safe_mean(window)
    sd = safe_std(window)
    upper = mid + std_mult * sd
    lower = mid - std_mult * sd
    return upper, mid, lower


def compute_atr(highs, lows, closes, period=14):
    """ATR (Average True Range)"""
    if len(highs) < period + 1:
        return None
    trs = []
    for i in range(1, len(highs)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    if len(trs) < period:
        return None
    return safe_mean(trs[-period:])


# ============================================================================
# 模块1: 71只长线基准线
# ============================================================================
def load_portfolio():
    """加载71只股票信息"""
    if not os.path.exists(PORTFOLIO_FILE):
        raise FileNotFoundError(f"投资组合文件不存在: {PORTFOLIO_FILE}")
    with open(PORTFOLIO_FILE) as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"投资组合文件格式错误: {e}") from e
    if not isinstance(data, list):
        raise ValueError(f"投资组合数据应为列表，实际为 {type(data).__name__}")
    return data


def compute_baseline_71_stocks():
    """计算71只股票的技术指标分位基准线"""
    print(f"\n{'='*60}")
    print(f"模块1: 71只长线股票基准线")
    print(f"{'='*60}")

    portfolio = load_portfolio()
    con = duckdb.connect(DUCKDB_PATH)

    baselines = []
    missing_count = 0

    for stock in portfolio:
        code = stock["stock_code"]
        name = stock["stock_name"]
        sector = stock.get("sector", "未知")

        # 提取纯数字代码（去掉 .SH/.SZ/.HK/.BJ 后缀）
        pure_code = code.split(".")[0]
        exchange = code.split(".")[-1] if "." in code else "A"

        # HK/BJ 股票不在 DuckDB 中，跳过
        if exchange in ("HK", "BJ"):
            missing_count += 1
            baselines.append({
                "stock_name": name,
                "stock_code": code,
                "sector": sector,
                "data_points": 0,
                "status": "no_data",
                "note": f"{exchange} 股票无 A 股历史数据",
                "rsi": None,
                "signal_score": None,
            })
            continue

        # 从 DuckDB 提取历史数据
        query = """
        SELECT trade_date, open, high, low, close, volume, amount, turnover
        FROM daily_kline
        WHERE code = ?
        ORDER BY trade_date
        """
        rows = con.execute(query, [pure_code]).fetchall()

        if len(rows) < 20:
            missing_count += 1
            baselines.append({
                "stock_name": name,
                "stock_code": code,
                "sector": sector,
                "data_points": len(rows),
                "status": "insufficient_data",
            })
            continue

        # 解析数据
        dates = [r[0] for r in rows]
        highs = [r[2] for r in rows]
        lows = [r[3] for r in rows]
        closes = [r[4] for r in rows]
        volumes = [r[5] for r in rows]
        turnovers = [r[7] if r[7] else 0 for r in rows]

        current_price = closes[-1]

        # RSI (先计算当前值)
        rsi = compute_rsi(closes)

        # 计算RSI的历史分位
        rsi_history = [compute_rsi(closes[:i + 1]) for i in range(20, len(closes))]
        rsi_history = [r for r in rsi_history if r is not None]
        rsi_quartile = round(
            sum(1 for v in rsi_history if v <= rsi) / len(rsi_history) * 100, 1
        ) if rsi and rsi_history else None

        # 计算价格位置分位
        price_positions = []
        for i in range(20, len(closes) + 1):
            window = closes[i - 20 : i]
            low = min(window)
            high = max(window)
            if high > low:
                pos = (closes[i - 1] - low) / (high - low)
            else:
                pos = 0.5
            price_positions.append(pos)
        price_pos_quartile = round(
            sum(1 for v in price_positions if v <= price_positions[-1]) / len(price_positions) * 100, 1
        ) if price_positions else None

        # MA 均线
        ma5 = compute_ma(closes, 5)
        ma10 = compute_ma(closes, 10)
        ma20 = compute_ma(closes, 20)
        ma60 = compute_ma(closes, 60)

        # 价格在均线上的位置
        ma_spreads = {}
        for label, ma_val in [("MA5", ma5), ("MA10", ma10), ("MA20", ma20), ("MA60", ma60)]:
            if ma_val and ma_val > 0:
                ma_spreads[label] = (current_price - ma_val) / ma_val * 100

        # MACD
        macd_line, signal_line, histogram = compute_macd(closes)

        # 布林带
        boll_upper, boll_mid, boll_lower = compute_bollinger(closes)

        # ATR
        atr = compute_atr(highs, lows, closes)

        # 20日波动率
        returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
        vol_20d = safe_std(returns[-20:]) * math.sqrt(252) * 100 if returns else 0

        # 近期趋势（近5/10/20日涨幅）
        chg_5d = (closes[-1] / closes[-6] - 1) * 100 if len(closes) >= 6 else 0
        chg_10d = (closes[-1] / closes[-11] - 1) * 100 if len(closes) >= 11 else 0
        chg_20d = (closes[-1] / closes[-21] - 1) * 100 if len(closes) >= 21 else 0

        # 成交量变化
        avg_vol_20 = safe_mean(volumes[-20:])
        vol_ratio = volumes[-1] / avg_vol_20 if avg_vol_20 > 0 else 1

        # 计算"基准分位数"（当前值在历史分布中的位置）
        baseline = {
            "stock_name": name,
            "stock_code": code,
            "sector": sector,
            "data_points": len(closes),
            "current_price": round(current_price, 2),
            "rsi": round(rsi, 2) if rsi else None,
            "rsi_quartile": rsi_quartile,
            "price_vs_ma5": round(ma_spreads.get("MA5", 0), 2),
            "price_vs_ma20": round(ma_spreads.get("MA20", 0), 2),
            "price_vs_ma60": round(ma_spreads.get("MA60", 0), 2),
            "bollinger_position": round(
                (current_price - boll_lower) / (boll_upper - boll_lower) * 100 if boll_upper and boll_lower and boll_upper > boll_lower else 50
            , 1),
            "atr": round(atr, 4) if atr else None,
            "volatility_20d": round(vol_20d, 2),
            "chg_5d": round(chg_5d, 2),
            "chg_10d": round(chg_10d, 2),
            "chg_20d": round(chg_20d, 2),
            "volume_ratio": round(vol_ratio, 2),
            "price_position_20d": price_pos_quartile,
        }

        # 买入/卖出信号评估
        signal = _evaluate_signal(baseline)
        baseline["signal"] = signal
        baseline["signal_score"] = signal["score"]

        baselines.append(baseline)

    con.close()

    # 按行业分组计算对比基准
    sector_benchmarks = _compute_sector_benchmarks(baselines)

    return baselines, sector_benchmarks, missing_count


def _evaluate_signal(baseline):
    """基于技术指标评估买入/卖出信号"""
    score = 50  # 中性
    reasons = []

    rsi = baseline.get("rsi")
    if rsi is not None:
        if rsi < 30:
            score += 15
            reasons.append(f"RSI={rsi} 超卖")
        elif rsi < 40:
            score += 8
        elif rsi > 70:
            score -= 15
            reasons.append(f"RSI={rsi} 超买")
        elif rsi > 60:
            score -= 8

    boll_pos = baseline.get("bollinger_position", 50)
    if boll_pos < 20:
        score += 12
        reasons.append(f"布林带低位={boll_pos}%")
    elif boll_pos > 80:
        score -= 12
        reasons.append(f"布林带高位={boll_pos}%")

    price_vs_ma20 = baseline.get("price_vs_ma20", 0)
    if price_vs_ma20 < -5:
        score += 10
        reasons.append(f"跌破MA20 {price_vs_ma20}%")
    elif price_vs_ma20 > 10:
        score -= 10
        reasons.append(f"远离MA20 {price_vs_ma20}%")

    vol_ratio = baseline.get("volume_ratio", 1)
    if vol_ratio > 2.0:
        score -= 5
        reasons.append(f"放量{vol_ratio}x 警惕")
    elif vol_ratio < 0.5 and boll_pos < 30:
        score += 5
        reasons.append("缩量回踩")

    # 确定信号等级
    if score >= 75:
        level = "强买入"
    elif score >= 60:
        level = "买入"
    elif score >= 40:
        level = "观望"
    elif score >= 25:
        level = "卖出"
    else:
        level = "强卖出"

    return {
        "level": level,
        "score": max(0, min(100, score)),
        "reasons": reasons,
    }


def _compute_sector_benchmarks(baselines):
    """按行业计算基准统计"""
    sectors = defaultdict(list)
    for b in baselines:
        if b.get("rsi") is not None and b.get("signal_score") is not None:
            sectors[b["sector"]].append(b)

    benchmarks = {}
    for sector, stocks in sectors.items():
        rsis = [s["rsi"] for s in stocks]
        scores = [s["signal_score"] for s in stocks]
        prices = [s["current_price"] for s in stocks]
        benchmarks[sector] = {
            "stock_count": len(stocks),
            "rsi_mean": round(safe_mean(rsis), 1),
            "rsi_std": round(safe_std(rsis), 1),
            "score_mean": round(safe_mean(scores), 1),
            "score_std": round(safe_std(scores), 1),
            "avg_price": round(safe_mean(prices), 2),
        }

    return benchmarks


# ============================================================================
# 模块2: 3000只短线聚类
# ============================================================================
def compute_baseline_clusters():
    """对3000只股票进行聚类，建立基准线"""
    print(f"\n{'='*60}")
    print(f"模块2: 3000只短线聚类基准线")
    print(f"{'='*60}")

    con = duckdb.connect(DUCKDB_PATH)

    # 提取所有股票的最新数据 + 技术指标
    query = """
    SELECT code, close, volume, turnover,
           LAG(close, 1) OVER (PARTITION BY code ORDER BY trade_date) as prev_close,
           LAG(close, 5) OVER (PARTITION BY code ORDER BY trade_date) as close_5d_ago,
           LAG(close, 10) OVER (PARTITION BY code ORDER BY trade_date) as close_10d_ago,
           LAG(close, 20) OVER (PARTITION BY code ORDER BY trade_date) as close_20d_ago
    FROM daily_kline
    ORDER BY trade_date DESC
    """
    # 只取最新一条
    latest = con.execute(query).fetchdf()
    latest = latest.drop_duplicates(subset=["code"], keep="first")

    # 计算指标
    latest["chg_1d"] = ((latest["close"] / latest["prev_close"].replace(0, np.nan)) - 1) * 100
    latest["chg_5d"] = ((latest["close"] / latest["close_5d_ago"].replace(0, np.nan)) - 1) * 100
    latest["chg_10d"] = ((latest["close"] / latest["close_10d_ago"].replace(0, np.nan)) - 1) * 100
    latest["chg_20d"] = ((latest["close"] / latest["close_20d_ago"].replace(0, np.nan)) - 1) * 100
    latest["turnover_pct"] = latest["turnover"]

    # 过滤极端异常值（新上市/停牌复牌/数据错误）
    mask = (
        (latest["chg_1d"].abs() <= 50) &
        (latest["chg_5d"].abs() <= 50) &
        (latest["chg_10d"].abs() <= 70) &
        (latest["chg_20d"].abs() <= 70) &
        (latest["turnover_pct"] >= 0) &
        (latest["turnover_pct"] <= 50) &
        (latest["close"] > 0)
    )
    latest = latest[mask]

    # 填充剩余缺失值
    for col in ["chg_1d", "chg_5d", "chg_10d", "chg_20d", "turnover_pct"]:
        latest[col] = latest[col].fillna(0)

    # 特征矩阵
    features = latest[["chg_1d", "chg_5d", "chg_10d", "chg_20d", "turnover_pct"]].values
    codes = latest["code"].values
    prices = latest["close"].values

    # 进一步压缩极端值防止 sklearn 数值溢出
    np.clip(features[:, :4], -50, 50, out=features[:, :4])  # 涨跌幅
    np.clip(features[:, 4], 0, 20, out=features[:, 4])  # 换手率

    # 标准化
    feature_means = np.nanmean(features, axis=0)
    feature_stds = np.nanstd(features, axis=0)
    feature_stds = np.clip(feature_stds, 1e-6, None)  # 防止除零
    features_norm = (features - feature_means) / feature_stds

    # 裁剪标准化后数据，防止极端值导致 sklearn 数值溢出
    features_norm = np.clip(features_norm, -5, 5)

    # KMeans 聚类
    try:
        from sklearn.cluster import KMeans
    except ImportError:
        print("  sklearn 不可用，跳过聚类")
        return None, None

    kmeans = KMeans(n_clusters=N_CLUSTERS, random_state=42, n_init=1)
    labels = kmeans.fit_predict(features_norm)

    # 按聚类整理
    cluster_centers_raw = kmeans.cluster_centers_
    cluster_centers = []
    for i, center in enumerate(cluster_centers_raw):
        center_denorm = center * feature_stds + feature_means
        cluster_centers.append({
            "cluster_id": i,
            "chg_1d_mean": round(center_denorm[0], 2),
            "chg_5d_mean": round(center_denorm[1], 2),
            "chg_10d_mean": round(center_denorm[2], 2),
            "chg_20d_mean": round(center_denorm[3], 2),
            "turnover_mean": round(center_denorm[4], 2),
            "description": _describe_cluster(center_denorm),
        })

    # 计算每个股票的偏离度
    outliers = []
    for i, (code, price) in enumerate(zip(codes, prices)):
        cluster_id = labels[i]
        dist = np.linalg.norm(features_norm[i] - cluster_centers_raw[cluster_id])
        cluster_mean_dist = np.mean(
            [np.linalg.norm(features_norm[j] - cluster_centers_raw[cluster_id])
             for j in range(len(labels)) if labels[j] == cluster_id]
        )
        if dist > OUTLIER_THRESHOLD * cluster_mean_dist:
            outliers.append({
                "stock_code": code,
                "cluster_id": int(cluster_id),
                "distance": round(dist, 2),
                "cluster_avg_distance": round(cluster_mean_dist, 2),
                "outlier_ratio": round(dist / cluster_mean_dist, 2) if cluster_mean_dist > 0 else 0,
                "chg_1d": round(float(features[i][0]), 2),
                "chg_5d": round(float(features[i][1]), 2),
                "chg_10d": round(float(features[i][2]), 2),
                "chg_20d": round(float(features[i][3]), 2),
                "turnover": round(float(features[i][4]), 2),
                "price": round(float(price), 2),
            })

    outliers.sort(key=lambda x: x["outlier_ratio"], reverse=True)

    # 聚类统计
    cluster_stats = defaultdict(lambda: {"count": 0, "codes": []})
    for code, label in zip(codes, labels):
        cluster_stats[int(label)]["count"] += 1
        cluster_stats[int(label)]["codes"].append(code)

    cluster_summary = []
    for cid in sorted(cluster_stats.keys()):
        cs = cluster_stats[cid]
        cluster_summary.append({
            "cluster_id": cid,
            "stock_count": cs["count"],
            "outlier_count": sum(1 for o in outliers if o["cluster_id"] == cid),
            "description": cluster_centers[cid]["description"],
        })

    con.close()

    result = {
        "n_stocks": len(codes),
        "n_clusters": N_CLUSTERS,
        "feature_columns": ["chg_1d", "chg_5d", "chg_10d", "chg_20d", "turnover_pct"],
        "cluster_centers": cluster_centers,
        "cluster_summary": cluster_summary,
        "n_outliers": len(outliers),
        "outliers": outliers[:50],  # 前50个异常
    }

    return result, cluster_centers


def _describe_cluster(center):
    """描述聚类特征"""
    chg_1d, chg_5d, chg_10d, chg_20d, turnover = center
    parts = []

    if chg_20d > 10:
        parts.append("强势上涨")
    elif chg_20d < -10:
        parts.append("弱势下跌")
    else:
        parts.append("横盘震荡")

    if turnover > 5:
        parts.append("高换手")
    elif turnover < 2:
        parts.append("低换手")

    if chg_5d > chg_20d * 2:
        parts.append("近期加速")

    return " · ".join(parts)


# ============================================================================
# 主流程
# ============================================================================
def main(cron=False):
    _null = None
    if cron:
        out = lambda *a, **kw: None
        notify = _notify
        _null = open(os.devnull, "w")
        stdout_mgr = redirect_stdout(_null)
    else:
        out = lambda *a, **kw: print(*a, **kw)
        notify = lambda *a: None
        stdout_mgr = nullcontext()

    with stdout_mgr:
        # 1. 数据新鲜度检查
        freshness = check_data_freshness()
        out(freshness["msg"])
        if not freshness["fresh"]:
            msg = f"[baseline_ml] {freshness['msg']}"
            notify(msg)
            if cron:
                print(f"⏭️ 数据陈旧，跳过本次运行: {freshness['msg']}")
                return  # 非错误，数据陈旧是预期情况
            # 交互模式继续，但给警告

        out("=" * 60)
        out("股票基准线机器学习系统")
        out(f"日期: {TODAY}")
        out("=" * 60)

        # 模块1: 71只长线
        t0 = datetime.now()
        baselines, sector_benchmarks, missing = compute_baseline_71_stocks()
        t1 = datetime.now()

        # 模块2: 3000只短线
        t2 = datetime.now()
        cluster_result, cluster_centers = compute_baseline_clusters()
        t3 = datetime.now()

        # 保存结果
        output_path = os.path.join(OUTPUT_DIR, "baseline_ml_results.json")
        has_data = sum(1 for b in baselines if b.get("rsi") is not None)
        signal_dist = {}
        for b in baselines:
            sig = b.get("signal", {}).get("level", "unknown")
            signal_dist[sig] = signal_dist.get(sig, 0) + 1

        output = {
            "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
            "data_freshness": freshness,
            "71_stocks": {
                "baselines": baselines,
                "sector_benchmarks": sector_benchmarks,
                "data_missing": missing,
                "signal_distribution": signal_dist,
            },
            "3000_stocks": cluster_result,
            "timing": {
                "71_stocks_sec": (t1 - t0).total_seconds(),
                "3000_stocks_sec": (t3 - t2).total_seconds(),
                "total_sec": (t3 - t0).total_seconds(),
            },
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        out(f"\n{'='*60}")
        out(f"结果已保存: {output_path}")
        out(f"71只: {len(baselines)} 条 (有数据: {has_data}, 缺失: {missing})")
        if cluster_result:
            out(f"3000只: {cluster_result['n_outliers']} 个异常候选")
        out(f"总耗时: {(t3 - t0).total_seconds():.1f}秒")
        out(f"{'='*60}")

        # cron 模式推送摘要
        if cron:
            sig_lines = " | ".join(f"{k}={v}" for k, v in sorted(signal_dist.items()) if k != "unknown")
            n_outliers = cluster_result["n_outliers"] if cluster_result else 0
            summary = (
                f"[baseline_ml] ML基准线刷新完成\n"
                f"71只: {has_data}只有数据, 信号分布: {sig_lines}\n"
                f"3000只: {n_outliers}个异常候选\n"
                f"耗时: {(t3 - t0).total_seconds():.1f}s"
            )
            notify(summary)

    if _null is not None:
        _null.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="股票基准线 ML 系统")
    parser.add_argument("--cron", action="store_true", help="cron 静默模式，结果推 iMessage")
    args = parser.parse_args()
    main(cron=args.cron)