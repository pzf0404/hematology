# S5 任务清单

对应 `docs/s5/spec.md`。状态以当前交付为准，不再保留中途批次记录。

## T0 可行性探针：StringTransform + VariableAggregator 注入 body

状态：**已通过**

实测结果：

- `StringTransform.result` 为 `{"disease_route":"AML","query":"AML FLT3","max_hops":2,"limit":3}`，变量引用被正确解析
- `VariableAggregator` 输出键含 `body`，值与 StringTransform 结果一致
- `Invoke` 无 error，`result` 可解析：`matched_entities=6`、`paths=3`、`evidence_types={"knowledge_graph":true,"guideline_text":false}`
- 结论：主方案成立，无需修改 RAGFlow 源码

前置细节：

- `StringTransform.delimiters` 在 API 层必须是数组（如 `[","]`）；UI 合并模式下为单选，保存后需复验 DSL 类型
- KG API 的 evidence 是图谱边列表，`guideline_text` 由 Retrieval 节点提供

清理：探针画布用完即删，不进入正式交付。

## T1 输出 UI 点选步骤

状态：**已完成**

- 按 `spec.md` 第五节给出逐节点字段与取值
- 明确 HTTP 请求节点参数表不要添加 body

## T2 复验 DSL

状态：**已通过**

正式画布 `hematology_kg_rag_v1`，9 节点，与规格一致：

- `Invoke`：URL、POST、headers、timeout 正确，params 无 body
- `StringTransform`：`method=merge`，script 为合法 JSON，引用指向正确节点
- `VariableAggregator`：组名 `body`，引用 StringTransform 的 `result`
- `Retrieval`：知识库 `hematology_guidelines_v1`，`vector=0.7 / keywords=0.3`，`top_n=12`，`similarity_threshold=0`
- 三个 Agent：模型由本机配置决定，作者环境为 `qwen3-vl-plus@hematology@Tongyi-Qianwen`，DSL 中存为 `tenant_model` UUID
- 最终 Agent：`cite=false`，787 字领域提示
- 快照：`docs/s5/dsl_snapshot.json`

当前线上 DSL `update_time=1795055089414`；该值会随前端自动保存变动，内容以 API/DB 复核为准：

- `cite=false`
- `sys_prompt` 787 字
- `top_n=12`
- `keywords_similarity_weight=0.3`

注意：画布打开时前端会用内存旧状态回写 DSL；改配置后必须关闭该 RAGFlow 页面的所有画布标签，重新打开并用 API 复核。

## T3 运行验收案例

状态：**5/5 + 25/25 通过**

首轮 5 条（AML/APL/ALL/CML/AA）：

- 全部 HTTP 200，9 节点 `error=null`
- `paths` 均 5 条
- Retrieval `formalized_content` 3,501–11,059 字、8 chunks
- 记录：`docs/s5/acceptance.md`；SSE：`docs/s5/runs/{AML,APL,ALL,CML,AA}.sse`；答案：`docs/s5/runs/answers/{AML,APL,ALL,CML,AA}.md`

扩充 R01–R25：

- 用例：`tests/acceptance_cases_ragflow.json`
- 结构判定 25/25 PASS
- 路由 25/25；路径 5–11 条；每条 12 chunks
- 期望来源 200/300；同病种 208/300
- 回答合计 78,735 字；22 条实质作答（R03/R14 部分作答）、3 条弃答（R07/R18/R19）
- `[ID:]` 400 次全部可回溯：398 次命中 chunk（86 个不同 chunk ID）、2 次命中 `paths` 内 `edge_id`
- 9 节点 `error` 全空
- 报告：`docs/05_acceptance_test.md`
- 存档：`docs/s5/runs/answers_r25/`

判定口径：

- `Invoke.result` 可解析
- `knowledge_graph.paths` 非空
- Retrieval 返回指南 chunks
- 最终回答与病种一致且含固定三段
- 无节点 error

## T4 截图归档

状态：**已完成**

`docs/s5/screenshots/` 共 7 张：

| 文件 | 内容 |
|---|---|
| `01_canvas.png` | 整体画布 |
| `02_invoke.png` | HTTP 请求配置 |
| `03_retrieval.png` | 知识检索配置（0.30 / 0.70） |
| `03b_retrieval_advanced.png` | 高级设置（Top N 12） |
| `04_result.png` | R01 运行结果 |
| `05_final_agent.png` | 最终 Agent 787 字系统提示 |
| `05b_final_agent_settings.png` | Show citations 关闭 |

索引见 `docs/s5/acceptance.md` 第五节。

## T5 文档收尾

状态：**已完成**

- `docs/04_ragflow_integration.md`：画布参数、body 注入原理、模型引用、从零重建步骤、已知限制、验收索引、复验命令
- `docs/05_acceptance_test.md`：R01–R25 当前基线结果
- `docs/s5/acceptance.md`：DSL 逐项核验、5 条案例、截图索引、25 条汇总

## 交付对照

| 任务指引要求 | 证据 | 状态 |
|---|---|---|
| HTTP Request 接入 KG API | Invoke `POST http://hematology-kg-api:8000/v1/kg/context`，timeout 30，`Content-Type: application/json`；运行无 error | 完成 |
| 结果传递 | StringTransform 拼 body；VariableAggregator 以 `body` 注入 Invoke；最终 Agent 同时引用 Invoke 与 Retrieval | 完成 |
| 端到端问答 | 5 条 + 25 条，25/25 PASS | 完成 |
| RAGFlow 配置截图 | 7 张 | 完成 |
| 两类证据区分 | 最终 Agent 分块呈现图谱与指南证据；回答固定三段；`evidence_types` 单独输出 | 完成 |
| 页面与 DSL 一致 | `dsl_snapshot.json` 与 API 一致；改配置后关闭页面并复核 | 完成 |
| 换机可重建 | `docs/04_ragflow_integration.md` 第五节 | 完成 |
