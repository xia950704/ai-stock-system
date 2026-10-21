# P2 配置与安全检查报告（config-security-report）

> 生成时间：2026-10-20
> 范围：`docs/config/` 模板、`.gitignore`、凭证风险、外部调用权限

---

## 一、配置模板审核

### 1.1 `docs/config/codex-config.toml.template`

| 配置项 | 用途 | 必需/可选 | 注入方式 | 缺失时行为 |
|---|---|---|---|---|
| `base_url` | 本机 relay 地址 | 必需 | 环境变量/本机配置 | Codex 无法连接模型，启动报错 |
| `experimental_bearer_token` | relay 认证 | 必需 | 环境变量/本机配置（禁止入库） | 401 认证失败 |
| `mcp_servers.jev-systemone` | JEV MCP 注册 | 可选（仅 JEV 功能） | 本机配置 | JEV 工具不可用，其他功能不受影响 |
| `model` / `model_reasoning_effort` | 模型选择 | 可选 | 模板默认值 | 使用 relay 默认路由 |

### 1.2 `docs/config/hermes-config.yaml.template`

| 配置项 | 用途 | 必需/可选 | 注入方式 | 缺失时行为 |
|---|---|---|---|---|
| `secrets.sensenova.api_key` | 通义千问 API | 可选（按 provider） | 环境变量 | 对应 provider 不可用 |
| `secrets.gemini.api_key` | Gemini API | 可选 | 环境变量 | 对应 provider 不可用 |
| `secrets.openrouter.api_key` | OpenRouter | 可选 | 环境变量 | 对应 provider 不可用 |
| `secrets.jev.api_key` | JEV/bynara | 仅 JEV 功能 | 环境变量或 `.key` 文件 | JEV 调用失败（server.py 有清晰 RuntimeError） |

**模板与代码一致性检查**：
- JEV server.py 读取顺序：`JEV_API_KEY` env > `BYNARA_API_KEY` env > `~/.hermes/mcp-servers/jev-systemone/.key` —— 与模板说明一致。
- JEV server.py 还读取 `JEV_BASE_URL`（默认 `https://router.bynara.id/v1`）、`JEV_TIMEOUT`（默认 60s）、`JEV_MODEL`（默认 `jev`）—— 模板未列全，**已补入本说明**（待 P3 同步回模板文件）。
- `STOCK_DAILY_DIR` / `DATA_ROOT` / `HERMES_WORKSPACE_DIR`：P2 修复引入的新环境变量，模板尚未更新 —— 登记为待办。

**"待运行时验证"标记**：
- JEV bynara 网络可达性：未验证（P2 禁止真实调用）。
- relay `127.0.0.1:57321` 服务状态：未验证（避免干扰本机服务）。
- GitHub Actions Secrets 有效期：未验证（P2 禁止触碰线上）。

## 二、`.gitignore` 实际验证

### 2.1 规则覆盖检查

| 规则 | 验证方式 | 结果 |
|---|---|---|
| `**/.key` / `**/*.key` | `git check-ignore` 模拟 | ✅ 覆盖 JEV `.key` |
| `**/.env` | 同上 | ✅ 覆盖 `.env*` |
| `**/config.toml` / `**/config.yaml` | 同上 | ✅ 覆盖真实配置 |
| `src/trading/auto_trade_state.json` | 同上 | ✅ 覆盖持仓状态 |
| `docs/config/*.toml`（排除 `.template`） | 同上 | ✅ 模板可提交、真配置不可 |

### 2.2 敏感文件排查

对 Workspace 内复制的文件做了文件名级扫描（`*key*`、`*secret*`、`*token*`、`*.env`、`auth.json`）：
- **发现 0 个**真实凭证文件被复制进 Workspace。
- `src/jev/` 下仅含 server.py、selftest、README —— `.key` 与 `.venv` 均在 P1 明确排除。
- `src/trading/auto_trade_state.json`（含模拟持仓）已被 `.gitignore` 排除。

## 三、凭证风险检查

| 项 | 结果 |
|---|---|
| Workspace 内硬编码明文密钥 | 0 处（扫描 `sk-`、`ghp_`、`freellmapi-` 等特征） |
| 测试日志输出敏感信息 | 0 处（测试不触碰真实配置） |
| 配置模板含真实值 | 0 处（全部 `<PLACEHOLDER_*>`） |

## 四、权限与外部调用风险

| 项 | 评估 |
|---|---|
| JEV server 网络调用 | 仅 POST `router.bynara.id/v1/systemone`，超时 60s，无写盘 |
| 行情脚本网络调用 | 仅 GET 腾讯 `qt.gtimg.cn`，超时 10s，只读 |
| 子进程调用 | 全部 `shell=False` 参数列表形式；osascript 仅用于 iMessage 通知（本机） |
| 文件系统写入 | `update_anchor.py` 写 `~/harness/`（其设计用途），其余脚本写各自 workspace；P2 未新增任何写入点 |
| 文件权限 | 复制保留原权限；无新增可执行脚本 |

## 五、尚待用户处理的安全事项

1. **`~/.hermes/config.yaml` 中的明文 API Key**（P0 已知 R-S01）：P2 未触碰（禁止修改全局配置），建议用户在 Hermes 侧改用环境变量注入。
2. **`/Volumes/夏爽/.github-token`**：移动硬盘根目录存在 GitHub token 文件（P0 已登记）。P2 未读取其内容，仅记录位置与风险。建议用户检查该 token 的有效期与权限范围，必要时轮换。
3. **`src/trading/` 内含模拟交易状态**（`auto_trade_state.json`）：已 gitignore；若未来初始化 Git，需再次确认。
4. **DuckDB 文件 `~/.hermes/deeppulse/db/astock.duckdb`**：被 legacy 脚本引用，含历史行情数据；未纳入 Workspace（体积与耦合原因），登记待确认。

