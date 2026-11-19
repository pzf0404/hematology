# 数据源许可审查（V1）

- 审查日期：2026-11-19
- 项目用途：科研与内部辅助，不用于直接临床决策
- 审查方式：逐一核验官方下载页、官方文档、仓库元数据与本地数据文件，不采用二传链接
- 取证记录：`docs/01_source_evaluation.xlsx`（URL、版本、下载时间、SHA256、大小、`verification_note`）

## 一、结论摘要

| 数据源 | 数据许可 | 可商用 | V1 用途 | 关键约束 |
|---|---|---|---|---|
| OptimusKG | CC BY-NC-SA 4.0（数据）；MIT（代码） | 否 | 仅评估，未入图 | 非商业 + 相同方式共享 |
| Open Targets | CC0 1.0（平台数据） | 是 | 药物、靶点、药物—疾病证据 | 上游逐源仍有署名/相同方式共享要求 |
| Monarch KG | 下载页未声明统一许可；入图上游已逐源核对 | 是（OMIM 记录除外） | 主数据源 | 上游逐源许可；OMIM 记录不得未经许可再分发 |
| DisMech | BSD-3-Clause（仓库） | 是（版权人待确认） | 机制与表型补充 | AI 辅助整理；LICENSE 为模板占位 |
| PrimeKG | CC0 1.0（数据）；MIT（代码） | 是 | 历史参考 | 2022 版，未覆盖 SAA |
| Hetionet | CC0 1.0（README 声明） | 是 | 测试参考 | 2017 版，仅 137 个疾病，种子未命中 |
| OpenBioLink | MIT（代码）；数据逐源 | 是（代码） | 测试参考 | benchmark 性质，数据需逐源核对 |

**总体判断：V1 可用于科研与非商业内部部署。对外分发前必须剔除 OMIM 贡献记录或取得授权；包含 OptimusKG 数据的衍生子图不得商用，且须按 CC BY-NC-SA 4.0 分发。**

## 二、逐源说明

### 1. OptimusKG

- 数据版本：Harvard Dataverse V3.2，2026-09-09
- 数据许可：CC BY-NC-SA 4.0（https://creativecommons.org/licenses/by-nc-sa/4.0）
- 代码许可：MIT（GitHub: mims-harvard/optimuskg）
- 官方入口：https://optimuskg.ai/docs ；https://doi.org/10.7910/DVN/IYNGEV
- 上游说明：整合约 65 个数据资源，各资源保留自身许可，部分限制再分发或商业使用
- 风险：
  1. 数据为非商业许可，商用需另行授权；
  2. ShareAlike 要求衍生子图以相同许可分发；
  3. 官网统计（192,813 节点 / 21,834,669 边）与 Dataverse V3.2（190,939 / 21,818,752）不一致，以 Dataverse V3.2 为版本基线
- V1 结论：仅作来源评估，未进入正式图谱

### 2. Open Targets

- 版本：26.09，2026-09-24，季度更新
- 许可：CC0 1.0（平台数据集）
- 官方入口：https://platform.opentargets.org/downloads
- 官方许可页：https://platform-docs.opentargets.org/licence
- 上游说明：licence 页逐源列出 CC BY 4.0、CC BY-SA 3.0、CC0 1.0、Apache 2.0 及 “Commercial use for Open Targets” 等条款；再分发时仍需保留上游署名/相同方式共享要求
- V1 结论：入图 38,551 条边；按数据集裁剪，不整库入图

### 3. Monarch KG

- 版本：固定路径 `2026-11-11`（不使用 `latest`）
- 文件：`monarch-kg.tar.gz`，368,326,109 字节，SHA256 `74B9CD49…AA18694C2`，Last-Modified 2026-11-12
- 许可：下载页未标注统一许可；官方 About 页称整合 33 个生物医学资源
- 文件实测：边表 16,961,180 行；`provided_by` 39 个、`primary_knowledge_source` 195 个（与 About 页统计口径不同，以文件枚举为准）
- 官方入口：https://monarchinitiative.org/kg/downloads
- 格式：KGX TSV、KGX JSONL、RDF、Neo4j dump、DuckDB
- V1 结论：主数据源；逐文件记录 SHA256、字节数与版本，许可按最终入图数据集逐源核对（见第四节）

### 4. DisMech

- 版本：固定提交 `38c23e10b0285becf70a0416fdb267698dfd20fe`（release v0.1.47，2026-11-06）
- 许可：仓库 LICENSE 为 BSD-3-Clause，但原文为模板占位（`Copyright (c) 2025 My Name`，第三条提及 `pytest-dismech`）
- 官方入口：https://github.com/monarch-initiative/dismech
- 内容性质：AI 辅助整理，经人工 PR 审核；引用校验不等同于科学正确性
- 覆盖实测：4,011 个疾病 YAML；有 ALL / CLL / CML；AML 仅 CEBPA 变体；无 APL、无获得性 AA；仅 Inherited AA
- V1 结论：仅作机制补充，不单独支撑临床结论；入图 63 条边

### 5. 参考源（未入图）

- **PrimeKG**：数据 CC0 1.0（Harvard Dataverse v2.1，2022-05-02），代码 MIT；17,080 个 MONDO 疾病，SAA 未覆盖
- **Hetionet**：数据 CC0 1.0（README 声明，逐节点/边带 license 属性）；v1.0（2017），仅 137 个 DO 疾病，6 个种子均未命中
- **OpenBioLink**：代码 MIT，数据逐源许可；OpenBioLink2020 HQ_DIR（Zenodo 3834052），9,509 个 DOID 疾病，无 SAA 独立实体

## 三、合规动作

1. 每个源保存官方 URL、下载时间、版本、文件大小、SHA256、License 原文
2. `build_manifest.json` 逐源记录版本与许可
3. 每条正式边保留 `source / source_version / source_record_id / license`
4. 包含 OptimusKG 数据的子图对外分发时按 CC BY-NC-SA 4.0
5. 不把任何数据源全量复制进 API 镜像或 Neo4j volume
6. 对外分发前剔除 OMIM 贡献记录或取得授权；DisMech / ClinGen 的残余不确定项须复核

## 四、入图数据集许可核对

核对方法：对 `data/processed/edges.csv` 的 `source_dataset` 逐条反查。多源合并边会在多个数据集重复计数，故各行之和大于 284,023。

| 入图数据集 | 覆盖边数 | 上游 | 许可结论 |
|---|---:|---|---|
| go_annotation_edges | 102,777 | Gene Ontology | CC BY 4.0，保留署名 |
| clinvar_variant_edges | 98,168 | ClinVar | 公共数据，建议署名 |
| reactome_gene_to_pathway_edges | 41,605 | Reactome | CC0 1.0 |
| open_targets | 38,551 | Open Targets 平台 | CC0 1.0；上游条款已留档 |
| clingen_variant_edges | 8,328 | ClinGen | 未找到独立许可页，按公开数据引用（残余不确定） |
| phenio_edges | 114 | PhenIO / HPO | HPO 自定义许可，需署名 |
| dismech | 63 | DisMech | BSD-3-Clause；版权人待确认 |
| hpoa_disease_to_phenotype_edges | 57 | HPO 注释 | HPO 自定义许可；部分原始记录上游为 OMIM |
| omim_gene_to_disease_edges | 17 | OMIM | 禁止未经许可再分发（残余风险） |

### 4.1 残余风险与处理

1. **OMIM（必须处理）**：27 条入图边可回溯到 OMIM：
   - 17 条基因—疾病，`source_dataset` 含 `omim_gene_to_disease_edges`，全部有 Open Targets 共支撑；
   - 10 条疾病—表型，经 `hpoa_disease_to_phenotype_edges` 进入，边上未标 OMIM。
   OMIM 条款禁止未经许可再分发。V1 仅限内部科研使用；对外分发前必须剔除 OMIM 贡献记录，或在 ETL 增加 `--exclude-omim` 重跑。
2. **DisMech LICENSE**：原文为模板占位，需维护方书面确认权利归属；确认前仅作内部机制补充。
3. **ClinGen**：未找到独立公开许可页，按公开数据引用并保留来源；对外分发前复核官网条款。
4. **HPO / HPOA**：HPO 为自定义许可，需署名；商用或再分发前复核官网条款。
