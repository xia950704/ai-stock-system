#!/usr/bin/env python3
"""
配对交易主运行管道
====================
统计套利（基于价格比率均值回归）的完整流程：
  1️⃣ 先跑数据检查 → 列出所有配对的相关性
  2️⃣ 跑全配对回测 → 看每个配对的套利效果
  3️⃣ 跑前向测试 → 模拟实盘（逐日推进，仅用当天数据）
  4️⃣ 检查实时信号 → 看当前哪些配对有开仓机会

用法:
  python3 run_pairs.py                    # 标准流程：数据检查 → 回测
  python3 run_pairs.py --mode full        # 完整流程
  python3 run_pairs.py --mode backtest    # 仅回测
  python3 run_pairs.py --mode forward     # 仅前向测试
  python3 run_pairs.py --mode signal      # 仅检查当前信号
  python3 run_pairs.py --mode list        # 列出所有配对
  python3 run_pairs.py --pair 600519,000858  # 指定配对
"""
import sys, os, argparse
from datetime import datetime
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from core.data import fetch_a_stock_data, STOCK_POOL
from strategies.pairs.engine import (PREDEFINED_PAIRS, backtest_pair, forward_test,
                           list_pairs, calc_spread_zscore, Z_SCORE_WINDOW,
                           Z_ENTRY, Z_EXIT)


def step1_data_check():
    """
    1️⃣ 数据检查：获取所有配对数据，计算相关性
    """
    print(f"\n{'='*55}")
    print(f"  1️⃣  数据检查 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  获取配对数据并计算相关性...")
    print(f"{'=':>55}")

    results = []
    for a, b, sector, label in PREDEFINED_PAIRS:
        name_a = STOCK_POOL.get(a, a)
        name_b = STOCK_POOL.get(b, b)

        df_a = fetch_a_stock_data(a)
        df_b = fetch_a_stock_data(b)

        if df_a is None or df_b is None or len(df_a) < 30 or len(df_b) < 30:
            print(f"  ⚠️  {label} ❌ 数据不足")
            continue

        # 对齐
        merged = df_a['收盘'].to_frame('A').join(df_b['收盘'].to_frame('B'), how='inner').dropna()
        corr = merged['A'].corr(merged['B']) if len(merged) > 30 else 0
        latest_a = merged['A'].iloc[-1]
        latest_b = merged['B'].iloc[-1]
        ratio = latest_a / latest_b if latest_b > 0 else 0

        strength = "🟢强" if corr > 0.85 else ("🟡中" if corr > 0.70 else ("🔴弱" if corr > 0 else "⚪负"))
        print(f"  {strength} {label:<20s} "
              f"r={corr:.3f} "
              f"¥{latest_a:.0f}↔¥{latest_b:.0f} "
              f"比率={ratio:.2f}")
        results.append((label, corr, a, b, sector))

    # 按相关性排序
    sorted_r = sorted(results, key=lambda x: x[1], reverse=True)
    print(f"\n  📊 相关性排名:")
    for label, corr, a, b, sector in sorted_r:
        bar = "█" * int(abs(corr) * 30)
        print(f"  {bar:30s} {corr:.3f}  {label}")

    return sorted_r


def step2_backtest(pair_filter=None):
    """
    2️⃣ 跑回测
    """
    print(f"\n{'='*55}")
    print(f"  2️⃣  统计套利回测 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'=':>55}")

    if pair_filter:
        from strategies.pairs.engine import backtest_pair, print_pair_summary
        codes = pair_filter.split(',')
        pair_info = None
        for a, b, sector, label in PREDEFINED_PAIRS:
            if (a == codes[0] and b == codes[1]) or (a == codes[1] and b == codes[0]):
                pair_info = (a, b, sector, label)
                break
        if not pair_info:
            name_a = STOCK_POOL.get(codes[0], codes[0])
            name_b = STOCK_POOL.get(codes[1], codes[1])
            pair_info = (codes[0], codes[1], '自定义', f'{name_a}↔{name_b}')
        result = backtest_pair(*pair_info)
        print_pair_summary(result)
        return [result]
    else:
        from strategies.pairs.engine import run_all_backtest
        return run_all_backtest()


def step3_forward():
    """
    3️⃣ 前向测试（最接近实盘）
    """
    print(f"\n{'='*55}")
    print(f"  3️⃣  前向测试 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  逐日推进 | 仅用当天已有数据")
    print(f"{'=':>55}")
    return forward_test()


def step4_signal_check(return_data=False):
    """
    4️⃣ 检查当前配对信号
    return_data=True 时返回结构化数据给报告生成器
    """
    print(f"\n{'='*55}")
    print(f"  4️⃣  当前配对信号 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'=':>55}")

    signals_data = []
    has_signal = False

    for a, b, sector, label in PREDEFINED_PAIRS:
        name_a = STOCK_POOL.get(a, a)
        name_b = STOCK_POOL.get(b, b)

        df_a = fetch_a_stock_data(a)
        df_b = fetch_a_stock_data(b)
        if df_a is None or df_b is None:
            continue

        merged = pd.DataFrame({
            'close_A': df_a['收盘'],
            'close_B': df_b['收盘'],
        }).dropna()

        if len(merged) < Z_SCORE_WINDOW + 10:
            continue

        merged = calc_spread_zscore(merged, window=Z_SCORE_WINDOW)
        latest = merged.iloc[-1]
        z = latest['z_score'] if not pd.isna(latest['z_score']) else 0
        ratio = latest['close_A'] / latest['close_B'] if latest['close_B'] > 0 else 0
        price_a = latest['close_A']

        if z < -Z_ENTRY:
            signal = f"🟢 买入 {name_a}"
            note = f"低估(z={z:.1f})"
            has_signal = True
        elif z > Z_ENTRY:
            signal = f"🔴 {name_a}偏高"
            note = f"高估(z={z:.1f})，考虑买入{name_b}或等待回归"
        else:
            signal = "⚪ 观望"
            note = f"均值附近(z={z:.1f})"

        print(f"  {label:<22s} ¥{price_a:.0f} "
              f"比率={ratio:.2f} | {signal} | {note}")

        if return_data:
            signals_data.append({
                'label': label, 'z': z, 'price_a': price_a,
                'ratio': ratio, 'name_a': name_a, 'name_b': name_b,
                'symbol_a': a, 'symbol_b': b, 'sector': sector,
            })

    if not has_signal:
        print(f"\n  ✅ 当前无配对触发开仓条件(|z|>{Z_ENTRY})")

    return signals_data if return_data else has_signal


def step5_generate_report():
    """5️⃣ 生成每日报告（Markdown → Obsidian）"""
    print(f"\n{'='*55}")
    print(f"  5️⃣  生成每日报告 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'=':>55}")

    from utils.report import generate_daily_md

    signals = step4_signal_check(return_data=True)

    from strategies.pairs.engine import run_all_backtest
    backtest_results = run_all_backtest()

    local_path, vault_path = generate_daily_md(signals, backtest_results)
    return local_path, vault_path


def step6_generate_dashboard(deploy=False):
    """6️⃣ 生成HTML仪表盘（可选部署EdgeOne）"""
    print(f"\n{'='*55}")
    print(f"  6️⃣  生成HTML仪表盘 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'=':>55}")

    from utils.report import generate_html_dashboard, deploy_to_edgeone

    from strategies.pairs.engine import run_all_backtest
    backtest_results = run_all_backtest()

    html_path = generate_html_dashboard(backtest_results)

    if deploy:
        print()
        url = deploy_to_edgeone(html_path)
        if url:
            print(f"\n  🌐 公网地址: {url}")
        return html_path, url

    print(f"\n  💡 部署到公网: python3 run.py pairs --mode dashboard --deploy")
    return html_path, None


def main():
    parser = argparse.ArgumentParser(description='配对交易主管道 ¥20,000')
    parser.add_argument('--mode', choices=['full', 'backtest', 'forward', 'signal',
                                           'list', 'check', 'report', 'dashboard'],
                        default='backtest')
    parser.add_argument('--pair', default=None, help='指定配对，如 600519,000858')
    parser.add_argument('--deploy', action='store_true', help='部署HTML仪表盘到EdgeOne')
    args = parser.parse_args()

    print(f"""
╔═══════════════════════════════════════════════════╗
║     📈 统计套利（配对交易）系统                    ║
║     初始资金: ¥20,000 | 配对: 16对                ║
║     策略: 价格比率均值回归(不依赖ML)               ║
║     开仓: |z|>{Z_ENTRY} | 平仓: |z|<{Z_EXIT}      ║
║     时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}               ║
╚═══════════════════════════════════════════════════╝
""")

    if args.mode == 'list':
        list_pairs()
        return

    if args.mode == 'check':
        step1_data_check()
        return

    if args.mode == 'signal':
        step4_signal_check()
        return

    if args.mode == 'forward':
        step3_forward()
        return

    if args.mode == 'report':
        step5_generate_report()
        return

    if args.mode == 'dashboard':
        step6_generate_dashboard(deploy=args.deploy)
        return

    # backtest 或 full
    if args.mode in ('full',):
        step1_data_check()

    step2_backtest(args.pair)

    if args.mode == 'full':
        step3_forward()
        step4_signal_check()


if __name__ == '__main__':
    import pandas as pd
    main()