# S5 验收记录

- 画布：`hematology_kg_rag_v1`，9 节点
- 数据基线：`hematology-kg-v1-20261118`（Monarch 2026-11-11，128,783 节点 / 284,023 边）
- 复验方式：`GET /api/v1/agents/{id}` 取 DSL（快照 `dsl_snapshot.json`），`POST /api/v1/agents/{id}/run` 逐条运行
- 当前线上 DSL：`update_time=1795055089414`，`cite=false`，787 字领域提示，`top_n=12`，`keywords_similarity_weight=0.3`
- 原始 SSE：`runs/{AML,APL,ALL,CML,AA}.sse`；25 条存档：`runs/answers_r25/`

> `agent_id`、`dataset_id`、模型 UUID 与 chunk ID 均为作者环境实测值。换机后需按 `docs/04_ragflow_integration.md` 第五节重建，不能直接复用。

## 一、DSL 复验

| 检查项 | 规格要求 | 实测 DSL | 判定 |
|---|---|---|---|
| 节点拓扑 | Begin→查询规划→检索词→(Retrieval ∥ String→Agg→Invoke)→最终分析→Message | `begin`→查询规划 Agent→检索词 Agent→{Retrieval, StringTransform→VariableAggregator→Invoke}→最终分析 Agent→Message | 通过 |
| Invoke URL/Method/Timeout/Headers | `http://hematology-kg-api:8000/v1/kg/context`、POST、30、`{"Content-Type":"application/json"}` | 一致 | 通过 |
| Invoke 参数表 | 不得出现 body | `params` 无 body | 通过 |
| StringTransform | merge；script 为合法 JSON；引用指向查询规划与检索词节点 | `method=merge`、`delimiters=[","]`、script 可 `json.loads` | 通过 |
| VariableAggregator | 组名 `body`，引用 StringTransform.result | `group_name=body` | 通过 |
| Retrieval | 混合检索关键词权重 0.3；`top_n=12`；`similarity_threshold=0`；`rerank_id=""` | 全部一致 | 通过 |
| 最终分析 Agent 提示 | 两路证据 + 证据优先 + 固定三段式 | 787 字领域提示，用户提示追加同义约束 | 通过 |
| 最终分析 Agent `cite` | `false` | `cite=false` | 通过 |
| 模型引用 | 本机模型，DSL 存 `tenant_model` UUID | 作者环境 `qwen3-vl-plus@hematology@Tongyi-Qianwen` | 通过（等价三段式） |
| Begin | `user_input` 注入 `sys.query` | `mode=conversational` | 通过 |

## 二、运行验收（5 例）

| 案例 | 用户问题 | 分诊 | disease_route | 图谱实体 ID | paths | context 字符 | formalized_content | chunks | 回答字符 | 节点 error |
|---|---|---|---|---|---|---|---|---|---|---|
| AML | AML 伴 FLT3 突变如何治疗 | AML | AML | MONDO:0018874 | 5 | 931 | 11,059 | 8 | 5,010 | 无 |
| APL | APL 急性早幼粒细胞白血病的诱导治疗方案 | APL | APL | MONDO:0012883 | 5 | 773 | 3,609 | 8 | 3,654 | 无 |
| ALL | 成人 ALL 费城染色体阳性如何选择靶向治疗 | ALL | ALL | MONDO:0004967 | 5 | 922 | 4,446 | 8 | 3,945 | 无 |
| CML | CML 慢性髓性白血病一线 TKI 如何选择 | CML | CML | MONDO:0011996 | 5 | 973 | 3,501 | 8 | 2,988 | 无 |
| AA | 重型再生障碍性贫血的免疫抑制治疗指征 | AA | AA | MONDO:0015909 | 5 | 818 | 6,358 | 8 | 3,110 | 无 |

判定：

1. `Invoke.result` 可 JSON 解析：5/5
2. `paths` 非空：5/5（均 5 条）
3. 指南证据非空：5/5（`formalized_content` 3,501–11,059 字、8 chunks；KG 的 `evidence_types.guideline_text` 恒为 false，指南证据由 Retrieval 提供）
4. 回答与病种一致：5/5
5. 无 `_ERROR`、无节点 error：5/5

## 三、观察项

- APL 早期回答曾出现“补标引用”元叙述，根因为 `cite=true` 注入 RAGFlow 内置引用助手提示；改为 `cite=false` 后消失，回答直接以 `### 1) 结论` 开头。代价是 UI 不再渲染编号卡片，正文保留 `[ID:<chunk_id>]`。
- `tenant_model.extra.verify` 对 `qwen3-vl-plus` 为 `fail`，不影响实际调用。
- Retrieval chunk 元数据未带 `document_keyword`（取值为 `?`），引用依赖 chunk id 映射，不影响召回。
- 9 节点 `error` 全空；`Message` 与最终 Agent 输出除首部空白外逐字一致。

## 四、截图索引

| 文件 | 内容 | 对照 |
|---|---|---|
| `01_canvas.png` | 整体画布 | 9 节点拓扑与规格一致 |
| `02_invoke.png` | Invoke：URL、POST、timeout 30、headers、无 body | 与规格一致 |
| `03_retrieval.png` | 知识库、阈值 0、full-text 0.30 / vector 0.70 | 与 API 一致 |
| `03b_retrieval_advanced.png` | Top N 12、Rerank 空 | 与 `top_n=12`、`rerank_id=""` 一致 |
| `04_result.png` | R01 运行结果，含三段与 `[ID:]` | 与 API 复跑一致 |
| `05_final_agent.png` | 787 字系统提示 | 与 `sys_prompt` 长度一致 |
| `05b_final_agent_settings.png` | Show citations 关闭 | 与 `cite=false` 一致 |

## 五、5 条完整答案

| 文件 | 案例 | 回答长度 | 路径 | chunks |
|---|---|---:|---:|---:|
| `runs/answers/AML.md` | AML 伴 FLT3 | 5,010 字 | 5 | 8 |
| `runs/answers/APL.md` | APL 诱导 | 3,654 字 | 5 | 8 |
| `runs/answers/ALL.md` | Ph+ ALL 靶向 | 3,945 字 | 5 | 8 |
| `runs/answers/CML.md` | CML 一线 TKI | 2,988 字 | 5 | 8 |
| `runs/answers/AA.md` | 重型 AA 的 IST | 3,110 字 | 5 | 8 |

## 六、扩充验收 R01–R25

- 用例：`tests/acceptance_cases_ragflow.json`（AML 5 / APL 4 / ALL 5 / CML 4 / CLL 3 / AA 4）
- 结果：**25/25 PASS**
- 路由 25/25；路径 5–11 条；每条 12 chunks
- 期望来源 200/300；同病种 208/300
- 回答合计 78,735 字（2,026–4,834）；22 条实质作答（R03、R14 为限定条件下部分作答）、3 条证据优先弃答（R07/R18/R19）
- `[ID:]` 400 次全部可回溯：398 次命中本次 chunk（86 个不同 chunk ID），2 次命中 `paths` 内 `edge_id`（R18）
- 9 节点 `error` 全空
- 报告：`docs/05_acceptance_test.md`
- 单条存档：`runs/answers_r25/R{01..25}.md`

## 七、换机复核口径

作者环境的 chunk ID、路径数量与 `agent_id` 不可移植。换机后按 `docs/04_ragflow_integration.md` 5.6 执行宽松验收：

- 路由病种正确
- `paths` 非空
- Retrieval 每条 12 chunks（若调整 `top_n`，按实际值）
- 回答三段齐全，`[ID:]` 均来自本次运行
- 9 节点无 error

本文件与 `docs/05_acceptance_test.md` 的数字只证明作者环境通过，不作为新环境的自动判据。
