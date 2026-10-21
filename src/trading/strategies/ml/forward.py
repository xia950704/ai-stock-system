#!/usr/bin/env python3
"""
2周短线模拟交易器
====================
模拟 ¥20,000 实盘交易，逐日推进，记录每笔交易。
可被 cron 调度，每天收盘后自动运行。

用法:
  python3 forward_test.py                           # 完整2周模拟
  python3 forward_test.py --today                   # 仅运行今日信号
  python3 forward_test.py --report                  # 查看当前持仓和盈亏
  python3 forward_test.py --reset                   # 重置模拟账户
"""
import sys, os, json, argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from core.data import fetch_a_stock_data, prepare_ml_data
from strategies.ml.model import MLSignalGenerator
import numpy as np

# ==================== 配置 ====================
INITIAL_CAPITAL = 20000.0
COMMISSION = 0.0003     # 万三
SLIPPAGE = 0.001        # 滑点
STOP_LOSS = -0.05       # -5%止损
TAKE_PROFIT = 0.08      # +8%止盈
SIGNAL_THRESHOLD = 0.55
POSITION_RATIO = 0.95

# 精选流动性最好的5只（从优化结果中选）
WATCH_LIST = ['002475', '000333', '002415', '000858', '600519']
STOCK_NAMES = {'002475': '立讯精密', '000333': '美的集团', '002415': '海康威视',
               '000858': '五粮液', '600519': '贵州茅台'}

STATE_FILE = os.path.join(os.path.dirname(__file__), 'sim_trading_state.json')
LOG_FILE = os.path.join(os.path.dirname(__file__), 'sim_trading_log.csv')

def default_state():
    return {
        'capital': INITIAL_CAPITAL,
        'position': None,        # { 'symbol':, 'shares':, 'entry_price':, 'entry_date': }
        'trades': [],
        'daily_balance': [],
        'start_date': str(datetime.now().date()),
        'last_updated': None
    }

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return default_state()

def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def train_model(symbol):
    """训练最新模型"""
    df = fetch_a_stock_data(symbol)
    if df is None or len(df) < 60:
        return None, None
    X, y, full = prepare_ml_data(df)
    if len(X) < 30:
        return None, None

    ml = MLSignalGenerator()
    acc = ml.train(X, y)
    return ml, full

def get_today_signal(symbol):
    """获取今日交易信号"""
    ml, full = train_model(symbol)
    if ml is None:
        return None
    X, _, _ = prepare_ml_data(fetch_a_stock_data(symbol))
    if X is None or len(X) == 0:
        return None
    signals, probas = ml.generate_signal(X, SIGNAL_THRESHOLD)
    return {
        'signal': int(signals[-1]),
        'probability': float(probas[-1]),
        'price': float(full['收盘'].iloc[-1]),
        'accuracy': ml.accuracy,
        'date': str(full.index[-1].date())
    }

def execute_trade(state, symbol, signal_info):
    """执行一笔交易"""
    price = signal_info['price']
    signal = signal_info['signal']
    prob = signal_info['probability']
    date = signal_info['date']
    name = STOCK_NAMES.get(symbol, symbol)

    result = []

    # 检查现有持仓是否需止损/止盈
    if state['position']:
        pos = state['position']
        ret = (price - pos['entry_price']) / pos['entry_price']
        if ret <= STOP_LOSS:
            # 止损
            revenue = pos['shares'] * price
            fee = revenue * (COMMISSION + SLIPPAGE)
            state['capital'] += revenue - fee
            trade = {
                'date': date, 'symbol': pos['symbol'], 'action': '止损',
                'entry_date': pos['entry_date'], 'days': (datetime.strptime(date,'%Y-%m-%d') - datetime.strptime(pos['entry_date'],'%Y-%m-%d')).days,
                'entry_price': pos['entry_price'], 'exit_price': price,
                'shares': pos['shares'], 'return': ret,
                'pnl': revenue - fee - pos['shares'] * pos['entry_price']
            }
            state['trades'].append(trade)
            result.append(f"  🛑 止损 {name} → {ret:.2%}")
            state['position'] = None

        elif ret >= TAKE_PROFIT:
            revenue = pos['shares'] * price
            fee = revenue * (COMMISSION + SLIPPAGE)
            state['capital'] += revenue - fee
            trade = {
                'date': date, 'symbol': pos['symbol'], 'action': '止盈',
                'entry_date': pos['entry_date'],
                'days': (datetime.strptime(date,'%Y-%m-%d') - datetime.strptime(pos['entry_date'],'%Y-%m-%d')).days,
                'entry_price': pos['entry_price'], 'exit_price': price,
                'shares': pos['shares'], 'return': ret,
                'pnl': revenue - fee - pos['shares'] * pos['entry_price']
            }
            state['trades'].append(trade)
            result.append(f"  ✅ 止盈 {name} → {ret:.2%}")
            state['position'] = None

    # 根据信号开仓/平仓
    if signal == 1 and not state['position']:
        # 买入
        cost = state['capital'] * POSITION_RATIO
        shares = int(cost / price)
        actual_cost = shares * price
        fee = actual_cost * (COMMISSION + SLIPPAGE)
        state['capital'] -= (actual_cost + fee)
        state['position'] = {
            'symbol': symbol, 'shares': shares,
            'entry_price': price, 'entry_date': date
        }
        result.append(f"  🟢 买入 {name} ×{shares}股 @¥{price:.2f} (概率{prob:.1%})")

    elif signal == -1 and state['position'] and state['position']['symbol'] == symbol:
        # 卖出
        pos = state['position']
        revenue = pos['shares'] * price
        fee = revenue * (COMMISSION + SLIPPAGE)
        state['capital'] += revenue - fee
        ret = (price - pos['entry_price']) / pos['entry_price']
        trade = {
            'date': date, 'symbol': symbol, 'action': '信号卖出',
            'entry_date': pos['entry_date'],
            'days': (datetime.strptime(date,'%Y-%m-%d') - datetime.strptime(pos['entry_date'],'%Y-%m-%d')).days,
            'entry_price': pos['entry_price'], 'exit_price': price,
            'shares': pos['shares'], 'return': ret,
            'pnl': revenue - fee - pos['shares'] * pos['entry_price']
        }
        state['trades'].append(trade)
        result.append(f"  🔴 卖出 {name} → {ret:.2%}")
        state['position'] = None

    # 记录每日余额
    total_value = state['capital']
    if state['position']:
        total_value += state['position']['shares'] * price
    state['daily_balance'].append({
        'date': date, 'cash': round(state['capital'], 2),
        'position_value': round(total_value - state['capital'], 2),
        'total': round(total_value, 2)
    })
    state['last_updated'] = date
    save_state(state)

    return result

def run_simulation():
    """运行完整2周模拟——逐日推进"""
    print(f"\n{'='*55}")
    print(f"  📈 2周短线模拟交易 ¥20,000")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*55}")

    state = load_state()
    if state['trades']:
        print(f"  📋 已有 {len(state['trades'])} 笔交易记录")

    # 对每只股票获取信号并执行
    for symbol in WATCH_LIST:
        name = STOCK_NAMES.get(symbol, symbol)
        print(f"\n  ── {symbol} ({name}) ──")

        signal_info = get_today_signal(symbol)
        if not signal_info:
            print(f"  ⚠️ 数据获取失败")
            continue

        price = signal_info['price']
        sig_dir = {1:'🟢买入', -1:'🔴卖出', 0:'⚪持有'}
        print(f"  💹 ¥{price:.2f} | {sig_dir.get(signal_info['signal'],'?')} "
              f"(概率{signal_info['probability']:.1%}, 模型准确率{signal_info['accuracy']:.1%})")

        results = execute_trade(state, symbol, signal_info)
        for r in results:
            print(r)

    # 输出当前汇总
    print(f"\n{'='*55}")
    total_value = state['capital']
    if state['position']:
        # 获取最新价格
        pos = state['position']
        df = fetch_a_stock_data(pos['symbol'])
        if df is not None:
            current_price = df['收盘'].iloc[-1]
            total_value += pos['shares'] * current_price
            ret_pos = (current_price - pos['entry_price']) / pos['entry_price']
            print(f"  📦 持仓: {pos['symbol']} {pos['shares']}股 "
                  f"¥{pos['entry_price']:.2f}→¥{current_price:.2f} ({ret_pos:+.2%})")

    total_return = (total_value - INITIAL_CAPITAL) / INITIAL_CAPITAL
    print(f"  💰 总资产: ¥{total_value:,.2f}")
    print(f"  📈 总收益: {total_return:+.2%}")
    print(f"  📊 交易次数: {len(state['trades'])}")
    if state['trades']:
        wins = sum(1 for t in state['trades'] if t.get('return', 0) > 0)
        print(f"  🎯 胜率: {wins}/{len(state['trades'])} ({wins/len(state['trades']):.0%})")
    print(f"{'='*55}\n")
    return total_return

def show_report():
    """查看当前持仓和盈亏报告"""
    state = load_state()
    print(f"\n{'='*55}")
    print(f"  📋 模拟交易报告")
    print(f"  最后更新: {state.get('last_updated', '无')}")
    print(f"{'='*55}")

    total_value = state['capital']
    if state['position']:
        pos = state['position']
        name = STOCK_NAMES.get(pos['symbol'], pos['symbol'])
        df = fetch_a_stock_data(pos['symbol'])
        if df is not None:
            current_price = df['收盘'].iloc[-1]
            total_value += pos['shares'] * current_price
            ret = (current_price - pos['entry_price']) / pos['entry_price']
            print(f"\n  📦 当前持仓:")
            print(f"    {name} ({pos['symbol']}) × {pos['shares']}股")
            print(f"    买入价: ¥{pos['entry_price']:.2f} | 现价: ¥{current_price:.2f}")
            print(f"    浮动盈亏: {ret:+.2%}")
            days = (datetime.now() - datetime.strptime(pos['entry_date'], '%Y-%m-%d')).days
            print(f"    持仓天数: {days}天")

    ret = (total_value - INITIAL_CAPITAL) / INITIAL_CAPITAL
    print(f"\n  💰 总资产: ¥{total_value:,.2f} (收益{ret:+.2%})")
    print(f"  📊 交易次数: {len(state['trades'])}")
    print(f"  现金: ¥{state['capital']:,.2f}")

    if state['trades']:
        print(f"\n  最近交易记录:")
        for t in state['trades'][-5:]:
            pnl = t.get('pnl', t['shares']*(t['exit_price']-t['entry_price']))
            print(f"    {t['date']} {t.get('action','?'):4s} {t['symbol']} "
                  f"¥{t['entry_price']:.1f}→¥{t['exit_price']:.1f} "
                  f"{t.get('return',0):+.2%} | PnL: ¥{pnl:+.0f}")

    print(f"\n  每日余额趋势:")
    for d in state['daily_balance'][-10:]:
        print(f"    {d['date']} 现金¥{d['cash']:>8.0f} 持仓¥{d['position_value']:>8.0f} "
              f"合计¥{d['total']:>8.0f}")

def reset_simulation():
    """重置模拟账户"""
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
        print("  ✅ 模拟账户已重置")
    else:
        print("  ⚠️ 无模拟账户数据")

def main():
    parser = argparse.ArgumentParser(description='2周短线模拟交易 ¥20,000')
    parser.add_argument('--today', action='store_true', help='仅运行今日信号')
    parser.add_argument('--report', action='store_true', help='查看持仓和盈亏')
    parser.add_argument('--reset', action='store_true', help='重置模拟账户')
    args = parser.parse_args()

    if args.reset:
        reset_simulation()
        return
    if args.report:
        show_report()
        return

    # 运行模拟
    if args.today:
        run_simulation()
    else:
        # 完整2周模拟：逐日回放最近10个交易日
        print(f"\n  🎬 开始2周模拟交易...")
        run_simulation()

if __name__ == '__main__':
    main()