#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""血液病知识图谱 V1 — FastAPI 服务（阶段 4）。

依据任务指引第十二、十三章：
- /health、/v1/entity/search、/v1/entity/{id}/neighbors、/v1/kg/context
- 所有 Neo4j 查询均为固定模板 + 参数，禁止把用户问题直接变成 Cypher
- max_hops 硬上限 2，limit 硬上限 50，关系仅限 8 类白名单
- 查询失败返回可读 JSON 错误，不返回 500 堆栈
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, Query
from neo4j import GraphDatabase
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(os.getenv("KG_CONFIG", str(PROJECT_ROOT / "config" / "disease_seeds.yaml")))

RELATIONS = (
    "HAS_PHENOTYPE",
    "ASSOCIATED_WITH",
    "AFFECTS",
    "TREATS",
    "TARGETS",
    "PARTICIPATES_IN",
    "INVOLVED_IN",
    "SUBTYPE_OF",
)
MAX_HOPS = 2
MAX_LIMIT = 50
DEFAULT_LIMIT = 20
ROUTE_ALLOWED = [
    "leukemia",
    "aplastic_anemia",
    "AML",
    "APL",
    "ALL",
    "CML",
    "CLL",
    "AA",
    "acquired_AA",
    "SAA",
]

app = FastAPI(
    title="血液病知识图谱 V1 API",
    description=(
        "面向 RAGFlow 的受控知识图谱查询服务。仅提供固定查询模板，"
        "max_hops ≤ 2，limit ≤ 50，关系仅限白名单；返回结构化证据与可读 context。"
    ),
    version="1.0.0",
)

_driver = None


def get_driver():
    global _driver
    if _driver is None:
        password = os.getenv("NEO4J_PASSWORD", "").strip()
        if not password:
            raise HTTPException(status_code=503, detail="NEO4J_PASSWORD 未配置")
        _driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687").strip(),
            auth=(os.getenv("NEO4J_USER", "neo4j").strip(), password),
        )
    return _driver


def fail(exc: Exception) -> None:
    raise HTTPException(
        status_code=503,
        detail=f"Neo4j 查询失败：{type(exc).__name__}: {str(exc)[:200]}",
    )


def business_label(labels: list[str]) -> str:
    return next((x for x in labels if x != "Entity"), labels[0] if labels else "")


def load_seed_config() -> tuple[dict[str, list[str]], dict[str, str]]:
    try:
        cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"种子配置不可用：{CONFIG_PATH}（{type(exc).__name__}）",
        )
    groups: dict[str, list[str]] = {}
    index: dict[str, str] = {}
    for group in ("leukemia", "aplastic_anemia"):
        ids: list[str] = []
        for d in (cfg.get(group) or {}).get("diseases", []):
            cid = d.get("canonical_id")
            if not cid:
                continue
            ids.append(cid)
            keys = [
                cid,
                d.get("name"),
                d.get("name_zh"),
                d.get("abbrev"),
                *(d.get("synonyms") or []),
                *(d.get("aliases") or []),
            ]
            for key in keys:
                if key:
                    index[str(key).strip().lower()] = cid
        groups[group] = ids
    return groups, index


ROUTE_ALIASES = {
    "白血病": "leukemia",
    "leukemia": "leukemia",
    "再障": "aplastic_anemia",
    "再生障碍性贫血": "aplastic_anemia",
    "aplastic anemia": "aplastic_anemia",
    "aplastic_anemia": "aplastic_anemia",
    # 单一疾病路由别名：值为 canonical_id，而非疾病组名
    "acquired_aa": "MONDO:0015610",
}


def resolve_route(route: str) -> list[str]:
    groups, index = load_seed_config()
    key = route.strip().lower()
    if key in groups:
        return groups[key]
    if key in ROUTE_ALIASES:
        target = ROUTE_ALIASES[key]
        return groups[target] if target in groups else [target]
    if key in index:
        return [index[key]]
    raise HTTPException(
        status_code=400,
        detail={"message": "未知 disease_route", "allowed": ROUTE_ALLOWED},
    )


def prioritize_route_ids(ids: list[str], query: str) -> list[str]:
    """把问题中明确提到的种子疾病排到前面，避免 route 组内顺序导致取错邻域。"""
    _, index = load_seed_config()
    q = query.lower()
    mentioned = {cid for key, cid in index.items() if key and key in q}
    return sorted(ids, key=lambda cid: 0 if cid in mentioned else 1)


SEARCH_QUERY = """
MATCH (n:Entity)
WHERE (toLower(n.name) CONTAINS $q
   OR toLower(coalesce(n.name_zh, '')) CONTAINS $q
   OR toLower(coalesce(n.synonyms, '')) CONTAINS $q)
  AND NOT n.id IN $exclude
RETURN n.id AS id, n.name AS name, n.name_zh AS name_zh,
       n.synonyms AS synonyms, labels(n) AS labels
LIMIT $fetch
"""
EXACT_QUERY = """
MATCH (n:Entity)
WHERE toLower(n.name) = $q
   OR toLower(coalesce(n.name_zh, '')) = $q
   OR $q IN [x IN split(toLower(coalesce(n.synonyms, '')), '|') | trim(x)]
RETURN n.id AS id, n.name AS name, n.name_zh AS name_zh,
       n.synonyms AS synonyms, labels(n) AS labels
LIMIT $fetch
"""

LABEL_ORDER = {
    "Disease": 0,
    "Gene": 1,
    "Drug": 2,
    "Phenotype": 3,
    "Pathway": 4,
    "BiologicalProcess": 5,
    "Variant": 6,
}


def search_entities(session, query: str, limit: int) -> list[dict[str, Any]]:
    q = query.strip().lower()
    if not q:
        return []
    fetch = min(max(limit * 3, limit), 150)
    exact_rows = session.run(EXACT_QUERY, q=q, fetch=fetch).data()
    exact_ids = [r["id"] for r in exact_rows]
    rows = exact_rows + session.run(
        SEARCH_QUERY, q=q, exclude=exact_ids, fetch=fetch
    ).data()

    def rank(row: dict[str, Any]) -> tuple[int, int, int]:
        name = (row["name"] or "").lower()
        zh = (row["name_zh"] or "").lower()
        syn = [x.strip().lower() for x in (row["synonyms"] or "").split("|") if x.strip()]
        if q in (name, zh) or q in syn:
            score = 0
        elif name.startswith(q) or zh.startswith(q):
            score = 1
        elif any(x.startswith(q) for x in syn):
            score = 2
        else:
            score = 3
        return score, LABEL_ORDER.get(business_label(row["labels"]), 9), len(name)

    rows.sort(key=rank)
    return [
        {
            "id": r["id"],
            "label": business_label(r["labels"]),
            "name": r["name"],
            "name_zh": r["name_zh"],
            "synonyms": r["synonyms"],
        }
        for r in rows[:limit]
    ]


PATH_1 = """
MATCH p=(a:Entity {id:$a})-[*1..1]-(b:Entity {id:$b})
WHERE ALL(r IN relationships(p) WHERE type(r) IN $rels)
RETURN p LIMIT $limit
"""
PATH_2 = """
MATCH p=(a:Entity {id:$a})-[*1..2]-(b:Entity {id:$b})
WHERE ALL(r IN relationships(p) WHERE type(r) IN $rels)
RETURN p LIMIT $limit
"""
NEIGHBOR_1 = """
MATCH p=(n:Entity {id:$id})-[*1..1]-(m:Entity)
WHERE ALL(r IN relationships(p) WHERE type(r) IN $rels)
RETURN p LIMIT $limit
"""
NEIGHBOR_2 = """
MATCH p=(n:Entity {id:$id})-[*1..2]-(m:Entity)
WHERE ALL(r IN relationships(p) WHERE type(r) IN $rels)
RETURN p LIMIT $limit
"""

DISEASE_GENES = """
MATCH (g:Gene)-[r:ASSOCIATED_WITH]->(d:Disease {id:$id})
RETURN g.id AS gene_id, g.symbol AS symbol, g.name AS gene_name,
       r.source AS source, r.source_version AS source_version,
       r.source_record_id AS source_record_id,
       r.original_predicate AS original_predicate, r.pmid AS pmid
LIMIT $limit
"""
DISEASE_PHENOTYPES = """
MATCH (d:Disease {id:$id})-[r:HAS_PHENOTYPE]->(p:Phenotype)
RETURN p.id AS phenotype_id, p.name AS phenotype, p.name_zh AS name_zh,
       r.source AS source, r.source_version AS source_version,
       r.source_record_id AS source_record_id,
       r.original_predicate AS original_predicate, r.pmid AS pmid
LIMIT $limit
"""
DISEASE_DRUGS = """
MATCH (dr:Drug)-[r:TREATS]->(d:Disease {id:$id})
RETURN dr.id AS drug_id, dr.name AS drug,
       r.source AS source, r.source_version AS source_version,
       r.source_record_id AS source_record_id,
       r.original_predicate AS original_predicate, r.pmid AS pmid
LIMIT $limit
"""
DRUG_TARGETS = """
MATCH (dr:Drug {id:$id})-[r:TARGETS]->(g:Gene)
RETURN g.id AS gene_id, g.symbol AS symbol, g.name AS gene_name,
       r.source AS source, r.source_version AS source_version,
       r.source_record_id AS source_record_id,
       r.original_predicate AS original_predicate, r.pmid AS pmid
LIMIT $limit
"""
GENE_PATHWAYS = """
MATCH (g:Gene {id:$id})-[r:PARTICIPATES_IN]->(p:Pathway)
RETURN p.id AS pathway_id, p.name AS pathway,
       r.source AS source, r.source_version AS source_version,
       r.source_record_id AS source_record_id,
       r.original_predicate AS original_predicate, r.pmid AS pmid
LIMIT $limit
"""


def cap_limit(value: int) -> int:
    return max(1, min(int(value), MAX_LIMIT))


def find_disease_genes(session, disease_id: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    return session.run(DISEASE_GENES, id=disease_id, limit=cap_limit(limit)).data()


def find_disease_phenotypes(session, disease_id: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    return session.run(DISEASE_PHENOTYPES, id=disease_id, limit=cap_limit(limit)).data()


def find_disease_drugs(session, disease_id: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    return session.run(DISEASE_DRUGS, id=disease_id, limit=cap_limit(limit)).data()


def find_drug_targets(session, drug_id: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    return session.run(DRUG_TARGETS, id=drug_id, limit=cap_limit(limit)).data()


def find_gene_pathways(session, gene_id: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    return session.run(GENE_PATHWAYS, id=gene_id, limit=cap_limit(limit)).data()


def find_biomedical_path(
    session, start_id: str, end_id: str, max_hops: int = MAX_HOPS, limit: int = DEFAULT_LIMIT
) -> list[Any]:
    hops = max(1, min(int(max_hops), MAX_HOPS))
    if start_id == end_id:
        return []
    query = PATH_1 if hops == 1 else PATH_2
    return [
        record["p"]
        for record in session.run(
            query, a=start_id, b=end_id, rels=list(RELATIONS), limit=cap_limit(limit)
        )
    ]


def node_brief(node) -> dict[str, Any]:
    labels = list(node.labels)
    return {
        "id": node.get("id"),
        "label": business_label(labels),
        "name": node.get("name"),
        "name_zh": node.get("name_zh"),
    }


def rel_brief(rel) -> dict[str, Any]:
    return {
        "edge_id": rel.get("edge_id"),
        "type": rel.type,
        "source": rel.get("source"),
        "source_version": rel.get("source_version"),
        "source_record_id": rel.get("source_record_id"),
        "original_predicate": rel.get("original_predicate"),
        "license": rel.get("license"),
        "pmid": rel.get("pmid"),
        "evidence_score": rel.get("evidence_score"),
        "subject_id": rel.start_node.get("id"),
        "object_id": rel.end_node.get("id"),
    }


def path_brief(path) -> dict[str, Any]:
    nodes = [node_brief(n) for n in path.nodes]
    rels = [rel_brief(r) for r in path.relationships]
    # 邻居查询用无向模式展开，节点顺序不保证是主→客；按关系方向还原
    if len(nodes) == len(rels) + 1 and len(nodes) >= 2:
        if (nodes[0]["id"], nodes[1]["id"]) == (rels[0].get("object_id"), rels[0].get("subject_id")):
            nodes.reverse()
            rels.reverse()
    return {"nodes": nodes, "relationships": rels}


def path_key(path) -> tuple:
    return (
        tuple(n.get("id") for n in path.nodes),
        tuple(r.get("edge_id") for r in path.relationships),
    )


def collect_evidence(paths: list[Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for path in paths:
        for rel in path.relationships:
            eid = rel.get("edge_id")
            if not eid or eid in seen:
                continue
            seen.add(eid)
            out.append(
                {
                    "edge_id": eid,
                    "subject_id": rel.start_node.get("id"),
                    "subject_name": rel.start_node.get("name"),
                    "predicate": rel.type,
                    "object_id": rel.end_node.get("id"),
                    "object_name": rel.end_node.get("name"),
                    "source": rel.get("source"),
                    "source_version": rel.get("source_version"),
                    "source_record_id": rel.get("source_record_id"),
                    "original_predicate": rel.get("original_predicate"),
                    "license": rel.get("license"),
                    "pmid": rel.get("pmid"),
                    "evidence_score": rel.get("evidence_score"),
                }
            )
    return out


SPLIT_RE = re.compile(r"[\s,，。；;：:、？?！!（）()\[\]{}<>/\\|\"'“”‘’]+")
STOP_WORDS = (
    "与", "和", "的", "有", "什么", "为什么", "哪些", "关系", "相关", "已知",
    "出现", "治疗", "基因", "药物", "机制", "通路", "表型", "是否", "如何",
    "之间", "是什么", "会", "能", "可以", "请问", "一下",
)


def query_tokens(query: str) -> list[str]:
    parts = [p.strip().lower() for p in SPLIT_RE.split(query) if p.strip()]
    out: list[str] = []
    for part in parts:
        for word in STOP_WORDS:
            part = part.replace(word, " ")
        for token in part.split():
            token = token.strip()
            if len(token) >= 2 and token not in out:
                out.append(token)
    if not out and query.strip():
        out = [query.strip().lower()]
    return out[:8]


def parse_relations(raw: str | None) -> list[str]:
    if not raw:
        return list(RELATIONS)
    rels = [x.strip().upper() for x in raw.split(",") if x.strip()]
    invalid = [x for x in rels if x not in RELATIONS]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail={"message": "关系不在白名单", "invalid": invalid, "allowed": list(RELATIONS)},
        )
    return rels


@app.get("/health", summary="健康检查 / Docker readiness")
def health() -> dict[str, Any]:
    try:
        with get_driver().session() as session:
            session.run("RETURN 1 AS ok").consume()
            version = session.run(
                "CALL dbms.components() YIELD versions RETURN versions[0] AS v"
            ).single()["v"]
        return {"status": "ok", "neo4j": "connected", "version": version}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Neo4j 不可用：{type(exc).__name__}")


@app.get("/v1/entity/search", summary="中文/英文/同义词实体搜索")
def entity_search(
    q: str = Query(..., min_length=1, description="名称、中文名或同义词片段"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> dict[str, Any]:
    try:
        with get_driver().session() as session:
            results = search_entities(session, q, limit)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        fail(exc)
    return {"query": q, "limit": limit, "count": len(results), "results": results}


@app.get("/v1/entity/{id}/neighbors", summary="按关系、深度、limit 查询邻居")
def entity_neighbors(
    id: str,
    depth: int = Query(1, ge=1, le=MAX_HOPS),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    relations: str | None = Query(None, description="逗号分隔的白名单关系；缺省为全部"),
) -> dict[str, Any]:
    entity_id = id
    rels = parse_relations(relations)
    try:
        with get_driver().session() as session:
            node = session.run(
                "MATCH (n:Entity {id:$id}) RETURN n", id=entity_id
            ).single()
            if not node:
                raise HTTPException(status_code=404, detail=f"实体不存在：{entity_id}")
            query = NEIGHBOR_1 if depth == 1 else NEIGHBOR_2
            paths = [
                record["p"]
                for record in session.run(query, id=entity_id, rels=rels, limit=limit)
            ]
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        fail(exc)

    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}
    for path in paths:
        for n in path.nodes:
            nodes[n.get("id")] = node_brief(n)
        for r in path.relationships:
            edges[r.get("edge_id")] = rel_brief(r)
    return {
        "entity": node_brief(node["n"]),
        "depth": depth,
        "limit": limit,
        "relations": rels,
        "paths": [path_brief(p) for p in paths],
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
    }


class ContextRequest(BaseModel):
    disease_route: str = Field(..., min_length=1, description="leukemia / aplastic_anemia / 种子缩写或 ID")
    query: str = Field(..., min_length=1, description="用户原始问题")
    max_hops: int = Field(2, ge=1, le=MAX_HOPS)
    limit: int = Field(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)


def build_context(
    route: str,
    matched: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    max_hops: int,
    limit: int,
) -> str:
    lines = [f"疾病路径：{route}（max_hops={max_hops}, limit={limit}）"]
    if matched:
        lines.append(
            "命中实体：" + "；".join(f"{m['name']}（{m['id']}）" for m in matched[:10])
        )
    if evidence:
        lines.append("知识图谱关系证据：")
        for e in evidence[:20]:
            lines.append(
                f"- {e['subject_name']} -[{e['predicate']}]-> {e['object_name']}"
                f"（来源：{e['source']}；版本：{e['source_version']}；记录：{e['source_record_id']}）"
            )
    else:
        lines.append("知识图谱关系证据：未找到符合白名单的路径。")
    lines.append("证据类型：仅知识图谱关系证据（knowledge_graph）；未包含指南/文献文本证据。")
    lines.append("提示：图谱关系不能替代临床指南，不得仅凭图谱边生成诊疗结论。")
    return "\n".join(lines)


@app.post("/v1/kg/context", summary="面向 RAGFlow 的结构化证据 + 可读 context")
def kg_context(req: ContextRequest) -> dict[str, Any]:
    route_ids = prioritize_route_ids(resolve_route(req.disease_route), req.query)
    tokens = query_tokens(req.query)
    try:
        with get_driver().session() as session:
            matched: list[dict[str, Any]] = []
            seen: set[str] = set()

            def add_entity(item: dict[str, Any]) -> None:
                if item["id"] not in seen and len(matched) < 10:
                    seen.add(item["id"])
                    matched.append(item)

            for row in sorted(
                session.run(
                    "MATCH (d:Disease) WHERE d.id IN $ids "
                    "RETURN d.id AS id, d.name AS name, d.name_zh AS name_zh, labels(d) AS labels",
                    ids=route_ids,
                ).data(),
                key=lambda r: route_ids.index(r["id"]) if r["id"] in route_ids else 99,
            ):
                add_entity(
                    {
                        "id": row["id"],
                        "label": business_label(row["labels"]),
                        "name": row["name"],
                        "name_zh": row["name_zh"],
                        "matched_by": "disease_route",
                    }
                )
            for token in tokens:
                for item in search_entities(session, token, 3):
                    item["matched_by"] = "query"
                    add_entity(item)

            paths: list[Any] = []
            seen_paths: set[tuple] = set()

            def add_path(path) -> bool:
                key = path_key(path)
                if key in seen_paths:
                    return False
                seen_paths.add(key)
                paths.append(path)
                return len(paths) >= req.limit

            route_set = set(route_ids)
            for item in matched:
                if item["id"] in route_set:
                    continue
                for rid in route_ids[:3]:
                    for path in find_biomedical_path(
                        session, item["id"], rid, req.max_hops, min(5, req.limit)
                    ):
                        if add_path(path):
                            break
                    if len(paths) >= req.limit:
                        break
                if len(paths) >= req.limit:
                    break

            # 补充 route 疾病的一跳邻域，保证“疾病 + 表型/药物/基因”型问题有上下文
            if len(paths) < req.limit:
                for rid in route_ids[:2]:
                    for record in session.run(
                        NEIGHBOR_1, id=rid, rels=list(RELATIONS), limit=min(5, req.limit - len(paths))
                    ):
                        if add_path(record["p"]) and len(paths) >= req.limit:
                            break
                    if len(paths) >= req.limit:
                        break
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        fail(exc)

    paths.sort(key=lambda p: len(p.relationships))
    evidence = collect_evidence(paths)
    return {
        "disease_route": req.disease_route,
        "route_disease_ids": route_ids,
        "query": req.query,
        "max_hops": req.max_hops,
        "limit": req.limit,
        "matched_entities": matched,
        "paths": [path_brief(p) for p in paths],
        "evidence": evidence,
        "evidence_types": {"knowledge_graph": True, "guideline_text": False},
        "context": build_context(req.disease_route, matched, evidence, req.max_hops, req.limit),
    }


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"service": "hematology-kg-api", "docs": "/docs", "health": "/health"}
