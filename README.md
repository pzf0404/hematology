# 血液病专病知识图谱 V1

面向白血病（AML / APL / ALL / CML / CLL）与再生障碍性贫血（AA）的小而可信、可追溯、可调用的专病知识图谱。

- 范围：8 个种子疾病（含获得性再障、重型再障 SAA），1–2 hop 邻域，8 类白名单关系
- 原则：不追求节点规模；未定义/语义模糊的关系进入 staging；每条正式边保留来源、版本、原始记录与许可
- 当前状态：**阶段 1–6 全部完成并核验通过**；2026-11-18 基于 Monarch KG 2026-11-11 全链路重建，节点 128,783 / 边 284,023，28 项校验 PASS；设置 `NEO4J_PASSWORD` 后 38 项测试 PASS；数据构建、部署、RAGFlow 接入、备份/恢复与交接说明分别见第四至第十节

## 一、数据源与许可

| 数据源 | 版本 | 用途 | 许可 |
|---|---|---|---|
| [Monarch KG](https://data.monarchinitiative.org/monarch-kg/2026-11-11/monarch-kg.tar.gz) | 2026-11-11 | 疾病/表型/基因/变异/通路/生物过程 | 未声明统一许可；入图上游已逐源核对（OMIM 记录除外，见 [02_license_review.md](docs/02_license_review.md) 第四节） |
| [MONDO](https://purl.obolibrary.org/obo/mondo.json) | 2026-11-03 | 疾病本体与层级 | CC BY 4.0 |
| [DisMech](https://github.com/monarch-initiative/dismech) | `38c23e10b0285becf70a0416fdb267698dfd20fe` | 精选机制与表型 | BSD-3-Clause（仓库）/ AI 辅助整理内容 |
| [Open Targets](https://api.platform.opentargets.org/api/v4/graphql) | 26.09 | 药物、靶点、药物—疾病证据 | 平台数据 CC0，上游逐源条款见 [02_license_review.md](docs/02_license_review.md) |

逐文件 URL / 下载时间 / 版本 / SHA256 / 大小 / 处理脚本版本记录在 [manifest.json](data/raw/manifest.json)；本次构建的节点、边、疾病数与数据源版本记录在 [build_manifest.json](data/processed/build_manifest.json)。

## 二、目录结构

```
hematology-kg/
├── README.md
├── docker-compose.yml
├── .env.example
├── docs/                    # 数据源评估、许可审查、Schema、校验报告
├── config/
│   ├── disease_seeds.yaml
│   ├── relation_allowlist.yaml   # 8 类关系白名单 + 实体 ID 政策
│   └── entity_mapping.yaml       # 种子、同义词、中文名、手工映射
├── data/
│   ├── raw/                 # 原始下载（离线来源，不入图）
│   ├── staging/             # 未入图的边、异常报告、候选表型
│   └── processed/
│       ├── nodes.csv        # 12 列，UTF-8 无 BOM
│       ├── edges.csv        # 14 列，UTF-8 无 BOM
│       ├── build_manifest.json
│       └── validation_report.json
├── etl/
│   ├── download.py
│   ├── normalize.py
│   ├── extract_subgraph.py
│   ├── validate.py
│   ├── load_neo4j.py        # 阶段 3：建约束 → 导入 → 核验
│   └── fetch_guidelines.py  # 阶段 5：指南原文入库
├── cypher/                  # 阶段 3：约束、验收查询
├── scripts/                 # 备份/恢复与验收存档生成（连接参数不入库）
│   ├── backup_neo4j.ps1     # 阶段 6：停容器一致性备份 + SHA256 + 计数核验
│   └── restore_neo4j.ps1    # 阶段 6：校验归档后恢复 + 计数/约束核验
├── backups/                 # 本地备份产物（.gitignore 排除，不入库）
├── neo4j/                   # Neo4j 数据卷与日志（compose 绑定挂载，重启后持久化）
├── api/                     # 阶段 4：FastAPI（/health、search、neighbors、kg/context）
└── tests/
    ├── test_etl.py
    ├── test_api.py
    ├── acceptance_cases.json          # 25 条数据层验收问题
    └── acceptance_cases_ragflow.json  # 25 条 RAGFlow 验收问题（R01–R25）
```

## 三、环境要求

- Python 3.10+（本机验证 3.14）
- 依赖：`python-docx`（仅调研阶段）、`PyYAML`、`pytest`、`neo4j`（阶段 3）
- Docker Desktop + Docker Compose（阶段 3 起）
- PowerShell 5 不支持 `&&`，多命令请分行执行

## 四、数据构建（阶段 2）

在项目根目录依次执行：

```powershell
python -m etl.download          # 已有归档默认跳过；--force 强制重下
python -m etl.normalize         # 四源标准化 → data/staging
python -m etl.extract_subgraph  # 裁剪 1–2 hop → data/processed + build_manifest.json
python -m etl.validate          # 完整性校验 + 验收抽查 → validation_report.json / docs/03_validation_report.md
```

构建是幂等的：同一份 raw 数据重复执行会得到相同节点/边（CSV 行内容一致）。如清空 `data/staging`、`data/processed`，按上述顺序即可全量重建。

运行日志与异常统计：四个脚本在控制台输出逐阶段进度与计数；异常、暂存与丢弃统计分别写入 `data/staging/normalize_report.json`、`data/processed/extract_report.json`、`data/processed/validation_report.json`。

校验通过标准：`python -m etl.validate` 退出码 0（28 项检查全部 PASS，6 项自动抽查命中；25 条固定验收问题的数据层证据见 `tests/acceptance_cases.json`）。

### 自动化测试

```powershell
pytest tests/test_etl.py -q
```

覆盖：列契约、冻结计数、ID 唯一性、引用完整性、关系方向、边溯源、孤立节点、中文覆盖、Gene ID 格式、异常暂存、关键验收三元组。

### 验收问题

[tests/acceptance_cases.json](tests/acceptance_cases.json) 按任务指引第十八章准备 25 条固定问题，逐条写明期望实体、关系、来源与数据层证据；其中 Q15、Q25 需阶段 4–5 的 API/RAGFlow 才能完成端到端验收。

## 五、Docker / Neo4j（阶段 3）

```powershell
Copy-Item .env.example .env      # 设置强密码（≥12 位、不含 $）；不要带 <>（Compose 会插值）
docker network inspect ai-network
docker network create ai-network # 不存在时创建
docker compose up -d hematology-neo4j
docker ps --filter name=hematology-neo4j
docker exec hematology-neo4j cypher-shell -u neo4j -p <密码> "RETURN 1;"
python -m pip install "neo4j>=5,<7"
$env:NEO4J_PASSWORD="<与 .env 相同的密码>"
python -m etl.load_neo4j          # 建约束 → 导入 → 核验 → 写 neo4j_import_report.json
python -m etl.load_neo4j          # 再执行一次，节点/边计数必须不变（幂等）
```

端口仅绑定 `127.0.0.1:7474/7687`。导入与验收查询见 `cypher/`、`etl/load_neo4j.py`，Schema、执行步骤与差异说明见 [03_schema.md](docs/03_schema.md)。

阶段 5（RAGFlow）见第七节。

## 六、FastAPI（阶段 4）

| 接口 | 方法 | 说明 |
|---|---|---|
| `/health` | GET | 检查 API 与 Neo4j 连通性 |
| `/v1/entity/search` | GET | 中文/英文/同义词实体搜索，`limit ≤ 50` |
| `/v1/entity/{id}/neighbors` | GET | 按关系、`depth ≤ 2`、`limit ≤ 50` 查询邻居 |
| `/v1/kg/context` | POST | 返回 `matched_entities/paths/evidence/context` |

```powershell
docker compose up -d --build
curl.exe http://127.0.0.1:18080/health
curl.exe "http://127.0.0.1:18080/v1/entity/search?q=AML&limit=5"
curl.exe "http://127.0.0.1:18080/v1/entity/HGNC:3765/neighbors?depth=1&limit=5"
curl.exe -X POST http://127.0.0.1:18080/v1/kg/context `
  -H "Content-Type: application/json" `
  -d '{"disease_route":"leukemia","query":"FLT3 与 AML 有什么关系？","max_hops":2,"limit":20}'
$env:NEO4J_PASSWORD = ((Select-String -Path .env -Pattern '^NEO4J_PASSWORD=').Line -replace '^NEO4J_PASSWORD=','').Trim()
python -m pytest -q
```

- Swagger：http://127.0.0.1:18080/docs
- 只使用固定 Cypher 模板，禁止用户问题直接生成 Cypher。
- 硬限制：`max_hops ≤ 2`、`limit ≤ 50`、关系仅限 8 类白名单。
- 查询失败返回 JSON 400/404/503，不返回堆栈。
- `evidence_types` 明确区分 `knowledge_graph` 与 `guideline_text`；V1 API 只返回图谱证据。
- 已实测：容器 healthy；`/health`、entity search、neighbors、kg/context 均 200；`max_hops=3`、`limit=51` 返回 422；未知 route 返回 400；设置 `NEO4J_PASSWORD` 后 `pytest -q` 38 passed。

> 若构建时 `python:3.12-slim` 拉取失败，可先从可用镜像源拉取并 tag 为 `python:3.12-slim`，再执行 `docker compose up -d --build`；这是网络镜像源问题，不是项目代码问题。

## 七、RAGFlow 接入（阶段 5）

- 画布：`hematology_kg_rag_v1`（agent_id `e75a102daebc43d3b327e0c64b3b0de4`），本机访问 `http://127.0.0.1:9381/agent/e75a102daebc43d3b327e0c64b3b0de4?category=agent_canvas`
- 运行方式：全部依赖由本机 Docker Compose 提供（RAGFlow Web 9381 / API 9380、MySQL、Elasticsearch、MinIO、Kvrocks、NATS），知识库与画布数据均落地在本机卷；基础服务端口（MySQL/ES/MinIO/Kvrocks/NATS）均绑定 `127.0.0.1`，仅本机可达。
- 编排（9 节点）：Begin → 查询规划 Agent → 检索词生成 Agent →（Retrieval ∥ StringTransform → VariableAggregator(`body`) → Invoke）→ 最终分析 Agent → Message
- 零源码改动注入 body：`Invoke` 无 body 字段且不解析模板，由 `StringTransform`（merge，输出整段 JSON 字符串）+ `VariableAggregator`（组名固定 `body`）把 `body` 并入 `inputs`，详见 [04_ragflow_integration.md](docs/04_ragflow_integration.md) 第 2 节
- KG 调用：`POST http://hematology-kg-api:8000/v1/kg/context`，`max_hops=2`、`limit=30`（API 侧硬上限 `max_hops ≤ 2`、`limit ≤ 50`）
- 文档检索：知识库 `hematology_guidelines_v1`（10 篇、384 chunks），混合检索 `keywords_similarity_weight=0.3`（vector=0.7）、`similarity_threshold=0`、`top_n=12`
- 验收：5 条分病种案例 5/5 通过；扩充 25 条（R01–R25）**25/25 PASS**，2026-11-18 16:58–17:15 在 Monarch 2026-11-11 新基线上全量复跑（787 字领域提示、`cite=false`、`top_n=12`），回答合计 78,735 字，22 条实质作答 + 3 条证据优先弃答，9 节点 `error` 全空，`[ID:]` 400 次（86 个不同 chunk ID + 2 个 edge_id）全部可回溯。报告 [05_acceptance_test.md](docs/05_acceptance_test.md)，明细 [s5/acceptance.md](docs/s5/acceptance.md)，逐条存档 `docs/s5/runs/answers_r25/`，DSL 快照 [s5/dsl_snapshot.json](docs/s5/dsl_snapshot.json)，截图 `docs/s5/screenshots/`
- 基线说明：本批验收与数据层同为 Monarch 2026-11-11（128,783 节点 / 284,023 边）；2026-11-17 批次（Monarch 2026-10-07，80,063 字 / 392 个 `[ID:]` / 24 实质 + 1 弃答）仅在 05 报告第六节保留作对照

## 八、已知限制

- **治疗方案 / HSCT 不入图**：关系白名单未定义治疗方案关系，DisMech 的 20 条治疗条目（含造血干细胞移植）仅保存在 `data/staging/staged_dismech_treatments.csv`。相关提问只能回答“无图内关系证据”，需指南/文献文本补充。
- **APL 的上级疾病**：Monarch 给出的 `SUBTYPE_OF` 指向 `MONDO:0017893`（遗传性 AML），不是 `MONDO:0018874`；不臆造 APL→AML 边。
- **表型覆盖稀疏**：种子疾病直接表型合计 80 条，AML 仅 2 个，AA 2 个；HPO 对白血病/再障注释有限。
- **疾病中文名**：仅种子疾病与 `entity_mapping.yaml` 覆盖 61 个表型；非种子疾病无官方中文名时字段留空。
- **未建节点类型**：Protein、Treatment、CellType 不建节点；`RELATED_TO` 关闭；Genotype/Case/ChemicalEntity 等仅进 staging 或丢弃。
- **Gene ID**：13,800 个 HGNC + 86 个无 HGNC 唯一匹配的 ncRNA 使用标准 Ensembl ID（`ENSG000...`）。
- **异常边**：320 条白名单外 Variant→Disease 边暂存并注明原因，另有 86 条 Genotype `model_of` 行因非 V1 节点类型丢弃，详见 [03_validation_report.md](docs/03_validation_report.md) 第五节。
- **RAGFlow 编排省略「患者数据查询 / 患者事实整理」节点**：V1 无患者数据源，该节点未实现；画布直接从「查询规划 Agent」进入「检索词生成 Agent」，与任务指引第十四章流程图存在这一处差异。
- **检索仍有跨病种噪声**：10 篇指南措辞高度相似；`top_n=12` + 混合检索 0.3 时同病种 chunk 为 208/300（2026-11-18 新基线；11-17 为 214/300、11-16 为 206/300；`top_n=8` 时 150/200，纯向量时 123/200）；继续升权重会挤掉英文 ELN 指南。
- **图谱证据以 SUBTYPE_OF 为主**：种子疾病邻域内 `paths` 多为疾病层级边，治疗/药物结论主要依赖指南文本。
- **UI 自动保存覆盖 API 改动**：画布打开时前端会用内存旧状态回写 DSL，改配置须在 UI 内保存并刷新复验；UI 保存会在 Retrieval 查询变量末尾追加 ` /`（实测对检索无影响）。
- **备份为整库文件级快照**：备份/恢复需短暂停止 Neo4j；备份不包含 `.env`、`data/raw` 与 RAGFlow 侧 MySQL/ES/MinIO 卷，RAGFlow 数据需按其部署方式单独备份。
- **OMIM 上游记录**：27 条边可回溯到 `primary_knowledge_source=OMIM`（17 条基因—疾病，均有 Open Targets 共支撑；10 条疾病—表型经 HPOA 文件进入）。OMIM 条款禁止未经许可再分发；V1 仅限内部科研使用，对外分发前需剔除或取得授权，详见 [02_license_review.md](docs/02_license_review.md) 第四节。

### 8.1 故障排查速查

| 现象 | 优先检查 |
|---|---|
| RAGFlow 调不到 API | Invoke URL 必须用服务名 `http://hematology-kg-api:8000/v1/kg/context`；两个容器都在 `ai-network`；在 RAGFlow 容器内 `curl http://hematology-kg-api:8000/health` |
| API 启动但 Neo4j 连接失败 | `docker logs hematology-kg-api`；确认 `NEO4J_URI=bolt://hematology-neo4j:7687`；`.env` 密码与 `NEO4J_AUTH` 一致 |
| 中文搜索命不中 | 用 `name_zh`/`synonyms` 检索：`GET /v1/entity/search?q=再生障碍性贫血`；确认节点 `name_zh` 非空 |
| 查询返回大量无关疾病 | 确认 `max_hops=2`；Disease 仅种子 + MONDO 直接父/子（见 `docs/03_schema.md` 第 6 节）；`max_hops=3` 会返回 422 |
| 同一关系重复很多条 | 多源合并边 `source` 用 `|` 连接，属预期；按 `edge_id` 去重，不要按三元组自行拆分 |
| 图谱回答确定但证据弱 | 最终 Agent 已要求证据优先；图谱路径多为 `SUBTYPE_OF`，治疗结论须以 Retrieval 指南原文为准 |
| 镜像 / volume 很大 | `data/raw` 不挂载；仅 `data/processed` 只读挂载；`docker system df` 清理未用镜像；`backups/` 不入库 |

## 九、备份与恢复（阶段 6）

Neo4j 数据通过 bind mount 落在 `neo4j/data`（容器内 `/data`）。备份脚本在停止容器后做文件级一致性快照，产物为 `backups/neo4j-data-<时间戳>.tar.gz` 及同名 `.sha256`、`.meta.json`（记录镜像 digest、SHA256、备份前后节点/边计数）。`backups/` 已被 `.gitignore` 排除，请单独保管。

```powershell
# 备份：停容器 -> tar.gz -> SHA256 -> 重启 -> 核对节点/边计数
powershell -ExecutionPolicy Bypass -File scripts\backup_neo4j.ps1

# 恢复：校验 SHA256 -> 停容器 -> 现有 data 改名 data.pre-restore-<时间戳> -> 解包 -> 启动 -> 计数/约束核验
powershell -ExecutionPolicy Bypass -File scripts\restore_neo4j.ps1 `
  -Archive backups\neo4j-data-<时间戳>.tar.gz

# 确认恢复结果后再删除旧数据目录（脚本加 -RemovePrevious 可自动删除）
Remove-Item -Recurse -Force neo4j\data.pre-restore-<时间戳>
```

- 备份/恢复期间 Neo4j 停机，`/health` 会短暂失败；恢复后 API 自动重连（本机实测无需重建容器）。
- 恢复失败时原数据仍在 `neo4j/data.pre-restore-<时间戳>`：停止容器后把该目录改回 `data` 即可回滚。
- 只重建不回滚：清空 `neo4j/data`，按第五节重新 `docker compose up -d hematology-neo4j` 并执行 `python -m etl.load_neo4j`（ETL 与导入均幂等）。
- 演练记录（2026-11-16，旧基线）：归档 90.8 MB，SHA256 `945824DB…4E093027`；恢复前后 nodes/edges 均为 **125,759 / 280,999**，约束 `entity_id_unique` 存在；`/health` 返回 `{"status":"ok","neo4j":"connected","version":"5.26.32"}`，`/v1/entity/search?q=AML` 命中 `MONDO:0018874`。该归档已按交付清理删除，需要时按本节命令重新生成。

## 十、新机器部署与交接核对

### 10.1 从零部署（按顺序执行）

```powershell
git clone https://github.com/pzf0404/hematology.git hematology-kg
cd hematology-kg
Copy-Item .env.example .env           # 设置强密码（≥12 位、不含 $）；不要带 <>
docker network inspect ai-network     # 不存在则 docker network create ai-network
python -m pip install PyYAML "neo4j>=5,<7" pytest httpx -r api\requirements.txt

# 1) 数据构建（阶段 2）：raw -> staging -> processed
python -m etl.download                # 缺失时下载 Monarch 2026-11-11，并登记 MONDO/DisMech/Open Targets；已有归档默认跳过
python -m etl.normalize
python -m etl.extract_subgraph
python -m etl.validate                # 退出码 0，28 项 PASS

# 2) Neo4j（阶段 3）
docker compose up -d hematology-neo4j
$env:NEO4J_PASSWORD = ((Select-String -Path .env -Pattern '^NEO4J_PASSWORD=').Line -replace '^NEO4J_PASSWORD=','').Trim()
python -m etl.load_neo4j              # 建约束 -> 导入 -> 核验

# 3) API（阶段 4）
docker compose up -d --build
curl.exe http://127.0.0.1:18080/health
$env:NEO4J_PASSWORD = ((Select-String -Path .env -Pattern '^NEO4J_PASSWORD=').Line -replace '^NEO4J_PASSWORD=','').Trim()
python -m pytest -q                   # 38 passed（已设置 NEO4J_PASSWORD）
```

- `data/raw` 体积大且不入库（见 `.gitignore`），新机器必须执行 `python -m etl.download`，或从交付介质复制 raw 目录与 `manifest.json` 后跳过下载。
- 若 `python:3.12-slim` / `neo4j:5-community` 拉取失败，先配置可用镜像源；这是网络问题，不改代码。
- RAGFlow（阶段 5）需在本机 RAGFlow 中按 [04_ragflow_integration.md](docs/04_ragflow_integration.md) 重建画布；当前 DSL 快照见 [s5/dsl_snapshot.json](docs/s5/dsl_snapshot.json)，端到端验收方法见 [05_acceptance_test.md](docs/05_acceptance_test.md)。

### 10.2 交接核对（约 10 分钟）

| 核对项 | 命令 / 位置 | 期望 |
|---|---|---|
| 数据校验 | `python -m etl.validate` | 退出码 0，28 项 PASS |
| 图谱规模 | `docker exec hematology-neo4j cypher-shell ... "MATCH (n) RETURN count(n);"` | nodes 128,783 / edges 284,023 |
| 约束 | `SHOW CONSTRAINTS` | `entity_id_unique`（`Entity.id`） |
| API 健康 | `curl.exe http://127.0.0.1:18080/health` | `status=ok`、Neo4j connected |
| 中英文/缩写命中 | `/v1/entity/search?q=AML`、`q=急性髓系白血病` | 均命中 `MONDO:0018874` |
| 自动测试 | `python -m pytest -q`（需设置 `NEO4J_PASSWORD`） | 38 passed |
| RAGFlow 端到端 | 第七节、`docs/05_acceptance_test.md` | R01–R25 25/25 PASS；2026-11-18 在 Monarch 2026-11-11 新基线上全量复跑通过 |
| 备份/恢复 | 第九节命令 + `backups/*.meta.json` | 恢复后计数不变、约束存在 |

## 十一、版本

- 图谱版本：`hematology-kg-v1-20261118`（与 `data/processed/build_manifest.json`、`neo4j_import_report.json` 一致；2026-11-18 基于 Monarch 2026-11-11 全链路重建，节点 128,783 / 边 284,023）
- Neo4j：`5.26.32`（镜像 `neo4j:5-community`，digest `sha256:249a1ec6…fb177`）
- RAGFlow：`infiniflow/ragflow:v1.0.0-rc3`（本机 9381/9380）
- 下载脚本：`1.1.0`
- API：`1.0.0`
- 关系白名单：`1.0`（2026-11-09 对原始数据实测）
- 备份/恢复脚本：2026-11-16 完成备份 + 恢复演练（见第九节）
- `build_manifest.json` 的 `git_commit`：`965d09b`（`965d09b571c50e95567bbac3180027f33e0c22de`，即 2026-11-19 重建后的数据快照提交；该字段记录**数据构建时**的 HEAD，回填该字段的提交会位于其后，因此不会指向自身，后续文档提交也可能使当前 HEAD 前进）
