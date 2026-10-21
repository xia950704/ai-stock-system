---
name: system-warmup-trading
description: >-
  交易系统预热入口 — 输出「系统结构/当前能做的事/持仓状态/建议下一步」。
  触发词：预热交易系统、配对交易、自动交易、回测、盯盘。
  具体操作交给 stock-research 技能。
trigger_keywords: ["预热交易系统", "配对交易", "自动交易", "回测", "盯盘", "持仓"]
category: finance
version: 1.0.0
updated: 2026-09-23
---

# 交易系统预热

把配对交易系统预热成一张能力地图，让夏爽一眼看清现在能做什么。

## 系统结构
- 引擎：~/stock_ml_trading/（run.py，28 py）
- 策略：pairs（配对交易）、ml（机器学习）、rotation（轮动）
- 调度：系统 crontab 5 条（signal/report/trade/backtest/ml-signal）
- 状态：auto_trade_state.json（持仓/现金/历史）
- 日志：logs/auto_trade_log.csv

## 当前能做的事
1. 查当日配对信号：python3 ~/stock_ml_trading/run.py pairs signal
2. 查持仓状态：python3 ~/stock_ml_trading/run.py pairs trade --status
3. 查交易日志：python3 ~/stock_ml_trading/run.py pairs trade --log
4. 周末回测：python3 ~/stock_ml_trading/run.py pairs backtest
5. ML 信号：python3 ~/stock_ml_trading/run.py ml --mode signal

## cron 时间表
- 15:17 配对信号 / 15:20 报告 / 15:22 自动交易（周一至五）
- 09:17 周六回测 / 09:30 ML 信号（周一至五）

## 建议下一步
- 查持仓 → run.py pairs trade --status
- 查信号 → run.py pairs signal
