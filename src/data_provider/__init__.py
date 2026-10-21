"""数据提供者统一抽象层（P3-2 基础设施）。

职责：
1. 定义 DataSource 抽象基类，统一三个数据源的契约
2. 管理多个数据源的注册与健康检查
3. 不修改任何现有模块的内部实现，仅提供横切面的统一视图

设计动机：
  当前系统有三个独立数据源，各自维护配置加载、错误分类、
  可用性判断和日志记录，彼此完全平行：
  - src/engine/data_loader.py    ：本地 JSON 文件（锚价/排名/持仓/实时价）
  - src/engine/jev_adapter.py    ：JEV MCP / HTTP（AI 判断）
  - src/search/client.py         ：Search API（新闻/证据搜索）

  本模块不替代它们，而是提供统一的健康检查入口和契约约束，
  为后续的 fallback / 熔断 / 多源切换打基础。
"""
from .base import DataSource, DataSourceRegistry, HealthReport, SourceHealth
from .health import run_health_check, format_health_report, get_registry

__all__ = [
    "DataSource",
    "DataSourceRegistry",
    "HealthReport",
    "SourceHealth",
    "run_health_check",
    "format_health_report",
    "get_registry",
]
