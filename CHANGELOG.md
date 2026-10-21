# Changelog

All notable changes to this project will be documented in this file.

> 格式基于 [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)。

## [Unreleased]

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

---
*本项目从 2026-10-21 开始建立 CHANGELOG 纪律。*
