# AGENTS.md — Obsidian Vault（Codex 工作规则）

> 行为总则继承 `~/.agent-context/BEHAVIOR.md`（R1-R10）。本文件只补充 vault 专属约定。
> 更新: 2026-09-16（当前优先级 + 写作路由 + 工具现状）

## 当前优先级（2026-09 中）

1. **求职：精鼎FSP 头号线**（二面通过，待百济对接部门面试，薪资锁 18.2 万）+ GCP 干事金九银十多线批量投递 — 详见 `08-职业发展/AGENTS.md`
2. **股票投研**：日更/周检由 Hermes cron 产数据到 `01-股票投研/data/` 与 `日更/`，锚价调整在 `锚价调整_YYYY-MM-DD.json`；深度分析读数据不重抓
3. **临床试验系统维护**：274 项目/尼非卡兰见 `06-临床研究/`；Vault 巡检现为每周 `Vault健康巡检-` + 每日 `Vault每日巡检-` 双节奏

## 写作任务路由

- 单人材料（给 HR/领导/医生/医生）→ `job-resume-kit` 技能三步法；数字与用词先过 `08-职业发展/求职_口径红线.md`
- 多人通知/群发 → 保留 AI 精准风格，不做人味化
- 公众号/宣传稿 → `qu-ai-wei`，发前人工核对每条细节
- 书籍/长文 → `huashu-bookwriter`

## Vault 结构速览

- 主库: `/Users/xiashuang/obsidian/all about xia`（约 2500 个 md，git 管理）
- 分区: `00-系统`(工具/巡检) `01-股票投研` `02-玄学` `03-方法学与工具` `06-临床研究` `08-职业发展` `10-健康与成长` `11-生活管理` `12-CBT心理追踪`(CBT辅助日记/基线) `99-*`(归档/共享记忆) `inbox` `wiki`
- 共享记忆: `99-Agent共享记忆/` → `~/.agent-context/`（Hermes / Claude Code / Codex 三端同步）

## 读写规则

1. 先搜索后回答: 用 `rg` 按关键词在 vault 内检索，引用已有笔记，禁止凭空编造内容
2. 写笔记位置: 按分区语义放置（临床→06-临床研究，投研→01-股票投研，求职→08-职业发展）；临时/未分类放 `inbox/`
   - 音乐/影视/明星/审美/听后感等「奇思妙想」类内容 → 一律放 `99-奇思妙想/`（2026-09-25 用户指定，勿放 11-生活管理）
3. 不写 `.trash` `.archive` `.templates` `.sync/`（Hermes 忽略目录）
4. 程序产物（脚本/报告/图表/MD 文件）统一保存到移动硬盘 `/Volumes/夏爽/`，按内容放入对应分区：
   - 项目代码/脚本 → `/Volumes/夏爽/10_Projects_项目/`
   - 报告/文档/图表/总结 → `/Volumes/夏爽/00_Inbox_收件箱/`
   - 审评参考/SOP → `/Volumes/夏爽/00_SOP系统_审评参考/`
   - 系统工具/维护脚本 → `/Volumes/夏爽/90_System_系统/`
   - 存档 → `/Volumes/夏爽/30_Archive_存档/`
   - 用户另有指定路径时优先遵循；完成后在回复中报完整路径
5. 新笔记建议带 frontmatter: `tags` + `created`；改分区 AGENTS.md/规范前确认与共享记忆约定不冲突

## 工具分工与交接

- Codex（本会话）: 编码、脚本、深度分析；直接读写 vault 文件，改动分区文件前 git 提交
- Hermes Agent: 日常自动化、定时任务（cron）、消息推送；经文件直读 + Obsidian REST API(:27124) 操作 vault
- 交接: 重要结论写回 `99-Agent共享记忆/`（KNOWLEDGE / DECISIONS / ACTIVE_TASKS），另一方读取即恢复上下文
- 诊断: Hermes↔Obsidian 链路检查 `bash ~/.hermes/scripts/vault-link-check.sh`
- 语义检索: `obsidian-brain` MCP 已注册（18 工具）；vault_search 走 `rg`，语义问题优先 obsidian-brain

## GCP 临床研究工具台（临床/文献/审评任务必读）

- 位置: `~/.hermes-web-ui/coding-agent/workspace/default/custom_token.sensenova.cn/`
- 用法与入口见 `06-临床研究/AGENTS.md` 任务路由；MCP 工具清单见下方。
- MCP: `gcp-clinical`（17 工具: `vault_search` / `vault_read_note` / `vault_list_category` / `pubmed_search` / `clinicaltrials_search` / `pubchem_search` / `ich_gcp_get` / `get_checklist` / `nmpa_guidance_search` 等），已注册于 `~/.codex/config.toml`
- 知识库: 80 项临床清单（study-design-guides/templates/process-management/workflows/references，见 `clinical-trial-manifest.json`）+ 审评知识库 `extra/regulatory_kb/`（外置硬盘 `/Volumes/夏爽/00_SOP系统_审评参考/`）
- 本地命令: `python3 scripts/knowledge_base.py search "终点"` / `python3 scripts/sync_regulatory.py status`

## 完成定义
任务完成 = 结论 + 数据出处/来源 + 文件路径 + 验证结果，四者齐全；分区 AGENTS.md 可加严不加宽。
