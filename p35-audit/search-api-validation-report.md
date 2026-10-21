# P3.5 Search API 验证报告

> 生成时间：2026-10-20 17:00

---

## 一、接口发现

### 1.1 Base URL 与认证
- **Base URL**: `http://127.0.0.1:31415/v1/search`（本地 llm-relay 搜索代理）
- **认证方式**: Bearer Token（`SEARCH_API_KEY` 环境变量）
- **HTTP 方法**: POST
- **Content-Type**: application/json

### 1.2 请求/响应结构
**请求**:
```json
{
  "query": "恒瑞医药 最新公告",
  "limit": 5,
  "provider": "parallel"  // 可选，指定搜索提供者
}
```

**成功响应**:
```json
{
  "results": [
    {"title": "...", "url": "...", "snippet": "...", "published_at": "..."}
  ]
}
```

**错误响应**:
```json
{
  "error": {
    "message": "search error: No search key configured...",
    "type": "server_error",
    "code": "no_search_keys"
  }
}
```

---

## 二、验证层级

| 层级 | 描述 | 状态 | 证据 |
|---|---|---|---|
| L1 | 端点可达 | PASS | POST /v1/search 返回 HTTP 200/400/500（非连接拒绝） |
| L2 | 认证通过 | PASS | 正确 Bearer Token 被接受（无 401） |
| L3 | 业务逻辑可用 | BLOCKED | 返回 `no_search_keys`：需配置 Tavily/Exa/Firecrawl/Linkup 等外部搜索提供者 key |

---

## 三、真实调用测试

| 测试 | 参数 | 结果 | 说明 |
|---|---|---|---|
| 1 | `query="恒瑞医药 最新公告", limit=3, provider=parallel` | **BLOCKED** | `error_code=no_search_keys`：需在 relay 侧配置外部搜索提供者 key |
| 2 | 无 provider | **BLOCKED** | 同上 |
| 3 | `use_mock=True` | PASS | Mock 层正常工作，返回 3 条测试记录 |

---

## 四、结论

**Search API 真实调用：BLOCKED**

- 本地 relay 端点可达，认证通过
- **阻塞原因**：relay 侧未配置外部搜索提供者 key（Tavily/Exa/Firecrawl/Linkup）
- relay 返回 `no_search_keys`，建议在 Keys 页面启用 "Parallel" 或添加提供者 key
- Mock 模式已完整实现，可用于引擎集成测试

---

## 五、集成状态

| 组件 | 状态 | 说明 |
|---|---|---|
| `src/search/client.py` | 完成 | 真实 POST、超时、重试、错误分类、日志脱敏 |
| `src/search/evidence.py` | 完成 | 来源分级（1-5 级）、转载去重、claim 状态机 |
| `src/search/probe.py` | 完成 | 面向研发/订单/事件 3 个面的查询模板、Mock 支持 |
| 引擎集成 (`daily_judge.py --mock-search`) | 完成 | 新增 `--mock-search` 标志，报告中渲染 `search_layer` |
| 报告渲染 | 完成 | 新增 "外部证据（Search API）" 节，显示 claim 状态、来源分级、独立来源计数 |

---

## 六、残留问题

| ID | 问题 | 等级 | 说明 |
|---|---|---|---|
| SA-01 | 真实搜索不可用 | BLOCKED | 需用户在 relay 侧配置 Tavily/Exa/Firecrawl/Linkup key 或启用 Parallel 模式 |
| SA-02 | 无真实响应样本 | L | 无法验证真实返回的字段完整性（published_at 等） |
| SA-03 | provider 参数未验证 | L | 未测试 `provider=tavily/exa/firecrawl/linkup` 的差异 |

---

## 七、回滚步骤

```bash
rm -rf /Users/xiashuang/AI-股票系统/src/search
# daily_judge.py 中 --mock-search 相关代码可保留或手动删除
```
