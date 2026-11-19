# 案例 AML：AML 伴 FLT3 突变的治疗

> 由 RAGFlow 画布 `hematology_kg_rag_v1` 实际运行产出，原文存档，未改写。
> 运行时间：2026-11-11 16:25:02（Asia/Shanghai）｜agent_id：`e75a102daebc43d3b327e0c64b3b0de4`｜session_id：`aa8dc44807ad426794872e703c648cca`
> 请求体：`{"user_input":"AML 伴 FLT3 突变如何治疗"}`

## 1. 判定基线（本案例必须满足）

- 病种路由：`AML`，实体 `MONDO:0018874`
- 关系证据：至少 1 条 `SUBTYPE_OF`（Monarch KG）
- 指南证据：Retrieval 必须返回非空原文，且来源属于 `ELN_2022_AML_recommendations.pdf、NHC_慢性髓性白血病诊疗指南_2022.pdf、NHC_成人急性髓系白血病诊疗规范_2018.docx` 等语料
- 回答：给出该病种的治疗结论，且带引用标记（`[n]` 或 `[ID:…]`）

## 2. 实际命中

### 2.1 前置节点

- 查询规划 Agent 输出：`AML`
- 检索词生成 Agent 输出：`AML伴FLT3突变治疗指南`

### 2.2 HTTP 请求（KG `/v1/kg/context`）

- `disease_route`：`AML`
- `query`：`AML伴FLT3突变治疗指南`
- 图谱命中实体：1 个 → `MONDO:0018874`
- 路径数：5；`evidence_types`：`{"knowledge_graph": true, "guideline_text": false}`
- `context` 长度：931 字符

路径明细：

| # | 起点 | 终点 | 关系 | 来源 | edge_id |
|---|---|---|---|---|---|
| 1 | `MONDO:0018874` 急性髓系白血病 | `MONDO:0010643` acute leukemia | SUBTYPE_OF | Monarch KG 2026-10-07 | `6518e549e9578f5a1680f310` |
| 2 | `MONDO:0018874` 急性髓系白血病 | `MONDO:0004643` myeloid leukemia | SUBTYPE_OF | Monarch KG 2026-10-07 | `93155622c5862fe9a39337ec` |
| 3 | `MONDO:0018874` 急性髓系白血病 | `MONDO:0019457` therapy related acute myeloid leukemia and myelodysplastic syndrome | SUBTYPE_OF | Monarch KG 2026-10-07 | `bc8141b8fb8949159cb3d062` |
| 4 | `MONDO:0018874` 急性髓系白血病 | `MONDO:0100424` acute myeloid leukemia, NRAS gene mutation | SUBTYPE_OF | Monarch KG 2026-10-07 | `d57ac38f37b26152412c2224` |
| 5 | `MONDO:0018874` 急性髓系白血病 | `MONDO:0004996` childhood acute myeloid leukemia | SUBTYPE_OF | Monarch KG 2026-10-07 | `d98622f575d4505274293dfb` |

### 2.3 知识检索（RAGFlow）

- `formalized_content` 长度：11059 字符
- 命中 chunk：8 个

| # | 来源文档 | 相似度 | 摘录 |
|---|---|---|---|
| 1 | ELN_2022_AML_recommendations.pdf | 0.8646 | It is recommended to enroll patients with AML onto clinical trials whenever a suitable tri… |
| 2 | ELN_2022_AML_recommendations.pdf | 0.8643 | ‡Concurrent KIT and/or FLT3 gene mutation does not alter risk categorization. §AML with NP… |
| 3 | NHC_慢性髓性白血病诊疗指南_2022.pdf | 0.8596 | ABL激酶区突变分析可以应用外周血或骨髓 为标本，推荐的方法为直接测序法（Sanger测序法，敏感性 为10%～20%）或针对BCR-ABL激酶区的二代测序，以发现 ABL激酶区点… |
| 4 | ELN_2022_AML_recommendations.pdf | 0.8580 | be available as rapidly as possible, preferably within 3 to 5 days, to identify therapeuti… |
| 5 | ELN_2022_AML_recommendations.pdf | 0.8578 | *Results from assessment of MRD should be taken into account for selecting the appropriate… |
| 6 | NHC_成人急性髓系白血病诊疗规范_2018.docx | 0.8528 | 低中危APL患者，ATRA联合砷剂作为一线治疗方案中建议预防性鞘内治疗；高危APL或复发患者，因发生CNSL的风险增加，对这些患者应进行至少2~6次预防性鞘内治疗。对于已诊断CNS… |
| 7 | NHC_成人急性髓系白血病诊疗规范_2018.docx | 0.8504 | 同时，随着近年新药的研发，AML的诱导治疗也可以在3+7方案的基础上加用其他药物，如目前美国已经上市的米哚妥林（midostaurin）和靶向CD33的免疫毒素GO单抗。此外，柔红… |
| 8 | NHC_成人急性髓系白血病诊疗规范_2018.docx | 0.8494 | <table> <tr><th>AML伴重现性遗传异常</th></tr> <tr><td>AML 伴 t（8；21）（q22；q22.1）；RUNX1-RUNX1T1</td><… |

## 3. 完整回答（原文）

> 注：API 返回的引用标记为 `[ID:<chunk_id>]`，UI 会渲染为 `[1]`…`[n]` 引用卡片（见 `screenshots/04_result.png`）。

以下是对临床问题 **“AML 伴 FLT3 突变如何治疗”** 的系统性回答，严格依据您提供的两类证据（知识图谱路径 + 指南原文），并按要求分三部分呈现：

---

### **1) 结论**

对于 **急性髓系白血病（AML）伴 FLT3 突变患者**，当前标准治疗策略如下：

#### ✅ **初诊、适合强化疗的患者（Fit for intensive therapy）**
- **一线诱导治疗**：  
  **“7+3”方案（柔红霉素/去甲氧柔红霉素 + 阿糖胞苷）联合FLT3抑制剂 midostaurin（米哚妥林）** 是标准方案（基于RATIFY试验）。  
  - Midostaurin显著改善4年总生存率（OS）：从44.3% → 51.4%（HR=0.78, *P*=0.009）[ID:c6b85eed93295094]；  
  - 适用于年龄18–59岁（部分研究扩展至≤70岁）[ID:c6b85eed93295094]；  
  - 巩固治疗推荐高剂量阿糖胞苷（3000 mg/m²），但临床实践中常用中剂量（1000–1500 mg/m²）[ID:b8b378fce0f45873]；  
  - **维持治疗价值尚不确定**（指南明确标注“uncertain”）[ID:b8b378fce0f45873][ID:c6b85eed93295094]。

- **新型FLT3抑制剂（如quizartinib）**：  
  - 在III期QuANTUM-R试验中，quizartinib单药用于复发/难治性FLT3-ITD⁺ AML显著延长OS（中位OS 6.2 vs 4.7个月）[ID:c6b85eed93295094]；  
  - 正在开展**一线联合化疗+quizartinib维持**的III期试验（NCT02668653），初步报告显示OS获益[ID:c6b85eed93295094]；  
  - 尚未获批一线适应症，但可考虑临床试验或超适应症使用（尤其对midostaurin不耐受者）[ID:c6b85eed93295094]。

#### ✅ **复发/难治性（R/R）患者**
- **首选靶向治疗**：  
  **Gilteritinib（吉列替尼）单药** 是FDA/NMPA批准的R/R FLT3突变AML标准治疗（ADMIRAL试验）：  
  - CR+CRh率 34% vs 化疗组 15.3%；  
  - 中位OS 9.3 vs 5.6个月（HR=0.63, *P*<0.001）[ID:1e2dd0968ead8437]；  
  - 特别适用于早期复发（<6个月）患者，疗效优于挽救性化疗[ID:1e2dd0968ead8437]；  
  - 对移植后复发患者亦为**首选方案**（指南ID:b8b378fce0f45873明确指出）[ID:b8b378fce0f45873]。

- **其他选择**（二线/桥接移植）：
  - Venetoclax + 阿扎胞苷（venetoclax-based regimens）：小部分患者可获缓解，毒性较低[ID:1e2dd0968ead8437]；
  - Azacitidine ± DLI（供体淋巴细胞输注）[ID:1e2dd0968ead8437]；
  - FLAG-IDA等强化挽救方案（适用于体能好者）[ID:1e2dd0968ead8437]；
  - **异基因造血干细胞移植（allo-HSCT）仍是唯一可能治愈手段**，建议在获得CR后尽早进行[ID:f43d69b5957fd6ee]。

#### ✅ **老年/ unfit 患者**
- 低强度方案：**阿扎胞苷 ± venetoclax**（虽非FLT3特异性，但可覆盖部分FLT3突变患者）[ID:1e2dd0968ead8437]；
- 若存在FLT3-ITD且体能允许，可考虑 **gilteritinib单药** 或 **midostaurin联合低强度化疗**（需个体化评估）[ID:c6b85eed93295094]；
- 强烈推荐**入组临床试验**（指南ID:1e2dd0968ead8437强调“whenever a suitable trial opportunity is available”）[ID:1e2dd0968ead8437]。

> 📌 **关键补充**：  
> - FLT3突变类型影响预后与治疗选择：**FLT3-ITD（内部串联重复）** 预后差，需积极干预；**FLT3-TKD（酪氨酸激酶结构域点突变）** 临床意义尚存争议，但多数指南将其纳入靶向治疗适应症。  
> - **MRD监测** 应贯穿全程，指导巩固/维持/移植决策[ID:b8b378fce0f45873]；  
> - **避免仅依赖知识图谱关系推断治疗**——图谱仅确认“AML伴FLT3突变”属于AML亚型，无直接治疗信息（见证据类型说明）。

---

### **2) 依据的图谱路径**

知识图谱证据 **未提供直接治疗路径**，仅确认疾病分类学关系，用于界定问题范围：

| 路径 | 关系 | 说明 |
|------|------|------|
| `MONDO:0018874 (AML)` → `SUBTYPE_OF` → `MONDO:0010643 (acute leukemia)` | 分类层级 | 确认AML是急性白血病的一种亚型 |
| `MONDO:0018874` → `SUBTYPE_OF` → `MONDO:0004643 (myeloid leukemia)` | 分类层级 | 支持AML属髓系肿瘤范畴 |
| `MONDO:0100424 (AML, NRAS mutation)` → `SUBTYPE_OF` → `MONDO:0018874` | 反向示例 | 说明基因突变型AML（如NRAS）归入AML大类，**暗示FLT3突变型同理应归入AML亚型** |

⚠️ **重要提示**：  
- 所有路径均为 **“SUBTYPE_OF”** 关系，**无任何治疗相关边（如 TREATS / TARGETS / USED_IN_TREATMENT）**；  
- 图谱证据类型标注为 `"knowledge_graph": true, "guideline_text": false`，**明确不可替代临床指南**；  
- 因此1e2dd0968ead8437、c6b85eed93295094、b8b378fce0f45873、f43d69b5957fd6ee、77e7707abde6b1a9等指南原文构成全部治疗依据，图谱仅用于逻辑归类验证。

---

### **3) 引用的指南原文证据（按ID标注）**

| 治疗环节 | 关键内容 | 出处（ID） | 原文摘录（精炼） |
|----------|-----------|------------|------------------|
| **一线治疗（midostaurin）** | Midostaurin联合“7+3”显著改善OS；巩固用高剂量Ara-C；维持价值不确定 | ID:c6b85eed93295094 & ID:b8b378fce0f45873 | “Midostaurin improved 4-year OS by 7.1%, from 44.3 to 51.4%... The value of adding maintenance therapy remains uncertain.” [ID:c6b85eed93295094][ID:b8b378fce0f45873] |
| **一线新药（quizartinib）** | Quizartinib联合化疗+维持的III期试验显示OS获益（初步） | ID:c6b85eed93295094 | “A placebo-controlled phase 3 trial... preliminary meeting abstract reported prolonged OS for quizartinib compared with placebo.” [ID:c6b85eed93295094] |
| **复发/难治治疗（gilteritinib）** | Gilteritinib单药为R/R FLT3⁺ AML标准治疗；移植后复发首选 | ID:1e2dd0968ead8437 & ID:b8b378fce0f45873 | “Gilteritinib improved survival in patients with early relapses... For patients relapsing after allogeneic HCT for FLT3-mutated AML, gilteritinib is the preferred” [ID:1e2dd0968ead8437][ID:b8b378fce0f45873] |
| **其他挽救方案** | Venetoclax±aza、azacitidine±DLI、FLAG-IDA可用于部分患者 | ID:1e2dd0968ead8437 | “Azacitidine, with or without donor lymphocyte infusion, and venetoclax-based salvage regimens may produce remissions in a small proportion...” [ID:1e2dd0968ead8437] |
| **移植地位** | allo-HSCT是唯一可能治愈手段；MRD指导巩固/移植决策 | ID:f43d69b5957fd6ee & ID:b8b378fce0f45873 | “异基因HSCT是唯一可能获得长期缓解的治疗措施”[ID:f43d69b5957fd6ee]；“Results from assessment of MRD should be taken into account for selecting the appropriate consolidation therapy.” [ID:b8b378fce0f45873] |
| **临床试验优先原则** | 强烈推荐入组临床试验，尤其有快速生物标志物筛查时 | ID:1e2dd0968ead8437 | “It is recommended to enroll patients with AML onto clinical trials whenever a suitable trial opportunity is available.” [ID:1e2dd0968ead8437] |
| **中国指南补充** | 2017版指南提及midostaurin、GO、CPX-351等新药可加入诱导方案 | ID:77e7707abde6b1a9 | “目前美国已经上市的米哚妥林（midostaurin）和靶向CD33的免疫毒素GO单抗...可以用于AML的诱导治疗。” [ID:77e7707abde6b1a9] |

---

### ✅ 总结声明

> **本结论严格基于权威指南原文证据（ID:1e2dd0968ead8437, c6b85eed93295094, b8b378fce0f45873, f43d69b5957fd6ee, 77e7707abde6b1a9），知识图谱仅用于疾病归类验证，不参与治疗决策生成**。  
> 实际临床中，需结合具体突变类型（ITD vs TKD）、等位基因比值（AR）、合并突变（如NPM1）、年龄、体能状态及MRD动态，由多学科团队制定个体化方案。

如需进一步细化某类人群（如老年、移植后复发、FLT3-TKD为主）的治疗路径，可提供补充信息继续深入分析。

## 4. 自检

- 9 个节点 `error`：无
- 节点 `elapsed_time`（服务端字段）：开始 0.0s、查询规划 Agent 0.59s、检索词生成 Agent 0.39s、文本处理 0.0s、变量聚合 0.0s、知识检索 0.33s、HTTP 请求 1.23s、最终分析 Agent 76.41s、回复消息 76.41s
- 回答长度 5010 字符；引用标记：`[n]` × 0、`[ID:…]` × 29
- 结尾完整：是
- 与 `Message` 节点输出一致：是
