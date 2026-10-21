# P2 代码审计报告

> 生成时间：2026-10-20  
> 审核范围：`src/` 下 7 个模块（1183 个文件）  
> 审核方法：静态扫描 + 关键文件精读 + 依赖检查

---

## 一、审核范围与概况

### 1.1 文件统计

| 模块 | 文件数 | 代码行数（估算） |
|---|---|---|
| `src/data/` | 11 | ~500 |
| `src/obsidian/` | 1012 | ~50,000（含大量 Markdown/CSV 数据） |
| `src/scripts/` | 37 | ~3,000 |
| `src/jev/` | 10 | ~800 |
| `src/skills/` | 5 | ~5,000（SKILL.md 为主） |
| `src/trading/` | 96 | ~8,000 |
| `src/workflows/` | 3 | ~200 |
| **总计** | **1174** | **~67,500** |

### 1.2 审核重点

- 硬编码路径（绝对路径、旧工作目录、移动硬盘依赖）
- 不安全代码模式（`shell=True`、裸 `except`、缺少 `timeout`）
- 配置与密钥管理
- JEV 调用契约
- 数据完整性与错误处理

---

## 二、硬编码路径审计

### 2.1 发现的路径引用

| 文件 | 行号 | 旧路径 | 类型 | 风险等级 |
|---|---|---|---|---|
| `src/scripts/legacy/stock_signal_extractor.py` | 18 | `~/.hermes/workspace/stock_daily` | 运行时代码 | P1 |
| `src/skills/stock-research/SKILL.md` | 164 | `~/.hermes/workspace/stock_daily` | Skill 文档 | P2 |
| `src/skills/system-warmup-stock/SKILL.md` | 18-19 | `~/.hermes/workspace/stock_daily` | Skill 文档 | P2 |
| `src/scripts/fetch/update_anchor.py` | 11-12 | `/Users/xiashuang/harness/...` | 运行时代码 | P1 |
| `src/scripts/fetch/fetch_realtime.py` | 25 | `/Users/xiashuang/harness/...` | 运行时代码 | P1 |
| `src/scripts/core/stock_ranking.py` | 35 | `~/harness/stock_daily` | 运行时代码 | P1 |
| `src/workflows/wrappers/stock_daily_fetch.sh` | 6 | `/Users/xiashuang/harness/...` | Shell 包装器 | P1 |
| `src/scripts/legacy/full_market_ml_backtest.py` | 35-36 | `/Users/xiashuang/harness/...` | 运行时代码 | P2 |
| `src/scripts/legacy/*.py` (10+ 文件) | 多处 | `HERMES_WORKSPACE` 环境变量 | 运行时代码 | P2 |

**总计**：发现 15+ 处硬编码路径引用，其中 4 处为 `~/.hermes/workspace/stock_daily`（已失效），其余为 `~/harness/stock_daily`（当前实际路径）。

### 2.2 路径类型分类

1. **失效路径**（4 处）：`~/.hermes/workspace/stock_daily` → 应改为 `~/harness/stock_daily`
2. **有效但硬编码**（10+ 处）：`/Users/xiashuang/harness/...` → 应改为环境变量或配置项
3. **文档引用**（3 处）：SKILL.md 中的操作说明 → 保留历史证据，添加注释说明当前实际路径
4. **环境变量**（10+ 处）：`HERMES_WORKSPACE` → 已提供降级默认值，建议文档化

### 2.3 修复建议

- **P1 修复**：4 处失效路径 → 改为 `~/harness/stock_daily` 或 `DATA_ROOT` 环境变量
- **P2 改进**：10+ 处硬编码 → 提取为 `DATA_ROOT` 环境变量，代码中统一使用 `os.getenv("DATA_ROOT", "~/harness/stock_daily")`
- **保留**：SKILL.md 中的历史引用 → 添加注释说明"此为旧路径，当前实际路径为..."

---

## 三、不安全代码模式审计

### 3.1 `shell=True` 检查

**发现**：0 处 `shell=True` 显式使用。

**说明**：所有 `subprocess.run()` 调用均使用参数列表形式（安全），未使用 `shell=True`。

### 3.2 裸 `except:` 检查

**发现**：4 处裸 `except:`

| 文件 | 行号 | 上下文 | 风险 |
|---|---|---|---|
| `src/obsidian/01-股票投研/tools/daily_update.py` | 122, 132 | 数据更新循环内 | P2（可能吞掉数据错误） |
| `src/trading/strategies/ml/alerts.py` | 87 | 告警发送 | P2（可能静默失败） |
| `src/trading/strategies/ml/optimizer.py` | 83 | 优化循环 | P2（可能吞掉优化错误） |

**建议**：改为 `except Exception as e:` 并记录日志。

### 3.3 `timeout` 检查

**发现**：
- JEV MCP 调用：已设置 `timeout=60`（合理）
- 网络请求（`urllib`）：`timeout=10-15`（合理）
- 子进程调用：部分有 `timeout=30`，部分无

**风险点**：
- `src/scripts/legacy/kotler_batch.py`（2 处）：无 timeout
- `src/scripts/legacy/backtest_signals.py`：无 timeout
- `src/scripts/legacy/ml_trend_predict.py`：无 timeout

**建议**：为所有子进程调用添加 `timeout=300`（5 分钟）。

---

## 四、配置与密钥管理审计

### 4.1 `.gitignore` 验证

**已检查**：`.gitignore` 包含以下规则：
- `**/.key`、`**/*.key`（密钥文件）
- `**/.env`（环境配置）
- `**/auth.json`、`**/settings.json`（认证信息）
- `**/config.toml`、`**/config.yaml`（真实配置）
- `**/portfolio_*.json`、`**/*holding*`（持仓信息）
- `**/logs/`、`**/__pycache__/`（日志与缓存）

**结论**：规则覆盖充分，但需验证实际效果（见 `config-security-report.md`）。

### 4.2 配置模板检查

**已创建**：
- `docs/config/codex-config.toml.template`（占位符版）
- `docs/config/hermes-config.yaml.template`（占位符版）

**问题**：
- 模板参数与代码实际读取的变量未逐一对齐
- 缺少必要配置缺失时的行为说明

**建议**：补充配置验证脚本，检查模板与代码的一致性。

---

## 五、JEV 调用契约审计

### 5.1 工具定义核实

已确认 5 个 MCP 工具（来自 `src/jev/server.py`）：

| 工具 | 输入 | 输出 | 状态 |
|---|---|---|---|
| `jev_decide` | `state`, `questions`, `model` | `{ok, model, answers, usage, request}` | ✓ 已实现 |
| `jev_yes_no` | `state`, `question`, `no_text`, `mode`, `model` | 同上 | ✓ 已实现 |
| `jev_guard_tool_call` | `tool`, `action`, `arguments_summary`, `side_effects`, ... | 同上 | ✓ 已实现 |
| `jev_route` | `task`, `options`, `model` | 同上 | ✓ 已实现 |
| `jev_front_door` | `task`, `model` | `{gate, gate_raw, route, hint}` | ✓ 已实现 |

### 5.2 错误处理检查

**发现**：
- `_call()` 函数处理了 `httpx.TimeoutException` 和 `httpx.HTTPError`
- 返回 `{"ok": False, "error": ...}` 格式
- CLI 调用有 `timeout=60` 和 `timeout_s + 30` 双重保护

**风险**：
- 未明确检查 `answers` 字段是否存在
- 未处理 `jev_front_door` 返回结构与其他工具不同的情况

**建议**：添加输入校验和返回字段验证。

---

## 六、数据完整性与错误处理

### 6.1 CSV/JSON 读取

**发现**：
- 大部分使用 `json.load()` 和 `pandas.read_csv()`
- 缺少显式的字段校验和类型检查

**风险**：
- 字段缺失时可能静默失败
- 类型错误可能导致后续计算异常

**建议**：添加数据验证层（如 `pydantic` 或手动校验）。

### 6.2 日期与时区

**发现**：
- 使用 `datetime.now()` 但未指定时区
- 部分脚本使用 `datetime.strptime()` 解析日期

**风险**：
- 时区不一致可能导致日期判断错误
- 交易日判断可能受时区影响

**建议**：统一使用 `Asia/Shanghai` 时区。

---

## 七、未检查项目

| 项目 | 原因 |
|---|---|
| 完整功能测试 | P2 仅静态审计，测试将在阶段四执行 |
| 网络调用实际行为 | 禁止执行真实 API 调用 |
| JEV MCP 真实可达性 | P2 禁止执行真实 JEV 调用 |
| 第三方依赖版本 | 未安装 `pip` 依赖，无法检查 |

---

## 八、总结

### 8.1 高风险问题（P0）

- **无**（未发现可能引起严重数据破坏或凭证泄露的问题）

### 8.2 中风险问题（P1）

| ID | 问题 | 文件数 | 建议 |
|---|---|---|---|
| P1-01 | 失效路径 `~/.hermes/workspace/stock_daily` | 4 | 改为 `~/harness/stock_daily` 或 `DATA_ROOT` |
| P1-02 | 裸 `except:` 可能吞掉错误 | 4 | 改为 `except Exception as e:` 并记录日志 |

### 8.3 低风险问题（P2）

| ID | 问题 | 文件数 | 建议 |
|---|---|---|---|
| P2-01 | 硬编码绝对路径 | 10+ | 提取为环境变量 `DATA_ROOT` |
| P2-02 | 子进程调用缺少 `timeout` | 3 | 添加 `timeout=300` |
| P2-03 | JEV 返回字段未校验 | 1 | 添加输入/输出验证 |
| P2-04 | 配置模板与代码未对齐 | 2 | 补充配置验证脚本 |
| P2-05 | 日期时区未统一 | 多处 | 统一使用 `Asia/Shanghai` |

### 8.4 未修复问题

- SKILL.md 中的历史路径引用 → 保留作为迁移证据，添加注释说明

---

## 九、下一步

1. 执行 P1 修复（失效路径、裸 `except`）
2. 执行 P2 改进（环境变量提取、timeout 补充）
3. 建立测试并验证修复效果
4. 更新配置模板与代码对齐

