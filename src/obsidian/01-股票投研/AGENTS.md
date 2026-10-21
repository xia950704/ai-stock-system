---
processed: true
processed_date: 2026-09-28
info_card_id: "skip-p1"
---
# AGENTS.md — 01-股票投研（Codex 工作规则）

> 继承 vault 根 `AGENTS.md`；本文件只补充本目录专属规则。
> 更新: 2026-08-12

## 任务路由（周检/日跟踪/深度分析）

1. 周检/日跟踪：Hermes cron 先产数据到 `data/`（`pe_data_YYYYMMDD.json`、`bayesian/Bayesian_H0H5_概率更新_YYYYMMDD.json` 等），Codex 读取后做深度分析，不重新抓行情
2. 深度分析输出固定四段：逻辑 / 数据 / 风险 / 结论
3. 重要判断写回 `99-Agent共享记忆/`（KNOWLEDGE / DECISIONS）
4. 数据脚本在 `scripts/`、`tools/`；命令参考 `06-Agent命令清单-股票数据更新.md`

## 引用这些数据前先核实（仅在结论引用时）

1. `MOC-股票投研.md` 是导航地图，但含失效链接（如 `03-投研关键规则-v2.0.md`、`15-2026-06-05投研核心判断.md`），引用前用 `rg` 确认实际文件
2. 跟踪池：`04-医药股票跟踪池.md`；更新清单：`05-股票更新清单.md`
3. 个股数据在 `股票/<公司名>/`（kline/events/meta.json + 投资笔记）；ETF 在 `ETF/`
4. `日更/` 当前为空，勿假设有内容

## 数据纪律（必须）

1. 所有行情/财务数字注明数据日期与来源（akshare/财报/公告），禁止编造股价、PE、涨跌幅
2. 引用 `data/` 机器产出时核对文件名日期，结论标注"数据截至 YYYY-MM-DD"
3. 新分析报告命名照现有格式：`NN-主题.md` 或 `YYYY-MM-DD主题.md`；个股笔记进 `股票/<公司名>/`
4. 完成定义：结论 + 数据日期/来源 + 文件链接，三者齐全才算完成
