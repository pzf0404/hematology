# S5 RAGFlow 智能体编排规格

## 一、目标与范围

依据任务指引：

- 第十四章：Begin → 查询规划 Agent → 检索词生成 Agent →（Retrieval ∥ KG HTTP Request）→ 最终分析 Agent → Message
- 第十五章：`POST http://hematology-kg-api:8000/v1/kg/context`，body 为 `{disease_route, query, max_hops:2, limit:30}`

本规格描述画布目标结构、节点参数、可行性依据、搭建步骤与复验方法。实际验收结果见 `docs/05_acceptance_test.md` 与 `docs/s5/acceptance.md`。

> `agent_id`、`dataset_id`、模型 UUID、模型实例名与端口均为作者环境实测值。换机后必须按 `docs/04_ragflow_integration.md` 第五节重建，并重新选择本机知识库与模型。

## 二、可行性依据

| 编号 | 检验 | 结果 |
|---|---|---|
| E1 | `Invoke` Go 实现 `invoke.go` | body 仅取 `inputs["body"]`；组件内部不解析变量引用 |
| E2 | 临时 agent（begin → invoke → message，静态 JSON body） | 成功，KG 返回 `matched_entities=[MONDO:0018874]` |
| E3 | 临时 agent（body 内写 `{{begin:0@query}}`） | 失败，KG 返回“未知 disease_route”，证明模板未解析 |
| E4 | 临时 agent 加 CodeExec 构造 body | 失败：`sandbox-executor-manager:9385` 不存在，沙箱未部署 |
| E5 | 前端 Invoke 表单 | 字段仅 url、method、timeout、headers、proxy、clean_html、variables；无 body 字段 |
| E6 | `mergeInputs` | 组件 params 优先；上游输出中未在 params 出现的 key 会并入 inputs |
| E7 | `VariableAggregator` 源码 | 输出键等于 `group_name`，值为首个非空解析结果 |
| E8 | `StringTransform` merge 源码 | `script` 内的变量引用会被 state 解析；输出固定键 `result` |

## 三、方案选择

**主方案（零源码改动）**：用已有节点拼出 `body` 输入。

```text
Begin → StringTransform(merge, 生成 JSON 字符串)
      → VariableAggregator(group_name=body)
      → Invoke(POST)
```

- `StringTransform.result` 为完整 JSON 字符串，其中变量引用由组件 state 解析。
- `VariableAggregator` 只设一个组，组名固定为 `body`，输出 `{"body": "<JSON字符串>"}`。
- `Invoke` 的 params 中不配置 body；按 E6，上游 `body` 会注入 `inputs["body"]`，由 E1 发出。

**备选（不采用）**：修改 Go 版 Invoke 增加模板解析，或部署 sandbox 启用 CodeExec。两者都需要重建 RAGFlow 或额外基础设施，成本高，V1 不做。

## 四、搭建前探针

用 API 创建临时 agent，不占用正式画布：

```text
begin:0(Begin)
 → string:0(StringTransform, method=merge)
 → agg:0(VariableAggregator, groups=[{group_name:"body", variables:["{string:0@result}"]}])
 → invoke:0(Invoke, POST, http://hematology-kg-api:8000/v1/kg/context, headers={"Content-Type":"application/json"}，无 body)
 → message:0(Message, content=["{invoke:0@result}"])
```

`string:0.params`：

- `method=merge`
- `delimiters=,`（Check 要求非空，merge 模式下不参与拼接）
- `script={"disease_route":"{begin:0@query}","query":"{begin:0@query} FLT3","max_hops":2,"limit":3}`

运行 `POST /api/v1/agents/{id}/run`，要求：

- `invoke:0` 无 error
- `result` 可 JSON 解析
- `matched_entities` 非空
- `evidence` 含 `knowledge_graph` 与 `guideline_text`

探针通过后再搭建正式画布。

## 五、正式画布

名称：`hematology_kg_rag_v1`，9 节点。

1. **开始（Begin）**
   - 输入变量 `query`（文本，必填，描述：临床问题）。

2. **查询规划 Agent**
   - 系统提示：只输出 `AML/APL/ALL/CML/CLL/AA` 之一。
   - 用户提示：`{sys.query}`。

3. **检索词生成 Agent**
   - 用户提示含 `{sys.query}` 与查询规划 Agent 的 `content`。
   - 输出用于文档检索的 `knowledge_query`。

4. **知识检索（Retrieval）**
   - 知识库：`hematology_guidelines_v1`。
   - 查询变量：引用步骤 3 的 `content`。
   - `keywords_similarity_weight=0.3`（vector=0.7）。
   - `similarity_threshold=0`。
   - `top_n=12`。
   - `rerank_id=""`（rerank 不可用）。

5. **字符串处理（StringTransform）**
   - 方法：merge。
   - 分隔符：`,`。
   - 脚本：

     ```json
     {"disease_route":"{查询规划AgentID@content}","query":"{检索词AgentID@content}","max_hops":2,"limit":30}
     ```

   - 脚本必须是合法 JSON；引用使用单花括号 `{cpn@key}`。

6. **变量聚合（VariableAggregator）**
   - 组名：`body`。
   - 变量：引用步骤 5 的 `result`。

7. **HTTP 请求（Invoke）**
   - URL：`http://hematology-kg-api:8000/v1/kg/context`
   - 方法：POST；超时：30；Headers：`{"Content-Type":"application/json"}`
   - 参数表不要新增 body。

8. **最终分析 Agent**
   - 提示中同时引用：
     - 图谱证据：`{invoke:0@result}`
     - 指南证据：`{retrieval:0@formalized_content}`
   - 系统提示要求：
     - 仅使用图谱与指南两路证据；
     - 不得仅凭图谱边推断治疗方案、剂量、适应证或预后；
     - 临床结论必须有指南原文支撑；
     - 引用写 `[ID:<chunk_id>]`；
     - 固定输出「1) 结论 / 2) 依据的图谱路径 / 3) 引用的指南原文」三段；
     - 不评价提问或证据本身；
     - 证据只覆盖部分问题时，先答可支持部分并单列「证据未覆盖：…」；仅当两路证据与问题完全无关时才写「现有证据不足以回答该问题」。
   - `cite=false`：`cite=true` 会注入 RAGFlow 内置“给输入文本补标引用”的提示，破坏三段式输出。
   - `temperature=0.1`。

9. **回复消息（Message）**
   - 内容：最终分析 Agent 的 `content`。

连线：

```text
Begin → 查询规划 → 检索词 →（Retrieval ∥ StringTransform → VariableAggregator → Invoke）→ 最终分析 → Message
```

截图要求：整体画布、Invoke 配置、检索配置、检索高级设置、运行结果、最终 Agent 提示、最终 Agent 设置，共 7 张。

## 六、API 复验

1. `GET /api/v1/agents` 找到画布，`GET /api/v1/agents/{id}` 保存 DSL 快照。
2. `POST /api/v1/agents/{id}/run` 跑 5 条分病种案例（AML/APL/ALL/CML/AA 各 1 条），保存 SSE。
3. 每条判定：
   - `Invoke.result` 可 JSON 解析；
   - `evidence.knowledge_graph.paths` 非空；
   - Retrieval 返回指南 chunks；
   - 最终回答包含病种对应结论；
   - 无节点 error。
4. 扩充 R01–R25，逐条记录路由、路径、指南证据、回答与判定。

## 七、验收标准

- 首轮 5/5 通过。
- R01–R25 结构判定 25/25 PASS。
- 截图 7 张归档于 `docs/s5/screenshots/`。
- DSL 快照与 UI 配置一致。
- 未修改 RAGFlow 源码。

## 八、已知限制

- Invoke 不支持 body 字段与模板解析，必须用 StringTransform + VariableAggregator 注入。
- CodeExec 沙箱未部署，不可用。
- rerank 不可用，使用混合检索 vector=0.7 / keywords=0.3。
- 模型引用在 DSL 中保存为 `tenant_model` UUID，等价于三段式 `model@instance@provider`；换机后需重选模型。
- 需 `ai-network` 存在且 RAGFlow 能访问 `hematology-kg-api:8000`（作者环境设置 `ALLOW_ANY_HOST=1`）。
- 知识库需 10 篇指南全部解析成功；作者环境为 384 chunks，换机后块数可能不同。
