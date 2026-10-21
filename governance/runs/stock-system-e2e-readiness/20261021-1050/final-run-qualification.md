# 股票投研系统端到端运行资格验收

> 运行时间：2026-10-21（Asia/Shanghai）
> 运行范围：调用链核实、真实 JEV/Search、影子运行、全量回归、历史数据复核

## 一、真实调用链

```text
daily_judge.py
  → stock_judge.py
  → jev_adapter.jev_yes_no
  → MCP stdio bridge
  → ~/.hermes/mcp-servers/jev-systemone/server.py
  → model_adapter.py
  → AMD Radeon API
  → Clef
  → 归一化 JEV 输出
```

每日引擎配置摘要：

```text
transport=mcp
provider=amd
base_url=https://developer.amd.com.cn/radeon/api/v1
model=Clef
key_source=mcp_env
```

旧报告中的“每日引擎仍走 bynara 并被积分阻断”基于旧调用链，不再适用于当前状态。当前 Workspace 复用既有 MCP Server 与 model_adapter，没有另造 JEV 判定逻辑。

## 二、真实运行证据

| 能力 | 结果 | 证据 |
|---|---|---|
| 行情日期 | `2026-10-20`，报告日 `2026-10-21`，FRESH | `reports/shadow/e2e_test_20261021_v3.md` |
| JEV | `jev_yes_no` 8/8、`jev_route` 1/1 成功，model `Clef` | `~/harness/logs/jev/jev_calls.jsonl` |
| Search | `24/24` 成功，每次 5 条 | `~/harness/logs/search/search_calls.jsonl` |
| 影子报告 | 已生成 | `reports/shadow/e2e_test_20261021_v3.md/json` |
| `INSUFFICIENT_EVIDENCE` | `512400` 正确输出 | 同一报告 |

JEV 输出仅作为单项证据；每日引擎仍因订单面缺失而将其视为有限支持，不据此自动产生买卖动作。

## 三、回归测试（实际执行）

```bash
for t in \
  p2-audit/tests/test_paths.py \
  p2-audit/tests/test_exceptions.py \
  p2-audit/tests/test_data_integrity.py \
  p2-audit/tests/test_jev_mock.py \
  p3-audit/tests/test_engine.py \
  p4-audit/tests/test_backtest.py \
  p5-audit/tests/test_p5.py \
  p6-audit/tests/test_p6.py \
  p6-audit/tests/test_radar_inventory.py; do
  python3 "$t"
done
```

结果：**137/137 PASS，0 FAIL，0 SKIP。**

## 四、历史数据状态

- 结构化行情库可覆盖长历史，但仅有价格层。
- 当前排名快照只有一份，锚价日期快照仅一份。
- 新发现 25 份每日雷达报告，可补充部分日期的价格、锚价和信号；覆盖不足以构成完整 8 标的输入。
- `PRICE + ANCHOR + RANKING` 完整输入历史日期仍为 **0 天**。
- 本次没有伪造排名回填，也没有把当前排名倒推到过去。

## 五、安全边界

- 本次 Codex 运行只读取 Obsidian，没有执行 Vault 写入。运行期间观察到 `512400日度跟踪.md` 与 `delta-512400-price.json` 由现有外部任务更新；本次没有触发、修改或新增该任务，也没有擅自清理或回滚外部状态。
- 未修改 GitHub Workflow、每四小时心跳配置、交易接口或全局 MCP 注册。
- 未自动选择 Decision Model；`p4-audit/decision-model-options.md` 保持空白。
- 未充值、未自动调用新模型、未执行交易。
- `.env` 权限已从 `644` 收紧为 `600`，密钥未写入报告。

## 六、最终资格

| 使用方式 | 资格 |
|---|---|
| 人工每日研究 | **CONDITIONAL PASS** |
| 正式无人值守自动化 | **BLOCKED** |
| 自动交易 | **NOT AUTHORIZED / NOT ENABLED** |

## 七、自动化启用前仍需完成

1. 连续归档每日 `anchor_status`、`stock_ranking`、`realtime_prices` 结构化快照，积累完整历史输入。
2. 确定并接入订单/商业化数据源；当前订单面必须保持显式缺口。
3. 建立可靠节假日/交易日日历，避免仅靠工作日推断。
4. 验证 AMD JEV 的长期配额、超时恢复及其他四个工具的真实调用兼容性。
5. 保留人工审核，不把 JEV 单项数值直接映射为交易动作。

**结论：当前系统可进入人工驱动的 shadow/daily research 使用，不应开启正式每日自动任务。**
---

## Final addendum ( **>>** 11:35)

- Eight scenarios were executed or represented by direct scenario artifacts.
- Final regression is now `137/137`, including radar coverage tests.
- Fixed report-date stale propagation and malformed JEV ok-response classification.
- AMD key rotation confirmation was not completed before this session’s real calls. Rotate the key before automated or prolonged use.
- Final qualification: infrastructure PASS, human research CONDITIONAL PASS, formal automation BLOCKED.
