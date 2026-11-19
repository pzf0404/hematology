# 阶段 2 数据校验报告（V1）

- 生成时间：2026-11-19T08:57:42+08:00
- 节点：128783
- 边：284023
- 结论：PASS 28 项，FAIL 0 项

## 一、完整性检查

| 类别 | 检查项 | 结果 | 证据 |
|---|---|---|---|
| 完整性 | 交付文件存在 | PASS | nodes.csv=True, edges.csv=True |
| 完整性 | UTF-8 无 BOM | PASS | nodes BOM=False, edges BOM=False |
| 完整性 | nodes 列与任务文档一致 | PASS | id|label|name|name_zh|canonical_id|synonyms|source_ids|xrefs|description|source|source_version|retrieved_at |
| 完整性 | edges 列与任务文档一致 | PASS | edge_id|subject_id|predicate|object_id|original_predicate|source|source_dataset|source_version|source_record_id|evidence_score|pmid|doi|license|retrieved_at |
| 完整性 | 节点 id 唯一 | PASS | 节点 128783，重复 0 |
| 完整性 | 节点必填字段非空 | PASS | 全部非空 |
| 实体策略 | 节点类型均在 V1 策略内 | PASS | 分布={'Drug': 867, 'Variant': 100877, 'Disease': 115, 'Gene': 13886, 'BiologicalProcess': 10701, 'Phenotype': 61, 'Pathway': 2276}；越界=无 |
| 中文覆盖 | 种子疾病中文名齐全 | PASS | AML=急性髓系白血病；APL=急性早幼粒细胞白血病；ALL=急性淋巴细胞白血病；CML=慢性髓性白血病；CLL=慢性淋巴细胞白血病；AA=再生障碍性贫血；acquired AA=获得性再生障碍性贫血；SAA=重型再生障碍性贫血 |
| 中文覆盖 | 表型中文名覆盖 | PASS | 61/61 |
| 完整性 | 边三元组唯一 | PASS | 边 284023，唯一三元组 284023，重复三元组 0 |
| 完整性 | edge_id 唯一 | PASS | 唯一 284023 |
| 完整性 | 引用完整性 | PASS | 悬空边 0 |
| 关系白名单 | 关系方向与白名单一致 | PASS | 越界 0 条：无 |
| 关系白名单 | 8 类启用关系是否全部可用 | PASS | 实际 8 类：{'AFFECTS': 100885, 'ASSOCIATED_WITH': 35204, 'HAS_PHENOTYPE': 80, 'INVOLVED_IN': 102790, 'PARTICIPATES_IN': 41605, 'SUBTYPE_OF': 112, 'TARGETS': 1820, 'TREATS': 1527} |
| 完整性 | 边必填字段非空 | PASS | 全部非空 |
| 完整性 | 许可字段完整 | PASS | 缺 license 0 条 |
| 完整性 | 证据可追溯率 | PASS | 284023/284023（pmid 或 source_record_id 至少一项） |
| 完整性 | 无孤立节点 | PASS | 孤立节点 0，例如 [] |
| 种子覆盖 | 种子 AML 已入图且有连接 | PASS | MONDO:0018874 度=12103 |
| 种子覆盖 | 种子 APL 已入图且有连接 | PASS | MONDO:0012883 度=2071 |
| 种子覆盖 | 种子 ALL 已入图且有连接 | PASS | MONDO:0004967 度=8086 |
| 种子覆盖 | 种子 CML 已入图且有连接 | PASS | MONDO:0011996 度=4650 |
| 种子覆盖 | 种子 CLL 已入图且有连接 | PASS | MONDO:0004948 度=5509 |
| 种子覆盖 | 种子 AA 已入图且有连接 | PASS | MONDO:0015909 度=4310 |
| 种子覆盖 | 种子 acquired AA 已入图且有连接 | PASS | MONDO:0015610 度=76 |
| 种子覆盖 | 种子 SAA 已入图且有连接 | PASS | EFO:0006927 度=120 |
| 异常报告 | 异常边已暂存并注明原因 | PASS | 暂存 320 条（CSV 320 行）；原因={'白名单无 Variant→Disease 箭头': 320}；按谓词={'ASSOCIATED_WITH_INCREASED_LIKELIHOOD_OF': 5, 'CAUSES': 315} |
| 异常报告 | 白名单谓词非法类型组合已入异常报告 | PASS | 710536 条，13 类组合；Top={'biolink:has_phenotype|Gene->Phenotype': 294904, 'biolink:causes|Variant->Disease': 192331, 'biolink:participates_in|ChemicalEntity->Pathway': 109374, 'biolink:subclass_of|ChemicalEntity->ChemicalEntity': 40875, 'biolink:subclass_of|BiologicalProcess->BiologicalProcess': 40486} |

## 二、验收问题抽查

| 问题 | 结果 | 证据 |
|---|---|---|
| 某药物的靶点是否与某白血病疾病节点关联？ | PASS | 示例：VATALANIB → TARGETS → HGNC:2433 → ASSOCIATED_WITH → CML |
| 环孢素是否与再生障碍性贫血关联？ | PASS | CYCLOSPORINE → TREATS → AA |
| 伊马替尼是否治疗 CML？ | PASS | IMATINIB MESYLATE → TREATS → CML；IMATINIB → TREATS → CML |
| APL 是否作为独立节点并可关联到上级疾病？ | PASS | APL 的 SUBTYPE_OF 目标：['MONDO:0017893'] |
| AML 是否有表型关联？ | PASS | AML 直接表型 2 个，例如 ['Anemia', 'Acute myeloid leukemia'] |
| 基因能否同时关联通路与生物过程？ | PASS | 8600 个基因，例如 ['HGNC:100', 'HGNC:10000', 'HGNC:10001'] |

## 三、节点类型分布

| 类型 | 数量 |
|---|---|
| BiologicalProcess | 10701 |
| Disease | 115 |
| Drug | 867 |
| Gene | 13886 |
| Pathway | 2276 |
| Phenotype | 61 |
| Variant | 100877 |

## 四、关系分布

| 谓词 | 边数 |
|---|---|
| AFFECTS | 100885 |
| ASSOCIATED_WITH | 35204 |
| HAS_PHENOTYPE | 80 |
| INVOLVED_IN | 102790 |
| PARTICIPATES_IN | 41605 |
| SUBTYPE_OF | 112 |
| TARGETS | 1820 |
| TREATS | 1527 |

## 五、异常与暂存

- 来源报告：data/staging/normalize_report.json（生成时间 2026-11-18T16:19:30+08:00）
- 白名单外暂存边：320 条，全部保留原始三元组与溯源字段，未进入 data/processed/edges.csv
- 暂存明细：data/staging/edges_staged.csv
- 同三元组合并的重复原始记录：94120 条（多来源证据已聚合，source 以 | 并列，未抹掉任何来源）

### 5.1 暂存边按谓词

| 原始谓词 | 条数 |
|---|---|
| ASSOCIATED_WITH_INCREASED_LIKELIHOOD_OF | 5 |
| CAUSES | 315 |

### 5.2 暂存原因

| 原因 | 条数 |
|---|---|
| 白名单无 Variant→Disease 箭头 | 320 |

### 5.3 直接丢弃的原始行

| 原因 | 行数 |
|---|---|
| biolink:model_of\|Genotype 非 V1 节点类型 | 86 |

### 5.4 白名单谓词但端点类型不符（未入图）

共 710536 条，按“原谓词|subject类型->object类型”聚合，全部未写入正式图：

| 原谓词 | 端点类型 | 条数 |
|---|---|---|
| biolink:has_phenotype | Gene->Phenotype | 294904 |
| biolink:causes | Variant->Disease | 192331 |
| biolink:participates_in | ChemicalEntity->Pathway | 109374 |
| biolink:subclass_of | ChemicalEntity->ChemicalEntity | 40875 |
| biolink:subclass_of | BiologicalProcess->BiologicalProcess | 40486 |
| biolink:subclass_of | Phenotype->Phenotype | 24443 |
| biolink:associated_with_increased_likelihood_of | Variant->Disease | 8006 |
| biolink:has_phenotype | Disease->Disease | 86 |
| biolink:participates_in | BiologicalProcess->ChemicalEntity | 11 |
| biolink:causes | Disease->Gene | 10 |
| biolink:causes | BiologicalProcess->BiologicalProcess | 7 |
| biolink:causes | Disease->BiologicalProcess | 2 |
| biolink:subclass_of | Phenotype->Disease | 1 |

## 六、已知限制

- 疾病中文名覆盖 8/115：非种子疾病（MONDO 父类与直接子类）无官方中文名，字段留空而不臆造
- 治疗方案/HSCT：任务文档关系白名单未定义“治疗方案”关系，DisMech 的 20 条治疗条目（含造血干细胞移植）按白名单规则不入正式图，明细见 data/staging/staged_dismech_treatments.csv；因此“造血干细胞移植与再障是什么关系”在 V1 只能回答“无图内关系证据”，需由指南/文献文本证据补充
- 种子疾病直接表型合计 80 条，其中 AML 仅 2 个；HPO 对白血病/再障注释稀疏，'临床表现'类问答覆盖有限
