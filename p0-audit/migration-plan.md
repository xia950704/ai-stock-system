# P0 迁移计划（migration-plan）

> 生成时间：2026-10-20。P0 只读探查产物。
> 基于资产清单、依赖地图、权威来源，提出 P1 迁移的顺序、原则与回滚方案。

## 1. 迁移原则

1. **只读先行**：P0 阶段仅探查，P1 阶段执行只读复制与只读同步，禁止在 Obsidian 中写回。
2. **逐批验证**：每批文件复制后，使用 sha256 对比源与目标，记录验证状态。
3. **解耦硬编码**：迁移过程中将绝对路径替换为相对路径或环境变量（如 `DATA_ROOT`、`OBSIDIAN_VAULT`）。
4. **保持可用性**：迁移不应中断现有 cron、workflow 或 Skill 的运行，必要时保持双份运行直至验证完成。
5. **可回滚**：所有复制操作均保留原始文件，目标文件可删除以回滚；不修改源文件。

## 2. 迁移批次与顺序

| 批次 | 内容 | 目标目录 | 关键依赖 | 风险点 |
|---|---|---|---|---|
| 0 | 本次 P0 产物 | `p0-audit/` | 无 | 低 |
| 1 | 核心行情数据与机器产出 | `src/data/` | `~/harness/stock_daily/`、`~/obsidian/all about xia/01-股票投研/data/` | 中（需保证更新不同步） |
| 2 | Obsidian 只读副本（增量） | `src/obsidian/` | `~/obsidian/all about xia/` | 低（只读复制） |
| 3 | 投研 Skill 与系统脚本 | `src/scripts/`、`src/jev/`、`src/trading/` | `/Volumes/夏爽/migration-20260922/hermes-scripts/`、`~/stock_ml_trading/`、`~/.hermes/mcp-servers/jev-systemone/` | 中（路径替换） |
| 4 | 工作流与定时任务声明 | `src/workflows/` | `~/.hermes/cron/`、`~/.hermes/scripts/wrappers/`、`xia950704/daily_stock_analysis` workflow | 低（参考迁移） |
| 5 | 文档与规则 | `docs/` | `~/agent-workspace/AGENTS.md`、`~/obsidian/all about xia/AGENTS.md`、`~/agent-workspace/` 规则 | 低 |

## 3. 每批次操作步骤（以批次 1 为例）

1. **清点源文件**：列出 `~/harness/stock_daily/` 下所有待迁移文件（JSON、CSV、PY 脚本）。
2. **创建目标目录**：`mkdir -p src/data/raw/prices src/data/raw/anchor src/data/processed/portfolio src/data/processed/rankings src/data/processed/indicators src/data/archive/daily/2026/10`。
3. **复制文件**：使用 `cp -p` 保持时间戳，或 `rsync --archive --update`。
4. **计算哈希**：对源与目标文件分别计算 sha256，记录于迁移清单。
5. **验证一致性**：若哈希匹配，标记 verification = verified；否则报告不一致。
6. **更新引用**：在脚本中将硬编码路径替换为环境变量或相对路径（如 `os.getenv('DATA_ROOT', '/default/path') + '/raw/prices/'`）。
7. **试运行**：在不影响现有任务的前提下，用新路径运行一次脚本，检查产出是否一致。
8. **切换**：如验证通过，将 cron wrapper 或 Skill 中的路径指向新目标；保留旧路径作为回滚。
9. **日志记录**：将本次迁移的 sha256、时间、操作人记录到 `docs/migration-log.md`。

## 4. 回滚方案

- **文件层面**：目标文件删除即可恢复至未迁移状态；源文件保持不变。
- **引用层面**：若修改了脚本或 Skill 中的路径，可恢复原备份（建议在修改前备份）。
- **数据层面**：因仅复制只读数据，无需担心数据丢失；如出现写回，需检查是否误修改源。
- **回滚记录**：在 `docs/migration-log.md` 中添加回滚条目，标记原因与时间。

## 5. 冲突处理策略

| 冲突类型 | 处理方式 |
|---|---|
| 目标目录已存在同名文件 | 比较 sha256：若一致，跳转；若不一致，加时间戳后缀保存为 `.conflict.<timestamp>` 并人工审查。 |
| 源文件缺失 | 记录为 missing，阻断该批次迁移，人工补全后重试。 |
| 脚本引用失效（路径替换后） | 恢复引用至原路径，调试后重新尝试替换。 |
| 版本不一致（如两处脚本内容不同） | 保留较新版本（根据文件时间），并记录决策依据至 `docs/migration-decision.md`。 |

## 6. 验证点（P1 完成标准）

- 所有迁移清单中的文件已复制并哈希验证（verification = verified）。
- 所有关键脚本（如 data 抓取、因子计算、报告生成）已成功运行至少一次，产出与预期一致。
- 所有硬编码绝对路径（如 `/Volumes/夏爽/`、`/Users/xiashuang/harness/`）在源码中已被环境变量或相对路径替换。
- Obsidian 原始文件（`.md`、`.csv`、`.json`）无任何写入痕迹（可通过 git diff 或在只快照中比较）。
- Hermes cron 与 GitHub workflow 均可正常触发，且使用新路径后产出未变化。
- 文档 `docs/migration-guide.md` 已完成，包含完整步骤与回滚方案。

## 7. 下一步（P1 交付物）

- `docs/migration-manifest.csv`（已含 hash、验证状态）。
- `docs/migration-log.md`（迁移与回滚记录）。
- `docs/migration-decision.md`（如有版本取舍的说明）。
- `docs/migration-guide.md`（完整操作手册）。
- 提交审计报告，等待批准进入 P2。

