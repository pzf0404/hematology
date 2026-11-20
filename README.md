# 血液病专病知识图谱 V1

面向白血病（AML / APL / ALL / CML / CLL）与再生障碍性贫血（AA）的小而可信、可追溯、可调用的专病知识图谱。

- 范围：8 个种子疾病（含获得性再障、重型再障 SAA），1–2 hop 邻域，8 类白名单关系
- 原则：不追求节点规模；未定义或语义模糊的关系进入 staging；每条正式边保留来源、版本、原始记录与许可
- 当前状态：阶段 1–6 全部完成并核验通过
- 数据基线：`hematology-kg-v1-20261118`（Monarch KG 2026-11-11），128,783 节点 / 284,023 边 / 115 个疾病
- 数据校验：28 项 PASS / 0 FAIL；自动化测试 38 passed
- RAGFlow 验收：R01–R25 25/25 PASS

## 一、数据源与许可

| 数据源 | 版本 | 用途 | 许可 |
|---|---|---|---|
| [Monarch KG](https://data.monarchinitiative.org/monarch-kg/2026-11-11/monarch-kg.tar.gz) | 2026-11-11 | 疾病、表型、基因、变异、通路、生物过程 | 未声明统一许可；入图上游已逐源核对（OMIM 记录除外） |
| [MONDO](https://purl.obolibrary.org/obo/mondo.json) | 2026-11-03 | 疾病本体与层级 | CC BY 4.0 |
| [DisMech](https://github.com/monarch-initiative/dismech) | `38c23e10b0285becf70a0416fdb267698dfd20fe` | 精选机制与表型 | BSD-3-Clause（仓库）/ AI 辅助整理内容 |
| [Open Targets](https://api.platform.opentargets.org/api/v4/graphql) | 26.09 | 药物、靶点、药物—疾病证据 | 平台数据 CC0；上游逐源条款见许可审查 |

- 数据源版本与下载时间、逐文件 URL / SHA256 / 大小 / 处理脚本版本：`data/raw/manifest.json`
- 每个数据源的许可结论、入图数据集核对与残余风险：`docs/02_license_review.md`
- 数据源评估表（可下载性、更新频率、结构、覆盖度、推荐用途）：`docs/01_source_evaluation.xlsx`
- 本次构建的节点、边、疾病数与数据源版本：`data/processed/build_manifest.json`

> 对外分发前必须剔除 OMIM 贡献的 27 条边或取得授权；V1 仅限内部科研使用，不用于直接临床决策。

## 二、目录结构

```text
hematology-kg/
├── README.md
├── docker-compose.yml
├── .env.example
├── api/                     # FastAPI：/health、search、neighbors、kg/context
├── config/
│   ├── disease_seeds.yaml
│   ├── relation_allowlist.yaml   # 8 类关系白名单 + 实体 ID 政策
│   └── entity_mapping.yaml       # 种子、同义词、中文名、手工映射
├── cypher/
│   ├── schema.cypher             # 约束与索引
│   └── acceptance_queries.cypher # 验收查询
├── data/
│   ├── raw/                      # 原始下载（不入库，只提交 manifest.json）
│   ├── staging/                  # 未入图边、异常报告、候选表型
│   └── processed/                # nodes.csv、edges.csv、构建/校验/导入报告
├── docs/
│   ├── 01_source_evaluation.xlsx
│   ├── 02_license_review.md
│   ├── 03_schema.md
│   ├── 03_validation_report.md   # 由 etl.validate 生成
│   ├── 04_ragflow_integration.md
│   ├── 05_acceptance_test.md
│   └── s5/                       # RAGFlow 规格、任务、验收与原始存档
├── etl/
│   ├── download.py
│   ├── normalize.py
│   ├── extract_subgraph.py
│   ├── validate.py
│   ├── load_neo4j.py
│   └── fetch_guidelines.py
├── scripts/
│   ├── backup_neo4j.ps1
│   └── restore_neo4j.ps1
└── tests/
    ├── test_etl.py
    ├── test_api.py
    ├── acceptance_cases.json
    └── acceptance_cases_ragflow.json
```

## 三、环境要求

- Windows + PowerShell 5（或 PowerShell 7）
- Python 3.10+（本机验证 3.14）
- Docker Desktop + Docker Compose
- 端口：`7474`、`7687`、`18080` 空闲（RAGFlow 另需其自身端口）
- 磁盘：原始数据约 480 MB、Neo4j 数据约 1 GB、镜像约 1.2 GB
- 网络：可访问 Docker Hub、monarchinitiative.org、Open Targets API 与 RAGFlow 模型服务；若采用 GitHub 方式获取代码，还需能访问 github.com

## 四、数据构建（阶段 2）

在项目根目录依次执行：

```powershell
python -m etl.download          # 已有关档默认跳过；--force 强制重下
python -m etl.normalize         # 四源标准化 -> data/staging
python -m etl.extract_subgraph  # 裁剪 1–2 hop -> data/processed + build_manifest.json
python -m etl.validate          # 完整性校验 + 验收抽查 -> validation_report.json / docs/03_validation_report.md
```

预期结果：

| 步骤 | 结果 |
|---|---|
| normalize | 185,067 节点 / 623,805 边（staging） |
| extract_subgraph | 128,783 节点 / 284,023 边（processed） |
| validate | 28 项 PASS / 0 FAIL，6 项抽查 PASS，退出码 0 |

构建幂等：同一份 raw 数据重复执行得到相同 CSV；清空 `data/staging`、`data/processed` 后按上述顺序可全量重建。

- 异常与暂存统计：`data/staging/normalize_report.json`、`data/processed/extract_report.json`、`data/processed/validation_report.json`
- 数据校验报告：`docs/03_validation_report.md`
- 30 条边抽样：`data/processed/edge_traceability_sample.csv`

### 4.1 自动化测试

```powershell
pytest tests/test_etl.py -q
```

覆盖列契约、冻结计数、ID 唯一性、引用完整性、关系方向、边溯源、孤立节点、中文覆盖、Gene ID 格式、异常暂存与关键验收三元组。

### 4.2 验收问题

`tests/acceptance_cases.json` 按任务指引第十八章准备 25 条固定问题，逐条写明期望实体、关系、来源与数据层证据；Q15、Q25 需阶段 4–5 的 API/RAGFlow 完成端到端验收。

## 五、Docker / Neo4j（阶段 3）

```powershell
Copy-Item .env.example .env      # 首次启动前修改；启动后再改 .env 不会更新 Neo4j 密码
notepad .env
docker network create ai-network # 已存在会提示 already exists，可忽略
docker compose up -d hematology-neo4j
docker ps --filter name=hematology-neo4j
$env:NEO4J_PASSWORD = ((Select-String -Path .env -Pattern '^NEO4J_PASSWORD=').Line -replace '^NEO4J_PASSWORD=','').Trim()
# 首次启动初始化需 1–2 分钟；下面命令返回 1 后再执行导入
docker exec hematology-neo4j cypher-shell -u neo4j -p $env:NEO4J_PASSWORD "RETURN 1;"
python -m pip install "neo4j>=5,<7"
python -m etl.load_neo4j          # 建约束 -> 导入 -> 核验 -> 写 neo4j_import_report.json
python -m etl.load_neo4j          # 再执行一次，节点/边计数必须不变（幂等）
```

- 端口仅绑定 `127.0.0.1:7474/7687`，不对公网暴露。
- 导入结果：128,783 节点 / 284,023 边，缺失端点 0、孤立节点 0、计数不一致项 0。
- Schema、字段契约、查询实测与差异说明：`docs/03_schema.md`
- 约束与索引：`cypher/schema.cypher`；验收查询：`cypher/acceptance_queries.cypher`

## 六、FastAPI（阶段 4）

| 接口 | 方法 | 说明 |
|---|---|---|
| `/health` | GET | 检查 API 与 Neo4j 连通性 |
| `/v1/entity/search` | GET | 中文/英文/同义词实体搜索，`limit ≤ 50` |
| `/v1/entity/{id}/neighbors` | GET | 按关系、`depth ≤ 2`、`limit ≤ 50` 查询邻居 |
| `/v1/kg/context` | POST | 返回 `matched_entities / paths / evidence / context` |

```powershell
docker compose up -d --build
curl.exe http://127.0.0.1:18080/health
curl.exe "http://127.0.0.1:18080/v1/entity/search?q=AML&limit=5"
curl.exe "http://127.0.0.1:18080/v1/entity/HGNC:3765/neighbors?depth=1&limit=5"

# PowerShell 5 直传含中文的 -d '{"..."}' 会丢引号，改用 UTF-8 文件传参
$body = '{"disease_route":"leukemia","query":"FLT3 与 AML 有什么关系？","max_hops":2,"limit":20}'
[IO.File]::WriteAllText("$PWD\kg_context.json", $body, (New-Object System.Text.UTF8Encoding($false)))
curl.exe -s -X POST http://127.0.0.1:18080/v1/kg/context `
  -H "Content-Type: application/json" `
  --data-binary "@kg_context.json"

$env:NEO4J_PASSWORD = ((Select-String -Path .env -Pattern '^NEO4J_PASSWORD=').Line -replace '^NEO4J_PASSWORD=','').Trim()
python -m pytest -q
```

- Swagger：http://127.0.0.1:18080/docs
- 只使用固定 Cypher 模板，禁止由用户问题直接生成 Cypher。
- 硬限制：`max_hops ≤ 2`、`limit ≤ 50`、关系仅限 8 类白名单。
- 查询失败返回 JSON 400/404/503，不返回堆栈。
- `evidence_types` 区分 `knowledge_graph` 与 `guideline_text`；V1 API 只返回图谱证据。
- 实测：容器 healthy；`/health`、search、neighbors、kg/context 均 200；`max_hops=3`、`limit=51` 返回 422；未知 route 返回 400；`pytest -q` 38 passed。

> 若 `python:3.12-slim` 或 `neo4j:5-community` 拉取失败，先配置可用镜像源；这是网络问题，不是项目代码问题。

## 七、RAGFlow 接入（阶段 5）

> **本节中的 agent_id、数据集 ID、模型 UUID、9380/9381 端口与登录账号均为作者本机 RAGFlow 实例，换机后不存在，不能直接复用。** 老师需按 `docs/04_ragflow_integration.md` 第五节从零重建，导入 DSL 后 RAGFlow 会自动生成新的 agent_id，知识库与模型需在画布中重新选择。

- 画布：`hematology_kg_rag_v1`，9 节点
- 编排：Begin → 查询规划 Agent → 检索词生成 Agent →（Retrieval ∥ StringTransform → VariableAggregator(`body`) → Invoke）→ 最终分析 Agent → Message
- 零源码改动注入 body：`Invoke` 无 body 字段且不解析模板，由 `StringTransform`（merge，输出整段 JSON 字符串）+ `VariableAggregator`（组名固定 `body`）把 `body` 并入 `inputs`
- KG 调用：`POST http://hematology-kg-api:8000/v1/kg/context`，`max_hops=2`、`limit=30`
- 文档检索：知识库 `hematology_guidelines_v1`（10 篇、384 chunks），`keywords_similarity_weight=0.3`（vector=0.7）、`similarity_threshold=0`、`top_n=12`
- 领域提示词：787 字，`cite=false`，`temperature=0.1`
- 验收：5 条分病种案例 5/5；R01–R25 25/25 PASS；回答合计 78,735 字；22 条实质作答 + 3 条证据优先弃答；9 节点 `error` 全空；`[ID:]` 400 次（86 个不同 chunk ID + 2 个 edge_id）全部可回溯

相关资料：

- 接入细节、重建步骤与已知限制：`docs/04_ragflow_integration.md`
- 验收报告：`docs/05_acceptance_test.md`
- 逐条结果：`docs/s5/acceptance.md`
- 原始存档：`docs/s5/runs/answers_r25/`
- DSL 快照：`docs/s5/dsl_snapshot.json`
- 截图：`docs/s5/screenshots/`

## 八、备份与恢复（阶段 6）

Neo4j 数据通过 bind mount 落在 `neo4j/data`（容器内 `/data`）。备份脚本停止容器后做文件级一致性快照，产物为 `backups/neo4j-data-<时间戳>.tar.gz` 及同名 `.sha256`、`.meta.json`（记录镜像 digest、SHA256、备份前后节点/边计数）。`backups/` 已被 `.gitignore` 排除，请单独保管。

```powershell
# 备份：停容器 -> tar.gz -> SHA256 -> 重启 -> 核对节点/边计数
powershell -ExecutionPolicy Bypass -File scripts\backup_neo4j.ps1

# 恢复：校验 SHA256 -> 停容器 -> 现有 data 改名 data.pre-restore-<时间戳> -> 解包 -> 启动 -> 计数/约束核验
powershell -ExecutionPolicy Bypass -File scripts\restore_neo4j.ps1 `
  -Archive backups\neo4j-data-YYYYMMDD-HHMMSS.tar.gz

# 确认恢复结果后再删除旧数据目录（脚本加 -RemovePrevious 可自动删除）
Remove-Item -Recurse -Force neo4j\data.pre-restore-YYYYMMDD-HHMMSS
```

- 备份/恢复期间 Neo4j 停机，`/health` 会短暂失败；恢复后 API 自动重连。
- 恢复失败时原数据仍在 `neo4j/data.pre-restore-<时间戳>`：停止容器后把该目录改回 `data` 即可回滚。
- 只重建不回滚：清空 `neo4j/data`，按第五节重新启动并执行 `python -m etl.load_neo4j`。
- 备份不包含 `.env`、`data/raw` 与 RAGFlow 侧 MySQL/ES/MinIO 卷；RAGFlow 数据需单独备份。

## 九、新机器部署与交接核对

### 9.1 从零部署（按顺序执行）

```powershell
# 获取代码（二选一，最终都要停在项目根目录 hematology-kg）
# 方式一：从 GitHub 克隆
git clone https://github.com/pzf0404/hematology.git hematology-kg
cd hematology-kg

# 方式二：使用交付压缩包（解压后直接进入目录即可，无需再 clone；路径按实际解压位置替换）
# Expand-Archive .\hematology-kg.zip -DestinationPath .
# cd .\hematology-kg

Copy-Item .env.example .env           # 首次启动前修改；密码仅用字母、数字、_、-，避免 $ 和 #（Compose 会当作变量/注释）
notepad .env
docker network create ai-network      # 已存在会提示 already exists，可忽略
python -m pip install PyYAML "neo4j>=5,<7" pytest httpx -r api\requirements.txt

# 1) 数据构建（阶段 2）
python -m etl.download                # 缺失时下载；已有归档默认跳过
python -m etl.normalize
python -m etl.extract_subgraph
python -m etl.validate                # 退出码 0，28 项 PASS

# 2) Neo4j（阶段 3）
docker compose up -d hematology-neo4j
$env:NEO4J_PASSWORD = ((Select-String -Path .env -Pattern '^NEO4J_PASSWORD=').Line -replace '^NEO4J_PASSWORD=','').Trim()
# 首次启动初始化需 1–2 分钟；下面命令返回 1 后再导入
docker exec hematology-neo4j cypher-shell -u neo4j -p $env:NEO4J_PASSWORD "RETURN 1;"
python -m etl.load_neo4j

# 3) API（阶段 4）
docker compose up -d --build
# 首次构建需数十秒；等待 /health 返回 200（最多 90 秒）
for ($i = 0; $i -lt 30; $i++) {
  try { if ((Invoke-WebRequest -UseBasicParsing http://127.0.0.1:18080/health).StatusCode -eq 200) { break } } catch {}
  Start-Sleep -Seconds 3
}
curl.exe http://127.0.0.1:18080/health
curl.exe "http://127.0.0.1:18080/v1/entity/search?q=AML&limit=5"
$body = '{"disease_route":"leukemia","query":"FLT3 与 AML 有什么关系？","max_hops":2,"limit":20}'
[IO.File]::WriteAllText("$PWD\kg_context.json", $body, (New-Object System.Text.UTF8Encoding($false)))
curl.exe -s -X POST http://127.0.0.1:18080/v1/kg/context -H "Content-Type: application/json" --data-binary "@kg_context.json"
Remove-Item kg_context.json
# 若在新终端执行，先重新设置 NEO4J_PASSWORD 再跑测试
$env:NEO4J_PASSWORD = ((Select-String -Path .env -Pattern '^NEO4J_PASSWORD=').Line -replace '^NEO4J_PASSWORD=','').Trim()
python -m pytest -q                   # 38 passed

# 4) RAGFlow（阶段 5）：需要本机已有 RAGFlow
python -m etl.fetch_guidelines        # 下载 10 个指南文件到 data/raw/guidelines
# 3 个 .doc 需先用 Word 另存为 .docx；无 Word 时可用 LibreOffice：
# Get-ChildItem data\raw\guidelines\*.doc | ForEach-Object { soffice --headless --convert-to docx --outdir data\raw\guidelines $_.FullName }
# 文件名对照 data/raw/guidelines/sources.json 的 upload_filename
# 在 RAGFlow 中创建知识库并上传 6 个 PDF + 4 个 DOCX -> 解析
# 导入 docs/s5/dsl_snapshot.json -> 在 Retrieval 重新选择知识库、在 3 个 Agent 节点重新选择模型
# RAGFlow 容器需接入 ai-network，并能访问 API（按镜像筛出 ragflow-server，避免误取 mysql/es/redis）
$ragflowContainer = (docker ps --format "{{.Names}}`t{{.Image}}" |
  Select-String "infiniflow/ragflow" |
  ForEach-Object { ($_.Line -split "`t")[0] } |
  Select-Object -First 1)
docker network connect ai-network $ragflowContainer   # 已连接会报错，可忽略
docker exec $ragflowContainer curl -s http://hematology-kg-api:8000/health
# 若 Invoke 报主机不可达，在 RAGFlow 的 .env 中设置 ALLOW_ANY_HOST=1 并重启 RAGFlow
# 详细步骤见 docs/04_ragflow_integration.md 第五节
```

- `data/raw` 体积大且不入库（见 `.gitignore`）。新机器可执行 `python -m etl.download`，或从交付介质复制 raw 目录与 `manifest.json` 后跳过下载。
- Monarch 归档 368 MB，直连较慢；复制方式必须校验 SHA256 与 `data/raw/manifest.json` 一致。
- 指南原文同样不在仓库中，RAGFlow 重建前必须先运行 `python -m etl.fetch_guidelines`。共 10 个文件：3 个 `.doc`、1 个 `.docx`、6 个 `.pdf`；3 个 `.doc` 需另存为 `.docx` 后上传，清单见 `data/raw/guidelines/sources.json`。
- 若端口被占用，先停止旧栈，或临时调整 `docker-compose.yml` 的宿主端口映射。

### 9.2 交接核对（约 10 分钟）

| 核对项 | 命令 / 位置 | 期望 |
|---|---|---|
| 数据校验 | `python -m etl.validate` | 退出码 0，28 项 PASS |
| 图谱规模 | `MATCH (n:Entity) RETURN count(n);` / `MATCH ()-[r]->() RETURN count(r);` | 128,783 / 284,023 |
| 约束 | `SHOW CONSTRAINTS` | `entity_id_unique`（`Entity.id`） |
| API 健康 | `curl.exe http://127.0.0.1:18080/health` | `status=ok`、Neo4j connected |
| 中英文/缩写命中 | `/v1/entity/search?q=AML`、`q=急性髓系白血病` | 均命中 `MONDO:0018874` |
| 自动测试 | `python -m pytest -q`（需设置 `NEO4J_PASSWORD`） | 38 passed |
| RAGFlow 端到端 | `docs/05_acceptance_test.md` | R01–R25 25/25 PASS（作者环境实测） |
| 备份/恢复 | 第八节命令 + `backups/*.meta.json` | 恢复后计数不变、约束存在 |

## 十、已知限制与排障

### 10.1 已知限制

- **治疗方案 / HSCT 不入图**：白名单未定义治疗方案关系，DisMech 的 20 条治疗条目（含 HSCT）仅在 `data/staging/staged_dismech_treatments.csv`；相关提问只能回答“无图内关系证据”，需指南文本补充。
- **APL 的上级疾病**：Monarch 给出的 `SUBTYPE_OF` 指向 `MONDO:0017893`（遗传性 AML），不是 `MONDO:0018874`；不臆造 APL→AML 边。
- **表型覆盖稀疏**：种子疾病直接表型合计 80 条，AML 仅 2 个，AA 2 个；HPO 对白血病/再障注释有限。
- **疾病中文名**：仅种子疾病与 `entity_mapping.yaml` 覆盖 61 个表型；非种子疾病无官方中文名时字段留空。
- **未建节点类型**：Protein、Treatment、CellType 不建节点；`RELATED_TO` 关闭；Genotype/Case/ChemicalEntity 等仅进 staging 或丢弃。
- **Gene ID**：13,800 个 HGNC + 86 个无 HGNC 唯一匹配的 ncRNA 使用 Ensembl ID（`ENSG000...`）。
- **异常边**：320 条白名单外 Variant→Disease 边暂存并注明原因，另有 86 条 Genotype `model_of` 行因非 V1 节点类型丢弃，详见 `docs/03_validation_report.md`。
- **RAGFlow 省略患者节点**：V1 无患者数据源，未实现“患者数据查询 / 患者事实整理”，画布从查询规划直接进入检索词生成；与任务指引第十四章存在这一处差异。
- **检索仍有跨病种噪声**：10 篇指南措辞高度相似；`top_n=12` + 混合检索 0.3 时同病种 chunk 为 208/300；继续升权重会挤掉英文 ELN 指南。
- **图谱证据以 SUBTYPE_OF 为主**：种子邻域内 `paths` 多为疾病层级边，治疗/药物结论主要依赖指南文本。
- **UI 自动保存覆盖 API 改动**：画布打开时前端会用内存旧状态回写 DSL；改配置须在 UI 内保存并刷新复验；UI 保存会在 Retrieval 查询变量末尾追加 ` /`（实测对检索无影响）。
- **备份为整库文件级快照**：备份/恢复需短暂停止 Neo4j；不包含 `.env`、`data/raw` 与 RAGFlow 卷。
- **OMIM 上游记录**：27 条边可回溯到 OMIM（17 条基因—疾病，均有 Open Targets 共支撑；10 条疾病—表型经 HPOA 进入）。对外分发前需剔除或取得授权。

### 10.2 故障排查速查

| 现象 | 优先检查 |
|---|---|
| RAGFlow 调不到 API | Invoke URL 必须是服务名 `http://hematology-kg-api:8000/v1/kg/context`；两个容器都在 `ai-network`；在 RAGFlow 容器内 `curl http://hematology-kg-api:8000/health` |
| API 启动但 Neo4j 连接失败 | `docker logs hematology-kg-api`；确认 `NEO4J_URI=bolt://hematology-neo4j:7687`；`.env` 密码与 `NEO4J_AUTH` 一致 |
| 导入时报连接失败 | Neo4j 首次启动需 1–2 分钟，先用 `cypher-shell "RETURN 1;"` 确认就绪 |
| 中文搜索命不中 | 用 `name_zh` / `synonyms` 检索；确认节点 `name_zh` 非空 |
| 查询返回大量无关疾病 | 确认 `max_hops=2`；`max_hops=3` 会返回 422 |
| 同一关系重复很多条 | 多源合并边 `source` 用 `|` 连接，属预期；按 `edge_id` 去重 |
| 图谱回答确定但证据弱 | 最终 Agent 已要求证据优先；治疗结论以 Retrieval 指南原文为准 |
| 镜像 / volume 很大 | `data/raw` 不挂载；仅 `data/processed` 只读挂载；`docker system df` 清理未用镜像 |

## 十一、版本

| 组件 | 版本 |
|---|---|
| 图谱 | `hematology-kg-v1-20261118`（Monarch 2026-11-11） |
| Neo4j | `5.26.32`（镜像 `neo4j:5-community`） |
| RAGFlow | `infiniflow/ragflow:v1.0.0-rc3` |
| 下载脚本 | `1.1.0` |
| 导入脚本 | `1.0.0` |
| API | `1.0.0` |
