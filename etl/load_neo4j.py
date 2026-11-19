#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 data/processed 的 nodes.csv / edges.csv 幂等导入 Neo4j，并做导入后核验（阶段 3）。

依据：任务指引 十一、Neo4j 导入与索引
- 约束/索引：cypher/schema.cypher
- 幂等：节点 MERGE on id；关系 MERGE on edge_id，重复执行不产生重复
- 核验：图内节点/关系总数与分类型计数逐项对比 CSV 实测值
- 记录：Neo4j 版本、导入脚本版本、源文件 SHA256、耗时、缺失端点统计

用法：
    python -m etl.load_neo4j                # 建约束 → 导入 → 核验 → 写报告
    python -m etl.load_neo4j --verify-only  # 只核验，不写数据
    python -m etl.load_neo4j --dry-run      # 只统计 CSV，不连 Neo4j

依赖：pip install "neo4j>=5,<7"
环境变量：NEO4J_PASSWORD（除 --dry-run 外必填）
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
NODES_CSV = PROCESSED / "nodes.csv"
EDGES_CSV = PROCESSED / "edges.csv"
SCHEMA_FILE = ROOT / "cypher" / "schema.cypher"
REPORT_FILE = PROCESSED / "neo4j_import_report.json"

IMPORT_SCRIPT_VERSION = "1.0.0"


def data_build_id() -> str:
    """优先沿用 build_manifest.json 的 build_id（数据版本），缺失时回退到当日日期。"""
    manifest = PROCESSED / "build_manifest.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("build_id"):
            return data["build_id"]
    except (OSError, json.JSONDecodeError):
        pass
    return f"hematology-kg-v1-{datetime.now().strftime('%Y%m%d')}"

# 与 config/relation_allowlist.yaml、阶段2 冻结产物一致；出现白名单外的值直接报错
NODE_LABELS = ("Disease", "Gene", "Variant", "Phenotype", "Drug", "Pathway", "BiologicalProcess")
EDGE_TYPES = ("HAS_PHENOTYPE", "ASSOCIATED_WITH", "AFFECTS", "TREATS", "TARGETS",
              "PARTICIPATES_IN", "INVOLVED_IN", "SUBTYPE_OF")

# 不写入关系属性的列：subject_id / object_id 已由图结构表达
EDGE_SKIP_COLUMNS = {"subject_id", "object_id"}


def log(msg: str) -> None:
    print(msg, flush=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def count_csv() -> dict:
    """只读统计 CSV，作为导入后的对比基线。"""
    labels: Counter = Counter()
    predicates: Counter = Counter()
    node_total = 0
    edge_total = 0

    with NODES_CSV.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            label = row["label"]
            if label not in NODE_LABELS:
                raise RuntimeError(f"nodes.csv 出现白名单外 label={label!r}, id={row['id']}")
            labels[label] += 1
            node_total += 1

    with EDGES_CSV.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            predicate = row["predicate"]
            if predicate not in EDGE_TYPES:
                raise RuntimeError(f"edges.csv 出现白名单外 predicate={predicate!r}, edge_id={row['edge_id']}")
            predicates[predicate] += 1
            edge_total += 1

    return {
        "nodes": node_total,
        "node_labels": dict(sorted(labels.items())),
        "edges": edge_total,
        "edge_types": dict(sorted(predicates.items())),
    }


def node_props(row: dict) -> dict:
    props = {k: v for k, v in row.items() if v not in ("", None)}
    # nodes.csv 无 symbol 列；HGNC 的 name 即官方 symbol，派生后满足文档要求的 Gene(symbol) 索引
    if row["label"] == "Gene" and row.get("name"):
        props["symbol"] = row["name"]
    return props


def edge_props(row: dict) -> dict:
    props = {k: v for k, v in row.items()
             if k not in EDGE_SKIP_COLUMNS and v not in ("", None)}
    if "evidence_score" in props:
        try:
            props["evidence_score"] = float(props["evidence_score"])
        except ValueError:
            props.pop("evidence_score")
    return props


def schema_statements() -> list[str]:
    text = SCHEMA_FILE.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("//")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def flush_nodes(tx, label: str, rows: list[dict]) -> int:
    query = (
        "UNWIND $rows AS row "
        "MERGE (n:Entity {id: row.id}) "
        "SET n += row.props "
        f"SET n:`{label}` "
        "RETURN count(*) AS n"
    )
    result = tx.run(query, rows=rows)
    result.single()
    # 只统计本次真正新建的节点；重复导入时为 0，避免把 MERGE 命中行误报成写入。
    return result.consume().counters.nodes_created


def flush_edges(tx, rel_type: str, rows: list[dict]) -> tuple[int, int]:
    query = (
        "UNWIND $rows AS row "
        "MATCH (s:Entity {id: row.subject_id}) "
        "MATCH (o:Entity {id: row.object_id}) "
        f"MERGE (s)-[r:`{rel_type}` {{edge_id: row.edge_id}}]->(o) "
        "SET r += row.props "
        "RETURN count(*) AS n"
    )
    result = tx.run(query, rows=rows)
    record = result.single()
    matched = int(record["n"]) if record else 0
    created = result.consume().counters.relationships_created
    return matched, created


def import_nodes(session, batch_size: int) -> dict:
    buffers: dict[str, list[dict]] = {label: [] for label in NODE_LABELS}
    written: Counter = Counter()
    total = 0
    with NODES_CSV.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            label = row["label"]
            buffers[label].append({"id": row["id"], "props": node_props(row)})
            total += 1
            if len(buffers[label]) >= batch_size:
                created = session.execute_write(flush_nodes, label, buffers[label])
                written[label] += created
                buffers[label] = []
                if created:
                    log(f"  节点 {label}: 新建累计 {written[label]}")
    for label, rows in buffers.items():
        if rows:
            created = session.execute_write(flush_nodes, label, rows)
            written[label] += created
            if created:
                log(f"  节点 {label}: 新建累计 {written[label]}")
    log(f"节点导入完成 {total} 行（本次新建 {sum(written.values())}）")
    return dict(written)


def import_edges(session, batch_size: int) -> tuple[dict, int]:
    buffers: dict[str, list[dict]] = {t: [] for t in EDGE_TYPES}
    written: Counter = Counter()
    missing = 0
    total = 0
    with EDGES_CSV.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            rel_type = row["predicate"]
            buffers[rel_type].append({
                "edge_id": row["edge_id"],
                "subject_id": row["subject_id"],
                "object_id": row["object_id"],
                "props": edge_props(row),
            })
            total += 1
            if len(buffers[rel_type]) >= batch_size:
                matched, created = session.execute_write(flush_edges, rel_type, buffers[rel_type])
                missing += len(buffers[rel_type]) - matched
                written[rel_type] += created
                buffers[rel_type] = []
                if created:
                    log(f"  关系 {rel_type}: 新建累计 {written[rel_type]}")
    for rel_type, rows in buffers.items():
        if rows:
            matched, created = session.execute_write(flush_edges, rel_type, rows)
            missing += len(rows) - matched
            written[rel_type] += created
            if created:
                log(f"  关系 {rel_type}: 新建累计 {written[rel_type]}")
    log(f"关系导入完成 {total} 行，缺失端点 {missing} 行（本次新建 {sum(written.values())}）")
    return dict(written), missing


def verify(session, expected: dict) -> dict:
    actual_nodes = session.run("MATCH (n:Entity) RETURN count(*) AS c").single()["c"]
    actual_labels = {}
    for label in NODE_LABELS:
        actual_labels[label] = session.run(
            f"MATCH (n:`{label}`) RETURN count(*) AS c").single()["c"]

    actual_edges = session.run("MATCH ()-[r]->() RETURN count(*) AS c").single()["c"]
    actual_types = {r["t"]: r["c"] for r in session.run(
        "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c")}

    mismatches = []
    if actual_nodes != expected["nodes"]:
        mismatches.append(f"节点总数 期望 {expected['nodes']} 实际 {actual_nodes}")
    for label, want in expected["node_labels"].items():
        got = actual_labels.get(label, 0)
        if got != want:
            mismatches.append(f"节点 {label} 期望 {want} 实际 {got}")
    if actual_edges != expected["edges"]:
        mismatches.append(f"关系总数 期望 {expected['edges']} 实际 {actual_edges}")
    for rel_type, want in expected["edge_types"].items():
        got = actual_types.get(rel_type, 0)
        if got != want:
            mismatches.append(f"关系 {rel_type} 期望 {want} 实际 {got}")
    extra_labels = set(actual_labels) - set(expected["node_labels"])
    extra_types = set(actual_types) - set(expected["edge_types"])
    if extra_labels:
        mismatches.append(f"多出节点标签 {sorted(extra_labels)}")
    if extra_types:
        mismatches.append(f"多出关系类型 {sorted(extra_types)}")

    isolated = session.run(
        "MATCH (n:Entity) WHERE NOT (n)--() RETURN count(*) AS c").single()["c"]

    return {
        "nodes": actual_nodes,
        "node_labels": actual_labels,
        "edges": actual_edges,
        "edge_types": actual_types,
        "isolated_nodes": isolated,
        "mismatches": mismatches,
    }


def graph_meta(session) -> dict:
    components = session.run(
        "CALL dbms.components() YIELD name, versions, edition "
        "RETURN name, versions, edition ORDER BY name").data()
    constraints = session.run(
        "SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties "
        "RETURN name, type, labelsOrTypes, properties ORDER BY name").data()
    indexes = session.run(
        "SHOW INDEXES YIELD name, type, labelsOrTypes, properties, state "
        "RETURN name, type, labelsOrTypes, properties, state ORDER BY name").data()
    return {"components": components, "constraints": constraints, "indexes": indexes}


def write_report(report: dict) -> None:
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"报告已写入 {REPORT_FILE}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Neo4j 幂等导入与核验")
    parser.add_argument("--uri", default=os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687"))
    parser.add_argument("--user", default=os.environ.get("NEO4J_USER", "neo4j"))
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--verify-only", action="store_true", help="只核验，不写入")
    parser.add_argument("--dry-run", action="store_true", help="只统计 CSV，不连接 Neo4j")
    parser.add_argument("--report", default=str(REPORT_FILE))
    args = parser.parse_args()

    started = time.time()
    expected = count_csv()
    log(f"CSV 基线：节点 {expected['nodes']}，关系 {expected['edges']}")
    log(f"  节点分布 {expected['node_labels']}")
    log(f"  关系分布 {expected['edge_types']}")

    if args.dry_run:
        log("--dry-run：仅统计，未连接 Neo4j")
        return 0

    password = os.environ.get("NEO4J_PASSWORD", "")
    if not password:
        log("错误：未设置 NEO4J_PASSWORD 环境变量")
        return 2

    try:
        from neo4j import GraphDatabase
    except ImportError:
        log('错误：缺少 neo4j 驱动，请先执行 pip install "neo4j>=5,<7"')
        return 2

    report = {
        "build_id": data_build_id(),
        "imported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "neo4j_uri": args.uri,
        "import_script": "etl/load_neo4j.py",
        "import_script_version": IMPORT_SCRIPT_VERSION,
        "source_files": {
            "nodes_csv_sha256": sha256(NODES_CSV),
            "edges_csv_sha256": sha256(EDGES_CSV),
        },
        "expected": expected,
    }

    driver = GraphDatabase.driver(args.uri, auth=(args.user, password))
    try:
        driver.verify_connectivity()
        with driver.session() as session:
            meta = graph_meta(session)
            log(f"Neo4j 组件：{meta['components']}")

            if not args.verify_only:
                log("执行约束与索引（cypher/schema.cypher）")
                for stmt in schema_statements():
                    session.run(stmt).consume()

                log("导入节点")
                node_written = import_nodes(session, args.batch_size)
                log("导入关系")
                edge_written, missing = import_edges(session, args.batch_size)
                log(f"本次写入：节点 {sum(node_written.values())}，关系 {sum(edge_written.values())}")
                report["written_this_run"] = {
                    "nodes": sum(node_written.values()),
                    "node_labels": node_written,
                    "edges": sum(edge_written.values()),
                    "edge_types": edge_written,
                    "missing_endpoints": missing,
                }
                meta = graph_meta(session)

            log("核验图内计数")
            verified = verify(session, expected)
            report["neo4j"] = meta
            report["actual"] = verified
            report["duration_seconds"] = round(time.time() - started, 1)
            report["status"] = "PASS" if not verified["mismatches"] else "FAIL"

            log(f"图内：节点 {verified['nodes']}，关系 {verified['edges']}，孤立节点 {verified['isolated_nodes']}")
            if verified["mismatches"]:
                for item in verified["mismatches"]:
                    log(f"  FAIL {item}")
            else:
                log("计数核验 PASS：与 CSV 基线逐项一致")
            write_report(report)
            return 0 if report["status"] == "PASS" else 1
    except Exception as exc:  # 连接失败等给出可读原因，而不是裸堆栈
        log(f"导入失败：{type(exc).__name__}: {exc}")
        log("排查：1) 容器是否 healthy  2) NEO4J_PASSWORD 是否与 .env 一致  3) bolt 是否绑定 127.0.0.1:7687")
        return 1
    finally:
        driver.close()


if __name__ == "__main__":
    sys.exit(main())
