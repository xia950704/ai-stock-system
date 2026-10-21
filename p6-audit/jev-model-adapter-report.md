# P6-3 JEV 模型适配层报告

> 生成时间：2026-10-20 23:15 (Asia/Shanghai)

## 一、设计原则

- **保留 JEV 核心逻辑**：`jev_decide` / `jev_yes_no` / `jev_guard_tool_call` / `jev_route` / `jev_front_door` 的输入校验、判定规则、错误分类和输出契约均未修改。
- **仅替换模型适配层**：Provider、Model ID、Base URL、API Key 读取方式通过环境变量配置。
- **不绕过安全校验**：所有请求仍经过 `_call()` 的 key 解析、超时、错误分类和日志记录。

## 二、实现内容

文件：`src/engine/jev_adapter.py`

| 新增项 | 说明 |
|--------|------|
| `PROVIDER` | 环境变量 `JEV_PROVIDER`，默认 `bynara` |
| `provider_config()` | 返回 `{provider, base_url, model, timeout_s, key_source}`，不含密钥 |
| `JEV_API_KEY` | 显式 API Key 环境变量，优先级最高 |

默认行为与修改前完全一致：
```python
BASE_URL = os.environ.get("JEV_BASE_URL", "https://router.bynara.id/v1")
DEFAULT_MODEL = os.environ.get("JEV_MODEL", "jev")
```

## 三、测试覆盖

`p6-audit/tests/test_p6.py` — **15 项全部 PASS**

| 测试 | 内容 |
|------|------|
| T-P6-01~05 | 默认配置正确（provider/model/base_url/timeout/key_source） |
| T-P6-06~09 | 环境变量覆盖配置 |
| T-P6-10~12 | Mock 调用仍可用，请求结构不变 |
| T-P6-13 | 无 key 时返回 `no_key` |
| T-P6-14~15 | 失败不被解释为有效判定 |

## 四、兼容性测试（Mock）

- 正常输入与正常返回：PASS
- 必填字段缺失：由 `jev_decide`/`jev_yes_no` 自动补齐 `instructions`
- 证据不足/冲突：由调用方根据 `error_code` 降级
- 模型超时/不可用/认证失败：`_classify_error` 保持原有分类
- 非预期返回格式：返回 `parse_error`
- 空结果：`is_available` 返回 False

**真实模型兼容性**：`BLOCKED`（未获得可用模型/积分，未发起真实请求）。

## 五、备选模型区域

`p4-audit/decision-model-options.md` 仍为空白，未自动填写任何模型名称。

## 六、回滚

- 删除环境变量 `JEV_PROVIDER` / `JEV_API_KEY` 即可恢复默认。
- 源码回滚：将 `src/engine/jev_adapter.py` 恢复至前置哈希 `3d1c88ee4b15e5fc8227b5a6af4abf1aa77936daea0309a08e0ecf3b0aed1eac`（基线见 `scratch/p6-prechange-hashes.txt`）。

## 七、2026-10-21 最终适配结果

| 项目 | 结果 |
|---|---|
| Provider 选择 | `amd`，来自 MCP Server 本地 `.env` |
| 模型 | `Clef`，大小写敏感，未自动切换 `d3`/`d3-flash` |
| 传输 | MCP stdio 优先，HTTP 仅显式回退 |
| 模型适配 | 通过现有 `model_adapter`，Workspace 未复制 Provider 规则 |
| 核心契约 | 5 个 JEV 工具名称和原有错误分类保持 |
| 真实调用 | 8/8 成功，`model=Clef` |
| 真实工具覆盖 | `jev_yes_no`（8/8）与 `jev_route`（1/1）已用 Clef 成功；其余 3 个工具 NOT TESTED |
| 判定规则 | 未修改核心提示词或业务规则 |

关键纠正：此前把“bynara 模型/积分不足”当作当前状态，是沿用旧链路结论。现有 AMD 路径已经接通，因此 JEV 可用性从 `BLOCKED` 更新为 `PASS`；但长期配额和其余 4 个工具仍需后续验证。

兼容测试：P6 适配层 18/18 通过；P3/P5 契约与失败降级测试共 64/64 通过。所有模型输出仍先经过适配器，不得绕过 `ok/error_code` 分类。
