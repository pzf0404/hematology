# Schema 与 Neo4j 导入说明

- 数据基线：`hematology-kg-v1-20261118`（Monarch KG 2026-11-11）
- 规模：128,783 节点 / 284,023 边 / 115 个疾病
- 导入脚本：`etl/load_neo4j.py` 1.0.0
- 约束与索引：`cypher/schema.cypher`

## 一、节点

所有节点统一为 `:Entity` + 业务标签的多标签结构，`Entity.id` 全局唯一。

| 标签 | 数量 | 主标识 | 说明 |
|---|---:|---|---|
| Disease | 115 | MONDO / EFO | 8 个种子疾病 + 1–2 hop 内的 MONDO 父/子疾病；重型再障使用 `EFO:0006927` |
| Gene | 13,886 | HGNC；86 个为 ENSG | 仅人类基因；无 HGNC 唯一匹配的 ncRNA 保留 Ensembl ID |
| Variant | 100,877 | CLINVAR | 仅 ClinVar 变异 |
| Phenotype | 61 | HP | 仅人类表型本体，含种子疾病与映射表覆盖的中文名 |
| Drug | 867 | CHEMBL | 来自 Open Targets 药物与机制数据 |
| Pathway | 2,276 | Reactome | 仅种子关联基因触达的通路 |
| BiologicalProcess | 10,701 | GO | 排除 GO 根节点 |

节点字段（`data/processed/nodes.csv`，12 列）：

```text
id,label,name,name_zh,canonical_id,synonyms,source_ids,xrefs,description,source,source_version,retrieved_at
```

- `name`：英文名；Gene 的 `name` 即 HGNC 官方 symbol，导入时派生为 `symbol` 属性以支撑索引。
- `name_zh`：中文名；仅种子疾病、`config/entity_mapping.yaml` 覆盖的表型与药物有值，其余为空。
- `synonyms`：多值用 `|` 连接。
- `source_ids` / `xrefs`：保留上游交叉引用，不参与图查询。

## 二、关系

| 类型 | 数量 | 方向 |
|---|---:|---|
| AFFECTS | 100,885 | Variant → Gene |
| ASSOCIATED_WITH | 35,204 | Gene → Disease |
| HAS_PHENOTYPE | 80 | Disease → Phenotype |
| INVOLVED_IN | 102,790 | Gene → BiologicalProcess |
| PARTICIPATES_IN | 41,605 | Gene → Pathway |
| SUBTYPE_OF | 112 | Disease → Disease |
| TARGETS | 1,820 | Drug → Gene |
| TREATS | 1,527 | Drug → Disease |

关系字段（`data/processed/edges.csv`，14 列）：

```text
edge_id,subject_id,predicate,object_id,original_predicate,source,source_dataset,
source_version,source_record_id,evidence_score,pmid,doi,license,retrieved_at
```

- `original_predicate`：必须保留上游谓词语义，不做二次推断。
- 同一 `subject_id + predicate + object_id` 的多来源证据合并为一行：`source`、`source_dataset`、`source_record_id` 用 `|` 连接，`evidence_score` 取最大值。
- `edge_id` 由 `subject_id|predicate|object_id` 稳定哈希生成，是 Neo4j 关系的幂等键。

## 三、Neo4j 建模

```cypher
// 约束：实体 id 唯一
CREATE CONSTRAINT entity_id_unique IF NOT EXISTS
FOR (n:Entity) REQUIRE n.id IS UNIQUE;

// 索引：疾病名、基因 symbol、跨类型英文名、中文名
CREATE INDEX disease_name IF NOT EXISTS FOR (n:Disease) ON (n.name);
CREATE INDEX gene_symbol IF NOT EXISTS FOR (n:Gene) ON (n.symbol);
CREATE INDEX entity_name IF NOT EXISTS FOR (n:Entity) ON (n.name);
CREATE INDEX entity_name_zh IF NOT EXISTS FOR (n:Entity) ON (n.name_zh);
```

`etl/load_neo4j.py` 启动时按分号切分 `cypher/schema.cypher` 并逐条执行，已在线对象重复执行不报错。

## 四、导入流程

```powershell
docker compose up -d hematology-neo4j
$env:NEO4J_PASSWORD = ((Select-String -Path .env -Pattern '^NEO4J_PASSWORD=').Line -replace '^NEO4J_PASSWORD=','').Trim()
docker exec hematology-neo4j cypher-shell -u neo4j -p $env:NEO4J_PASSWORD "RETURN 1;"
python -m etl.load_neo4j
```

导入逻辑：

1. 建立约束与索引；
2. 按标签分批 `UNWIND + MERGE (n:Entity {id})`，再补业务标签；
3. 按关系类型分批 `MATCH` 两端点后 `MERGE (s)-[r:TYPE {edge_id}]->(o)`；
4. 逐标签、逐关系类型对比 CSV 实测值；
5. 写 `data/processed/neo4j_import_report.json`。

幂等性：节点按 `id` 合并、关系按 `edge_id` 合并；重复执行时 `written_this_run` 为 0，节点/边总数不变。

## 五、导入结果

| 项目 | 结果 |
|---|---|
| Neo4j 版本 | 5.26.32 Community |
| 节点 | 128,783（期望 128,783） |
| 关系 | 284,023（期望 284,023） |
| 缺失端点 | 0 |
| 孤立节点 | 0 |
| 计数不一致项 | 无 |
| 约束/索引 | 1 个唯一约束 + 4 个业务索引，全部 ONLINE |
| 状态 | PASS |

分类型计数与 CSV 完全一致，详见 `data/processed/neo4j_import_report.json`。

## 六、验收查询实测

查询语句见 `cypher/acceptance_queries.cypher`。以下为当前基线实测值：

| 问题 | 结果 |
|---|---:|
| AML 相关基因（`MONDO:0018874`，ASSOCIATED_WITH） | 11,438 |
| AML 相关药物（TREATS） | 587 |
| AML 直接表型（HAS_PHENOTYPE） | 2 |
| APL 相关基因（`MONDO:0012883`） | 2,001 |
| APL 相关药物 | 31 |
| APL 直接表型 | 38 |
| ALL 相关基因（`MONDO:0004967`） | 7,752 |
| ALL 相关药物 | 306 |
| ALL 直接表型 | 11 |
| CML 相关基因（`MONDO:0011996`） | 4,449 |
| CML 相关药物 | 179 |
| CML 直接表型 | 17 |
| CLL 相关基因（`MONDO:0004948`） | 5,148 |
| CLL 相关药物 | 345 |
| CLL 直接表型 | 10 |
| 再障相关基因（`MONDO:0015909`） | 4,241 |
| 再障相关药物 | 62 |
| 再障直接表型 | 2 |
| 重型再障相关基因（`EFO:0006927`） | 103 |
| 重型再障相关药物 | 17 |
| PML / RARA 与 APL 的 ASSOCIATED_WITH | 2 条 |
| FLT3 与 AML 的 ASSOCIATED_WITH | 1 条 |
| 环孢素 TREATS 再障 | 1 条 |
| 伊马替尼 TREATS CML | 2 条 |
| 再障关联基因触达的免疫类 BP | 117 个 |
| 血小板减少（HP:0001873）关联的种子疾病 | 4 个（APL/ALL/CML/CLL） |
| AML–药物–靶点完整路径 | 1,791 条 |
| 同名/中文名/缩写 “AML” 命中疾病 | 55 个 |
| 孤立节点 | 0 |

说明：`HAS_PHENOTYPE` 只统计 Disease → Phenotype 的直接边；Gene/Variant/Genotype → Phenotype 不在白名单，已进入 staging。

## 七、与任务指引的差异

| 项 | 任务指引 | V1 实现 | 原因 |
|---|---|---|---|
| 节点标签 | 建议 Disease/Gene/Variant/Phenotype/Drug/Pathway/Protein 等 | 7 类，未建 Protein | 实测无 Protein → Pathway 边，建了会成为孤立节点 |
| 治疗方案 | 建议保留治疗关系 | 仅 `TREATS` 药物边；HSCT 等治疗条目在 staging | 白名单未定义 Treatment 节点/关系 |
| Variant → Disease | 未列入白名单 | 320 条暂存 | 白名单只有 Variant → Gene（AFFECTS） |
| Genotype / Case | 禁止患者数据 | 丢弃或暂存 | Genotype 非 V1 节点类型；Case 违反患者数据约束 |
| Disease → Disease | 建议 RELATED_TO | 仅 SUBTYPE_OF，RELATED_TO 关闭 | `related_to` 语义混杂，无法逐条证明 |
| 药物 ID | 建议统一 ChEMBL | 全部 CHEMBL | Monarch 的 CHEBI 药物无稳定映射，进 staging |
