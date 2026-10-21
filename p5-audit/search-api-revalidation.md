# P5-2 Search API 复核：真实可用性与证据质量

> 生成时间：2026-10-20 21:5x

## 一、配置与调用路径

| 项目 | 实测值 |
|---|---|
| Base URL | `http://127.0.0.1:31415/v1/search`（`SEARCH_API_BASE_URL`） |
| 认证 | Bearer Token（`SEARCH_API_KEY`） |
| 客户端 | `src/search/client.py` |
| 证据层 | `src/search/evidence.py` |
| 探查层 | `src/search/probe.py` |
| 配置文件 | `.env`（真实值，未提交） |
| 模板 | `docs/config/search-api.env.template` |

## 二、真实请求证据（本次执行）

通过 `src/search/client.py` 发出 3 次真实查询，全部成功：

| # | 查询 | 结果数 | 耗时 |
|---|---|---|---|
| 1 | 百利天恒 BL-B01D1 临床试验 最新进展 公告 | 5 | 3.565s |
| 2 | 百利天恒 BL-B01D1 上交所 公告 | 5 | 3.878s |
| 3 | 百利天恒 BL-B01D1 临床试验 官方公告 | 5 | 3.98s |

**状态**：Search API 真实调用 **PASS**。

## 三、返回字段实测

| 字段 | 是否存在 | 说明 |
|---|---|---|
| `title` | ✅ | 标题 |
| `url` | ✅ | 来源 URL |
| `content` | ✅ | 正文摘要（**真实返回使用此字段**） |
| `score` | ✅ | 相关性分数 |
| `snippet` | ❌ | **API 不返回此字段** |
| `published_at` | ❌ | **API 不返回此字段** |

## 四、证据层兼容性问题与修复

### 4.1 问题

`src/search/evidence.py` 原先只读取 `snippet`，导致真实返回的 `content` 被丢弃，所有 claim 的 `snippet` 为空字符串。

### 4.2 修复（Workspace 内）

```python
snippet = result.get("snippet") or result.get("content") or ""
```

同时：
- `published_at` 保持 `None`，**不从正文推断日期**。
- `accessed_at` 正确填充。
- URL 归一化改进：使用 `urlsplit` + `unquote`，正确折叠百分号编码路径（如 `%2F`）。
- 新增官方发行人域名 `baili-pharm.com` 的 tier 1 规则。

### 4.3 修复后的验证

| 检查项 | 结果 |
|---|---|
| `content` 被保留 | PASS |
| 无发布日期时保持 `None` | PASS |
| 编码/未编码 URL 去重 | PASS |
| 官方发行人域名 tier=1 | PASS |
| 两个独立官方来源 → multi_source_confirmed | PASS |
| 同一域名不同 URL 只算 1 个独立来源 | PASS |

## 五、来源独立性现状

| 来源域名 | tier |
|---|---|
| `baili-pharm.com` | 1（官方发行人） |
| `sse.com.cn` / `cninfo.com.cn` | 1（交易所/公告） |
| `cls.cn` / `eastmoney.com` / `sina.com.cn` | 3（财经媒体） |
| 其他未知域名 | 4（默认） |

**当前局限**：真实查询结果中，除 `baili-pharm.com` 外，多数结果来自 tier 4/5 域名，因此独立来源数可能为 0，claim 状态保持 `unverified`。这是**如实的证据状态**，不是系统缺陷。

## 六、结论

- Search API 真实调用：**PASS**
- 证据层字段兼容：**已修复**（Workspace 内）
- 来源追溯质量：**受限**（多数结果非 tier 1-3，独立来源不足）
- 发布日期：**保持 unknown**，不推断

**未宣称**：多源交叉验证已充分。当前结论仍需人工核验原始公告。
