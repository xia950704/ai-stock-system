# jev-systemone 接入说明（Hermes + Codex）

测试日期：2026-10-09，所有命令实际跑过。

## 一句话结论

Jev（NaraRouter 路由上的 `jev` 模型）**不是对话模型**，不能走 `/v1/chat/completions`（全 400）。
它的真实端点是 **`POST https://router.bynara.id/v1/systemone`**，输入是"状态 + 类型化问题"，输出是 选项/分数 + 概率 + 置信度。
已写成 MCP server 接入 Hermes 和 Codex，两边各加 5 个工具：

| 工具 | 用途 | 关键参数 |
|------|------|---------|
| `jev_decide` | 原生决策：任意 state + 问题组 | `state`(dict), `questions`(dict) |
| `jev_yes_no` | 是否判定（你说的"只输出是否"） | `state`(dict), `question`(str) |
| `jev_guard_tool_call` | 工具守卫：allow/confirm/review/deny | `tool`, `action`, 可选 side_effects/safeguards/policy/reversibility |
| `jev_route` | **前置路由**：任务最短路径选择（默认 light/heavy/jev 三档，也可传自定义候选仲裁） | `task`(str), 可选 `options`{标签:描述} |
| `jev_front_door` | **前置门**（一次调用分完流）：jev 先判"数值/二值直判 vs 需生成"；数值→hint 转 jev_yes_no/jev_decide(noul,0元)；生成→sh 调 `jev route` 在 openrouter 池挑模型 | `task`(str) |

## 文件位置

```
~/.hermes/mcp-servers/jev-systemone/
├── server.py    # MCP server（FastMCP v1，5 个工具）
├── .key         # NaraRouter key（sk-nry-G1jl...，600 权限）
├── .venv/       # 独立 venv（uv 建，python 3.12 + mcp>=1,<2 + httpx）
├── run.sh       # 启动脚本
└── selftest.py  # stdio 协议自测（发现工具+实调 jev_yes_no）
```

## 格式规则（实测踩出来的，最容易记反）

- `questions` 里每个问题的值：`{"type": "choice"|"score"|"noul", ...}`
- **choice**：`criteria` 必须是**对象**，**键 = 选项名**（2-255 个），值写"该选项适用时的描述"
- **score**：`criteria` 必须是**数组**，第 0 个元素 = 问题字符串，后面 2-10 个 = 档位名
- **noul**：不用 criteria，用 **`instructions` 字段**写是非陈述句 → 返回 `noul: 0-1`（= P(true)），无 confidence。这是"是否判定"的原生走法
- 不流式；body 上限 32 KiB
- state 可以是 dict、字符串、文本数组（三种都实测 200）

## 用法（对话形式）

### Hermes 里这样说

Hermes 启动后会看到工具名 `mcp_jev_systemone_jev_decide` / `mcp_jev_systemone_jev_yes_no` / `mcp_jev_systemone_jev_guard_tool_call`。
直接自然语言触发即可：

> "用 jev 判断一下：客户争议重复扣款 680 美元，政策是 500 以上需人工审批，这单该放行还是转人工？"

→ agent 调 `jev_guard_tool_call`（或 `jev_decide`），返回 review/confidence 0.99。

> "这条消息紧急吗？'URGENT: 生产数据库挂了，客户没法结账'"

→ agent 调 `jev_yes_no`，返回 yes/confidence 1.0。

> "给这个任务分级：周五前重构鉴权模块，风险高、范围不清"

→ agent 调 `jev_decide`（score 题型），返回 score 2.63、block 概率 0.72。

Hermes 内直接 curl 也行（兜底）：

```bash
curl -s -X POST 'https://router.bynara.id/v1/systemone' \
  -H "Authorization: Bearer $(cat ~/.hermes/mcp-servers/jev-systemone/.key)" \
  -H 'Content-Type: application/json' \
  -d '{"model":"jev","state":{"message":"URGENT: db down"},"questions":{"urgency":{"type":"choice","criteria":{"yes":"表达紧急","no":"不表达"}}}}'
```

### Codex 里这样说

Codex 配置同 Hermes（共享同一个 server.py + .key）。在 Codex 会话里：

> "用 jev-systemone 的 jev_guard_tool_call 评估：issue_customer_refund 工具，动作是争议重复扣款后退款 680 美元，副作用=动资金，保障=已核实重复扣款，政策=500 以上需人工审批，可逆性=部分可逆"

## 注册配置（已写入，留档备查）

Hermes（`hermes mcp add` 生成，~/.hermes/config.yaml）：

```yaml
mcp_servers:
  jev-systemone:
    command: /Users/xiashuang/.hermes/mcp-servers/jev-systemone/.venv/bin/python
    args:
      - /Users/xiashuang/.hermes/mcp-servers/jev-systemone/server.py
    enabled: true
```

Codex（~/.codex/config.toml，已验证 TOML 可解析）：

```toml
[mcp_servers.jev-systemone]
command = "/Users/xiashuang/.hermes/mcp-servers/jev-systemone/.venv/bin/python"
args = ["/Users/xiashuang/.hermes/mcp-servers/jev-systemone/server.py"]
enabled = true
```

Key 不需要进 env：server.py 自动读 `~/.hermes/mcp-servers/jev-systemone/.key`（也可用 env `JEV_API_KEY` 覆盖）。

## 验证记录（2026-10-09 全部实跑）

| 验证 | 结果 |
|------|------|
| `hermes mcp test jev-systemone` | ✓ 连接 546ms，3 工具发现 |
| MCP stdio 自测（client 握手 + 实调 jev_yes_no） | ✓ 发现 3 工具，返回 yes/conf 1.0 |
| jev_decide choice | ✓ HTTP 200，review/conf 0.99 |
| jev_guard_tool_call | ✓ HTTP 200，review/conf 0.99 |
| Codex config.toml 解析 | ✓ tomllib 通过，jev-systemone 段完整 |
| jev_route 前置路由（10-09 补加） | ✓ 4 工具发现；默认三档路由 jev 档命中 conf 1.0；自定义候选仲裁 outline/full/skip 选 outline conf 0.53（候选描述长度不对称，已记录为已知边界） |
| jev_front_door 前置门（10-09 补加） | ✓ 5 工具发现；数值任务(597.7亿>600亿)判 gate=native→hint 转 noul(0元)；生成任务(GCP SOP)判 gate=generate→sh 调 jev route 转出 openrouter:mistral-large-4-0。坑：jev CLI 默认超时会静默 fallback，front_door 固定 --timeout 60 |

## 生效方式

- Hermes：新开会话即生效（MCP 启动时发现工具）
- Codex：重启 Codex 会话后在工具列表里找 `jev-systemone`
- 排查（在该目录下跑，四个脚本各司其职）：
  - `./.venv/bin/python selftest.py` — 协议层握手 + 单模式实调（2 分钟自检）
  - `./.venv/bin/python selftest_modes.py` — choice / noul 两模式回归（含 no_text / mode 新参数）
  - `./.venv/bin/python noise_check.py` — 同输入重复性（5 次，看 argmax 与 conf 抖动）
  - `./.venv/bin/python selftest_skill_examples.py` — 校验 skill 里的 JSON 模板仍打得住
    （防文档漂移：改了题型格式或 SKILL.md 模板后跑这个）
  - `./.venv/bin/python selftest_router.py` — 两个路由工具（jev_route / jev_front_door）
    + 选项长短偏置的回归

注意 `jev_front_door` 的返回信封与其余四个工具不同：是
`{gate, gate_raw, route, hint}`，**没有顶层 `ok` / `answers`**。判成功看 `route`。

## 已知限制

- bynara 路由**没有** `/v1/decisions/*` 端点（12 种路径全 404）；jev 官方站 www.jevai.org 的 decisions 接口要单独的 Jev key，bynara key 打过去 401
- `jev` 在 bynara 模型列表里 0 元定价、32k 上下文、无 vision
- venv 里 mcp 锁在 1.x（mcp 2.x 把 FastMCP 改名了，别升级时不留意）

## 实测基准（2026-10-09，4 个真实临床入排案例）

用同一批患者数据对 `jev_yes_no` 两种题型做对照，结论是 **choice 优于 noul**：

| 案例 | 真实结论 | noul P(true) | choice | choice conf |
|------|:---:|:---:|:---:|:---:|
| eGFR 42，其余正常 | 应筛除 | 0.89 | yes | **0.96** |
| eGFR 88，全部阴性 | 可入组 | 0.04 | no | **1.00** |
| eGFR 47 + 未控高血压 | 模糊 | 0.41 | yes | **0.12** |

- **confidence 是真正的升级信号**。前两个清晰案例 conf >=0.96，第三个模糊案例 conf 塌到 0.12 —— 模型自己都不确定，这种时候就该转人工，而不是拿 0.41 的 noul 值硬做决定。
- **noul 没有这个信号**。它只给一个 0-1 的数，0.41 和 0.89 之间没有"我不确定"的出口。
- **建议**：需要路由（放行/转人工/升级）用 choice；需要给模糊案例打分排序时再用 noul。

### 反向标注的坑（已修）

`jev_yes_no` 之前把 "no" 选项自动生成成 `question + " (not supported)"`，实测会**拉低正面结论的置信度**：同一个 eGFR 42 案例，手写真实反向语句时 conf 0.98，用自动反向语句时只有 0.76。
现在改成：默认生成一个中性反向语句，但**支持 `no_text` 参数传你自己的反向语句**。规则是——能写清楚"什么情况下不成立"就自己写。

### selftest_modes.py

新增的回归脚本，跑真实 MCP stdio 握手 + 两种模式实调：

```
cd ~/.hermes/mcp-servers/jev-systemone && ./.venv/bin/python selftest_modes.py
```

注意：脚本必须在**该目录下**运行（`selftest.py` 同理），否则 `/tmp` 下同名的 `copy.py` 会遮蔽 stdlib。
