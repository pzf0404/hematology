# S5 RAGFlow 智能体编排（方案 1：UI 点选 + API 复验）实施规格

## 1. 目标与范围

- 依据任务文档：第十四章流程图（Begin → 查询规划 Agent → 检索词生成 Agent →（文档 Retrieval ∥ KG HTTP Request）→ 最终分析 Agent → Message）；第十五章 L224/L232（KG 接口 `POST http://hematology-kg-api:8000/v1/kg/context`，body `{disease_route, query, max_hops:2, limit:30}`）。
- 用户负责在 RAGFlow Web（9381）按本规格逐节点点选；本规格给出精确节点/字段/取值。
- 我方负责：搭建前用 API 做可行性探针；搭建后用 API 读取 DSL 与运行结果复验首轮 5 条验收案例，并归档截图；后续已按第十八章扩展为 R01–R25（见 `acceptance.md` 第 7 节）。

## 2. 实测事实（已亲自检验，非记忆）

| 编号 | 检验 | 结果 |
|---|---|---|
| E1 | `Invoke` Go 实现 `internal/agent/component/invoke.go` L204 | body 仅取 `inputs["body"]`；组件内部**不解析** `{{...}}` |
| E2 | 临时 agent（begin→invoke→message，body 为静态 JSON） | 成功，KG 返回 `matched_entities=[MONDO:0018874]` |
| E3 | 临时 agent（body 内写 `{{begin:0@query}}`） | 失败，KG 返回 `未知 disease_route`，证明模板未解析 |
| E4 | 临时 agent 加 CodeExec 构造 body | 失败：`sandbox-executor-manager:9385` 不存在（DNS 解析失败），沙箱未部署 |
| E5 | 前端 `web/src/pages/agent/form/invoke-form/index.tsx` | 字段仅：url、method、timeout、headers(JSON)、proxy、clean_html、variables(参数表)；**无 body 字段** |
| E6 | `mergeInputs`（invoke.go L337） | 组件 params 优先；上游输出中**未在 params 出现的 key** 会并入 inputs |
| E7 | `VariableAggregator` 源码 | 输出键 = `group_name`，值 = 首个非空解析结果 |
| E8 | `StringTransform` merge 源码 | `script` 内的变量引用会被 state 解析（临时探针用双花括号 `{{cpn@var}}`，正式画布用单花括号 `{cpn@key}`，两者均实测可用），输出固定键 `result` |

## 3. 方案决策

**主方案（零改动，推荐）**：用已有节点拼出 `body` 输入，绕开 Invoke 无 body 字段/不解析模板的限制。

```
Begin ──► StringTransform(merge, 生成 JSON 字符串) ──► VariableAggregator(group_name=body) ──► Invoke(POST) ──► … 
```

- `StringTransform.result` = 完整 JSON 字符串（其中的变量引用由组件 state 解析）。
- `VariableAggregator` 只有一个组，组名固定为 `body`，其输出 map 即 `{"body": "<JSON字符串>"}`。
- `Invoke` 的 params 中**不配置 body**，按 E6，上游 `body` 会注入 `inputs["body"]`，由 E1 发送。

**备选（仅当主方案探针失败才启用，需用户再次批准）**：给 Go 版 `Invoke` 增加模板解析（url/body/headers），需重建 `ragflow_server`（本机无 Go、需 cgo/ONNX 静态库，成本高），或部署 sandbox 使 CodeExec 可用。默认不执行。

## 4. 搭建前的可行性探针（必须通过才让用户动手）

用 API 创建临时 agent（不占用用户画布命名）：

```
begin:0(Begin) → string:0(StringTransform, method=merge)
 → agg:0(VariableAggregator, groups=[{group_name:"body", variables:["{{string:0@result}}"]}])
 → invoke:0(Invoke, method=POST, url=http://hematology-kg-api:8000/v1/kg/context, headers={"Content-Type":"application/json"}, 无 body)
 → message:0(Message, content=["{{invoke:0@result}}"])
```

- `string:0.params`：
  - `method`: `merge`
  - `delimiters`: `,`（Check 要求非空，merge 模式下不参与拼接）
  - `script`: `{"disease_route":"{{begin:0@query}}","query":"{{begin:0@query}} FLT3","max_hops":2,"limit":3}`
- 运行 `POST /api/v1/agents/{id}/run`，要求：`invoke:0` 无 error，`result` 可 JSON 解析且 `matched_entities` 非空、`evidence` 含 `knowledge_graph`/`guideline_text`。
- 探针通过后，`string:0` 的 script 中的 `query` 改为引用「检索词生成 Agent」的输出变量；节点 ID 以用户实际画布为准。

## 5. 用户 UI 搭建步骤（探针通过后按此逐节点点选）

画布名称：`hematology_kg_rag_v1`（agent 画布）。

1. **开始**（Begin）
   - 输入变量：`query`（文本，必填，描述：临床问题）。
2. **查询规划 Agent**
   - 模型：`qwen3-vl-plus@hematology@Tongyi-Qianwen`
   - 系统提示：按任务文档第十四章职责，输出病种路由（AML/APL/ALL/CML/CLL/AA 之一）。
   - 用户提示：`{sys.query}`（单花括号，正式画布实测写法）
3. **知识检索词生成 Agent**
   - 同上模型；用户提示含 `{sys.query}` 与查询规划 Agent 的 `content`（如 `{Agent:<查询规划AgentID>@content}`）。
   - 输出用于文档检索的 `knowledge_query`。
4. **知识检索**（Retrieval）
   - 知识库：`hematology_guidelines_v1`
   - 查询变量：引用步骤 3 的 `content`
   - `keywords_similarity_weight`=0.3（vector=0.7；DSL 只存关键词权重，向量权重为其补数；rerank 不可用）
   - `top_n`=12（2026-11-12 14:33 由 8 调整）：部分治疗章节在向量排序中靠后（R11 需要的 chunk 在 `top_n=8` 时排第 11），调至 12 后每条召回 12 chunks，期望来源 198/300、同病种 206/300，弃答由 6 条降为 5 条；17:14 恢复配置重跑后 R14 亦转为实质作答，弃答为 4 条。
   - 2026-11-12 实测：纯向量（vector=1.0）跨病种噪声更多，同病种 chunk 123/200；关键词 0.3 提升到 150/200（`top_n=8`）；0.5 会挤掉英文 ELN 指南（R04 失去 ELN 证据），故取 0.3。提高 `similarity_threshold` 无效（相关/不相关分数重叠 0.83–0.91）。
5. **字符串处理**（StringTransform）
   - 方法：合并（merge）
   - 分隔符：`,`
   - 脚本（精确取值，替换其中的节点 ID 为实际 ID）：
     `{"disease_route":"{查询规划AgentID@content}","query":"{检索词AgentID@content}","max_hops":2,"limit":30}`
   - 注意：脚本必须是合法 JSON；引用使用单花括号 `{cpn@key}`（本画布实测可用）；临时探针中双花括号 `{{cpn@key}}` 亦可用。
6. **变量聚合**（VariableAggregator）
   - 组名：`body`
   - 变量：引用步骤 5 的 `result`
7. **HTTP 请求**（Invoke）
   - URL：`http://hematology-kg-api:8000/v1/kg/context`
   - 方法：POST；超时：30；Headers：`{"Content-Type":"application/json"}`
   - **不要**在参数表里新增 body（body 由上游聚合节点注入）
8. **最终分析 Agent**
   - 模型同上；提示中同时引用：
     - 知识图谱证据：`{invoke:0@result}`
     - 指南原文证据：`{retrieval:0@formalized_content}`（或 chunks）
   - 要求输出结论 + 两类证据出处。
   - 系统提示必须写明（2026-11-12 补齐，2026-11-13 17:12 扩写为 787 字，增加表格、分层维度、剂量/疗程与年龄一致性要求）：仅用两路证据；不得仅凭图谱边推断治疗方案/剂量/适应证/预后；临床结论须由指南原文支撑；引用写 `[ID:<chunk_id>]`；固定输出「1) 结论 / 2) 依据的图谱路径 / 3) 引用的指南原文」三段；不评价提问或证据本身；若证据仅覆盖问题的一部分，先答证据支持的部分并单列「证据未覆盖：…」，仅当两路证据与问题完全无关时才写「现有证据不足以回答该问题」（2026-11-12 11:40 补，避免过度弃答）。
  - `cite` 必须为 `false`（2026-11-12 补）：`cite=true` 会注入 RAGFlow 内置“给输入文本补标引用”的系统提示，导致回答以「您的文本整体严谨…最小必要修改」开头、破坏三段式；关闭后由本节点系统提示自行约束 `[ID:<chunk_id>]` 引用。
9. **回复消息**（Message）
   - 内容：最终分析 Agent 的 `content`。

连线：Begin→查询规划→检索词→（Retrieval ∥ StringTransform→VariableAggregator→Invoke）→最终分析→Message。
截图要求：①整体画布 ②Invoke 配置 ③检索配置 ④运行结果（含两类证据）。

## 6. API 复验（用户搭建完成后）

1. `GET /api/v1/agents` 找到画布 → `GET /api/v1/agents/{id}` 保存 DSL 快照（确认节点/参数与规格一致）。
2. `POST /api/v1/agents/{id}/run` 先跑首轮 5 条验收案例（AML/APL/ALL/CML/AA 各 1 条）并保存 SSE；第十八章扩充的 R01–R25 见 `acceptance.md` 第 7 节。
3. 每条判定：
   - `invoke:0` 输出 `result` 可 JSON 解析；
   - `evidence.knowledge_graph.paths` 非空；
   - `evidence.guideline_text` 非空；
   - 最终回答包含病种对应结论；
   - 无 `_ERROR`、无节点 error。
4. 输出 `docs/s5/acceptance.md`（案例、请求、证据摘要、通过/失败）。

## 7. 验收标准

- 首轮 5/5 案例通过第 6 节判定；扩充 R01–R25 的判定见 `acceptance.md` 第 7/8 节（25/25 PASS）；
- 截图归档于 `docs/s5/screenshots/`（现 7 张：整体画布、Invoke、检索、检索高级设置、运行结果、最终 Agent 提示、最终 Agent 设置）；
- DSL 快照与 UI 配置一致；
- 无对 RAGFlow 源码的改动（主方案成立时）。

## 8. 已知限制（写入最终文档）

- Invoke 不支持 body 字段与模板解析，故采用 StringTransform+VariableAggregator 注入 body。
- CodeExec 沙箱未部署（`sandbox-executor-manager:9385` 不可达），不可用。
- rerank 不可用；检索使用混合检索 `vector=0.7 / keywords=0.3`（2026-11-12 由 vector=1.0 调整，理由见第 3 节第 4 条）。
- 模型引用在 DSL 中保存为 `tenant_model` UUID，等价于三段式 `model@instance@provider`；验收按解析结果判定。
- 需 `ai-network` 已存在且 `ALLOW_ANY_HOST=1`。
