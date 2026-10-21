# P2 修复日志

> 生成时间：2026-10-20  
> 修复原则：局部修复，保持原有业务逻辑，不改变策略语义

---

## 修复记录

### P1-01: 失效路径修复 `~/.hermes/workspace/stock_daily`

**问题**：旧工作目录 `~/.hermes/workspace/stock_daily` 已失效；SKILL 文档中的历史引用需保留。

**修复**：

| 文件 | 旧路径 | 新路径 | 修复方式 |
|---|---|---|---|
| `src/scripts/legacy/stock_signal_extractor.py:18` | `~/.hermes/workspace/stock_daily` | `~/harness/stock_daily` | 改为 `STOCK_DAILY_DIR` 环境变量，缺失时降级到 `~/harness/stock_daily` |
| `src/skills/stock-research/SKILL.md` | `~/.hermes/workspace/stock_daily` | 未修改 | 保留历史证据（见 `reference-audit.md` REF-08） |
| `src/skills/system-warmup-stock/SKILL.md` | `~/.hermes/workspace/stock_daily` | 未修改 | 保留原样，待用户确认（见 `reference-audit.md` REF-09） |

**验证**：
- 运行 `grep -rn "~/.hermes/workspace/stock_daily" src/` 确认无遗漏
- 测试脚本运行（待阶段四执行）

**回滚**：恢复旧路径字符串即可。

---

### P1-02: 裸 `except:` 修复

**问题**：4 处裸 `except:` 可能吞掉错误。

**修复**：

| 文件 | 行号 | 修复 |
|---|---|---|
| `src/obsidian/01-股票投研/tools/daily_update.py` | 122, 132 | 改为 `except Exception as e:` 并 `print(f"⚠️ 解析失败：{e}")` |
| `src/trading/strategies/ml/alerts.py` | 87 | 改为 `except Exception as e:` 并记录日志 |
| `src/trading/strategies/ml/optimizer.py` | 83 | 改为 `except Exception as e:` 并记录日志 |

**验证**：
- 语法检查通过
- 测试执行（待阶段四）

**回滚**：恢复裸 `except:`。

---

### P2-02: 子进程 `timeout` 补充（部分）

**问题**：多步子进程调用缺少 `timeout` 或 timeout 较短。

**本次修复**：

| 文件 | 行号 | 修复 |
|---|---|---|
| `src/scripts/legacy/kotler_batch.py` | 41, 62 | 添加 `timeout=300` / `timeout=600` |

**未修改（登记）**：

| 文件 | 行号 | 当前值 | 说明 |
|---|---|---|---|
| `src/scripts/legacy/backtest_signals.py` | 775 | `timeout=30` | 已登记，P3/P4 再评估是否加长 |
| `src/scripts/legacy/ml_trend_predict.py` | 474 | `timeout=30` | 已登记，P3/P4 再评估是否加长 |

**验证**：
- 语法检查通过
- 测试执行（待阶段四）

**回滚**：移除 `timeout` 参数。

---

## 未修复问题

| ID | 问题 | 原因 |
|---|---|---|
| P2-01 | 硬编码绝对路径（10+ 处） | 需建立 `DATA_ROOT` 环境变量规范，待用户确认 |
| P2-03 | JEV 返回字段未校验 | 需添加输入验证层，待阶段四测试覆盖 |
| P2-04 | 配置模板与代码未对齐 | 需补充配置验证脚本 |
| P2-05 | 日期时区未统一 | 需全局时区规范 |

---

## 测试对应

| 修复 ID | 对应测试 |
|---|---|
| P1-01 | 路径测试：环境变量缺失、移动硬盘未挂载 |
| P1-02 | 错误处理测试：无效输入、异常数据 |
| P2-02 | 未单独建测试（离线验证 timeout 参数存在） |

