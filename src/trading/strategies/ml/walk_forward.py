#!/usr/bin/env python3
"""
两周历史模拟回放：逐日推进，模拟实盘交易
用最近10个交易日的数据做前向测试
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from core.data import fetch_a_stock_data, prepare_ml_data
from strategies.ml.model import MLSignalGenerator
import numpy as np

INITIAL_CAPITAL = 20000.0
COMMISSION = 0.0003
SLIPPAGE = 0.001
STOP_LOSS = -0.05
TAKE_PROFIT = 0.08
SIGNAL_THRESHOLD = 0.55
POSITION_RATIO = 0.95
STOCKS = ['002475', '000333', '002415', '000858', '600519']
STOCK_NAMES = {'002475':'立讯精密','000333':'美的集团','002415':'海康威视',
               '000858':'五粮液','600519':'贵州茅台'}

def simulate(symbol):
    name = STOCK_NAMES.get(symbol, symbol)
    df = fetch_a_stock_data(symbol)
    if df is None or len(df) < 80:
        print(f"\n  ── {symbol} ({name}) ── ❌ 数据不足"); return

    test_days = 15  # 模拟3周
    total_days = len(df)
    capital = INITIAL_CAPITAL
    position = None
    trades = []
    daily = []
    wins = losses = 0

    for i in range(total_days - test_days, total_days):
        train = df.iloc[:i]
        price = float(df['收盘'].iloc[i])
        date = str(df.index[i].date())

        # 训练模型
        X, y, _ = prepare_ml_data(train)
        if len(X) < 20:
            daily.append({'date': date, 'total': capital}); continue

        ml = MLSignalGenerator()
        ml.train(X, y)

        # 预测
        last_X = X.iloc[-1:].values if hasattr(X, 'iloc') else np.array([X[-1]]).reshape(1,-1)
        prob_up = ml.model.predict_proba(last_X)[0][1]
        signal = 1 if prob_up > SIGNAL_THRESHOLD else (-1 if prob_up < (1 - SIGNAL_THRESHOLD) else 0)

        # 止损止盈检查
        if position:
            ret = (price - position['entry_price']) / position['entry_price']
            if ret <= STOP_LOSS:
                capital += position['shares'] * price * (1 - COMMISSION - SLIPPAGE)
                trades.append(f"🛑止损 {date} {ret:.2%}"); losses += 1; position = None
            elif ret >= TAKE_PROFIT:
                capital += position['shares'] * price * (1 - COMMISSION - SLIPPAGE)
                trades.append(f"✅止盈 {date} {ret:.2%}"); wins += 1; position = None

        # 开仓
        if signal == 1 and not position:
            shares = int(capital * POSITION_RATIO / price)
            cost = shares * price * (1 + COMMISSION + SLIPPAGE)
            capital -= cost
            position = {'shares': shares, 'entry_price': price}
            trades.append(f"🟢买入 {date} ¥{price:.1f} ×{shares} (概率{prob_up:.0%})")

        # 平仓
        elif signal == -1 and position:
            capital += position['shares'] * price * (1 - COMMISSION - SLIPPAGE)
            ret = (price - position['entry_price']) / position['entry_price']
            if ret > 0: wins += 1
            else: losses += 1
            trades.append(f"🔴卖出 {date} ¥{position['entry_price']:.1f}→¥{price:.1f} {ret:.2%}")
            position = None

        # 每日总值
        total = capital + (position['shares'] * price if position else 0)
        daily.append({'date': date, 'total': round(total, 2)})

    # 收盘平仓
    if position:
        capital += position['shares'] * price * (1 - COMMISSION - SLIPPAGE)
        ret = (price - position['entry_price']) / position['entry_price']
        trades.append(f"🔚收盘 {date} 平仓 {ret:.2%}")
        if ret > 0: wins += 1
        else: losses += 1
        position = None

    total_ret = (capital - INITIAL_CAPITAL) / INITIAL_CAPITAL
    total_trades = wins + losses

    print(f"\n  ── {symbol} ({name}) ──")
    print(f"  📅 {df.index[total_days-test_days].date()} → {df.index[-1].date()} ({test_days}天)")
    print(f"  💰 ¥{INITIAL_CAPITAL:,.0f} → ¥{capital:,.0f} ({total_ret:+.2%})")
    if total_trades > 0:
        print(f"  📊 交易{total_trades}次 | 胜{wins}败{losses} | 胜率{wins/total_trades:.0%}")
    print(f"  📉 股价: ¥{df['收盘'].iloc[total_days-test_days]:.1f} → ¥{df['收盘'].iloc[-1]:.1f}")

    print(f"\n  交易明细:")
    for t in trades[:10]: print(f"    {t}")
    if len(trades) > 10: print(f"    ... 还有{len(trades)-10}笔")

    print(f"\n  每日余额:")
    for d in daily:
        arrow = "📈" if d['total'] > INITIAL_CAPITAL else "📉"
        print(f"    {d['date']} {arrow} ¥{d['total']:>8.2f}")

    return total_ret, total_trades, wins, losses

print(f"\n{'='*60}")
print(f"  📈 2周短线模拟回放 ¥20,000")
print(f"  逐日推进 | 每步仅用当时已有数据")
print(f"{'='*60}")
all_results = []
for s in STOCKS:
    r = simulate(s)
    if r: all_results.append(r)

print(f"\n{'='*60}")
print(f"  汇总:")
total = sum(r[0] for r in all_results) / len(all_results) if all_results else 0
all_trades = sum(r[1] for r in all_results)
all_wins = sum(r[2] for r in all_results)
all_losses = sum(r[3] for r in all_results)
print(f"  5只股票平均收益: {total:+.2%}")
print(f"  总交易: {all_trades}次 | 胜{all_wins}败{all_losses}")
if all_trades > 0:
    print(f"  综合胜率: {all_wins/all_trades:.0%}")
print(f"{'='*60}")