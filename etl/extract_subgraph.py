#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V1 子图抽取：从 staging 结果裁剪到 8 个种子疾病的 1–2 hop 邻域。

用法：
    python etl/extract_subgraph.py

输入：
    data/staging/nodes.csv
    data/staging/edges.csv
    config/entity_mapping.yaml

输出：
    data/processed/nodes.csv   列严格等于任务文档
    data/processed/edges.csv   列严格等于任务文档
    data/processed/extract_report.json
    data/processed/build_manifest.json  任务指引第十六章的构建清单

规则（与 relation_allowlist.yaml 的 extraction 段一致）：
- hop1：种子疾病 + 白名单直接邻居（表型、基因、药物、SUBTYPE_OF 直接父/子）
- hop2：hop1 基因的 Pathway / BiologicalProcess / Variant；hop1 药物的靶点基因
- 禁止纳入 GO 根节点；禁止从 hub 继续扩散
- 引用完整性：边两端必须都能在 nodes.csv 找到，否则报错退出
"""

from __future__ import annotations

import collections
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data" / "staging"
PROCESSED = ROOT / "data" / "processed"

NODE_COLUMNS = [
    "id", "label", "name", "name_zh", "canonical_id", "synonyms", "source_ids",
    "xrefs", "description", "source", "source_version", "retrieved_at",
]
EDGE_COLUMNS = [
    "edge_id", "subject_id", "predicate", "object_id", "original_predicate",
    "source", "source_dataset", "source_version", "source_record_id",
    "evidence_score", "pmid", "doi", "license", "retrieved_at",
]
GO_ROOTS = {"GO:0008150", "GO:0003674", "GO:0005575"}
HOP2_GENE_PREDICATES = {"PARTICIPATES_IN", "INVOLVED_IN", "AFFECTS"}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_seeds() -> set[str]:
    mapping = yaml.safe_load((ROOT / "config" / "entity_mapping.yaml").read_text(encoding="utf-8"))
    seeds = {d["canonical_id"] for d in mapping["diseases"]
             if d.get("in_graph") and d.get("canonical_id")}
    if len(seeds) != 8:
        raise SystemExit(f"种子疾病数量异常: {len(seeds)}（预期 8）")
    return seeds


def git_commit() -> str | None:
    """读取当前 commit；非 git 仓库时返回 None，不伪造版本号。"""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT,
            capture_output=True, text=True, timeout=5, check=False,
        )
        if out.returncode != 0:
            return None
        commit = out.stdout.strip()
        return commit if len(commit) == 40 else None
    except (OSError, subprocess.SubprocessError):
        return None


def load_source_versions() -> list[dict]:
    path = ROOT / "data" / "raw" / "manifest.json"
    if not path.exists():
        return []
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    sources = []
    for s in manifest.get("sources", []):
        version = s.get("version")
        # 上游只提供 latest 标签时，以归档日（release_date）作为可追溯版本
        if not version or str(version).lower() == "latest":
            version = s.get("release_date") or version
        sources.append({"name": s.get("name"), "version": version, "license": s.get("license")})
    return sources


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    PROCESSED.mkdir(parents=True, exist_ok=True)
    seeds = load_seeds()

    # 第一遍：hop1 药物（TREATS 种子疾病）与 hop1 边
    hop1_drugs: set[str] = set()
    with (STAGING / "edges.csv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["predicate"] == "TREATS" and r["object_id"] in seeds:
                hop1_drugs.add(r["subject_id"])

    hop1_genes: set[str] = set()
    hop1_diseases: set[str] = set(seeds)
    hop1_rows: list[dict] = []
    with (STAGING / "edges.csv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            s, p, o = r["subject_id"], r["predicate"], r["object_id"]
            if s in seeds or o in seeds:
                if p == "SUBTYPE_OF":
                    hop1_diseases.add(s)
                    hop1_diseases.add(o)
                hop1_rows.append(r)
                if p == "ASSOCIATED_WITH" and o in seeds:
                    hop1_genes.add(s)
                continue
            if p == "TARGETS" and s in hop1_drugs:
                hop1_rows.append(r)
                hop1_genes.add(o)

    # 第二遍：hop2（基因的机制关系），剔除 GO 根节点
    # 方向：PARTICIPATES_IN / INVOLVED_IN 主体是 Gene；AFFECTS 主体是 Variant、对象才是 Gene
    hop2_rows: list[dict] = []
    go_root_dropped = 0
    with (STAGING / "edges.csv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            s, p, o = r["subject_id"], r["predicate"], r["object_id"]
            if p not in HOP2_GENE_PREDICATES:
                continue
            anchor = o if p == "AFFECTS" else s
            if anchor not in hop1_genes:
                continue
            if o in GO_ROOTS:
                go_root_dropped += 1
                continue
            hop2_rows.append(r)

    selected_ids: set[str] = set()
    for r in hop1_rows + hop2_rows:
        selected_ids.add(r["subject_id"])
        selected_ids.add(r["object_id"])
    selected_ids |= hop1_diseases

    node_rows: dict[str, dict] = {}
    with (STAGING / "nodes.csv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["id"] in selected_ids:
                node_rows[r["id"]] = r
    missing = selected_ids - set(node_rows)
    if missing:
        raise SystemExit(f"节点缺失 {len(missing)} 个，例如 {sorted(missing)[:5]}")

    edge_rows = hop1_rows + hop2_rows
    triples = collections.Counter((r["subject_id"], r["predicate"], r["object_id"]) for r in edge_rows)
    dup = sum(1 for v in triples.values() if v > 1)
    if dup:
        raise SystemExit(f"存在重复三元组 {dup} 个，staging 未去重，拒绝输出")

    edge_rows.sort(key=lambda r: (r["predicate"], r["subject_id"], r["object_id"]))
    with (PROCESSED / "edges.csv").open("w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=EDGE_COLUMNS)
        w.writeheader()
        for r in edge_rows:
            w.writerow({k: r[k] for k in EDGE_COLUMNS})

    with (PROCESSED / "nodes.csv").open("w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=NODE_COLUMNS)
        w.writeheader()
        for nid in sorted(node_rows):
            w.writerow({k: node_rows[nid][k] for k in NODE_COLUMNS})

    label_count = collections.Counter(r["label"] for r in node_rows.values())
    pred_count = collections.Counter(r["predicate"] for r in edge_rows)
    report = {
        "generated_at": now_iso(),
        "seeds": sorted(seeds),
        "hop1_edges": len(hop1_rows),
        "hop2_edges": len(hop2_rows),
        "hop1_genes": len(hop1_genes),
        "hop1_drugs": len(hop1_drugs),
        "go_root_edges_dropped": go_root_dropped,
        "nodes": len(node_rows),
        "node_labels": dict(sorted(label_count.items())),
        "edges": len(edge_rows),
        "predicates": dict(sorted(pred_count.items())),
    }
    (PROCESSED / "extract_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    commit = git_commit()
    build_manifest = {
        "build_id": f"hematology-kg-v1-{datetime.now().strftime('%Y%m%d')}",
        "build_date": datetime.now().date().isoformat(),
        "sources": load_source_versions(),
        "node_count": len(node_rows),
        "edge_count": len(edge_rows),
        "disease_count": label_count.get("Disease", 0),
        "git_commit": commit,
    }
    if commit is None:
        build_manifest["git_commit_note"] = (
            "当前工作树无 git 提交（git rev-parse HEAD 不可用，不伪造版本号）；"
            "以 build_id 与 data/raw/manifest.json 记录的数据源版本追溯"
        )
    (PROCESSED / "build_manifest.json").write_text(
        json.dumps(build_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    print("完成：")
    print("  nodes.csv:", len(node_rows), dict(label_count))
    print("  edges.csv:", len(edge_rows))
    print("  谓词:", dict(pred_count))
    print("  hop1/hop2 边:", len(hop1_rows), "/", len(hop2_rows))
    print("  GO 根节点边剔除:", go_root_dropped)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
