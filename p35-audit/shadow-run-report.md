# P3.5 影子运行报告

> 生成时间：2026-10-20 17:30
> 运行日期：2026-10-20（三次运行：fresh / stale-gate / search-mock）

---

## 一、运行摘要

| 运行 | 参数 | 数据日期 | 关键结果 |
|---|---|---|---|
| Fresh | `--mock-jev` | 2026-10-20 | 数据新鲜度正常，百利天恒 CONSIDER_ENTRY 有效 |
| Stale Gate | 模拟 asof=09-30 | 2026-09-30 | CONSIDER_ENTRY 降级 OBSERVE（阻断生效） |
| Search Mock | `--mock-jev --mock-search` | 2026-10-20 | Search Layer 渲染，claim 状态 multi_source_confirmed/single_source |

---

## 二、数据新鲜度对比

| 指标 | P3 (旧) | P3.5 Fresh (新) |
|---|---|---|
| realtime_prices | 20260923.json | 20261020.json |
| stock_ranking run_date | 2026-10-19 | 2026-10-20 |
| ranking latest_date (P0) | 2026-09-30 | 2026-10-20 |
| anchor current (恒瑞) | 46.08 | 47.45 |
| 引擎数据新鲜度 | "行情日期 2026-09-30" | "行情日期 2026-10-20，数据新鲜度：正常" |

---

## 三、大盘研判对比

| 运行 | 判断 | 置信度 | 关键证据 |
|---|---|---|---|
| Fresh | 中性 | low | 锚价池平均偏离 +12.17%，卖出信号 26/0 |
| Stale Gate | (同 Fresh，仅 stock action 不同) | - | - |

---

## 四、个股行动建议对比

| 股票 | Fresh (10-20 data) | Stale Gate (模拟 09-30) | 说明 |
|---|---|---|---|
| 恒瑞医药 | HOLD | HOLD | 偏离 1% |
| 华东医药 | WAIT | WAIT | 偏离 -1% |
| 恩华药业 | HOLD | HOLD | 偏离 3.4% |
| 科伦药业 | HOLD | HOLD | 偏离 2.9% |
| 药明康德 | HOLD | HOLD | 偏离 1.8% |
| **百利天恒** | **CONSIDER_ENTRY** | **OBSERVE (staleness_blocked)** | 偏离 -12.7%，stale gate 降级 |
| 512400 ETF | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE | 无锚价 |
| 荣昌生物 | HOLD | HOLD | 偏离 5.1% |

---

## 五、Search API Mock 探查结果

| 股票 | queries | claims | 状态 | 示例 claim |
|---|---|---|---|---|
| 恒瑞医药 | 3 (rd/order/event) | 3 | ok | [single_source] NMPA 受理新适应证申请 (tier=1) |
| 华东医药 | 3 | 3 | ok | [single_source] 三季报披露 (tier=3) |
| ... | ... | ... | ok | ... |

> **注**：Mock 结果显示 `single_source`，真实调用需多源验证。真实 Search API 因 relay 无搜索 key 处于 BLOCKED 状态。

---

## 六、异常场景验证

| 场景 | 测试方法 | 结果 |
|---|---|---|
| 实时价格缺失 | 删除 realtime_prices_*.json | 引擎降级使用 anchor current，报告标注数据质量 |
| JEV 不可用 | 不加 `--mock-jev` | 报告标注 "JEV 调用失败 (model_na/insufficient)，不参与判断" |
| Search 不可用 | 不加 `--mock-search` | search_layer 缺失，报告标注 "未启用" |
| 数据过期 | 手动构造 asof=09-30 | stale gate 阻断 CONSIDER_ENTRY/REDUCE/EXIT，降级 OBSERVE |
| 证据冲突 | 荣昌生物技术面偏弱但价格高于锚价 | 综合标注 "存在冲突" |

---

## 七、结论

**影子运行成功**，P3.5 核心目标达成：

1. ✅ **行情管道修复**：duckdb、排名、实时快照、anchor 价格均更新至 10-20
2. ✅ **数据新鲜度门槛**：STALE/DATE_UNKNOWN 时阻断 CONSIDER_ENTRY/ADD/REDUCE/EXIT，降级 OBSERVE
3. ✅ **Search API Mock 集成**：client/evidence/probe/report 全链路打通，报告渲染外部证据层
4. ✅ **真实调用 BLOCKED 标记**：JEV (model_na/insufficient)、Search (no_search_keys) 均已记录并标记
5. ✅ **回滚可用**：线上脚本有备份，引擎代码可删除/回滚

---

## 八、遗留问题

| ID | 问题 | 等级 | 下一步 |
|---|---|---|---|
| H-01 | 真实 JEV 不可用 | BLOCKED | 用户需在 bynara 充值或指定可用模型 |
| H-02 | 真实 Search 不可用 | BLOCKED | 用户需在 relay 侧配置 Tavily/Exa/Firecrawl/Linkup key |
| H-03 | 实时快照自动化 | M | 需写入 wrapper 或 systemd timer（需用户批准） |
| H-04 | anchor 无 data_date 字段 | L | 后续版本加字段，便于精确新鲜度校验 |
| H-05 | 节假日表缺失 | L | 接入可信节假日源或人工维护表 |

---

## 九、产出文件

```
reports/shadow/
├── 2026-10-20-fresh.md       # fresh data 运行
├── 2026-10-20-gated.md       # stale gate 演示
├── 2026-10-20-gated2.md      # 同 gated（重复）
├── 2026-10-20-search3.md     # search mock（空 claims）
├── 2026-10-20-search4.md     # search mock（完整 claims）
└── 2026-10-20.md             # P3 原始运行
```
