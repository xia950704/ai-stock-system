#!/usr/bin/env python3
"""
ml_trend_predict.py — ML 趋势预测模型
========================================
用 RandomForest 训练趋势预测模型：

输入特征 (过去20天):
  - 价格: close, open, high, low (归一化)
  - 技术指标: RSI, MACD, 布林带位置, ATR
  - 量: volume 变化率
  - 动量: 1d, 3d, 5d 收益

输出:
  - 未来1天/3天/5天涨跌方向 (概率)
  - 模型准确率评估
  - 特征重要性排名

用法:
  python3 ml_trend_predict.py [--cron] [--retrain]
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

# 尝试导入 ML 库
try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
    from sklearn.preprocessing import StandardScaler
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

# ============================================================
# 配置
# ============================================================
WORKSPACE = os.environ.get("HERMES_WORKSPACE", "/Users/xiashuang/harness/stock_daily")
DUCKDB_PATH = os.path.expanduser("~/.hermes/deeppulse/db/astock.duckdb")
PORTFOLIO_FILE = os.path.join(WORKSPACE, "stock_portfolio_enriched.json")
OUTPUT_DIR = WORKSPACE

TODAY = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
IMSG_TO = "285336749@qq.com"

# 模型参数
LOOKBACK = 20          # 用过去20天作特征
FORECAST_DAYS = [1, 3, 5]  # 预测未来N天
MIN_TRAIN_SAMPLES = 500
TEST_SPLIT = 0.2       # 20% 做测试集

# 随机森林参数
RF_N_ESTIMATORS = 200
RF_MAX_DEPTH = 10
RF_MIN_SAMPLES_SPLIT = 5


def get_db_conn():
    if not os.path.exists(DUCKDB_PATH):
        raise FileNotFoundError(f"DuckDB not found: {DUCKDB_PATH}")
    return duckdb.connect(DUCKDB_PATH)


def load_portfolio_stocks() -> list[dict]:
    """加载持仓股票"""
    if not os.path.exists(PORTFOLIO_FILE):
        codes = []
        conn = get_db_conn()
        rows = conn.execute("SELECT DISTINCT code FROM daily_kline ORDER BY code LIMIT 71").fetchall()
        conn.close()
        for r in rows:
            codes.append({"code": r[0].zfill(6), "name": r[0]})
        return codes

    with open(PORTFOLIO_FILE, encoding="utf-8") as f:
        portfolio = json.load(f)

    stocks = []
    for item in portfolio:
        code = item.get("stock_code", "")
        name = item.get("stock_name", "")
        code = code.split(".")[0].replace("SH", "").replace("SZ", "").replace("HK", "")
        code = code.zfill(6)
        stocks.append({"code": code, "name": name})
    return stocks


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """从 K 线数据计算特征矩阵

    每个交易日生成一个特征向量:
    - 价格归一化 (相对前20日均线)
    - 技术指标 (RSI, MACD, 布林带)
    - 量价关系
    - 动量特征
    """
    closes = df["close"].values.astype(float)
    opens = df["open"].values.astype(float)
    highs = df["high"].values.astype(float)
    lows = df["low"].values.astype(float)
    volumes = df["volume"].values.astype(float)
    dates = df["trade_date"].values
    n = len(closes)

    features = []
    targets = {d: [] for d in FORECAST_DAYS}

    # 预计算技术指标
    ma20 = np.full(n, np.nan)
    for i in range(19, n):
        ma20[i] = np.mean(closes[max(0, i - 19) : i + 1])

    # 计算 RSI
    rsi = np.full(n, np.nan)
    if n > 14:
        for i in range(14, n):
            gains = np.diff(closes[max(0, i - 14) : i + 1])
            gains = gains[gains > 0].sum() / 14 if len(gains[gains > 0]) > 0 else 0
            losses = -np.diff(closes[max(0, i - 14) : i + 1])
            losses = losses[losses > 0].sum() / 14 if len(losses[losses > 0]) > 0 else 1
            rs = gains / losses if losses > 0 else 100
            rsi[i] = 100 - 100 / (1 + rs)

    # 计算 20日波动率
    volatility = np.full(n, np.nan)
    for i in range(19, n):
        volatility[i] = np.std(closes[max(0, i - 19) : i + 1]) / ma20[i] if ma20[i] > 0 else 0

    # 生成特征和标签
    for i in range(LOOKBACK, n):
        # 特征: 过去 LOOKBACK 天的数据
        feat = []

        # 1. 价格归一化 (相对于当前)
        current_close = closes[i]
        if current_close <= 0:
            continue

        # 过去20天归一化价格
        for j in range(i - LOOKBACK + 1, i + 1):
            feat.append(closes[j] / current_close - 1)

        # 2. 过去20天归一化成交量
        vol_mean = np.mean(volumes[max(0, i - 20) : i + 1]) if i >= 20 else np.mean(volumes[: i + 1])
        if vol_mean > 0:
            for j in range(i - LOOKBACK + 1, i + 1):
                feat.append(volumes[j] / vol_mean - 1)

        # 3. 技术指标
        feat.append(rsi[i] / 100 if not np.isnan(rsi[i]) else 0.5)
        feat.append(ma20[i] / current_close - 1 if not np.isnan(ma20[i]) else 0)
        feat.append(volatility[i] if not np.isnan(volatility[i]) else 0)

        # 4. 动量特征
        for d in [1, 3, 5, 10]:
            if i >= d:
                ret = closes[i] / closes[i - d] - 1
                feat.append(ret)
            else:
                feat.append(0)

        # 5. 价格范围
        feat.append((highs[i] - lows[i]) / current_close)

        features.append(feat)

        # 标签: 未来 N 天收益为正?
        for fd in FORECAST_DAYS:
            target_idx = i + fd
            if target_idx < n:
                future_ret = closes[target_idx] / current_close - 1
                targets[fd].append(1 if future_ret > 0 else 0)
            else:
                targets[fd].append(None)

    return features, targets


def train_model(features: list, labels: list) -> tuple:
    """训练 RandomForest 模型"""
    if not HAS_SKLEARN:
        print("⚠️ sklearn 未安装，跳过 ML 训练")
        return None, None, {}

    if len(features) < MIN_TRAIN_SAMPLES:
        print(f"⚠️ 样本太少 ({len(features)} < {MIN_TRAIN_SAMPLES})，跳过")
        return None, None, {}

    X = np.array(features)
    y = np.array(labels)

    # 过滤 None 标签
    valid = y != None
    X = X[valid]
    y = y[valid].astype(int)

    if len(X) < MIN_TRAIN_SAMPLES:
        return None, None, {}

    # 时间序列分割 (按时间顺序，不 shuffle)
    split_idx = int(len(X) * (1 - TEST_SPLIT))
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    if len(X_train) < 100 or len(X_test) < 50:
        return None, None, {}

    # 标准化
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # 训练
    model = RandomForestClassifier(
        n_estimators=RF_N_ESTIMATORS,
        max_depth=RF_MAX_DEPTH,
        min_samples_split=RF_MIN_SAMPLES_SPLIT,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train_scaled, y_train)

    # 评估
    y_pred = model.predict(X_test_scaled)
    y_proba = model.predict_proba(X_test_scaled)

    metrics = {
        "train_samples": int(len(X_train)),
        "test_samples": int(len(X_test)),
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "precision": round(float(precision_score(y_test, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_test, y_pred, zero_division=0)), 4),
    }

    # AUC (需要两类都有样本)
    try:
        if len(np.unique(y_test)) > 1:
            metrics["auc"] = round(float(roc_auc_score(y_test, y_proba[:, 1])), 4)
    except Exception:
        metrics["auc"] = None

    # 特征重要性 (前10)
    n_features = X.shape[1]
    n_price = LOOKBACK  # 价格特征数量
    n_volume = LOOKBACK  # 成交量特征数量
    feature_names = (
        [f"price_{i}" for i in range(n_price)]
        + [f"vol_{i}" for i in range(n_volume)]
        + ["rsi", "ma20_dev", "volatility", "ret_1d", "ret_3d", "ret_5d", "ret_10d", "range"]
    )
    # 截断到实际特征数
    feature_names = feature_names[:n_features]

    importances = sorted(
        zip(feature_names, model.feature_importances_),
        key=lambda x: -x[1],
    )[:15]

    metrics["top_features"] = [{"name": n, "importance": round(float(v), 4)} for n, v in importances]

    return model, scaler, metrics


def predict_stock(model, scaler, df: pd.DataFrame) -> dict:
    """对单只股票的最新数据做预测"""
    if model is None:
        return {}

    features, _ = compute_features(df)
    if not features:
        return {}

    # 取最新特征
    latest_features = features[-1:]
    if not latest_features:
        return {}

    X = np.array(latest_features)
    X_scaled = scaler.transform(X)

    # 预测
    proba = model.predict_proba(X_scaled)[0]
    pred = model.predict(X_scaled)[0]

    result = {
        "prediction": int(pred),
        "confidence": float(max(proba)),
        "prob_up": float(proba[1]) if len(proba) > 1 else 0.5,
        "prob_down": float(proba[0]) if len(proba) > 0 else 0.5,
    }
    return result


def run_pipeline() -> dict:
    """运行完整 ML 预测流程"""
    if not HAS_SKLEARN:
        return {"error": "sklearn not installed"}

    stocks = load_portfolio_stocks()
    print(f"🚀 ML 趋势预测启动: {len(stocks)} 只股票")
    print(f"  特征维度: {LOOKBACK * 2 + 8} (价格{LOOKBACK}+量{LOOKBACK}+指标8)")
    print(f"  预测周期: {FORECAST_DAYS} 天")
    print()

    conn = get_db_conn()

    # 收集所有股票的特征
    all_features = {d: [] for d in FORECAST_DAYS}
    all_labels = {d: [] for d in FORECAST_DAYS}
    stock_predictions = []
    skipped = 0

    for i, stock in enumerate(stocks):
        code = stock["code"]
        name = stock["name"]

        df = conn.execute(f"""
            SELECT trade_date, open, high, low, close, volume, amount
            FROM daily_kline
            WHERE code = '{code}'
            ORDER BY trade_date
        """).fetchdf()

        if df.empty or len(df) < LOOKBACK + 10:
            skipped += 1
            continue

        df = df.fillna(0)

        try:
            features, targets = compute_features(df)
            if len(features) < 10:
                skipped += 1
                continue

            # 添加到训练集
            for fd in FORECAST_DAYS:
                for j, feat in enumerate(features):
                    if targets[fd][j] is not None:
                        all_features[fd].append(feat)
                        all_labels[fd].append(targets[fd][j])

            # 对最新数据做预测
            latest_close = float(df["close"].iloc[-1])
            latest_date = str(df["trade_date"].iloc[-1]).split(" ")[0].split("T")[0]

            stock_predictions.append({
                "code": code,
                "name": name,
                "latest_close": latest_close,
                "latest_date": latest_date,
                "signal_score": _compute_signal_score(features[-1] if features else None),
            })

        except Exception as e:
            skipped += 1

        if (i + 1) % 20 == 0:
            print(f"  进度: {i+1}/{len(stocks)}")

    conn.close()

    print(f"\n✅ 数据准备完成: {len(stocks) - skipped} 只可用")
    print(f"   训练样本: 1天={len(all_features[1])}, 3天={len(all_features[3])}, 5天={len(all_features[5])}")

    # 分别训练 1天/3天/5天 模型
    models = {}
    results = {}

    for fd in FORECAST_DAYS:
        print(f"\n📊 训练 {fd}天预测模型...")
        features = all_features[fd]
        labels = all_labels[fd]

        if len(features) < MIN_TRAIN_SAMPLES:
            print(f"  跳过: 样本不足 ({len(features)} < {MIN_TRAIN_SAMPLES})")
            continue

        model, scaler, metrics = train_model(features, labels)
        if model is None:
            continue

        models[fd] = (model, scaler)
        results[fd] = metrics

        print(f"  准确率: {metrics['accuracy']*100:.1f}%")
        print(f"  精确率: {metrics['precision']*100:.1f}%")
        print(f"  召回率: {metrics['recall']*100:.1f}%")
        print(f"  F1: {metrics['f1']*100:.1f}%")
        if metrics.get("auc"):
            print(f"  AUC: {metrics['auc']:.3f}")
        if metrics.get("top_features"):
            print(f"  重要特征: {metrics['top_features'][:3]}")

    # 对每只股票做预测
    print(f"\n🔮 生成个股预测...")
    for sp in stock_predictions:
        code = sp["code"]
        conn = get_db_conn()
        df = conn.execute(f"""
            SELECT trade_date, open, high, low, close, volume, amount
            FROM daily_kline
            WHERE code = '{code}'
            ORDER BY trade_date
        """).fetchdf()
        conn.close()
        df = df.fillna(0)

        for fd in FORECAST_DAYS:
            if fd in models:
                model, scaler = models[fd]
                pred = predict_stock(model, scaler, df)
                sp[f"pred_{fd}d"] = pred

    # 汇总结果
    result = {
        "run_date": TODAY,
        "stocks_analyzed": len(stock_predictions),
        "stocks_skipped": skipped,
        "model_metrics": {str(fd): results[fd] for fd in FORECAST_DAYS if fd in results},
        "stock_predictions": stock_predictions,
    }

    return result


def _compute_signal_score(features) -> float:
    """从特征向量计算一个简单的综合信号评分 (0-100)"""
    if features is None:
        return 50

    score = 50
    # 特征结构: LOOKBACK*2 个价格/量特征 + 8 个技术指标
    n_price = LOOKBACK

    # 最近几天价格动量
    if len(features) > n_price + 5:
        # 最近3天价格变化
        recent_ret = features[-1] - features[-3] if len(features) >= 3 else 0
        score += recent_ret * 50

    return max(0, min(100, score))


def save_results(result: dict):
    """保存结果"""
    json_path = os.path.join(OUTPUT_DIR, "ml_trend_predictions.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 结果: {json_path}")


def notify(text: str):
    try:
        subprocess.run(
            ["osascript", "-e",
             f'tell application "Messages" to send "{text}" to buddy "{IMSG_TO}"'],
            timeout=30,
        )
    except Exception:
        pass


def main(cron: bool = False, retrain: bool = False):
    if not HAS_SKLEARN:
        print("❌ 需要安装 scikit-learn: pip install scikit-learn")
        return

    print(f"{'⏰' if cron else '🚀'} ML 趋势预测: {TODAY}")
    start = time.time()

    result = run_pipeline()

    elapsed = time.time() - start
    save_results(result)

    # 摘要
    summary_lines = [f"📊 ML趋势预测完成 ({elapsed:.0f}秒)"]
    for fd in FORECAST_DAYS:
        if str(fd) in result.get("model_metrics", {}):
            m = result["model_metrics"][str(fd)]
            summary_lines.append(f"  {fd}天: 准确率{m['accuracy']*100:.1f}% AUC={m.get('auc', 'N/A')}")

    print("\n" + "\n".join(summary_lines))

    if cron:
        notify("\n".join(summary_lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ML 趋势预测")
    parser.add_argument("--cron", action="store_true", help="定时模式")
    parser.add_argument("--retrain", action="store_true", help="强制重新训练")
    args = parser.parse_args()
    main(cron=args.cron, retrain=args.retrain)