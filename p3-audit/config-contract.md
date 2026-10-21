# P3 配置契约文档（config-contract）

> 生成时间：2026-10-20
> 验证脚本：`src/scripts/validate_stock_config.py`

---

## 一、环境变量规范

### 1.1 `DATA_ROOT`

| 属性 | 值 |
|---|---|
| **用途** | 数据根目录，包含锚价权威源和备份目录 |
| **默认值** | `~/harness` |
| **必需** | 否（有默认值） |
| **被读取** | `update_anchor.py`, `fetch_realtime.py` |
| **路径拼接** | `ANCHOR_PATH = os.path.join(DATA_ROOT, "anchor_status.json")` |
| **缺失行为** | 使用默认值 `~/harness` |
| **验证** | 目录必须存在且可访问 |

**关键文件**：
- `{DATA_ROOT}/anchor_status.json` — 锚价权威源（56 条记录）
- `{DATA_ROOT}/backup_phase1/anchor_status.pre_update.json` — 更新前备份

---

### 1.2 `STOCK_DAILY_DIR`

| 属性 | 值 |
|---|---|
| **用途** | 股票日常数据目录，包含实时价格、排名、回测信号等 |
| **默认值** | `~/harness/stock_daily` |
| **必需** | 否（有默认值） |
| **被读取** | `stock_signal_extractor.py`, `stock_ranking.py`, `backtest_*.py` |
| **路径拼接** | `REPORT_DIR = os.path.expanduser(os.environ.get("STOCK_DAILY_DIR", "~/harness/stock_daily"))` |
| **缺失行为** | 使用默认值 `~/harness/stock_daily` |
| **验证** | 目录必须存在且包含必要的 JSON 文件 |

**关键文件**：
- `{STOCK_DAILY_DIR}/realtime_prices_YYYYMMDD.json` — 实时价格快照
- `{STOCK_DAILY_DIR}/anchor_status_YYYY-MM-DD.json` — 锚价日期快照
- `{STOCK_DAILY_DIR}/stock_portfolio_enriched.json` — 投资组合（56 条）
- `{STOCK_DAILY_DIR}/stock_ranking.json` — 综合排名
- `{STOCK_DAILY_DIR}/backtest_signals.json` — 回测信号

---

### 1.3 `HERMES_WORKSPACE_DIR`

| 属性 | 值 |
|---|---|
| **用途** | Hermes 工作目录，包含 ML 预测等中间产物 |
| **默认值** | `~/.hermes/workspace` |
| **必需** | 否（有默认值） |
| **被读取** | `stock_ranking.py` |
| **路径拼接** | `path = os.path.join(os.path.expanduser(os.environ.get("HERMES_WORKSPACE_DIR", "~/.hermes/workspace")), "ml_trend_predictions.json")` |
| **缺失行为** | 使用默认值 `~/.hermes/workspace` |
| **验证** | 目录应存在，但 ML 预测文件可能缺失（非阻塞） |

**关键文件**：
- `{HERMES_WORKSPACE_DIR}/ml_trend_predictions.json` — ML 趋势预测（可选）

---

## 二、路径规则

### 2.1 路径拼接原则

1. 所有路径使用 `os.path.join()` 拼接，禁止字符串拼接。
2. 所有路径使用 `os.path.expanduser()` 处理 `~`。
3. 所有路径优先从环境变量读取，其次使用默认值。
4. 路径不存在时，程序应清晰报错，不静默创建空白目录。

### 2.2 已修复的硬编码路径

| 文件 | 修复内容 |
|---|---|
| `stock_signal_extractor.py:18` | 改为 `os.environ.get("STOCK_DAILY_DIR", "~/harness/stock_daily")` |
| `stock_ranking.py:35` | 改为 `os.environ.get("STOCK_DAILY_DIR", "~/harness/stock_daily")` |
| `update_anchor.py:11-12` | 改为 `DATA_ROOT` 环境变量 |
| `fetch_realtime.py:25` | 改为 `DATA_ROOT` 环境变量 |

### 2.3 保留的路径（登记）

| 文件 | 路径 | 原因 |
|---|---|---|
| `stock_daily_fetch.sh` | `/Users/xiashuang/harness/stock_daily` | 心跳脚本，P3 禁止修改 |
| `SKILL.md`（多个） | `~/.hermes/workspace/stock_daily` | 历史证据，全局 Skill 禁改 |
| `full_market_ml_backtest.py` | `~/harness/deeppulse/db/astock.duckdb` | DB 文件真实存在，legacy 脚本 |

---

## 三、配置字段规范

### 3.1 `anchor_status.json` 字段

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `name` | string | 是 | 股票名称 |
| `code` | string | 是 | 股票代码（如 `sh600276`） |
| `current` | float | 是 | 当前价 |
| `anchor` | float | 是 | 锚价（用户维护的动态值） |
| `deviation` | float | 是 | 偏离百分比 `(current-anchor)/anchor*100` |
| `status` | string | 是 | 状态（买入区间/偏低估/合理/偏高/超买/无锚价） |
| `pe` | float | 否 | 市盈率 |
| `prev_close` | float | 否 | 前收盘价 |
| `change_pct` | float | 否 | 涨跌幅 |

### 3.2 `realtime_prices_*.json` 字段

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `code` | string | 是 | 股票代码 |
| `name` | string | 是 | 股票名称 |
| `price` | float | 是 | 实时价格 |
| `prev_close` | float | 否 | 前收盘价 |
| `change_pct` | float | 否 | 涨跌幅 |
| `timestamp` | string | 否 | 时间戳 |
| `anchor` | float | 否 | 锚价 |
| `deviation` | float | 否 | 偏离百分比 |
| `status` | string | 否 | 状态 |

---

## 四、验证脚本

**位置**：`src/scripts/validate_stock_config.py`

**用法**：
```bash
# 普通验证
python3 src/scripts/validate_stock_config.py

# 严格模式（警告也返回非零）
python3 src/scripts/validate_stock_config.py --strict
```

**检查项**：
1. 环境变量是否存在（`DATA_ROOT`, `STOCK_DAILY_DIR`, `HERMES_WORKSPACE_DIR`）
2. 路径是否按预期解析
3. 目录是否存在且可访问
4. `anchor_status.json` 是否存在且 JSON 格式有效
5. 配置契约文档与代码一致性

---

## 五、时区与日期规则

### 5.1 时区

- **程序运行时区**：使用系统时区（默认 `Asia/Shanghai`）
- **行情源时区**：腾讯 API 返回的时间戳为北京时间
- **报告生成时间**：使用 `datetime.now(timezone(timedelta(hours=8)))`（UTC+8）

### 5.2 交易日判断

- **A 股交易日**：周一至周五（排除法定节假日）
- **数据新鲜度**：
  - 实时价格：盘中每分钟更新，收盘后固定
  - 锚价状态：每日收盘后更新
- **非交易日处理**：
  - 若当天无行情，应使用最近一个交易日的收盘数据
  - 报告应明确标注数据所属交易日

### 5.3 日期格式

| 文件 | 日期格式 | 示例 |
|---|---|---|
| `realtime_prices_*.json` | `YYYYMMDD` | `realtime_prices_20260923.json` |
| `anchor_status_*.json` | `YYYY-MM-DD` | `anchor_status_2026-09-23.json` |
| 报告生成时间 | `YYYY-MM-DD` | `2026-10-20` |

---

## 六、配置缺失时的行为

| 配置缺失 | 行为 |
|---|---|
| `DATA_ROOT` 未设置 | 降级到 `~/harness` |
| `STOCK_DAILY_DIR` 未设置 | 降级到 `~/harness/stock_daily` |
| `HERMES_WORKSPACE_DIR` 未设置 | 降级到 `~/.hermes/workspace` |
| `anchor_status.json` 不存在 | 程序报错退出（清晰错误） |
| `stock_portfolio_enriched.json` 不存在 | 排名程序报错退出 |
| `ml_trend_predictions.json` 不存在 | 排名程序继续（ML 加成设为 0） |

---

## 七、安全注意事项

1. **不打印真实密钥**：验证脚本不读取或输出任何 API Key。
2. **不修改配置**：验证脚本只读检查，不修改环境变量或配置文件。
3. **不创建业务目录**：验证脚本不自动创建 `~/harness` 或其他业务目录。
4. **不访问交易接口**：验证脚本不调用任何真实交易 API。

---

## 八、待运行时验证项

| 项 | 状态 |
|---|---|
| JEV MCP 真实网络可达性 | P3-1 验证 |
| relay `127.0.0.1:57321` 服务状态 | 未验证 |
| GitHub Actions Secrets 有效期 | 未验证 |
| `~/.hermes/config.yaml` 中的明文 API Key | 已知风险，待用户轮换 |

---

## 九、配置验证历史

| 日期 | 验证结果 | 备注 |
|---|---|---|
| 2026-10-20 | ✅ 通过（3 警告） | 环境变量均使用默认值，路径存在且有效 |

