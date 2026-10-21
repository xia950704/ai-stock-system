# P6-2 JEV 恢复计划

> 生成时间：2026-10-20 23:10 (Asia/Shanghai)

## 一、当前阻断状态

| 层级 | 状态 | 证据 |
|------|------|------|
| 工具注册 | OK | `src/jev/server.py` 存在，MCP server 进程运行中（pid 37559/42898/99509/99608） |
| 网络可达性 | 未测试 | 未发起真实请求，避免产生费用 |
| 认证 | 本地 key 存在（`~/.hermes/mcp-servers/jev-systemone/.key`，51 字节） | `ls -l` |
| relay 路由 | 默认 `https://router.bynara.id/v1` | `src/engine/jev_adapter.py` |
| 上游模型可用性 | **BLOCKED** | P5 记录 `model_na / insufficient / forbidden` |
| 积分/权限 | **BLOCKED** | 需 bynara 积分或更换模型 |

**结论**：JEV 真实调用仍为 `BLOCKED`，根因在上游模型/积分，不在本地代码。

## 二、已完成的本地修复

在 `src/engine/jev_adapter.py` 中新增可配置模型适配层：
- `JEV_PROVIDER`：后端标识（默认 `bynara`）
- `JEV_MODEL`：模型 ID（默认 `jev`）
- `JEV_BASE_URL`：基础 URL（默认 `https://router.bynara.id/v1`）
- `JEV_API_KEY`：显式 API Key（优先级最高）
- 新增 `provider_config()` 返回不含密钥的配置摘要

该修改**不改变**默认行为，仅允许用户通过环境变量切换后端。

## 三、需要用户授权的操作

1. **充值 bynara 积分**或获取可用模型 ID。
2. **设置环境变量**（在运行每日研判前）：
   ```bash
   export JEV_API_KEY="你的key"
   export JEV_MODEL="可用模型ID"
   ```
3. **验证**：运行 `python3 -c "import sys; sys.path.insert(0,'src'); from engine import jev_adapter; print(jev_adapter.provider_config())"`，确认 `key_source=env` 且 `model` 为预期值。

## 四、禁止事项

- 不自动充值 bynara 积分。
- 不自动选择或更换模型。
- 不修改全局路由池或 MCP 注册。
- 不在未授权情况下发起真实 JEV 请求。

## 五、回滚

删除 `JEV_PROVIDER`/`JEV_API_KEY` 环境变量即可恢复默认行为；代码改动可通过 `scratch/p6-prechange-hashes.txt` 中的前置哈希校验。

## 六、2026-10-21 恢复结果

### 故障根因

此前 `BLOCKED` 报告成立的前提是每日引擎直连 bynara `/v1/systemone`。当前真实调用链已经变化：

```text
daily_judge.py
  → jev_adapter.jev_yes_no
  → MCP stdio（JEV_TRANSPORT=mcp）
  → ~/.hermes/mcp-servers/jev-systemone/server.py
  → model_adapter
  → AMD Clef
```

`~/.hermes/mcp-servers/jev-systemone/.env` 当前显式设置 `JEV_PROVIDER=amd`、`JEV_MODEL=Clef`。Workspace 适配器只读加载该配置，不修改全局 MCP 注册，也不覆盖 `.env`。

### 真实调用证据

- `provider_config()`：`transport=mcp`、`provider=amd`、`base_url=https://developer.amd.com.cn/radeon/api/v1`、`model=Clef`、`key_source=mcp_env`。
- 2026-10-21 每日引擎 8/8 标的 `jev_yes_no` 真实返回 `ok=true`，模型均为 `Clef`。
- 另以无持仓隐私的医药研究任务完成 `jev_route` 真实调用，返回 choice、概率和 confidence。
- 日志：`~/harness/logs/jev/jev_calls.jsonl`。

### 当前状态

| 项目 | 状态 |
|---|---|
| JEV 可用性 | PASS |
| JEV 核心工具契约 | PASS（Mock 回归） |
| JEV 输出解释 | 仅作单项证据，不参与自动动作 |
| AMD 额度/长期配额 | NOT TESTED，不能据此承诺无限调用 |
| 备选模型选择 | 用户控制，候选表仍空白 |
