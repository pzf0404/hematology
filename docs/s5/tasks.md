﻿# S5 任务清单（对应 spec.md）

## T0 探针：验证 StringTransform + VariableAggregator 注入 body  ✅ 已通过
- 实测结果（2026-11-11）：
  - `string:0.result` = `{"disease_route":"AML","query":"AML FLT3","max_hops":2,"limit":3}`（`{{begin:0@query}}` 被正确解析）
  - `agg:0` 输出键含 `body`，值与 string 结果一致
  - `invoke:0` 无 error，result 为 JSON：`matched_entities=6`、`paths=3`、`evidence_types={"knowledge_graph":true,"guideline_text":false}`、`context` 869 字符
  - 结论：主方案成立，零源码改动。注意：KG API 的 evidence 是图谱边列表，`guideline_text` 由 Retrieval 节点提供。
- 前置细节：`StringTransform.delimiters` 在 API 层必须是数组（如 `[","]`）；UI 合并模式下为单选，保存后需复验 DSL 类型。
- 执行步骤（本机 API 探针）：
  1. 登录拿 token：`POST http://127.0.0.1:9380/api/v1/auth/login`（openssl 加密 `base64(明文)`，token 在响应头 Authorization）。
  2. `POST /api/v1/agents` 创建临时画布，DSL：
     - `begin:0` Begin
     - `string:0` StringTransform：`method=merge`，`delimiters=","`，`script={"disease_route":"{{begin:0@query}}","query":"{{begin:0@query}} FLT3","max_hops":2,"limit":3}`
     - `agg:0` VariableAggregator：`groups=[{"group_name":"body","variables":["{{string:0@result}}"]}]`
     - `invoke:0` Invoke：`url=http://hematology-kg-api:8000/v1/kg/context`、`method=POST`、`headers={"Content-Type":"application/json"}`、无 body
     - `message:0` Message：`content=["{{invoke:0@result}}"]`
  3. `POST /api/v1/agents/{id}/run`（不带 session_id，body `{"user_input":"AML"}`）。
- 通过条件：invoke 无 error；result 为 JSON；`matched_entities` 非空；`evidence.knowledge_graph` 与 `evidence.guideline_text` 均存在。
- 失败则停机，向用户报告并请求是否启用 spec.md 第 3 节备选方案。
- 清理：`DELETE /api/v1/agents/{id}` 删除临时画布。

## T1 输出 UI 点选步骤  ✅ 已输出（画布已于 2026-11-11 搭建完成，见 T2/T3）
- 按 spec.md 第 5 节，把画布内实际节点 ID 代入后发给用户（逐步、精确字段/取值）。
- 明确告知：HTTP 请求节点参数表**不要**加 body。

## T2 用户搭建完成后复验 DSL  ✅ 已通过
- 实测（2026-11-11 16:2x）：画布 `hematology_kg_rag_v1`（id `e75a102daebc43d3b327e0c64b3b0de4`），9 节点拓扑与 spec 第 5 节一致；Invoke 无 body；StringTransform merge + 合法 JSON；VariableAggregator 组名 `body`；Retrieval `7295cb...` + `keywords_similarity_weight=0`（vector 1.0，2026-11-12 已调为 0.3，见 T3 扩充）；三个 Agent 的 `llm_id=1a467ebc...`（tenant_model UUID，经 `resolveTenantModelByID` 解析为 `qwen3-vl-plus`/`Tongyi-Qianwen`/`hematology`）。
- 快照：`docs/s5/dsl_snapshot.json`；逐项对照表见 `docs/s5/acceptance.md` 第 1 节。
- `GET /api/v1/agents` → `GET /api/v1/agents/{id}`，核对：
  - Invoke：url/method/headers/timeout 正确，params 无 body；
  - StringTransform：method=merge、script 为合法 JSON、引用指向正确节点；
  - VariableAggregator：组名 body、引用 string 的 result；
  - Retrieval：知识库 id=7295cb112d764d6faf0d58492e3a3262、`vector=0.7 / keywords=0.3`、`top_n=12`、`similarity_threshold=0`；
  - 模型三段式 `qwen3-vl-plus@hematology@Tongyi-Qianwen`。
- 保存 DSL 快照到 `docs/s5/dsl_snapshot.json`（脱敏后）。
- 2026-11-12 11:04 补充：最终 Agent `sys_prompt` 由默认模板改为领域提示（证据优先、禁止仅凭图谱边下结论、固定三段式、不评述），用户提示追加同义约束；快照已刷新至 `update_time=1794452646043`。
- 2026-11-12 11:23 补充：`Agent:KhakiPoetsSend.cite` 由 `true` 改为 `false`（`update_time=1794453822437`）。原因：`cite=true` 会注入 RAGFlow 内置“给输入文本补标引用”的系统提示，实测回答以「您的文本整体严谨…最小必要修改」开头、R10 只输出第 1 段；关闭后直接输出 `### 1) 结论` 三段，`[ID:<chunk_id>]` 行内保留。前两个 Agent 的 `cite` 保持 `true`。
- 2026-11-12 14:33 补充：`Retrieval:FluffyCoinsMatter.top_n` 由 8 改为 **12**（`update_time=1794465200198`），用于召回 25 条中治疗章节靠后的 chunk（如 R11 的 `7a7e87f677742f1c`）。
- 2026-11-12：`cite=false` 与领域提示经 API 设置并通过 `update_time=1794478995564` 复核；`dsl_snapshot.json` 当时已刷新为该版本（后续见下方 11-13/11-16 两条）。前端旧缓存可能回写，改完须关闭页面并用 API 复核。
- 2026-11-13 17:12：`Agent:KhakiPoetsSend.sys_prompt` 扩写为 **787 字**（增加表格、分层维度、剂量/疗程与年龄一致性要求）。
- 2026-11-16 09:16/09:36：画布两次自动保存，`cite=false`、`sys_prompt` 787 字、检索参数均未被回退（该次保存 `update_time=1794792978481`；该值随前端自动保存变动，内容经 DB 直查与复跑复核未变；2026-11-17 15:54 再次自动保存为 `1794902055806`，见下条）；`dsl_snapshot.json` 已按当前线上 DSL 刷新。

## T3 运行 5 条验收案例  ✅ 已通过（5/5）
- 实测：AML/APL/ALL/CML/AA 全部 `HTTP 200`，9 节点 `error=null`；`paths` 均 5 条；Retrieval `formalized_content` 3501–11059 字、chunks 8。
- 记录：`docs/s5/acceptance.md`；精简 SSE：`docs/s5/runs/{AML,APL,ALL,CML,AA}.sse`；完整答案存档：`docs/s5/runs/answers/{AML,APL,ALL,CML,AA}.md`（问题、判定基线、KG 路径明细、chunk 来源、回答原文、自检）。
- 口径说明：KG 接口 `evidence_types.guideline_text` 恒 false，指南证据按 Retrieval 输出判定（与 T0 结论一致）。
- 扩充（对应第十八章 ≥25 条）：`tests/acceptance_cases_ragflow.json` 定义 R01–R25，批量执行 **25/25 PASS**（结构判定）；报告 `docs/05_acceptance_test.md`，存档 `docs/s5/runs/answers_r25/`。
- 修复后重跑（2026-11-12）：① 路径方向——`api/app/main.py` 的 `path_brief()` 按关系 `subject_id/object_id` 还原节点顺序，实测 0 处不一致；② 检索噪声——`keywords_similarity_weight` 0→0.3（阈值方案经实测否决：相关/不相关分数重叠），`top_n=8` 时同病种 chunk 150/200（kw=0 时 123/200）；③ 最终 Agent——`sys_prompt` 改领域提示、`cite=false`（消除 RAGFlow 内置引用助手提示导致的「您的文本…最小必要修改」元叙述）；④ 检索召回——`top_n` 8→12（2026-11-12 14:33）。11-12 批次全量重跑 **25/25 PASS**：每条 12 chunks，回答合计 44,810 字、均含固定三段，其中 21 条实质作答、4 条证据优先弃答（R03/R07/R18/R19），期望来源 chunk 198/300、同病种 206/300；该批次存档已于 2026-11-16 被全量复跑结果替换，见下条；该批次 DSL 快照为 `update_time=1794478995564`；后续 2026-11-16 刷新为 `1794792978481`、2026-11-17 15:54 自动保存为 `1794902055806`（见 T2 与下文）。
- 页面同步（2026-11-12 10:2x）：API 改值会被打开中的画布以旧状态写回，最终在画布 UI 内改为 0.30 保存；面板显示 full-text 0.30 / vector 0.70，API 复验 `keywords_similarity_weight=0.3`、`update_time=1794450069074` 一致。UI 保存会把查询变量写成 `…} /`（API 去掉后被页面写回，属前端形态），实测对检索无影响（R19 两次运行 chunk 组成一致、无 error）。
- 2026-11-17 10:43–10:47 全量复跑（当前配置：787 字提示、`cite=false`、`top_n=12`、`kw=0.3`）：**25/25 PASS**；路由 25/25；路径 5–11 条；每条 12 chunks；期望来源 198/300、同病种 214/300（11-16 为 206/300）；回答合计 **80,063 字**（2,139–4,674），24 条实质作答、1 条证据优先弃答（R14）；`[ID:]` 392 个**全部可回溯**（R02 于 11:27 单条重跑，消除原 `xxx` 占位）、无虚构真实格式 ID；9 节点 `error` 全空；`docs/s5/runs/answers_r25/` 已替换为本次结果。11-16 批次（82,917 字、21 实质 + 4 弃答）数字保留在 `docs/05_acceptance_test.md` 第三节历史对照；11-17 批次明细见 `docs/s5/acceptance.md` 第 8.1 节。
- 2026-11-18 16:58–17:15 新基线（Monarch 2026-11-11，Neo4j 128,783 节点 / 284,023 边）全量复跑（配置同上，`update_time=1794902055806`）：**25/25 PASS**；路由 25/25；路径 5–11 条；每条 12 chunks；期望来源 200/300、同病种 208/300；回答合计 **78,735 字**（2,026–4,834），22 条实质作答（R03/R14 为限定条件下部分作答）、3 条证据优先弃答（R07/R18/R19）；`[ID:]` 400 次全部可回溯（398 次命中 chunk，涉及 86 个不同 chunk ID；2 次命中 `paths` 内 `edge_id`），无虚构 ID；9 节点 `error` 全空；`docs/s5/runs/answers_r25/` 已替换为本次结果（R18 于 17:15 单条重跑）。
- `POST /api/v1/agents/{id}/run`，保存 SSE 到 `docs/s5/runs/{case}.sse`（截断到证据摘要）。
- 判定：invoke result 可解析；knowledge_graph.paths 非空；guideline_text 非空；最终回答与病种一致；无 error。
- 产出 `docs/s5/acceptance.md`。

## T4 截图归档  ✅ 已完成
- `docs/s5/screenshots/`：`01_canvas.png`（整体画布）、`02_invoke.png`（HTTP 请求配置）、`03_retrieval.png`（知识检索配置）、`03b_retrieval_advanced.png`（高级设置）、`04_result.png`（R01 运行结果）、`05_final_agent.png`（最终 Agent 787 字系统提示）、`05b_final_agent_settings.png`（Show citations 关闭）。
- 索引与逐图对照见 `docs/s5/acceptance.md` 第 5 节。
- 用户提供 4 张截图（画布/ Invoke / 检索 / 运行结果），存入 `docs/s5/screenshots/` 并在 acceptance.md 引用。
- 2026-11-12 10:21 复拍 `03_retrieval.png`：替换调整前（0.00/1.00）旧图，现显示 full-text 0.30 / vector 0.70，页面 `Autosaved 12/11/2026 10:21` 与库 `update_time=1794450069074` 对应。
- 2026-11-12 14:45 复拍 `03b_retrieval_advanced.png`：Top N 由 8 改为 **12**（Rerank candidates 64、Rerank model 空），与 `top_n=12` 一致。
- 2026-11-16 09:12–09:16 本机 Edge 重拍全部 7 张：`01_canvas`、`02_invoke`、`03_retrieval`、`03b_retrieval_advanced`（Top N 12、0.30/0.70）、`04_result`（本次 UI 运行，`cite=false`、正文 `[ID:]`）、`05_final_agent`（787 字提示）、`05b_final_agent_settings`（Show citations 关闭）。

## T5 文档收尾（S6）  ✅ 已完成
- 已新建 `docs/04_ragflow_integration.md`：画布 9 节点参数表、零改动注入 body 原理、模型 UUID 引用解析、已知限制（含 UI 登录 base64 口令口径）、验收与截图索引、复验命令。
- `docs/04_ragflow_integration.md` 增加：
  - 零改动注入 body 的节点组合与原理；
  - 已知限制（Invoke 无 body/不解析模板、CodeExec 沙箱不可用、rerank 不可用、混合检索权重 0.3、模型引用 UUID（三段式解析）、ai-network/ALLOW_ANY_HOST）；
  - 5 条验收记录与截图索引。

## 阶段 5 交付对照（任务指引第十四、十五、二十一、二十二章）

| 要求 | 证据 | 状态 |
|---|---|---|
| HTTP Request 接入 KG API | `Invoke:ShortStampsShare`：`POST http://hematology-kg-api:8000/v1/kg/context`、timeout 30、`Content-Type: application/json`；运行日志 `invoke` 无 error | 完成 |
| 结果传递（第十五章：先用 content/解析节点） | `StringTransform` script 用 `{Agent:AfraidSpidersOccur@content}`/`{Agent:QuietBugsAccept@content}` 拼 body；`VariableAggregator(group_name=body)` 注入 Invoke；最终 Agent 提示同时含 `{Invoke:ShortStampsShare@result}` 与 `{Retrieval:FluffyCoinsMatter@formalized_content}` | 完成 |
| 端到端问答 | 5 条（`docs/s5/acceptance.md`）+ 25 条（`docs/05_acceptance_test.md`，25/25 PASS；当次 DSL 抽验 5 例全通过） | 完成 |
| RAGFlow 配置截图 | `01_canvas`、`02_invoke`、`03_retrieval`（0.30/0.70）、`03b_retrieval_advanced`（Top N 12）、`04_result`（本次 UI 运行）、`05_final_agent`（787 字提示）、`05b_final_agent_settings`（Show citations 关闭），均 2026-11-16 09:12–09:16 重拍 | 完成 |
| 两类证据区分（第二十二章） | 最终 Agent 提示分块「知识图谱证据（JSON）」「指南原文证据」，回答固定「结论 / 依据的图谱路径 / 引用的指南原文」；`evidence_types` 字段单独输出 | 完成 |
| 页面与 DSL 一致 | `dsl_snapshot.json` 与 API 一致（2026-11-19 回滚后 `update_time=1795055089414`，`cite=false`，`sys_prompt` 787 字，9 节点）；前端旧缓存可能回写，改完须关闭页面并用 API 复核 | 完成 |

