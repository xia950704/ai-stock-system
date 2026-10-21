# Changelog

All notable changes to this project will be documented in this file.

> 格式基于 [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)。

## [Unreleased]

- 新增 src/stock_codes.py：集中式股票代码注册表（P0=7, P2=1, HK=3, ETF=32, LEGACY=36），所有模块统一引用
- 新增 src/decision/adapter.py：AMD Decision Model 适配层（Clef / d3 / d3-flash，endpoint=/v1/systemone）
- 新增 src/decision/registry.json：注册 3 个 AMD 决策模型（Clef primary, d3, d3-flash fallback）
- 改进 src/engine/daily_judge.py：新增 --decision-model CLI 开关，第 5.25 步调用 AMD Decision Model
- 改进 src/engine/report.py：新增 C2 节展示 AMD Decision Model 个股判断
- 改进 src/engine/daily_judge.py：股票池引用从 data_loader 迁移到 stock_codes（唯一真源）
- 改进 src/decision/adapter.py：429 速率限制指数退避（4s/8s/12s/16s/20s），最多 5 次重试
- 改进 .env：新增 AMD_API_KEY / AMD_API_BASE / AMD_DECISION_MODEL 配置
- 安装 @tencent-qqmail/agently-cli：Agent Mail CLI 已授权（xiahshuang@agent.qq.com）

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
