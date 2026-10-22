# 基线说明 (Baseline Documentation)

> 创建时间：2026-10-21

## 证据基线 (Evidence Baseline)

**文件**：`evidence_baseline_20261021.json`

### 捕捉内容

每次运行 `daily_judge.py --search` 时，Search API 返回的每条结果都被整理为一条 claim 记录，包含：
- `claim_id`：基于 SHA1 的稳定标识
- `facet`：研发面 (rd) / 订单面 (order) / 事件 (event)
- `status`：验证状态
- `independent_sources`：独立来源数
- `best_tier`：最优来源优先级（1=官方，5=社交）

### 验证状态含义

| 状态 | 含义 |
|---|---|
| `multi_source_confirmed` | ≥2 个独立来源且最优 tier≤3（含 relay_verified） |
| `single_source` | 仅 1 个独立来源 |
| `unverified` | 无来源或仅 tier≥4 来源 |

### 用途

对比历史基线：
- `summary.multi_source_confirmed` 比例下降 → 可能搜索质量退化或 relay 不可用
- `summary.single_source` 上升 → 第二路验证通道失效
- 按 stock 逐条对比 `status` 变化 → 定位具体标的证据退化

## 数据基线 (Data Baseline)

**文件**：`data_baseline_20261021.json`

### 捕捉内容

所有输入数据文件的清单，包含：
- `path`：文件路径
- `size_bytes`：文件大小
- `sha256`：内容哈希
- `mtime`：最后修改时间
- `source`：数据来源标记（data / report / harness）

覆盖范围：
- `src/data/raw/` — 原始行情快照
- `src/data/processed/` — 清洗后数据
- `reports/shadow/` — 当日报告
- `~/harness/` — 外部锚价/排名/持仓

### 用途

对比历史基线：
- `sha256` 变化 → 数据内容被修改（可能非预期）
- `size_bytes` 变化但 sha256 不变 → 可能是元数据变化
- `mtime` 回退 → 文件被意外还原
- 文件缺失 → 数据源不可用

## 基线生成方式

```bash
# 证据基线（每次 --search 运行后）
python3 src/engine/daily_judge.py --search --json --output reports/shadow/<date>.md

# 数据基线
python3 -c "
import json, hashlib, os
# ... 扫描目录、计算 sha256、写入 JSON
"
```

## 基线对比脚本

未来可编写 `scripts/compare_baselines.py`：
1. 加载新旧两个基线 JSON
2. 逐字段 diff
3. 输出变化报告
