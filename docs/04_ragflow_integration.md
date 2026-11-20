# RAGFlow 智能体接入（阶段 5）

对应任务指引第十四章流程图与第十五章 KG 接口。

> **环境说明**：本文出现的 `agent_id`、`dataset_id`、`tenant_model` UUID、模型实例名、RAGFlow 端口与登录账号，均为作者本机 RAGFlow 的实测值，只用于说明配置形态。换一台机器后这些值不存在，也不能直接填用；正确做法是按第五节从零重建，导入 DSL 后由 RAGFlow 生成新的 `agent_id`，知识库与模型在画布中重新选择。

## 一、画布结构

画布 `hematology_kg_rag_v1`，共 9 个节点：

```text
开始 ──► 查询规划 Agent ──► 检索词生成 Agent ──┬──► 知识检索 ──────────────────────┐
                                             └──► 文本处理 ──► 变量聚合(body) ──► HTTP 请求 ──┐
                                                                                        ▼
                                                              最终分析 Agent ──► 回复消息
```

| 节点 | 组件 | 关键参数 |
|---|---|---|
| 开始 | Begin | `mode=conversational`；`user_input` 注入 `sys.query` |
| 查询规划 Agent | Agent | 系统提示限定只输出 `AML/APL/ALL/CML/CLL/AA` |
| 检索词生成 Agent | Agent | 输入 `{sys.query}` + 查询规划 Agent 的 `content` |
| 知识检索 | Retrieval | 知识库 `hematology_guidelines_v1`；`similarity_threshold=0`；`keywords_similarity_weight=0.3`（vector=0.7）；`top_n=12`；`rerank_id=""` |
| 文本处理 | StringTransform | `method=merge`、`delimiters=[","]`；`script` 为含两个 Agent 引用的 JSON 字符串 |
| 变量聚合 | VariableAggregator | 单组，`group_name="body"`，引用 `StringTransform.result` |
| HTTP 请求 | Invoke | `url=http://hematology-kg-api:8000/v1/kg/context`、`method=POST`、`timeout=30`、`Content-Type=application/json`；**params 无 body** |
| 最终分析 Agent | Agent | 引用 `Invoke.result` 与 `Retrieval.formalized_content`；787 字领域提示；`cite=false` |
| 回复消息 | Message | 输出最终 Agent 的 `content` |

## 二、零改动注入 body

`Invoke` 组件只读取 `inputs["body"]`，且组件内部不解析变量引用（单花括号与双花括号均不解析），前端表单也没有 body 字段，因此不能把 JSON 直接写进 Invoke。

采用的绕行链路：

1. `StringTransform(method=merge)` 在 `script` 中写完整 JSON 字符串；组件 state 会解析其中的 `{cpn@key}` 引用，输出固定键 `result`。
2. `VariableAggregator` 只设一个组，组名固定为 `body`，其输出 map 即 `{"body": "<JSON 字符串>"}`。
3. `Invoke` 的 `mergeInputs` 会把上游输出中未在 params 出现的 key 并入 inputs，`body` 因此进入 `inputs["body"]` 并由 HTTP 请求发出。

运行时 `StringTransform.result` 形如：

```json
{"disease_route":"AML","query":"AML伴FLT3突变治疗指南","max_hops":2,"limit":30}
```

聚合节点输出同名 `body`，Invoke 无 error，KG 返回 `matched_entities / paths / evidence / context`。

## 三、模型引用

UI 保存的 `llm_id` 是 `tenant_model.id`（作者环境为 `1a467ebc0df742e5961aff478759a048`），不是字面三段式。后端按该 UUID 解析出模型名、provider 与实例凭据，作者环境等价于 `qwen3-vl-plus@hematology@Tongyi-Qianwen`。三段式字符串写在 DSL 中同样可用，但 UI 以 UUID 存储。

换机重建时，**不要沿用上述 UUID**：在三个 Agent 节点重新选择本机已配置的模型即可，RAGFlow 会写入新的 `llm_id`。

## 四、检索与引用

- 知识库：`hematology_guidelines_v1`，10 篇指南、384 chunks
- 检索：混合检索，`keywords_similarity_weight=0.3`（vector=0.7）、`similarity_threshold=0`、`top_n=12`、`rerank_id=""`
- 最终 Agent：`cite=false`，领域提示 787 字，`temperature=0.1`；要求只使用图谱与指南两路证据、图谱边不得推断方案/剂量/适应证/预后、临床结论须有指南原文支撑、引用写 `[ID:<chunk_id>]`、固定输出「结论 / 依据的图谱路径 / 引用的指南原文」三段
- KG 接口：`POST http://hematology-kg-api:8000/v1/kg/context`，`max_hops=2`、`limit=30`

关闭 `cite` 的原因：`cite=true` 时 RAGFlow 会在系统提示后追加内置引用助手提示，模型会把任务理解成“给原文补标引用”，输出元叙述；仅改 `sys_prompt` 无法覆盖该内置提示。前两个 Agent 保持 `cite=true`，其输出为病种代码/检索词，不受影响。

## 五、从零重建（换机必读）

前置条件：

- RAGFlow 已启动，Web 与 API 可访问（作者环境为 9381 / 9380，端口以实际部署为准）
- RAGFlow 中已配置可用的对话模型与 embedding 模型
- 本仓库的 Neo4j 与 API 已启动，且 RAGFlow 容器能访问 `http://hematology-kg-api:8000/health`
- 两个栈都在 `ai-network`；RAGFlow 允许访问该主机名（作者环境设置 `ALLOW_ANY_HOST=1`）

网络自查与修复（按镜像筛出 RAGFlow 主容器，避免误取 mysql / es / redis）：

```powershell
docker network inspect ai-network --format "{{range .Containers}}{{.Name}} {{end}}"
$ragflowContainer = (docker ps --format "{{.Names}}`t{{.Image}}" |
  Select-String "infiniflow/ragflow" |
  ForEach-Object { ($_.Line -split "`t")[0] } |
  Select-Object -First 1)
docker network connect ai-network $ragflowContainer   # 已连接会报错，可忽略
docker exec $ragflowContainer curl -s http://hematology-kg-api:8000/health
```

若返回主机不可达，在 RAGFlow 安装目录的 `docker/.env` 中追加 `ALLOW_ANY_HOST=1`，然后在该目录执行 `docker compose -f docker/docker-compose.yml up -d` 使环境变量生效（或 `docker restart $ragflowContainer`），再重试上面的 `docker exec` 命令。

### 5.1 准备指南文档

```powershell
python -m etl.fetch_guidelines
```

确认 `data/raw/guidelines/` 下有 10 个文件：3 个 `.doc`、1 个 `.docx`、6 个 `.pdf`。将 3 个 `.doc` 用 Word 另存为 `.docx`（文件名见 `sources.json` 的 `upload_filename`），最终上传 6 个 PDF + 4 个 DOCX。无 Word 时可用 LibreOffice：

```powershell
Get-ChildItem data\raw\guidelines\*.doc | ForEach-Object { soffice --headless --convert-to docx --outdir data\raw\guidelines $_.FullName }
```

清单以 `data/raw/guidelines/sources.json` 为准；指南原文不入 Git，若官方链接失效，需要从交付介质复制。

### 5.2 创建知识库

1. RAGFlow → 知识库 → 新建，名称 `hematology_guidelines_v1`。
2. 选择本机可用的 embedding 模型。
3. 上传 10 个文件（6 个 PDF + 4 个 DOCX，其中 3 个 DOCX 由 `.doc` 转换），启动解析。
4. 等待全部文档解析完成；作者环境解析结果为 384 chunks。块数不要求逐块一致，但 10 个文件必须全部成功。
5. 用“FLT3 AML 治疗”做一次检索测试，确认能返回指南原文。

### 5.3 导入画布

1. RAGFlow → Agent → 导入 DSL，选择 `docs/s5/dsl_snapshot.json`。
2. 导入后会生成**新的 agent_id**；打开新画布，不要使用文档中的旧链接。
3. 画布应显示 9 个节点、连线与作者环境一致。

### 5.4 重新绑定知识库与模型

导入的 DSL 仍带有作者环境的 `dataset_ids` 与 `llm_id`，必须逐项替换：

| 节点 | 操作 |
|---|---|
| 知识检索（Retrieval） | 重新选择 `hematology_guidelines_v1`；确认 `top_n=12`、`keywords_similarity_weight=0.3`、`similarity_threshold=0` |
| 查询规划 Agent | 重新选择本机对话模型 |
| 检索词生成 Agent | 重新选择本机对话模型 |
| 最终分析 Agent | 重新选择本机对话模型；确认 `cite=false`；确认系统提示仍为 787 字领域提示 |
| HTTP 请求（Invoke） | 确认 URL 为 `http://hematology-kg-api:8000/v1/kg/context`、`timeout=30`；params 不要添加 body |

保存后关闭该 RAGFlow 页面的所有画布标签再重新打开，避免前端用内存旧状态回写 DSL。

### 5.5 冒烟验证

在画布中依次运行：

1. `AML 伴 FLT3 突变如何治疗`
2. `再生障碍性贫血的一线免疫抑制治疗是什么`

检查：

- 9 个节点均无 error
- Retrieval 每条返回 12 chunks
- Invoke 的 `result` 可解析，`matched_entities` 与 `paths` 非空
- 最终回答包含「结论 / 依据的图谱路径 / 引用的指南原文」三段
- `[ID:...]` 均来自本次运行的 chunks

### 5.6 全量验收

`tests/acceptance_cases_ragflow.json` 提供 R01–R25 的问题、期望病种与期望来源。换机后由于 chunk ID 会变，只能校验：

- 路由病种正确
- `paths` 非空
- 每条 Retrieval 返回 12 chunks
- 回答三段齐全、无编造引用
- 9 节点无 error

作者环境的 25/25 实测结果见 `docs/05_acceptance_test.md` 与 `docs/s5/acceptance.md`，可作为对照，不作为换机后的自动判据。

## 六、验收结果（作者环境）

- 5 条分病种案例：5/5 通过；各节点 `error=null`，`paths` 均 5 条，指南原文 3,501–11,059 字、8 chunks
- R01–R25：25/25 PASS；路由 25/25；路径非空 25/25（5–11 条）；指南证据 25/25（每条 12 chunks）；回答 25/25（合计 78,735 字；22 条实质作答，R03/R14 为限定条件下部分作答，R07/R18/R19 为证据优先弃答）；9 节点 `error` 全空
- 期望来源 chunk 200/300；同病种 chunk 208/300
- `[ID:]` 共 400 次，全部可回溯：398 次命中本次召回 chunk（86 个不同 chunk ID），2 次命中 `paths` 内 `edge_id`（均来自 R18）

证据位置：

- 报告：`docs/05_acceptance_test.md`
- 逐条明细：`docs/s5/acceptance.md`
- 原始存档：`docs/s5/runs/answers_r25/`、`docs/s5/runs/*.sse`
- DSL 快照：`docs/s5/dsl_snapshot.json`
- 截图：`docs/s5/screenshots/`

## 七、已知限制

- **Invoke 无 body 字段、不解析模板**：必须用 StringTransform + VariableAggregator 注入。
- **CodeExec 沙箱不可用**：作者环境未部署 `sandbox-executor-manager:9385`，不能用代码节点构造 body。
- **rerank 不可用**：`qwen3-rerank` 验证失败，`rerank_id` 留空；改用混合检索 0.3。
- **检索跨病种噪声**：10 篇指南措辞高度相似；`top_n=12` + 混合检索 0.3 时同病种 208/300。继续升权重会挤掉英文 ELN 指南。
- **召回仍有缺口**：CLL 部分治疗 chunk 在 top 12 之外；改进方向是提高 `top_n` 或按章节重切。
- **模型 verify 标记**：作者环境 `tenant_model.extra.verify` 对 `qwen3-vl-plus` 仍为 `fail`，不影响实际调用。
- **依赖 `ai-network` 与 `ALLOW_ANY_HOST=1`**：Invoke 需能解析并访问 `hematology-kg-api:8000`。
- **UI 自动保存覆盖 API 改动**：画布打开时前端会用内存旧状态回写 DSL；改配置须在 UI 内保存并刷新复验；UI 保存会在 Retrieval 查询变量末尾追加 ` /`，实测对检索无影响。
- **UI 登录口令口径**：前端先 Base64 再 RSA，后端只解密、不做 Base64 解码；数据库需存 `base64(密码)` 的 scrypt 哈希。通过 API/脚本登录时，`password` 传 base64 后的字符串。
- **换机后 chunk ID 必变**：`docs/s5/acceptance.md` 中的 `[ID:]` 只证明作者环境可回溯，不能作为新环境判据。
- **KB embedding / 分块方式未固化在仓库**：重建时需选择本机可用模型；不同模型会导致召回差异，验收应按第五节 5.6 的宽松规则执行。

## 八、复验命令（作者环境形态）

以下命令仅示意 API 形态，ID、端口、账号需替换为本机值：

```bash
# 1) 登录取 token（password 传 base64(密码)）
POST http://127.0.0.1:9380/api/v1/auth/login
{"email":"<本机账号>","password":"<base64(密码)>"}
# token 在响应头 Authorization

# 2) 读 DSL（{agent_id} 为导入后新生成的值）
GET /api/v1/agents/{agent_id}

# 3) 跑案例（SSE）
POST /api/v1/agents/{agent_id}/run
{"user_input":"AML 伴 FLT3 突变如何治疗"}
```
