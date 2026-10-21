#!/usr/bin/env python3
"""每日研判的外部证据探查层（P3.5）。

职责：
  - 为 P0 池各标的生成研发面/订单面/事件类检索查询
  - 调用 search.client 执行检索（真实或 Mock）
  - 将结果整理为 evidence.claim 记录
  - 输出结构化探查结果供 engine/stock_judge 使用
  - Search API 不可用时返回明确的降级状态，不伪造结果

安全约束：
  - 查询内容不含持仓、成本价等敏感信息（仅股票代码与名称）
  - 检索结果属于待验证数据，不直接参与行动建议
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "search"))
from client import search, failure_status, is_available
from evidence import make_claim, add_source, verify_claim, sanitize_for_report, summarize

TZ = timezone(timedelta(hours=8))

# 每只股票每个 facet 一个查询（只含代码与名称，不含持仓/成本）
def build_queries(stock: Dict[str, str]) -> List[Dict[str, str]]:
    name, code = stock["name"], stock["code"]
    num = code.replace("sh", "").replace("sz", "").replace("hk", "")
    return [
        {"facet": "rd", "query": f"{name} {num} 临床试验 最新进展 公告"},
        {"facet": "order", "query": f"{name} {num} 业绩 销售 订单 公告"},
        {"facet": "event", "query": f"{name} {num} 最新公告 监管 审批"},
    ]

def probe_stock(stock: Dict[str, str], use_mock: bool = False,
                mock_results: Optional[List[Dict]] = None,
                max_queries: int = 3) -> Dict[str, Any]:
    """对单只股票执行外部证据探查。

    Returns:
        {
          "code", "name", "available": bool, "status": "ok|<error_code>",
          "claims": [...], "summary": {...}, "queries_executed": n, "notes": [...]
        }
    """
    code, name = stock["code"], stock["name"]
    claims: List[Dict[str, Any]] = []
    notes: List[str] = []
    queries_executed = 0
    status = "ok"

    for i, q in enumerate(build_queries(stock)[:max_queries]):
        facet, query = q["facet"], q["query"]
        # 每条查询使用 mock_results 的不同子集（避免所有查询返回相同结果）
        mock_for_q = mock_results
        if mock_results and len(mock_results) > 0:
            mock_for_q = [mock_results[i % len(mock_results)]]
        r = search(query, limit=5, use_mock=use_mock, mock_results=mock_for_q)
        queries_executed += 1

        if not r.get("ok"):
            status = failure_status(r)
            notes.append(f"[{facet}] 搜索失败: {status} - {r.get('error_message', '')[:120]}")
            # 继续尝试其他查询（不同 facet 可能命中不同缓存/路由），但不无限重试
            continue

        results = r.get("results", [])
        if not results:
            notes.append(f"[{facet}] 搜索返回空结果")
            continue

        # 每条结果 -> 一条 claim（标题即待核验命题）
        for res in results:
            title = res.get("title") or ""
            if not title:
                continue
            c = make_claim(title, stock_code=code, facet=facet)
            add_source(c, res)
            verify_claim(c)
            claims.append(c)

    if status != "ok":
        notes.insert(0, f"Search API 状态: {status}（结果仅为部分/待验证数据，不构成已核实事实）")

    return {
        "code": code,
        "name": name,
        "available": status == "ok" and len(claims) > 0,
        "status": status,
        "queries_executed": queries_executed,
        "claims": claims,
        "summary": summarize(claims),
        "notes": notes,
    }

DEFAULT_MOCK_RESULTS = [
    {"title": "公司发布最新公告", "url": "https://www.cls.cn/a/1", "snippet": "mock 检索结果（仅供测试）",
     "published_at": "2026-10-19"},
    {"title": "NMPA 受理新适应证申请", "url": "https://www.sse.com.cn/a/2", "snippet": "mock 检索结果（仅供测试）",
     "published_at": "2026-10-18"},
    {"title": "三季报披露", "url": "https://www.cninfo.com.cn/a/3", "snippet": "mock 检索结果（仅供测试）",
     "published_at": "2026-10-17"},
]

def probe_pool(stocks: List[Dict[str, str]], use_mock: bool = False,
               mock_results: Optional[List[Dict]] = None,
               max_queries: int = 3) -> Dict[str, Any]:
    """对整个池执行探查。"""
    if use_mock and not mock_results:
        mock_results = DEFAULT_MOCK_RESULTS
    results = {s["code"]: probe_stock(s, use_mock=use_mock,
                                      mock_results=mock_results,
                                      max_queries=max_queries)
               for s in stocks}
    # 池级状态：任一查询失败即降级
    overall = "ok"
    for r in results.values():
        if r["status"] != "ok":
            overall = r["status"]
            break
    return {
        "status": overall,
        "stocks": results,
        "generated_at": datetime.now(TZ).isoformat(),
    }

# ---- 自测（Mock） ----
if __name__ == "__main__":
    mock = [
        {"title": "某药获 NMPA 受理", "url": "https://www.cls.cn/a/1", "snippet": "s"},
        {"title": "某药获 NMPA 受理（转载）", "url": "https://static.sse.com.cn/1.pdf", "snippet": "s"},
        {"title": "三季报披露", "url": "https://www.cls.cn/a/2", "snippet": "s"},
    ]
    stock = {"code": "sh600276", "name": "恒瑞医药"}
    out = probe_stock(stock, use_mock=True, mock_results=mock)
    print("status:", out["status"], "claims:", len(out["claims"]))
    for c in out["claims"][:2]:
        s = sanitize_for_report(c)
        print(" -", s["status"], s["claim"][:30])
    sys.exit(0)
