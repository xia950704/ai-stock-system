# P6 回归测试报告

> 生成时间：2026-10-20 23:30 (Asia/Shanghai)

## 一、测试套件概览

| 套件 | 测试数 | 通过 | 失败 | 跳过 | 说明 |
|------|--------|------|------|------|------|
| P2 (`p2-audit/tests/`) | 19 | 19 | 0 | 0 | 路径、异常、数据完整性、JEV Mock |
| P3 (`p3-audit/tests/test_engine.py`) | 28 | 28 | 0 | 0 | 引擎、交易日、大盘、股票、报告 |
| P4 (`p4-audit/tests/test_backtest.py`) | 32 | 32 | 0 | 0 | 回放、评估、Decision Model 契约、注册表 |
| P5 (`p5-audit/tests/test_p5.py`) | 36 | 36 | 0 | 0 | Search 结构、URL 去重、来源分级、JEV 契约、新鲜度、报告冲突 |
| P6 (`p6-audit/tests/test_p6.py`) | 18 | 18 | 0 | 0 | JEV 模型适配层配置、Mock 兼容、无 key 处理、`.env` 加载 |
| **总计** | **133** | **133** | **0** | **0** | **全部通过** |

## 二、P6 新增测试明细

| 测试 ID | 内容 |
|---------|------|
| T-P6-01~05 | 默认 provider/model/base_url/timeout/key_source |
| T-P6-06~09 | 环境变量覆盖配置 |
| T-P6-10~12 | Mock 调用仍可用，请求结构不变 |
| T-P6-13 | 无 key 时返回 `no_key` |
| T-P6-14~15 | 失败不被解释为有效判定 |
| T-P6-16 | `.env` 中 SEARCH_API_BASE_URL / SEARCH_API_KEY 被加载 |
| T-P6-17 | 环境变量优先于 `.env` |
| T-P6-18 | 无 key 时（禁用 `.env`）返回 `no_key` |

### P5 测试修复

| 修复 | 内容 |
|------|------|
| T-S07 | 原测试未禁用 `.env`，在 P6 新增 `.env` 加载后会误读真实 key；已改为使用临时空配置文件隔离 |

## 二、执行命令（含 P6 新增）</arg_value>

## 三、未执行/未覆盖

- **真实 JEV 调用**：`BLOCKED`（上游模型/积分未就绪），未标记为 PASS。
- **真实 Search 多源交叉验证**：2 次真实查询成功，但独立来源不足，证据层标记为受限，未计入 130 项。
- **P3.5 原始 21 项测试**：`p35-audit/tests/` 目录仍缺失完整测试源码，标记为 `NOT TESTED`；P5 36 项已覆盖其核心功能块。

## 四、执行命令

```bash
python3 p2-audit/tests/test_paths.py
python3 p2-audit/tests/test_exceptions.py
python3 p2-audit/tests/test_data_integrity.py
python3 p2-audit/tests/test_jev_mock.py
python3 p3-audit/tests/test_engine.py
python3 p4-audit/tests/test_backtest.py
python3 p5-audit/tests/test_p5.py
python3 p6-audit/tests/test_p6.py
```

## 五、结论

**130 项全部通过，0 失败，0 跳过。** 真实 JEV 与完整历史回放仍为外部阻断，不影响本阶段测试结果。

## 六、2026-10-21 最终回归

实际命令：

```bash
for t in \
  p2-audit/tests/test_paths.py \
  p2-audit/tests/test_exceptions.py \
  p2-audit/tests/test_data_integrity.py \
  p2-audit/tests/test_jev_mock.py \
  p3-audit/tests/test_engine.py \
  p4-audit/tests/test_backtest.py \
  p5-audit/tests/test_p5.py \
  p6-audit/tests/test_p6.py
  p6-audit/tests/test_radar_inventory.py
do
  python3 "$t"
done
```

结果：

| 套件 | 通过 | 失败 |
|---|---:|---:|
| P2 | 19/19 | 0 |
| P3 | 28/28 | 0 |
| P4 | 32/32 | 0 |
| P5 | 36/36 | 0 |
| P6 适配层 | 18/18 | 0 |
| P6 历史雷达清单 | 4/4 | 0 |
| **总计** | **137/137** | **0** |

修正说明：P6 原 5 项测试仍硬编码 bynara 默认配置，与当前 AMD/Clef `.env` 冲突；这是测试基线过期，不是代码回归。已改为验证真实 provider/base/model/key source，并禁用本地 `.env` 后验证 `no_key`。

真实调用验证未计入单元回归，单独记录：JEV 8/8 成功；Search 24/24 成功。其余 JEV 工具及 AMD 长期配额 NOT TESTED。
