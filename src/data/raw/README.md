# ~/harness/stock_daily/ — 股票数据层（阶段 1 重建）

重建时间: 2026-09-23
授权: 用户拍板 stock_daily 归属 ~/harness/

## 文件
- `anchor_status_YYYY-MM-DD.json` — 锚价状态（权威源: harness/anchor_status.json，55 只）
- `realtime_prices_YYYYMMDD.json` — 当日现价（从 anchor_status 提取）
- `stock_portfolio_enriched.json` — 投资组合登记（P0 6 只 + ETF 512400，全部空仓/待确认）

## 口径
- P0 = 恒瑞医药 / 华东医药 / 恩华药业 / 科伦药业 / 药明康德 / 百利天恒 + ETF 512400
- 依据: `01-股票投研/ETF/512400_口径说明.md`
- 荣昌生物已从 P0 降级（观察池/P2）

## 约束
- 不编造持仓: position 全部为「空仓」+「待确认」
- 锚价/现价来自已有数据源，非预测
- 缺 API key 只登记，不硬编码
