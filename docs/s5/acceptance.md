# S5 验收记录（RAGFlow 智能体 hematology_kg_rag_v1）

- 画布：`hematology_kg_rag_v1`，agent_id `e75a102daebc43d3b327e0c64b3b0de4`
- 复验方式：`GET /api/v1/agents/{id}` 取 DSL（快照见 `dsl_snapshot.json`），`POST /api/v1/agents/{id}/run` 逐条运行
- 运行时间：2026-11-11 16:2x～16:3x（首次 5 例）；2026-11-16 09:19 复跑 R01，11:38–11:56 以当前配置（787 字领域提示、`cite=false`、`top_n=12`）全量复跑 R01–R25；2026-11-17 10:43–10:47 以同一配置再次全量复跑；2026-11-18 16:58–17:15 在 Monarch 2026-11-11 新基线上全量复跑（本文件第 7–8 节为本批次结果，11-17 批次数字见 8.1 对照）（Asia/Shanghai）
- 精简 SSE：`runs/{AML,APL,ALL,CML,AA}.sse`（保留 workflow/node 事件，Retrieval 仅保留 `formalized_content` 前 1500 字与 chunks 数量）
- 截图：2026-11-16 09:12–09:16 由本机 Edge 打开画布重拍，见第 5 节

## 1. DSL 复验（对照 spec.md 第 5 节）

| 检查项 | 规格要求 | 实测 DSL | 判定 |
|---|---|---|---|
| 节点拓扑 | Begin→查询规划→检索词→(Retrieval ∥ String→Agg→Invoke)→最终分析→Message | `begin`→`Agent:AfraidSpidersOccur`→`Agent:QuietBugsAccept`→{`Retrieval:FluffyCoinsMatter`, `StringTransform:ChattyNailsVisit`→`VariableAggregator:EightDonutsAttend`→`Invoke:ShortStampsShare`}→`Agent:KhakiPoetsSend`→`Message:RealCornersLook` | 通过 |
| Invoke URL/Method/Timeout/Headers | `http://hematology-kg-api:8000/v1/kg/context`、POST、30、`{"Content-Type":"application/json"}` | `url=http://hematology-kg-api:8000/v1/kg/context`、`method=POST`、`timeout=30`、`headers={"Content-Type":"application/json"}` | 通过 |
| Invoke 参数表 | **不得**出现 body | `params` 键为 `clean_html/headers/method/outputs/proxy/timeout/url/variables`，**无 body** | 通过 |
| StringTransform | merge；script 为合法 JSON；引用指向查询规划与检索词节点 | `method=merge`、`delimiters=[","]`、`script={"disease_route":"{Agent:AfraidSpidersOccur@content}","query":"{Agent:QuietBugsAccept@content}","max_hops":2,"limit":30}`；`json.loads(script)` 成功 | 通过 |
| VariableAggregator | 组名 `body`，引用 StringTransform.result | `groups=[{"group_name":"body","type":"string","variables":[{"value":"StringTransform:ChattyNailsVisit@result"}]}]` | 通过 |
| Retrieval | 知识库 `7295cb112d764d6faf0d58492e3a3262`；混合检索关键词权重 0.3；`top_n=12` | `dataset_ids=["7295cb112d764d6faf0d58492e3a3262"]`、`keywords_similarity_weight=0.3`（vector=0.7）、`similarity_threshold=0`、`top_n=12`、`rerank_id=""`（权重 2026-11-12 由 0 调整；`top_n` 同日 14:33 由 8 调整，见第 7 节） | 通过 |
| 最终分析 Agent 提示 | 两路证据注入 + 证据优先规则 + 固定三段式 | `sys_prompt` 已由默认模板改为领域提示（仅用两路证据；不得仅凭图谱边推断方案/剂量/适应证/预后；临床结论须由指南原文支撑；引用 `[ID:<chunk_id>]`；固定「结论 / 图谱路径 / 指南原文」三段）；2026-11-13 17:12 扩写为 **787 字**（增加表格、分层维度、剂量/疗程与年龄一致性要求）；用户提示末尾追加同义约束（2026-11-12 11:04 补齐，当前 `update_time=1794902055806`） | 通过 |
| 最终分析 Agent `cite` | 关闭（`false`） | `Agent:KhakiPoetsSend.params.cite=false`（当前 `update_time=1794902055806`，2026-11-17 15:54 画布自动保存，`sys_prompt` 787 字不变）。`cite=true` 时 RAGFlow 会注入内置引用助手系统提示（二进制原文：`Based on the provided document or chat history, add citations to the input text…` + `# Citation Requirements`），实测导致回答以「您的文本整体严谨…最小必要修改」开头、R10 仅输出第 1 段；关闭后直接输出 `### 1) 结论` 三段 | 通过 |
| 模型引用 | `qwen3-vl-plus@hematology@Tongyi-Qianwen` | 三个 Agent 的 `llm_id` 均为 `1a467ebc0df742e5961aff478759a048`（= `tenant_model.id`），经 `resolveTenantModelByID`（`internal/agent/component/llm_credentials.go#L192-260`）解析为 model=`qwen3-vl-plus`、provider=`Tongyi-Qianwen`、instance=`20169f6bf8c44c44972b0aa2de55e790`（`hematology`） | 通过（等价三段式；该版本 DSL 存 tenant_model UUID） |
| Begin | 输入变量 query | `mode=conversational`、`inputs={}`；`user_input` 由运行请求注入 `sys.query`（`handler/agent.go#L478-533`） | 通过（等价） |

## 2. 运行验收（5 例）

> 本节为 2026-11-11 首次运行记录（当时最终 Agent 仍用默认系统提示、`cite=true`）。2026-11-12 补齐证据优先规则并关闭 `cite` 后，已用 25 条全量重跑覆盖六个病种（见第 7 节与 `docs/05_acceptance_test.md`），5 例结论不变；差异仅回答篇幅（去掉了引用标注模式的复述）与个别弃答。2026-11-16 以当前配置全量复跑 R01–R25，见 `docs/04_ragflow_integration.md` 第 6 节与 `docs/05_acceptance_test.md` 第三节历史对照。

| 案例 | 用户问题 | 分诊输出 | disease_route | 图谱实体 ID | paths | context 字符 | Retrieval.formalized_content | chunks | 最终回答字符 | 节点 error |
|---|---|---|---|---|---|---|---|---|---|---|
| AML | AML 伴 FLT3 突变如何治疗 | `AML` | AML | MONDO:0018874 | 5 | 931 | 11059 | 8 | 5010 | 无 |
| APL | APL 急性早幼粒细胞白血病的诱导治疗方案 | `APL` | APL | MONDO:0012883 | 5 | 773 | 3609 | 8 | 3654 | 无 |
| ALL | 成人 ALL 费城染色体阳性如何选择靶向治疗 | `ALL` | ALL | MONDO:0004967 | 5 | 922 | 4446 | 8 | 3945 | 无 |
| CML | CML 慢性髓性白血病一线 TKI 如何选择 | `CML` | CML | MONDO:0011996 | 5 | 973 | 3501 | 8 | 2988 | 无 |
| AA | 重型再生障碍性贫血的免疫抑制治疗指征 | `AA` | AA | MONDO:0015909 | 5 | 818 | 6358 | 8 | 3110 | 无 |

判定口径（spec.md 第 6.3 节）：
1. Invoke `result` 可 JSON 解析 —— 5/5 通过（键：`disease_route/route_disease_ids/query/max_hops/limit/matched_entities/paths/evidence/evidence_types/context`）。
2. `paths` 非空 —— 5/5 通过（均为 5 条 SUBTYPE_OF 路径）。
3. 指南原文证据非空 —— 5/5 通过，取 Retrieval `formalized_content`（3501–11059 字）与 8 个 chunks。**注**：KG 接口自身 `evidence_types.guideline_text` 恒为 `false`（T0 已确认，健康检查口径见 tasks.md T0），指南证据由 Retrieval 节点提供，故此处按 Retrieval 判定。
4. 回答与病种一致 —— 5/5 通过（AML 含 FLT3；ALL 含 Ph；CML 含 TKI；AA 含免疫抑制；APL 含 ATRA/ATO/PML-RARα 方案）。
5. 无 `_ERROR`、无 GraphRunError —— 5/5 通过（9 个节点全部 `error=null`）。

## 3. 观察项（不构成验收失败）

- APL 最终回答开头出现 "您的回答结构严谨…现依据您提供的原始文本补标引用" 这类元叙述，属引用标注模式下的话术漂移；医学内容（ATRA+砷剂±蒽环）正确。2026-11-12 已定位根因：`cite=true` 会注入 RAGFlow 内置“给输入文本补标引用”的系统提示（二进制原文 `Based on the provided document or chat history, add citations to the input text…`）。已将 `Agent:KhakiPoetsSend.cite` 置为 `false` 并全量重跑，回答不再出现该元叙述，直接以 `### 1) 结论` 开头（代价：UI 不再渲染 `[1]…[n]` 编号卡片，回答内保留 `[ID:<chunk_id>]`）。
- `tenant_model.extra.verify` 对 `qwen3-vl-plus` 仍为 `fail`（历史验证标记），但运行链路 5/5 成功，说明不影响实际调用；如需消除，可在模型页重新点击验证。
- Retrieval chunk 元数据未带 `document_keyword`（取值为 `?`），引用卡片依赖 `chunk id` 映射；不影响召回与回答。

## 4. 结论

- 5/5 案例通过 spec.md 第 6/7 节验收判定；
- DSL 与 UI 配置一致，Invoke 无 body、body 由 StringTransform+VariableAggregator 注入；
- 零 RAGFlow 源码改动。

## 5. 截图索引（`docs/s5/screenshots/`）

| 文件 | 内容（2026-11-16 09:12–09:16 本机重拍） | 与规格对照 |
|---|---|---|
| `01_canvas.png` | 整体画布（fit view）：开始 → 查询规划 Agent → 检索词生成 Agent →（知识检索 ∥ 文本处理 → 变量聚合 `body` → HTTP 请求）→ 最终分析 Agent → 回复消息 | 与 spec 第 5 节拓扑一致，三个 Agent 均显示 `qwen3-vl-...` / `hematology` |
| `02_invoke.png` | HTTP 请求节点：Url `http://hematology-kg-api:8000/v1/kg/context`、方法 POST、超时 30 秒、请求头 `{"Content-Type":"application/json"}`、代理空、清除 HTML 关闭 | 与 spec 第 5.7 节一致；页面无 body 输入项（API 复验亦确认 params 无 body） |
| `03_retrieval.png` | 知识检索：查询变量 `检索词生成 Agent/content`、来源知识库 `hematology_guidelines_v1`、相似度阈值 0、关键词相似度权重 full-text **0.30** / vector **0.70** | 与 spec 第 5.4 节一致；API 同值为 `keywords_similarity_weight=0.3`、`similarity_threshold=0` |
| `03b_retrieval_advanced.png` | 知识检索高级设置：关键词权重 0.30/0.70、Rerank candidates 64、**Top N 12**、Rerank model 空、Cross-language search 空 | 与 spec 第 5.4 节一致（`top_n=12`、`rerank_id=""`） |
| `04_result.png` | R01 本次 UI 运行结果：从 `### 1) 结论` 开始，含 FLT3 分层表格与 `[ID:<chunk_id>]` 行内引用，三段齐全 | 当前 `cite=false`，不再渲染 `[1]…[n]` 编号卡片；与 API 复跑结果一致 |
| `05_final_agent.png` | 最终分析 Agent 系统提示：787 字领域提示（证据优先、两路证据、固定三段、表格/分层/剂量与年龄一致性要求） | 与 `sys_prompt` 实测 787 字一致 |
| `05b_final_agent_settings.png` | 最终分析 Agent 设置：**Show citations 关闭**、用户提示以「注意：临床结论必须有指南原文支撑，不得仅凭图谱路径下结论。」结尾 | 与 `cite=false`、用户提示约束一致 |

## 6. 完整答案存档（`docs/s5/runs/answers/`）

每条含：判定基线、前置节点输出、KG 路径明细、检索 chunk 来源与相似度、完整回答原文、自检。

| 文件 | 案例 | 回答长度 | 引用标记 | 路径 | chunks |
|---|---|---|---|---|---|
| `AML.md` | AML 伴 FLT3 突变治疗 | 5010 字 | `[ID:…]`×29 | 5 | 8 |
| `APL.md` | APL 诱导治疗 | 3654 字 | `[ID:…]`×33 | 5 | 8 |
| `ALL.md` | Ph+ 成人 ALL 靶向治疗 | 3945 字 | `[ID:…]`×23 | 5 | 8 |
| `CML.md` | CML 一线 TKI | 2988 字 | `[ID:…]`×16 | 5 | 8 |
| `AA.md` | 重型 AA 的 IST 指征 | 3110 字 | `[ID:…]`×20 | 5 | 8 |

说明：API 输出用 `[ID:<chunk_id>]`，UI 渲染为 `[1]`…`[n]` 引用卡片；5 条均完整结尾、`Message` 节点与最终 Agent 输出一致、9 节点 `error` 为空。

## 7. 扩充验收（25 条，第十八章口径）

为满足任务文档第十八章「至少 25 条固定问题，并写明期望命中实体/关系/来源」，新增 25 条用例并批量执行：

- 用例：`tests/acceptance_cases_ragflow.json`（R01–R25，AML 5 / APL 4 / ALL 5 / CML 4 / CLL 3 / AA 4）
- 报告：`docs/05_acceptance_test.md`
- 存档：`docs/s5/runs/answers_r25/R{01..25}.md`
- 结果：**25/25 PASS**（2026-11-18 新基线全量复跑；路由 25/25、路径非空 25/25、指南证据 25/25、回答 25/25 且均含固定三段、9 节点 `error` 全空；每条 12 chunks，回答合计 78,735 字。其中 22 条实质作答（R03、R14 为限定条件下部分作答）、3 条按证据优先规则弃答：R07/R18/R19；期望来源 chunk 200/300、同病种 chunk 208/300）
- 修复（2026-11-12）：
  - 路径方向：`api/app/main.py` 的 `path_brief()` 按 `subject_id/object_id` 还原节点顺序，实测 CLL 查询 9 条路径 0 处方向不一致；
  - 检索噪声：Retrieval 的 `keywords_similarity_weight` 由 0 调为 0.3（vector 0.7）。实测阈值方案不可行（相关 0.832–0.907 / 不相关 0.829–0.890 重叠），权重方案使同病种 chunk 达 150/200（`top_n=8`、kw=0 时 123/200）；0.5 会挤掉英文 ELN 指南（R04 失去 ELN 证据），故取 0.3。
  - 检索召回：`top_n` 由 8 调为 **12**（2026-11-12 14:33，UI 保存）。11-12 批次每条召回 12 chunks、期望来源 198/300、同病种 206/300；R11（ALL 诱导方案药物组成）由弃答转为实质作答；17:14 恢复配置重跑后 R14 亦转为实质作答，当时弃答为 4 条（R03/R07/R18/R19）。
  - 最终 Agent：`sys_prompt` 改为领域提示（证据优先、禁止仅凭图谱边下结论、部分覆盖先答支持部分并标注缺口、固定三段），`cite` 改为 `false`（关闭 RAGFlow 内置引用助手提示，消除「您的文本…最小必要修改」元叙述）。改后全量重跑，存档与报告已按重跑结果更新。
  - 快照：2026-11-19 回滚后当前线上 DSL `update_time=1795055089414`，内容与 11-18 批次一致（`cite=false`，787 字）；前端旧缓存可能回写，演示前用 API 复核。
  - 页面同步：检索权重 0.30/0.70 与 Top N 12 已在 UI 复验；以 API 快照为准（`top_n=12`、`kw=0.3`、`cite=false`、787 字）。

## 8. 2026-11-18 新基线复核（本机）

- 线上配置（API 复核）：`update_time=1794902055806`（2026-11-17 15:54 前端自动保存，内容与 11-16 一致）：9 组件；`Agent:KhakiPoetsSend.cite=false`、`sys_prompt` **787 字**、`user_prompt` 为空（UI 使用 `prompts` 数组）；`Retrieval:FluffyCoinsMatter`：`top_n=12`、`keywords_similarity_weight=0.3`、`similarity_threshold=0`、`rerank_id=""`。
- 数据基线：Monarch 2026-11-11，Neo4j 128,783 节点 / 284,023 边；`/v1/kg/context` 返回路径的 `source_version` 为 `2026-11-11`。
- 知识库：`7295cb112d764d6faf0d58492e3a3262`（`hematology_guidelines_v1`），10 文档 / 384 chunks（MySQL `knowledgebase.doc_num/chunk_num` 实测一致）。
- 全量复跑（2026-11-18 16:58–17:15，本机直连 `POST /api/v1/agents/.../run`，串行；R18 于 17:15 单条重跑）：
  - 结果 **25/25 PASS**；路由 25/25；路径 5–11 条；每条 12 chunks；期望来源 200/300（11-17 为 198/300）、同病种 208/300（11-17 为 214/300）；
  - 回答合计 **78,735 字**（单条 2,026–4,834 字），22 条实质作答（R03、R14 为限定条件下部分作答）、3 条证据优先弃答（R07/R18/R19）；
  - `[ID:…]` 共 400 次，**全部可回溯**：398 次命中本次召回 chunk（86 个不同 chunk ID）、2 次命中 `paths` 内 `edge_id`（R18）；R18 首轮按仅 chunk 口径误判的 2 个 ID 经复核为 `edge_id`，无虚构 ID；
  - 9 节点 `error` 全空；`Message` 与最终 Agent 输出除首部空白外逐字一致（25/25）；
  - 单条存档已替换为本次结果（`docs/s5/runs/answers_r25/`，文件头记录 session_id 与运行时间；R18 为 17:15 单条重跑，其余 24 条为 16:58 批次）。
- 截图：`01_canvas.png`（09:12）、`02_invoke.png`（09:12）、`03_retrieval.png`（09:12）、`05_final_agent.png`（09:13）、`05b_final_agent_settings.png`（09:15）、`03b_retrieval_advanced.png`（09:15）、`04_result.png`（09:16）均为 2026-11-16 本机 Edge 重拍（配置未变故未重拍），见第 5 节。

### 8.1 历史对照（2026-11-17 批次，Monarch 2026-10-07）

- 25/25 PASS；路由 25/25；路径 5–11 条；每条 12 chunks；期望来源 198/300、同病种 214/300。
- 回答合计 80,063 字（单条 2,139–4,674 字），24 条实质作答、1 条证据优先弃答（R14）。
- `[ID:…]` 共 392 个，全部可回溯；原 R02 的 1 处 `[ID:xxx]` 占位已由 11:27 单条重跑消除；R15 的 5 个唯一 ID 为图谱 `SUBTYPE_OF` 边 ID。
- 配置与 11-16 相同（`update_time=1794792978481`）；该批次存档已被 11-18 批次替换，数字仅作对照。
