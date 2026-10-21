#!/usr/bin/env python3
"""JEV 调用适配层（P3-1 / P3-2）。

与现有 `~/.hermes/mcp-servers/jev-systemone/server.py` 保持同一工具契约：
  优先通过 MCP stdio 调用 jev_decide / jev_yes_no / jev_guard_tool_call /
  jev_route / jev_front_door；HTTP 仅作为显式回退。
返回归一化结构：
  {"ok": True, "model":..., "answers":..., "usage":...}
或
  {"ok": False, "error_code":..., "error_message":..., "http_status":...}

失败分级（P3-1 要求）：
  - timeout        : httpx.TimeoutException
  - transport      : httpx.HTTPError（连接失败等）
  - auth           : HTTP 401
  - model_na       : HTTP 400 "model is not available"
  - insufficient   : HTTP 402 "Insufficient credits"
  - forbidden      : HTTP 403 "plan does not include"
  - not_found      : HTTP 404 "model does not exist"
  - rejected       : HTTP 400 "model rejected this request"
  - server_error   : HTTP 5xx
  - parse_error    : 返回体无法解析或缺少 answers
  - no_key         : 未解析到 API key
  - no_httpx       : httpx 不可用
  - unknown        : 其他

重要：JEV 调用失败**不等于**中性、看多或看空。由调用方根据 error_code 决定降级。
"""
import json
import importlib.util
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import httpx
except ImportError:  # pragma: no cover - 环境依赖
    httpx = None

# ---- 配置（复用现有 MCP Server 的本地 .env，不修改全局注册）----
MCP_SERVER_DIR = os.path.expanduser(
    os.environ.get("JEV_MCP_SERVER_DIR", "~/.hermes/mcp-servers/jev-systemone")
)
MCP_ENV_FILE = os.path.join(MCP_SERVER_DIR, ".env")
_DEFAULT_MCP_PYTHON = os.environ.get(
    "JEV_MCP_PYTHON",
    os.path.join(MCP_SERVER_DIR, ".venv", "bin", "python"),
)

def _mcp_python() -> str:
    """Return an existing interpreter for the MCP bridge.

    The .venv symlink under jev-systemone has changed across Hermes desktop
    runtime updates dropped file. If the default interpreter is missing, fall
    back to the newest Hermes desktop-runtime venv already installed locally.
    """
    if os.path.isfile(_DEFAULT_MCP_PYTHON):
        return _DEFAULT_MCP_PYTHON
    candidates = sorted(
        Path.home().joinpath(
            ".hermes-web-ui", "desktop-runtime", "hermes"
        ).glob("*")
    )
    for runtime in reversed(candidates):
        python = runtime.joinpath("mac-arm64", "python", "venv", "bin", "python3")
        if python.is_file():
            return str(python)
    return _DEFAULT_MCP_PYTHON

MCP_PYTHON = _mcp_python()
MCP_BRIDGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "jev", "mcp_bridge.py",
)
KEY_FILE = os.path.expanduser(
    os.environ.get("JEV_KEY_FILE", "~/.hermes/mcp-servers/jev-systemone/.key")
)


def _read_local_env() -> Dict[str, str]:
    """只读现有 MCP Server 的 JEV_* 配置；不写回、不打印密钥。"""
    values: Dict[str, str] = {}
    if not os.path.isfile(MCP_ENV_FILE):
        return values
    try:
        with open(MCP_ENV_FILE, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                if key.startswith("JEV_"):
                    values[key] = value.strip()
    except OSError:
        return {}
    return values


_LOCAL_ENV = _read_local_env()

BASE_URL = os.environ.get(
    "JEV_BASE_URL",
    _LOCAL_ENV.get("JEV_BASE_URL", "https://router.bynara.id/v1"),
)
PROVIDER = os.environ.get(
    "JEV_PROVIDER",
    _LOCAL_ENV.get("JEV_PROVIDER", "bynara"),
)
DEFAULT_MODEL = os.environ.get(
    "JEV_MODEL",
    _LOCAL_ENV.get("JEV_MODEL", "jev"),
)
TIMEOUT_S = float(
    os.environ.get("JEV_TIMEOUT", _LOCAL_ENV.get("JEV_TIMEOUT", "60"))
)
TRANSPORT = os.environ.get(
    "JEV_TRANSPORT",
    _LOCAL_ENV.get("JEV_TRANSPORT", "mcp"),
).lower()

# ---- 日志（不含密钥）----
LOG_DIR = os.path.expanduser(os.environ.get("JEV_LOG_DIR", "~/harness/logs/jev"))
LOG_FILE = os.path.join(LOG_DIR, "jev_calls.jsonl")


def _resolve_key() -> Optional[str]:
    """按 env > MCP 本地 .env > key 文件解析 key；返回 None 表示无 key。"""
    for var in ("JEV_API_KEY", "BYNARA_API_KEY"):
        v = os.environ.get(var)
        if v:
            return v
    local_key = _LOCAL_ENV.get("JEV_API_KEY")
    if local_key:
        return local_key
    if os.path.exists(KEY_FILE):
        try:
            with open(KEY_FILE) as f:
                k = f.read().strip()
            if k:
                return k
        except OSError:
            return None
    return None

def provider_config() -> Dict[str, Any]:
    """返回当前生效的 JEV 后端配置（不含密钥值）。"""
    return {
        "transport": TRANSPORT,
        "provider": PROVIDER,
        "base_url": BASE_URL,
        "model": DEFAULT_MODEL,
        "timeout_s": TIMEOUT_S,
        "mcp_server_dir": MCP_SERVER_DIR,
        "mcp_python_available": os.path.isfile(MCP_PYTHON),
        "key_source": (
            "env" if os.environ.get("JEV_API_KEY") or os.environ.get("BYNARA_API_KEY")
            else ("mcp_env" if _LOCAL_ENV.get("JEV_API_KEY")
                  else ("file" if os.path.exists(KEY_FILE) else "none"))
        ),
    }


def _load_external_model_adapter():
    """只读加载现有 model_adapter，避免在 Workspace 复制 Provider 规则。"""
    path = os.path.join(MCP_SERVER_DIR, "model_adapter.py")
    if not os.path.isfile(path):
        return None
    try:
        spec = importlib.util.spec_from_file_location("_jev_external_model_adapter", path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


def _classify_error(http_status: Optional[int], detail: str) -> str:
    """根据 HTTP 状态与 detail 文本归类错误码。"""
    if http_status is None:
        return "unknown"
    if http_status == 401:
        return "auth"
    if http_status == 402:
        return "insufficient"
    if http_status == 403:
        return "forbidden"
    if http_status == 404:
        return "not_found"
    if http_status == 400:
        d = detail.lower()
        if "not available" in d:
            return "model_na"
        if "rejected this request" in d:
            return "rejected"
        return "bad_request"
    if 500 <= http_status < 600:
        return "server_error"
    return "unknown"


def _log_invocation(record: Dict[str, Any]) -> None:
    """追加写入调用日志（不含 key / 敏感 state 字段）。"""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass  # 日志失败不阻塞主流程


def _call(payload: Dict[str, Any], use_mock: bool = False,
          mock_response: Optional[Dict[str, Any]] = None,
          tool: Optional[str] = None,
          tool_args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    call_id = str(uuid.uuid4())[:8]
    ts = datetime.now(timezone(timedelta(hours=8))).isoformat()

    if use_mock:
        rec = {
            "call_id": call_id, "ts": ts, "mode": "mock",
            "model": payload.get("model"), "state_keys": list((payload.get("state") or {}).keys()),
            "question_count": len(payload.get("questions") or {}),
            "result": mock_response,
        }
        _log_invocation(rec)
        return mock_response or {"ok": False, "error_code": "mock_empty", "error_message": "mock returned None"}

    key = _resolve_key()
    if not key:
        rec = {"call_id": call_id, "ts": ts, "mode": "real", "model": payload.get("model"),
               "error_code": "no_key", "error_message": "no API key resolved"}
        _log_invocation(rec)
        return {"ok": False, "error_code": "no_key",
                "error_message": "No JEV API key found (env JEV_API_KEY/BYNARA_API_KEY or key file)"}

    if TRANSPORT == "mcp":
        import json as _json
        bridge_request = {
            "action": "call",
            "tool": tool or "jev_yes_no",
            "arguments": tool_args or payload.get("questions", {}),
            "timeout_s": TIMEOUT_S,
            "python": MCP_PYTHON,
            "server_dir": MCP_SERVER_DIR,
            "pythonpath": str(
                Path(MCP_PYTHON).parent.parent.parent / "optional-skills" / "mcp"
            ),
        }
        try:
            proc = subprocess.run(
                [MCP_PYTHON, MCP_BRIDGE],
                input=_json.dumps(bridge_request),
                capture_output=True, text=True,
                timeout=TIMEOUT_S + 30,
                cwd=MCP_SERVER_DIR,
            )
        except subprocess.TimeoutExpired:
            rec = {"call_id": call_id, "ts": ts, "mode": "real", "model": payload.get("model"),
                   "error_code": "timeout", "error_message": f"mcp_bridge timeout {TIMEOUT_S+30}s"}
            _log_invocation(rec)
            return {"ok": False, "error_code": "timeout",
                    "error_message": f"mcp_bridge timeout after {TIMEOUT_S+30}s"}
        except FileNotFoundError:
            rec = {"call_id": call_id, "ts": ts, "mode": "real", "model": payload.get("model"),
                   "error_code": "transport", "error_message": f"MCP python not found: {MCP_PYTHON}"}
            _log_invocation(rec)
            return {"ok": False, "error_code": "transport",
                    "error_message": f"MCP python not found: {MCP_PYTHON}"}
        except OSError as e:
            rec = {"call_id": call_id, "ts": ts, "mode": "real", "model": payload.get("model"),
                   "error_code": "transport", "error_message": str(e)}
            _log_invocation(rec)
            return {"ok": False, "error_code": "transport", "error_message": f"MCP transport error: {e}"}

        try:
            parsed = _json.loads(proc.stdout.strip())
        except Exception as e:
            rec = {"call_id": call_id, "ts": ts, "mode": "real", "model": payload.get("model"),
                   "error_code": "parse_error", "error_message": f"bridge stdout not JSON: {e}"}
            _log_invocation(rec)
            return {"ok": False, "error_code": "parse_error",
                    "error_message": f"bridge stdout not JSON: {e}"}

        if not isinstance(parsed, dict):
            parsed = {"ok": False, "error_code": "parse_error",
                      "error_message": "bridge returned non-dict"}

        elapsed_s = None
        if hasattr(proc, 'elapsed'):
            elapsed_s = round(proc.elapsed.total_seconds(), 2)
        rec = {"call_id": call_id, "ts": ts, "mode": "real", "model": payload.get("model"),
               "elapsed_s": elapsed_s, "result": parsed}
        _log_invocation(rec)
        return parsed

    # HTTP fallback with external model adapter
    if httpx is None:
        rec = {"call_id": call_id, "ts": ts, "mode": "real", "model": payload.get("model"),
               "error_code": "no_httpx", "error_message": "httpx not installed"}
        _log_invocation(rec)
        return {"ok": False, "error_code": "no_httpx", "error_message": "httpx library unavailable"}

    adapter_mod = _load_external_model_adapter()
    if adapter_mod is not None:
        ep = getattr(adapter_mod, "endpoint_path", lambda *a, **k: "/systemone")(BASE_URL, PROVIDER)
        url = BASE_URL.rstrip("/") + ep
        adapted = getattr(adapter_mod, "adapt_request", lambda p, *a, **k: p)(payload, BASE_URL, PROVIDER)
    else:
        url = f"{BASE_URL}/systemone"
        adapted = payload

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    start = time.time()
    try:
        with httpx.Client(timeout=TIMEOUT_S) as client:
            r = client.post(url, headers=headers, json=adapted)
    except httpx.TimeoutException:
        elapsed = round(time.time() - start, 2)
        rec = {"call_id": call_id, "ts": ts, "mode": "real", "model": payload.get("model"),
               "elapsed_s": elapsed, "error_code": "timeout",
               "error_message": f"timeout after {TIMEOUT_S}s"}
        _log_invocation(rec)
        return {"ok": False, "error_code": "timeout",
                "error_message": f"timeout after {TIMEOUT_S}s calling {url}"}
    except httpx.HTTPError as e:
        elapsed = round(time.time() - start, 2)
        rec = {"call_id": call_id, "ts": ts, "mode": "real", "model": payload.get("model"),
               "elapsed_s": elapsed, "error_code": "transport", "error_message": str(e)}
        _log_invocation(rec)
        return {"ok": False, "error_code": "transport", "error_message": f"transport error: {e}"}

    elapsed = round(time.time() - start, 2)
    if r.status_code != 200:
        detail = r.text[:600] if r.text else ""
        code = _classify_error(r.status_code, detail)
        rec = {"call_id": call_id, "ts": ts, "mode": "real", "model": payload.get("model"),
               "elapsed_s": elapsed, "http_status": r.status_code, "error_code": code,
               "detail": detail}
        _log_invocation(rec)
        return {"ok": False, "error_code": code, "http_status": r.status_code,
                "error_message": detail, "elapsed_s": elapsed}

    try:
        raw = r.json()
    except Exception as e:
        rec = {"call_id": call_id, "ts": ts, "mode": "real", "model": payload.get("model"),
               "elapsed_s": elapsed, "error_code": "parse_error", "error_message": str(e)}
        _log_invocation(rec)
        return {"ok": False, "error_code": "parse_error", "error_message": f"invalid JSON: {e}"}

    if adapter_mod is not None:
        norm = getattr(adapter_mod, "adapt_response", None)
        if norm:
            result = norm(raw, BASE_URL, PROVIDER)
        else:
            result = {"ok": True, "model": raw.get("model"),
                      "answers": raw.get("answers", {}), "usage": raw.get("usage", {})}
    else:
        if not isinstance(raw, dict) or "answers" not in raw:
            rec = {"call_id": call_id, "ts": ts, "mode": "real", "model": payload.get("model"),
                   "elapsed_s": elapsed, "error_code": "parse_error",
                   "error_message": "response missing 'answers' field"}
            _log_invocation(rec)
            return {"ok": False, "error_code": "parse_error",
                    "error_message": "response missing 'answers' field"}
        result = {"ok": True, "model": raw.get("model"), "answers": raw.get("answers", {}),
                  "usage": raw.get("usage", {}), "elapsed_s": elapsed}

    rec = {"call_id": call_id, "ts": ts, "mode": "real", "model": payload.get("model"),
           "elapsed_s": elapsed, "result": result}
    _log_invocation(rec)
    return result


def jev_decide(state: Dict[str, Any], questions: Dict[str, Any],
               model: str = DEFAULT_MODEL, use_mock: bool = False,
               mock_response: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    normalized_questions: Dict[str, Any] = {}
    for qid, question in questions.items():
        q = dict(question) if isinstance(question, dict) else question
        if isinstance(q, dict) and not q.get("instructions"):
            criteria = q.get("criteria")
            if isinstance(criteria, list) and criteria and isinstance(criteria[0], str):
                q["instructions"] = criteria[0]
            elif q.get("type") in ("choice", "score"):
                q["instructions"] = "Select the option that best matches the supplied state."
        normalized_questions[qid] = q
    payload = {"model": model, "state": state, "questions": normalized_questions}
    result = _call(
        payload=payload,
        tool="jev_decide",
        tool_args={"state": state, "questions": normalized_questions, "model": model},
        use_mock=use_mock,
        mock_response=mock_response
    )
    result["request"] = payload
    return result


def jev_yes_no(state: Dict[str, Any], question: str, no_text: Optional[str] = None,
               mode: str = "choice", model: str = DEFAULT_MODEL,
               use_mock: bool = False,
               mock_response: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if mode == "noul":
        q = {"type": "noul", "instructions": question}
    else:
        q = {"type": "choice", "instructions": question, "criteria": {
            "yes": question,
            "no": no_text or ("the statement above does not hold given this state: " + question),
        }}
    payload = {"model": model, "state": state, "questions": {"answer": q}}
    result = _call(
        payload=payload,
        tool="jev_yes_no",
        tool_args={"state": state, "question": question, "no_text": no_text, "mode": mode, "model": model},
        use_mock=use_mock,
        mock_response=mock_response
    )
    result["request"] = payload
    return result


def jev_route(task: str, options: Optional[Dict[str, str]] = None,
              model: str = DEFAULT_MODEL, use_mock: bool = False,
              mock_response: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    criteria = options or {
        "light": "简短、有明确单一目标、无需复杂推理",
        "heavy": "开放式、需长上下文、规划或多步推理",
        "jev": "纯数值或二值判断，单步可判定",
    }
    payload = {"model": model, "state": {"task": task},
               "questions": {"route": {"type": "choice",
                                       "instructions": "Select the shortest adequate path for this task.",
                                       "criteria": criteria}}}
    result = _call(
        payload=payload,
        tool="jev_route",
        tool_args={"task": task, "options": options, "model": model},
        use_mock=use_mock,
        mock_response=mock_response
    )
    result["request"] = payload
    return result


def jev_guard_tool_call(tool: str, action: str, arguments_summary=None,
                        side_effects=None, safeguards=None,
                        policy=None, reversibility=None,
                        model=str(DEFAULT_MODEL), use_mock=False,
                        mock_response=None):
    state = {"tool": tool, "action": action}
    for k, v in (("arguments_summary", arguments_summary), ("side_effects", side_effects),
                 ("safeguards", safeguards), ("policy", policy), ("reversibility", reversibility)):
        if v:
            state[k] = v
    payload = {
        "model": model,
        "state": state,
        "questions": {"decision": {"type": "choice", "criteria": {
            "allow": "Safe to execute without human review",
            "confirm": "Execute only after explicit user confirmation",
            "review": "Escalate to human for full review",
            "deny": "Must not execute",
        }}},
    }
    result = _call(payload, use_mock=use_mock, mock_response=mock_response)
    result["request"] = payload
    return result


DEFAULT_ROUTER = {
    "light": "简短、有明确单一目标、无需复杂推理（翻译/格式化/摘要/比对）",
    "heavy": "开放式、需长上下文、规划或多步推理（方案设计/审计/风控/综合写作）",
    "jev":   "纯数值或二值判断，单步可判定",
}


def jev_front_door(task, model=str(DEFAULT_MODEL), use_mock=False, mock_response=None):
    state = {"task": task}
    native_q = {"gate": {"type": "choice", "criteria": {
        "native": "单步数值或二值判断，答案可直接判定，无需生成任何文本",
        "generate": "需要开放式文本生成、规划或多步推理"}}}
    gate_payload = {"model": model, "state": state, "questions": native_q}
    gate_result = _call(gate_payload, use_mock=use_mock, mock_response=mock_response)
    gate_ans = gate_result.get("answers", {}) if gate_result.get("ok") else {}
    gate_choice = gate_ans.get("gate", {}).get("choice") if isinstance(gate_ans.get("gate"), dict) else None
    out = {"gate": gate_choice, "gate_raw": gate_result}
    if gate_choice == "native":
        out["route"] = "jev_native"
        out["hint"] = "改用 jev_yes_no 或 jev_decide(noul) 直接判"
    else:
        out["route"] = "openrouter"
        out["hint"] = "建议使用 jev_route 或前端路由工具做进一步选择"
    return out



def is_available(result: Dict[str, Any]) -> bool:
    """判断 JEV 调用是否可用（ok=True 且有结构化 answers）。"""
    if not result.get("ok"):
        return False
    answers = result.get("answers")
    return (
        isinstance(answers, dict)
        and bool(answers)
        and all(isinstance(value, dict) for value in answers.values())
    )


def failure_status(result: Dict[str, Any]) -> str:
    """返回失败状态标签，供报告使用。"""
    if not result.get("ok"):
        return result.get("error_code", "unknown")
    return "ok" if is_available(result) else "parse_error"


# ---- 自测（仅离线，不触发真实调用）----
if __name__ == "__main__":
    import sys
    r = jev_yes_no({"x": 1}, "1 < 2", use_mock=True,
                   mock_response={"ok": True, "model": "mock", "answers": {"answer": {"noul": 0.99}}})
    print("mock ok:", r.get("ok"), r.get("answers"))
    r2 = jev_yes_no({"x": 1}, "1 < 2", use_mock=True,
                    mock_response={"ok": False, "error_code": "timeout", "error_message": "timeout"})
    print("mock fail:", r2.get("ok"), r2.get("error_code"))
    sys.exit(0)
