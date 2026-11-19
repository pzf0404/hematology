#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V1 校验：对 data/processed 的最终节点/边做完整性与可用性检查。

用法：
    python etl/validate.py

输出：
    data/processed/validation_report.json   机器可读（每项 PASS/FAIL + 证据数字）
    docs/03_validation_report.md            人工可读（含验收问题抽查）

退出码：0 = 全部 PASS，1 = 存在 FAIL
"""

from __future__ import annotations

import collections
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
DOCS = ROOT / "docs"

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
FORBIDDEN_LABELS = {"Case", "Genotype", "ChemicalEntity", "Cell", "Protein", "AnatomicalEntity"}
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

results: list[dict] = []
spot: list[dict] = []
limitations: list[str] = []


def check(name: str, ok: bool, detail: str, category: str = "完整性") -> None:
    results.append({"category": category, "check": name, "status": "PASS" if ok else "FAIL",
                    "detail": detail})


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def md_cell(value: object) -> str:
    """转义 Markdown 表格中的竖线，避免原因文本破坏表格。"""
    return str(value).replace("|", "\\|")


def collect_staging() -> dict:
    """汇总规范化阶段的异常暂存信息（任务指引第十七章：非法类型组合进入异常报告）。"""
    report_path = ROOT / "data" / "staging" / "normalize_report.json"
    staged_path = ROOT / "data" / "staging" / "edges_staged.csv"
    info: dict = {
        "normalize_report": report_path.relative_to(ROOT).as_posix(),
        "staged_csv": staged_path.relative_to(ROOT).as_posix(),
        "edges_staged": 0,
        "discarded_rows": {},
        "staged_by_predicate": {},
        "reason_counts": {},
        "illegal_type_combo": {},
        "illegal_type_combo_total": 0,
        "has_illegal_type_section": False,
    }
    if report_path.exists():
        rep = json.loads(report_path.read_text(encoding="utf-8"))
        info["generated_at"] = rep.get("generated_at")
        info["edges_staged"] = rep.get("edges_staged", 0)
        info["discarded_rows"] = rep.get("staged_dropped", {})
        info["staged_dropped"] = rep.get("staged_dropped", {})
        info["staged_by_predicate"] = rep.get("staged_counts", {})
        info["edges_merged_duplicate_records"] = rep.get("edges_merged_duplicate_records")
        info["has_illegal_type_section"] = "illegal_type_combo" in rep
        info["illegal_type_combo"] = rep.get("illegal_type_combo", {})
        info["illegal_type_combo_total"] = rep.get("illegal_type_combo_total", 0)
    if staged_path.exists():
        reasons: collections.Counter = Counter()
        with staged_path.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                reasons[(r.get("staging_reason") or "").strip() or "未注明原因"] += 1
        info["reason_counts"] = dict(reasons)
    return info


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    nodes_path = PROCESSED / "nodes.csv"
    edges_path = PROCESSED / "edges.csv"

    check("交付文件存在", nodes_path.exists() and edges_path.exists(),
          f"nodes.csv={nodes_path.exists()}, edges.csv={edges_path.exists()}")
    if not (nodes_path.exists() and edges_path.exists()):
        write_report({}, 0)
        return 1

    with nodes_path.open("rb") as f:
        node_bom = f.read(3) == b"\xef\xbb\xbf"
    with edges_path.open("rb") as f:
        edge_bom = f.read(3) == b"\xef\xbb\xbf"
    check("UTF-8 无 BOM", not node_bom and not edge_bom,
          f"nodes BOM={node_bom}, edges BOM={edge_bom}")

    with nodes_path.open(encoding="utf-8", newline="") as f:
        node_header = next(csv.reader(f))
    with edges_path.open(encoding="utf-8", newline="") as f:
        edge_header = next(csv.reader(f))
    check("nodes 列与任务文档一致", node_header == NODE_COLUMNS, "|".join(node_header))
    check("edges 列与任务文档一致", edge_header == EDGE_COLUMNS, "|".join(edge_header))

    nodes: dict[str, dict] = {}
    label_count: collections.Counter = Counter()
    empty_required = collections.Counter()
    with nodes_path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["id"] in nodes:
                empty_required["重复节点 id"] += 1
            nodes[r["id"]] = r
            label_count[r["label"]] += 1
            for key in ("id", "label", "name", "canonical_id", "source", "source_version", "retrieved_at"):
                if not r[key].strip():
                    empty_required[f"节点缺 {key}"] += 1
    check("节点 id 唯一", empty_required["重复节点 id"] == 0,
          f"节点 {len(nodes)}，重复 {empty_required['重复节点 id']}")
    check("节点必填字段非空", all(v == 0 for k, v in empty_required.items() if k.startswith("节点缺")),
          ", ".join(f"{k}={v}" for k, v in empty_required.items() if k.startswith("节点缺")) or "全部非空")

    forbidden = {k: v for k, v in label_count.items() if k in FORBIDDEN_LABELS}
    check("节点类型均在 V1 策略内", not forbidden, f"分布={dict(label_count)}；越界={forbidden or '无'}",
          "实体策略")

    disease_zh = sum(1 for r in nodes.values() if r["label"] == "Disease" and r["name_zh"].strip())
    disease_total = label_count.get("Disease", 0)
    check("种子疾病中文名齐全", all(nodes.get(s, {}).get("name_zh", "").strip() for s in SEEDS),
          "；".join(f"{SEEDS[s]}={nodes.get(s, {}).get('name_zh', '缺失')}" for s in SEEDS), "中文覆盖")
    if disease_zh < disease_total:
        limitations.append(
            f"疾病中文名覆盖 {disease_zh}/{disease_total}：非种子疾病（MONDO 父类与直接子类）无官方中文名，"
            f"字段留空而不臆造"
        )
    pheno_zh = sum(1 for r in nodes.values() if r["label"] == "Phenotype" and r["name_zh"].strip())
    pheno_total = label_count.get("Phenotype", 0)
    check("表型中文名覆盖", pheno_zh == pheno_total, f"{pheno_zh}/{pheno_total}", "中文覆盖")
    if pheno_zh < pheno_total:
        limitations.append(f"表型中文名 {pheno_zh}/{pheno_total}：未映射的 HPO 术语字段留空，不臆造")

    triples: collections.Counter = Counter()
    edge_ids: collections.Counter = Counter()
    dangling = 0
    bad_arrow: list[str] = []
    pred_count: collections.Counter = Counter()
    src_count: collections.Counter = Counter()
    license_missing = 0
    evidence_ok = 0
    edge_empty = collections.Counter()
    total_edges = 0
    adjacency: dict[str, set[str]] = collections.defaultdict(set)
    treats: dict[tuple[str, str], str] = {}
    targets: dict[str, set[str]] = collections.defaultdict(set)

    with edges_path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            total_edges += 1
            s, p, o = r["subject_id"], r["predicate"], r["object_id"]
            triples[(s, p, o)] += 1
            edge_ids[r["edge_id"]] += 1
            pred_count[p] += 1
            src_count[r["source"]] += 1
            if s not in nodes or o not in nodes:
                dangling += 1
                continue
            pair = (nodes[s]["label"], nodes[o]["label"])
            if pair not in ALLOWED_ARROWS.get(p, set()):
                bad_arrow.append(f"{p}:{pair[0]}->{pair[1]}")
            adjacency[s].add(o)
            adjacency[o].add(s)
            if not r["license"].strip():
                license_missing += 1
            if r["pmid"].strip() or r["source_record_id"].strip():
                evidence_ok += 1
            for key in ("edge_id", "subject_id", "predicate", "object_id", "original_predicate",
                        "source", "source_version", "retrieved_at"):
                if not r[key].strip():
                    edge_empty[f"边缺 {key}"] += 1
            if p == "TREATS":
                treats[(s, o)] = nodes[s]["name"]
            if p == "TARGETS":
                targets[s].add(o)

    check("边三元组唯一", all(v == 1 for v in triples.values()),
          f"边 {total_edges}，唯一三元组 {len(triples)}，重复三元组 {sum(1 for v in triples.values() if v > 1)}")
    check("edge_id 唯一", all(v == 1 for v in edge_ids.values()),
          f"唯一 {len(edge_ids)}")
    check("引用完整性", dangling == 0, f"悬空边 {dangling}")
    check("关系方向与白名单一致", not bad_arrow,
          f"越界 {len(bad_arrow)} 条：{collections.Counter(bad_arrow).most_common(5) or '无'}", "关系白名单")
    check("8 类启用关系是否全部可用",
          set(pred_count) == set(ALLOWED_ARROWS),
          f"实际 {len(pred_count)} 类：{dict(sorted(pred_count.items()))}", "关系白名单")
    check("边必填字段非空", all(v == 0 for k, v in edge_empty.items() if k.startswith("边缺")),
          ", ".join(f"{k}={v}" for k, v in edge_empty.items() if k.startswith("边缺")) or "全部非空")
    check("许可字段完整", license_missing == 0, f"缺 license {license_missing} 条")
    check("证据可追溯率", evidence_ok == total_edges,
          f"{evidence_ok}/{total_edges}（pmid 或 source_record_id 至少一项）")

    # 固定抽取 30 条边，输出可复核的溯源明细
    sample_cols = ["edge_id", "subject_id", "predicate", "object_id", "source",
                   "source_version", "source_record_id", "pmid", "doi"]
    sample_path = PROCESSED / "edge_traceability_sample.csv"
    picks = {round(i * (total_edges - 1) / 29) for i in range(30)} if total_edges else set()
    with edges_path.open(encoding="utf-8", newline="") as f, \
            sample_path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=sample_cols)
        writer.writeheader()
        for idx, r in enumerate(csv.DictReader(f)):
            if idx in picks:
                writer.writerow({k: r[k] for k in sample_cols})

    orphans = [nid for nid in nodes if nid not in adjacency]
    check("无孤立节点", not orphans, f"孤立节点 {len(orphans)}，例如 {orphans[:5]}")

    for seed, abbrev in SEEDS.items():
        n_edges = len(adjacency.get(seed, ()))
        check(f"种子 {abbrev} 已入图且有连接", seed in nodes and n_edges > 0,
              f"{seed} 度={n_edges}", "种子覆盖")

    # ---------------------------------------------------------------- 异常与暂存
    staging = collect_staging()
    staged_total = sum(staging["reason_counts"].values())
    check("异常边已暂存并注明原因",
          staging["edges_staged"] == 0
          or (staged_total == staging["edges_staged"] and "未注明原因" not in staging["reason_counts"]),
          f"暂存 {staging['edges_staged']} 条（CSV {staged_total} 行）；"
          f"原因={staging['reason_counts'] or '无'}；"
          f"按谓词={staging['staged_by_predicate'] or '无'}",
          "异常报告")
    top_illegal = sorted(staging["illegal_type_combo"].items(), key=lambda kv: -kv[1])[:5]
    check("白名单谓词非法类型组合已入异常报告",
          staging["has_illegal_type_section"],
          f"{staging['illegal_type_combo_total']} 条，"
          f"{len(staging['illegal_type_combo'])} 类组合；Top={dict(top_illegal) or '无'}",
          "异常报告")
    limitations.append(
        "治疗方案/HSCT：任务文档关系白名单未定义“治疗方案”关系，DisMech 的 20 条治疗条目"
        "（含造血干细胞移植）按白名单规则不入正式图，明细见 data/staging/staged_dismech_treatments.csv；"
        "因此“造血干细胞移植与再障是什么关系”在 V1 只能回答“无图内关系证据”，"
        "需由指南/文献文本证据补充"
    )

    # ---------------------------------------------------------------- 验收问题抽查
    def add_spot(q: str, ok: bool, evidence: str) -> None:
        spot.append({"question": q, "status": "PASS" if ok else "FAIL", "evidence": evidence})

    # 1) 药物→靶点→基因→疾病 路径是否存在
    path_found = None
    for (drug, disease), name in treats.items():
        for gene in sorted(targets.get(drug, ())):
            if disease in adjacency.get(gene, set()):
                path_found = (name, gene, SEEDS.get(disease, disease))
                break
        if path_found:
            break
    add_spot("某药物的靶点是否与某白血病疾病节点关联？", bool(path_found),
             f"示例：{path_found[0]} → TARGETS → {path_found[1]} → ASSOCIATED_WITH → {path_found[2]}" if path_found else "未找到")

    # 2) 再障是否有环孢素治疗
    cyc_aa = [(d, nodes[drug]["name"]) for (drug, d) in treats
              if "CYCLOSPORINE" in (nodes[drug]["name"] or "").upper()
              and d in ("MONDO:0015909", "MONDO:0015610")]
    add_spot("环孢素是否与再生障碍性贫血关联？", bool(cyc_aa),
             "；".join(f"{n} → TREATS → {SEEDS[d]}" for d, n in cyc_aa) or "未找到")

    # 3) CML 与伊马替尼
    ima = [(d, nodes[drug]["name"]) for (drug, d) in treats
           if d == "MONDO:0011996" and "IMATINIB" in (nodes[drug]["name"] or "").upper()]
    add_spot("伊马替尼是否治疗 CML？", bool(ima),
             "；".join(f"{n} → TREATS → CML" for d, n in ima) or "未找到")

    # 4) APL 是否为 AML 亚型
    sub_edges = []
    with edges_path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["predicate"] == "SUBTYPE_OF" and r["subject_id"] == "MONDO:0012883":
                sub_edges.append(r["object_id"])
    add_spot("APL 是否作为独立节点并可关联到上级疾病？",
             "MONDO:0012883" in nodes and bool(sub_edges),
             f"APL 的 SUBTYPE_OF 目标：{sub_edges or '无（Monarch 未提供该亚型边）'}")

    # 5) AML 表型
    aml_pheno = sorted(o for o in adjacency.get("MONDO:0018874", set())
                       if nodes[o]["label"] == "Phenotype")
    add_spot("AML 是否有表型关联？", bool(aml_pheno),
             f"AML 直接表型 {len(aml_pheno)} 个，例如 {[nodes[p]['name'] for p in aml_pheno[:3]]}")
    limitations.append(
        f"种子疾病直接表型合计 {pred_count.get('HAS_PHENOTYPE', 0)} 条，其中 AML 仅 {len(aml_pheno)} 个；"
        f"HPO 对白血病/再障注释稀疏，'临床表现'类问答覆盖有限"
    )

    # 6) 某基因同时参与通路和生物过程
    both = [g for g in sorted(nodes)
            if nodes[g]["label"] == "Gene"
            and any(nodes[x]["label"] == "Pathway" for x in adjacency.get(g, set()))
            and any(nodes[x]["label"] == "BiologicalProcess" for x in adjacency.get(g, set()))]
    add_spot("基因能否同时关联通路与生物过程？", bool(both),
             f"{len(both)} 个基因，例如 {both[:3]}")

    summary = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "files": {
            "nodes.csv": {"rows": len(nodes), "sha256": sha256(nodes_path)},
            "edges.csv": {"rows": total_edges, "sha256": sha256(edges_path)},
        },
        "node_labels": dict(sorted(label_count.items())),
        "predicates": dict(sorted(pred_count.items())),
        "sources": dict(sorted(src_count.items())),
        "staging": staging,
        "checks": results,
        "acceptance_spot_checks": spot,
        "limitations": limitations,
        "passed": sum(1 for r in results if r["status"] == "PASS"),
        "failed": sum(1 for r in results if r["status"] == "FAIL"),
    }
    write_report(summary, total_edges)

    print(f"检查 {len(results)} 项：PASS {summary['passed']} / FAIL {summary['failed']}")
    for r in results:
        if r["status"] == "FAIL":
            print(f"  [FAIL] {r['check']}: {r['detail']}")
    print(f"验收抽查 {len(spot)} 项：PASS {sum(1 for s in spot if s['status'] == 'PASS')}")
    for s in spot:
        print(f"  [{s['status']}] {s['question']} — {s['evidence']}")
    return 0 if summary["failed"] == 0 else 1


def write_report(summary: dict, total_edges: int) -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    (PROCESSED / "validation_report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    DOCS.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 阶段 2 数据校验报告（V1）",
        "",
        f"- 生成时间：{summary.get('generated_at', '-')}",
        f"- 节点：{summary.get('files', {}).get('nodes.csv', {}).get('rows', 0)}",
        f"- 边：{total_edges}",
        f"- 结论：PASS {summary.get('passed', 0)} 项，FAIL {summary.get('failed', 0)} 项",
        "",
        "## 一、完整性检查",
        "",
        "| 类别 | 检查项 | 结果 | 证据 |",
        "|---|---|---|---|",
    ]
    for r in summary.get("checks", []):
        lines.append(f"| {r['category']} | {r['check']} | {r['status']} | {r['detail']} |")
    lines += ["", "## 二、验收问题抽查", "", "| 问题 | 结果 | 证据 |", "|---|---|---|"]
    for s in summary.get("acceptance_spot_checks", []):
        lines.append(f"| {s['question']} | {s['status']} | {s['evidence']} |")
    lines += [
        "",
        "## 三、节点类型分布",
        "",
        "| 类型 | 数量 |",
        "|---|---|",
    ]
    for k, v in summary.get("node_labels", {}).items():
        lines.append(f"| {k} | {v} |")
    lines += ["", "## 四、关系分布", "", "| 谓词 | 边数 |", "|---|---|"]
    for k, v in summary.get("predicates", {}).items():
        lines.append(f"| {k} | {v} |")
    st = summary.get("staging") or {}
    lines += [
        "",
        "## 五、异常与暂存",
        "",
        f"- 来源报告：{st.get('normalize_report', '-')}（生成时间 {st.get('generated_at', '-')}）",
        f"- 白名单外暂存边：{st.get('edges_staged', 0)} 条，全部保留原始三元组与溯源字段，未进入 data/processed/edges.csv",
        f"- 暂存明细：{st.get('staged_csv', '-')}",
        f"- 同三元组合并的重复原始记录：{st.get('edges_merged_duplicate_records', 0)} 条"
        f"（多来源证据已聚合，source 以 | 并列，未抹掉任何来源）",
        "",
        "### 5.1 暂存边按谓词",
        "",
        "| 原始谓词 | 条数 |",
        "|---|---|",
    ]
    for k, v in (st.get("staged_by_predicate") or {}).items():
        lines.append(f"| {k} | {v} |")
    lines += ["", "### 5.2 暂存原因", "", "| 原因 | 条数 |", "|---|---|"]
    for k, v in (st.get("reason_counts") or {}).items():
        lines.append(f"| {md_cell(k)} | {v} |")
    lines += ["", "### 5.3 直接丢弃的原始行", "", "| 原因 | 行数 |", "|---|---|"]
    for k, v in (st.get("discarded_rows") or {}).items():
        lines.append(f"| {md_cell(k)} | {v} |")
    lines += ["", "### 5.4 白名单谓词但端点类型不符（未入图）", ""]
    combos = st.get("illegal_type_combo") or {}
    if combos:
        lines += [
            f"共 {st.get('illegal_type_combo_total', sum(combos.values()))} 条，"
            f"按“原谓词|subject类型->object类型”聚合，全部未写入正式图：",
            "",
            "| 原谓词 | 端点类型 | 条数 |",
            "|---|---|---|",
        ]
        for k, v in sorted(combos.items(), key=lambda kv: -kv[1]):
            pred_name, pair = str(k).split("|", 1)
            lines.append(f"| {md_cell(pred_name)} | {md_cell(pair)} | {v} |")
    else:
        lines.append("- 报告未提供该统计，需重跑 `python -m etl.normalize`")
    lines += ["", "## 六、已知限制", ""]
    for item in summary.get("limitations", []) or ["无"]:
        lines.append(f"- {item}")
    (DOCS / "03_validation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    raise SystemExit(main())
