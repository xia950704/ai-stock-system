# P3-1 JEV 可达性验证报告

> 生成时间：2026-10-20
> 验证范围：JEV MCP 工具注册、静态实现、Mock 契约、真实调用

---

## 一、验证层级

P3-1 要求区分以下层级，逐层验证：

| 层级 | 描述 | 状态 | 证据 |
|---|---|---|---|
| L1 | MCP 工具已在当前环境注册 | PASS | tool_search 发现 5 个工具：jev_decide, jev_yes_no, jev_guard_tool_call, jev_route, jev_front_door |
| L2 | MCP 进程可以启动 | PASS | ~/.codex/config.toml 注册了 jev-systemone MCP server，enabled=true |
| L3 | 网络请求成功 | PASS | HTTP POST 到 router.bynara.id/v1/systemone，收到 HTTP 响应 |
| L4 | 认证通过 | PASS | 未返回 401；请求到达模型路由层（400/402/403/404 均为业务错误，非认证错误） |
| L5 | 工具实际返回符合预期 | BLOCKED | 见下文 |

---

## 二、真实调用测试记录

### 2.1 测试方法

使用 mcp__jev_systemone__jev_yes_no 和 mcp__jev_systemone__jev_decide 工具，输入最小化、非敏感 state（仅含测试数字，无持仓/成本/股票数据）。

### 2.2 测试结果

| # | 模型 | 工具 | HTTP 状态 | 错误码 | 结论 |
|---|---|---|---|---|---|
| 1 | jev（默认） | jev_yes_no (noul) | 400 | model_na | 模型不可用 |
| 2 | jev（默认） | jev_decide (choice) | 400 | model_na | 模型不可用 |
| 3 | deepseek-v4-flash | jev_yes_no (noul) | 402 | insufficient | 积分不足 |
| 4 | jev-1.14.0 | jev_yes_no (noul) | 402 | insufficient | 积分不足 |
| 5 | minimax-m3.1-flash:free | jev_yes_no (noul) | 403 | forbidden | 套餐不包含 |
| 6 | gpt-4o-mini | jev_decide (choice) | 404 | not_found | 模型不存在 |
| 7 | agnes-2.5-flash | jev_yes_no (noul) | 400 | rejected | 模型拒绝请求格式 |

### 2.3 bynara 路由器模型列表

通过 /v1/models 端点（已认证）获取，共 46 个模型：

- 包含 jev-1.14.0（但账户积分不足，返回 402）
- 不包含 jev（默认模型名，返回 400 model_na）
- 包含免费模型 minimax-m3.1-flash:free 和 nemotron-3.5-lightning-free（但套餐不包含，返回 403）
- 包含 agnes/claude/glm/gpt/kimi 等通用模型（但 /v1/systemone 端点格式为 JEV 专用，通用模型返回 400 rejected）

---

## 三、结论

### 3.1 JEV 当前状态：不可用（BLOCKED）

JEV MCP 服务在技术上可达（网络、认证均通过），但账户层面存在两个阻塞问题：

1. 默认模型 jev 已不在 bynara 路由器上（400 model_na）
2. 账户积分不足，无法调用 jev-1.14.0 等付费模型（402 insufficient）
3. 套餐不包含免费模型（403 forbidden）

### 3.2 对每日研判的影响

- 每日研判引擎已设计为 JEV 不可用时的降级模式
- JEV 调用失败不等于中性、看多或看空
- 报告中明确标记「JEV 调用失败（model_na），不参与判断」
- 证据综合中将 JEV 失败记录为数据缺口，不影响其他证据的判断

### 3.3 恢复条件

JEV 恢复可用需要以下条件之一：
1. 用户在 bynara 路由器上充值积分（解决 402 insufficient）
2. 用户确认可用的替代模型名并更新 JEV_MODEL 环境变量（解决 400 model_na）
3. 用户确认套餐包含免费模型（解决 403 forbidden）

以上均需用户操作，P3 无法自动解决。

---

## 四、Mock 验证

Mock 测试覆盖了以下场景（详见 p3-audit/tests/test_engine.py）：

| 测试 | 场景 | 状态 |
|---|---|---|
| T-J01 | Mock 正常返回 | PASS |
| T-J02 | Mock 失败不等于中性 | PASS |
| T-J02b | 失败状态可追溯 | PASS |
| T-J03 | 401 -> auth | PASS |
| T-J03b | 402 -> insufficient | PASS |
| T-J03c | 403 -> forbidden | PASS |
| T-J03d | 404 -> not_found | PASS |
| T-J03e | 400 model_na | PASS |
| T-J03f | 500 -> server_error | PASS |

注意：Mock 测试通过不代表真实 JEV 可用。真实 JEV 状态为 BLOCKED。

---

## 五、安全声明

- 所有真实调用均使用最小化、非敏感 state（仅含测试数字）
- 未输入任何持仓、成本价、账户数据
- 未修改 JEV 核心判定规则或路由池
- 未调用真实交易接口
- 未修改全局 MCP 配置
- 调用日志记录在 ~/harness/logs/jev/jev_calls.jsonl（不含密钥）
