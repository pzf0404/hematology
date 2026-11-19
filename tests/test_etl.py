# -*- coding: utf-8 -*-
"""阶段 2 ETL 交付物的自动化校验（pytest）。

对应任务指引：
- 第九章 tests/test_etl.py
- 第十六章 manifest / build_manifest.json
- 第十七章 质量控制与自动校验
- 第十八章 验收问题集（数据层用例）

运行：
    pytest tests/test_etl.py -q

说明：
- 只读取 data/processed 与 data/staging，不重新构建数据；
- 计数断言是 V1 冻结值，ETL 重跑后若数字变化会显式失败，迫使复核差异。
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
STAGING = ROOT / "data" / "staging"
NODES_PATH = PROCESSED / "nodes.csv"
EDGES_PATH = PROCESSED / "edges.csv"
STAGED_PATH = STAGING / "edges_staged.csv"

NODE_COLUMNS = [
    "id", "label", "name", "name_zh", "canonical_id", "synonyms", "source_ids",
    "xrefs", "description", "source", "source_version", "retrieved_at",
]
EDGE_COLUMNS = [
    "edge_id", "subject_id", "predicate", "object_id", "original_predicate",
    "source", "source_dataset", "source_version", "source_record_id",
    "evidence_score", "pmid", "doi", "license", "retrieved_at",
]
ALLOWED_ARROWS = {
    "HAS_PHENOTYPE": {("Disease", "Phenotype")},
    "ASSOCIATED_WITH": {("Gene", "Disease")},
    "AFFECTS": {("Variant", "Gene")},
    "TREATS": {("Drug", "Disease")},
    "TARGETS": {("Drug", "Gene")},
    "PARTICIPATES_IN": {("Gene", "Pathway")},
    "INVOLVED_IN": {("Gene", "BiologicalProcess")},
    "SUBTYPE_OF": {("Disease", "Disease")},
}
EXPECTED_NODE_LABELS = {
    "BiologicalProcess": 10701,
    "Disease": 115,
    "Drug": 867,
    "Gene": 13886,
    "Pathway": 2276,
    "Phenotype": 61,
    "Variant": 100877,
}
EXPECTED_PREDICATES = {
    "AFFECTS": 100885,
    "ASSOCIATED_WITH": 35204,
    "HAS_PHENOTYPE": 80,
    "INVOLVED_IN": 102790,
    "PARTICIPATES_IN": 41605,
    "SUBTYPE_OF": 112,
    "TARGETS": 1820,
    "TREATS": 1527,
}
SEEDS = {
    "MONDO:0018874": "AML",
    "MONDO:0012883": "APL",
    "MONDO:0004967": "ALL",
    "MONDO:0011996": "CML",
    "MONDO:0004948": "CLL",
    "MONDO:0015909": "AA",
    "MONDO:0015610": "acquired AA",
    "EFO:0006927": "SAA",
}


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


@pytest.fixture(scope="module")
def nodes() -> dict[str, dict]:
    assert NODES_PATH.exists(), f"缺少 {NODES_PATH}，请先运行 python -m etl.extract_subgraph"
    _, rows = read_csv(NODES_PATH)
    return {r["id"]: r for r in rows}


@pytest.fixture(scope="module")
def edges() -> list[dict]:
    assert EDGES_PATH.exists(), f"缺少 {EDGES_PATH}，请先运行 python -m etl.extract_subgraph"
    _, rows = read_csv(EDGES_PATH)
    return rows


@pytest.fixture(scope="module")
def adjacency(edges: list[dict]) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        adj[e["subject_id"]].add(e["object_id"])
        adj[e["object_id"]].add(e["subject_id"])
    return adj


def test_files_exist_and_utf8_without_bom() -> None:
    for path in (NODES_PATH, EDGES_PATH):
        assert path.exists(), f"缺少交付文件 {path}"
        with path.open("rb") as f:
            assert f.read(3) != b"\xef\xbb\xbf", f"{path.name} 带 UTF-8 BOM"


def test_column_contract() -> None:
    node_header, _ = read_csv(NODES_PATH)
    edge_header, _ = read_csv(EDGES_PATH)
    assert node_header == NODE_COLUMNS
    assert edge_header == EDGE_COLUMNS


def test_node_counts_frozen(nodes: dict[str, dict]) -> None:
    assert len(nodes) == sum(EXPECTED_NODE_LABELS.values()) == 128783
    assert dict(Counter(r["label"] for r in nodes.values())) == EXPECTED_NODE_LABELS


def test_node_required_fields(nodes: dict[str, dict]) -> None:
    required = ("id", "label", "name", "canonical_id", "source", "source_version", "retrieved_at")
    missing = Counter()
    for r in nodes.values():
        for key in required:
            if not r[key].strip():
                missing[key] += 1
    assert not missing, f"必填字段为空: {dict(missing)}"


def test_node_ids_unique_and_canonical(nodes: dict[str, dict]) -> None:
    _, rows = read_csv(NODES_PATH)
    ids = Counter(r["id"] for r in rows)
    assert all(v == 1 for v in ids.values()), "存在重复节点 id"
    assert all(r["canonical_id"] == r["id"] for r in rows), "canonical_id 必须等于 id"


def test_no_forbidden_labels(nodes: dict[str, dict]) -> None:
    forbidden = {"Case", "Genotype", "ChemicalEntity", "Cell", "Protein", "AnatomicalEntity"}
    assert not (set(EXPECTED_NODE_LABELS) & forbidden)
    assert set(r["label"] for r in nodes.values()) == set(EXPECTED_NODE_LABELS)


def test_edge_counts_frozen(edges: list[dict]) -> None:
    assert len(edges) == sum(EXPECTED_PREDICATES.values()) == 284023
    assert dict(Counter(e["predicate"] for e in edges)) == EXPECTED_PREDICATES


def test_edge_ids_and_triples_unique(edges: list[dict]) -> None:
    edge_ids = Counter(e["edge_id"] for e in edges)
    triples = Counter((e["subject_id"], e["predicate"], e["object_id"]) for e in edges)
    assert all(v == 1 for v in edge_ids.values()), "edge_id 不唯一"
    assert all(v == 1 for v in triples.values()), "三元组不唯一"


def test_referential_integrity(edges: list[dict], nodes: dict[str, dict]) -> None:
    dangling = [e["edge_id"] for e in edges if e["subject_id"] not in nodes or e["object_id"] not in nodes]
    assert not dangling, f"悬空边 {len(dangling)} 条，例如 {dangling[:5]}"


def test_relation_direction(edges: list[dict], nodes: dict[str, dict]) -> None:
    bad = []
    for e in edges:
        pair = (nodes[e["subject_id"]]["label"], nodes[e["object_id"]]["label"])
        if pair not in ALLOWED_ARROWS[e["predicate"]]:
            bad.append((e["predicate"], pair))
    assert not bad, f"方向越界 {len(bad)} 条，例如 {Counter(bad).most_common(5)}"
    assert {e["predicate"] for e in edges} == set(ALLOWED_ARROWS), "8 类白名单关系未全部出现"


def test_edge_provenance(edges: list[dict]) -> None:
    required = ("edge_id", "subject_id", "predicate", "object_id", "original_predicate",
                "source", "source_version", "retrieved_at")
    missing = Counter()
    for e in edges:
        for key in required:
            if not e[key].strip():
                missing[key] += 1
    assert not missing, f"边必填字段为空: {dict(missing)}"
    assert all(e["license"].strip() for e in edges), "存在缺 license 的边"
    assert all(e["pmid"].strip() or e["source_record_id"].strip() for e in edges), "存在不可溯源的边"
    assert sum(1 for e in edges if e["pmid"].strip()) == 55473


def test_no_orphan_nodes(nodes: dict[str, dict], adjacency: dict[str, set[str]]) -> None:
    orphans = [nid for nid in nodes if nid not in adjacency]
    assert not orphans, f"孤立节点 {len(orphans)} 个，例如 {orphans[:5]}"


def test_gene_id_format(nodes: dict[str, dict]) -> None:
    genes = [n for n in nodes.values() if n["label"] == "Gene"]
    bad = [n["id"] for n in genes if not (n["id"].startswith("HGNC:") or n["id"].startswith("ENSG0"))]
    assert not bad, f"非法 Gene ID {len(bad)} 个，例如 {bad[:5]}"
    assert not [n["id"] for n in genes if n["id"].startswith("ENSG:")], "存在 ENSG:ENSG 双前缀"
    assert sum(1 for n in genes if n["id"].startswith("ENSG0")) == 86


def test_chinese_coverage(nodes: dict[str, dict]) -> None:
    pheno = [n for n in nodes.values() if n["label"] == "Phenotype"]
    assert pheno and all(n["name_zh"].strip() for n in pheno), "存在无中文名的表型"
    assert all(nodes[s]["name_zh"].strip() for s in SEEDS), "种子疾病缺中文名"


def test_seed_synonyms(nodes: dict[str, dict]) -> None:
    for seed, abbrev in SEEDS.items():
        if abbrev == "acquired AA":
            continue  # 获得性再障以全称入图，无独立缩写词条
        syn = nodes[seed]["synonyms"].upper()
        assert abbrev.upper() in syn or abbrev.upper() in nodes[seed]["name"].upper(), \
            f"{abbrev} 的缩写未出现在 synonyms/name 中"


def test_multi_source_edges(edges: list[dict]) -> None:
    multi = [e for e in edges if "|" in e["source"]]
    assert len(multi) == 67, f"多来源聚合边应为 67 条，实际 {len(multi)}"
    assert Counter(e["source"] for e in multi) == {
        "Monarch KG|Open Targets": 38,
        "DisMech|Open Targets": 20,
        "Monarch KG|DisMech": 7,
        "Monarch KG|DisMech|Open Targets": 2,
    }


def test_staging_report() -> None:
    report = json.loads((STAGING / "normalize_report.json").read_text(encoding="utf-8"))
    _, staged = read_csv(STAGED_PATH)
    assert report["edges_staged"] == len(staged) == 320
    assert Counter(r["staging_reason"] for r in staged) == {"白名单无 Variant→Disease 箭头": 320}
    assert Counter(r["predicate"] for r in staged) == {
        "CAUSES": 315,
        "ASSOCIATED_WITH_INCREASED_LIKELIHOOD_OF": 5,
    }
    assert report["staged_dropped"] == {"biolink:model_of|Genotype 非 V1 节点类型": 86}
    assert all(r["staging_reason"].strip() for r in staged), "暂存边必须写明原因"
    assert report["illegal_type_combo_total"] > 0, "非法类型组合未计入异常报告"
    assert "biolink:has_phenotype|Gene->Phenotype" in report["illegal_type_combo"]


def test_build_manifest() -> None:
    path = PROCESSED / "build_manifest.json"
    assert path.exists(), "缺少 build_manifest.json（任务指引第十六章）"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["node_count"] == 128783
    assert manifest["edge_count"] == 284023
    assert manifest["disease_count"] == 115
    assert manifest["sources"] and {"name", "version", "license"} <= set(manifest["sources"][0])
    assert "git_commit" in manifest


@pytest.mark.parametrize("subject,predicate,object_id", [
    # 验收问题 1：药物→靶点→基因→疾病
    ("CHEMBL941", "TARGETS", "HGNC:76"),
    ("CHEMBL941", "TREATS", "MONDO:0011996"),
    # 验收问题 2/10：环孢素与再障
    ("CHEMBL160", "TREATS", "MONDO:0015909"),
    # 验收问题 3：FLT3 与 AML
    ("HGNC:3765", "ASSOCIATED_WITH", "MONDO:0018874"),
    # 验收问题 2：PML / RARA 与 APL
    ("HGNC:9113", "ASSOCIATED_WITH", "MONDO:0012883"),
    ("HGNC:9864", "ASSOCIATED_WITH", "MONDO:0012883"),
    # 验收问题 13：基因通过通路关联 AML
    ("HGNC:3765", "PARTICIPATES_IN", "Reactome:R-HSA-9607240"),
])
def test_acceptance_triples(edges: list[dict], subject: str, predicate: str, object_id: str) -> None:
    assert any(e["subject_id"] == subject and e["predicate"] == predicate and e["object_id"] == object_id
               for e in edges), f"缺少验收三元组 {subject} -[{predicate}]-> {object_id}"
