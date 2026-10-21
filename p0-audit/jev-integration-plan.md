# P0 JEV 集成方案（jev-integration-plan）

> 生成时间：2026-10-20。P0 只读探查产物。
> 基于 JEV MCP 工具契约与现有技能，提出在股票投研系统中的集成方式。

## 1. 集成目标

在不修改 JEV MCP 服务器或核心逻辑的前提下，将 JEV 的二值/概率判断能力安全地集成到股票投研分析流程中，用于：
- 辅助信号判断（如“此价格突破是否真实”）
- 路由决策（轻量判断 vs 深度分析）
- 工具守卫（破坏性操作前的风险评估）
- 所有结论必须明确区分 JEV 辅助与人工判断。

## 2. 现有 JEV 能力（来自 skill 与 MCP server）

| 工具 | 输入格式 | 输出 | 适用场景 |
|---|---|---|---|
| `jev_decide` | `state` (dict)，`questions` (dict of 题型) | `{ok, model, answers, usage, request}` | 多题判断，可一次问多题 |
| `jev_yes_no` | `state`, `question` (str)，`no_text` (str, optional)，`mode` (`choice`\|`noul`) | 同上 | 二值判断，`choice` 提供置信度，`noul` 提供裸概率 |
| `jev_guard_tool_call` | `tool`, `action`, `arguments_summary` (list)，`side_effects` (list)，`safeguards` (list)，`policy` (list)，`reversibility` (str) | 同上 | 仅给建议，不执行工具 |
| `jev_route` | `task` (str)，`options` (dict of 标签: 描述)，`model` (str) | 同上 | 路由任务至适当复杂度模型 |
| `jev_front_door` | `task` (str)，`model` (str) | `{gate, gate_raw, route, hint}` | 前门：先判断是否为轻量判断（jev_native）或需 openrouter（生成文本） |

**题型**：
- `choice`: `criteria` 为对象，键为选项名，值为描述。
- `score`: `criteria` 为数组，第 0 项为问题字符串，后续项为档位名。
- `noul`: 无 `criteria`，使用 `instructions` 字段写是非陈述句 → 返回 `noul: 0-1`（无 confidence）。

**返回字段通用结构**：
- `ok`: bool
- `model`: str
- `answers`: dict of 题目名 → 题目结果
  - 题目结果包含 `choice`、`confidence`、`probabilities`（choice/score）或 `noul`（noul）。
- `usage`: 可选的使用统计。
- `request`: 回显的输入请求。

## 3. 集成设计

### 3.1 调用封装

在 `src/jev/client.py` 中提供薄包装，隐藏 MCP 细节：

```python
import json
import os
import httpx
from typing import Dict, Any, Optional, Union

JEV_BASE_URL = os.getenv("JEV_BASE_URL", "https://router.bynara.id/v1")
JEV_MODEL = os.getenv("JEV_MODEL", "jev")
JEV_TIMEOUT = float(os.getenv("JEV_TIMEOUT", "60"))
JEV_API_KEY = os.getenv("JEV_PROXY_API_KEY")  # 由 Hermes 注入或从 .key 读取

def _get_api_key() -> str:
    if JEV_APIKEY:
        return JEV_APIKEY
    key_path = os.path.expanduser("~/.hermes/mcp-servers/jev-systemone/.key")
    with open(key_path, 'r') as f:
        return f.read().strip()

def _call(payload: Dict) -> Dict:
    url = f"{JEV_BASE_URL}/systemone"
    headers = {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type": "application/json"
    }
    with httpx.Client(timeout=JEV_TIMEOUT) as client:
        resp = client.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            return {"ok": False, "http_status": resp.status_code, "detail": resp.text[:600]}
        data = resp.json()
        return {"ok": True, "model": data.get("model"), "answers": data.get("answers", {}), "usage": data.get("usage", {})}

def jev_decide(state: Dict[str, Any], questions: Dict[str, Any], model: str = JEV_MODEL) -> Dict:
    payload = {"model": model, "state": state, "questions": questions}
    result = _call(payload)
    result["request"] = payload
    return result

def jev_yes_no(state: Dict[str, Any], question: str, no_text: Optional[str] = None,
               mode: str = "choice", model: str = JEV_MODEL) -> Dict:
    if mode == "noul":
        q = {"type": "noul", "instructions": question}
    else:
        q = {"type": "choice", "criteria": {
            "yes": question,
            "no": no_text or f"the statement above does not hold given this state: {question}"
        }}
    payload = {"model": model, "state": state, "questions": {"answer": q}}
    result = _call(payload)
    result["request"] = payload
    return result

def jev_guard_tool_call(tool: str, action: str,
                        arguments_summary: Optional[list] = None,
                        side_effects: Optional[list] = None,
                        safeguards: Optional[list] = None,
                        policy: Optional[list] = None,
                        reversibility: Optional[str] = None,
                        model: str = JEV_MODEL) -> Dict:
    state = {"tool": tool, "action": action}
    for k, v in (("arguments_summary", arguments_summary),
                 ("side_effects", side_effects),
                 ("safeguards", safeguards),
                 ("policy", policy),
                 ("reversibility", reversibility)):
        if v:
            state[k] = v
    payload = {"model": model, "state": state,
               "questions": {"decision": {"type": "choice", "criteria": {
                   "allow": "Safe to execute without human review",
                   "confirm": "Execute only after explicit user confirmation",
                   "review": "Escalate to human for full review",
                   "deny": "Must not execute",
               }}}}
    result = _call(payload)
    result["request"] = payload
    return result

def jev_route(task: str, options: Optional[Dict[str, str]] = None,
              model: str = JEV_MODEL) -> Dict:
    criteria = options or {
        "light": "简短、有明确单一目标、无需复杂推理（翻译/格式化/摘要/比对）",
        "heavy": "开放式、需长上下文、规划或多步推理（方案设计/审计/风控/综合写作）",
        "jev":   "纯数值或二值判断，单步可判定（占比/完成率/阈值检查/公式计算）"
    }
    payload = {"model": model, "state": {"task": task},
               "questions": {"route": {"type": "choice", "criteria": criteria}}}
    result = _call(payload)
    result["request"] = payload
    return result

def jev_front_door(task: str, model: str = JEV_MODEL) -> Dict:
    state = {"task": task}
    native_q = {"gate": {"type": "choice", "criteria": {
        "native": "单步数值或二值判断，答案可直接判定，无需生成任何文本",
        "generate": "需要开放式文本生成、规划或多步推理（翻译/写作/方案/代码）"
    }}}
    gate = _call({"model": model, "state": state, "questions": native_q})
    gate_result = gate.get("answers", {}).get("gate", {})
    pick = gate_result.get("choice")
    out = {"gate": pick, "gate_raw": gate}
    if pick == "native":
        out["route"] = "jev_native"
        out["hint"] = "改用 jev_yes_no 或 jev_decide(noul) 直接判，0 元 ~2s"
        return out
    # generate: 调用 jev CLI（需依赖 hermes-jev-skills）
    import subprocess
    cli = os.path.expanduser("~/.hermes/jev-skills/bin/jev")
    env = dict(os.environ)
    env.setdefault("TYPESAFE_BASE_URL", "https://router.bynara.id")
    env.setdefault("TYPESAFE_MODEL", "jev")
    env.setdefault("JEV_PROXY_API_KEY", _get_api_key())
    timeout_s = float(os.getenv("JEV_ROUTE_TIMEOUT", "60"))
    try:
        out = subprocess.run(
            [cli, "route", "--prompt", task, "--timeout", str(int(timeout_s))],
            env=env, capture_output=True, text=True, timeout=timeout_s + 30,
            check=False
        )
        result = {"route": "openrouter",
                  "cli_stdout": out.stdout[-2000:],
                  "cli_stderr": out.stderr[-500:],
                  "exit_code": out.returncode}
        # 尝试解析 CLI 输出的 JSON
        import re
        json_match = re.search(r'\{.*\}', out.stdout, re.DOTALL)
        if json_match:
            try:
                result["cli_json"] = json.loads(json_match.group())
            except Exception:
                pass
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}
```

### 3.2 在分析流程中的使用位置

| 位置 | 调用工具 | 目的 | 示例 |
|---|---|---|---|
| 数据验证步骤 | `jev_yes_no`（noul） | 判断“此行情数据是否异常（如价格偏离 > 3σ）”。 | `state = {"price": 45.2, "mean": 40.0, "std": 2.0, "zscore": (price-mean)/std}`<br>`question = "该价格异常偏离超过 2 倍标准差"` |
| 信号路由 | `jev_route` | 决定是否使用轻量 JEV 判断还是进入深度分析。 | `task = "根据当前技术面和基本面，判断是否需要深度分析此股票"` |
| 工具守卫 | `jev_guard_tool_call` | 在执行可能修改文件的操作前（如写入报告）进行风险评估。 | `tool = "file_write"`, `action = "更新每日检查 CSV"`, `side_effects = ["可能覆盖历史数据"]`, `safeguards = ["备份原文件", "只追加新行"]`, `reversibility = "partially_reversible"` |
| 二值信号 | `jev_yes_no`（choice） | 判断“此突破是否真实”或“该新闻是否看多”。 | `state = {"news_sentiment": 0.8, "volume_ratio": 1.5, "price_change_pct": 3.2}`<br>`question = "该利好新闻配合放量是否表示真实突破"`<br>`no_text = "该利好新闻未能引起持续买盘，可能是假突破"` |
| 排序/分档 | `jev_decide`（score） | 将多因子得分映射至档位（如强/中/弱）。 | `state = {"score": 7.5}`<br>`question = "此综合得分对应的投资评级是什么？"`<br>`criteria = ["这个得分对应的评级是？", "强", "中", "弱", "很弱"]` |

### 3.3 错误处理与降级

- 若 JEV MCP 调用超时或返回非 200，则返回 `{"ok": False, "error": ...}`，上层应记录日志并采取降级策略：
  - 降级为仅基于规则判断（如阈值检查），在结论中明确标注：“JEV 调用失败，结论仅基于规则”。
  - 不得将 JEV 调用失败解释为中性、看多或看空。
- 若返回的 `confidence` 过低（如 < 0.3）或 `noul` 在 0.3~0.7 区间，视为模糊，应在结论中注明：“判断置信度较低，建议进一步收集证据”。
- 所有 JEV 调用均应记录输入 `state`、`questions`、`model`、`输出` 以及 `timestamp`，存放于 `logs/jev/` 供审计。

## 4. 风险与对策

| 风险 | 等级 | 对策 |
|---|---|---|
| JEV 网络不可达（超时、502） | M | 降级为规则判断，明确标注 JEV 缺失 |
| JEV 返回值被误用（如将 confidence 当作概率） | L | 在客户端文档中强调使用字段，教育使用者 |
| MCP key 泄漏 | H | 确保 key 文件权限 600，不写入仓库，仅存于 `.hermes/` |
| 并发调用导致速率限制 | M | 在客户端加入简单重试与退避（如指数 backoff） |
| 使用 jelv_front_door 时误判路由 | M | 建议在非确定场景下直接使用 jev_decide/jev_yes_no，避免额外开销 |

## 5. 与现有技能的映射

| 现有技能 | 集成点 |
|---|---|
| stock-research | 在数据验证（如检查价格是否异常）中使用 jev_yes_no；在信号路由中使用 jev_route。 |
| system-warmup-stock/system-warmup-trading | 预热时可展示 JEV 服务状态（如是否可达、key 是否存在）。 |
| jev-browser-use / jev-computer-use | 与 JEV MCP 无直接依赖，仅为示例技能。 |
| 投研 AGENTS.md | 应补充：引用 JEV 判断时，必须标注数据来源、调用时间、工具名称及原始输出。 |

## 6. 下一步（P1 重点）

1. 实现 `src/jev/client.py` 参考上述封装（可简化为仅实现所需子集）。
2. 在 stock-research 技能中添加示例调用（仅作演示，不修改核心判断逻辑）。
3. 编写单元测试（使用 mock 响应）验证封装函数行为。
4. 编写文档 `docs/jev-integration-guide.md`，包含调用示例与错误处理。
5. 在 P1 验收后，进入 P2 进行真实网络测试与基于 JEV 的辅助判断试点。

