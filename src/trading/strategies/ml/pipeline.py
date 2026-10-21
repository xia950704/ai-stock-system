#!/usr/bin/env python3
"""
主运行脚本：A股ML策略回测管道
================================
模拟 ¥20,000 短线交易策略，支持真实A股数据
  1️⃣ 跑回测 → 从东方财富获取A股数据 → 执行回测引擎
  2️⃣ 刷新基准线 → 刷新 ML 信号
  3️⃣ 检查预警 → 触发价格预警

用法:
  python3 run_pipeline.py                        # 完整运行(默认股票池)
  python3 run_pipeline.py --symbol 000858         # 指定个股
  python3 run_pipeline.py --mode backtest        # 仅回测
  python3 run_pipeline.py --mode signal          # 仅刷新信号
  python3 run_pipeline.py --mode alert           # 仅预警
  python3 run_pipeline.py --list                 # 列出股票池
"""
import sys
import os
import argparse
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from core.data import (fetch_a_stock_data, fetch_multiple_stocks,
                  prepare_ml_data, STOCK_POOL, list_available_stocks)
from strategies.ml.model import MLSignalGenerator
from core.backtest import BacktestEngine
from strategies.ml.alerts import check_price_alert, check_ml_signal_alert, check_performance_alert, show_recent_alerts

CAPITAL = 20000
SIGNAL_THRESHOLD = 0.55

def run_backtest(symbols):
    """1️⃣ 跑回测"""
    print(f"\n{'='*55}")
    print(f"  1️⃣  跑回测 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  初始资金: ¥{CAPITAL:,} | 股票: {', '.join(symbols)}")
    print(f"{'='*55}")

    # 获取数据
    if len(symbols) == 1:
        # 单只股票
        symbol = symbols[0]
        name = STOCK_POOL.get(symbol, symbol)
        print(f"  📊 获取 {symbol}({name}) 数据...")
        df = fetch_a_stock_data(symbol)
        if df is None or len(df) < 30:
            print(f"  ❌ 数据不足，无法回测")
            return None, None
        print(f"  ✅ {len(df)} 根日K线 | ¥{df['收盘'].iloc[0]:.1f} → ¥{df['收盘'].iloc[-1]:.1f}")
        results = {symbol: df}
    else:
        results = fetch_multiple_stocks(symbols)
        if not results:
            print("  ❌ 未获取到有效数据")
            return None, None

    summaries = []
    models = {}

    for symbol, df in results.items():
        name = STOCK_POOL.get(symbol, symbol)
        print(f"\n  ── {symbol} ({name}) ──")

        X, y, df_full = prepare_ml_data(df)
        if len(X) < 30:
            print(f"  ⚠️ 特征数据不足({len(X)}行)，跳过")
            continue

        print(f"  📐 特征: {X.shape[1]}维 | 样本: {len(X)}")

        ml = MLSignalGenerator()
        acc = ml.train(X, y)
        print(f"  🤖 ML准确率: {acc:.2%}")
        for feat, imp in ml.feature_importance()[:3]:
            print(f"    {feat}: {imp:.3f}")
        ml.save(symbol)

        signals, probas = ml.generate_signal(X, threshold=SIGNAL_THRESHOLD)
        sc = {1: (signals==1).sum(), -1: (signals==-1).sum(), 0: (signals==0).sum()}

        test_df = df_full.iloc[-len(signals):]
        engine = BacktestEngine(test_df, signals, test_df['收盘'].values)
        summary = engine.run()
        engine.print_summary(summary)

        summaries.append((symbol, name, summary))
        models[symbol] = ml

    return summaries, models

def refresh_signal(models, symbols):
    """2️⃣ 刷新ML信号"""
    print(f"\n{'='*55}")
    print(f"  2️⃣  刷新ML信号 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*55}")

    results = {}
    for symbol in symbols:
        name = STOCK_POOL.get(symbol, symbol)
        df = fetch_a_stock_data(symbol)
        if df is None or len(df) < 20:
            continue

        X, y, df_full = prepare_ml_data(df)
        if len(X) == 0:
            continue

        ml = models.get(symbol) if symbol in models else MLSignalGenerator()
        if symbol not in models:
            ml.load(symbol)

        signals, probas = ml.generate_signal(X, threshold=SIGNAL_THRESHOLD)
        latest_signal = signals[-1] if len(signals) > 0 else 0
        latest_prob = probas[-1] if len(probas) > 0 else 0.5
        latest_price = df_full['收盘'].iloc[-1]
        prev_price = df_full['收盘'].iloc[-2] if len(df_full) > 1 else latest_price

        direction = {1: "🟢 买入", -1: "🔴 卖出", 0: "⚪ 持有"}
        change = (latest_price - prev_price) / prev_price

        print(f"  {symbol} ({name})")
        print(f"    💹 ¥{latest_price:.2f} ({change:+.2%})")
        print(f"    🎯 {direction.get(latest_signal, '?')} (概率: {latest_prob:.1%})")
        print(f"    📊 模型准确率: {ml.accuracy:.2%}")

        results[symbol] = {
            'signal': latest_signal, 'probability': latest_prob,
            'price': latest_price, 'accuracy': ml.accuracy
        }

    return results

def run_alerts(signal_info=None):
    """3️⃣ 检查预警"""
    print(f"\n{'='*55}")
    print(f"  3️⃣  检查预警 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*55}")

    all_alerts = []
    if signal_info:
        for symbol, info in signal_info.items():
            pa = check_price_alert(info['price'], threshold_pct=0.03, symbol=symbol)
            all_alerts.extend(pa)
            if info['signal'] != 0:
                ma = check_ml_signal_alert(info['signal'], info['probability'], symbol=symbol)
                all_alerts.extend(ma)

    if not all_alerts:
        print("  ✅ 当前无预警触发")
    show_recent_alerts(3)
    return all_alerts

def main():
    parser = argparse.ArgumentParser(description='A股ML策略回测系统 ¥20,000')
    parser.add_argument('--mode', choices=['full', 'backtest', 'signal', 'alert'],
                       default='full')
    parser.add_argument('--symbol', default=None, help='股票代码，如 000858')
    parser.add_argument('--list', action='store_true', help='列出股票池')
    args = parser.parse_args()

    if args.list:
        list_available_stocks()
        return

    symbols = [args.symbol] if args.symbol else ['000858']  # 默认五粮液

    print(f"""
╔═══════════════════════════════════════════════════╗
║     📈 A股短线ML策略回测系统 ¥20,000               ║
║     股票: {symbols[0]:8s} ({STOCK_POOL.get(symbols[0], '')})           ║
║     模式: {args.mode:8s}                           ║
║     时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}               ║
╚═══════════════════════════════════════════════════╝
""")

    summaries = None
    models = {}
    signal_info = None

    if args.mode in ('full', 'backtest'):
        summaries, models = run_backtest(symbols)

    if args.mode in ('full', 'signal'):
        if not models:
            for s in symbols:
                m = MLSignalGenerator()
                if m.load(s):
                    models[s] = m
        signal_info = refresh_signal(models, symbols)

    if args.mode in ('full', 'alert'):
        run_alerts(signal_info)

    print(f"\n{'='*55}")
    print(f"  ✅ 管道完成 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if summaries:
        for symbol, name, s in summaries:
            ret = s.get('总收益率', '0%')
            trades = s.get('交易次数', 0)
            win = s.get('胜率', '0%')
            print(f"  {symbol}({name}): 收益{ret} | {trades}次 | 胜率{win}")
    print(f"{'='*55}\n")

if __name__ == '__main__':
    main()