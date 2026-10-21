#!/usr/bin/env python3
"""检索证据整理层（P3.5 第 4.5/4.6 节）。

职责：
  - 将 Search API 原始结果整理为结构化 claim 记录
  - 多源交叉验证：去重、来源独立性检查、来源优先级
  - 状态标记：multi_source_confirmed / single_source / unverified / conflict
  - 检索结果属于待验证数据，不直接进入买卖判断

来源优先级（4.5 节）：
  1. 官方披露：交易所公告、上市公司公告（csrc/交易所域名）
  2. 监管与注册机构：cde/cninfo/药品注册相关
  3. 可靠财经媒体：有明确采编来源
  4. 行业资料/研究材料
  5. 社交/论坛/未经证实消息
"""
import hashlib
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlsplit

TZ = timezone(timedelta(hours=8))

# 来源域名 -> 优先级（数字越小越权威）
SOURCE_TIER_RULES = [
    # Observed official issuer domain from the live Search response.
    (re.compile(r"baili-pharm\.com", re.I), 1),
    (re.compile(r"(sse\.com\.cn|szse\.cn|cninfo\.com\.cn|csrc\.gov\.cn|nmpa\.gov\.cn)", re.I), 1),
    (re.compile(r"(cde\.com|pharmcube|chinadrugtrials|fda\.gov|clinicaltrials\.gov)", re.I), 1),
    (re.compile(r"(cls\.cn|yicai|stcn\.com|eastmoney\.com|sina\.com\.cn/finance|10jqka|wallstreetcn|caixin|thepaper|21jingji|xinhuanet|news\.cn)", re.I), 3),
    (re.compile(r"(zhihu|weibo|tieba|guba|baidu\.com)", re.I), 5),
]

# Relay LLM 池作为第二路独立验证通道（tier=2，高于一般财经媒体）
RELAY_VERIFIED_TIER = 2

def source_tier(url: Optional[str]) -> int:
    """根据 URL 域名估计来源优先级（1-5）。"""
    if not url:
        return 4
    for pattern, tier in SOURCE_TIER_RULES:
        if pattern.search(url):
            return tier
    return 4  # 未知来源默认第 4 级（行业资料/研究材料）

def _url_key(url: Optional[str]) -> str:
    """URL 归一化用于转载去重（去 query/fragment/尾斜杠/协议）。"""
    if not url:
        return ""
    raw = url.strip()
    parsed = urlsplit(raw if "://" in raw else "//" + raw)
    host = (parsed.hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    path = unquote(parsed.path or "").lower()
    path = re.sub(r"/{2,}", "/", path).rstrip("/")
    if not host and not path:
        return re.sub(r"[?#].*$", "", raw.lower()).rstrip("/")
    return host + path

def _domain(url: Optional[str]) -> str:
    if not url:
        return ""
    raw = url.strip()
    parsed = urlsplit(raw if "://" in raw else "//" + raw)
    host = unquote(parsed.hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    # Preserve registrable domains under common second-level suffixes.
    if len(parts) >= 3 and parts[-2] in {
        "ac", "co", "com", "edu", "gov", "net", "org"
    }:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host

def claim_id_for(claim: str) -> str:
    """为一条事实/命题生成稳定 ID。"""
    return "clm-" + hashlib.sha1(claim.strip().lower().encode("utf-8")).hexdigest()[:12]

def make_claim(claim_text: str, stock_code: Optional[str] = None,
               facet: str = "general") -> Dict[str, Any]:
    """创建待验证 claim 记录。"""
    return {
        "claim_id": claim_id_for(claim_text),
        "claim": claim_text,
        "stock_code": stock_code,
        "facet": facet,  # rd(研发面) / order(订单面) / event(事件) / market(大盘) / general
        "status": "unverified",
        "sources": [],
        "verified_at": None,
        "notes": [],
    }

def add_source(claim: Dict[str, Any], result: Dict[str, Any],
               accessed_at: Optional[str] = None) -> None:
    """将一条检索结果登记到 claim 上。
    
    去重规则（4.5 节）：
      - 同一 URL 的转载不重复计权
      - 同一域名的第二条结果标记为同域，不算独立来源
    """
    url = result.get("url") or ""
    title = result.get("title") or ""
    # Live relay results use `content`; legacy/mock fixtures use `snippet`.
    snippet = result.get("snippet") or result.get("content") or ""
    # Relay verified sources use explicit tier and synthetic domain
    if result.get("type") == "relay_verified":
        domain = "relay"
        tier = result.get("tier", RELAY_VERIFIED_TIER)
        url_key = f"relay:{result.get('model', 'unknown')}:{result.get('timestamp', '')}"
    else:
        domain = _domain(url)
        tier = source_tier(url)
        url_key = _url_key(url)
    published = result.get("published_at") or result.get("date") or None

    for s in claim["sources"]:
        if s.get("url_key") == url_key and url_key:
            s["duplicate_count"] = s.get("duplicate_count", 1) + 1
            return
        # 同域名同标题：视为转载
        if domain and s.get("domain") == domain and s.get("title") == title:
            s["duplicate_count"] = s.get("duplicate_count", 1) + 1
            return

    claim["sources"].append({
        "title": title,
        "url": url,
        "url_key": url_key,
        "domain": domain,
        "tier": tier,
        "published_at": published,
        "snippet": snippet[:300],
        "accessed_at": accessed_at or datetime.now(TZ).isoformat(),
        "duplicate_count": 1,
        "type": result.get("type", "web"),
    })

def independent_sources(claim: Dict[str, Any]) -> int:
    """独立来源数：不同域名且 tier<=3 的来源 + relay_verified 来源。"""
    domains = set()
    relay_count = 0
    for s in claim["sources"]:
        if s.get("type") == "relay_verified":
            relay_count += 1
        if s.get("domain") and s["tier"] <= 3:
            domains.add(s["domain"])
    return len(domains) + relay_count

def best_source_tier(claim: Dict[str, Any]) -> Optional[int]:
    """最优来源优先级（最小 tier）。"""
    tiers = [s["tier"] for s in claim["sources"]]
    return min(tiers) if tiers else None

def verify_claim(claim: Dict[str, Any]) -> Dict[str, Any]:
    """对 claim 执行验证状态判定。
    
    规则（4.5 节）：
      - >=2 个独立来源且最优 tier<=3 -> multi_source_confirmed
      - 仅 1 个独立来源 -> single_source
      - 来源之间存在明显冲突（snippet 层面无法自动判定，保留 conflict 人工标记）
      - 无来源或仅 tier>=4 -> unverified
      - 摘要-only 且无可访问原始来源 -> unverified（摘要只是线索）
    """
    n_indep = independent_sources(claim)
    best = best_source_tier(claim)

    if n_indep >= 2 and best is not None and best <= 3:
        claim["status"] = "multi_source_confirmed"
    elif n_indep == 1:
        claim["status"] = "single_source"
    elif claim["sources"]:
        claim["status"] = "unverified"
    else:
        claim["status"] = "unverified"

    claim["verified_at"] = datetime.now(TZ).isoformat()
    return claim

def summarize(claims: List[Dict[str, Any]]) -> Dict[str, Any]:
    """汇总验证状态，供报告使用。"""
    by_status: Dict[str, int] = {}
    for c in claims:
        by_status[c["status"]] = by_status.get(c["status"], 0) + 1
    return {
        "total": len(claims),
        "by_status": by_status,
        "claims": claims,
    }

def sanitize_for_report(claim: Dict[str, Any]) -> Dict[str, Any]:
    """报告用精简结构（脱敏、限量）。"""
    return {
        "claim_id": claim["claim_id"],
        "claim": claim["claim"],
        "status": claim["status"],
        "independent_sources": independent_sources(claim),
        "best_tier": best_source_tier(claim),
        "top_sources": [
            {"title": s["title"], "url": s["url"], "domain": s["domain"],
             "tier": s["tier"], "published_at": s.get("published_at")}
            for s in sorted(claim["sources"], key=lambda x: x["tier"])[:3]
        ],
    }

# ---- 自测 ----
if __name__ == "__main__":
    import sys
    c = make_claim("测试命题", stock_code="sh600276", facet="rd")
    add_source(c, {"title": "公告", "url": "https://static.sse.com.cn/x.pdf", "snippet": "s1"})
    add_source(c, {"title": "公告转载", "url": "https://static.sse.com.cn/x.pdf?from=weixin", "snippet": "s1"})
    add_source(c, {"title": "媒体", "url": "https://www.cls.cn/a/123", "snippet": "s2"})
    verify_claim(c)
    print("status:", c["status"], "indep:", independent_sources(c))
    print("summary:", summarize([c])["by_status"])
    sys.exit(0)
