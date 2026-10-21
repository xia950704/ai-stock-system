# P4 修改记录与回滚说明

> 生成时间：2026-10-20 18:57

---

## 一、新增文件

| 文件 | 说明 |
|------|------|
| `src/backtest/__init__.py` | 模块入口 |
| `src/backtest/provenance.py` | 数据源溯源与反前视验证 |
| `src/backtest/replay.py` | 逐日回放引擎 |
| `src/backtest/evaluate.py` | 研判质量评估 |
| `src/decision/__init__.py` | 模块入口 |
| `src/decision/contract.py` | Decision Model 契约与校验 |
| `src/decision/registry.py` | Decision Model 注册表与对比 |
| `p4-audit/data-coverage.md` | 历史数据可用性审计 |
| `p4-audit/backtest-design.md` | 回放机制设计文档 |
| `p4-audit/backtest-results.md` | 回放执行结果 |
| `p4-audit/decision-model-contract.md` | Decision Model 契约 |
| `p4-audit/decision-model-options.md` | 用户填写的候选模型区域 |
| `p4-audit/search-jev-availability.md` | Search/JEV 可用性记录 |
| `p4-audit/test-report.md` | 测试报告 |
| `p4-audit/remediation-log.md` | 本文件 |
| `p4-audit/p4-acceptance.md` | 验收清单 |
| `p4-audit/tests/test_backtest.py` | P4 测试套件 |

---

## 二、修改文件

| 文件 | 修改内容 | 影响范围 |
|------|----------|----------|
| `src/engine/stock_judge.py` | 1. `judge_stock` 增加 `research_override` 参数\n2. `apply_staleness_to_analysis` 增加 `report_date` 参数 | 历史回放注入 git 还原的研究笔记；历史回放使用正确的 report_date 计算新鲜度 |
| `src/backtest/provenance.py` | 移除 `CURRENT_ANCHOR_DATA_DATE` 等硬编码假设，仅使用显式日期文件 | 修正锚价/排名/实时快照选择逻辑，避免假设当前文件存在 |

---

## 三、回滚步骤

### 3.1 回滚新增文件

```bash
# 删除 backtest 模块
rm -rf /Users/xiashuang/AI-股票系统/src/backtest/

# 删除 decision 模块
rm -rf /Users/xiashuang/AI-股票系统/src/decision/

# 删除 p4-audit 目录
rm -rf /Users/xiashuang/AI-股票系统/p4-audit/
```

### 3.2 回滚 stock_judge.py

```bash
# 恢复原版 (需从 git 恢复或备份)
cd /Users/xiashuang/AI-股票系统
# 1. 恢复 judge_stock 签名
# 2. 恢复 apply_staleness_to_analysis 签名
```

### 3.3 回滚 provenance.py

```bash
# 恢复原版
cd /Users/xiashuang/AI-股票系统
git checkout src/backtest/provenance.py  # 如有 git
```

---

## 四、验证回滚

回滚后运行：
1. `python3 -m src.engine.daily_judge --mock-jev --mock-search` - 应正常运行
2. `python3 -m pytest p3-audit/tests/` - 应 28/28 通过
2. `python3 -m pytest p4-audit/tests/` - 应无测试 (目录已删除)

---

## 五、影响评估

| 影响项 | 评估 |
|--------|------|
| P3 日常引擎 | 无影响 (stock_judge 参数有默认值，向后兼容) |
| Obsidian 原始文件 | 无修改 (只读) |
| GitHub Workflow | 无修改 |
| 全局配置 | 无修改 |
| 真实交易 | 未执行 |
