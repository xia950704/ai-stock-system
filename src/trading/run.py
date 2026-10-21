#!/usr/bin/env python3
"""
📈 股票交易策略系统 — 统一入口
===================================
整合 ML 策略 + 配对交易，统一参数、统一启动。

用法:
  # 配对交易（主要策略）
  python3 run.py pairs backtest              # 跑全配对回测
  python3 run.py pairs forward               # 前向测试（最接近实盘）
  python3 run.py pairs signal                # 检查当前信号
  python3 run.py pairs report                # 生成每日报告→Obsidian
  python3 run.py pairs dashboard             # 生成HTML仪表盘
  python3 run.py pairs dashboard --deploy    # 生成并部署到EdgeOne
  python3 run.py pairs list                  # 列出所有配对
  python3 run.py pairs 600519,000858         # 指定配对回测

  # ML 策略（已弃用，保留参考）
  python3 run.py ml                          # 跑ML回测
  python3 run.py ml --symbol 000858          # 指定个股

  # 通用
  python3 run.py --help                      # 帮助
  python3 run.py --version                   # 版本
"""
import sys, os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import INITIAL_CAPITAL

VERSION = "1.0.0"


def show_version():
    print(f"股票交易策略系统 v{VERSION}")
    print(f"策略: ML(弃用) + Pairs(活跃)")
    print(f"默认资金: ¥{INITIAL_CAPITAL:,.0f}")
    print(f"更多: python3 run.py --help")


def run_pairs(args):
    """路由到配对交易"""
    # 检查是否 trade 模式（直接路由到auto_trader）
    if args and args[0] == 'trade':
        from strategies.pairs.auto_trader import main as trade_main
        sys.argv = sys.argv[:1] + args[1:]
        trade_main()
        return
    from strategies.pairs.runner import main as pairs_main
    # 兼容位置参数写法（cron 传 `pairs signal` 而不是 `pairs --mode signal`）
    _MODES = ('full', 'backtest', 'forward', 'signal', 'list', 'check', 'report', 'dashboard')
    if args and args[0] in _MODES and '--mode' not in args:
        args = ['--mode'] + args
    sys.argv = sys.argv[:1] + args
    pairs_main()


def run_ml(args):
    """路由到ML策略（弃用）"""
    from strategies.ml.pipeline import main as ml_main
    sys.argv = sys.argv[:1] + args
    ml_main()


def main():
    parser = argparse.ArgumentParser(
        description='📈 股票交易策略系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 run.py pairs backtest          # 全配对回测
  python3 run.py pairs signal            # 查看当前信号
  python3 run.py pairs report            # 生成日报→Obsidian
  python3 run.py pairs dashboard         # HTML仪表盘
  python3 run.py pairs dashboard --deploy  # 仪表盘+部署EdgeOne
  python3 run.py pairs trade              # 自动执行交易（Codex）
  python3 run.py pairs trade --status     # 查看持仓/盈亏
  python3 run.py pairs 600519,000858     # 茅台↔五粮液回测
  python3 run.py pairs forward           # 前向测试
  python3 run.py ml                      # ML策略回测
        """
    )
    parser.add_argument('--version', action='store_true', help='显示版本')
    parser.add_argument('strategy', nargs='?', choices=['pairs', 'ml'],
                        help='策略: pairs(推荐) / ml(弃用)')
    parser.add_argument('subargs', nargs=argparse.REMAINDER,
                        help='子命令参数')

    args = parser.parse_args()

    if args.version:
        show_version()
        return

    if not args.strategy:
        parser.print_help()
        return

    if args.strategy == 'pairs':
        run_pairs(args.subargs)
    elif args.strategy == 'ml':
        run_ml(args.subargs)


if __name__ == '__main__':
    main()
