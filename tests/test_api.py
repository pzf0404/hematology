# -*- coding: utf-8 -*-
"""阶段 4 API 验收测试（对应任务指引第十二、十三、十八、二十二章）。

运行前提：
- Neo4j 已启动且已导入阶段 2 数据；
- 当前 shell 设置 NEO4J_PASSWORD（与 .env 一致）。

若未设置密码或 Neo4j 不可用，本文件整体 skip，不影响 test_etl.py。
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from api.app.main import app


@pytest.fixture(scope="module")
def client():
    if not os.getenv("NEO4J_PASSWORD"):
        pytest.skip("未设置 NEO4J_PASSWORD，跳过 API 集成测试")
    with TestClient(app) as c:
        health = c.get("/health")
        if health.status_code != 200:
            pytest.skip(f"Neo4j 不可用：{health.status_code} {health.text[:120]}")
        yield c


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["neo4j"] == "connected"
    assert body["version"]


def test_openapi_has_four_endpoints(client: TestClient) -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    for path in ("/health", "/v1/entity/search", "/v1/entity/{id}/neighbors", "/v1/kg/context"):
        assert path in paths


def test_search_english_and_abbreviation(client: TestClient) -> None:
    r = client.get("/v1/entity/search", params={"q": "AML", "limit": 10})
    assert r.status_code == 200
    ids = [x["id"] for x in r.json()["results"]]
    assert "MONDO:0018874" in ids


def test_search_chinese(client: TestClient) -> None:
    r = client.get("/v1/entity/search", params={"q": "急性髓系白血病", "limit": 10})
    assert r.status_code == 200
    assert "MONDO:0018874" in [x["id"] for x in r.json()["results"]]
    assert r.json()["results"][0]["id"] == "MONDO:0018874"


def test_search_limit_cap(client: TestClient) -> None:
    assert client.get("/v1/entity/search", params={"q": "AML", "limit": 51}).status_code == 422


def test_neighbors(client: TestClient) -> None:
    found = client.get("/v1/entity/search", params={"q": "FLT3", "limit": 10}).json()["results"]
    gene = next(x for x in found if x["label"] == "Gene" and x["name"].upper() == "FLT3")
    r = client.get(f"/v1/entity/{gene['id']}/neighbors", params={"depth": 1, "limit": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["paths"] and body["edges"]
    assert all(e["source"] and e["license"] for e in body["edges"])


def test_neighbors_depth_cap(client: TestClient) -> None:
    found = client.get("/v1/entity/search", params={"q": "FLT3", "limit": 10}).json()["results"]
    gene = next(x for x in found if x["label"] == "Gene" and x["name"].upper() == "FLT3")
    assert client.get(f"/v1/entity/{gene['id']}/neighbors", params={"depth": 3}).status_code == 422


def test_neighbors_relation_whitelist(client: TestClient) -> None:
    found = client.get("/v1/entity/search", params={"q": "FLT3", "limit": 10}).json()["results"]
    gene = next(x for x in found if x["label"] == "Gene" and x["name"].upper() == "FLT3")
    ok = client.get(
        f"/v1/entity/{gene['id']}/neighbors", params={"relations": "TARGETS,ASSOCIATED_WITH"}
    )
    assert ok.status_code == 200
    bad = client.get(f"/v1/entity/{gene['id']}/neighbors", params={"relations": "EVIL"})
    assert bad.status_code == 400


def test_context_leukemia_flt3(client: TestClient) -> None:
    r = client.post(
        "/v1/kg/context",
        json={
            "disease_route": "leukemia",
            "query": "FLT3 与 AML 有什么关系？",
            "max_hops": 2,
            "limit": 20,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["matched_entities"]
    assert body["paths"]
    assert body["evidence"]
    assert body["evidence_types"] == {"knowledge_graph": True, "guideline_text": False}
    assert "knowledge_graph" in body["context"]
    assert "指南" in body["context"]


def test_context_aplastic_anemia_chinese(client: TestClient) -> None:
    r = client.post(
        "/v1/kg/context",
        json={
            "disease_route": "aplastic_anemia",
            "query": "再生障碍性贫血为什么会出现血小板减少",
            "max_hops": 2,
            "limit": 30,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "MONDO:0015909" in [x["id"] for x in body["matched_entities"]]
    assert body["context"].startswith("疾病路径")


def test_context_unknown_route(client: TestClient) -> None:
    r = client.post(
        "/v1/kg/context",
        json={"disease_route": "not_a_disease", "query": "test", "max_hops": 2, "limit": 10},
    )
    assert r.status_code == 400


def test_context_hard_caps(client: TestClient) -> None:
    base = {"disease_route": "leukemia", "query": "FLT3"}
    assert client.post("/v1/kg/context", json={**base, "max_hops": 3, "limit": 10}).status_code == 422
    assert client.post("/v1/kg/context", json={**base, "max_hops": 2, "limit": 99}).status_code == 422


def test_controlled_query_functions() -> None:
    """任务指引第十三章：至少提供 6 个受控查询函数，均限制数量/深度/关系类型。"""
    if not os.getenv("NEO4J_PASSWORD"):
        pytest.skip("未设置 NEO4J_PASSWORD")
    from api.app.main import (
        find_biomedical_path,
        find_disease_drugs,
        find_disease_genes,
        find_disease_phenotypes,
        find_drug_targets,
        find_gene_pathways,
        get_driver,
    )

    with get_driver().session() as session:
        assert find_disease_genes(session, "MONDO:0015909", 5)
        assert find_disease_phenotypes(session, "MONDO:0015909", 5)
        assert find_disease_drugs(session, "MONDO:0015909", 5)
        assert find_drug_targets(session, "CHEMBL941", 5)
        assert find_gene_pathways(session, "HGNC:3765", 5)
        assert find_biomedical_path(session, "HGNC:3765", "MONDO:0018874", 2, 5)
