# P4-1 多日历史回放机制设计

> 生成时间：2026-10-20 18:57
> 模块：src/backtest/

## 一、模块结构

src/backtest/
  __init__.py        # 模块入口
  provenance.py      # 数据源溯源与反前视验证
  replay.py          # 逐日回放引擎
  evaluate.py        # 研判质量评估

## 二、回放流程

### 2.1 逐日重放 (replay_day)

1. 加载历史价格 (duckdb, trade_date <= as_of)
2. provenance 检查各数据源可用性
3. 构建 pool_status (历史价格填补 current)
4. 交易日判断 (使用 as_of 作为基准)
5. 大盘研判 (基于可用锚价/排名)
6. JEV/Search 标记为 historical_unavailable
7. 股票逐只分析 (research_override 注入 git 还原笔记)
8. 新鲜度门槛 (report_date = as_of)
9. 前视偏差检查
10. 生成报告 + JSON

### 2.2 批量回放 (run_replay)

for date in trading_dates(start, end):
    replay_day(date)
    write JSON + MD to reports/backtest/<task_id>/
write summary.json

## 三、反前视偏差控制

### 3.1 数据源日期约束

| 数据源 | 约束方式 | 实现 |
|--------|---------|------|
| K 线 | trade_date <= as_of | SQL WHERE + Python 断言 |
| 锚价快照 | 文件日期 <= as_of | provenance 选择器 |
| 排名快照 | run_date <= as_of | provenance 选择器 |
| 实时价格 | 文件日期 <= as_of | provenance 选择器 |
| 研究笔记 | git commit 日期 <= as_of | git rev-list --before |
| JEV | 无历史记录 -> 标记 unavailable | 不伪造 |
| Search | 无历史记录 -> 标记 unavailable | 不伪造 |

### 3.2 前视偏差检查 (check_lookahead)

对所有输入执行断言：
- K 线: assert max(trade_date) <= as_of
- 锚价: assert latest_date <= as_of
- 排名: assert run_date <= as_of
- 任何违规 -> lookahead_check.violations 记录

验证结果: 30/30 天 clean，0 次违规。

### 3.3 研究笔记的 git 还原

1. git rev-list -1 --before=<as_of+1day> HEAD
2. git show <commit>:01-股票投研/股票/<name>/<name>投资笔记.md
3. 返回 (content, commit, commit_date)

优势: 直接验证 as_of 当日可见的研究内容。
局限: git history 不连续 (69 commits)，某些日期无对应 commit。

## 四、回放输出

reports/backtest/<task_id>/
  summary.json              # 汇总
  2026-09-01.json           # 每日 JSON
  2026-09-01.md             # 每日报告
  ...
  evaluation.json           # 评估结果

每日输出字段: report_date, trading_day, freshness, snapshot_info,
market, stocks, provenance, lookahead_check, jev_status, search_status

## 五、评估指标

### 5.1 数据质量

| 指标 | 定义 | 当前值 |
|------|------|--------|
| anchor_availability | 有锚价快照的日期比例 | 46.7% (14/30) |
| ranking_availability | 有排名快照的日期比例 | 0% (0/30) |
| realtime_availability | 有实时快照的日期比例 | 46.7% (14/30) |
| freshness_fresh_rate | 新鲜度合格率 | 0% (历史数据均滞后) |
| lookahead_clean_rate | 前视检查通过率 | 100% (30/30) |

### 5.2 系统可靠性

| 指标 | 当前值 |
|------|--------|
| 任务成功率 | 100% (30/30) |
| 内部错误 | 0 |
| staleness_gate_blocks | 14 次 (正确降级) |

### 5.3 可追溯性

| 指标 | 当前值 |
|------|--------|
| 有支持证据的分析 | 40.8% (98/240) |
| 有反证的分析 | 0% |
| 有失效条件的分析 | 35.0% (84/240) |

### 5.4 历史表现

| action | 样本量 | 5日均收益 | 10日均收益 |
|--------|--------|----------|-----------|
| WAIT | 18 | +1.62% | +3.46% |
| HOLD | 36 | -3.00% | -6.57% |
| INSUFFICIENT_EVIDENCE | 142 | N/A | N/A |

注意: 样本量 54，可计算统计量但不可宣称稳定表现。
多数为 INSUFFICIENT_EVIDENCE (证据不足时正确拒绝判断)。

## 六、局限与诚实声明

1. 不宣称完整历史回测: 仅 2 个日期有完整引擎输入
2. 不宣称锚价策略跨期表现: 锚价快照仅 2 个日期
3. 不宣称 JEV/Search 历史效果: 无真实历史记录
4. 不宣称交易策略: 未定义仓位、成本、风险参数
5. 历史表现仅作参考: 样本量 54，不可外推
