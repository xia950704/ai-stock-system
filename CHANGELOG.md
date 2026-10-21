# Changelog

All notable changes to this project will be documented in this file.

> 格式基于 [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)。

## [Unreleased]

- 新增 `scripts/daily_positions_snapshot.py`：每日持仓快照归档脚本
- 改进 `src/engine/trading_day.py`：新增中国 A 股静态节假日表（2026-2027），`trading_day_status()` 支持节假日判断
- 改进 `src/search/evidence.py`：新增 `RELAY_VERIFIED_TIER=2`，relay LLM 池作为第二路独立验证通道
- 改进 `src/search/probe.py`：新增 `relay_verify_claim()` 函数，每条 claim 经 relay 池交叉验证
- 改进 `scripts/daily_commit_bot.py`：去掉 mock 模式，改为真实 JEV + Search API 调用，串入持仓快照脚本
- 新增 `src/data_provider/` 统一数据源抽象层（DataSource ABC + Registry + 健康检查）
- 新增 `AGENTS.md` 开发治理规范
- 新增 `requirements.txt` 依赖管理
- 改进 `daily_judge.py` 启动时增加数据源健康检查步骤

## [2026-10-21] — data_provider 基础设施

### 新功能

- `src/data_provider/base.py`：DataSource 抽象基类 + DataSourceRegistry
- `src/data_provider/adapters.py`：data_loader / jev_adapter / search.client 三个适配器
- `src/data_provider/health.py`：统一健康检查入口

### 改进

- `daily_judge.py`：启动时输出三个数据源的健康状态
- `AGENTS.md`：建立开发治理规范
- `requirements.txt`：锁定核心依赖版本

## [2026-10-21] — 全自动整改

### 新功能

- `scripts/daily_positions_snapshot.py`：持仓每日归档，幂等
- `src/search/probe.py`：`relay_verify_claim()` — relay LLM 池作为第二路独立证据通道

### 改进

- `src/engine/trading_day.py`：中国 A 股静态节假日表（2026-2027），节假日正确识别为 NON_TRADING_DAY
- `src/search/evidence.py`：`RELAY_VERIFIED_TIER=2`，`add_source()` 和 `independent_sources()` 支持 relay_verified 源类型
- `scripts/daily_commit_bot.py`：真实模式运行（去掉 `--mock-jev`/`--mock-search`），串入持仓快照

---
*本项目从 2026-10-21 开始建立 CHANGELOG 纪律。*
