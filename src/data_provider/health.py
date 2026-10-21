"""健康检查入口（P3-2 基础设施）。

提供：
  - run_health_check() : 对所有内置数据源执行健康检查
  - format_health_report() : 将 HealthReport 格式化为人类可读字符串
"""
from __future__ import annotations

from typing import Optional

from .base import HealthReport, DataSourceRegistry


def _build_registry() -> DataSourceRegistry:
    """构建默认注册表，包含三个内置数据源。

    注意：此处使用延迟导入，避免循环依赖。
    """
    from .adapters import build_default_registry
    return build_default_registry()


_default_registry: Optional[DataSourceRegistry] = None


def get_registry() -> DataSourceRegistry:
    """获取默认注册表（单例）。"""
    global _default_registry
    if _default_registry is None:
        _default_registry = _build_registry()
    return _default_registry


def run_health_check(registry: Optional[DataSourceRegistry] = None) -> HealthReport:
    """对所有数据源执行健康检查。

    Args:
        registry: 默认为 None（使用内置注册表），也可传入自定义注册表。

    Returns:
        HealthReport: 包含所有数据源的健康状态。
    """
    reg = registry if registry is not None else get_registry()
    return reg.health_check_all()


def format_health_report(report: HealthReport) -> str:
    """将 HealthReport 格式化为人类可读字符串。"""
    lines = [
        f"=== 数据源健康检查 ({report.check_time}) ===",
        f"可用: {sum(1 for s in report.sources if s.available)}/{len(report.sources)}",
        "",
    ]
    for s in report.sources:
        status = "OK " if s.available else "ERR"
        lines.append(f"  [{status}] {s.name}")
        if s.detail:
            lines.append(f"         {s.detail}")
        if s.error_code:
            lines.append(f"         error_code={s.error_code}")
    lines.append("")
    if report.all_available:
        lines.append("结论: 所有数据源可用")
    else:
        lines.append(f"结论: {len(report.unavailable_source_names())} 个数据源不可用 "
                     f"({', '.join(report.unavailable_source_names())})")
    return "\n".join(lines)
