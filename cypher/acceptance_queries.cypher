// 血液病知识图谱 V1 — 阶段 3 示例 Cypher（任务指引 十一「查询模板」/ 十八「验收问题集」可执行版）
// 数据基线（阶段 2 冻结）：节点 125,759；关系 280,999
// 注释里的“实测”数字来自对 data/processed/*.csv 的只读统计；导入后执行应一致。
// 用法：Neo4j Browser（http://127.0.0.1:7474）或 docker exec -it hematology-neo4j cypher-shell -u neo4j -p <密码>

// ---------- 0. 规模与类型分布核验 ----------
MATCH (n:Entity) RETURN count(n) AS nodes;              // 期望 125759
MATCH ()-[r]->() RETURN count(r) AS edges;              // 期望 280999
MATCH (n:Entity) UNWIND labels(n) AS lab
RETURN lab, count(*) AS c ORDER BY c DESC;

// ---------- 1. 急性髓系白血病有哪些已知相关基因？（实测 11,438） ----------
MATCH (g:Gene)-[r:ASSOCIATED_WITH]->(d:Disease {id: 'MONDO:0018874'})
RETURN g.id AS gene_id, g.symbol AS symbol,
       r.original_predicate AS original_predicate, r.source AS source,
       r.source_record_id AS record
ORDER BY symbol LIMIT 20;

// ---------- 2. APL 与 PML-RARA 有什么关系？ ----------
// 2a MONDO 把 t(15;17) / PML-RARalpha 记录在 APL 的标准同义词中
MATCH (d:Disease {id: 'MONDO:0012883'})
RETURN d.name AS name, d.name_zh AS name_zh, d.synonyms AS synonyms;
// 2b PML、RARA 两个基因均与 APL 存在 ASSOCIATED_WITH（实测均存在）
MATCH (g:Gene)-[r:ASSOCIATED_WITH]->(d:Disease {id: 'MONDO:0012883'})
WHERE g.symbol IN ['PML', 'RARA']
RETURN g.symbol AS gene, r.original_predicate AS original_predicate, r.source AS source;

// ---------- 3. FLT3 与 AML 有什么关系？ ----------
MATCH (g:Gene {symbol: 'FLT3'})-[r:ASSOCIATED_WITH]->(d:Disease {id: 'MONDO:0018874'})
RETURN g.id AS gene_id, d.id AS disease_id, r.original_predicate AS original_predicate,
       r.source AS source, r.source_record_id AS record, r.pmid AS pmid;

// ---------- 4. 哪些药物与 APL 相关？（实测 31） ----------
MATCH (dr:Drug)-[r:TREATS]->(d:Disease {id: 'MONDO:0012883'})
RETURN dr.name AS drug, r.source AS source, r.source_record_id AS record
ORDER BY drug LIMIT 50;

// ---------- 5. CML 相关的关键分子异常有哪些？ ----------
// 5a ABL1 上的变异（AFFECTS 方向：Variant → Gene）
MATCH (v:Variant)-[r:AFFECTS]->(g:Gene {symbol: 'ABL1'})
RETURN v.id AS variant, v.name AS variant_name, r.source AS source LIMIT 20;
// 5b CML 关联基因总数（实测 4,449）
MATCH (g:Gene)-[:ASSOCIATED_WITH]->(d:Disease {id: 'MONDO:0011996'})
RETURN count(g) AS cml_genes;

// ---------- 6. ALL 有哪些相关基因或分子机制？（实测 7,752） ----------
MATCH (g:Gene)-[:ASSOCIATED_WITH]->(d:Disease {id: 'MONDO:0004967'})
RETURN count(g) AS all_genes;

// ---------- 7. CLL 常见的疾病相关基因有哪些？（实测 5,148） ----------
MATCH (g:Gene)-[:ASSOCIATED_WITH]->(d:Disease {id: 'MONDO:0004948'})
RETURN count(g) AS cll_genes;

// ---------- 8. 再生障碍性贫血有哪些典型血液学表型？（实测 2） ----------
MATCH (d:Disease {id: 'MONDO:0015909'})-[r:HAS_PHENOTYPE]->(p:Phenotype)
RETURN p.id AS phenotype_id, p.name AS phenotype, r.source AS source,
       r.original_predicate AS original_predicate;

// ---------- 9. 再生障碍性贫血与免疫相关机制有哪些关联？（实测 117 个免疫类 BP） ----------
MATCH (g:Gene)-[:ASSOCIATED_WITH]->(d:Disease {id: 'MONDO:0015909'})
MATCH (g)-[:INVOLVED_IN]->(b:BiologicalProcess)
WHERE toLower(b.name) CONTAINS 'immun'
RETURN b.id AS bp_id, b.name AS biological_process, count(g) AS gene_count
ORDER BY gene_count DESC LIMIT 20;

// ---------- 10. 环孢素与再生障碍性贫血之间是什么关系？ ----------
MATCH (dr:Drug)-[r:TREATS]->(d:Disease {id: 'MONDO:0015909'})
WHERE toUpper(dr.name) CONTAINS 'CYCLOSPORINE'
RETURN dr.name AS drug, d.name AS disease, r.source AS source, r.source_record_id AS record;

// ---------- 11. 造血干细胞移植与再障是什么关系？V1 无 Treatment 节点（已知缺口），预期 0 行 ----------
MATCH (n)
WHERE toUpper(n.name) CONTAINS 'HEMATOPOIETIC STEM CELL TRANSPLANT'
   OR n.name_zh CONTAINS '造血干细胞移植'
RETURN n.id AS id, n.name AS name, n.name_zh AS name_zh LIMIT 5;

// ---------- 11b. 补充：伊马替尼是否治疗 CML？ ----------
MATCH (dr:Drug)-[r:TREATS]->(d:Disease {id: 'MONDO:0011996'})
WHERE toUpper(dr.name) CONTAINS 'IMATINIB'
RETURN dr.name AS drug, r.source AS source, r.source_record_id AS record;

// ---------- 12. 血小板减少可以关联到哪些种子疾病？（实测 4：APL/ALL/CML/CLL） ----------
MATCH (d:Disease)-[:HAS_PHENOTYPE]->(p:Phenotype {id: 'HP:0001873'})
RETURN d.id AS disease_id, d.name AS disease, d.name_zh AS name_zh;

// ---------- 13. 某一基因通过哪些通路与 AML 产生关联？（FLT3 示例） ----------
MATCH (g:Gene {symbol: 'FLT3'})-[rp:PARTICIPATES_IN]->(pw:Pathway)
MATCH (g)-[ra:ASSOCIATED_WITH]->(d:Disease {id: 'MONDO:0018874'})
RETURN pw.id AS pathway_id, pw.name AS pathway,
       ra.original_predicate AS original_predicate, ra.source AS source LIMIT 30;

// ---------- 14. 某药物的靶点是否与某白血病疾病节点关联？（实测 1,791 条完整路径） ----------
MATCH (d:Disease {id: 'MONDO:0018874'})<-[:ASSOCIATED_WITH]-(g:Gene)<-[rt:TARGETS]-(dr:Drug)
RETURN dr.name AS drug, g.symbol AS target_gene,
       rt.source AS source, rt.source_record_id AS record LIMIT 10;

// ---------- 15. 同一疾病中文名、英文名、缩写能否命中同一实体？ ----------
// 精确名优先；缩写 'AML' 会同时命中多个含该同义词的亚型（阶段 4 实体搜索按匹配精确度排序）
MATCH (d:Disease)
WHERE d.name = 'acute myeloid leukemia'
   OR d.name_zh = '急性髓系白血病'
   OR 'AML' IN split(d.synonyms, '|')
RETURN d.id AS disease_id, d.name AS name, d.name_zh AS name_zh
ORDER BY CASE WHEN d.id = 'MONDO:0018874' THEN 0 ELSE 1 END, d.id LIMIT 20;

// ---------- 16. 边溯源抽查（任务指引二十二：抽查 30 条边可追溯） ----------
MATCH ()-[r]->()
RETURN r.edge_id AS edge_id, r.source AS source, r.source_dataset AS dataset,
       r.source_version AS version, r.source_record_id AS record,
       r.original_predicate AS original_predicate, r.license AS license
LIMIT 30;

// ---------- 17. 孤立节点检查（阶段 2 校验为 0） ----------
MATCH (n:Entity) WHERE NOT (n)--()
RETURN count(n) AS isolated_nodes;
