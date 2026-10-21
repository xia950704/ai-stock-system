# P4-4 Search API 与 JEV 的历史使用边界与当前可用性

> 生成时间：2026-10-20 18:57

---

## 一、Search API 当前状态

### 1.1 探测结果

**探测时间**：2026-10-20 18:xx  
**端点**：`http://127.0.0.1:31415/v1/search`  
**认证**：Bearer token (SEARCH_API_KEY)

### 1.2 可用 Provider

| Provider | 状态 | 延迟 | 备注 |
|----------|------|------|------|
| default (relay自动路由) | 可用 | ~1.5s | 返回 5 条结果 |
| tavily | 可用 | ~2.0s | 返回 5 条结果 |
| exa | 可用 | ~2.5s | 返回 5 条结果 |
| firecrawl | 未测试 | - | - |
| linkup | 未测试 | - | - |

### 1.3 真实调用验证

```python
# 探测代码
from search.client import search
r = search("百利天恒 BL-B01D1 临床试验 进展", limit=3, use_mock=False)
# 结果: ok=True, results=5, provider=None (默认)
```

**状态**：**真实调用可用** (P3.5 阻碍 H-02 已解除)

### 1.4 配置位置

| 配置项 | 位置 | 当前值 |
|--------|------|--------|
| SEARCH_API_BASE_URL | `/Users/xiashuang/AI-股票系统/.env` | `http://127.0.0.1:31415/v1/search` |
| SEARCH_API_KEY | `/Users/xiashuang/AI-股票系统/.env` | 已配置 (长度 59) |
| SEARCH_API_TIMEOUT | 环境变量/默认 | 30s |
| SEARCH_API_MAX_RETRIES | 环境变量/默认 | 2 |

**模板**：`docs/config/search-api.env.template`

### 1.5 历史边界

| 项目 | 状态 | 说明 |
|------|------|------|
| 历史检索记录 | 无 | 本地未保存任何 search_results |
| 回放可用性 | 不可用 | 无历史记录，回放标记 historical_unavailable |
| 当前可用性 | 可用 | 真实调用返回结果 |

---

## 二、JEV 当前状态

### 2.1 探测结果

**探测时间**：2026-10-20 18:xx  
**端点**：`http://127.0.0.1:31415/v1/decisions`  
**认证**：Bearer token (SEARCH_API_KEY)

### 2.2 可用 Decision Model

| Model ID | Provider | 状态 | 说明 |
|----------|----------|------|------|
| `@cf/cloudflare/clef-flash` | Cloudflare | 可用 | 但 400: model 字段未正确转发 |
| `inception/mercury-decide:free` | OpenRouter | 冷却中 | 429 decision_keys_cooling_down |

### 2.3 真实调用验证

```python
# /v1/decisions 契约
{
  "model": "@cf/cloudflare/clef-flash",
  "state": {...},
  "questions": {"action": {"type": "choice", "instructions": "..."}}
}
# 结果: 400 "required properties at '/' are 'model,state,questions'"
# 原因: relay 未正确转发 model 字段到上游
```

**状态**：**真实调用不可用** (relay 转发 bug + mercury 冷却)

### 2.4 配置位置

| 配置项 | 位置 | 当前值 |
|--------|------|--------|
| JEV Base URL | `~/.hermes/mcp-servers/jev-systemone/server.py` | `https://router.bynara.id/v1/systemone` |
| JEV API Key | `~/.hermes/mcp-servers/jev-systemone/.key` | 已配置 |
| Decision 端点 | `http://127.0.0.1:31415/v1/decisions` | 本地 relay |

### 2.5 历史边界

| 项目 | 状态 | 说明 |
|------|------|------|
| 历史调用记录 | 有 | `~/harness/logs/jev/jev_calls.jsonl` (128 条) |
| 记录时间范围 | 2026-10-20 | 仅当日 |
| 记录模式 | 全为 mock | model="mock" |
| 真实调用记录 | 无 | 无真实 JEV 调用成功记录 |
| 回放可用性 | 不可用 | 无真实历史记录，回放标记 historical_unavailable |

---

## 三、回放中的使用规则

| 场景 | Search | JEV |
|------|--------|-----|
| 历史回放 | 标记 historical_unavailable，不伪造结果 | 标记 historical_unavailable，不伪造结果 |
| 当前影子运行 | 真实调用可用 (--search) | Mock 模式 (--mock-jev) |
| 实时生产 | 真实调用可用 | 待修复 relay + 积分 |

---

## 四、结论

**Search API**：真实调用可用，历史无记录，回放标记 unavailable。  
**JEV**：真实决策端点不可用 (relay bug + 积分不足)，历史无真实记录，回放标记 unavailable。

**P3.5 阻碍状态**：
- H-01 (JEV 真实调用)：**仍 BLOCKED** - 需修复 relay 转发 + bynara 积分
- H-02 (Search 真实调用)：**已解除** - 真实调用返回结果
