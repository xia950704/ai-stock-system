# P5-1 JEV 调用链诊断与 relay 故障定位

> 生成时间：2026-10-20 21:5x
> 诊断范围：每日引擎 → JEV 适配器 → 实际端点 → 上游错误

## 一、实际调用链（与 P4 假设不同）

P4 报告把故障定位在「本地 relay `/v1/decisions` 转发」。本阶段实测后发现**每日引擎并不走该路径**：

```
src/engine/daily_judge.py
  → src/engine/jev_adapter.py  (BASE_URL 默认 https://router.bynara.id/v1)
  → POST https://router.bynara.id/v1/systemone
  → 上游 NaraRouter
```

本地 `127.0.0.1:31415/v1/decisions` 是 **FreeLLMAPI 内置的 Decision Model 路径**，与每日引擎的 JEV 适配器是两条独立链路。P4 把两者混为一谈，本阶段已分开记录。

## 二、每日引擎 JEV 适配器实际状态

| 项目 | 实测值 |
|---|---|
| 默认 BASE_URL | `https://router.bynara.id/v1` |
| 端点 | `POST /v1/systemone` |
| 请求字段 | `model`, `state`, `questions` |
| key 来源 | 环境变量 `JEV_API_KEY`/`BYNARA_API_KEY` 或 `~/.hermes/mcp-servers/jev-systemone/.key` |
| 超时 | 60s（`JEV_TIMEOUT`） |
| 错误分类 | timeout / transport / auth / model_na / insufficient / forbidden / not_found / rejected / server_error / parse_error / no_key / no_httpx / unknown |
| 历史调用记录 | `~/harness/logs/jev/jev_calls.jsonl`（全为 mock） |

**结论**：每日引擎的 JEV 从未被真实调用成功；P3 阶段已记录 `model_na / insufficient / forbidden`，本阶段未改变该状态。

## 三、本地 `/v1/decisions`（FreeLLMAPI Decision Model 路径）实测

### 3.1 证据来源

- 已安装应用：`/Applications/FreeLLMAPI.app`，版本 **0.16.5**
- `app.asar` SHA256：`20a129ef44d6b0a3a2b0d6fb6c56325789e80ba36974d8374a764bd52a50f09e`
- 只读 DB：`~/Library/Application Support/FreeLLMAPI/freeapi.db`
- `decision_requests` 表共 **41 条**记录

### 3.2 记录分布

| 模型 | 成功 | 失败 |
|---|---|---|
| `@cf/cloudflare/clef-flash` | 2 | 24 |
| `inception/mercury-decide:free` | 1 | 14 |
| （无 model_id） | 3 | 0 |

**成功时间（Asia/Shanghai）**：
- 2026-10-19 17:25:43 Cloudflare
- 2026-10-19 17:25:44 Cloudflare
- 2026-10-20 18:03:05 OpenRouter

**错误类别**：
- Cloudflare 429 每日免费额度耗尽（10,000 neurons）：14 次
- Cloudflare 400 schema-required：7 次，最新 18:00
- OpenRouter 30s 超时：14 次
- Cloudflare 30s 超时：3 次

### 3.3 接口契约（从 `app.asar` 提取）

```
POST /v1/decisions   (handleDecision)
POST /v1/systemone   (handleDecision，同一路由)
GET  /v1/decisions/models
```

**请求体 schema（zod）**：

```jsonc
{
  "model": "optional string",
  "state": "required, 非空",
  "questions": {
    "<id>": {
      "type": "choice|noul|score",
      "instructions": "required, 非空",
      "criteria": "optional"
    }
  }
}
```

**上游转发行为（实测）**：

| 平台 | 转发 body |
|---|---|
| Cloudflare | `{ model: selector, state, questions }` |
| OpenRouter | `{ model: modelId, state, questions }` |
| apinex / beatapi | `{ model: modelId, state, questions }` |

**结论**：relay **并没有丢弃 `model` 字段**；旧报告「relay drops model」的说法不被支持。`model` 一直被正确转发。

## 四、故障根因分析

### 4.1 已证实

1. **每日引擎 JEV 适配器与本地 `/v1/decisions` 无关**，不存在「relay 转发 bug 影响每日引擎」。
2. **本地 Decision Model 路径的 schema 是合法的**，且 `model/state/questions` 三字段都被转发。
3. **Cloudflare 400 的根因不在 relay 丢字段**，而在于上游 Workers AI 对请求体有额外 schema 要求（`required properties at '/' are 'model,state,questions'`）。这说明 **Cloudflare 侧实际收到的 body 缺少某个必填字段**，而 relay 自身 schema 是宽松的（`model` optional）。
4. **Cloudflare 每日免费额度已耗尽**，是当前最主要的阻断因素。
5. **OpenRouter 冷却/超时**是第二阻断因素。

### 4.2 仍属推测（未证实）

- Cloudflare 400 的确切缺失字段机制：可能是上游 Workers AI 对 `state` 或 `questions` 的嵌套结构有额外要求，而 relay 的 zod schema 允许通过。**精确机制未被证实**。
- 是否存在请求体大小、编码或特定题型（choice 缺 `instructions`）触发的上游校验差异。

### 4.3 修复状态

| 修复项 | 状态 |
|---|---|
| 每日引擎 JEV 适配器补齐 `instructions` 字段（满足本地 `/v1/decisions` schema） | **已在 Workspace 内完成**（`src/engine/jev_adapter.py`） |
| 本地 relay 源码修复 | **BLOCKED** — relay 位于 `/Applications/FreeLLMAPI.app`，外部应用，未获授权修改 |
| Cloudflare 额度充值 | **BLOCKED** — 需用户操作 |
| OpenRouter 积分 | **BLOCKED** — 需用户操作 |

## 五、Workspace 内已做的适配层修复

在 `src/engine/jev_adapter.py` 中：

1. `jev_decide()` 对每个问题自动补齐 `instructions` 字段（score 题从 `criteria[0]` 取，choice 题用通用描述）。
2. `jev_yes_no()` 的 `choice` 模式现在显式包含 `instructions`。
3. `jev_route()` 的 `choice` 模式现在显式包含 `instructions`。

**影响范围**：仅改变请求 payload 结构，不影响 bynara `/v1/systemone` 的既有行为（bynara 侧对额外字段无排斥记录）。若未来 bynara 严格校验，需回滚。

## 六、当前结论

- **每日引擎 JEV**：真实调用仍为 BLOCKED（bynara 侧 model_na / insufficient），与本地 `/v1/decisions` 无关。
- **本地 Decision Model 路径**：间歇性成功（历史 3 次），当前因 Cloudflare 额度耗尽 + OpenRouter 冷却而阻断。
- **Workspace 内修复**：已补齐 `instructions` 字段，使本地 `/v1/decisions` schema 合规；但 **不能保证上游成功**，模型可用性与额度问题仍需用户处理。
- **外部 relay 修复**：BLOCKED，未执行。

## 七、需要用户授权的操作

1. 充值 Cloudflare Workers 额度或更换可用 key。
2. 为 OpenRouter `inception/mercury-decide:free` 添加积分或等待冷却结束。
3. 若需彻底修复 Cloudflare 400，需提供失败请求的精确 payload 与上游 schema 文档。
