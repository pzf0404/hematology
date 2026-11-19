# 阶段 3：Neo4j Schema 与导入记录

依据：任务指引 六（Schema）、十（Docker 部署）、十一（Neo4j 导入与索引）、十六（版本追踪）、十七（质量控制）、十八（验收问题集）。
数据基线为阶段 2 冻结产物：`data/processed/nodes.csv` 128,783 行、`edges.csv` 284,023 行（Monarch KG 2026-11-11），校验 28 项全 PASS。

## 1. 节点模型

所有节点统一带 `:Entity` 标签，再叠加业务标签（多标签结构）。这样任务文档给出的 `Entity.id` 唯一约束可以原样落地，跨类型检索也有统一入口。

| CSV `label` | Neo4j 标签 | 节点数 | 说明 |
|---|---|---|---|
| Disease | `:Entity:Disease` | 115 | 8 个种子（含 EFO SAA）+ MONDO 父类/子类 |
| Gene | `:Entity:Gene` | 13,886 | HGNC 为主；86 个无 HGNC 唯一匹配的 ncRNA 保留原始 Ensembl ID（`ENSG000...`） |
| Variant | `:Entity:Variant` | 100,877 | CLINVAR |
| Phenotype | `:Entity:Phenotype` | 61 | HPO |
| Drug | `:Entity:Drug` | 867 | Open Targets / ChEMBL |
| Pathway | `:Entity:Pathway` | 2,276 | Reactome |
| BiologicalProcess | `:Entity:BiologicalProcess` | 10,701 | GO |

节点属性：`id`、`label`、`name`、`name_zh`、`canonical_id`、`synonyms`、`source_ids`、`xrefs`、`description`、`source`、`source_version`、`retrieved_at`，空值不写入。

派生字段：`Gene.symbol = name`。`nodes.csv` 没有独立 symbol 列，而 HGNC 的 `name` 本身即官方 symbol，派生后满足任务文档要求的 `Gene(symbol)` 索引，不修改已冻结的 CSV。

## 2. 关系模型

关系类型直接使用白名单大写谓词，方向与阶段 2 校验一致（`data/processed/validation_report.json` 28/28 PASS）。

| 关系类型 | 方向 | 边数 |
|---|---|---|
| `HAS_PHENOTYPE` | Disease → Phenotype | 80 |
| `ASSOCIATED_WITH` | Gene → Disease | 35,204 |
| `AFFECTS` | Variant → Gene | 100,885 |
| `TREATS` | Drug → Disease | 1,527 |
| `TARGETS` | Drug → Gene | 1,820 |
| `PARTICIPATES_IN` | Gene → Pathway | 41,605 |
| `INVOLVED_IN` | Gene → BiologicalProcess | 102,790 |
| `SUBTYPE_OF` | Disease → Disease | 112 |

边属性：`edge_id`、`predicate`、`original_predicate`、`source`、`source_dataset`、`source_version`、`source_record_id`、`evidence_score`（数值）、`pmid`、`doi`、`license`、`retrieved_at`。`subject_id`/`object_id` 由图结构表达，不重复存为属性。

## 3. 约束与索引

`cypher/schema.cypher`，由导入脚本自动执行：

| 名称 | 类型 | 目标 | 依据 |
|---|---|---|---|
| `entity_id_unique` | 唯一约束 | `Entity(id)` | 任务文档第十一章原文 |
| `disease_name` | 索引 | `Disease(name)` | 任务文档第十一章原文 |
| `gene_symbol` | 索引 | `Gene(symbol)` | 任务文档第十一章原文（symbol 为派生字段） |
| `entity_name` | 索引 | `Entity(name)` | 支撑阶段 4 `/v1/entity/search` 英文检索 |
| `entity_name_zh` | 索引 | `Entity(name_zh)` | 任务指引第十七章「中文命中」、第二十章「中文搜索命不中」 |

前三条是文档硬性要求；后两条是为第十二章实体搜索和第十七章中文命中准备的，属于文档「至少建立以下约束/索引」的允许范围。

## 4. 导入设计（etl/load_neo4j.py）

- 导入方式：Python neo4j driver + `UNWIND` 批量写入，批量默认 2,000 行（任务文档第十一章允许 driver 或 LOAD CSV）。
- 幂等：节点 `MERGE (n:Entity {id})`；关系 `MERGE (s)-[r:TYPE {edge_id}]->(o)`。重复执行不产生重复节点/关系。
- 异常统计：每条边写入后比对 `RETURN count(*)` 与批大小，统计「缺失端点」行数（应为 0）。
- 导入后核验：节点/关系总数、7 类节点、8 类关系逐项与 CSV 基线对比，不一致列 FAIL 并以退出码 1 结束。
- 版本记录：报告写入 `data/processed/neo4j_import_report.json`，包含 Neo4j 组件版本、编辑版、导入脚本版本 `1.0.0`、两个 CSV 的 SHA256、耗时、约束/索引清单。
- 预演：`--dry-run` 只读统计 CSV，不连库；`--verify-only` 只核验。

## 5. 执行步骤（由项目负责人执行）

```powershell
# 0) 进入项目
cd c:\Users\Lenovo\Desktop\任务\hematology-kg

# 1) 生成本地环境变量（.env 已在 .gitignore 中）
Copy-Item .env.example .env
#    打开 .env，把 NEO4J_PASSWORD 改成强密码

# 2) 创建 Docker 网络（已存在会报错，忽略即可）
docker network create ai-network

# 3) 启动 Neo4j（首次拉取 neo4j:5-community 镜像）
docker compose up -d

# 4) 等待 healthy / 就绪
docker ps --filter name=hematology-neo4j
docker exec hematology-neo4j cypher-shell -u neo4j -p <你的密码> "RETURN 1;"

# 5) 安装 Python 驱动并导入
python -m pip install "neo4j>=5,<7"
$env:NEO4J_PASSWORD="<你的密码>"
python -m etl.load_neo4j

# 6) 幂等验证：再执行一次，计数必须不变
python -m etl.load_neo4j

# 7) Neo4j Browser 执行示例查询
#    浏览器打开 http://127.0.0.1:7474，粘贴 cypher/acceptance_queries.cypher 中的语句
```

## 6. 核验结果（执行后回填）

| 项 | 期望 | 实测 | 结论 |
|---|---|---|---|
| 节点总数 `MATCH (n:Entity)` | 128,783 | 128,783 | PASS |
| 关系总数 `MATCH ()-[r]->()` | 284,023 | 284,023 | PASS |
| 7 类节点分项 | 见 §1 | 115 / 13,886 / 100,877 / 61 / 867 / 2,276 / 10,701 | PASS |
| 8 类关系分项 | 见 §2 | 80 / 35,204 / 100,885 / 1,527 / 1,820 / 41,605 / 102,790 / 112 | PASS |
| 孤立节点 | 0 | 0 | PASS |
| 约束/索引 | 5 条 | 1 约束 + 4 索引；另有 2 个自动标签索引 | PASS |
| 重复执行计数不变 | 不变 | 图内计数不变；2026-11-18 全链路重跑新建 0 | PASS |
| Neo4j 版本 | `5-community` 实际解析版本 | 导入时 5.26.32；2026-11-12 曾复验 5.26.33；2026-11-13 与 2026-11-18 重新导入/重跑均为 5.26.32（镜像 tag 未固定，重建前需重新记录） | PASS |
| 导入脚本版本 | 1.0.0 | 1.0.0 | PASS |

### 6.1 验收查询实测（Neo4j 5.26.32 Community，2026-11-13 复验；2026-11-12 曾为 5.26.33，查询结果一致，只读 Cypher）

| 查询 | 实测结果 |
|---|---|
| AML 关联基因 / 药物 / 表型 | 11,438 / 587 / 2 |
| APL 关联基因 / 药物 / 表型 | 2,001 / 31 / 38 |
| ALL 关联基因 / 药物 / 表型 | 7,752 / 306 / 11 |
| CML 关联基因 / 药物 / 表型 | 4,449 / 179 / 17 |
| CLL 关联基因 / 药物 / 表型 | 5,148 / 345 / 10 |
| AA 关联基因 / 药物 / 表型 | 4,241 / 62 / 2 |
| 获得性 AA 关联基因 / 药物 / 表型 | 72 / 0 / 0 |
| SAA（EFO:0006927）关联基因 / 药物 / 表型 | 103 / 17 / 0 |
| FLT3 → AML | 1 条 |
| PML、RARA → APL | 两个基因均命中 |
| 环孢素 → AA / 伊马替尼 → CML | 1 条 / 2 条 |
| 血小板减少关联种子疾病 | 4 个（APL/ALL/CML/CLL） |
| AA 免疫类 BP | 117 个 |
| 药物→靶点→基因→AML 完整路径 | 1,791 条 |
| 中文“急性髓系白血病”/AML 搜索 | 规范节点 `MONDO:0018874` 排第一 |
| 抽查 30 条边溯源字段 | 30/30 完整（bad=0；固定抽样明细见 `data/processed/edge_traceability_sample.csv`） |

## 7. 与任务文档的差异说明

1. `docker-compose.yml` 在阶段 3 只含 `hematology-neo4j`；阶段 4 已按任务文档模板追加 `hematology-kg-api`（build、`depends_on`、只读挂载 `config/` 与 `data/processed/`）。
2. 文档模板未发布端口；Neo4j 的 `7687`/`7474` 与 API 的 `18080` 均只绑定 `127.0.0.1`，符合表 9「Bolt 端口不对公网暴露」。
3. `Gene.symbol` 为派生字段（见 §1），CSV 未改动。
4. `Protein`、`Treatment`、`CellType` 未建节点：阶段 1–2 实测这些类型在选定数据源中没有符合白名单的关系，启用会产生孤立节点，违反表 11「孤立节点」要求。`RELATED_TO` 同前，保持关闭。
5. `APL` 的 `SUBTYPE_OF` 指向 `inherited acute myeloid leukemia (MONDO:0017893)`，是 Monarch 实际提供的层级，不手工改写为 AML 直连。
6. 中文覆盖：种子疾病中文名 8/115；表型中文名 61/61；非种子疾病无官方中文名时字段留空，不臆造译名。
7. 验收问题 11（造血干细胞移植与再障）在当前图中无 `Treatment` 节点，无法检索，属 V1 已知缺口，已在 README「已知限制」中标注，不用文档库或其他来源伪造图谱边。

## 8. 示例 Cypher

见 `cypher/acceptance_queries.cypher`：覆盖任务指引第十八章的问题 1–15，另加规模核验、边溯源抽查、孤立节点检查。
