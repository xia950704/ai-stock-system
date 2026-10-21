"""现有数据源的适配器（P3-2 基础设施）。

不修改 data_loader / jev_adapter / search.client 的内部实现，
仅包装它们以满足 DataSource 契约。
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

from .base import DataSource, DataSourceRegistry, SourceHealth

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


class LocalFileDataSource(DataSource):
    """本地 JSON 文件数据源适配器（data_loader）。"""

    @property
    def name(self) -> str:
        return "local_files"

    @property
    def is_available(self) -> bool:
        # data_loader 的数据文件位于 ~/harness/
        data_root = os.path.expanduser(os.environ.get("DATA_ROOT", "~/harness"))
        anchor_path = os.path.join(data_root, "anchor_status.json")
        return os.path.isfile(anchor_path)

    def provider_config(self) -> Dict[str, Any]:
        data_root = os.path.expanduser(os.environ.get("DATA_ROOT", "~/harness"))
        stock_daily = os.path.expanduser(os.environ.get("STOCK_DAILY_DIR", "~/harness/stock_daily"))
        return {
            "data_root": data_root,
            "stock_daily_dir": stock_daily,
            "anchor_exists": os.path.isfile(os.path.join(data_root, "anchor_status.json")),
            "ranking_exists": os.path.isfile(os.path.join(stock_daily, "stock_ranking.json")),
            "portfolio_exists": os.path.isfile(os.path.join(stock_daily, "stock_portfolio_enriched.json")),
        }

    def health_check(self) -> SourceHealth:
        config = self.provider_config()
        missing = [k for k, v in config.items() if k.endswith("_exists") and not v]
        if missing:
            return SourceHealth(
                name=self.name,
                available=False,
                detail=f"缺失数据文件: {[m.replace('_exists', '') for m in missing]}",
                config=config,
                error_code="missing_files",
            )
        return SourceHealth(
            name=self.name,
            available=True,
            detail="锚价/排名/持仓文件均存在",
            config=config,
        )


class JevDataSource(DataSource):
    """JEV MCP / HTTP 数据源适配器（jev_adapter）。"""

    @property
    def name(self) -> str:
        return "jev"

    @property
    def is_available(self) -> bool:
        from engine import jev_adapter
        return jev_adapter._resolve_key() is not None

    def provider_config(self) -> Dict[str, Any]:
        from engine import jev_adapter
        cfg = jev_adapter.provider_config()
        # 不含密钥值
        cfg.pop("key_source", None)
        return cfg

    def health_check(self) -> SourceHealth:
        from engine import jev_adapter
        cfg = self.provider_config()
        key = jev_adapter._resolve_key()
        if key is None:
            return SourceHealth(
                name=self.name,
                available=False,
                detail="未解析到 JEV API key（env JEV_API_KEY/BYNARA_API_KEY 或 key 文件）",
                config=cfg,
                error_code="no_key",
            )
        return SourceHealth(
            name=self.name,
            available=True,
            detail=f"transport={cfg.get('transport')}, model={cfg.get('model')}",
            config=cfg,
        )


class SearchDataSource(DataSource):
    """Search API 数据源适配器（search.client）。"""

    @property
    def name(self) -> str:
        return "search"

    @property
    def is_available(self) -> bool:
        from search import client
        return bool(client.API_KEY) and client.httpx is not None

    def provider_config(self) -> Dict[str, Any]:
        from search import client
        return {
            "base_url": client.BASE_URL,
            "timeout_s": client.TIMEOUT_S,
            "max_retries": client.MAX_RETRIES,
            "httpx_available": client.httpx is not None,
        }

    def health_check(self) -> SourceHealth:
        from search import client
        cfg = self.provider_config()
        if not cfg["httpx_available"]:
            return SourceHealth(
                name=self.name,
                available=False,
                detail="httpx 库不可用",
                config=cfg,
                error_code="no_httpx",
            )
        if not client.API_KEY:
            return SourceHealth(
                name=self.name,
                available=False,
                detail="SEARCH_API_KEY 未配置",
                config=cfg,
                error_code="no_key",
            )
        return SourceHealth(
            name=self.name,
            available=True,
            detail=f"base_url={cfg['base_url']}",
            config=cfg,
        )


def build_default_registry() -> DataSourceRegistry:
    """构建默认注册表，包含三个内置数据源。"""
    registry = DataSourceRegistry()
    registry.register(LocalFileDataSource())
    registry.register(JevDataSource())
    registry.register(SearchDataSource())
    return registry


def get_source(name: str) -> Optional[DataSource]:
    """按名称获取数据源。"""
    return build_default_registry().get(name)


def list_sources() -> List[str]:
    """列出所有内置数据源名称。"""
    return build_default_registry().names()
