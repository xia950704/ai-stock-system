# P6 修复与回滚日志

> 生成时间：2026-10-20 23:35 (Asia/Shanghai)

## 一、源码变更

| 文件 | 操作 | 前置 SHA‑256 | 后置 SHA‑256 | 说明 |
|------|------|-------------|-------------|------|
| `src/engine/jev_adapter.py` | 修改 | `3d1c88ee4b15e5fc8227b5a6af4abf1aa77936daea0309a08e0ecf3b0aed1eac` | 见 `scratch/p6-prechange-hashes.txt` | 新增 `PROVIDER` 配置与 `provider_config()`，不影响默认行为 |
| `p6-audit/tests/test_p6.py` | 新增 | — | — | 15 项适配层测试 |
| `scratch/p6/citation-ledger.json` | 新增 | — | — | Search 验证来源台账 |
| `p6-audit/*.md` | 新增 | — | — | 本阶段 9 份审计报告 |

## 一、P6 后续修正（2026-10-20 收尾）

| 文件 | 操作 | 前置 SHA‑256 | 后置 SHA‑256 | 说明 |
|------|------|-------------|-------------|------|
| `src/search/client.py` | 修改 | `66638f454f08385196d1b578057a5c08ef8a1075cb9d9ea74c2958e694f5e6f7` | `7c13c3ce5460cd48a7f1171b2f948364677bda14440199b74c4eb89dc94b4c99` | 新增 `_load_dotenv()`：从 Workspace 根目录 `.env` 加载 `SEARCH_API_BASE_URL` / `SEARCH_API_KEY` 等变量（环境变量优先） |
| `p5-audit/tests/test_p5.py` | 修改 | `9aae718e10d8757999099c0dc0be4da3affed6950b8ae177d455194363c5015c` | `45f90d51c4607a0dfb539c8f0282031bd81c4e9a6ff076814e6b2adf000ed4af` | T-S07 改为使用临时空配置文件隔离，避免 `.env` 加载导致真实 key 被读取 |
| `p6-audit/tests/test_p6.py` | 修改 | — | `09a7fc71a930b64a5cfa815752dc476e63460ae4c8d26d179fab1145c34c1732` | 新增 T-P6-16~18：`.env` 加载、环境变量优先、无 key 降级 |

### 回滚步骤（P6 后续修正）

1. **Search 客户端**：将 `src/search/client.py` 恢复至前置哈希 `66638f454f08385196d1b578057a5c08ef8a1075cb9d9ea74c2958e694f5e6f7`（删除 `_load_dotenv()` 函数及其调用即可）。
2. **P5 测试**：将 `p5-audit/tests/test_p5.py` 恢复至前置哈希 `9aae718e10d8757999099c0dc0be4da3affed6950b8ae177d455194363c5015c`。
3. **P6 测试**：删除 `p6-audit/tests/test_p6.py` 中 T-P6-16~18 三个测试函数及其调用。

基线记录：`scratch/p6-prechange-hashes.txt`

## 二、回滚步骤

### 2.1 源码回滚
1. 将 `src/engine/jev_adapter.py` 恢复至前置哈希 `3d1c88ee4b15e5fc8227b5a6af4abf1aa77936daea0309a08e0ecf3b0aed1eac`（若无备份，删除新增的 `PROVIDER` 行与 `provider_config()` 函数即可）。
2. 删除环境变量 `JEV_PROVIDER` / `JEV_API_KEY`。
3. 校验：`shasum -a 256 src/engine/jev_adapter.py` 应与前置哈希一致。

### 2.2 测试与产物回滚
- 删除 `p6-audit/` 目录下本阶段新增文件。
- 删除 `scratch/p6/` 目录。
- 重新运行 P2‑P5 测试，确认总数回到 115 项。

## 三、风险

- 本阶段修改仅限 `src/engine/jev_adapter.py`，未触及 JEV 核心判定逻辑或 `src/jev/server.py`。
- 未修改 Obsidian、GitHub Workflow、全局配置。
- 未发起真实 JEV 请求，未产生费用。

## 四、2026-10-21 运行资格修复

| 文件 | 修改 | 原因 |
|---|---|---|
| `src/engine/daily_judge.py` | 读取行情 as-of 日期和 freshness gate；汇总 JEV 真实成功率；追溯链动态描述 | 修复报告把系统日期误当行情日期、JEV 状态硬编码的问题 |
| `src/engine/report.py` | A 节显示行情所属日期和 gate；JEV 状态解释更准确 | 防止把 effective_date 误认为行情日期 |
| `src/engine/stock_judge.py` | JEV 层保留错误分类，同时展示 model/transport/answers；更新陈旧 note | 让真实 JEV 输出可审计，同时明确不驱动动作 |
| `p6-audit/tests/test_p6.py` | 测试跟随当前 AMD/Clef 配置；禁用本地 server dir 验证无 key | 修正过期硬编码 bynara 假设 |
| `.env` | 权限 `644` → `600` | 收紧真实配置读取权限 |
| `scratch/p6/citation-ledger.json` | 新增恒瑞半年度报告来源 | 记录事实核验证据 |
| `src/backtest/radar_inventory.py` | 新增 | 生成可复现的历史雷达覆盖清单 |
| `p6-audit/tests/test_radar_inventory.py` | 新增 | 验证覆盖统计与完整性门槛 |
| `governance/runs/stock-system-e2e-readiness/20261021-1050/` | 新增 | 记录最终资格、清单和真实运行产物 |

最终哈希：`scratch/p6-20261021-postchange-hashes.txt`；备份：`scratch/p6-20261021-backup/`。

回滚：从备份恢复上述四个代码/测试文件；执行 `chmod 644 .env` 可恢复原权限；P6 测试和 citation ledger 追加项可按本次修改记录逐项删除。JEV 外部配置未修改，恢复 Workspace 代码后即可回到适配层修改前的行为。

副作用记录：本次执行了用户目标明确授权的 JEV 与 Search 真实只读调用；调用日志已落盘。未充值、未交易、未触发远程 Workflow、未修改全局配置。

## Final eight-scenario completion

- Added controlled `--mock-jev-fail` path to execute real Search with a guaranteed JEV failure.
- Fixed stale gate by passing request `report_date` into stock-level analysis.
- Fixed malformed JEV availability classification: `ok=true` with non-dict answers becomes `parse_error`.
- Executed scenarios 1 through 8; see governance run `20261021-1050`, especially `05_SHADOW_RUN.md`.
- Re-ran full regression after all fixes: 137/137 passed.
- Governance documents 00 through 09 were created under `governance/runs/stock-system-e2e-readiness/20261021-1050/`.
