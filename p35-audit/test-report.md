# P3.5 测试报告

> 生成时间：2026-10-20 17:15

---

## 一、测试执行汇总

| 测试套件 | 通过 | 失败 | 跳过 | 说明 |
|---|---|---|---|---|
| `trading_day.py` (freshness gate) | 5 | 0 | 0 | FRESH/STALE/DATE_UNKNOWN/边界/动作降级 |
| `search/client.py` | 4 | 0 | 0 | Mock OK / no_key / 真实调用 BLOCKED 记录 |
| `search/evidence.py` | 5 | 0 | 0 | 来源分级/去重/claim 状态/多源确认/报告摘要 |
| `search/probe.py` | 4 | 0 | 0 | 3 面查询/Mock 分发/DEFAULT_MOCK/池级聚合 |
| 引擎集成 (`daily_judge --mock-jev --mock-search`) | 1 | 0 | 0 | 端到端：数据读取 -> 交易日 -> 大盘 -> JEV -> 搜索 -> 股票 -> 报告 |
| 影子运行 (fresh data) | 1 | 0 | 0 | `reports/shadow/2026-10-20-fresh.md` 数据日期 2026-10-20 |
| 影子运行 (stale gate 模拟) | 1 | 0 | 0 | 09-30 数据 -> CONSIDER_ENTRY 降级为 OBSERVE |

**总计：21 通过，0 失败，0 跳过**

---

## 二、关键测试详情

### 2.1 数据新鲜度门槛 (`trading_day.py`)

| 测试 | 场景 | 预期 | 实际 |
|---|---|---|---|
| T-FRESH | asof=report_date | FRESH, blocking=False | PASS |
| T-STALE-14 | asof=09-30, report=10-20 | STALE, lag=14, blocking=True | PASS |
| T-STALE-1 | asof=10-19, report=10-20 | FRESH, blocking=False | PASS |
| T-UNKNOWN | asof=None | DATE_UNKNOWN, blocking=True | PASS |
| T-ACTION-DOWNGRADE | CONSIDER_ENTRY + STALE gate | OBSERVE + staleness_blocked=True | PASS |

### 2.2 Search API 客户端

| 测试 | 场景 | 预期 | 实际 |
|---|---|---|---|
| T-MOCK | use_mock=True + mock_results | ok=True, 3 results | PASS |
| T-NO-KEY | SEARCH_API_KEY="" | error_code=no_key | PASS |
| T-REAL-BLOCKED | 真实 relay 无搜索 key | error_code=no_search_keys | PASS (记录并标记 BLOCKED) |

### 2.3 证据层

| 测试 | 场景 | 预期 | 实际 |
|---|---|---|---|
| T-TIER-1 | 交易所域名 | tier=1 | PASS |
| T-TIER-3 | 财经媒体域名 | tier=3 | PASS |
| T-DEDUP | 同 URL 不同 query 参数 | duplicate_count=2 | PASS |
| T-MULTI-SOURCE | 2 个独立域名 tier<=3 | multi_source_confirmed | PASS |
| T-REPORT | sanitize_for_report 字段完整 | claim_id/status/tier/top_sources | PASS |

### 2.4 Search Probe

| 测试 | 场景 | 预期 | 实际 |
|---|---|---|---|
| T-3-FACETS | rd/order/event 各 1 查询 | queries_executed=3 | PASS |
| T-MOCK-DIST | 每查询不同 mock 结果 | 3 不同 claim | PASS |
| T-DEFAULT-MOCK | use_mock=True 无参 mock_results | 使用 DEFAULT_MOCK_RESULTS | PASS |
| T-POOL | 8 只股票并行 | 8/8 available=true | PASS |

---

## 三、影子运行验证

| 运行 | 参数 | 关键指标 | 结果 |
|---|---|---|---|
| Fresh | `--mock-jev` | 数据日期 2026-10-20, CONSIDER_ENTRY 有效 | PASS |
| Stale Gate | 手动构造 asof=09-30 | CONSIDER_ENTRY -> OBSERVE | PASS |
| Search Mock | `--mock-jev --mock-search` | search_layer 渲染, claim 状态显示 | PASS |

---

## 四、测试限制

| 限制 | 说明 |
|---|---|
| 真实 JEV 调用 | 仅 Mock 验证，真实调用 BLOCKED (model_na / insufficient) |
| 真实 Search 调用 | relay 无搜索 key，仅 Mock 验证 |
| 真实网络请求 | 无外部 API 调用测试 |
| 历史回测 | 使用固定样本，未进行多交易日回测 |
| 并发/压力 | 未覆盖并发场景 |

---

## 五、测试证据

- `p35-audit/tests/` 目录（新建）
- `reports/shadow/2026-10-20-fresh.md` (fresh data)
- `reports/shadow/2026-10-20-gated.md` (stale gate demo)
- `reports/shadow/2026-10-20-search4.md` (search mock evidence)

---

## 六、结论

**所有测试通过 (21/21)**。P3.5 核心功能：
1. 行情管道已修复（duckdb、排名、实时快照、anchor 价格均为 10-20）
2. 数据新鲜度门槛生效（STALE/DATE_UNKNOWN 阻断交易类建议）
3. Search API Mock 集成完整（client/evidence/probe/report 渲染）
4. 真实 JEV/Search 均 BLOCKED，已记录并标记，Mock 路径完整可测
