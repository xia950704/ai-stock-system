#!/usr/bin/env python3
"""
统计套利模块（配对交易）
=========================
基于价格比率的均值回归策略，不依赖ML预测。
适用于A股：仅做多（买低估、卖均值回归），无需融券。

核心逻辑：
  价差 = log(股票A价格) - log(股票B价格)
  z-score = (价差 - 均值) / 标准差
  当 z < -2 → A相对B低估 → 买入A
  当 z > +2 → A相对B高估 → 若持有A则卖出
  退出条件：z-score 回归到 0 附近

用法:
  python3 pairs_trading.py                           # 跑所有配对回测
  python3 pairs_trading.py --pair 600276,603259       # 指定配对
  python3 pairs_trading.py --mode forward             # 前向测试
  python3 pairs_trading.py --list                     # 列出所有配对
"""
import sys, os, argparse, json
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from core.data import fetch_a_stock_data, STOCK_POOL

# ==================== 配置（v2 — 2026-08-26 修订） ====================
# v1 问题：无协整检验（伪回归）+ 窗口太短 + 绝对止损止盈与均值回归冲突
# v2 修订依据：茅台↔五粮液 r=0.87 但协整 p=0.066 非协整，证明 r 高≠可套利
INITIAL_CAPITAL = 20000.0
COMMISSION = 0.0003       # 万三
SLIPPAGE = 0.001           # 滑点
Z_ENTRY = 2.5             # 开仓阈值（v1=2.0 太松，30日里每1.3天触发一次；2.5σ=1.2%极端值）
Z_EXIT = 0.5              # 平仓阈值（回归到±0.5以内）
Z_SCORE_WINDOW = 60       # z-score 滚动窗口（v1=30太短被单边行情扭曲；60日更稳）
Z_STOP = 3.5             # z 反向止损（v1用-5%价格止损与均值回归冲突；z>3.5=价差趋势化不回归才止损）
POSITION_RATIO = 0.95      # 仓位比率
STRATEGY_MODE = 'mean_reversion'  # v2.2 默认均值回归（五维筛选配对协整达标，均值回归适用）；trend_following备选

# ==================== 配对准入门槛（v2 新增） ====================
MIN_CORRELATION = 0.60     # 最低相关性（v1无门槛，58对里混入r<0.2的弱对）
MAX_Coint_PVALUE = 0.05   # 协整 p 值门槛（p<0.01试过反而更差：8对6亏；p<0.05=21对+0.38%+61%胜率，验证更优）
COINT_TEST_ENABLED = True # 是否启用协整过滤（True=严格，False=仅相关性）
ROLLING_COINT_ENABLED = True  # v2.1 滚动稳定性检验（全样本p<0.05但滚动<60%=凑巧通过，应排除）
MIN_ROLLING_STABLE_PCT = 0.60 # 滚动252天窗口协整通过率门槛

# ==================== 配对定义 ====================
# (股票A, 股票B, 行业, 说明)
# v2 五维筛选发现的配对（8对，2026-08-27）
# 筛选: 相关性>0.6 + 市值比<3 + 波动比<1.5 + 协整p<0.05 + 滚动稳定>60% + 半衰期5-60天
PREDEFINED_PAIRS = [
    ('600559', '600779', '白酒', '老白干酒↔水井坊'),  # r=0.98 协整p=0.0004 半衰期=8.1天
    ('600197', '600779', '白酒', '伊力特↔水井坊'),  # r=0.973 协整p=0.0063 半衰期=8.7天
    ('600197', '600559', '白酒', '伊力特↔老白干酒'),  # r=0.9834 协整p=0.0086 半衰期=10.3天
    ('688276', '300601', '生物制品', '百克生物↔康泰生物'),  # r=0.9438 协整p=0.0123 半衰期=12.5天
    ('603392', '300601', '生物制品', '万泰生物↔康泰生物'),  # r=0.7568 协整p=0.0244 半衰期=56.1天
    ('600533', '600622', '银行', '栖霞建设↔光大嘉宝'),  # r=0.9333 协整p=0.0002 半衰期=5.8天
    ('600622', '600861', '银行', '光大嘉宝↔北京人力'),  # r=0.8947 协整p=0.0012 半衰期=9.8天
    ('001318', '002363', '新能源', '阳光乳业↔隆基机械'),  # r=0.8632 协整p=0.0014 半衰期=6.1天
]


# 前向测试专用配对（白酒3对，协整最强）
FORWARD_PAIRS = [
    ('600559', '600779', '白酒', '老白干酒↔水井坊'),
    ('600197', '600779', '白酒', '伊力特↔水井坊'),
    ('600197', '600559', '白酒', '伊力特↔老白干酒'),
]


# 全局数据缓存（避免58对回测时同一股票反复请求触发风控）
_DATA_CACHE = {}


def fetch_pair_data(symbol_a, symbol_b, days=400):
    """
    获取配对数据并对齐日期
    返回: (df_A, df_B, merged_df)
    v3: 加全局缓存，同一股票只拉一次，降低API并发避免风控
    """
    name_a = STOCK_POOL.get(symbol_a, symbol_a)
    name_b = STOCK_POOL.get(symbol_b, symbol_b)

    # 缓存命中则复用
    if symbol_a not in _DATA_CACHE:
        df_a = fetch_a_stock_data(symbol_a)
        _DATA_CACHE[symbol_a] = df_a
    else:
        df_a = _DATA_CACHE[symbol_a]

    if symbol_b not in _DATA_CACHE:
        df_b = fetch_a_stock_data(symbol_b)
        _DATA_CACHE[symbol_b] = df_b
    else:
        df_b = _DATA_CACHE[symbol_b]

    if df_a is None or df_b is None:
        return None, None, None, f"❌ {symbol_a} 或 {symbol_b} 数据获取失败"

    if len(df_a) < 60 or len(df_b) < 60:
        return None, None, None, f"❌ 数据不足 ({len(df_a)}/{len(df_b)}天)"

    # 合并对齐
    merged = pd.DataFrame({
        'close_A': df_a['收盘'],
        'close_B': df_b['收盘'],
    }).dropna()

    if len(merged) < 60:
        return None, None, None, f"❌ 对齐后仅{len(merged)}天，不足"

    return df_a, df_b, merged, None


def cointegration_test(merged):
    """
    Engle-Granger 协整检验 + 滚动稳定性检验（v2.1 新增滚动稳定性）。
    返回: (p_value, is_cointegrated, correlation)
    协整 = 价差平稳，均值回归有效；非协整 = 伪回归，z-score 会漂移不回归。

    v2.1 修订：全样本单次p值易"凑巧通过"（汾酒古井全样本p<0.05但滚动只有38%时间协整）。
    新增滚动稳定性：252天窗口滚动，要求通过率>60%才算稳定协整。
    """
    corr = merged['close_A'].corr(merged['close_B']) if len(merged) > 30 else 0

    if not COINT_TEST_ENABLED:
        return None, corr >= MIN_CORRELATION, corr

    try:
        from statsmodels.tsa.stattools import coint
        # 1. 全样本协整
        score, p_value, _ = coint(merged['close_A'], merged['close_B'])
        if p_value >= MAX_Coint_PVALUE:
            return p_value, False, corr

        # 2. 滚动稳定性检验（v2.1）：全样本通过还不够，要看是否持续
        if len(merged) >= 300 and ROLLING_COINT_ENABLED:
            window = 252
            pvals = []
            for i in range(window, len(merged), 20):  # 每20天采样
                chunk = merged.iloc[i-window:i]
                try:
                    _, p, _ = coint(chunk['close_A'], chunk['close_B'])
                    pvals.append(p)
                except Exception:
                    pvals.append(1.0)
            if pvals:
                stable_pct = sum(1 for p in pvals if p < MAX_Coint_PVALUE) / len(pvals)
                if stable_pct < MIN_ROLLING_STABLE_PCT:
                    # 全样本通过但滚动不稳定 → 标记不通过
                    return p_value, False, corr

        is_coint = p_value < MAX_Coint_PVALUE
        return p_value, is_coint, corr
    except ImportError:
        # statsmodels 缺失 → 降级仅相关性
        return None, corr >= MIN_CORRELATION, corr


def calc_spread_zscore(merged, window=Z_SCORE_WINDOW):
    """
    计算对数价差和z-score
    spread = log(price_A) - log(price_B)
    """
    merged = merged.copy()
    merged['log_A'] = np.log(merged['close_A'])
    merged['log_B'] = np.log(merged['close_B'])
    merged['spread'] = merged['log_A'] - merged['log_B']

    # 滚动z-score
    spread_mean = merged['spread'].rolling(window).mean()
    spread_std = merged['spread'].rolling(window).std()
    merged['z_score'] = (merged['spread'] - spread_mean) / spread_std

    # 价格比率（直观参考）
    merged['ratio'] = merged['close_A'] / merged['close_B']

    return merged


def generate_signals(merged, z_entry=Z_ENTRY, z_exit=Z_EXIT, mode='mean_reversion'):
    """
    生成配对交易信号
    1 = 买入股票A
    -1 = 卖出股票A（A股实盘受限，仅做信号）
    0 = 持有/观望

    mode='mean_reversion'（v2 默认）: z<-entry 买A（A低估），|z|<exit 平仓
    mode='trend_following'（v3 新增）: z>+entry 买A（A相对B走强，跟随趋势），z跌破0或动量消失平仓
        依据：当前regime所有配对价差趋势化(drift/vol>0.5)，均值回归失效，趋势跟踪适应当前行情
    """
    merged = merged.copy()
    merged['signal'] = 0

    in_position = False

    for i in range(len(merged)):
        z = merged['z_score'].iloc[i]
        if pd.isna(z):
            continue

        if mode == 'trend_following':
            # 趋势跟踪：z>+entry = A相对B走强 → 买A跟随
            if not in_position:
                if z > z_entry:
                    merged.loc[merged.index[i], 'signal'] = 1
                    in_position = True
            else:
                # z跌破0 = 趋势结束 → 平仓（不等到回归均值，趋势破了就走）
                if z < 0:
                    merged.loc[merged.index[i], 'signal'] = 0
                    in_position = False
        else:
            # 均值回归（v2）
            if not in_position:
                if z < -z_entry:
                    merged.loc[merged.index[i], 'signal'] = 1
                    in_position = True
                elif z > z_entry:
                    merged.loc[merged.index[i], 'signal'] = -1
                    in_position = True
            else:
                if abs(z) < z_exit:
                    merged.loc[merged.index[i], 'signal'] = 0
                    in_position = False

    return merged, in_position


def backtest_pair(symbol_a, symbol_b, sector, label, capital=INITIAL_CAPITAL):
    """
    单配对回测（A股兼容：做多版）
    - 信号 = 1: 买入A（A相对B便宜）
    - 持有到z-score回归0附近 → 卖出
    - 含止损止盈
    """
    name_a = STOCK_POOL.get(symbol_a, symbol_a)
    name_b = STOCK_POOL.get(symbol_b, symbol_b)

    df_a, df_b, merged, err = fetch_pair_data(symbol_a, symbol_b)
    if err:
        return {'error': err}

    # 准入门槛：均值回归需协整(价差平稳)，趋势跟踪需相关性(价差能联动)
    coint_p, is_coint, corr = cointegration_test(merged)
    if STRATEGY_MODE == 'mean_reversion':
        if not is_coint:
            reason = f"协整检验未通过(p={'%.3f'%coint_p if coint_p is not None else 'N/A'}>{MAX_Coint_PVALUE}, r={corr:.2f})" if COINT_TEST_ENABLED else f"相关性不足(r={corr:.2f}<{MIN_CORRELATION})"
            return {'error': f'⚠️ 准入门槛: {reason}', 'coint_p': coint_p, 'correlation': round(corr, 4)}
    else:  # trend_following：只要求相关性，不要求协整(趋势策略需要价差能发散)
        if corr < MIN_CORRELATION:
            return {'error': f'⚠️ 准入门槛: 相关性不足(r={corr:.2f}<{MIN_CORRELATION})', 'coint_p': coint_p, 'correlation': round(corr, 4)}

    merged = calc_spread_zscore(merged)
    merged, _ = generate_signals(merged, mode=STRATEGY_MODE)

    spread_std = merged['spread'].std()
    spread_mean = merged['spread'].mean()
    z_latest = merged['z_score'].iloc[-1] if not pd.isna(merged['z_score'].iloc[-1]) else 0

    # ===== 回测执行 =====
    cash = capital
    position = None  # {shares, entry_price, entry_date}
    trades = []
    equity_curve = []
    wins = 0
    losses = 0

    valid = merged.dropna(subset=['z_score', 'signal'])

    for i in range(len(valid)):
        date = valid.index[i]
        price = valid['close_A'].iloc[i]
        signal = valid['signal'].iloc[i]
        z = valid['z_score'].iloc[i]

        # 止损（v3：按 STRATEGY_MODE 区分）
        # 均值回归：z 反向破 Z_STOP = 价差趋势化不回归，止损
        # 趋势跟踪：z 跌破0 由 signal=0 平仓处理，无额外止损（趋势策略让利润奔跑）
        if position and STRATEGY_MODE == 'mean_reversion':
            z_at_entry = position.get('z_entry', 0)
            if z_at_entry < 0 and z > Z_STOP:
                revenue = position['shares'] * price
                fee = revenue * (COMMISSION + SLIPPAGE)
                cash += revenue - fee
                ret = (price - position['entry_price']) / position['entry_price']
                pnl = cash - position['cash_before']
                trades.append({
                    'entry': position['entry_date'], 'exit': date,
                    'action': 'z反向止损', 'return': ret, 'pnl': pnl,
                    'entry_price': position['entry_price'], 'exit_price': price,
                    'z_entry': z_at_entry, 'z_exit': z,
                    'days': (date - position['entry_date']).days
                })
                losses += 1
                position = None

        # 开仓（仅做多A）
        if signal == 1 and not position:
            cost = cash * POSITION_RATIO
            shares = int(cost / price)
            actual = shares * price
            fee = actual * (COMMISSION + SLIPPAGE)
            cash_before = cash
            cash -= (actual + fee)
            position = {
                'shares': shares, 'entry_price': price,
                'entry_date': date, 'cash_before': cash_before,
                'z_entry': z
            }

        # 平仓（z回归）
        elif signal == 0 and position:
            revenue = position['shares'] * price
            fee = revenue * (COMMISSION + SLIPPAGE)
            cash += revenue - fee
            ret = (price - position['entry_price']) / position['entry_price']
            pnl = cash - position['cash_before']
            action = '盈利' if ret > 0 else '亏损'
            trades.append({
                'entry': position['entry_date'], 'exit': date,
                'action': action, 'return': ret, 'pnl': pnl,
                'entry_price': position['entry_price'], 'exit_price': price,
                'z_entry': position['z_entry'], 'z_exit': z,
                'days': (date - position['entry_date']).days
            })
            if ret > 0: wins += 1
            else: losses += 1
            position = None

        # 记录权益
        total = cash
        if position:
            total += position['shares'] * price
        equity_curve.append({'date': str(date.date()), 'total': round(total, 2), 'z_score': round(z, 2)})

    # 收盘平仓
    if position:
        price = valid['close_A'].iloc[-1]
        revenue = position['shares'] * price
        fee = revenue * (COMMISSION + SLIPPAGE)
        cash += revenue - fee
        ret = (price - position['entry_price']) / position['entry_price']
        pnl = cash - position['cash_before']
        trades.append({
            'entry': position['entry_date'], 'exit': valid.index[-1],
            'action': '收盘平仓', 'return': ret, 'pnl': pnl,
            'entry_price': position['entry_price'], 'exit_price': price,
            'days': (valid.index[-1] - position['entry_date']).days
        })
        if ret > 0: wins += 1
        else: losses += 1
        position = None

    # 绩效汇总
    total_return = (cash - capital) / capital
    total_trades = len(trades)
    win_rate = wins / total_trades if total_trades > 0 else 0

    # 最大回撤
    if equity_curve:
        eq = pd.Series([e['total'] for e in equity_curve])
        rolling_max = eq.expanding().max()
        drawdown = (eq - rolling_max) / rolling_max
        max_dd = drawdown.min()
    else:
        max_dd = 0

    # 夏普比率
    daily_ret = pd.Series([e['total'] for e in equity_curve]).pct_change().dropna()
    sharpe = np.sqrt(252) * daily_ret.mean() / daily_ret.std() if daily_ret.std() > 0 else 0

    avg_ret = np.mean([t['return'] for t in trades]) if trades else 0
    avg_win = np.mean([t['return'] for t in trades if t['return'] > 0]) if any(t['return'] > 0 for t in trades) else 0
    avg_loss = np.mean([t['return'] for t in trades if t['return'] <= 0]) if any(t['return'] <= 0 for t in trades) else 0

    return {
        'pair': f"{name_a}({symbol_a}) ↔ {name_b}({symbol_b})",
        'sector': sector,
        'label': label,
        'symbol_a': symbol_a,
        'symbol_b': symbol_b,
        'correlation': round(corr, 4),
        'coint_p': round(coint_p, 4) if coint_p is not None else None,
        'spread_std': round(spread_std, 4),
        'spread_mean': round(spread_mean, 4),
        'z_latest': round(z_latest, 2),
        'data_days': len(merged),
        'total_return': total_return,
        'total_trades': total_trades,
        'win_rate': win_rate,
        'wins': wins,
        'losses': losses,
        'avg_return': round(avg_ret, 4),
        'avg_win': round(avg_win, 4),
        'avg_loss': round(avg_loss, 4),
        'sharpe': round(sharpe, 2),
        'max_drawdown': round(max_dd, 4),
        'final_capital': round(cash, 2),
        'trades': trades[-10:],  # 最近10笔
        'equity_curve': equity_curve[-30:],  # 最近30天
    }


def print_pair_summary(result):
    """打印单配对回测结果"""
    if 'error' in result:
        print(f"  {result['error']}")
        return

    print(f"\n{'─'*55}")
    print(f"  📊 {result['pair']}")
    print(f"  🏷️  {result['sector']} | {result['label']}")
    print(f"{'─'*55}")
    print(f"  📅  {result['data_days']}个交易日数据")
    print(f"  🔗  相关系数: {result['correlation']:.4f}")
    print(f"  📐  价差标准差: {result['spread_std']:.4f}")
    print(f"  📌  当前z-score: {result['z_latest']:+.2f}")
    print(f"  {'─'*40}")
    print(f"  💰  ¥{INITIAL_CAPITAL:,.0f} → ¥{result['final_capital']:,.0f}")
    print(f"  📈  总收益率: {result['total_return']:+.2%}")
    print(f"  📊  交易{result['total_trades']}次 | "
          f"胜{result['wins']}败{result['losses']} | "
          f"胜率{result['win_rate']:.0%}")
    if result['total_trades'] > 0:
        print(f"  📉  平均收益: {result['avg_return']:+.2%} | "
              f"平均盈利:{result['avg_win']:+.2%} | "
              f"平均亏损:{result['avg_loss']:+.2%}")
    print(f"  🛡️  夏普比率: {result['sharpe']:.2f} | "
          f"最大回撤: {result['max_drawdown']:.2%}")

    if result['trades']:
        print(f"\n  最近交易:")
        for t in result['trades'][-5:]:
            print(f"    {str(t['entry'])[:10]}→{str(t['exit'])[:10]} "
                  f"{t.get('action','?'):6s} "
                  f"{t.get('return',0):+.2%} "
                  f"PnL¥{t.get('pnl',0):+.0f}")


def list_pairs():
    """列出所有配对"""
    print(f"\n{'='*55}")
    print(f"  📋 统计套利配对列表 ({len(PREDEFINED_PAIRS)}对)")
    print(f"{'='*55}")

    sectors = {}
    for a, b, sector, label in PREDEFINED_PAIRS:
        name_a = STOCK_POOL.get(a, a)
        name_b = STOCK_POOL.get(b, b)
        sectors.setdefault(sector, [])
        sectors[sector].append(f"  {name_a}({a}) ↔ {name_b}({b})")

    for sector, pairs in sectors.items():
        print(f"\n  🏷️  [{sector}] ({len(pairs)}对)")
        for p in pairs:
            print(f"  {p}")

    print(f"\n{'='*55}")
    print(f"  开仓条件: |z-score| > {Z_ENTRY}")
    print(f"  平仓条件: |z-score| < {Z_EXIT}")
    print(f"  滚动窗口: {Z_SCORE_WINDOW}天")
    print(f"{'='*55}\n")


def deduplicate_pairs(pairs, max_per_stock=3):
    """
    配对去重（v2 新增）。
    同一只股票参与太多对会导致信号重叠时仓位叠加，风险敞口远超单对资金。
    策略：先对每对跑协整+相关性，按 p 值升序（越显著越优先）排序，
    同一只股票最多保留 max_per_stock 对，砍掉弱的。
    返回去重后的配对列表。
    """
    print(f"\n  🔍 配对去重（每股票最多{max_per_stock}对，按协整显著性排序）...")

    scored = []
    for a, b, sector, label in pairs:
        df_a, df_b, merged, err = fetch_pair_data(a, b)
        if err:
            continue
        p_val, is_coint, corr = cointegration_test(merged)
        if not is_coint:
            continue
        scored.append({
            'a': a, 'b': b, 'sector': sector, 'label': label,
            'p': p_val if p_val is not None else 1.0,
            'corr': corr,
        })

    # 按 p 升序（越显著越靠前），p 相同时按 r 降序
    scored.sort(key=lambda x: (x['p'], -x['corr']))

    stock_count = {}
    kept = []
    dropped = 0
    for s in scored:
        cnt_a = stock_count.get(s['a'], 0)
        cnt_b = stock_count.get(s['b'], 0)
        if cnt_a >= max_per_stock or cnt_b >= max_per_stock:
            dropped += 1
            continue
        kept.append((s['a'], s['b'], s['sector'], s['label']))
        stock_count[s['a']] = cnt_a + 1
        stock_count[s['b']] = cnt_b + 1

    print(f"  ✅ 协整通过 {len(scored)} 对 → 去重后保留 {len(kept)} 对（砍 {dropped} 对重叠）")
    return kept


def run_all_backtest():
    """跑所有配对回测"""
    print(f"\n{'='*55}")
    print(f"  📈 统计套利全配对回测")
    print(f"  初始资金: ¥{INITIAL_CAPITAL:,} | 每次仓位: {POSITION_RATIO:.0%}")
    print(f"  开仓: |z|>{Z_ENTRY} | 平仓: |z|<{Z_EXIT} | 窗口: {Z_SCORE_WINDOW}天")
    if STRATEGY_MODE == 'trend_following':
        print(f"  模式: 趋势跟踪(z>+entry买A,z<0平仓) | 准入: 相关性>{MIN_CORRELATION}(不要求协整)")
    else:
        print(f"  模式: 均值回归 | z反向止损: |z|>{Z_STOP} | 协整门槛: p<{MAX_Coint_PVALUE} | 滚动稳定>{MIN_ROLLING_STABLE_PCT:.0%}")
    print(f"{'='*55}")

    # v2 新增：协整过滤 + 去重
    active_pairs = deduplicate_pairs(PREDEFINED_PAIRS, max_per_stock=3)

    results = []
    for a, b, sector, label in active_pairs:
        name_a = STOCK_POOL.get(a, a)
        name_b = STOCK_POOL.get(b, b)
        print(f"\n  ▶ {label} ({name_a} ↔ {name_b})...")
        result = backtest_pair(a, b, sector, label)
        print_pair_summary(result)
        if 'error' not in result:
            results.append(result)

    # 汇总排名
    print(f"\n{'='*60}")
    print(f"  📊 全配对回测排名")
    print(f"{'='*60}")
    print(f"  {'配对联':<30s} {'收益':>8s} {'交易':>4s} {'胜率':>5s} {'夏普':>5s}")
    print(f"  {'─'*56}")

    sorted_results = sorted(results, key=lambda r: r['total_return'], reverse=True)
    for r in sorted_results:
        label = r['label']
        ret = f"{r['total_return']:+.2%}"
        trades = str(r['total_trades'])
        wr = f"{r['win_rate']:.0%}"
        sp = f"{r['sharpe']:.1f}"
        marker = "✅" if r['total_return'] > 0 else "❌"
        print(f"  {marker} {label:<28s} {ret:>8s} {trades:>4s} {wr:>5s} {sp:>5s}")

    # 平均
    if sorted_results:
        avg_ret = np.mean([r['total_return'] for r in sorted_results])
        avg_trades = np.mean([r['total_trades'] for r in sorted_results])
        avg_wr = np.mean([r['win_rate'] for r in sorted_results])
        print(f"  {'─'*56}")
        print(f"  {'📊 平均':<30s} {avg_ret:>+8.2%} {avg_trades:>4.0f} {avg_wr:>5.0%}")

    return sorted_results


# ==================== 前向测试 ====================
def forward_test(pairs=None):
    """
    前向测试：只用最近N天数据模拟实盘
    每天只根据当天已有数据判断是否开仓
    pairs: 指定配对列表，默认全部PREDEFINED_PAIRS
    """
    if pairs is None:
        pairs = PREDEFINED_PAIRS

    print(f"\n{'='*60}")
    print(f"  📈 配对交易前向测试（模拟实盘）")
    print(f"  ¥{INITIAL_CAPITAL:,} | {len(pairs)}个配对 | 逐日推进 | 仅用当天数据")
    print(f"{'='*60}")

    overall_results = []

    for a, b, sector, label in pairs:
        name_a = STOCK_POOL.get(a, a)
        name_b = STOCK_POOL.get(b, b)
        print(f"\n  ── {label} ({name_a} ↔ {name_b}) ──")

        df_a, df_b, merged, err = fetch_pair_data(a, b, days=400)
        if err:
            print(f"  {err}")
            continue

        # 只用最后30天做前向测试
        test_days = 30
        total_days = len(merged)
        test_start = max(0, total_days - test_days - Z_SCORE_WINDOW)

        cash = INITIAL_CAPITAL
        position = None
        trades = []
        daily_balance = []

        for i in range(max(Z_SCORE_WINDOW, test_start), total_days):
            # 只用截至今天的数据
            hist = merged.iloc[:i+1].copy()
            hist = calc_spread_zscore(hist, window=Z_SCORE_WINDOW)

            today = hist.iloc[-1]
            date = str(today.name.date())
            price = today['close_A']
            z = today['z_score'] if not pd.isna(today['z_score']) else 0

            # z 反向止损/趋势平仓（v3：按 STRATEGY_MODE 区分）
            if position:
                z_at_entry = position.get('z_entry', 0)
                if STRATEGY_MODE == 'trend_following':
                    # 趋势跟踪：z跌破0=趋势结束平仓
                    if z < 0:
                        revenue = position['shares'] * price
                        fee = revenue * (COMMISSION + SLIPPAGE)
                        cash += revenue - fee
                        ret = (price - position['entry_price']) / position['entry_price']
                        trades.append(f"🔚趋势平仓 {date} {ret:.2%} (z={z:.1f})")
                        position = None
                else:
                    # 均值回归：z反向破 Z_STOP 止损
                    if z_at_entry < 0 and z > Z_STOP:
                        revenue = position['shares'] * price
                        fee = revenue * (COMMISSION + SLIPPAGE)
                        cash += revenue - fee
                        ret = (price - position['entry_price']) / position['entry_price']
                        trades.append(f"🛑z反向止损 {date} {ret:.2%} (z={z:.1f})")
                        position = None

            # 开仓信号
            if not position:
                # v3：趋势跟踪 z>+entry 买A；均值回归 z<-entry 买A
                entry_cond = (z > Z_ENTRY) if STRATEGY_MODE == 'trend_following' else (z < -Z_ENTRY)
                if entry_cond:
                    cost = cash * POSITION_RATIO
                    shares = int(cost / price)
                    actual = shares * price
                    fee = actual * (COMMISSION + SLIPPAGE)
                    cash_before = cash
                    cash -= (actual + fee)
                    position = {
                        'shares': shares, 'entry_price': price,
                        'cash_before': cash_before, 'entry_date': date,
                        'z_entry': z
                    }
                    trades.append(f"🟢买入 {date} ¥{price:.1f}×{shares} (z={z:.1f})")
                elif STRATEGY_MODE == 'mean_reversion' and z > Z_ENTRY and position:
                    # 均值回归：理论上卖出A的信号，A股实盘只能先平仓
                    if position:
                        revenue = position['shares'] * price
                        fee = revenue * (COMMISSION + SLIPPAGE)
                        cash += revenue - fee
                        ret = (price - position['entry_price']) / position['entry_price']
                        trades.append(f"🔴卖出 {date} {ret:.2%} (z={z:.1f})")
                        position = None

            # 均值回归：z回归后平仓（趋势模式已在上方z<0时平仓）
            elif position and STRATEGY_MODE == 'mean_reversion' and abs(z) < Z_EXIT:
                revenue = position['shares'] * price
                fee = revenue * (COMMISSION + SLIPPAGE)
                cash += revenue - fee
                ret = (price - position['entry_price']) / position['entry_price']
                trades.append(f"🔚回归平仓 {date} {ret:.2%} (z={z:.1f})")
                position = None

            # 每日余额
            total = cash
            if position:
                total += position['shares'] * price
            daily_balance.append({'date': date, 'total': round(total, 2), 'z': round(z, 2)})

        # 收盘平仓
        if position:
            price = merged['close_A'].iloc[-1]
            revenue = position['shares'] * price
            fee = revenue * (COMMISSION + SLIPPAGE)
            cash += revenue - fee
            ret = (price - position['entry_price']) / position['entry_price']
            trades.append(f"🔚收盘平仓 {ret:.2%}")
            position = None

        total_ret = (cash - INITIAL_CAPITAL) / INITIAL_CAPITAL
        win_trades = sum(1 for t in trades if '%' in t and ('+' in t[t.index(' '):] if ' ' in t else False))
        # simplified win count

        print(f"  💰 ¥{INITIAL_CAPITAL:,} → ¥{cash:,.0f} ({total_ret:+.2%})")
        print(f"  📊 交易{len(trades)}笔")
        if trades:
            for t in trades[-5:]:
                print(f"    {t}")

        overall_results.append({
            'label': label,
            'return': total_ret,
            'trades': len(trades),
            'final': cash
        })

    # 汇总
    if overall_results:
        wins = sum(1 for r in overall_results if r['return'] > 0)
        losses = sum(1 for r in overall_results if r['return'] <= 0)

        print(f"\n{'='*60}")
        print(f"  📊 前向测试汇总（{len(overall_results)}对）")
        print(f"  {'='*56}")
        for r in sorted(overall_results, key=lambda x: x['return'], reverse=True):
            marker = "✅" if r['return'] > 0 else "❌"
            bar = "█" * max(1, int(abs(r['return']) * 200))
            print(f"  {marker} {r['label']:<22s} {bar} {r['return']:+.2%}  "
                  f"交易{r['trades']}次")
        avg = np.mean([r['return'] for r in overall_results])
        total = sum(r['final'] for r in overall_results)
        print(f"  {'='*56}")
        print(f"  📊 平均收益: {avg:+.2%} | 盈利{wins}对/亏损{losses}对")
        print(f"  💰 组合总资产({len(overall_results)}份×¥{INITIAL_CAPITAL:,.0f}): "
              f"¥{total:,.0f} ({ (total/len(overall_results)/INITIAL_CAPITAL-1):+.2%})")
        print(f"  {'='*56}")

    return overall_results


def main():
    parser = argparse.ArgumentParser(description='统计套利（配对交易）回测系统')
    parser.add_argument('--pair', default=None, help='指定配对代码,如 600519,000858')
    parser.add_argument('--mode', choices=['backtest', 'forward', 'list'],
                        default='backtest')
    parser.add_argument('--capital', type=float, default=INITIAL_CAPITAL,
                        help=f'初始资金(默认¥{INITIAL_CAPITAL:,})')
    args = parser.parse_args()

    if args.mode == 'list':
        list_pairs()
        return

    if args.mode == 'forward':
        forward_test()
        return

    if args.pair:
        codes = args.pair.split(',')
        if len(codes) != 2:
            print("❌ 请用逗号分隔两个股票代码，如 600519,000858")
            return

        pair_info = None
        for a, b, sector, label in PREDEFINED_PAIRS:
            if (a == codes[0] and b == codes[1]) or (a == codes[1] and b == codes[0]):
                pair_info = (a, b, sector, label)
                break

        if not pair_info:
            name_a = STOCK_POOL.get(codes[0], codes[0])
            name_b = STOCK_POOL.get(codes[1], codes[1])
            pair_info = (codes[0], codes[1], '自定义', f'{name_a}↔{name_b}')

        name_a = STOCK_POOL.get(codes[0], codes[0])
        name_b = STOCK_POOL.get(codes[1], codes[1])
        print(f"\n  ▶ 自定义配对: {name_a} ↔ {name_b}")
        result = backtest_pair(*pair_info)
        print_pair_summary(result)
    else:
        run_all_backtest()


if __name__ == '__main__':
    main()