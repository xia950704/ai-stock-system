# P2 验收清单

> 生成时间：2026-10-20  
> 验收范围：代码审计、路径修复、错误处理、配置管理、离线测试

---

## 验收要求与状态

| ID | 要求 | 状态 | 证据 |
|---|---|---|---|
| A-01 | P1 交付物和迁移基线已核实 | PASS | `p2-audit/baseline-*.json` |
| A-02 | 关键代码、配置和引用得到实际检查 | PASS | `p2-audit/code-audit-report.md` |
| A-03 | 已确认的高风险问题得到修复 | PASS | `p2-audit/remediation-log.md` |
| A-04 | 硬编码路径完成修复或明确保留 | PASS | 4 处失效/硬编码运行路径已改为环境变量，其余（SKILL.md、heartbeat wrapper、legacy 回测、Obsidian 镜像）保留并登记于 `reference-audit.md` |
| A-05 | 关键错误处理和输入校验有对应测试 | PASS | `p2-audit/tests/test_exceptions.py` |
| A-06 | 关键测试实际执行并有结果证据 | PASS | `p2-audit/tests/output/` 19/19 通过 |
| A-07 | JEV 失败不会被错误解释为有效信号 | PASS | `test_jev_mock.py` 验证 `_call` 返回 `ok=False` |
| A-08 | 配置模板和 `.gitignore` 已检查 | PASS | `p2-audit/config-security-report.md` |
| A-09 | Obsidian 原始文件未发生非预期变化 | PASS（有外部观察） | HEAD 仍为 `2734b0a1`；基线 22 个未提交变更，复查时为 25 个，新增 3 个 `.vault-operator/` 外部改动（13:16 发生），不属于 P2 修改，未回滚 |
| A-10 | 线上 Workflow、心跳脚本、全局配置未被触碰 | PASS | 未修改 `~/.hermes/cron/`、`~/.codex/config.toml` |
| A-11 | 所有修改可追溯，回滚方式明确 | PASS | `remediation-log.md` 记录每项修复及回滚步骤 |
| A-12 | 未解决的问题、剩余风险已披露 | PASS | `code-audit-report.md` 第 8 节 |

---

## 测试执行汇总

| 测试文件 | 通过 | 失败 | 跳过 |
|---|---|---|---|
| `test_paths.py` | 7 | 0 | 0 |
| `test_exceptions.py` | 3 | 0 | 0 |
| `test_data_integrity.py` | 4 | 0 | 0 |
| `test_jev_mock.py` | 5 | 0 | 0 |
| **总计** | **19** | **0** | **0** |

---

## 修复汇总

| 修复 ID | 问题 | 文件 | 状态 |
|---|---|---|---|
| P1-01 | 失效路径 `~/.hermes/workspace/stock_daily` | `stock_signal_extractor.py` | ✅ |
| P1-02 | 裸 `except:` | `alerts.py`, `optimizer.py`, `daily_update.py` | ✅ |
| P2-01 | 硬编码绝对路径 | `update_anchor.py`, `fetch_realtime.py`, `stock_ranking.py` | ✅ |
| P2-02 | 缺少 `import os` | `update_anchor.py`, `fetch_realtime.py` | ✅ |

---

## 未解决问题（非阻塞）

| ID | 问题 | 原因 | 建议 |
|---|---|---|---|
| U-01 | 配置模板与代码未逐一对齐 | P2 范围外 | P3 补充配置验证脚本 |
| U-02 | 日期时区未统一 | 需全局规范 | P3 建立时区工具函数 |
| U-03 | JEV 真实网络可达性 | P2 禁止真实调用 | P3 在隔离环境验证 |

---

## P2 验收结论

**建议：P2 有条件通过**

条件：
1. 用户确认 `DATA_ROOT` 和 `STOCK_DAILY_DIR` 环境变量规范
2. P3 前补充配置验证脚本
3. P3 验证 JEV 真实网络可达性

**禁止自动进入 P3**。需用户明确批准。

