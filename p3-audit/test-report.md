# P3 测试报告

> 生成时间：2026-10-20 14:30
> 测试范围：引擎模块（data_loader, trading_day, market_judge, stock_judge, jev_adapter, report）

---

## 一、测试执行汇总

| 测试文件 | 通过 | 失败 | 跳过 |
|---|---|---|---|
| `p3-audit/tests/test_engine.py` | 28 | 0 | 0 |
| `p2-audit/tests/test_paths.py` | 7 | 0 | 0 |
| `p2-audit/tests/test_exceptions.py` | 3 | 0 | 0 |
| `p2-audit/tests/test_data_integrity.py` | 4 | 0 | 0 |
| `p2-audit/tests/test_jev_mock.py` | 5 | 0 | 0 |
| **总计** | **47** | **0** | **0** |

---

## 二、P3 引擎测试详情（28 项）

**测试文件**：`p3-audit/tests/test_engine.py`

### 数据加载（T-D01 ~ T-D04c）：6/6

| ID | 场景 | 结果 |
|---|---|---|
| T-D01 | anchor_status.json 加载成功 | PASS |
| T-D02 | 缺失文件返回 None + 错误 | PASS |
| T-D03 | 无效 JSON 返回错误 | PASS |
| T-D04 | 代码标准化 sh600276 | PASS |
| T-D04b | 代码标准化 sz000963 | PASS |
| T-D04c | 代码标准化纯数字 | PASS |

### 交易日判断（T-T01 ~ T-T02b）：5/5

| ID | 场景 | 结果 |
|---|---|---|
| T-T01 | 周六为非交易日 | PASS |
| T-T01b | 周日为非交易日 | PASS |
| T-T01c | 周三为交易日 | PASS |
| T-T02 | 周六 likely_trading_day=False | PASS |
| T-T02b | 周三 likely_trading_day=True | PASS |

### 大盘研判（T-M01 ~ T-M02）：3/3

| ID | 场景 | 结果 |
|---|---|---|
| T-M01 | 大盘研判返回 verdict | PASS |
| T-M01b | 大盘研判有局限说明 | PASS |
| T-M02 | 无数据时无法判断 | PASS |

### JEV 适配（T-J01 ~ T-J03f）：9/9

| ID | 场景 | 结果 |
|---|---|---|
| T-J01 | Mock JEV 正常返回 | PASS |
| T-J02 | Mock JEV 失败不等于中性 | PASS |
| T-J02b | 失败状态可追溯 | PASS |
| T-J03 | 401 -> auth | PASS |
| T-J03b | 402 -> insufficient | PASS |
| T-J03c | 403 -> forbidden | PASS |
| T-J03d | 404 -> not_found | PASS |
| T-J03e | 400 model_na | PASS |
| T-J03f | 500 -> server_error | PASS |

### 股票分析（T-S01 ~ T-S02）：3/3

| ID | 场景 | 结果 |
|---|---|---|
| T-S01 | 股票分析返回完整结构 | PASS |
| T-S01b | 行动建议有效 | PASS |
| T-S02 | 锚价失效股票行动为 OBSERVE | PASS |

### 报告生成（T-R01 ~ T-R01b）：2/2

| ID | 场景 | 结果 |
|---|---|---|
| T-R01 | 报告生成非空 | PASS |
| T-R01b | 报告包含必要章节 | PASS |

---

## 三、P2 测试复验（19 项）

所有 P2 测试已重新执行，结果与原始报告一致：

- **路径测试**（7/7）：环境变量 `DATA_ROOT`, `STOCK_DAILY_DIR`, `HERMES_WORKSPACE_DIR` 生效
- **错误处理**（3/3）：裸 `except:` 已修复为 `except Exception`
- **数据完整性**（4/4）：JSON/CSV 读取健壮性验证通过
- **JEV Mock**（5/5）：超时/错误处理验证通过

---

## 四、测试限制

| 限制 | 说明 |
|---|---|
| 真实 JEV 调用 | 仅 Mock 验证，真实调用 BLOCKED（model_na / insufficient） |
| 真实网络请求 | 无外部 API 调用测试 |
| 完整业务流程 | 影子运行已验证端到端流程，但未覆盖并发/压力场景 |
| 历史回测 | 使用固定样本，未进行多交易日回测 |

---

## 五、测试证据

- `p3-audit/tests/output/test_engine_output.txt`（28 项通过）
- `p2-audit/tests/output/`（19 项通过）
- `reports/shadow/2026-10-20.md`（影子运行报告）

---

## 六、结论

**测试通过率：100%（47/47）**

所有测试均实际执行，无失败项。JEV 真实调用因账户积分不足被阻塞，但 Mock 验证已通过，降级逻辑正确。
