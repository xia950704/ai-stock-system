# 🤖 Codex 自动交易指令

## 每日执行流程

1. **15:17** → 配对信号检查（自动 cron）
2. **15:20** → 每日报告生成（Obsidian + 日志）
3. **15:22** → 自动交易执行（Codex 模式）

## Codex 调用方式

```bash
cd /Users/xiashuang/Downloads/stock_ml_trading

# 执行当日交易
python3 run.py pairs trade

# 查看持仓状态
python3 run.py pairs trade --status

# 查看交易日志
python3 run.py pairs trade --log

# 重置模拟账户
python3 run.py pairs trade --reset
```

## 自动交易逻辑

```
每配对独立仓位管理 | 总资金¥20,000 | 最多5个同时持仓 | 每仓配额¥4,000

开仓条件: z-score < -2（股票A相对股票B低估）
平仓条件: |z-score| < 0.5（价差回归均值）/ 止损-5% / 止盈+8%
```

## 状态文件

`auto_trade_state.json` — 记录当前持仓、现金、历史交易、每日余额

## 交易记录

`logs/auto_trade_log.csv` — 每笔交易的完整记录（日期/配对/操作/价格/盈亏）

## 当前信号（可手动查看）

```bash
python3 run.py pairs signal
```