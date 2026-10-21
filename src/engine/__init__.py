"""每日研判引擎（P3-2）。

模块边界：
  - data_loader.py     : 输入数据读取与校验
  - trading_day.py     : 交易日与行情新鲜度判断
  - market_judge.py    : 大盘环境分析
  - stock_judge.py     : 关注股票逐只分析
  - jev_adapter.py     : JEV 调用适配（含降级）
  - report.py          : 报告生成
  - daily_judge.py     : CLI 入口 / 编排
"""
