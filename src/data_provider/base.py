"""数据提供者抽象基类与注册表（P3-2 基础设施）。

设计原则：
  - 不修改现有模块（data_loader / jev_adapter / search.client）的内部实现
  - 通过适配器模式将现有模块纳入统一契约
  - 抽象级别恰到好处：只定义健康检查与元信息契约，不涉及具体数据格式
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

TZ = timezone(timedelta(hours=8))


@dataclass
class SourceHealth:
    """单个数据源的健康状态。"""

    name: str
    available: bool
    detail: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
    last_check: str = field(default_factory=lambda: datetime.now(TZ).isoformat())
    error_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "detail": self.detail,
            "config": self.config,
            "last_check": self.last_check,
            "error_code": self.error_code,
        }


@dataclass
class HealthReport:
    """所有数据源的健康检查报告。"""

    check_time: str = field(default_factory=lambda: datetime.now(TZ).isoformat())
    sources: List[SourceHealth] = field(default_factory=list)
    all_available: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_time": self.check_time,
            "sources": [s.to_dict() for s in self.sources],
            "all_available": self.all_available,
            "available_count": sum(1 for s in self.sources if s.available),
            "total_count": len(self.sources),
        }

    def available_source_names(self) -> List[str]:
        return [s.name for s in self.sources if s.available]

    def unavailable_source_names(self) -> List[str]:
        return [s.name for s in self.sources if not s.available]


class DataSource(ABC):
    """数据提供者抽象基类。

    子类需要实现：
      - name          : 数据源标识
      - is_available  : 是否可用
      - health_check  : 返回 SourceHealth

    推荐但不强制：
      - provider_config : 返回诊断用的配置快照（不含密钥）
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """数据源唯一标识。"""

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """数据源当前是否可用。"""

    @abstractmethod
    def health_check(self) -> SourceHealth:
        """执行健康检查，返回 SourceHealth。"""

    def provider_config(self) -> Dict[str, Any]:
        """返回诊断用的配置快照（不含密钥值）。"""
        return {}

    def failure_status(self) -> str:
        """返回失败状态标签。"""
        if self.is_available:
            return "ok"
        return "unavailable"


class DataSourceRegistry:
    """数据源注册表：管理多个 DataSource，提供批量健康检查。"""

    def __init__(self, sources: Optional[List[DataSource]] = None):
        self._sources: List[DataSource] = list(sources) if sources else []

    def register(self, source: DataSource) -> None:
        """注册一个数据源。"""
        self._sources.append(source)

    @property
    def sources(self) -> List[DataSource]:
        return list(self._sources)

    def names(self) -> List[str]:
        return [s.name for s in self._sources]

    def get(self, name: str) -> Optional[DataSource]:
        for s in self._sources:
            if s.name == name:
                return s
        return None

    def health_check_all(self) -> HealthReport:
        """对所有数据源执行健康检查。"""
        report = HealthReport()
        for source in self._sources:
            try:
                health = source.health_check()
            except Exception as e:
                health = SourceHealth(
                    name=source.name,
                    available=False,
                    detail=f"health_check raised: {e}",
                    error_code="exception",
                )
            report.sources.append(health)
        report.all_available = all(s.available for s in report.sources) and len(report.sources) > 0
        return report

    def available_sources(self) -> List[str]:
        return [s.name for s in self._sources if s.is_available]

    def all_unavailable(self) -> bool:
        """所有数据源均不可用。"""
        return len(self._sources) > 0 and all(not s.is_available for s in self._sources)
