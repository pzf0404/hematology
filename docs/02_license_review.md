# 数据源许可审查（V1）

- 审查日期：2026-11-09
- 项目用途：研发 / 科研辅助，不用于直接临床决策
- 审查方式：逐一核验官方下载页、官方文档与仓库元数据，未采用二转链接
- 复核（2026-11-13，2026-11-19 随 Monarch 2026-11-11 基线更新评估表）：通过 Dataverse API、官方 README 与样本数据实测，补齐参考源许可与疾病覆盖度（取证记录见 `01_source_evaluation.xlsx` 的 `verification_note` 列）

## 一、结论摘要

| 数据源 | 数据许可 | 是否可商用 | V1 可用性 | 关键约束 |
|---|---|---|---|---|
| OptimusKG | CC BY-NC-SA 4.0（数据）；MIT（代码） | **否** | 可用（科研） | 非商业 + 相同方式共享 |
| Open Targets | CC0 1.0 | 是（平台数据集） | 可用 | 个别上游源仍可能有附加条款 |
| Monarch KG | 下载页未声明统一许可；入图上游已逐源核对（见 §四） | 是（OMIM 记录除外） | 可用（已闭环） | 上游逐源许可（About 页称 33 个；文件实测 provided_by 39、primary_knowledge_source 195）；实际入图 9 类数据集 |
| DisMech | BSD-3-Clause（仓库） | 是（BSD-3 允许，版权人待确认） | 仅机制补充 | AI 生成内容；版权人字段为占位符 |
| PrimeKG | 数据 CC0 1.0（Dataverse）；代码 MIT | 是 | 仅历史参考 | 数据为 2022 版；SAA 未覆盖 |
| Hetionet | 数据 CC0 1.0（README 声明）；逐节点/边 license 属性 | 是（数据 CC0；上游逐源） | 仅测试参考 | 数据为 2017 版，仅 137 个疾病；种子 0 命中 |
| OpenBioLink | 代码 MIT；数据集逐源 | 是（代码）；数据需逐源核对 | 仅测试参考 | benchmark 性质 |

**总体判断：V1 可用于科研与非商业内部部署；禁止将包含 OptimusKG 数据的子图用于商业用途或闭源分发。对外分发前还需剔除 OMIM 贡献记录或取得授权（见 §四）。**

## 二、逐源说明

### 1. OptimusKG

- 数据版本：Harvard Dataverse **V3.2**，发布日期 **2026-09-09**
- 数据许可：**CC BY-NC-SA 4.0**（https://creativecommons.org/licenses/by-nc-sa/4.0）
- 代码许可：MIT（GitHub: mims-harvard/optimuskg）
- 官方入口：https://optimuskg.ai/docs ；https://doi.org/10.7910/DVN/IYNGEV
- 上游说明：整合约 65 个数据资源，每个资源保留自身许可；部分资源限制再分发、商业使用或下游应用
- 风险：
  1. 数据为**非商业**许可，商用需另行取得授权
  2. ShareAlike：若对外分发包含其数据的衍生子图，需以相同许可分发
  3. 官网统计（192,813 节点 / 21,834,669 边）与 Dataverse V3.2（190,939 / 21,818,752）不一致，**以 Dataverse V3.2 为版本基线并记录差异**

### 2. Open Targets

- 版本：**26.09**，发布日期 **2026-09-24**，季度更新
- 许可：**CC0 1.0**（平台数据集）
- 官方入口：https://platform.opentargets.org/downloads
- 官方许可页：https://platform-docs.opentargets.org/licence
- 上游说明：平台数据整体为 CC0 1.0；官方 licence 页的 "Data sources licensing" 表逐源列出上游许可，包含 CC-BY 4.0、CC BY 4.0、CC-BY-SA 3.0、CC0 1.0、Apache 2.0，以及标注 "Commercial use for Open Targets" 的源。页面明确说明这些源已同意在 Open Targets 内无限制使用；但再分发时仍需逐源保留署名/相同方式共享要求
- 风险：全量数据体积大，只能按数据集下载并裁剪，禁止整库入图

### 3. Monarch KG

- 版本：固定版本路径 `2026-11-11`（不再使用 `latest`）；本次下载文件 `Last-Modified: 2026-11-12`，SHA256 `74B9CD49…AA18694C2`
- 许可：下载页**未标注统一许可**；官方 About 页称整合 33 个生物医学资源
- 实测来源数（本次下载文件）：边表 **16,961,180 行**，`provided_by` **39 个**、`primary_knowledge_source` **195 个**（与 About 页的 33 个统计口径不同，以文件枚举为准记录）
- 官方入口：https://monarchinitiative.org/kg/downloads
- 格式：KGX TSV、KGX JSONL、RDF、Neo4j dump、DuckDB
- 风险：即使固定版本 URL，也须记录**文件 SHA256 与字节数**；许可需逐源核对后再对外分发

### 4. DisMech

- 版本：**v0.1.47**，发布 **2026-11-06**
- 许可：仓库 LICENSE 为 **BSD-3-Clause**，但已核对原文：`Copyright (c) 2025 My Name`，且第三条写 `pytest-dismech`，确认是模板占位符，需向维护方书面确认后再正式引用
- 官方入口：https://github.com/monarch-initiative/dismech ；https://dismech.monarchinitiative.org/app/
- 内容性质：**AI-curated**，人工 PR 审核；引用与片段校验不等同于科学正确性
- 覆盖实测（4,011 个疾病 YAML）：有 ALL / CLL / CML；AML 仅 CEBPA 变体；**无 APL、无获得性 AA**；仅 Inherited AA（不得并入 AA）
- 风险：**不能作为唯一证据源**，只能作机制层补充

### 5. 参考源

- **PrimeKG**：数据许可 **CC0 1.0**（Harvard Dataverse v2.1，2022-05-02），代码 MIT；最后推送 2026-06-30。数据 17,080 个疾病（MONDO），AML/APL/ALL/CML/CLL/AA 命中，SAA 未覆盖；仅历史参考，已被 OptimusKG 取代
- **Hetionet**：数据许可 **CC0 1.0**（仓库 README 声明，逐节点/边带 license 属性；上游 29 个数据库各自许可保留）。v1.0（2017），最后推送 2023-04-03；Disease 节点仅 137 个（DO），AML/APL/ALL/CML/CLL/AA 均未命中，不能承担 V1 疾病覆盖；仅测试参考
- **OpenBioLink**：代码 MIT，数据集为多源衍生、逐源许可；OpenBioLink2020 HQ_DIR（Zenodo 3834052），最后推送 2024-05-03。节点 7 类、DIS 9,509 个（DOID），6 个核心种子均命中，无 SAA 独立实体；仅测试参考

## 三、合规动作（必须执行）

1. 每个源保存：官方 URL、下载时间、版本、文件大小、**SHA256**、License 原文
2. 生成 `build_manifest.json`，逐源记录版本与许可
3. 正式边必须带 `source / source_version / source_record_id`
4. 对外分发包含 OptimusKG 数据的子图时，按 **CC BY-NC-SA 4.0** 分发
5. 不得将任何数据源的全量数据复制进 API 镜像或 Neo4j volume
6. 对外分发前必须剔除 OMIM 贡献记录或取得 OMIM 授权（见 §四）；DisMech/ClinGen 的残余不确定项须在对外分发前复核

## 四、逐源许可核对结果与残余风险

核对日期：2026-11-18。方法：对 `data/processed/edges.csv` 的 `source_dataset` 逐条反查，统计实际入图的上游数据集；多源合并边会在多个数据集重复计数，故各行之和大于 284,023。

| 入图数据集 | 覆盖边数 | 上游 | 许可结论 |
|---|---:|---|---|
| go_annotation_edges | 102,777 | Gene Ontology | CC BY 4.0，保留署名 |
| clinvar_variant_edges | 98,168 | ClinVar | 公共数据，可自由使用，建议署名 |
| reactome_gene_to_pathway_edges | 41,605 | Reactome | CC0 1.0 |
| open_targets | 38,551 | Open Targets 平台 | CC0 1.0；上游逐源条款已留档，再分发保留署名/相同方式共享 |
| clingen_variant_edges | 8,328 | ClinGen | 未找到独立公开许可页，按公开数据引用（残余不确定） |
| phenio_edges | 114 | PhenIO / HPO | HPO 自定义许可，需署名；商用前复核官网条款 |
| dismech | 63 | DisMech | BSD-3-Clause；版权人仍为占位符（残余风险） |
| hpoa_disease_to_phenotype_edges | 57 | HPO 注释 | HPO 自定义许可；其中部分原始记录上游为 OMIM |
| omim_gene_to_disease_edges | 17 | OMIM | 禁止未经许可再分发（残余风险） |

### 4.1 已办结

- **Monarch KG 逐源许可**：已按最终入图边反查并逐源核对（上表），不再以“逐源核对中”挂起。
- **Open Targets 上游许可留档**：`https://platform-docs.opentargets.org/licence` 的 “Data sources licensing” 表已核实；平台数据 CC0 1.0，再分发保留上游署名/相同方式共享要求。

### 4.2 残余风险与处理

1. **OMIM（必须处理）**：27 条入图边可回溯到 `primary_knowledge_source=OMIM` 或 `omim_gene_to_disease_edges`（2026-11-18 对 `monarch-kg_edges.tsv` 逐行复核）：
   - 17 条基因—疾病，`source_dataset` 均显式含 `omim_gene_to_disease_edges`，且全部有 Open Targets 共支撑（其中 2 条另并入 HPOA/DisMech）；
   - 10 条疾病—表型，经 `hpoa_disease_to_phenotype_edges` 进入，边上未标 OMIM。

   OMIM 条款禁止未经许可再分发。V1 作为非商业内部科研使用保留；**对外分发前必须**剔除 OMIM 贡献记录（或在 ETL 增加 `--exclude-omim` 重跑开关），或取得 OMIM 授权。17 条基因—疾病边均有 Open Targets 共支撑，剔除 OMIM 归属后语义不变；10 条表型边需在分发前复核 HPOA 原始记录归属。
2. **DisMech LICENSE**：已核对原文为模板（`Copyright (c) 2025 My Name` / `pytest-dismech`），仍需维护方书面确认权利归属；确认前仅作内部机制补充。
3. **ClinGen**：未找到独立公开许可页，按公开数据引用并保留来源；对外分发前复核官网条款。
4. **HPO/HPOA**：HPO 为自定义许可，需署名；商用或再分发前复核官网条款。
