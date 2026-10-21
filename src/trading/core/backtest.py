"""
回测引擎模块：模拟交易、计算绩效
初始资金 ¥20,000，T+1 短线交易
"""
import numpy as np
import pandas as pd
from datetime import datetime

INITIAL_CAPITAL = 20000.0      # 初始资金 ¥20,000
COMMISSION_RATE = 0.0003       # 万三佣金
SLIPPAGE = 0.001               # 滑点 0.1%
STOP_LOSS = -0.05              # 单笔止损 -5%
TAKE_PROFIT = 0.08             # 单笔止盈 +8%
POSITION_RATIO = 0.95          # 每次仓位 95%

class BacktestEngine:
    def __init__(self, df, signals, prices):
        self.df = df                           # 原始数据
        self.signals = signals                 # 信号序列 (1买入,0不动,-1卖出)
        self.prices = prices                   # 价格序列
        self.capital = INITIAL_CAPITAL
        self.positions = []                    # 持仓记录
        self.trades = []                       # 交易记录
        self.equity_curve = []                 # 权益曲线
        self.in_position = False
        self.entry_price = 0.0
        self.entry_date = None
        self.shares = 0
        self.daily_returns = []

    def run(self):
        """执行回测"""
        self.equity_curve.append(self.capital)

        for i in range(1, len(self.df)):
            date = self.df.index[i]
            price = self.prices[i]
            signal = self.signals[i]

            # === 检查止损止盈 ===
            if self.in_position:
                ret = (price - self.entry_price) / self.entry_price
                if ret <= STOP_LOSS or ret >= TAKE_PROFIT:
                    self._close_position(date, price, f"{'止损' if ret <= STOP_LOSS else '止盈'}({ret:.2%})")

            # === 执行信号 ===
            if signal == 1 and not self.in_position:
                self._open_position(date, price)
            elif signal == -1 and self.in_position:
                self._close_position(date, price, "信号卖出")

            # 记录权益
            current_equity = self.capital
            if self.in_position:
                current_equity += self.shares * price
            self.equity_curve.append(current_equity)

        # 收盘平仓
        if self.in_position:
            self._close_position(self.df.index[-1], self.prices[-1], "收盘平仓")

        return self._summary()

    def _open_position(self, date, price):
        """开仓"""
        cost = self.capital * POSITION_RATIO
        self.shares = int(cost / price)
        actual_cost = self.shares * price
        commission = actual_cost * COMMISSION_RATE
        slippage_cost = actual_cost * SLIPPAGE
        self.capital -= (actual_cost + commission + slippage_cost)
        self.in_position = True
        self.entry_price = price
        self.entry_date = date
        self.positions.append({'date': date, 'price': price, 'shares': self.shares})

    def _close_position(self, date, price, reason):
        """平仓"""
        revenue = self.shares * price
        commission = revenue * COMMISSION_RATE
        slippage_cost = revenue * SLIPPAGE
        self.capital += (revenue - commission - slippage_cost)
        ret = (price - self.entry_price) / self.entry_price
        self.trades.append({
            'entry_date': self.entry_date,
            'exit_date': date,
            'entry_price': self.entry_price,
            'exit_price': price,
            'return': ret,
            'reason': reason
        })
        self.in_position = False
        self.shares = 0
        self.entry_price = 0.0

    def _summary(self):
        """汇总绩效"""
        if not self.trades:
            return {'error': '无交易', 'total_return': 0, 'capital': self.capital}

        total_return = (self.capital - INITIAL_CAPITAL) / INITIAL_CAPITAL
        wins = [t for t in self.trades if t['return'] > 0]
        losses = [t for t in self.trades if t['return'] <= 0]
        win_rate = len(wins) / len(self.trades) if self.trades else 0

        # 计算夏普比率 (假设无风险利率=0)
        self.equity_curve = pd.Series(self.equity_curve)
        self.daily_returns = self.equity_curve.pct_change().dropna()
        sharpe = np.sqrt(252) * self.daily_returns.mean() / self.daily_returns.std() if self.daily_returns.std() > 0 else 0

        # 最大回撤
        rolling_max = self.equity_curve.expanding().max()
        drawdown = (self.equity_curve - rolling_max) / rolling_max
        max_drawdown = drawdown.min()

        avg_win = np.mean([t['return'] for t in wins]) if wins else 0
        avg_loss = np.mean([t['return'] for t in losses]) if losses else 0

        return {
            '初始资金': f"¥{INITIAL_CAPITAL:,.0f}",
            '最终资金': f"¥{self.capital:,.0f}",
            '总收益率': f"{total_return:.2%}",
            '交易次数': len(self.trades),
            '胜率': f"{win_rate:.1%}",
            '平均盈利': f"{avg_win:.2%}",
            '平均亏损': f"{avg_loss:.2%}",
            '夏普比率': f"{sharpe:.2f}",
            '最大回撤': f"{max_drawdown:.2%}",
            '最后10笔交易': self.trades[-10:] if self.trades else []
        }

    def print_summary(self, summary):
        """打印绩效摘要"""
        print("\n" + "="*50)
        print("           📊 回测绩效报告")
        print("="*50)
        for k, v in summary.items():
            if k == '最后10笔交易': continue
            print(f"  {k:10s}: {v}")
        print("-"*50)

        if '最后10笔交易' in summary and summary['最后10笔交易']:
            print("  最近10笔交易:")
            for t in summary['最后10笔交易'][-5:]:
                print(f"    {str(t['entry_date'])[:10]}→{str(t['exit_date'])[:10]} "
                      f"{t['reason']:6s} {t['return']:+.2%}")
        print("="*50)

if __name__ == '__main__':
    from core.data import generate_synthetic_data, prepare_ml_data
    from strategies.ml.model import MLSignalGenerator

    df = generate_synthetic_data(n_days=250)
    X, y, df_full = prepare_ml_data(df)
    ml = MLSignalGenerator()
    ml.train(X, y)

    signals, probas = ml.generate_signal(X, threshold=0.55)
    engine = BacktestEngine(df_full.iloc[-len(signals):], signals, df_full['Close'].values[-len(signals):])
    summary = engine.run()
    engine.print_summary(summary)