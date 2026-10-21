---
name: jev-systemone
description: >-
  Jev 快判断模型（MCP 工具已接入）：给结构化 state + 类型化问题，返回选项/分数 + 概率 + 置信度。
  定位是「第二意见 + 转人工触发器」，不是决策者。五个工具 jev_decide / jev_yes_no /
  jev_guard_tool_call / jev_route / jev_front_door；三种题型 choice / score / noul。
  适用：批量初筛（入排初筛、EDC 缺口排优先级）、破坏性动作前读概率尾部、
  当我需要一个可复现的外部判断参照时。
  不适用：确定性检查工作（路径是否存在、JSON 能否解析——用 test/jq，别问概率模型）、
  需要新信息（它只能看到我序列化给它的 state，不能补充任何新事实）、
  医疗或投资的最终决策（概率供人拍板）。
  触发词：jev、jev 判断、jev 打分、systemone、快判断、判断模型、概率判断、
  入排初筛、缺口优先级、批量初筛、guard、工具守卫、放行还是转人工、要不要转人工。
trigger_keywords: ["Jev", "快判断", "决策", "第二意见", "yes_no", "choice", "score", "noul"]

---

# jev-systemone — 快判断模型用法与参数

Jev 不是对话模型，走 `POST /v1/systemone`（不是 `/v1/chat/completions`，那个全 400）。
输入「状态 + 类型化问题」，输出「选项/分数 + 概率 + 置信度」。不流式，body 上限 32 KiB，
32k 上下文，无 vision，0 元定价。单次 ~2-5s、~400 input tokens。

MCP server：`~/.hermes/mcp-servers/jev-systemone/`（Hermes/Codex 共用一份 server.py + .key）。
Codex 注册在 `~/.codex/config.toml` 的 `[mcp_servers.jev-systemone]`。

## 五个工具与参数

Codex 里工具名带命名空间前缀 `mcp__jev_systemone__`；Hermes 里是 `mcp_jev_systemone_`。

### jev_decide(state, questions, model="jev")

原生决策。`state` 是 dict（也可以是字符串或文本数组，三种都实测通过），
`questions` 是「问题名 → 题型定义」的 dict，可一次问多题。

### jev_yes_no(state, question, no_text=None, mode="choice", model="jev")

是否判断。`mode="choice"`（默认）返回选项 + confidence；`mode="noul"` 返回裸概率。

**`no_text` 要自己写。** 它是反向陈述句，不传则自动拼一个中性反向语句。
实测：同一个正面案例，手写真实反向语句 conf 0.98，自动拼只有 0.76。
能写清「什么情况下不成立」就自己写，这是精度最便宜的一次提升。

### jev_guard_tool_call(tool, action, arguments_summary, side_effects, safeguards, policy, reversibility, model="jev")

工具守卫。**只给建议，不执行任何东西。**
`arguments_summary` / `side_effects` / `safeguards` / `policy` 是字符串数组，
`reversibility` 取 `reversible` / `partially_reversible` / `irreversible`。

### jev_route(task, options=None, model="jev")

任务路由器。默认三档 `light` / `heavy` / `jev`（翻译格式化摘要=light；
方案设计审计风控综合写作=heavy；纯数值或二值单步判断=jev）。
也可以传自己的候选方案 `options={标签: 描述}`（2-255 个标签）让它仲裁。

**它只仲裁，不发明候选**：自定义方案的好坏取决于写 options 的人。
**各选项描述长短要对齐**：它偏向写得最长最详细的那个。
实测（同一任务、两个候选，只把 B 写长）：B 拿到 0.95、A 只剩 0.05。
延迟 ~2.8-8.6s。

### jev_front_door(task, model="jev")

一次调用决定「这件事该谁做」：先问 jev 这是不是单步数值/二值判断，
是 → `route="jev_native"`（改用 jev_yes_no / jev_decide，0 成本 ~2s）；
否 → `route="openrouter"`（调 jev CLI 从 332 个模型的池子里挑档）。
依赖 `~/.hermes/jev-skills` 检出（该路径已稳定，不要改成 /tmp）和三个环境变量，
server.py 会自动注入；CLI 默认超时对 bynara 太短，这里固定传 `--timeout 60`。

**返回信封和另外四个工具不一样**：它返回
`{gate, gate_raw, route, hint}`，**没有顶层 `ok`，也没有 `answers`**。
实测 `task="计算 383 个病例里已完成 EDC 录入的占比"` →
`route="jev_native"`、`hint` 提示改用 jev_yes_no / jev_decide。
判成功要看 `route` 字段；按 `{ok, answers}` 去读会误判成失败
（本条就是先误判了一次才查出来的）。

> 路由类工具的 docstring 自己写了「trust `choice`, not confidence」。
> 和我在 decide/yes_no/guard 上测到的「confidence 会在模糊处塌陷」并不矛盾：
> 前者是说别拿 confidence 排序取优，后者是说它能当「这条别硬判」的开关。
> 用法上分开看：判断题信 confidence 的塌陷，路由器只信 choice。

## 题型格式（最容易记反的三条）

一个问题的值长这样：`{"type": "...", "criteria": ...}`

- **choice**：`criteria` 是**对象**，**键 = 选项名**（2-255 个），值写「该选项适用时的描述」。
- **score**：`criteria` 是**数组**，第 0 个元素 = 问题字符串，后面 2-10 个 = 档位名。
- **noul**：**不用 criteria**，用 `instructions` 字段写是非陈述句 → 返回 `noul: 0-1`，**无 confidence**。

返回形状：choice → `{choice, confidence, probabilities{选项: p}}`；
score → `{score, confidence, legend{序号: 档位}, probabilities{序号: p}}`；
noul → `{noul}`。外层统一是 `{ok, model, answers, usage, request}`。

## 可直接抄的模板

入排判断（choice，带手写反向语句）：

```json
{"state": {"age": 68, "egfr": 42, "bp": "128/78",
           "exclusion": ["eGFR<45", "未控制的高血压", "5年内恶性肿瘤史"],
           "malignancy_history": "无"},
 "questions": {"screen": {"type": "choice", "criteria": {
     "yes": "该患者符合排除标准，应当筛除",
     "no": "逐条核对后所有排除标准均为阴性，可以入组"}}}}
```

批量缺口排优先级（score）：

```json
{"questions": {"triage": {"type": "score", "criteria": [
    "这份 EDC 数据缺口应该优先补录吗？",
    "紧急-阻塞统计分析", "高-影响主要终点", "中-仅影响可读性", "低-可忽略"]}}}
```

破坏性动作前问一轮（guard）：

```
tool="batch_file_rename", action="批量 mv 40 个病历 md 并改名",
side_effects=["改动 40 个文件路径","wiki-link 可能失效"],
safeguards=["先 git tag 基线","dry-run 映射表","复扫验证"],
reversibility="partially_reversible"
```

## 能力边界（11 次实调 + 5 次重复性测试，别越过这几条）

**可信的部分。** 事实核对很准。给结构化指标做入排判断，清晰案例 conf ≥0.96；
反向对照（全部阴性的健康受试者）正确返回 no/conf 1.00，不是关键词匹配。
同输入近乎确定性：5 次重复 argmax 5/5 一致，conf 波动 ±0.05。

**`confidence` 塌陷是最有价值的输出。** 真正模糊的案例（eGFR 47 卡阈值 + 血压 151/94）
conf 掉到 0.12，而清晰案例是 0.96/1.00。低 conf 就转人工，别拿它硬判。
我自己在这类案例上倾向照样给出笃定答案，所以这个信号值得外部来给。

**guard 的结论词不可信。** 同一动作把可逆性改成 irreversible 且无 git 回滚后，
argmax 仍是 confirm，只有升级概率质量从 0.11 移到 0.45。
**读概率分布，不要读 allow/deny 这个词。**

**对措辞敏感。** 同一场景换个写法，结论在 review 和 confirm 之间跳；但同输入是稳定的。
也就是说它是我 `criteria` 写法的函数——我框架写歪，它就照着歪，等于把我的偏见复读给我。
所以它能做初筛，不能当硬门禁。

**score 的标量跨量表不可比。** 同一判断、档位正反序两种写法得 1.49 和 2.93，
但概率质量都压在同一个档位标签上。**只读 `probabilities`，别读 `score`。**

**choice 优于 noul。** 同批案例：choice 给 0.96 / 1.00 / 0.12（清晰/清晰/模糊），
noul 给 0.89 / 0.04 / 0.41。两者分开得都对，但 noul 没有「我不确定」这个出口。
要路由（放行/转人工）用 choice；要打分排序再用 noul。

## 与 probvote 的分工

两个都在做概率判断，别混：jev 是单个外部模型、免费、~2-5s，适合逐条初筛；
probvote 是 K 家模型投票 + 校准回流、能出 `disagreement`，适合需要跨模型一致性和
历史校准回流的批量决策。要「一个数 + 一个别信标记」用 jev，
要「多家是否同意 + 校准后的权重」用 probvote。

## 自检

```bash
cd ~/.hermes/mcp-servers/jev-systemone && ./.venv/bin/python selftest_modes.py
```

四个脚本各司其职（都必须在该目录下运行，否则 `/tmp` 下同名 `copy.py`
会遮蔽 stdlib `copy` 并让 mcp 导入失败）：

- `selftest.py` — 协议层握手 + 单模式实调
- `selftest_modes.py` — choice / noul 两模式回归（含 `no_text` / `mode` 新参数）
- `noise_check.py` — 同输入重复性（5 次，看 argmax 与 conf 抖动）
- `selftest_skill_examples.py` — 校验本文件里的 JSON 模板仍打得住（改了题型或模板后跑）

## 配额：每分钟约 17-18 次，超了就整窗 429

实测（清空窗口后不间断连发 58 秒）：总共发出 21 次，前 **17 次全成功**，
之后 **4 次全是 429 `Per-minute request limit reached for your plan`**。
配额是按分钟计的硬上限，不是软节流——撞线后这一分钟剩下的请求全部失败。

**批量初筛必须自己控速**：

- 安全节奏 **~4 秒/次（≈15 次/分钟）**，留一点余量
- 40 个病例的入排筛 → 约 3 分钟；383 个 → 约 17 分钟，适合放 cron 夜间跑
- `429` 要**退避重试**（`noise_check.py` 已实现：`WAIT * (attempt+1)`，最多 4 次），
  不要当成失败丢弃，也不要当成"判断不稳定"
- 单次判断别并行扇出超过 ~10 路

出现过一次「5 连发中 4 次失败」，当时误记成"偶发抖动"，真因就是这个配额。
`noise_check.py` 现在会把配额/传输失败显式标成 `TRANSPORT_FAIL`，
不再伪装成 `choice=None` 污染稳定性结论。

已知坑：venv 里 mcp 锁在 1.x（2.x 把 FastMCP 改名了，别随手升级）。
改了 `server.py` 要重启 Codex 会话才会加载新代码，当前进程仍跑旧版。
原文件备份 `/tmp/jev_server_pre_patch_20261009.py`。
