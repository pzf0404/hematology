# 验收测试报告（RAGFlow 智能体层）

- 对应任务指引：第十八章固定问题集、第二十二章验收清单
- 被测对象：RAGFlow 画布 `hematology_kg_rag_v1`，9 节点
- 图谱基线：`hematology-kg-v1-20261118`（Monarch KG 2026-11-11，128,783 节点 / 284,023 边）
- 检索配置：`keywords_similarity_weight=0.3`（vector=0.7）、`similarity_threshold=0`、`top_n=12`
- 生成配置：最终分析 Agent `cite=false`，787 字领域提示，`temperature=0.1`
- 结果：**25/25 PASS**（结构判定）；22 条实质作答（R03、R14 为限定条件下部分作答），3 条证据优先弃答（R07、R18、R19）
- 用例定义：`tests/acceptance_cases_ragflow.json`（R01–R25）
- 单条存档：`docs/s5/runs/answers_r25/R{01..25}.md`
- 原始运行记录：`docs/s5/runs/*.sse`

> `agent_id`、`dataset_id`、模型 UUID 与 RAGFlow 端口均为作者本机实例，换机后需按 `docs/04_ragflow_integration.md` 第五节重建；本报告的 chunk ID 与路径数量只对作者环境有效。

## 一、测试范围

| 层 | 用例 | 报告 |
|---|---|---|
| 数据层（图谱构建） | `tests/acceptance_cases.json`（Q01–Q25） | `docs/03_validation_report.md`（28 项 PASS / 0 FAIL） |
| 智能体层（RAGFlow 问答） | `tests/acceptance_cases_ragflow.json`（R01–R25） | 本报告 |

智能体层覆盖 6 个病种：AML 5 条、APL 4 条、ALL 5 条、CML 4 条、CLL 3 条、AA 4 条。每题均定义 `expected_entities`、`expected_relations`、`expected_sources`、`expected_keywords`，25 条均非空。

## 二、判定规则

1. **路由**：查询规划 Agent 输出等于期望病种（AML/APL/ALL/CML/CLL/AA）。
2. **图谱证据**：`Invoke.result.paths` 非空，且关系集合含 `SUBTYPE_OF`。
3. **指南证据**：Retrieval 的 chunk 来源至少命中 1 个期望文档。
4. **回答**：最终回答超过 300 字符，且命中至少 1 个期望关键词。
5. **无异常**：9 个节点 `error` 均为空。

## 三、结果

| 用例 | 病种 | 问题 | 分诊 | 路径 | 指南字数 | chunks | 命中期望来源 | 同病种 chunk | 回答字数 | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|
| R01 | AML | AML 伴 FLT3 突变如何治疗？ | AML | 5 | 18,161 | 12 | 10 | 10 | 4,834 | PASS |
| R02 | AML | 老年 AML 不适合强化疗时如何选择治疗方案？ | AML | 5 | 11,699 | 12 | 9 | 9 | 3,197 | PASS |
| R03 | AML | AML 达到完全缓解后哪些患者需要异基因造血干细胞移植？ | AML | 5 | 7,509 | 12 | 2 | 2 | 2,517 | PASS（部分作答） |
| R04 | AML | AML 的预后危险分层依据哪些细胞遗传学和分子学标志？ | AML | 5 | 13,113 | 12 | 2 | 4 | 4,470 | PASS |
| R05 | AML | 成人急性髓系白血病的标准诱导化疗方案是什么？ | AML | 5 | 5,972 | 12 | 10 | 10 | 3,330 | PASS |
| R06 | APL | APL 的诱导治疗方案如何选择？ | APL | 5 | 5,762 | 12 | 5 | 5 | 3,801 | PASS |
| R07 | APL | APL 治疗中分化综合征如何识别和处理？ | APL | 5 | 5,747 | 12 | 3 | 3 | 2,204 | PASS（弃答） |
| R08 | APL | APL 治疗中三氧化二砷的适应证和用法是什么？ | APL | 5 | 5,523 | 12 | 6 | 6 | 2,907 | PASS |
| R09 | APL | APL 达到完全缓解后如何巩固和维持治疗？ | APL | 5 | 5,899 | 12 | 5 | 5 | 3,520 | PASS |
| R10 | ALL | 成人费城染色体阳性 ALL 如何选择 TKI 治疗？ | ALL | 8 | 5,784 | 12 | 5 | 5 | 3,628 | PASS |
| R11 | ALL | 成人 ALL 的诱导化疗方案由哪些药物组成？ | ALL | 5 | 6,399 | 12 | 8 | 8 | 2,572 | PASS |
| R12 | ALL | ALL 的中枢神经系统白血病预防怎么做？ | ALL | 5 | 6,097 | 12 | 11 | 11 | 3,057 | PASS |
| R13 | ALL | 儿童 ALL 的危险分层依据是什么？ | ALL | 5 | 7,253 | 12 | 4 | 8 | 3,145 | PASS |
| R14 | ALL | 复发难治性 ALL 有哪些治疗选择？ | ALL | 5 | 5,564 | 12 | 6 | 6 | 2,587 | PASS（部分作答） |
| R15 | CML | CML 一线 TKI 如何选择？ | CML | 5 | 4,931 | 12 | 12 | 12 | 3,112 | PASS |
| R16 | CML | CML 患者出现 TKI 耐药应如何处理？ | CML | 11 | 11,883 | 12 | 12 | 12 | 4,127 | PASS |
| R17 | CML | CML 达到深度分子学反应后能否停用 TKI？ | CML | 5 | 9,584 | 12 | 12 | 12 | 3,458 | PASS |
| R18 | CML | CML 加速期和急变期的治疗策略是什么？ | CML | 5 | 5,763 | 12 | 8 | 8 | 2,378 | PASS（弃答） |
| R19 | CLL | CLL 一线治疗如何选择？ | CLL | 5 | 6,337 | 12 | 8 | 8 | 2,607 | PASS（弃答） |
| R20 | CLL | CLL 伴 del(17p) 或 TP53 异常如何治疗？ | CLL | 7 | 7,111 | 12 | 9 | 9 | 3,355 | PASS |
| R21 | CLL | 老年或有合并症的 CLL 患者如何选择治疗方案？ | CLL | 5 | 5,568 | 12 | 7 | 7 | 2,779 | PASS |
| R22 | AA | 重型再生障碍性贫血的免疫抑制治疗指征是什么？ | AA | 5 | 8,139 | 12 | 12 | 12 | 2,547 | PASS |
| R23 | AA | 再生障碍性贫血患者什么情况下选择造血干细胞移植而不是免疫抑制治疗？ | AA | 5 | 8,621 | 12 | 12 | 12 | 3,649 | PASS |
| R24 | AA | 非重型再生障碍性贫血如何治疗？ | AA | 5 | 8,681 | 12 | 10 | 12 | 2,928 | PASS |
| R25 | AA | 再生障碍性贫血的支持治疗包括哪些措施？ | AA | 5 | 8,307 | 12 | 12 | 12 | 2,026 | PASS |

## 四、汇总

- 路由准确 25/25。
- 路径非空 25/25：多数 5 条，R10 8 条、R16 11 条、R20 7 条。
- 指南证据 25/25：每条 12 chunks，`formalized_content` 4,931–18,161 字。
- 期望来源 chunk 命中 200/300（66.7%）；同病种 chunk 208/300（69.3%，口径：chunk 文件名含该病种中文名或缩写，ELN 英文文件名按缩写计入）。
- 回答 25/25：均含固定三段「1) 结论 / 2) 依据的图谱路径 / 3) 引用的指南原文」，合计 78,735 字，单条 2,026–4,834 字。
- 实质作答 22 条；R03、R14 为限定条件下部分作答并标注证据缺口；R07、R18、R19 按证据优先规则弃答。
- 9 节点 `error` 全空；`Message` 输出与最终 Agent 逐字一致（仅首部空白差异）。
- 回答内 `[ID:…]` 共 400 个，全部可回溯：398 个命中本次召回 chunk（86 个不同 chunk ID），2 个命中 `paths` 内 `edge_id`（均来自 R18），无占位或虚构 ID。
- 执行口径：SSE 文件在下载开始时即创建，必须等到 `ALL_DONE` 后再判定，不能按文件数判断完成。

## 五、观察与已知限制

1. **检索跨病种噪声**：根因是 `similarity_threshold=0` + 纯向量召回时各指南相似度高度重叠（相关 0.832–0.907、不相关 0.829–0.890），提高阈值无法区分，会同时砍掉正确证据。改为混合检索 `keywords_similarity_weight=0.3`（vector=0.7）后，同病种召回明显提升。继续升到 0.5 会把英文 ELN 指南挤出（R04 失去 ELN 证据），故取 0.3。
2. **`top_n` 取 12**：`top_n=8` 时部分治疗章节排在第 9–11 位，R11 因此漏召；调到 12 后 R11 转为实质作答，当前同病种 chunk 为 208/300。
3. **KG 不返回指南原文**：`evidence_types.guideline_text` 恒为 `false`，指南证据统一由 Retrieval 节点提供。
4. **引用格式**：API 返回 `[ID:<chunk_id>]`。`cite=true` 时 RAGFlow 会在系统提示后追加内置引用助手提示，模型会把任务理解成“给原文补标引用”，输出元叙述；因此最终 Agent 设 `cite=false`。代价是 UI 不再生成 `[1]…[n]` 编号卡片，原始 chunk ID 仍保留在正文，可回溯。前两个 Agent 保持 `cite=true`，不影响路由与检索词。
5. **弃答 3 条属证据优先规则**：R07（APL 分化综合征）、R18（CML 加速/急变期）、R19（CLL 一线治疗）在 12 个 chunk 中缺少可直接回答的方案段落，最终 Agent 写「无法依据现有指南原文…」并列出缺口。R03、R14 为部分作答。历史核查显示：R07 的 chunks 中「分化综合征/维甲酸综合征/ATRA 综合征」出现 0 次；R18 只有进展期标题与急变期诊断标准，无 AP/BP 治疗方案；R19 指南章节未含一线方案推荐。
6. **检索召回仍有缺口**：知识库 10 篇文档仅 384 chunks，部分治疗章节被切成大块且开头措辞与问题不相似，向量排序偏低。R03 需要的 `77e7707abde6b1a9` 在 top 12 之外；CLL 治疗 chunk `9c75306a51d28c98` / `2a0829e4047b2f04` 在 top 30 之外。改进方向：提高 `top_n` 至 20，或按章节/表格重切分块。
7. **图谱路径口径**：`paths` 为 5–11 条，多数是 `SUBTYPE_OF` 分类边；R06–R09 还返回 `TREATS`，R20 返回 `ASSOCIATED_WITH`。模型判定这些关联不覆盖问题所需的治疗方案/机制，因此按提示声明“无可用路径”或不以其作为结论依据。这与第十四章「不允许仅凭图谱边生成诊疗结论」一致。
8. **换机不可直接复用 chunk ID**：`agent_id`、`dataset_id`、模型 UUID 与 chunk ID 均由实例生成；换机后只能按 `docs/04_ragflow_integration.md` 5.6 的宽松规则验收。

## 六、证据索引

| 内容 | 位置 |
|---|---|
| 逐条明细与 DSL 核验 | `docs/s5/acceptance.md` |
| 25 条答案 | `docs/s5/runs/answers_r25/` |
| SSE 运行记录 | `docs/s5/runs/*.sse` |
| DSL 快照 | `docs/s5/dsl_snapshot.json` |
| 截图 | `docs/s5/screenshots/`（01_canvas、02_invoke、03_retrieval、03b_retrieval_advanced、04_result、05_final_agent、05b_final_agent_settings） |
