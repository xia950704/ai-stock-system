#!/usr/bin/env python3
"""P5 回归测试（离线，不触发真实 JEV / 真实网络）。

覆盖：Search 真实返回结构兼容、URL 去重、来源分级与独立性、
JEV 请求契约与错误分类、历史数据缺失、新鲜度门槛、
重复输出保护与显式输出冲突保护。
"""
import os
import sys
import tempfile
from pathlib import Path

WS = Path("/Users/xiashuang/AI-股票系统")
sys.path.insert(0, str(WS / "src"))

# 测试期把 Search 调用日志与 JEV 调用日志重定向到 scratch，不污染本机日志。
os.environ["SEARCH_LOG_DIR"] = str(WS / "scratch" / "search_logs")
os.environ["JEV_LOG_DIR"] = str(WS / "scratch" / "jev_logs")
os.environ["SEARCH_API_KEY"] = ""
os.environ["SEARCH_API_BASE_URL"] = "http://127.0.0.1:9/v1/search"
os.environ["SEARCH_API_TIMEOUT"] = "0.1"
os.environ["SEARCH_API_MAX_RETRIES"] = "0"

PASS = 0
FAIL = 0

def check(tid, desc, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[PASS] {tid} {desc}")
    else:
        FAIL += 1
        print(f"[FAIL] {tid} {desc} | {detail}")

from search import evidence, client
from engine import jev_adapter, trading_day, report
from backtest import provenance

# ---------------- Search 真实返回结构兼容 ----------------

def test_content_fallback():
    c = evidence.make_claim("test", facet="rd")
    evidence.add_source(c, {"title": "t", "url": "https://www.cls.cn/a/1",
                            "content": "real body"})
    check("T-S01", "真实返回 content 被保留（fallback 到 snippet）",
          c["sources"][0]["snippet"] == "real body")

def test_no_published_date():
    c = evidence.make_claim("test")
    evidence.add_source(c, {"title": "t", "url": "https://www.cls.cn/a/1",
                            "content": "2026-10-20 发布"})
    check("T-S02", "API 未提供 published_at 时保持 None，不从正文推断日期",
          c["sources"][0]["published_at"] is None)
    check("T-S02b", "accessed_at 正确填充",
          bool(c["sources"][0].get("accessed_at")))

def test_url_dedupe_encoded():
    c = evidence.make_claim("test")
    evidence.add_source(c, {"title": "t", "url": "https://finance.yahoo.com/quote/688506.SS%2F"})
    evidence.add_source(c, {"title": "t", "url": "https://finance.yahoo.com/quote/688506.SS/"})
    check("T-S03", "百分号编码与未编码 URL 归一化后视为同一来源",
          len(c["sources"]) == 1 and c["sources"][0].get("duplicate_count", 1) >= 2)

def test_official_issuer_tier():
    check("T-S04", "官方发行人域名 baili-pharm.com 归为 tier 1",
          evidence.source_tier("https://www.baili-pharm.com/news/1") == 1)

def test_multi_source_confirmed():
    c = evidence.make_claim("test")
    evidence.add_source(c, {"title": "t1", "url": "https://www.baili-pharm.com/news/1"})
    evidence.add_source(c, {"title": "t2", "url": "https://www.cninfo.com.cn/a/2"})
    evidence.verify_claim(c)
    check("T-S05", "两个独立官方来源 -> multi_source_confirmed",
          c["status"] == "multi_source_confirmed" and evidence.independent_sources(c) == 2)

def test_same_domain_not_independent():
    c = evidence.make_claim("test")
    evidence.add_source(c, {"title": "t1", "url": "https://www.baili-pharm.com/a"})
    evidence.add_source(c, {"title": "t2", "url": "https://baili-pharm.com/b"})
    evidence.verify_claim(c)
    check("T-S06", "同一发行人域名不同 URL 只算 1 个独立来源（转载不重复计权）",
          evidence.independent_sources(c) == 1 and c["status"] == "single_source")

def test_second_level_public_suffix_domains():
    check("S06b", "sse.com.cn 与 cninfo.com.cn 不被误合并为 com.cn",
          evidence._domain("https://www.sse.com.cn/a") == "sse.com.cn" and
          evidence._domain("https://www.cninfo.com.cn/a") == "cninfo.com.cn")
    c = evidence.make_claim("test")
    evidence.add_source(c, {"title": "exchange", "url": "https://www.sse.com.cn/a"})
    evidence.add_source(c, {"title": "exchange mirror", "url": "https://static.sse.com.cn/b"})
    check("S06c", "同一 sse.com.cn 仍只计为 1 个独立来源",
          evidence.independent_sources(c) == 1)

# ---------------- Search API 错误分类 ----------------

def test_search_no_key():
    import os, importlib, tempfile
    saved_key = os.environ.get("SEARCH_API_KEY")
    saved_url = os.environ.get("SEARCH_API_BASE_URL")
    tmp = tempfile.NamedTemporaryFile("w", suffix=".env", delete=False)
    tmp.write("# empty\n")
    tmp.close()
    try:
        os.environ.pop("SEARCH_API_KEY", None)
        os.environ["SEARCH_API_CONFIG_FILE"] = tmp.name
        importlib.reload(client)
        r = client.search("test", use_mock=False)
        check("T-S07", "未配置 SEARCH_API_KEY 返回 no_key",
              r.get("ok") is False and r.get("error_code") == "no_key")
    finally:
        os.unlink(tmp.name)
        os.environ.pop("SEARCH_API_CONFIG_FILE", None)
        if saved_key is None:
            os.environ.pop("SEARCH_API_KEY", None)
        else:
            os.environ["SEARCH_API_KEY"] = saved_key
        if saved_url is None:
            os.environ.pop("SEARCH_API_BASE_URL", None)
        else:
            os.environ["SEARCH_API_BASE_URL"] = saved_url
        importlib.reload(client)

def test_search_error_codes():
    check("T-S08", "401 -> auth", client._classify_error(401, "") == "auth")
    check("T-S08b", "429 -> rate_limited", client._classify_error(429, "") == "rate_limited")
    check("T-S08c", "500 -> server_error", client._classify_error(500, "") == "server_error")
    check("T-S08d", "400 no key -> no_provider_key",
          client._classify_error(400, "no search key configured") == "no_provider_key")

def test_search_timeout_static():
    txt = (WS / "src/search/client.py").read_text(encoding="utf-8")
    check("T-S09", "Search 客户端处理 httpx.TimeoutException",
          "httpx.TimeoutException" in txt)

# ---------------- JEV 请求契约 ----------------

def test_jev_noul_schema():
    r = jev_adapter.jev_yes_no({"x": 1}, "1 < 2", mode="noul", use_mock=True,
                                mock_response={"ok": True, "model": "mock",
                                               "answers": {"answer": {"noul": 0.99}}})
    req = r["request"]
    check("T-J01", "noul 请求含 model/state/questions",
          set(req.keys()) == {"model", "state", "questions"})
    q = req["questions"]["answer"]
    check("T-J01b", "noul 题型含 instructions",
          q.get("type") == "noul" and q.get("instructions") == "1 < 2")

def test_jev_choice_schema():
    r = jev_adapter.jev_yes_no({"x": 1}, "1 < 2", use_mock=True,
                                mock_response={"ok": True, "model": "mock",
                                               "answers": {"answer": {"type": "choice",
                                                                      "choice": "yes", "confidence": 0.9}}})
    q = r["request"]["questions"]["answer"]
    check("T-J02", "choice 题型补齐 instructions 字段",
          q.get("type") == "choice" and q.get("instructions") == "1 < 2" and "criteria" in q)

def test_jev_route_schema():
    r = jev_adapter.jev_route("翻译一段文字", use_mock=True,
                              mock_response={"ok": True, "model": "mock",
                                             "answers": {"route": {"type": "choice", "choice": "light"}}})
    q = r["request"]["questions"]["route"]
    check("T-J03", "route 题型含 instructions 与 criteria",
          q.get("type") == "choice" and q.get("instructions") and "criteria" in q)

def test_jev_error_classification():
    check("T-J04", "401 -> auth", jev_adapter._classify_error(401, "") == "auth")
    check("T-J04b", "402 -> insufficient", jev_adapter._classify_error(402, "") == "insufficient")
    check("T-J04c", "400 model_na", jev_adapter._classify_error(400, "model is not available") == "model_na")
    check("T-J04d", "500 -> server_error", jev_adapter._classify_error(500, "") == "server_error")

def test_jev_failure_degradation():
    failed = {"ok": False, "error_code": "model_na", "error_message": "model not available"}
    check("T-J05", "失败 JEV 不被当作可用",
          jev_adapter.is_available(failed) is False)
    from engine import stock_judge
    status = {"name": "百利天恒", "current": 100.0, "anchor": 90.0, "deviation": 11.1,
              "status": "超买入区间", "composite_score": 70.0, "latest_date": "2026-10-20"}
    analysis = stock_judge.judge_stock("sh688506", {"sh688506": status}, failed,
                                       research_override={"exists": False})
    check("T-J05b", "JEV 失败被记为缺口而非支持证据",
          any("JEV" in g for g in analysis["synthesis"]["gaps"]))
    check("T-J05c", "失败不产生看多/看空结论",
          analysis["action"]["action"] in ("CONSIDER_REDUCE", "HOLD", "OBSERVE", "INSUFFICIENT_EVIDENCE"))

# ---------------- 历史数据缺失与新鲜度 ----------------

def test_parse_date_invalid():
    check("T-H01", "无效日期解析返回 None",
          provenance._parse_date("not-a-date") is None)
    check("T-H01b", "YYYYMMDD 解析正确",
          provenance._parse_date("20261020").isoformat() == "2026-10-20")

def test_anchor_before_first_snapshot():
    snap = provenance.anchor_snapshot_asof(__import__("datetime").date(2020, 1, 1))
    check("T-H02", "2020 年无锚价快照",
          snap["available"] is False)

def test_ranking_no_historical():
    snap = provenance.ranking_snapshot_asof(__import__("datetime").date(2026, 10, 19))
    check("T-H03", "历史日期无排名快照",
          snap["available"] is False)

def test_staleness_blocks_entry():
    gate = trading_day.data_staleness_gate("2026-09-30", "2026-10-20", max_lag_trading_days=2)
    check("T-H04", "数据滞后 14 交易日触发 STALE",
          gate["verdict"] == "STALE" and gate["blocking"] is True)
    gated = trading_day.apply_staleness_gate(
        {"action": "CONSIDER_ENTRY", "reason": "x"}, gate)
    check("T-H04b", "过期行情将 CONSIDER_ENTRY 降级为 OBSERVE",
          gated["action"] == "OBSERVE" and gated.get("staleness_blocked") is True)

# ---------------- 重复输出保护 ----------------

def test_save_report_unique():
    with tempfile.TemporaryDirectory() as tmp:
        report.REPORTS_DIR = tmp
        p1 = report.save_report("first")
        p2 = report.save_report("second")
        check("T-R01", "重复保存生成不同文件名",
              p1 != p2 and Path(p1).exists() and Path(p2).exists())
        check("T-R01b", "内容不覆盖",
              Path(p1).read_text() == "first" and Path(p2).read_text() == "second")

def test_explicit_output_conflict():
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "2026-10-20.md"
        target.write_text("old", encoding="utf-8")
        conflicts = report.output_conflicts(str(target))
        check("T-R02", "已存在输出被 output_conflicts 检出",
              str(target) in conflicts)
        json_target = Path(tmp) / "2026-10-20.json"
        json_target.write_text("{}", encoding="utf-8")
        conflicts2 = report.output_conflicts(str(target))
        check("T-R02b", "同名 JSON 也被视为冲突",
              str(json_target) in conflicts2)

test_content_fallback()
test_no_published_date()
test_url_dedupe_encoded()
test_official_issuer_tier()
test_multi_source_confirmed()
test_same_domain_not_independent()
test_second_level_public_suffix_domains()
test_search_no_key()
test_search_error_codes()
test_search_timeout_static()
test_jev_noul_schema()
test_jev_choice_schema()
test_jev_route_schema()
test_jev_error_classification()
test_jev_failure_degradation()
test_parse_date_invalid()
test_anchor_before_first_snapshot()
test_ranking_no_historical()
test_staleness_blocks_entry()
test_save_report_unique()
test_explicit_output_conflict()

print(f"\n=== test_p5: {PASS} passed, {FAIL} failed ===")
sys.exit(1 if FAIL else 0)
test_content_fallback()
test_no_published_date()
test_url_dedupe_encoded()
test_official_issuer_tier()
test_multi_source_confirmed()
test_same_domain_not_independent()
test_search_no_key()
test_search_error_codes()
test_search_timeout_static()
test_jev_noul_schema()
test_jev_choice_schema()
test_jev_route_schema()
test_jev_error_classification()
test_jev_failure_degradation()
test_parse_date_invalid()
test_anchor_before_first_snapshot()
test_ranking_no_historical()
test_staleness_blocks_entry()
test_save_report_unique()
test_explicit_output_conflict()

