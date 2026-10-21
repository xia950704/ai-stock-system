# P4 验收清单

> 生成时间：2026-10-20 18:57
> 验收范围：多日历史回放、研判质量评估、Decision Model 框架、Search/JEV 状态

---

## 一、P4-0 历史数据可用性审计

| ID | 要求 | 状态 | 证据 |
|---|---|---|---|
| A-01 | 建立历史数据清单 | PASS | `data-coverage.md` §1-2 |
| A-02 | 明确三类数据区分 | PASS | `data-coverage.md` §3.2 |
| A-03 | 判断回放可行性 | PASS | `data-coverage.md` §3.3 (模式A/B) |
| A-04 | 创建数据覆盖报告 | PASS | `data-coverage.md` |

---

## 二、P4-1 多日历史回放机制

| ID | 要求 | 状态 | 证据 |
|---|---|---|---|
| B-01 | 按交易日顺序处理 | PASS | `backtest-design.md` §2, `replay.py` |
| B-02 | 使用当时可得输入 | PASS | `provenance.py` 选择器 |
| B-03 | 生成对应日期研判 | PASS | `reports/backtest/1a3b24fdb5a6/*.md` |
| B-04 | 记录数据/代码/规则版本 | PASS | 输出含 provenance/replay_task_id |
| B-05 | 保留输出与历史报告对应 | PASS | 写入独立目录 `reports/backtest/` |
| B-06 | 相同输入可重复运行 | PASS | 评估重复性测试通过 |
| B-07 | 新结果写入独立目录 | PASS | `reports/backtest/<task_id>/` |
| B-08 | 反前视偏差控制 | PASS | `check_lookahead` 30/30 clean |
| B-09 | 研究笔记 git 还原 | PASS | `research_note_asof` |
| B-10 | 历史无 JEV/Search 标记 | PASS | historical_unavailable |

---

## 三、P4-2 研判质量评估

| ID | 要求 | 状态 | 证据 |
|---|---|---|---|
| C-01 | 数据质量指标 | PASS | `evaluate.py` data_quality |
| C-02 | 系统可靠性指标 | PASS | `evaluate.py` system_reliability |
| C-03 | 可追溯性指标 | PASS | `evaluate.py` traceability |
| C-04 | 历史表现评估 | PASS | `evaluate.py` forward_returns (54样本) |
| C-05 | 样本量/缺失/不确定性保留 | PASS | evaluation.json 注明 54 样本、多数 INSUFFICIENT |
| C-06 | 不擅自建立交易策略 | PASS | 未定义仓位/成本/风险，仅报告设计 |
| C-07 | 结果诚实 (无少样本宣称稳定) | PASS | 标注 "不可宣称稳定表现" |

---

## 四、P4-3 Decision Model 框架

| ID | 要求 | 状态 | 证据 |
|---|---|---|---|
| D-01 | 职责边界分离 | PASS | `decision-model-contract.md` §1 |
| D-02 | 统一调用契约 | PASS | `contract.py` DecisionInput/Output |
| D-03 | 当前/备选模型空白留存 | PASS | `decision-model-options.md` 全空白 |
| D-04 | 模型注册与对比框架 | PASS | `registry.py` compare_outputs |
| D-05 | 安全要求 (Key在配置/环境变量) | PASS | `decision-model-options.md` §二 |

---

## 五、P4-4 Search/JEV 历史边界

| ID | 要求 | 状态 | 证据 |
|---|---|---|---|
| E-01 | Search 真实调用探测 | PASS | `search-jev-availability.md` §1 |
| E-02 | Search 配置位置记录 | PASS | `search-jev-availability.md` §1.4 |
| E-03 | JEV 真实调用探测 | PASS | `search-jev-availability.md` §2 |
| E-04 | JEV 配置位置记录 | PASS | `search-jev-availability.md` §2.4 |
| E-05 | 历史边界记录 | PASS | `search-jev-availability.md` §3 |

---

## 六、P4-5 测试与验收

| ID | 要求 | 状态 | 证据 |
|---|---|---|---|
| F-01 | 单日回放测试 | PASS | P1-1 |
| F-02 | 多日回放测试 | PASS | P1-6, 长回放 30/30 |
| F-03 | 缺失数据处理 | PASS | INSUFFICIENT_EVIDENCE 正确 |
| F-04 | 输入重复测试 | PASS | evaluate_repeatability |
| F-05 | 前视偏差检查 | PASS | 30/30 clean |
| F-06 | 同输入重复运行 | PASS | 重复性测试通过 |
| F-07 | 历史数据不足停止/降级 | PASS | DATE_UNKNOWN -> OBSERVE |
| F-08 | 判断缺失/无法判断 | PASS | INSUFFICIENT_EVIDENCE 统计 |
| F-09 | 预测期限无覆盖 | PASS | 评估标注不可计算 |
| F-10 | 样本量不足 | PASS | evaluation.json 注明 54 样本 |
| F-11 | 指标计算一致性 | PASS | evaluate.py 统计分母一致 |
| F-12 | 缺交易策略参数不自动模拟 | PASS | 未定义参数，仅报告设计 |
| F-13 | Search Mock/未配置/超时 | PASS | 测试覆盖 (client.py) |
| F-14 | JEV Mock/失败/未验证 | PASS | 测试覆盖 (stock_judge.py) |
| F-15 | 数据保护 | PASS | 无 Obsidian 修改/无覆盖历史/无秘密输出 |

---

## 七、交付物完整性

| ID | 交付物 | 状态 | 路径 |
|---|---|---|---|
| G-01 | data-coverage.md | PASS | `p4-audit/data-coverage.md` |
| G-02 | backtest-design.md | PASS | `p4-audit/backtest-design.md` |
| G-03 | backtest-results.md | PASS | `p4-audit/backtest-results.md` |
| G-04 | decision-model-contract.md | PASS | `p4-audit/decision-model-contract.md` |
| G-05 | decision-model-options.md | PASS | `p4-audit/decision-model-options.md` |
| G-06 | search-jev-availability.md | PASS | `p4-audit/search-jev-availability.md` |
| G-07 | test-report.md | PASS | `p4-audit/test-report.md` |
| G-08 | remediation-log.md | PASS | `p4-audit/remediation-log.md` |
| G-09 | p4-acceptance.md | PASS | 本文件 |

---

## 八、关键约束验证

| 约束 | 验证结果 |
|---|---|
| 不修改 Obsidian 原始文件 | PASS (HEAD 仍为 2734b0a1) |
| 不覆盖历史报告 | PASS (输出到独立目录) |
| 不修改 GitHub Workflow | PASS (未触碰) |
| 不修改全局配置 | PASS (未修改) |
| 不安装新依赖 | PASS (仅标准库 + duckdb/httpx) |
| 不执行真实交易 | PASS (纯研究模式) |
| 不自动启用定时任务 | PASS (仅手动运行) |
| 不打印秘密 | PASS (日志脱敏) |

---

## 九、遗留问题

| ID | 问题 | 等级 | 说明 |
|---|---|---|---|
| H-01 | JEV 真实调用不可用 | BLOCKED | relay 转发 bug + bynara 积分不足 |
| H-02 | Search 真实调用可用 | PASS | 已验证可用 |
| H-03 | 锚价/排名历史快照缺失 | NOT TESTED | 仅 2 日期有快照，无法评估完整引擎跨期表现 |
| H-04 | JEV/Search 历史记录缺失 | NOT TESTED | 无真实历史记录 |
| H-05 | 历史表现样本量不足 | NOT TESTED | 仅 54 样本，不可外推 |
| H-06 | Decision Model 候选模型未填写 | NOT TESTED | 等待用户填写 |

---

## 十、验收结论

**P4 有条件通过**

条件：
1. JEV 真实调用仍 BLOCKED (需修复 relay 转发 bug + bynara 积分)
2. 完整引擎历史回放仅覆盖 2 个日期，锚价/排名历史快照缺失
3. Decision Model 候选模型配置需用户填写
4. 历史表现样本量 54，可计算统计量但不可宣称稳定表现

**已完成**：
- 历史数据审计完整，回放框架建立并验证 (30/30 成功)
- 反前视机制有效 (0 次违规)
- 降级逻辑正确 (INSUFFICIENT_EVIDENCE/OBSERVE)
- Decision Model 契约/注册表/对比框架完整
- Search 真实调用已解除阻碍
- 所有测试通过 (59/59)

**建议下一步**：
- 用户修复 JEV relay + 积分
- 用户填写 Decision Model 候选模型配置
- 若需完整历史回测，需建立锚价/排名/实时价格的每日自动归档

---

## 十一、回滚步骤

见 `remediation-log.md` 第 3 节。删除 `src/backtest/`、`src/decision/`、`p4-audit/`，回滚 `stock_judge.py` 两处签名变更。

---

## 十二、签字确认

| 角色 | 姓名 | 日期 | 签字 |
|---|---|---|---|
| 项目负责人 | 夏爽 | 2026-10-20 | （待用户确认） |
| 执行 Agent | Codex | 2026-10-20 | ✅ |
