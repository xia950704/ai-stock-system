# Agent Workspace Rules

统一的 agent 产物与 session 归档制度。适用于本机所有 agent：ChatGPT Desktop（bundle `com.openai.codex`）、HermesAgent、ekkoagent、ekkoagent 所带 Claude Code、以及 Codex 自身。

## 写入位置

- 所有新产物必须写入 `_inbox/` 或 `projects/<项目>/artifacts/`
- 禁止在桌面、下载、home 根目录、项目根目录直接写 `.py` / `.md` / `.ipynb`
- 临时文件写入 `projects/<项目>/scratch/`，7 天内清理

## Session 归档

- session 归档统一放 `sessions/<source>/archive/`
- 命名遵循 `{source}_{date}_{sid8}_{slug}.{ext}`
- 原始 session 数据只读，不移动、不删除
- `<source>` 取值固定为 `chatgpt-desktop` / `hermes-agent` / `ekkoagent` / `claude-code`
- 结构化记录文件（`.jsonl`、`.json`、`.zst`、SQLite 快照）的元数据写进同名 `.meta.yaml` sidecar，不往文件头部塞 frontmatter——那会让 JSONL 和 JSON 失去可解析性。Markdown 类文件仍使用真正的 YAML frontmatter。需要内联时用 `organize.py --frontmatter inline` 或 `both`
- ChatGPT Desktop：`/Applications/ChatGPT.app` 与 Codex 桌面端是同一个 App（bundle id `com.openai.codex`），因此 `~/.codex/sessions/` 的 rollout 归入 `sessions/chatgpt-desktop/archive/`，其元数据固定携带 `bundle_id` 与 `note` 两行以保留这一判定依据

## 只读区

- `reference/` 只读
- `sessions/` 只读，除非新增归档
- `_archive/` 只读

## _inbox 生命周期

- `_inbox/` 文件 7 天内必须归档或删除
- 移入的散落文件保持原名，冲突时追加 `__YYYYmmdd_HHMMSS`

## 安全边界

- `organize.py` 不删除任何原始 session，不使用 sudo，不写系统目录
- 敏感文件一律排除：`.env*`、`auth.json`、`settings.json`、`.token`、`secrets/`、`*.bak*`、`*.key`
- 跨卷移动一律先复制、校验 sha256，再删除原文件
- 活跃 SQLite 库通过 backup API 做在线一致性快照，禁止裸 `cp`

## 任务结束

每次任务结束输出：

- 产物路径列表
- 是否需要归档
- 是否有散落文件需要移入 `_inbox/`

## 日常守则（待启用）

以下四条本轮未启用，留作后续开启依据。launchd 定时任务尚未安装。

<!--
- 外置卷根（/Volumes/*）禁止直接写文件，需要落盘时软链到 _inbox/unsorted/
- ~/.codex/sessions/ 快照保留最近 3 个版本，更早的转入 _archive/
- 每周一 09:00 由 launchd 跑 organize.py --apply --quiet，仅整理 _inbox 和散落文件
- 任何 agent 在 home 根目录写出 .md/.py 前必须先询问
-->
