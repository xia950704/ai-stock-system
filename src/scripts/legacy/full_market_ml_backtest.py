#!/usr/bin/env python3
"""
full_market_ml_backtest.py — 全市场 ML 回测系统

用法:
  python3 full_market_ml_backtest.py                      # 标准回测（含基本面）
  python3 full_market_ml_backtest.py --quick               # 轻量回测（~3min）
  python3 full_market_ml_backtest.py --full                # 完整回测（~30min, 强模型）
  python3 full_market_ml_backtest.py --cron                # 静默模式（cron 用）
  python3 full_market_ml_backtest.py --no-fundamentals     # 跳过基本面因子

输入: DuckDB daily_kline (3201只, 4个月)
处理: 特征工程 -> ML 分类 -> 滚动窗口回测 -> 策略性能排名
输出: JSON 结果 + 可读报告

核心设计:
1. 特征工程: 动量, 趋势, 波动率, 成交量, 换手率, 均值回归
2. 标签: 次日收益率分桶 (-2%以下/ -2%~+2% / +2%以上)
3. 模型: GradientBoostingClassifier (sklearn 内置)
4. 回测: 每 N 日滚动训练 + 前向预测 -> 多股组合交易
5. 评价: 夏普, 最大回撤, 胜率, 平均收益, 信息比率
"""
import duckdb
import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import classification_report, f1_score, accuracy_score
from sklearn.preprocessing import StandardScaler
import json
import os
import warnings
warnings.filterwarnings('ignore')

DB_PATH = os.path.join(os.path.expanduser('~/harness/deeppulse/db/'), 'astock.duckdb')
OUTPUT_DIR = '/Users/xiashuang/harness/stock_daily'

# ============ CLI 参数（必须在其他代码前处理）============
import sys as _sys
_CRON = '--cron' in _sys.argv
_QUICK = '--quick' in _sys.argv
_FULL = '--full' in _sys.argv
_NO_FUNDAMENTALS = '--no-fundamentals' in _sys.argv
if _CRON:
    _null = open('/dev/null', 'w')
    _sys.stdout = _null
_MODE = 'FULL' if _FULL else ('QUICK' if _QUICK else 'NORMAL')
print(f"⚡ {_MODE} 模式")

# ============ 配置 ============
CONFIG = {
    'lookback_days': 20,          # 特征计算窗口
    'train_days': 30,             # 训练集最小长度
    'retrain_freq': 5,            # 每5日重新训练
    'hold_period': 3,             # 持有期（天）
    'max_positions': 20,          # 同时持仓最大数
    'min_trades': 50,             # 最少交易次数才计算结果
    'top_features': 15,           # 保留特征数
    'n_estimators': 100,          # 树木数量
    'max_depth': 4,               # 最大深度
    'min_samples_leaf': 50,       # 叶节点最小样本数
    'stop_loss_pct': -0.05,       # 止损线（-5%）
    'label_top_pct': 30,          # 标签用前30%收益率作为"上涨"
    'dynamic_position': True,     # 动态仓位（up_prob越高仓位越大）
}

if _FULL:
    CONFIG['retrain_freq'] = 5
    CONFIG['n_estimators'] = 200
    CONFIG['max_depth'] = 6
    CONFIG['min_samples_leaf'] = 20
    print("  完整模式: n_estimators=200, max_depth=6, retrain_freq=5")
elif _QUICK:
    CONFIG['retrain_freq'] = 20
    CONFIG['n_estimators'] = 50
    CONFIG['max_depth'] = 3
    CONFIG['min_samples_leaf'] = 100

# ============ 1. 加载数据 ============
print("=" * 60)
print("加载数据...")

con = duckdb.connect(DB_PATH)

# 检查 daily_fundamentals 表是否存在（预处理好的基本面）
has_daily_fund = con.execute(
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'daily_fundamentals'"
).fetchone()[0] > 0

# 加载 K 线 + 基本面（如果表存在且未禁用）
if has_daily_fund and not _NO_FUNDAMENTALS:
    raw = con.execute("""
        SELECT d.*, f.pe_ttm, f.pb, f.roe, f.eps, f.roa, f.operating_profit_margin
        FROM daily_kline d
        LEFT JOIN daily_fundamentals f ON d.code = f.code AND d.trade_date = f.trade_date
        ORDER BY d.code, d.trade_date
    """).df()
    print(f"基本面数据: ✅ daily_fundamentals（含 PE/PB/ROE/EPS/ROA/利润率）")
else:
    raw = con.execute("SELECT *, 0 as pe_ttm, 0 as pb, 0 as roe, 0 as eps, 0 as roa, 0 as operating_profit_margin FROM daily_kline ORDER BY code, trade_date").df()
    print(f"基本面数据: ❌ 跳过（无表或 --no-fundamentals）")

con.close()

print(f"原始数据: {raw.shape[0]} 行, {raw.shape[1]} 列")
print(f"股票数: {raw['code'].nunique()}")
print(f"日期范围: {raw['trade_date'].min()} ~ {raw['trade_date'].max()}")
print(f"基本面因子行数: {sum(1 for _ in raw.itertuples() if raw['pe_ttm'].iloc[0] != 0)} 行")

# 筛选有足够数据的股票（至少60行）
stock_counts = raw.reset_index().groupby('code').size()
valid_codes = stock_counts[stock_counts >= 60].index.tolist()
df = raw[raw['code'].isin(valid_codes)].copy()
print(f"有效股票（>=60日）: {len(valid_codes)} 只")
print(f"有效数据: {df.shape[0]} 行")

# ============ 2. 特征工程 ============
print("\n特征工程...")

def compute_features(group: pd.DataFrame) -> pd.DataFrame:
    """为单只股票计算技术指标"""
    g = group.sort_values('trade_date').copy()
    g['code'] = group.name  # pandas 3.0 groupby + group_keys=False 丢弃分组键，显式恢复
    
    close = g['close']
    high = g['high']
    low = g['low']
    volume = g['volume']
    amount = g['amount']
    turnover = g['turnover']
    open_price = g['open']
    
    # --- 动量特征 ---
    g['ret_1d'] = close.pct_change(1)
    g['ret_5d'] = close.pct_change(5)
    g['ret_10d'] = close.pct_change(10)
    g['ret_20d'] = close.pct_change(20)
    
    # --- 趋势强度 ---
    ma5 = close.rolling(5).mean()
    ma10 = close.rolling(10).mean()
    ma20 = close.rolling(20).mean()
    g['price_vs_ma5'] = close / ma5 - 1
    g['price_vs_ma10'] = close / ma10 - 1
    g['price_vs_ma20'] = close / ma20 - 1
    g['ma5_vs_ma20'] = ma5 / ma20 - 1
    
    # --- 波动率 ---
    g['volatility_5d'] = g['ret_1d'].rolling(5).std()
    g['volatility_10d'] = g['ret_1d'].rolling(10).std()
    g['volatility_20d'] = g['ret_1d'].rolling(20).std()
    
    # --- 布林带位置 ---
    bb_mid = ma20
    bb_std = close.rolling(20).std()
    g['bb_position'] = (close - bb_mid) / bb_std  # 标准化位置
    g['bb_width'] = 2 * bb_std / bb_mid
    
    # --- RSI ---
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    g['rsi_14'] = 100 - (100 / (1 + rs))
    
    # --- 成交量 ---
    vol_ma5 = volume.rolling(5).mean()
    vol_ma20 = volume.rolling(20).mean()
    g['vol_ratio_5d'] = volume / vol_ma5
    g['vol_ratio_20d'] = volume / vol_ma20
    g['vol_trend'] = vol_ma5 / vol_ma20
    
    # --- 换手率 ---
    g['turnover_ma5'] = turnover.rolling(5).mean()
    g['turnover_ma20'] = turnover.rolling(20).mean()
    g['turnover_ratio'] = turnover / g['turnover_ma20']
    
    # --- 振幅 ---
    g['amplitude'] = (high - low) / close
    
    # --- 开盘溢价 ---
    g['open_premium'] = (close - open_price) / open_price
    
    # --- 量价配合 ---
    price_change = close.pct_change()
    vol_change = volume.pct_change()
    g['price_vol_corr'] = (price_change * vol_change).rolling(5).mean()
    
    # --- 高低点突破 ---
    g['high_20d'] = high.rolling(20).max()
    g['low_20d'] = low.rolling(20).min()
    g['dist_from_high'] = close / g['high_20d'] - 1
    g['dist_from_low'] = close / g['low_20d'] - 1
    
    # --- 成交额排名（相对自身历史）---
    g['amount_ma5'] = amount.rolling(5).mean()
    g['amount_ma20'] = amount.rolling(20).mean()
    g['amount_ratio'] = g['amount_ma5'] / g['amount_ma20']
    
    # --- EMA 信号 ---
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    g['macd'] = ema12 - ema26
    g['macd_signal'] = g['macd'].ewm(span=9).mean()
    g['macd_hist'] = g['macd'] - g['macd_signal']
    
    return g

# 按股票代码分组计算特征
df = df.reset_index().groupby('code', group_keys=False).apply(compute_features)

# 填充无效值
df = df.replace([np.inf, -np.inf], np.nan)
numeric_cols = df.select_dtypes(include=[np.number]).columns
df[numeric_cols] = df[numeric_cols].ffill().bfill().fillna(0)

# 基本面因子已在数据加载时通过 daily_fundamentals JOIN 完成
# 此处无需额外操作

print(f"特征计算完成: {df.shape[0]} 行, {df.shape[1]} 列")
print(f"特征数: {len(df.columns) - 8}")  # 减去 code/trade_date/OHLCV/amount/turnover/data_source

# ============ 3. 标签生成 ============
print("\n标签生成...")

def create_percentile_labels(df_group, hold_period=3, top_pct=30):
    """基于每日收益率排序分桶（前30%为上涨，中间为震荡，后30%为下跌）"""
    g = df_group.sort_values('trade_date').copy()
    g['future_ret'] = g['close'].shift(-hold_period) / g['close'] - 1
    return g

# 计算未来收益（持有期）并分桶
def _label_wrapper(g):
    result = create_percentile_labels(g, CONFIG['hold_period'], CONFIG['label_top_pct'])
    result['code'] = g.name
    return result

df = df.reset_index().groupby('code', group_keys=False).apply(_label_wrapper)

# 按每个交易日独立排序分桶（避免跨期偏差）
def bucket_by_date(date_group):
    """对单日所有股票的未来收益率排序分桶"""
    g = date_group.copy()
    valid = g['future_ret'].dropna()
    if len(valid) < 10:
        g['label'] = 0
        return g
    # 按收益率排序分三等份
    sorted_vals = valid.sort_values()
    n = len(sorted_vals)
    bottom_cut = sorted_vals.iloc[int(n * 0.3)]
    top_cut = sorted_vals.iloc[int(n * 0.7)]
    g['label'] = g['future_ret'].apply(
        lambda x: -1 if pd.isna(x) or x <= bottom_cut
        else (1 if x >= top_cut else 0))
    return g

def _bucket_wrapper(g):
    result = bucket_by_date(g)
    result['trade_date'] = g.name
    return result

df = df.groupby('trade_date', group_keys=False).apply(_bucket_wrapper)

# 统计标签分布
label_counts = df['label'].value_counts().to_dict()
print(f"标签分布（前30%/中间40%/后30%）: {label_counts}")
print(f"  上涨={label_counts.get(1,0)}, 震荡={label_counts.get(0,0)}, 下跌={label_counts.get(-1,0)}")
print(f"  最终列数: {df.shape[1]}, 前10列: {list(df.columns[:10])}")

# ============ 4. 特征选择 ============
print("\n特征选择...")

FEATURE_COLS = [
    'ret_1d', 'ret_5d', 'ret_10d', 'ret_20d',
    'price_vs_ma5', 'price_vs_ma10', 'price_vs_ma20', 'ma5_vs_ma20',
    'volatility_5d', 'volatility_10d', 'volatility_20d',
    'bb_position', 'bb_width',
    'rsi_14',
    'vol_ratio_5d', 'vol_ratio_20d', 'vol_trend',
    'turnover_ratio',
    'amplitude', 'open_premium', 'price_vol_corr',
    'dist_from_high', 'dist_from_low',
    'amount_ratio',
    'macd', 'macd_signal', 'macd_hist',
    # 基本面因子（如果有的话）
    'pe_ttm', 'pb', 'roe', 'eps', 'roa', 'operating_profit_margin',
]

# 保留存在的特征
FEATURE_COLS = [c for c in FEATURE_COLS if c in df.columns]
fundamental_active = any(c in FEATURE_COLS for c in ['pe_ttm', 'pb', 'roe'])
print(f"使用特征数: {len(FEATURE_COLS)}")
print(f"基本面因子: {'✅ 已启用' if fundamental_active else '❌ 不活跃'}")

# ============ 5. 滚动窗口回测 ============
print("\n滚动窗口回测...")

def rolling_backtest(df, feature_cols, label_col='label', binary=True):
    """
    滚动窗口回测:
    1. 每 retrain_freq 日重新训练
    2. 用训练好的模型预测所有股票
    3. 选股: 预测为上涨的概率最高的 top_N
    4. 计算组合收益
    """
    daily_dates = sorted(df['trade_date'].unique())
    results = []
    trades = []
    portfolio_daily = []
    
    model = None
    scaler = StandardScaler()
    
    for i, trade_date in enumerate(daily_dates):
        # 训练窗口: 从 retrain_freq 日前开始
        if i < CONFIG['train_days']:
            continue
        
        if model is None or i % CONFIG['retrain_freq'] == 0:
            # 准备训练数据
            train_end = daily_dates[i]
            train_dates = [d for d in daily_dates if d < train_end]
            if len(train_dates) < CONFIG['train_days']:
                continue
            
            train_df = df[df['trade_date'].isin(train_dates)]
            # 移除无效行
            train_df = train_df[train_df['label'].notna() & (train_df['label'].isin([0, 1, -1]))]
            
            if len(train_df) < 1000:
                continue
            
            X_train = train_df[feature_cols].values
            y_train = train_df[label_col].values
            
            # 标准化
            X_train = scaler.fit_transform(X_train)
            
            # 训练模型
            model = GradientBoostingClassifier(
                n_estimators=CONFIG['n_estimators'],
                max_depth=CONFIG['max_depth'],
                learning_rate=0.1,
                min_samples_leaf=CONFIG['min_samples_leaf'],
                random_state=42,
            )
            model.fit(X_train, y_train)
            
            # 记录训练集性能
            y_pred_train = model.predict(X_train)
            train_acc = accuracy_score(y_train, y_pred_train)
            results.append({
                'date': str(train_end),
                'train_accuracy': round(train_acc, 4),
                'train_size': len(X_train),
                'n_stocks': len(df[df['trade_date'] == train_end]),
            })
        
        # 预测
        current_df = df[df['trade_date'] == trade_date].copy()
        if len(current_df) == 0:
            continue
        
        X_pred = current_df[feature_cols].values
        X_pred = scaler.transform(X_pred)
        
        # 预测概率
        if binary:
            probs = model.predict_proba(X_pred)
            up_prob = probs[:, 1] if probs.shape[1] >= 2 else probs[:, 0]
        else:
            # 三分类: 用 [下跌概率, 震荡概率, 上涨概率]
            pred_classes = model.predict(X_pred)
            up_prob = np.where(pred_classes == 1, 0.8, 0.2)
        
        current_df = current_df.assign(up_prob=up_prob)
        
        # 选股: 上涨概率最高的 top_N
        top_n = CONFIG['max_positions']
        top_stocks = current_df.nlargest(top_n, 'up_prob')
        
        # 计算这些股票在未来 hold_period 日的收益
        hold_d = CONFIG['hold_period']
        stop_loss = CONFIG.get('stop_loss_pct', -0.05)
        use_dynamic = CONFIG.get('dynamic_position', True)

        # 找到持有期末的日期
        if i + hold_d < len(daily_dates):
            hold_end_date = daily_dates[i + hold_d]
        else:
            hold_end_date = daily_dates[-1]

        hold_end_df = df[df['trade_date'] == hold_end_date]

        # 取持有期内所有日期用于止损检查
        hold_dates = []
        for j in range(1, hold_d + 1):
            if i + j < len(daily_dates):
                hold_dates.append(daily_dates[i + j])
        hold_daily_dfs = {d: df[df['trade_date'] == d] for d in hold_dates if d <= hold_end_date}

        # 计算组合收益（动态仓位 + 止损）
        portfolio_ret = 0
        n_selected = 0
        total_weight = 0

        # 动态仓位权重：up_prob 越高权重越大（线性映射 0.5~1.5x）
        up_probs = top_stocks['up_prob'].values
        if use_dynamic and len(up_probs) > 0 and up_probs.std() > 0.01:
            weights = (up_probs - up_probs.min()) / (up_probs.max() - up_probs.min()) * 1.0 + 0.5
            weights = weights / weights.sum() * len(weights)  # 归一化，总和=1
        else:
            weights = np.ones(len(up_probs)) / len(up_probs) if len(up_probs) > 0 else np.array([])

        for idx, (_, row) in enumerate(top_stocks.iterrows()):
            code = row['code']
            entry_price = row['close']
            weight = weights[idx] if idx < len(weights) else 1.0 / max(len(top_stocks), 1)

            # 止损检查：持有期内逐日检查
            stopped_out = False
            exit_price = None
            for hd in hold_dates:
                daily_df = hold_daily_dfs.get(hd)
                if daily_df is not None:
                    day_row = daily_df[daily_df['code'] == code]
                    if len(day_row) > 0:
                        current_price = day_row.iloc[0]['close']
                        if current_price / entry_price - 1 <= stop_loss:
                            exit_price = current_price  # 止损出场
                            stopped_out = True
                            break

            if not stopped_out:
                # 正常持有到期
                end_row = hold_end_df[hold_end_df['code'] == code]
                if len(end_row) > 0:
                    exit_price = end_row.iloc[0]['close']

            if exit_price is not None:
                ret = exit_price / entry_price - 1
                portfolio_ret += ret * weight
                n_selected += 1
                total_weight += weight

                trades.append({
                    'date': str(trade_date),
                    'code': code,
                    'up_prob': round(float(row['up_prob']), 4),
                    'entry_price': round(float(entry_price), 2),
                    'exit_price': round(float(exit_price), 2),
                    'return': round(float(ret), 4),
                    'weight': round(float(weight), 4),
                    'stopped_out': stopped_out,
                    'label': int(row['label']) if pd.notna(row.get('label')) else 0,
                })

        if n_selected > 0:
            avg_ret = portfolio_ret / total_weight if total_weight > 0 else 0
            portfolio_daily.append({
                'date': str(trade_date),
                'portfolio_return': round(avg_ret, 6),
                'n_positions': n_selected,
                'avg_up_prob': round(float(top_stocks['up_prob'].mean()), 4),
                'stopped_out': sum(1 for t in trades if t.get('stopped_out') and t['date'] == str(trade_date)),
            })
        
        # 进度
        if i % 20 == 0:
            print(f"  进度: {i}/{len(daily_dates)} 日期, {len(trades)} 笔交易")
    
    return results, trades, portfolio_daily

results, trades, portfolio_daily = rolling_backtest(df, FEATURE_COLS)

print(f"\n回测完成: {len(trades)} 笔交易, {len(portfolio_daily)} 日")

# ============ 6. 策略性能计算 ============
print("\n计算策略性能...")

def calc_strategy_metrics(portfolio_rets, trades_list):
    """计算策略性能指标"""
    if len(portfolio_rets) < 10:
        return {}
    
    rets = [d['portfolio_return'] for d in portfolio_rets]
    rets_series = pd.Series(rets)
    
    # 累计收益
    cumulative = (1 + pd.Series(rets)).cumprod()
    
    # 年化收益（4个月 ≈ 0.33年）
    years = 4 / 12
    annual_return = cumulative.iloc[-1] ** (1 / years) - 1
    
    # 夏普比率（年化）
    daily_vol = rets_series.std()
    annual_vol = daily_vol * np.sqrt(252)
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0
    
    # 最大回撤
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = drawdown.min()
    
    # 胜率（正收益天数比例）
    win_days = sum(1 for r in rets if r > 0)
    win_rate = win_days / len(rets)
    
    # 交易级胜率
    trade_rets = [t['return'] for t in trades_list if t['return'] != 0]
    trade_win = sum(1 for r in trade_rets if r > 0)
    trade_win_rate = trade_win / len(trade_rets) if trade_rets else 0
    avg_trade_ret = np.mean(trade_rets) if trade_rets else 0
    
    # 信息比率（对比基准）
    # 基准: 等权全市场
    benchmark_rets = []
    for d in portfolio_rets:
        date = d['date']
        bench_df = df[df['trade_date'] == pd.Timestamp(date)]
        if len(bench_df) > 0:
            # 简单基准: 平均收益
            bench_ret = bench_df['close'].pct_change().mean()
            if pd.isna(bench_ret):
                bench_ret = 0
            benchmark_rets.append(bench_ret)
    
    if len(benchmark_rets) == len(rets):
        excess = [r - b for r, b in zip(rets, benchmark_rets)]
        info_ratio = np.mean(excess) / np.std(excess) if np.std(excess) > 0 else 0
    else:
        info_ratio = 0
    
    return {
        'total_return': round(float(cumulative.iloc[-1] - 1), 6),
        'annual_return': round(float(annual_return), 6),
        'sharpe_ratio': round(float(sharpe), 4),
        'max_drawdown': round(float(max_drawdown), 6),
        'daily_win_rate': round(float(win_rate), 4),
        'trade_win_rate': round(float(trade_win_rate), 4),
        'avg_trade_return': round(float(avg_trade_ret), 6),
        'info_ratio': round(float(info_ratio), 4),
        'total_trades': len(trades_list),
        'trading_days': len(rets),
        'avg_positions': round(np.mean([d['n_positions'] for d in portfolio_rets]), 1),
    }

metrics = calc_strategy_metrics(portfolio_daily, trades)
print("策略性能:")
for k, v in metrics.items():
    print(f"  {k}: {v}")

# ============ 7. 模型特征重要性 ============
print("\n计算特征重要性...")

# 最后一次训练的特征重要性
all_dates = sorted(df['trade_date'].unique())
train_end = all_dates[-1]
train_dates = [d for d in all_dates if d < train_end]
train_df = df[df['trade_date'].isin(train_dates)]
train_df = train_df[train_df['label'].notna() & (train_df['label'].isin([0, 1, -1]))]

if len(train_df) >= 1000:
    X_train = train_df[FEATURE_COLS].values
    y_train = train_df['label'].values
    from sklearn.preprocessing import StandardScaler as SS
    X_train = SS().fit_transform(X_train)
    
    final_model = GradientBoostingClassifier(
        n_estimators=CONFIG['n_estimators'], max_depth=CONFIG['max_depth'],
        learning_rate=0.1, min_samples_leaf=CONFIG['min_samples_leaf'],
        random_state=42,
    )
    final_model.fit(X_train, y_train)
    
    feature_importance = {
        FEATURE_COLS[i]: round(float(final_model.feature_importances_[i]), 4)
        for i in range(len(FEATURE_COLS))
    }
    feature_importance = dict(sorted(feature_importance.items(), key=lambda x: -x[1]))
else:
    feature_importance = {}

print("特征重要性 TOP 10:")
for i, (feat, imp) in enumerate(list(feature_importance.items())[:10]):
    print(f"  {i+1}. {feat}: {imp}")

# ============ 8. 保存结果 ============
print("\n保存结果...")

output = {
    'config': CONFIG,
    'data_stats': {
        'total_rows': int(raw.shape[0]),
        'total_stocks': int(raw['code'].nunique()),
        'valid_stocks': len(valid_codes),
        'date_range': [str(raw['trade_date'].min()), str(raw['trade_date'].max())],
    },
    'model_metrics': {
        'final_accuracy': round(float(accuracy_score(y_train, final_model.predict(X_train))), 4) if len(train_df) >= 1000 else None,
        'feature_importance': feature_importance,
    },
    'strategy_performance': metrics,
    'training_results': results[-10:],  # 最后10次训练结果
    'sample_trades': trades[:50],  # 前50笔交易
}

out_path = os.path.join(OUTPUT_DIR, 'full_market_ml_backtest.json')
with open(out_path, 'w') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"结果已保存: {out_path}")

# 也保存每日收益曲线用于可视化
portfolio_df = pd.DataFrame(portfolio_daily)
csv_path = os.path.join(OUTPUT_DIR, 'ml_backtest_daily_returns.csv')
portfolio_df.to_csv(csv_path, index=False)
print(f"每日收益曲线已保存: {csv_path}")

print("\n" + "=" * 60)
print("ML 回测系统完成!")
print("=" * 60)
print(f"\n核心结果:")
print(f"  总收益: {metrics.get('total_return', 'N/A')}")
print(f"  年化收益: {metrics.get('annual_return', 'N/A')}")
print(f"  夏普比率: {metrics.get('sharpe_ratio', 'N/A')}")
print(f"  最大回撤: {metrics.get('max_drawdown', 'N/A')}")
print(f"  胜率: {metrics.get('daily_win_rate', 'N/A')}")
print(f"  交易胜率: {metrics.get('trade_win_rate', 'N/A')}")
print(f"  平均单笔收益: {metrics.get('avg_trade_return', 'N/A')}")
