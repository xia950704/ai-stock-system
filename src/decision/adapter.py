#!/usr/bin/env python3
"""P0 Decision Model adapter for AMD Radeon API (Clef / d3 / d3-flash).

Endpoint: https://developer.amd.com.cn/radeon/api/v1/chat/completions
Auth:     Bearer <AMD_API_KEY>
Models:   Clef, d3, d3-flash  (output modality = decision)

The adapter:
  1. Builds a DecisionInput-compatible prompt
  2. Calls AMD API with exponential backoff on 429 / transport errors
  3. Parses the JSON response into a DecisionOutput
  4. Validates against decision.contract

No position size, cost basis, or portfolio data is sent to the model.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decision.contract import (
    DecisionInput,
    DecisionOutput,
    StockDecision,
    ActionType,
    validate_decision_output,
)

TZ = timezone(timedelta(hours=8))

# ---- Config (env overrides; .env values are defaults) ----
AMD_BASE_URL = os.environ.get(
    "AMD_API_BASE",
    "https://developer.amd.com.cn/radeon/api/v1",
)
# 密钥只走环境变量，不写默认值（原默认值为明文泄漏，已移除）。
# 缺失时 is_available() / decide() 会显式返回不可用，而不是静默使用泄漏凭据。
AMD_API_KEY = os.environ.get("AMD_API_KEY", "")
AMD_MODEL = os.environ.get("AMD_DECISION_MODEL", "Clef")
REQUEST_TIMEOUT_S = float(os.environ.get("AMD_TIMEOUT_S", "60"))
MAX_RETRIES = int(os.environ.get("AMD_MAX_RETRIES", "5"))
BACKOFF_BASE_S = float(os.environ.get("AMD_BACKOFF_BASE_S", "4.0"))
# 优先读新名 AMD_API_BASE_FALLBACKS，兜底读旧名 AMD_FALLBACK_URLS
_fallback_env = os.environ.get("AMD_API_BASE_FALLBACKS") or os.environ.get("AMD_FALLBACK_URLS", "")
AMD_FALLBACK_URLS = [
    url.strip()
    for url in _fallback_env.split(",")
    if url.strip()
]


def _endpoints() -> List[str]:
    """返回有序 endpoint 列表（primary 在前，fallback 在后，自动去重）。"""
    urls = [AMD_BASE_URL] + AMD_FALLBACK_URLS
    seen: set = set()
    result: List[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result


def _now_iso() -> str:
    return datetime.now(TZ).isoformat()


# ---- Prompt builders ----

def build_system_prompt() -> str:
    return (
        "You are a professional A-share stock decision analyst.\n"
        "\n"
        "Output MUST be valid JSON matching this schema:\n"
        "{\n"
        '  "model_id": "<model name>",\n'
        '  "report_date": "YYYY-MM-DD",\n'
        '  "generated_at": "ISO datetime",\n'
        '  "market_verdict": "偏多|中性|偏空|无法判断",\n'
        '  "market_confidence": <0.0-1.0>,\n'
        '  "market_reasoning": "string",\n'
        '  "stocks": [\n'
        "    {\n"
        '      "code": "sh600276",\n'
        '      "name": "恒瑞医药",\n'
        '      "action": "CONSIDER_ENTRY|CONSIDER_ADD|HOLD|WAIT|OBSERVE|'
        "CONSIDER_REDUCE|CONSIDER_EXIT|INSUFFICIENT_EVIDENCE\",\n"
        '      "confidence": <0.0-1.0>,\n'
        '      "reasoning": "string",\n'
        '      "supports": ["string"],\n'
        '      "conflicts": ["string"],\n'
        '      "gaps": ["string"],\n'
        '      "conditions": ["string"],\n'
        '      "invalidation": ["string"],\n'
        '      "evidence_claims": [\n'
        "        {\n"
        '          "claim_id": "string",\n'
        '          "statement": "string",\n'
        '          "status": "confirmed|refuted|single_source|unverified|conflicting",\n'
        '          "supporting_sources": [{"url":"","title":"","snippet":"","tier":1,"publish_date":"","retrieved_at":"","domain":""}],\n'
        '          "refuting_sources": [],\n'
        '          "independent_source_count": 0,\n'
        '          "notes": []\n'
        "        }\n"
        "      ],\n"
        '      "unknown_fields": ["string"],\n'
        '      "provenance": {}\n'
        "    }\n"
        "  ],\n"
        '  "overall_notes": ["string"],\n'
        '  "trace": {}\n'
        "}\n"
        "\n"
        "Rules:\n"
        "- action must be one of the 8 valid values\n"
        "- confidence must be 0.0-1.0\n"
        "- evidence_claims tier: 1=official, 2=regulatory, 3=reputable_media, 4=industry_research, 5=social_unverified\n"
        "- Be honest about uncertainty; use INSUFFICIENT_EVIDENCE when data is missing\n"
        "- Do NOT give buy/sell recommendations; use the action vocabulary only\n"
        "- Do NOT reference position size, cost basis, or portfolio data\n"
    )


def build_user_prompt(input_obj: DecisionInput) -> str:
    data: Dict[str, Any] = {
        "report_date": input_obj.report_date,
        "market_context": input_obj.market_context,
        "stocks": input_obj.stocks,
        "data_provenance": input_obj.data_provenance,
        "freshness_gate": input_obj.freshness_gate,
        "constraints": input_obj.constraints,
    }
    if input_obj.historical_judgments:
        data["historical_judgments"] = input_obj.historical_judgments
    return (
        "Analyze the following A-share stock data and produce a decision report.\n\n"
        + json.dumps(data, ensure_ascii=False, indent=2, default=str)
    )


# ---- HTTP layer ----

def _call_amd_api_once(
    system_prompt, user_prompt, model=AMD_MODEL,
    base_url=AMD_BASE_URL, api_key=AMD_API_KEY,
    timeout_s=REQUEST_TIMEOUT_S,
):
    """Single HTTP call to AMD /v1/systemone endpoint.

    The AMD decision models (Clef/d3/d3-flash) use a structured question
    format, not OpenAI-compatible chat/completions.
    """
    try:
        import httpx
    except ImportError:
        return False, {}, 'httpx not installed'

    # Build state from user_prompt
    state = {
        'description': 'A-share stock decision analysis',
        'data': {'analysis_request': user_prompt},
        'mode': 'decision',
    }

    # Build noul question (yes/no with uncertainty)
    question_text = 'Based on the provided data, is this stock a good candidate for consideration?'
    payload = {
        'model': model,
        'state': state,
        'questions': {
            'type': {
                'type': 'noul',
                'instructions': question_text,
            },
            'question': {
                'type': 'noul',
                'instructions': question_text,
            },
        },
    }
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + api_key,
    }
    url = base_url + '/systemone'

    try:
        with httpx.Client(timeout=timeout_s) as client:
            r = client.post(url, headers=headers, json=payload)
    except Exception as e:
        return False, {}, 'transport: ' + type(e).__name__ + ': ' + str(e)[:200]

    if r.status_code == 429:
        return False, {}, '429 rate_limit_exceeded'
    if r.status_code != 200:
        return False, {}, 'http_%d: %s' % (r.status_code, r.text[:300])

    try:
        data = r.json()
    except Exception as e:
        return False, {}, 'json_parse_error: ' + str(e)

    # AMD /v1/systemone returns: {answers: {type: {type:'noul', noul:0.44}, question: {...}}, usage: {...}, model: 'Clef'}
    answers = data.get('answers', {})
    type_ans = answers.get('type', {})
    question_ans = answers.get('question', {})

    # Build a DecisionOutput-compatible dict
    noul_val = type_ans.get('noul', question_ans.get('noul', 0.5))
    # Convert noul (0-1) to action
    if noul_val >= 0.65:
        action = 'CONSIDER_ENTRY'
    elif noul_val >= 0.55:
        action = 'CONSIDER_ADD'
    elif noul_val >= 0.45:
        action = 'HOLD'
    elif noul_val >= 0.35:
        action = 'WAIT'
    elif noul_val >= 0.25:
        action = 'OBSERVE'
    else:
        action = 'CONSIDER_REDUCE'

    result = {
        'model_id': data.get('model', model),
        'report_date': '',
        'generated_at': '',
        'market_verdict': '无法判断',
        'market_confidence': noul_val,
        'market_reasoning': 'AMD %s noul=%.4f' % (model, noul_val),
        'stocks': [],
        'overall_notes': ['AMD Decision Model (noul): score=%.4f' % noul_val],
        'trace': {'raw_response': data, 'endpoint': '/systemone'},
    }
    return True, result, ''

def call_amd_api(
    system_prompt: str,
    user_prompt: str,
    model: str = AMD_MODEL,
    api_key: str = AMD_API_KEY,
    timeout_s: float = REQUEST_TIMEOUT_S,
) -> Tuple[bool, Dict[str, Any], str]:
    """Call AMD API with exponential backoff on 429/transport errors.

    支持 endpoint fallback：主 endpoint 连续失败后自动切换到备用 endpoint。
    """
    if not api_key:
        return False, {}, "missing AMD_API_KEY"
    last_err = ""
    for endpoint in _endpoints():
        for attempt in range(MAX_RETRIES):
            ok, parsed, err = _call_amd_api_once(
                system_prompt, user_prompt, model, endpoint, api_key, timeout_s
            )
            if ok:
                return True, parsed, ""
            if "429" in err or "transport" in err.lower():
                wait = BACKOFF_BASE_S * (attempt + 1)
                print("  AMD API retry %d/%d in %.0fs: %s" % (
                    attempt + 1, MAX_RETRIES, wait, err[:100]))
                time.sleep(wait)
                last_err = err
                continue
            # 非重试错误（auth / bad_request / not_found 等）不换 endpoint
            return False, parsed, err
    return False, {}, last_err or "max retries exceeded"


# ---- High-level decision entry point ----

def decide(
    input_obj: DecisionInput,
    model: str = AMD_MODEL,
    api_key: str = AMD_API_KEY,
    timeout_s: float = REQUEST_TIMEOUT_S,
    validate: bool = True,
) -> DecisionOutput:
    """Call AMD Decision Model and return a DecisionOutput."""
    generated_at = _now_iso()
    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(input_obj)

    ok, parsed, err = call_amd_api(
        system_prompt, user_prompt, model, api_key, timeout_s
    )

    if not ok:
        return DecisionOutput(
            model_id=model,
            model_version=None,
            report_date=input_obj.report_date,
            generated_at=generated_at,
            market_verdict="无法判断",
            market_confidence=0.0,
            market_reasoning="API 调用失败: " + err,
            stocks=[],
            overall_notes=["Decision Model 不可用: " + err],
            trace={"error": err, "model": model},
        )

    if validate:
        is_valid, errors = validate_decision_output(parsed)
        if not is_valid:
            return DecisionOutput(
                model_id=model,
                model_version=None,
                report_date=input_obj.report_date,
                generated_at=generated_at,
                market_verdict="无法判断",
                market_confidence=0.0,
                market_reasoning="输出契约校验失败: " + "; ".join(errors[:5]),
                stocks=[],
                overall_notes=["契约校验失败: %d errors" % len(errors)],
                trace={"validation_errors": errors, "raw": parsed},
            )

    stocks: List[StockDecision] = []
    for s in parsed.get("stocks", []):
        try:
            action_val = s.get("action", "INSUFFICIENT_EVIDENCE")
            if not isinstance(action_val, str):
                action_val = str(action_val)
            stocks.append(StockDecision(
                code=str(s.get("code", "")),
                name=str(s.get("name", "")),
                action=ActionType(action_val),
                confidence=float(s.get("confidence", 0.0)),
                reasoning=str(s.get("reasoning", "")),
                supports=list(s.get("supports", [])),
                conflicts=list(s.get("conflicts", [])),
                gaps=list(s.get("gaps", [])),
                conditions=list(s.get("conditions", [])),
                invalidation=list(s.get("invalidation", [])),
                evidence_claims=list(s.get("evidence_claims", [])),
                unknown_fields=list(s.get("unknown_fields", [])),
                provenance=dict(s.get("provenance", {})),
            ))
        except (ValueError, KeyError) as e:
            stocks.append(StockDecision(
                code=str(s.get("code", "unknown")),
                name=str(s.get("name", "unknown")),
                action=ActionType.INSUFFICIENT_EVIDENCE,
                confidence=0.0,
                reasoning="解析失败: " + str(e),
                supports=[],
                conflicts=[],
                gaps=["解析失败: " + str(e)],
                conditions=[],
                invalidation=[],
                evidence_claims=[],
                unknown_fields=[],
                provenance={},
            ))

    return DecisionOutput(
        model_id=parsed.get("model_id", model),
        model_version=parsed.get("model_version"),
        report_date=parsed.get("report_date", input_obj.report_date),
        generated_at=parsed.get("generated_at", generated_at),
        market_verdict=parsed.get("market_verdict"),
        market_confidence=parsed.get("market_confidence"),
        market_reasoning=parsed.get("market_reasoning"),
        stocks=stocks,
        overall_notes=list(parsed.get("overall_notes", [])),
        trace=dict(parsed.get("trace", {})),
    )


def is_available() -> Tuple[bool, str]:
    """Quick check whether the AMD API endpoint is reachable."""
    if not AMD_API_KEY:
        return False, "missing AMD_API_KEY"
    try:
        import httpx
    except ImportError:
        return False, "httpx not installed"
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(
                AMD_BASE_URL + "/models",
                headers={"Authorization": "Bearer " + AMD_API_KEY},
            )
        if r.status_code != 200:
            return False, "HTTP %d" % r.status_code
        data = r.json()
        model_ids = [m.get("id", "") for m in data.get("data", [])]
        if AMD_MODEL in model_ids:
            return True, "OK: %s available (%d models total)" % (AMD_MODEL, len(model_ids))
        return False, "model %s not found in %s" % (AMD_MODEL, model_ids[:5])
    except Exception as e:
        return False, "transport error: %s" % str(e)[:200]


# ---- Self-test ----

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="only check API availability")
    parser.add_argument("--model", default=AMD_MODEL, help="model name (Clef/d3/d3-flash)")
    args = parser.parse_args()

    if args.check:
        ok, msg = is_available()
        print("AMD API: %s - %s" % ("OK" if ok else "FAIL", msg))
        sys.exit(0 if ok else 1)

    # End-to-end test with a minimal DecisionInput
    test_input = DecisionInput(
        report_date="2026-10-21",
        market_context={
            "verdict": "中性",
            "confidence": "low",
            "supporting_evidence": ["锚价池平均偏离 +12.16%"],
            "conflicting_evidence": ["卖出信号多于买入信号"],
            "limitations": ["无外部指数数据"],
        },
        stocks=[
            {
                "code": "sh600276",
                "name": "恒瑞医药",
                "price": 47.38,
                "anchor": 47.0,
                "deviation_pct": 0.81,
                "pe": 36,
                "composite_score": 31.7,
                "tech_score": 35.0,
                "ml_boost": -3.2,
                "jev_answer": 0.5,
                "search_claims": ["公司发布最新公告"],
            }
        ],
        data_provenance={"anchor": "ok", "ranking": "ok", "jev": "ok", "search": "ok"},
        freshness_gate={"verdict": "FRESH", "lag_trading_days": 0},
        constraints={"max_position_pct": 10},
    )

    print("Calling AMD Decision Model (%s)..." % args.model)
    result = decide(test_input, model=args.model)
    print("market_verdict: %s" % result.market_verdict)
    print("market_confidence: %s" % result.market_confidence)
    print("stocks: %d" % len(result.stocks))
    for s in result.stocks:
        print("  %s %s: %s (conf=%s)" % (s.code, s.name, s.action.value, s.confidence))
    if result.stocks:
        print("reasoning: %s" % result.stocks[0].reasoning[:200])
    print("notes: %s" % result.overall_notes)
