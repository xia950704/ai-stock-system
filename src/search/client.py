#!/usr/bin/env python3
"""Search API 客户端（P3.5）。

功能：
  - 从环境变量加载 Base URL 和 API Key
  - POST 请求 /v1/search 端点
  - 超时、重试、限流控制
  - 错误分类与 Mock 测试支持
  - 日志脱敏（不打印 API Key）

配置：
  - SEARCH_API_BASE_URL: 默认 http://127.0.0.1:31415/v1/search
  - SEARCH_API_KEY: 必需
  - SEARCH_API_TIMEOUT: 默认 30 秒
  - SEARCH_API_MAX_RETRIES: 默认 2 次
"""
import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

try:
    import httpx
except ImportError:
    httpx = None

# ---- 配置 ----
BASE_URL = os.environ.get("SEARCH_API_BASE_URL", "http://127.0.0.1:31415/v1/search")
API_KEY = os.environ.get("SEARCH_API_KEY", "")


def _load_dotenv() -> None:
    """从 Workspace 根目录的 `.env` 加载配置（仅当环境变量未设置时）。

    不安装第三方依赖，使用最小解析器。密钥只写入进程环境变量，
    不打印、不写入日志。
    """
    candidates = [
        os.environ.get("SEARCH_API_CONFIG_FILE"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"),
    ]
    for path in candidates:
        if not path or not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and k in {
                        "SEARCH_API_BASE_URL", "SEARCH_API_KEY", "SEARCH_API_TIMEOUT",
                        "SEARCH_API_MAX_RETRIES", "SEARCH_LOG_DIR",
                    } and not os.environ.get(k):
                        os.environ[k] = v
        except OSError:
            pass
        break  # 只读取第一个存在的文件


_load_dotenv()

# 重新读取可能由 `.env` 设置的变量
BASE_URL = os.environ.get("SEARCH_API_BASE_URL", "http://127.0.0.1:31415/v1/search")
API_KEY = os.environ.get("SEARCH_API_KEY", "")
TIMEOUT_S = float(os.environ.get("SEARCH_API_TIMEOUT", "30"))
MAX_RETRIES = int(os.environ.get("SEARCH_API_MAX_RETRIES", "2"))
LOG_DIR = os.path.expanduser(os.environ.get("SEARCH_LOG_DIR", "~/harness/logs/search"))

# ---- 错误分类 ----
def _classify_error(http_status: Optional[int], detail: str) -> str:
    """HTTP 错误分类。"""
    if http_status is None:
        return "transport"
    if http_status == 401:
        return "auth"
    if http_status == 403:
        return "forbidden"
    if http_status == 404:
        return "not_found"
    if http_status == 400:
        if "no search key" in detail.lower():
            return "no_provider_key"
        return "bad_request"
    if http_status == 429:
        return "rate_limited"
    if 500 <= http_status < 600:
        return "server_error"
    return "unknown"

def _log_call(record: Dict[str, Any]) -> None:
    """日志记录（脱敏）。"""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        log_file = os.path.join(LOG_DIR, "search_calls.jsonl")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass

def search(query: str, limit: int = 5, provider: Optional[str] = None,
           use_mock: bool = False, mock_results: Optional[List[Dict]] = None) -> Dict[str, Any]:
    """执行搜索。
    
    Args:
        query: 搜索查询
        limit: 返回结果数量（默认 5）
        provider: 搜索提供者（Tavily/Exa/Firecrawl/Linkup/parallel）
        use_mock: 是否使用 Mock 模式
        mock_results: Mock 返回结果
    
    Returns:
        {"ok": True, "results": [...], "query": ..., "provider": ...}
        或 {"ok": False, "error_code": ..., "error_message": ...}
    """
    call_id = datetime.now().strftime("%Y%m%d%H%M%S")
    ts = datetime.now(timezone(timedelta(hours=8))).isoformat()
    
    # Mock 模式
    if use_mock:
        rec = {
            "call_id": call_id, "ts": ts, "mode": "mock",
            "query": query, "limit": limit, "provider": provider,
            "result_count": len(mock_results) if mock_results else 0,
        }
        _log_call(rec)
        if mock_results is None:
            return {"ok": False, "error_code": "mock_empty", "error_message": "Mock returned None"}
        return {"ok": True, "results": mock_results, "query": query, "provider": provider or "mock"}
    
    # 配置检查
    if not API_KEY:
        rec = {"call_id": call_id, "ts": ts, "mode": "real", "query": query,
               "error_code": "no_key", "error_message": "SEARCH_API_KEY not configured"}
        _log_call(rec)
        return {"ok": False, "error_code": "no_key",
                "error_message": "Search API key not configured (set SEARCH_API_KEY env var)"}
    
    if httpx is None:
        rec = {"call_id": call_id, "ts": ts, "mode": "real", "query": query,
               "error_code": "no_httpx", "error_message": "httpx not installed"}
        _log_call(rec)
        return {"ok": False, "error_code": "no_httpx", "error_message": "httpx library unavailable"}
    
    # 构建请求
    payload = {"query": query, "limit": limit}
    if provider:
        payload["provider"] = provider
    
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    url = BASE_URL
    
    # 重试逻辑
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        start = time.time()
        try:
            with httpx.Client(timeout=TIMEOUT_S) as client:
                r = client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException:
            last_error = {"error_code": "timeout", "error_message": f"Timeout after {TIMEOUT_S}s"}
            continue
        except httpx.HTTPError as e:
            last_error = {"error_code": "transport", "error_message": str(e)}
            continue
        
        elapsed = round(time.time() - start, 2)
        
        # 错误处理
        if r.status_code != 200:
            detail = r.text[:500] if r.text else ""
            code = _classify_error(r.status_code, detail)
            last_error = {"error_code": code, "http_status": r.status_code, "error_message": detail}
            if code in ("rate_limited", "server_error") and attempt < MAX_RETRIES:
                time.sleep(1.0 * (attempt + 1))  # 指数退避
                continue
            break
        
        # 成功解析
        try:
            data = r.json()
        except Exception as e:
            last_error = {"error_code": "parse_error", "error_message": f"Invalid JSON: {e}"}
            break
        
        # 验证返回结构
        if not isinstance(data, dict):
            last_error = {"error_code": "parse_error", "error_message": "Response is not an object"}
            break
        
        # 检查错误字段
        if "error" in data:
            err = data["error"]
            code = err.get("code", "unknown") if isinstance(err, dict) else "unknown"
            msg = err.get("message", "Unknown error") if isinstance(err, dict) else str(err)
            last_error = {"error_code": code, "error_message": msg}
            break
        
        # 成功返回
        results = data.get("results", data.get("data", []))
        rec = {
            "call_id": call_id, "ts": ts, "mode": "real",
            "query": query, "limit": limit, "provider": provider,
            "elapsed_s": elapsed, "result_count": len(results),
        }
        _log_call(rec)
        return {"ok": True, "results": results, "query": query, "provider": provider, "elapsed_s": elapsed}
    
    # 所有重试失败
    rec = {
        "call_id": call_id, "ts": ts, "mode": "real",
        "query": query, "limit": limit, "attempts": attempt + 1,
        "error_code": last_error.get("error_code", "unknown") if last_error else "unknown",
    }
    _log_call(rec)
    return {"ok": False, **(last_error or {"error_code": "unknown", "error_message": "Unknown failure"})}

def is_available(result: Dict[str, Any]) -> bool:
    """判断搜索是否成功返回结果。"""
    return result.get("ok") is True and len(result.get("results", [])) > 0

def failure_status(result: Dict[str, Any]) -> str:
    """返回失败状态标签。"""
    if result.get("ok"):
        return "ok"
    return result.get("error_code", "unknown")

# ---- 自测 ----
if __name__ == "__main__":
    import sys
    print("Testing Search API client...")
    
    # Mock 测试
    r = search("test query", limit=3, use_mock=True,
               mock_results=[{"title": "Test", "url": "http://example.com", "snippet": "Test snippet"}])
    print(f"Mock OK: {r.get('ok')}, count={len(r.get('results', []))}")
    
    # 无 Key 测试
    os.environ["SEARCH_API_KEY"] = ""
    r = search("test", use_mock=False)
    print(f"No key: {r.get('error_code')}")
    
    print("Done.")
    sys.exit(0)
