# P4 测试报告

> 生成时间：2026-10-20 18:57

---

## 一、测试执行汇总

| 测试套件 | 通过 | 失败 | 跳过 | 说明 |
|---|---|---|---|---|
| `provenance.py` (数据源溯源) | 10 | 0 | 0 | 交易日列表、K线无前视、快照选择、git还原、前视检查 |
| `replay.py` (回放引擎) | 6 | 0 | 0 | 单日回放、批量回放、provenance集成、前视检查、JEV/Search标记 |
| `evaluate.py` (质量评估) | 6 | 0 | 0 | 数据质量、系统可靠性、可追溯性、前视收益、重复性 |
| `decision/contract.py` (契约校验) | 4 | 0 | 0 | 合法输出、非法action、confidence越界、缺字段 |
| `decision/registry.py` (注册表) | 5 | 0 | 0 | 空注册表、添加/重复、对比输出、同一/不同 |
| **P4 核心测试** | **31** | **0** | **0** | **全部通过** |
| P3 继承测试 (`test_engine.py`) | 28 | 0 | 0 | 复用验证 |

**总计：59 通过，0 失败，0 跳过**

---

## 二、关键测试详情

### 2.1 Provenance 测试

| 测试 | 场景 | 预期 | 实际 |
|---|---|---|---|
| P0-1 | duckdb kline 可用 | True | PASS |
| P0-2 | 交易日列表获取 | >0 | PASS (9天) |
| P0-3 | K线无前视 | max <= as_of | PASS |
| P0-4 | 锚价快照选择 | 09-23 | PASS |
| P0-5 | 当前日期回退快照 | 09-23 | PASS |
| P0-6 | 排名快照不可用 | False | PASS |
| P0-7 | 实时快照选择 | 09-23 | PASS |
| P0-8 | 研究笔记 git 还原 | available=True | PASS |
| P0-9 | provenance_check 结构 | 完整 | PASS |
| P0-10 | 前视偏差检查 | clean=True | PASS |

### 2.2 Replay 测试

| 测试 | 场景 | 预期 | 实际 |
|---|---|---|---|
| P1-1 | 单日回放 | success | PASS (2026-10-15) |
| P1-2 | 回放含 provenance | 有字段 | PASS |
| P1-3 | 前视检查 | clean=True | PASS |
| P1-4 | JEV/Search 标记 | historical_unavailable | PASS |
| P1-5 | 快照信息 | 含可用性 | PASS |
| P1-6 | 批量回放 2天 | success=2 | PASS |

### 2.3 Evaluate 测试

| 测试 | 场景 | 预期 | 实际 |
|---|---|---|---|
| E1 | 评估完整运行 | 含所有维度 | PASS |
| E2 | 无前视违规 | 0 | PASS |
| E3 | 0 内部错误 | 0 | PASS |
| E4 | action 分布有值 | >0 | PASS |
| E5 | 前视收益可计算 | computable=True | PASS |
| E6 | 样本量>0 | >0 | PASS (54) |

### 2.4 Decision Contract 测试

| 测试 | 场景 | 预期 | 实际 |
|---|---|---|---|
| C1 | 合法输出 | ok=True | PASS |
| C2 | 非法 action | ok=False | PASS |
| C3 | confidence 越界 | ok=False | PASS |
| C4 | 缺 model_id | ok=False | PASS |

### 2.5 Registry 测试

| 测试 | 场景 | 预期 | 实际 |
|---|---|---|---|
| R1 | 空注册表 | len=0 | PASS |
| R2 | 添加模型 | added=True | PASS |
| R3 | 重复添加拒绝 | added=False | PASS |
| R4 | 对比同一 | identical=True | PASS |
| R5 | 对比不同 | identical=False | PASS |

---

## 三、回放验证

| 场景 | 参数 | 结果 |
|---|---|---|
| 短回放 | 2026-10-15 ~ 2026-10-16 | 2/2 success |
| 长回放 | 2026-09-01 ~ 2026-10-20 | 30/30 success |
| 评估运行 | reports/backtest/1a3b24fdb5a6 | 全维度通过 |

---

## 四、测试限制

| 限制 | 说明 |
|---|---|
| 真实 JEV 调用 | 仅 Mock 验证，真实调用 BLOCKED (relay bug + 积分) |
| 真实 Search 调用 | 探测通过，但测试中仅用 Mock |
| 历史回测 | 使用固定样本 (30天)，非完整历史回测 |
| 并发/压力 | 未覆盖 |
| 交易策略 | 未定义仓位/成本/风险参数，不测试组合收益 |

---

## 五、结论

**所有测试通过 (59/59)**。P4 核心功能：
1. 历史数据溯源与反前视验证通过
2. 多日回放机制端到端工作 (30/30 成功)
3. 质量评估全维度通过
4. Decision Model 契约与注册表功能正确
5. P3 继承测试复用通过
