# 04 RAGFlow 智能体接入（S5 收尾）

对应任务文档第十四章流程图、第十五章 KG 接口。实施规格见 `docs/s5/spec.md`，任务与实测记录见 `docs/s5/tasks.md`，验收见 `docs/s5/acceptance.md`。

## 1. 画布结构

画布 `hematology_kg_rag_v1`（agent_id `e75a102daebc43d3b327e0c64b3b0de4`），9 个节点：

```
开始 ──► 查询规划 Agent ──► 检索词生成 Agent ──┬──► 知识检索 ──────────────────────┐
                                             └──► 文本处理 ──► 变量聚合(body) ──► HTTP 请求 ──┐
                                                                                        ▼
                                                              最终分析 Agent ──► 回复消息
```

| 节点 | 组件 | 关键参数（实测 DSL） |
|---|---|---|
| 开始 | Begin | `mode=conversational`，`inputs={}`；`user_input` 注入 `sys.query` |
| 查询规划 Agent | Agent | 系统提示限定只输出 `AML/APL/ALL/CML/CLL/AA` |
| 检索词生成 Agent | Agent | 输入 `{sys.query}` + 查询规划 Agent 的 `content` |
| 知识检索 | Retrieval | `dataset_ids=["7295cb112d764d6faf0d58492e3a3262"]`、`similarity_threshold=0`、`keywords_similarity_weight=0.3`（vector=0.7，混合检索）、`top_n=12`、`rerank_id=""` |
| 文本处理 | StringTransform | `method=merge`、`delimiters=[","]`、`script` 为含两个 Agent 引用的 JSON 字符串 |
| 变量聚合 | VariableAggregator | `groups=[{group_name:"body", type:"string", variables:[{value:"StringTransform:ChattyNailsVisit@result"}]}]` |
| HTTP 请求 | Invoke | `url=http://hematology-kg-api:8000/v1/kg/context`、`method=POST`、`timeout=30`、`headers={"Content-Type":"application/json"}`，**params 无 body** |
| 最终分析 Agent | Agent | 提示中引用 `{Invoke:...@result}` 与 `{Retrieval:...@formalized_content}`；领域 `sys_prompt`（787 字）+ 固定三段；`cite=false`（见第 4 节） |
| 回复消息 | Message | `content=["{Agent:KhakiPoetsSend@content}"]` |

## 2. 零改动注入 body 的原理

`Invoke` 组件（`internal/agent/component/invoke.go`）只读取 `inputs["body"]`，且组件内部不解析变量引用（单花括号 `{cpn@key}` 与双花括号均不解析）；前端表单也没有 body 字段。因此不能直接把 JSON 写进 Invoke。

采用的绕行链路：

1. `StringTransform(method=merge)` 在 `script` 里写完整 JSON 字符串，引用在组件内被 state 解析（正式画布统一用单花括号 `{cpn@key}`，见 `docs/s5/dsl_snapshot.json`；搭建前临时探针中双花括号 `{{cpn@key}}` 亦可用）；
2. `VariableAggregator` 只有一个组，组名固定 `body`，其输出 map 即 `{"body": "<JSON 字符串>"}`；
3. `Invoke` 的 `mergeInputs` 会把上游输出中未在 params 出现的 key 并入 inputs，于是 `body` 被送进 `inputs["body"]` 并由 HTTP 请求发出。

运行实测（2026-11-11）：`StringTransform.result` = `{"disease_route":"AML","query":"AML伴FLT3突变治疗指南","max_hops":2,"limit":30}`，聚合节点输出同名 `body`，Invoke 无 error，KG 返回 `matched_entities/paths/evidence/context`。

## 3. 模型引用口径

UI 保存的 `llm_id` 是 `tenant_model.id`（如 `1a467ebc0df742e5961aff478759a048`），不是字面三段式。后端 `resolveModelRef` → `resolveTenantModelByID`（`internal/agent/component/llm_credentials.go`）按该 UUID 解析出模型名、provider 与实例凭据，等价于 `qwen3-vl-plus@hematology@Tongyi-Qianwen`。三段式字符串写在 DSL 里同样可用，但 UI 以 UUID 存储，验收时应按解析结果判定。

## 4. 已知限制

- **Invoke 无 body 字段、不解析模板**：必须用 StringTransform + VariableAggregator 注入，见第 2 节。
- **CodeExec 沙箱不可用**：`sandbox-executor-manager:9385` 未部署（DNS 解析失败），不能用代码节点构造 body。
- **rerank 不可用**：`qwen3-rerank` 验证失败，`rerank_id` 留空；检索改用混合检索 `keywords_similarity_weight=0.3`（vector=0.7）。
- **检索跨病种噪声（已缓解，2026-11-12）**：原 `keywords_similarity_weight=0`（纯向量）时，各指南相似度高度重叠（相关 0.832–0.907、不相关 0.829–0.890），提高 `similarity_threshold` 无法区分、只会同时砍掉正确证据；改为 `keywords_similarity_weight=0.3` 后（`internal/agent/tool/retrieval_nlp.go` 中权重 ≥0.01 即启用混合检索），25 条用例的同病种 chunk 由 123/200 升至 150/200（`top_n=8` 时期、按文件名正则统计，ELN 英文文件名不计入，实际同病种比例更高；命中 `expected_sources` 的 chunk 为 141/200）。继续升到 0.5 会把英文 ELN 指南挤出（R04 失去 ELN 证据），故取 0.3。
- **检索召回不足（2026-11-12 部分解决）**：部分指南治疗章节被切成大块、向量排序靠后，`top_n=8` 时漏召（如 R11 需要的 `7a7e87f677742f1c` 排第 11）。将 `top_n` 由 8 调至 **12**（14:33）后，25 条每条召回 12 chunks，期望来源命中 198/300、同病种 206/300（`top_n=8` 时为 141/200、150/200），R11 由弃答转为实质作答；17:14 恢复配置重跑后 R14 亦转为实质作答，弃答为 4 条（R03/R07/R18/R19）。剩余缺口：R03 需要的 `77e7707abde6b1a9` 在 top 12 之外，CLL 治疗 chunk `9c75306a51d28c98`/`2a0829e4047b2f04` 在 top 30 之外；改进方向为继续提高 `top_n` 或按章节重切分块。
- **最终 Agent 提示词（2026-11-12 11:04 补齐，2026-11-13 17:12 扩写为 787 字）**：原 `sys_prompt` 为 RAGFlow 默认通用模板，只靠用户提示要求三段式，未落实第十四章「不允许仅凭图谱边生成诊疗结论」和第二十章「证据优先规则」。现 `Agent:KhakiPoetsSend` 的系统提示已改为领域提示：仅用两路证据、图谱边不得推断方案/剂量/适应证/预后、临床结论须由指南原文支撑、引用必须写 `[ID:<chunk_id>]`、固定输出「结论 / 依据的图谱路径 / 引用的指南原文」三段、不评价提问或证据本身；2026-11-13 扩写增加表格、分层维度、剂量/疗程与年龄一致性要求（共 787 字）；用户提示末尾追加「临床结论必须有指南原文支撑，不得仅凭图谱路径下结论」。
- **关闭最终 Agent 的 `cite`（2026-11-12 11:23）**：`cite=true` 时 RAGFlow 会在系统提示后追加内置引用助手提示（实测取自容器二进制：`Based on the provided document or chat history, add citations to the input text…# Citation Requirements: … DO NOT modify whitespace or original text`），模型因此把任务理解为“给用户原文补标引用”，输出「您的文本整体严谨…我将对原文进行最小必要修改」式元叙述，个别用例（R10）只输出第 1 段。仅改 `sys_prompt` 无法覆盖该内置提示，故把 `Agent:KhakiPoetsSend.params.cite` 置为 `false`（其余两个 Agent 保持 `true`，其输出为病种代码/检索词，不受影响）。关闭后回答直接以 `### 1) 结论` 开头，三段齐全、`[ID:<chunk_id>]` 行内保留；代价是 UI 不再生成 `[1]…[n]` 编号引用卡片（原始 chunk ID 仍可回溯）。前两个 Agent 的 `cite` 未改，不影响路由与检索词。
- **拓扑与第十四章流程图的偏差（有意为之）**：第十四章示意图包含「患者数据查询 / 患者事实整理」节点；本 V1 依据第一章边界（患者数据不进入知识图谱，患者事实仍由外部病历/患者库链路提供），画布从 Begin 直接到查询规划 Agent，未设该节点。后续接入患者库时再补，不改变现有 KG + RAG 两路证据结构。
- **KG 接口不返回指南原文**：`evidence_types.guideline_text` 恒为 `false`，指南证据由 Retrieval 节点的 `formalized_content` 提供，验收按 Retrieval 判定。
- **模型 verify 标记**：`tenant_model.extra.verify` 对 `qwen3-vl-plus` 仍为 `fail`（历史标记），不影响实际调用；5 条首轮验收与 25 条扩充验收全部成功。
- **依赖 `ai-network` 与 `ALLOW_ANY_HOST=1`**：Invoke 需能解析并访问 `hematology-kg-api:8000`。
- **UI 自动保存会覆盖 API 改动（已知限制）**：画布前端会用页面内存中的 DSL 覆盖 `user_canvas.dsl`；当页面在 API 修改前打开、或该 origin 留有旧缓存时，`sys_prompt`/`cite` 会被回退。改配置后应关闭该 origin 的所有画布页面、重新登录/刷新，并用 API 复核 `Agent:KhakiPoetsSend.params`（`cite=false`、`sys_prompt` 787 字；当前 `update_time=1795055089414`（2026-11-19 回滚后，内容仍为 787 字），该值随前端自动保存变动，内容以 DB/API 复核为准）。Retrieval 查询变量末尾的 ` /` 为前端表单形态，实测对检索无影响（R19 带/不带该分隔符的 chunk 组成一致、9 节点无 error）。
- **UI 登录口令口径（重要）**：前端 `rsaPsw()` 先 `Base64.encode(password)` 再做 RSA（`web/src/utils/index.ts`），而 Go 端 `DecryptPassword` 只解密、不做 Base64 解码（`internal/common/password.go`）。因此数据库里必须存 **`base64(密码)` 的 scrypt 哈希**，UI 才能登录；通过 API/脚本登录时，`password` 字段需传 base64 后的字符串（或直接发 RSA 密文）。

## 5. 验收与证据

- 5/5 案例（AML/APL/ALL/CML/AA）通过：各节点 `error=null`，`paths` 均 5 条，Retrieval 指南原文 3501–11059 字、8 chunks，回答与病种一致。
- 25/25 扩充验收（2026-11-18 16:58–17:15 新基线全量复跑：Monarch 2026-11-11、`top_n=12`、`keywords_similarity_weight=0.3`、最终 Agent `cite=false`、787 字领域提示）：路由 25/25、路径非空 25/25（5–11 条）、指南证据 25/25（每条 12 chunks）、回答 25/25（均含固定三段，合计 78,735 字；22 条实质作答，其中 R03/R14 为限定条件下部分作答，3 条证据优先弃答 R07/R18/R19）、9 节点 `error` 全空；期望来源 chunk 200/300、同病种 208/300；`[ID:]` 共 400 次全部可回溯，其中 398 次命中本次召回 chunk（86 个不同 chunk ID）、2 次命中 `paths` 内 `edge_id`（均来自 R18）。报告：`docs/05_acceptance_test.md`；逐条存档：`docs/s5/runs/answers_r25/`。
- 2026-11-17 10:43–10:47 全量复跑（Monarch 2026-10-07，历史批次）：25/25 PASS；回答合计 80,063 字（24 实质 + 1 弃答 R14）；期望来源 198/300、同病种 214/300；`[ID:]` 392 个全部可回溯（R02 于 11:27 单条重跑消除原占位）。该批次存档已被 2026-11-18 批次替换，数字保留作对照。
- 2026-11-16 11:38–11:56 全量复跑（同配置，历史批次）：25/25 PASS；路由 25/25；期望来源 198/300、同病种 206/300（与 11-12 批次检索结果一致）；回答合计 82,917 字（21 实质 + 4 弃答）；`[ID:]` 全部可回溯、0 编造；9 节点 `error` 全空；应用重启后配置未回退（`update_time=1794792978481`）。该批次存档已被替换，数字保留作对照，明细见 `docs/05_acceptance_test.md` 第三节历史对照。
- 明细：`docs/s5/acceptance.md`；DSL 快照：`docs/s5/dsl_snapshot.json`；精简 SSE：`docs/s5/runs/*.sse`；完整答案存档：`docs/s5/runs/answers/{AML,APL,ALL,CML,AA}.md`。
- 截图（2026-11-16 09:12–09:16 本机 Edge 重拍）：`docs/s5/screenshots/01_canvas.png`、`02_invoke.png`、`03_retrieval.png`（full-text 0.30 / vector 0.70）、`03b_retrieval_advanced.png`（Top N 12、Rerank candidates 64）、`04_result.png`（本次 UI 运行结果，`cite=false`，正文 `[ID:<chunk_id>]`）、`05_final_agent.png`（787 字系统提示）、`05b_final_agent_settings.png`（Show citations 关闭）。

## 6. 复验操作

```bash
# 1) 登录取 token（password 传 base64(密码)）
POST http://127.0.0.1:9380/api/v1/auth/login
{"email":"kgops@hematology.local","password":"<base64(pw)>"}
# token 在响应头 Authorization

# 2) 读 DSL
GET  /api/v1/agents/e75a102daebc43d3b327e0c64b3b0de4

# 3) 跑案例（SSE）
POST /api/v1/agents/e75a102daebc43d3b327e0c64b3b0de4/run
{"user_input":"AML 伴 FLT3 突变如何治疗"}
```
