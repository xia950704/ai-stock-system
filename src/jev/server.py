#!/usr/bin/env python
"""jev-systemone MCP server.

Wraps NaraRouter's /v1/systemone endpoint (Jev decision model) as MCP tools.
Jev answers typed questions about a piece of state (choice / score) with
probabilities + confidence. It is NOT a chat model.

Key resolution order: JEV_API_KEY env > BYNARA_API_KEY env >
~/.hermes/mcp-servers/jev-systemone/.key file.
"""
import json
import os

import httpx
from mcp.server.fastmcp import FastMCP

BASE_URL = os.environ.get("JEV_BASE_URL", "https://router.bynara.id/v1")
DEFAULT_MODEL = os.environ.get("JEV_MODEL", "jev")
KEY_FILE = os.path.expanduser("~/.hermes/mcp-servers/jev-systemone/.key")
TIMEOUT_S = float(os.environ.get("JEV_TIMEOUT", "60"))

mcp = FastMCP("jev-systemone")


def _key() -> str:
    for var in ("JEV_API_KEY", "BYNARA_API_KEY"):
        v = os.environ.get(var)
        if v:
            return v
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE) as f:
            k = f.read().strip()
        if k:
            return k
    raise RuntimeError(
        "No Jev/NaraRouter API key found. Set JEV_API_KEY (or BYNARA_API_KEY) "
        f"in the server env, or write the key to {KEY_FILE}"
    )


def _call(payload: dict) -> dict:
    """POST /v1/systemone and return a normalized result dict."""
    url = f"{BASE_URL}/systemone"
    try:
        with httpx.Client(timeout=TIMEOUT_S) as client:
            r = client.post(
                url,
                headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"},
                json=payload,
            )
    except httpx.TimeoutException:
        return {"ok": False, "error": f"timeout after {TIMEOUT_S}s calling {url}"}
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"transport error: {e}"}
    if r.status_code != 200:
        return {"ok": False, "http_status": r.status_code, "detail": r.text[:600]}
    data = r.json()
    return {"ok": True, "model": data.get("model"), "answers": data.get("answers", {}), "usage": data.get("usage", {})}


# ---------------------------------------------------------------- tools

@mcp.tool()
def jev_decide(state: dict, questions: dict, model: str = DEFAULT_MODEL) -> dict:
    """Native Jev decision: ask typed questions about a state, get answers with probabilities.

    Format rules (learned by live testing against NaraRouter):
    - Each question value: {"type": "choice"|"score", "criteria": <choice=object / score=array>}
    - choice criteria = object whose KEYS are the option labels (2-255 options);
      each key maps to a short description of when that option applies.
    - score criteria = array: element 0 = the question string, elements 1..N = level labels (2-10 levels);
      response carries a weighted numeric score + probabilities per level.
    - noul type: use the "instructions" field (NOT criteria) with a yes/no statement;
      returns a noul value 0-1 = P(true). Native and working on this router.
    """
    payload = {"model": model, "state": state, "questions": questions}
    result = _call(payload)
    result["request"] = payload
    return result


@mcp.tool()
def jev_yes_no(state: dict, question: str, no_text: str | None = None,
               mode: str = "choice", model: str = DEFAULT_MODEL) -> dict:
    """Yes/no judgment: does a statement hold given this state?

    state: business fields (dict or string). question: the statement to evaluate
    (e.g. "Does this evidence support issuing the refund?").
    mode: "choice" (default) or "noul". choice is sharper and returns a
        `confidence` field that collapses on genuinely ambiguous states, which is
        the signal to escalate to a human. Measured on clinical screening: clear
        cases conf 0.96/1.00, ambiguous case conf 0.12. noul returns a bare
        P(true) 0.0-1.0 instead (same cases 0.89 / 0.04 / 0.41): calmer, but it
        carries no uncertainty flag.
    no_text: the opposite statement, choice mode only. Pass a real negation when
        you can -- a proper opposite lifted a positive answer's confidence from
        0.76 to 0.98 versus an auto-built one, so the default is a fallback.
    """
    if mode == "noul":
        q: dict = {"type": "noul", "instructions": question}
    else:
        q = {"type": "choice", "criteria": {
            "yes": question,
            "no": no_text or ("the statement above does not hold given this state: " + question),
        }}
    payload = {"model": model, "state": state, "questions": {"answer": q}}
    result = _call(payload)
    result["request"] = payload
    return result


@mcp.tool()
def jev_guard_tool_call(tool: str, action: str, arguments_summary: list | None = None,
                        side_effects: list | None = None, safeguards: list | None = None,
                        policy: list | None = None, reversibility: str | None = None,
                        model: str = DEFAULT_MODEL) -> dict:
    """Tool-guard preset: allow/confirm/review/deny a consequential tool call.

    Jev only advises — it does not execute the tool.
    arguments_summary/side_effects/safeguards/policy: string lists.
    reversibility: e.g. "reversible", "partially_reversible", "irreversible".
    """
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
    result = _call(payload)
    result["request"] = payload
    return result


DEFAULT_ROUTER = {
    "light": "简短、有明确单一目标、无需复杂推理（翻译/格式化/摘要/比对）",
    "heavy": "开放式、需长上下文、规划或多步推理（方案设计/审计/风控/综合写作）",
    "jev":   "纯数值或二值判断，单步可判定（占比/完成率/阈值检查/公式计算）",
}


@mcp.tool()
def jev_route(task: str, options: dict | None = None, model: str = DEFAULT_MODEL) -> dict:
    """Front-door task router: pick the shortest adequate path for a task.

    Default 3-way criteria (light/heavy/jev, see DEFAULT_ROUTER); pass options
    {label: description} to arbitrate your own candidate plans instead.
    2-255 labels. Jev only arbitrates — it does not invent candidates, so the
    quality of custom plans is bounded by whoever wrote the options. Keep
    option descriptions roughly equal in detail (jev drifts toward the
    longest one). Returns choice + probabilities; trust `choice`, not
    confidence (argmax on probabilities is unreliable). Latency ~2.8-8.6s.
    """
    criteria = options or DEFAULT_ROUTER
    payload = {"model": model, "state": {"task": task},
               "questions": {"route": {"type": "choice", "criteria": criteria}}}
    result = _call(payload)
    result["request"] = payload
    return result


DEFAULT_CLI = os.path.expanduser("~/.hermes/jev-skills/bin/jev")


@mcp.tool()
def jev_front_door(task: str, model: str = DEFAULT_MODEL) -> dict:
    """Front door: pick the shortest adequate path for a task, in one call.

    Step 1 asks jev (choice, 2 options): is this task a single-step
    numeric/binary judgment that needs NO generated text?
    - yes -> route="jev_native": call jev_yes_no / jev_decide (noul) instead;
      0 cost, ~2s. This is the point where jev decides its OWN path.
    - no  -> route="openrouter": shell out to the jev CLI (`jev route`) to
      pick a tier+model from the 332-model openrouter pool (~3-5s).
    Requires ~/.hermes/jev-skills checkout (stabilized 10-09; do NOT pin /tmp)
    and the 3 env vars (injected here: TYPESAFE_BASE_URL / JEV_PROXY_API_KEY
    from the local .key / TYPESAFE_MODEL=jev). jEV CLI default timeout is too
    short for bynara — this tool always passes --timeout 60.
    """
    state = {"task": task}
    native_q = {"gate": {"type": "choice", "criteria": {
        "native": "单步数值或二值判断，答案可直接判定，无需生成任何文本",
        "generate": "需要开放式文本生成、规划或多步推理（翻译/写作/方案/代码）"}}}
    gate = _call({"model": model, "state": state, "questions": native_q})
    gate_result = gate.get("answers", {}).get("gate", {})
    pick = gate_result.get("choice")
    out = {"gate": pick, "gate_raw": gate}
    if pick == "native":
        out["route"] = "jev_native"
        out["hint"] = "改用 jev_yes_no 或 jev_decide(noul) 直接判，0 元 ~2s"
        return out
    # generate: shell out to jev CLI route
    import subprocess
    cli = os.environ.get("JEV_CLI", DEFAULT_CLI)
    env = dict(os.environ)
    env.setdefault("TYPESAFE_BASE_URL", "https://router.bynara.id")
    env.setdefault("TYPESAFE_MODEL", "jev")
    key = ""
    try:
        key = _key()
    except RuntimeError:
        pass
    if key:
        env["JEV_PROXY_API_KEY"] = key
    timeout_s = float(os.environ.get("JEV_ROUTE_TIMEOUT", "60"))
    r = subprocess.run([cli, "route", "--prompt", task, "--timeout", str(int(timeout_s))],
                       env=env, capture_output=True, text=True, timeout=timeout_s + 30)
    out["route"] = "openrouter"
    out["cli_stdout"] = r.stdout[-2000:]
    out["cli_stderr"] = r.stderr[-500:]
    out["exit_code"] = r.returncode
    # The CLI prints a JSON object (possibly after other lines); parse it so
    # callers don't have to string-slice.
    start = r.stdout.find("{\n  \"routed\"")
    if start == -1:
        start = r.stdout.find("{")
    if start != -1:
        tail = r.stdout[start:]
        depth, end = 0, -1
        for i, ch in enumerate(tail):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end != -1:
            try:
                j = json.loads(tail[:end])
                out["cli_json"] = {k: j.get(k) for k in
                                   ("routed", "model", "provider", "model_id", "tier",
                                    "specialty", "confidence", "difficulty", "costly_mistake",
                                    "latency_ms", "reason", "notice", "current")}
            except (json.JSONDecodeError, AttributeError):
                pass
    return out


if __name__ == "__main__":
    mcp.run(transport="stdio")
