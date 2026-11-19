// 血液病知识图谱 V1 — Neo4j 约束与索引
// 依据：任务指引 十一、Neo4j 导入与索引（“至少建立以下约束/索引”）
// 执行方式：etl/load_neo4j.py 启动时按分号切分并逐条执行；也可用 cypher-shell 手工执行。
// 节点统一为「:Entity + 业务标签」多标签结构，因此文档给出的 Entity.id 唯一约束可原样落地。

// 文档要求 1：实体 id 唯一（所有节点都带 :Entity）
CREATE CONSTRAINT entity_id_unique IF NOT EXISTS
FOR (n:Entity) REQUIRE n.id IS UNIQUE;

// 文档要求 2：疾病名称索引
CREATE INDEX disease_name IF NOT EXISTS
FOR (n:Disease) ON (n.name);

// 文档要求 3：基因 symbol 索引
// 说明：nodes.csv 无独立 symbol 列，导入时为 Gene 节点派生 symbol = name（HGNC 的 name 即官方 symbol）
CREATE INDEX gene_symbol IF NOT EXISTS
FOR (n:Gene) ON (n.symbol);

// 附加索引 1：跨类型英文名搜索（支撑阶段4 /v1/entity/search，任务指引第十二章）
CREATE INDEX entity_name IF NOT EXISTS
FOR (n:Entity) ON (n.name);

// 附加索引 2：中文名搜索（任务指引第十七章“中文命中”、第二十章“中文搜索命不中”）
CREATE INDEX entity_name_zh IF NOT EXISTS
FOR (n:Entity) ON (n.name_zh);
