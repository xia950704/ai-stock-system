#!/usr/bin/env python3
"""
批量优化器：自动跑几百只A股、多种参数组合、寻找最优策略
========================================================
用法：
  python3 batch_optimizer.py                          # 全量运行（耗时较长）
  python3 batch_optimizer.py --quick                  # 快速模式（只跑50只）
  python3 batch_optimizer.py --stocks my_stocks.txt   # 自定义股票列表
  python3 batch_optimizer.py --report                 # 仅查看上次结果
"""
import sys, os, json, time, argparse
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
os.environ['PYTHONWARNINGS'] = 'ignore'

from core.data import fetch_a_stock_data, prepare_ml_data, STOCK_POOL
from strategies.ml.model import MLSignalGenerator
from core.backtest import BacktestEngine

# ==================== 参数网格 ====================
PARAM_GRID = {
    'model_type': ['rf', 'gbm', 'lr'],      # 随机森林 / 梯度提升 / 逻辑回归
    'threshold': [0.50, 0.55, 0.60],         # 信号阈值（越低交易越多）
    'stop_loss': [-0.03, -0.05, -0.07],       # 止损线
    'take_profit': [0.05, 0.08, 0.10],        # 止盈线
    'position_ratio': [0.50, 0.75, 0.95],     # 仓位比例
    'feature_set': ['full', 'basic', 'price']  # 特征集
}

# 简化版参数网格（快速测试用）
QUICK_PARAM_GRID = {
    'model_type': ['rf', 'lr'],
    'threshold': [0.50, 0.60],
    'stop_loss': [-0.05],
    'take_profit': [0.08],
    'position_ratio': [0.95],
    'feature_set': ['full', 'basic']
}

FEATURE_SETS = {
    'full': ['Pct_MA5', 'Pct_MA10', 'Pct_MA20', 'RSI', 'Return_1d', 'Return_5d',
             'Return_10d', 'Volatility_5d', 'Volatility_10d', 'Volume_Ratio',
             'MACD', 'MACD_Hist', 'BB_Position', 'Price_Position'],
    'basic': ['Pct_MA5', 'Pct_MA10', 'RSI', 'Return_1d', 'Return_5d', 'Volume_Ratio'],
    'price': ['Return_1d', 'Return_5d', 'Return_10d', 'Pct_MA5', 'Pct_MA10', 'Volatility_5d']
}

RESULTS_FILE = os.path.join(os.path.dirname(__file__), 'batch_results.json')

def get_stock_list(min_count=50):
    """从新浪获取A股列表，按成交量排序取前 N 只"""
    print("  📋 获取A股列表...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        import requests
        # 获取沪深全部股票列表
        url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
        all_stocks = []
        page = 1
        while len(all_stocks) < min_count and page < 10:
            params = {
                "page": str(page),
                "num": "80",
                "sort": "amount",
                "asc": "0",
                "node": "hs_a",
                "symbol": "",
                "_s_r_a": "init"
            }
            try:
                r = requests.get(url, params=params, headers=headers, timeout=10)
                data = r.json()
                if not data or len(data) == 0:
                    break
                for item in data:
                    code = item.get('code', '')
                    name = item.get('name', '')
                    vol = float(item.get('amount', 0))
                    all_stocks.append({'code': code, 'name': name, 'volume': vol})
                page += 1
            except Exception as e:
                print(f"⚠️ 股票列表获取失败 (page {page}): {e}")
                break

        # 按成交量排序取前 min_count 只
        all_stocks.sort(key=lambda x: x['volume'], reverse=True)
        result = [s['code'] for s in all_stocks[:min_count] if s['code']]
        print(f"  ✅ 获取 {len(result)} 只股票")
        return result
    except Exception as e:
        print(f"  ⚠️ 获取列表失败: {e}，使用默认股票池")
        return list(STOCK_POOL.keys())

def train_model(X, y, model_type='rf'):
    """训练指定类型的模型"""
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression

    if model_type == 'rf':
        model = RandomForestClassifier(n_estimators=100, max_depth=6, random_state=42)
    elif model_type == 'gbm':
        model = GradientBoostingClassifier(n_estimators=100, max_depth=4, random_state=42)
    elif model_type == 'lr':
        model = LogisticRegression(max_iter=1000, random_state=42)
    else:
        model = RandomForestClassifier(n_estimators=100, max_depth=6, random_state=42)

    # 时序交叉验证
    from sklearn.model_selection import TimeSeriesSplit
    tscv = TimeSeriesSplit(n_splits=3)
    accs = []
    for train_idx, val_idx in tscv.split(X):
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        accs.append(model.score(X.iloc[val_idx], y.iloc[val_idx]))
    model.fit(X, y)
    return model, np.mean(accs)

def run_single_test(symbol, params):
    """对一只股票运行一组参数"""
    import numpy as np

    df = fetch_a_stock_data(symbol)
    if df is None or len(df) < 60:
        return None, None

    X, y, full = prepare_ml_data(df)
    if len(X) < 30:
        return None, None

    # 选择特征集
    feat_cols = FEATURE_SETS.get(params['feature_set'], FEATURE_SETS['full'])
    avail_cols = [c for c in feat_cols if c in X.columns]
    if len(avail_cols) < 3:
        return None, None

    X_sel = X[avail_cols]

    # 训练模型
    model, acc = train_model(X_sel, y, params['model_type'])

    # 生成信号
    proba = model.predict_proba(X_sel)
    prob_up = proba[:, 1] if proba.shape[1] > 1 else proba[:, 0]

    th = params['threshold']
    signals = np.where(prob_up > th, 1, np.where(prob_up < (1 - th), -1, 0))

    # 创建自定义回测引擎
    engine = BacktestEngine(full.iloc[-len(signals):], signals, full['收盘'].values[-len(signals):])
    # 覆盖参数
    engine.STOP_LOSS = params['stop_loss']
    engine.TAKE_PROFIT = params['take_profit']
    engine.POSITION_RATIO = params['position_ratio']
    engine.COMMISSION_RATE = 0.0003
    engine.SLIPPAGE = 0.001

    summary = engine.run()

    total_ret = (engine.capital - 20000) / 20000

    return {
        'symbol': symbol,
        'params': params,
        'accuracy': float(acc),
        'total_return': float(total_ret),
        'trades': summary.get('交易次数', 0),
        'win_rate': float(summary.get('胜率', '0%').strip('%')) if '%' in str(summary.get('胜率', '0%')) else 0,
        'sharpe': float(summary.get('夏普比率', '0')),
        'max_drawdown': float(summary.get('最大回撤', '0%').strip('%')) if '%' in str(summary.get('最大回撤', '0%')) else 0,
        'final_capital': float(engine.capital)
    }, params

def run_batch(symbols, quick=False):
    """批量跑所有参数组合"""
    param_grid = QUICK_PARAM_GRID if quick else PARAM_GRID
    import itertools

    # 展开参数组合
    keys = list(param_grid.keys())
    combinations = list(itertools.product(*param_grid.values()))
    total_combo = len(combinations)
    total_runs = len(symbols) * total_combo

    print(f"\n{'='*55}")
    print(f"  🔬 批量优化 | 股票: {len(symbols)}只 | 参数组合: {total_combo}种")
    print(f"  总任务数: {total_runs}")
    print(f"  参数网格:")
    for k, v in param_grid.items():
        print(f"    {k}: {v}")
    print(f"{'='*55}\n")

    all_results = []
    start_time = time.time()
    run_count = 0

    for symbol in symbols:
        for combo in combinations:
            params = dict(zip(keys, combo))
            run_count += 1

            # 进度显示（每50次显示一次）
            if run_count % 50 == 1 or run_count == total_runs:
                elapsed = time.time() - start_time
                pct = run_count / total_runs * 100
                eta = elapsed / run_count * (total_runs - run_count) if run_count > 0 else 0
                print(f"  [{run_count}/{total_runs}] {pct:.0f}% | ETA: {eta:.0f}s | 当前最佳: {_get_best_return(all_results) if all_results else 'N/A'}")

            result, _ = run_single_test(symbol, params)
            if result:
                all_results.append(result)

            # 小幅延时避免API限流
            if run_count % 10 == 0:
                time.sleep(0.1)

    elapsed = time.time() - start_time
    print(f"\n  ✅ 完成! {len(all_results)} 个有效结果 | 耗时: {elapsed:.0f}s")

    # 保存结果
    with open(RESULTS_FILE, 'w') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    return all_results

def _get_best_return(results):
    if not results:
        return 'N/A'
    best = max(results, key=lambda r: r.get('total_return', -999))
    return f"{best.get('total_return', 0):+.1%}"

def analyze_results(results):
    """分析结果，找出最优参数组合"""
    if not results:
        print("  ❌ 无结果可分析")
        return

    print(f"\n{'='*55}")
    print(f"  📊 批量优化分析报告")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')} | 有效样本: {len(results)}")
    print(f"{'='*55}")

    # 1. 按收益率排序TOP10
    top10 = sorted(results, key=lambda r: r['total_return'], reverse=True)[:10]
    print(f"\n  🏆 收益率TOP10:")
    print(f"  {'股票':8s} {'模型':4s} {'阈值':4s} {'止损':4s} {'止盈':4s} {'仓位':4s} {'特征':6s} {'收益率':8s} {'交易':4s} {'胜率':6s} {'夏普':5s}")
    print(f"  {'-'*60}")
    for r in top10:
        p = r['params']
        print(f"  {r['symbol']:8s} {p['model_type']:4s} {p['threshold']:.2f} {p['stop_loss']:.0%} {p['take_profit']:.0%} {p['position_ratio']:.0%} {p['feature_set']:6s} {r['total_return']:+.1%} {r['trades']:4d} {r['win_rate']:.0%} {r['sharpe']:.1f}")

    # 2. 按夏普比率排序TOP10
    top_sharpe = sorted(results, key=lambda r: r['sharpe'], reverse=True)[:10]
    print(f"\n  🏆 夏普比率TOP10:")
    for r in top_sharpe:
        p = r['params']
        print(f"  {r['symbol']:8s} {p['model_type']:4s} 阈值{p['threshold']:.2f} 止损{p['stop_loss']:.0%} 收益{r['total_return']:+.1%} 夏普{r['sharpe']:.1f} 回撤{r['max_drawdown']:.1%}")

    # 3. 按参数聚合分析
    print(f"\n  📈 参数影响分析:")
    param_keys = list(PARAM_GRID.keys()) if any('model_type' in r.get('params',{}) for r in results) else list(QUICK_PARAM_GRID.keys())

    for key in param_keys:
        groups = defaultdict(list)
        for r in results:
            val = r['params'][key]
            groups[str(val)].append(r['total_return'])

        print(f"\n    {key}:")
        for val, rets in sorted(groups.items()):
            avg_ret = sum(rets) / len(rets)
            win_rate = sum(1 for r in rets if r > 0) / len(rets)
            print(f"      {val:10s} → 平均收益{avg_ret:+.1%} 胜率{win_rate:.0%} ({len(rets)}次)")

    # 4. 最佳配置推荐
    print(f"\n  🎯 最佳策略推荐:")
    best_sharpe = max(results, key=lambda r: r['sharpe'])
    best_return = max(results, key=lambda r: r['total_return'])
    best_stable = max([r for r in results if r['trades'] >= 5], key=lambda r: r['sharpe'] * r['win_rate'])

    print(f"  【最高收益】{best_return['symbol']} {best_return['params']}")
    print(f"    收益{best_return['total_return']:+.1%} 夏普{best_return['sharpe']:.1f} 回撤{best_return['max_drawdown']:.1%}")

    print(f"  【最稳策略】{best_stable['symbol']} {best_stable['params']}")
    print(f"    收益{best_stable['total_return']:+.1%} 夏普{best_stable['sharpe']:.1f} 回撤{best_stable['max_drawdown']:.1%}")

    return best_stable['params']

def format_short_term_strategy(params):
    """生成1-2周短线策略推荐"""
    if not params:
        return

    print(f"\n{'='*55}")
    print(f"  🚀 短线1-2周策略推荐")
    print(f"{'='*55}")
    print(f"")
    print(f"  📌 推荐参数:")
    print(f"     模型: {params.get('model_type', 'rf')}")
    print(f"     信号阈值: {params.get('threshold', 0.55)}")
    print(f"     止损: {params.get('stop_loss', -0.05):.0%}")
    print(f"     止盈: {params.get('take_profit', 0.08):.0%}")
    print(f"     仓位: {params.get('position_ratio', 0.95):.0%}")
    print(f"     特征集: {params.get('feature_set', 'full')}")
    print(f"")
    print(f"  📋 操作建议:")
    print(f"     - 每天收盘后运行: python3 run_pipeline.py --mode signal")
    print(f"     - 仅在ML信号为'买入'且概率>55%时进场")
    print(f"     - 单笔止损-5%，止盈+8%")
    print(f"     - 最多同时持有1-2只股票")
    print(f"     - 每周末复盘调参")
    print(f"")
    print(f"  ⚠️ 注意:")
    print(f"     - 回测收益包含幸存者偏差")
    print(f"     - 实盘需考虑滑点和交易成本")
    print(f"     - 建议先用模拟盘验证1-2周")
    print(f"{'='*55}\n")

def main():
    parser = argparse.ArgumentParser(description='A股批量优化器')
    parser.add_argument('--quick', action='store_true', help='快速模式（50只股票，简化参数）')
    parser.add_argument('--stocks', default=None, help='自定义股票列表文件')
    parser.add_argument('--report', action='store_true', help='仅查看上次结果')
    args = parser.parse_args()

    if args.report:
        if os.path.exists(RESULTS_FILE):
            with open(RESULTS_FILE) as f:
                results = json.load(f)
            analyze_results(results)
            return
        else:
            print("  ❌ 无历史结果，请先运行优化")
            return

    # 获取股票列表
    if args.stocks:
        with open(args.stocks) as f:
            symbols = [line.strip() for line in f if line.strip()]
    else:
        n_stocks = 30 if args.quick else 100
        symbols = get_stock_list(min_count=n_stocks)

    if not symbols:
        print("  ❌ 未获取到股票，请检查网络")
        return

    # 跑批量优化
    results = run_batch(symbols, quick=args.quick)

    # 分析结果
    best_params = analyze_results(results)

    # 生成短线策略推荐
    format_short_term_strategy(best_params)

if __name__ == '__main__':
    main()
