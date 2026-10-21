---
name: system-warmup-stock
description: >-
  投研系统预热入口：加载 stock-research 技能，读取投研监控池与锚价状态，
  输出「系统结构 / 当前能做的事 / 监控池状态 / 建议下一步」。
  触发词：预热投研系统、投研、监控池。（具体投研操作交给 stock-research 技能）
trigger_keywords: ["预热投研系统", "投研", "监控池", "系统预热"]
whenToUse: 用户说「预热投研系统」或表达投研意图但还没指定具体操作时。
---

# 投研系统预热

把投研系统"预热"成一张能力地图，让夏爽一眼看清现在能做什么。

## 步骤
1. 用 skill 工具加载 stock-research，获得完整投研指令。
2. 只读读取投研状态文件：
   - ~/.hermes/workspace/stock_daily/anchor_status_*.json（取最新日期，锚价状态）
   - ~/.hermes/workspace/stock_daily/realtime_prices_*.json（取最新日期，实时价）
   - ~/.agent-context/ACTIVE_TASKS.md（投研相关任务）
3. 只读不改，不跑任何交易/操作建议。

## 输出格式（四段）
1. 系统结构：投研技能依赖的数据源与文件路径。
2. 当前能做的事：查价 / 扫财报 / 三诊 / GF-DMA 评分 / 建仓对照。
3. 监控池状态：P0/P1 各股票当前锚价与状态（来自最新 anchor_status）。
4. 建议的下一步：一个 2 分钟内能完成的具体动作。

## 边界
- 医疗归临床，投研归市场，绝不给操作建议。
- 数据只来自上述文件，不臆测价格。
