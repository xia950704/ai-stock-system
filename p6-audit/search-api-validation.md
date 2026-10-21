# P6-1 Search API 配置与真实验证

> 生成时间：2026-10-20 23:05 (Asia/Shanghai)
> 来源台账：`scratch/p6/citation-ledger.json`

## 一、配置位置（用户需要填写的字段）

**实际配置文件绝对路径**：`/Users/xiashuang/AI-股票系统/.env`

| 字段 | 当前值 | 说明 |
|------|--------|------|
| `SEARCH_API_BASE_URL` | `http://127.0.0.1:31415/v1/search` | 已填 |
| `SEARCH_API_KEY` | `<set>`（长度 59，未在报告中打印） | 已填 |

**代码读取方式**（P6 补强）：
- `src/search/client.py` 在导入时调用 `_load_dotenv()`，从 Workspace 根目录 `.env` 加载配置（仅当环境变量未设置时）。
1. 优先读取环境变量 `SEARCH_API_CONFIG_FILE` 指向的文件；
2. 其次读取 `src/search/../.env`（即 Workspace 根目录的 `.env`）。
- 然后 `BASE_URL = os.environ.get("SEARCH_API_BASE_URL", ...)`、`API_KEY = os.environ.get("SEARCH_API_KEY", "")`。
- 环境变量优先级高于 `.env`：若已导出 `SEARCH_API_BASE_URL`，则 `.env` 中的同名变量不会覆盖。

**验证配置已加载的方法**（不打印密钥）：
```bash
python3 -c "import sys; sys.path.insert(0,'src'); from search import client; print(client.BASE_URL, bool(client.API_KEY))"
```
输出 `http://127.0.0.1:31415/v1/search True` 即表示配置已加载。

`.gitignore` 已包含 `**/.env`，真实配置不会进入 Git。

**P6 新增测试**：`p6-audit/tests/test_p6.py` 中 T-P6-16/17/18 分别验证 `.env` 加载、环境变量优先、无 key 时返回 `no_key`。

## 二、真实调用证据

通过 `src/search/client.py` 发出 2 次只读查询，均成功：

| # | 查询 | 结果数 | 状态 |
|---|------|--------|------|
| 1 | `恒瑞医药 sh600276 创新药 最新进展 公告` | 5 | ok=True |
| 2 | `百利天恒 sh688506 BL-B01D1 临床试验 最新进展` | 5 | ok=True |

## 三、返回字段与证据处理

| 字段 | 存在 | 说明 |
|------|------|------|
| `title` | ✅ | 来源标题 |
| `url` | ✅ | 来源 URL |
| `content` | ✅ | 正文摘要（真实返回使用此字段） |
| `score` | ✅ | 相关性分数 |
| `published_at` | ❌ | API 不返回，代码保持 `None`，不从正文推断 |

证据层 `src/search/evidence.py` 已将 `content` 作为 `snippet` 回退，因此真实结果可被正确登记。

## 四、多源交叉验证（以百利天恒 BL-B01D1 为例）

**查询**：`百利天恒 sh688506 BL-B01D1 临床试验 最新进展`

| 来源 | 域名 | tier | 独立？ |
|------|------|------|--------|
| 官方发行人公告 | `baili-pharm.com` | 1 | 是 [7][8][9] |
| 新浪财经公司公告 | `sina.com.cn` | 3 | 是 [6] |
| 行业知识平台 | `zhihuiya.com` | 4 | 否（tier>3）[5] |

**交叉验证结果**：
- 官方发行人与新浪财经为两个独立来源，但内容层级不同（官方公告 vs 媒体转载），**不构成 fully multi_source_confirmed**。
- 状态标记为 `SINGLE_SOURCE`（以官方公告为准）+ 媒体补充。
- 发布时间：API 未返回，标记为 `unknown`，不推断。

## 五、局限

- 真实结果中多数来源为 tier 3-4（财经媒体、行业平台），独立来源数量有限。
- 未发现来源冲突，但也未达到多源交叉验证标准。
- 搜索摘要不等于已核实事实；需人工核验原始公告。

## 六、结论

- Search API 真实调用：**PASS**
- 配置安全：**PASS**（`.env` + `.gitignore` 保护）
- 多源交叉验证：**受限**（独立来源不足）

## 七、2026-10-21 复核结果

### 配置

| 项 | 当前值 |
|---|---|
| 配置文件 | `/Users/xiashuang/AI-股票系统/.env` |
| `SEARCH_API_BASE_URL` | `http://127.0.0.1:31415/v1/search` |
| Key 状态 | 已设置；未在任何报告中打印 |
| 文件权限 | 本次从 `644` 收紧为 `600` |
| Git 保护 | `.gitignore` 含 `**/.env` |

### 真实调用

- 2026-10-21 每日引擎执行 24 次只读查询，全部返回 5 条结果，状态 `ok=true`。
- 日志：`~/harness/logs/search/search_calls.jsonl`。
- 单票证据层记录来源层级、标题、URL、检索时间；`published_at` 仍不由客户端推断。

### 事实级多源核验

核验命题：**恒瑞医药 2026 年半年度报告已于 2026-08-19 发布，媒体口径为营业收入 `154.56` 亿元、归母净利润 `44.65` 亿元。**

| 来源 | 类型 | 独立性 | 结果 |
|---|---|---|---|
| 巨潮资讯官方 PDF | 一级披露 | 一手 | 确认半年度报告文件存在 |
| 财联社经新浪转载 | 媒体转述 | 二手 | 确认数字 |
| 新京报经新浪转载 | 媒体转述 | 另一采编主体，但共享同一公告 | 确认数字 |

结论：`CONFIRMED_PRIMARY_SOURCE_AVAILABLE`；媒体数字一致但仍共享同一原始公告，不标记为完全独立多源。来源台账：`scratch/p6/citation-ledger.json`。

总体：Search API 日常研究状态 **PASS**；事实自动确认上限受来源独立性限制。
