#!/usr/bin/env python3
"""
配对交易自动执行器（Codex 可调用）
=====================================
每天收盘后自动执行：
  1. 读取所有配对的实时信号
  2. 检查现有持仓（每对独立仓位管理）
  3. 判断是否开仓/平仓（z-score + 止损止盈）
  4. 执行模拟交易，记录到状态文件
  5. 生成交易日志 CSV

用法:
  python3 strategies/pairs/auto_trader.py            # 自动执行当日交易
  python3 strategies/pairs/auto_trader.py --status   # 查看持仓和盈亏
  python3 strategies/pairs/auto_trader.py --reset    # 重置模拟账户
  python3 strategies/pairs/auto_trader.py --log      # 查看历史交易
"""
import sys, os, json, csv, argparse
from datetime import datetime, date
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from core.data import fetch_a_stock_data, STOCK_POOL
from strategies.pairs.engine import (PREDEFINED_PAIRS, calc_spread_zscore,
                                     Z_SCORE_WINDOW, Z_ENTRY, Z_EXIT,
                                     STOP_LOSS, TAKE_PROFIT, COMMISSION,
                                     SLIPPAGE, POSITION_RATIO)

# ==================== 配置 ====================
INITIAL_CAPITAL = 20000.0       # 总资金
MAX_POSITIONS = 5               # 最大同时持仓数
CAPITAL_PER_SLOT = INITIAL_CAPITAL / MAX_POSITIONS  # ¥4,000/每对

# 活跃交易配对（从15对中精选最有把握的）
ACTIVE_PAIRS = PREDEFINED_PAIRS  # 可用全部，但可以只选有把握的

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          '..', '..', 'auto_trade_state.json')
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        '..', '..', 'logs', 'auto_trade_log.csv')


def default_state():
    return {
        'capital': INITIAL_CAPITAL,
        'positions': [],      # [{label, symbol, shares, entry_price, entry_z, entry_date, slot_capital}]
        'trades': [],          # [{date, label, action, entry_price, exit_price, return, pnl}]
        'daily_balance': [],
        'start_date': str(date.today()),
        'last_updated': None
    }


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding='utf-8') as f:
            return json.load(f)
    return default_state()


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def get_pair_signals():
    """获取所有配对的当前z-score和价格"""
    signals = []
    for a, b, sector, label in ACTIVE_PAIRS:
        name_a = STOCK_POOL.get(a, a)
        name_b = STOCK_POOL.get(b, b)

        df_a = fetch_a_stock_data(a)
        df_b = fetch_a_stock_data(b)
        if df_a is None or df_b is None:
            continue

        merged = df_a['收盘'].to_frame('close_A').join(
            df_b['收盘'].to_frame('close_B'), how='inner').dropna()

        if len(merged) < Z_SCORE_WINDOW + 10:
            continue

        merged = calc_spread_zscore(merged, window=Z_SCORE_WINDOW)
        latest = merged.iloc[-1]
        z = latest['z_score'] if not pd.isna(latest['z_score']) else 0
        price = latest['close_A']
        ratio = latest['close_A'] / latest['close_B'] if latest['close_B'] > 0 else 0

        signals.append({
            'label': label, 'symbol_a': a, 'symbol_b': b,
            'name_a': name_a, 'name_b': name_b, 'sector': sector,
            'z': z, 'price': price, 'ratio': ratio,
            'date': str(merged.index[-1].date())
        })

    return signals


def find_position(state, label):
    """按配对label查找持仓"""
    for i, pos in enumerate(state['positions']):
        if pos['label'] == label:
            return i, pos
    return None, None


def execute_daily(state, signals):
    """
    自动执行当日交易
    返回: action_log (list of strings)
    """
    today = str(date.today())
    action_log = []
    cash = state['capital']

    # 查找当日价格（用于止损止盈计算）
    for sig in signals:
        label = sig['label']
        z = sig['z']
        price = sig['price']
        name_a = sig['name_a']
        pos_idx, position = find_position(state, label)

        # === 检查现有持仓的止损止盈 ===
        if position:
            # 获取该股票最新价格
            symbol = position['symbol']
            df = fetch_a_stock_data(symbol)
            if df is not None and len(df) > 0:
                current_price = float(df['收盘'].iloc[-1])
            else:
                current_price = price

            ret = (current_price - position['entry_price']) / position['entry_price']

            # 止损
            if ret <= STOP_LOSS:
                revenue = position['shares'] * current_price
                fee = revenue * (COMMISSION + SLIPPAGE)
                cash += revenue - fee
                pnl = revenue - fee - position['slot_capital']
                state['positions'].pop(pos_idx)
                trade = {
                    'date': today, 'label': label,
                    'action': '🛑 止损', 'symbol': symbol,
                    'entry_date': position['entry_date'],
                    'entry_price': position['entry_price'],
                    'exit_price': current_price,
                    'return': ret, 'pnl': round(pnl, 2),
                    'reason': f'止损{ret:.2%}'
                }
                state['trades'].append(trade)
                action_log.append(
                    f"  🛑 止损 {label} "
                    f"¥{position['entry_price']:.1f}→¥{current_price:.1f} ({ret:.2%}) "
                    f"PnL¥{pnl:+.0f}"
                )
                continue

            # 止盈
            if ret >= TAKE_PROFIT:
                revenue = position['shares'] * current_price
                fee = revenue * (COMMISSION + SLIPPAGE)
                cash += revenue - fee
                pnl = revenue - fee - position['slot_capital']
                state['positions'].pop(pos_idx)
                trade = {
                    'date': today, 'label': label,
                    'action': '✅ 止盈', 'symbol': symbol,
                    'entry_date': position['entry_date'],
                    'entry_price': position['entry_price'],
                    'exit_price': current_price,
                    'return': ret, 'pnl': round(pnl, 2),
                    'reason': f'止盈{ret:.2%}'
                }
                state['trades'].append(trade)
                action_log.append(
                    f"  ✅ 止盈 {label} "
                    f"¥{position['entry_price']:.1f}→¥{current_price:.1f} ({ret:.2%}) "
                    f"PnL¥{pnl:+.0f}"
                )
                continue

            # z-score 回归平仓
            if abs(z) < Z_EXIT:
                revenue = position['shares'] * price
                fee = revenue * (COMMISSION + SLIPPAGE)
                cash += revenue - fee
                pnl = revenue - fee - position['slot_capital']
                state['positions'].pop(pos_idx)
                trade = {
                    'date': today, 'label': label,
                    'action': '🔚 回归平仓', 'symbol': symbol,
                    'entry_date': position['entry_date'],
                    'entry_price': position['entry_price'],
                    'exit_price': price,
                    'return': (price - position['entry_price']) / position['entry_price'],
                    'pnl': round(pnl, 2),
                    'reason': f'z回归(z={z:.1f})'
                }
                state['trades'].append(trade)
                action_log.append(
                    f"  🔚 回归平仓 {label} "
                    f"¥{position['entry_price']:.1f}→¥{price:.1f} "
                    f"PnL¥{pnl:+.0f}"
                )
                continue

            # 持仓中，无操作
            action_log.append(
                f"  📦 持仓 {label} "
                f"z={z:+.1f} 浮动盈亏{ret:.2%}"
            )

        # === 开仓信号 ===
        # 条件：z < -2（低估）AND 该配对无持仓 AND 未达到最大持仓数
        elif z < -Z_ENTRY:
            if len(state['positions']) >= MAX_POSITIONS:
                action_log.append(
                    f"  ⚠️  {label} 信号触发但已达最大持仓({MAX_POSITIONS})，跳过"
                )
                continue

            # 检查可用资金
            slot_capital = CAPITAL_PER_SLOT
            if slot_capital > cash:
                action_log.append(
                    f"  ⚠️  {label} 信号触发但现金不足(¥{cash:.0f}<¥{slot_capital:.0f})，跳过"
                )
                continue

            # 执行买入
            cost = slot_capital * POSITION_RATIO
            shares = int(cost / price)
            actual = shares * price
            fee = actual * (COMMISSION + SLIPPAGE)
            cash -= (actual + fee)

            state['positions'].append({
                'label': label,
                'symbol': sig['symbol_a'],
                'shares': shares,
                'entry_price': price,
                'entry_z': round(z, 2),
                'entry_date': today,
                'slot_capital': round(slot_capital, 2),
                'capital_used': round(actual + fee, 2)
            })
            state['trades'].append({
                'date': today, 'label': label, 'action': '🟢 开仓',
                'symbol': sig['symbol_a'],
                'entry_date': today, 'entry_price': price, 'exit_price': None,
                'return': 0.0, 'pnl': 0.0, 'reason': f'z={z:.1f} 开仓'
            })

            action_log.append(
                f"  🟢 买入 {label} "
                f"¥{price:.1f}×{shares}股 "
                f"(z={z:.1f}, ¥{slot_capital:.0f}配额)"
            )

    # 更新现金
    state['capital'] = round(cash, 2)

    # 记录每日余额
    total_value = state['capital']
    pos_value = sum(p['shares'] * fetch_stock_price(p['symbol'], fallback=p['entry_price'])
                    for p in state['positions'])
    total_value += pos_value

    state['daily_balance'].append({
        'date': today,
        'cash': round(state['capital'], 2),
        'position_value': round(pos_value, 2),
        'total': round(total_value, 2),
        'positions': len(state['positions'])
    })
    state['last_updated'] = today
    save_state(state)

    return action_log


def fetch_stock_price(symbol, fallback=0):
    """获取股票最新价格"""
    df = fetch_a_stock_data(symbol)
    if df is not None and len(df) > 0:
        p = float(df['收盘'].iloc[-1])
        if p > 0:
            return p
    return fallback


def save_log_csv(state):
    """追加交易到CSV日志"""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    file_exists = os.path.exists(LOG_FILE)

    with open(LOG_FILE, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['日期', '配对', '操作', '买入价', '卖出价', '收益率', '盈亏', '原因'])

        for t in state['trades']:
            writer.writerow([
                t.get('date', ''),
                t.get('label', ''),
                t.get('action', ''),
                t.get('entry_price', ''),
                t.get('exit_price', ''),
                f"{t.get('return', 0):.2%}",
                t.get('pnl', ''),
                t.get('reason', '')
            ])


def show_status():
    """查看当前持仓和盈亏"""
    state = load_state()
    total_value = state['capital']

    print(f"\n{'='*55}")
    print(f"  📋 自动交易状态报告")
    print(f"  最后更新: {state.get('last_updated', '无')}")
    print(f"  运行天数: {len(state.get('daily_balance', []))}")
    print(f"{'='*55}")

    # 持仓
    positions = state.get('positions', [])
    pos_value = 0
    if positions:
        print(f"\n  📦 当前持仓 ({len(positions)}个):")
        for p in positions:
            price = fetch_stock_price(p['symbol'], fallback=p['entry_price'])
            ret = (price - p['entry_price']) / p['entry_price'] if p['entry_price'] > 0 else 0
            pos_value += p['shares'] * price
            marker = "🟢" if ret > 0 else "🔴"
            print(f"  {marker} {p['label']:<22s} {p['shares']}股 "
                  f"¥{p['entry_price']:.1f}→¥{price:.1f} ({ret:+.2%}) "
                  f"入z={p['entry_z']:+.1f}")
    else:
        print(f"\n  📦 无持仓")
        pos_value = 0

    total_value = state['capital'] + pos_value
    ret = (total_value - INITIAL_CAPITAL) / INITIAL_CAPITAL
    print(f"\n  💰 总资产: ¥{total_value:,.2f}")
    print(f"     现金:   ¥{state['capital']:,.2f}")
    print(f"     持仓:   ¥{pos_value:,.2f}")
    print(f"  📈 总收益: {ret:+.2%}")
    print(f"  📊 交易次数: {len(state.get('trades', []))}")

    # 汇总胜率
    trades = [t for t in state.get('trades', []) if not str(t.get('action', '')).startswith('🟢')]
    if trades:
        wins = sum(1 for t in trades if t.get('return', 0) > 0)
        losses = sum(1 for t in trades if t.get('return', 0) <= 0)
        print(f"  🎯 胜率: {wins}/{len(trades)} ({wins/len(trades):.0%})")

        print(f"\n  最近5笔交易:")
        for t in trades[-5:]:
            print(f"    {t['date']} {t.get('action','?'):6s} {t['label']:<16s} "
                  f"{t.get('return',0):+.2%}  PnL¥{t.get('pnl',0):+.0f}")

    print()


def show_log():
    """显示交易日志"""
    if not os.path.exists(LOG_FILE):
        print("  ⚠️  暂无交易日志")
        return

    df = pd.read_csv(LOG_FILE)
    print(f"\n  📋 交易日志 ({len(df)}条)")
    print(df.to_string(index=False))
    print()


def reset():
    """重置模拟账户"""
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
        print("  ✅ 自动交易账户已重置")
    else:
        print("  ⚠️  无自动交易账户数据")


def main():
    parser = argparse.ArgumentParser(description='配对交易自动执行器')
    parser.add_argument('--status', action='store_true', help='查看持仓和盈亏')
    parser.add_argument('--reset', action='store_true', help='重置模拟账户')
    parser.add_argument('--log', action='store_true', help='查看交易日志')
    args = parser.parse_args()

    if args.reset:
        reset()
        return
    if args.status:
        show_status()
        return
    if args.log:
        show_log()
        return

    # === 自动执行当日交易 ===
    today = str(date.today())
    print(f"\n{'='*55}")
    print(f"  🤖 配对交易自动执行器")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  资金: ¥{INITIAL_CAPITAL:,} | 最大持仓: {MAX_POSITIONS} | 每仓配额: ¥{CAPITAL_PER_SLOT:.0f}")
    print(f"{'='*55}")

    state = load_state()
    print(f"  当前持仓: {len(state.get('positions', []))}个")
    print(f"  累计交易: {len(state.get('trades', []))}笔\n")

    # 获取信号
    print(f"  📡 获取配对信号...")
    try:
        import pandas as pd
    except ImportError:
        print("  ❌ 需要 pandas")
        return

    signals = get_pair_signals()
    print(f"  ✅ 获取 {len(signals)}/15 对有效\n")

    # 打印信号摘要
    buy_count = sum(1 for s in signals if s['z'] < -Z_ENTRY)
    over_count = sum(1 for s in signals if s['z'] > Z_ENTRY)
    neutral_count = len(signals) - buy_count - over_count
    print(f"  🟢 买入信号: {buy_count} | 🔴 偏高: {over_count} | ⚪ 观望: {neutral_count}")

    if buy_count > 0:
        print(f"\n  🟢 触发开仓信号:")
        for s in signals:
            if s['z'] < -Z_ENTRY:
                print(f"    {s['label']:<22s} z={s['z']:+.1f} ¥{s['price']:.0f}")

    # 执行交易
    print(f"\n  🎯 执行交易...")
    action_log = execute_daily(state, signals)
    for a in action_log:
        print(a)

    # 保存日志
    save_log_csv(state)

    # 摘要
    trades = state.get('trades', [])
    recent = [t for t in trades if t.get('date') == today]
    print(f"\n  {'='*45}")
    print(f"  📊 今日执行摘要")
    print(f"  今日交易: {len(recent)}笔")
    print(f"  当前持仓: {len(state.get('positions', []))}个")
    print(f"  可用现金: ¥{state['capital']:,.2f}")
    print(f"  历史交易: {len(trades)}笔")
    if trades:
        closed = [t for t in trades if not str(t.get('action', '')).startswith('🟢')]
        if closed:
            wins = sum(1 for t in closed if t.get('return', 0) > 0)
            print(f"  历史胜率: {wins}/{len(closed)} ({wins/len(closed):.0%})")
    print(f"  {'='*45}\n")


if __name__ == '__main__':
    main()
