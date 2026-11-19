#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V1 标准化：把 4 个原始数据源转成统一节点/边，写入 data/staging。

用法：
    python etl/normalize.py

输入（只读）：
    data/raw/monarch-kg/2026-11-11/monarch-kg.tar.gz
    data/raw/open-targets/26.09/*.json
    data/raw/dismech/<commit>/*.yaml
    config/disease_seeds.yaml, entity_mapping.yaml, relation_allowlist.yaml
    data/raw/manifest.json

输出：
    data/staging/nodes.csv                  统一节点（列严格等于任务文档）
    data/staging/edges.csv                  正式边（列严格等于任务文档）
    data/staging/edges_staged.csv           非白名单但需留证的种子邻接边（+staging_reason）
    data/staging/phenotype_candidates.csv
    data/staging/staged_dismech_treatments.csv
    data/staging/normalize_report.json

约束：
- 幂等：重复运行覆盖同一批输出
- 去重：subject_id+predicate+object_id 唯一；多来源证据合并进同一行，不丢来源
- 不伪造：缺失字段留空并计数
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
import sys
import tarfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
STAGING = ROOT / "data" / "staging"
MANIFEST = RAW / "manifest.json"

MONARCH_TAR = RAW / "monarch-kg" / "2026-11-11" / "monarch-kg.tar.gz"
MONARCH_VERSION = "2026-11-11"
OT_DIR = RAW / "open-targets" / "26.09"
OT_VERSION = "26.09"
DISMECH_REF = "38c23e10b0285becf70a0416fdb267698dfd20fe"

HUMAN_TAXON = "NCBITaxon:9606"

NODE_COLUMNS = [
    "id", "label", "name", "name_zh", "canonical_id", "synonyms", "source_ids",
    "xrefs", "description", "source", "source_version", "retrieved_at",
]
EDGE_COLUMNS = [
    "edge_id", "subject_id", "predicate", "object_id", "original_predicate",
    "source", "source_dataset", "source_version", "source_record_id",
    "evidence_score", "pmid", "doi", "license", "retrieved_at",
]
STAGED_COLUMNS = EDGE_COLUMNS + ["staging_reason"]

# (original_predicate, relation_key, predicate_out, subject_type, object_type,
#  subject_category, object_category, object_id_prefix)
MONARCH_RULES = [
    ("biolink:has_phenotype", "disease_has_phenotype", "HAS_PHENOTYPE",
     "Disease", "Phenotype", "biolink:Disease", "biolink:PhenotypicFeature", "HP"),
    ("biolink:gene_associated_with_condition", "gene_associated_with_disease", "ASSOCIATED_WITH",
     "Gene", "Disease", "biolink:Gene", "biolink:Disease", "MONDO"),
    ("biolink:causes", "gene_associated_with_disease", "ASSOCIATED_WITH",
     "Gene", "Disease", "biolink:Gene", "biolink:Disease", "MONDO"),
    ("biolink:associated_with_increased_likelihood_of", "gene_associated_with_disease", "ASSOCIATED_WITH",
     "Gene", "Disease", "biolink:Gene", "biolink:Disease", "MONDO"),
    ("biolink:is_sequence_variant_of", "variant_affects_gene", "AFFECTS",
     "Variant", "Gene", "biolink:SequenceVariant", "biolink:Gene", None),
    ("biolink:participates_in", "gene_participates_in_pathway", "PARTICIPATES_IN",
     "Gene", "Pathway", "biolink:Gene", "biolink:Pathway", "Reactome"),
    ("biolink:actively_involved_in", "gene_involved_in_biological_process", "INVOLVED_IN",
     "Gene", "BiologicalProcess", "biolink:Gene", "biolink:BiologicalProcess", "GO"),
    ("biolink:subclass_of", "disease_subtype_of_disease", "SUBTYPE_OF",
     "Disease", "Disease", "biolink:Disease", "biolink:Disease", "MONDO"),
]
RULE_BY_PRED = {r[0]: r for r in MONARCH_RULES}

STAGED_RULES = {
    "biolink:causes",
    "biolink:associated_with_increased_likelihood_of",
    "biolink:genetically_associated_with",
    "biolink:has_phenotype",
    "biolink:model_of",
    "biolink:has_disease",
    "biolink:has_gene",
    "biolink:applied_to_treat",
    "biolink:participates_in",
    "biolink:directly_physically_interacts_with",
    "biolink:expresses",
    "biolink:has_sequence_variant",
}
STAGED_REASON = {
    "biolink:causes": "白名单无 Variant→Disease 箭头",
    "biolink:associated_with_increased_likelihood_of": "白名单无 Variant→Disease 箭头",
    "biolink:genetically_associated_with": "白名单无 Variant→Disease 箭头",
    "biolink:has_phenotype": "白名单仅允许 Disease→Phenotype",
    "biolink:model_of": "Genotype 非 V1 节点类型",
    "biolink:has_disease": "Case 为病例级记录，文档禁止入图",
    "biolink:has_gene": "Case 为病例级记录，文档禁止入图",
    "biolink:applied_to_treat": "CHEBI 药物 ID 未映射到 ChEMBL",
    "biolink:participates_in": "主体类型不属于 Gene/Protein",
    "biolink:directly_physically_interacts_with": "非 Drug→Gene 关系",
    "biolink:expresses": "实体类型不在 V1 节点策略",
    "biolink:has_sequence_variant": "实体类型不在 V1 节点策略",
}

LABEL_BY_CATEGORY = {
    "biolink:Disease": "Disease",
    "biolink:Gene": "Gene",
    "biolink:PhenotypicFeature": "Phenotype",
    "biolink:Pathway": "Pathway",
    "biolink:BiologicalProcess": "BiologicalProcess",
    "biolink:SequenceVariant": "Variant",
    "biolink:ChemicalEntity": "ChemicalEntity",
}
PREFIX_FILTER = {
    "biolink:Disease": ("MONDO",),
    "biolink:Gene": ("HGNC",),
    "biolink:PhenotypicFeature": ("HP",),
    "biolink:Pathway": ("Reactome",),
    "biolink:BiologicalProcess": ("GO",),
    "biolink:SequenceVariant": ("CLINVAR",),
}

OT_DRUG_BY_NAME: dict[str, str] = {}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def clean_list(text: str) -> str:
    if not text:
        return ""
    return "|".join(
        tok.strip().strip("'").strip('"')
        for tok in text.strip("[]").split(",")
        if tok.strip().strip("'").strip('"')
    )


def parse_pmid(text: str) -> str:
    if not text or "PMID" not in text:
        return ""
    out = []
    for tok in text.strip("[]").split(","):
        tok = tok.strip().strip("'").strip('"')
        if tok.startswith("PMID:"):
            out.append(tok.split(":", 1)[1])
    return "|".join(out)


def uniq_join(value: str) -> str:
    if not value:
        return ""
    seen: list[str] = []
    for tok in str(value).split("|"):
        tok = tok.strip()
        if tok and tok not in seen:
            seen.append(tok)
    return "|".join(seen)


def verify_config(allowlist: dict) -> None:
    configured = {}
    for r in allowlist["relations"]:
        for s in r.get("sources") or []:
            if s.get("name") == "Monarch KG":
                configured.setdefault(s["original_predicate"], set()).add(r["key"])
    for pred, key, *_ in MONARCH_RULES:
        if pred not in configured:
            raise SystemExit(f"谓词 {pred} 不在允许名单配置中，拒绝运行")
        if key not in configured[pred]:
            raise SystemExit(f"谓词 {pred} 的关系键 {key} 与配置不一致，拒绝运行")
    print(f"配置校验通过：{len(MONARCH_RULES)} 条 Monarch 谓词规则 ↔ relation_allowlist.yaml")


def load_seeds() -> tuple[dict, dict, dict]:
    seeds_cfg = yaml.safe_load((ROOT / "config" / "disease_seeds.yaml").read_text(encoding="utf-8"))
    mapping = yaml.safe_load((ROOT / "config" / "entity_mapping.yaml").read_text(encoding="utf-8"))
    in_graph = {d["canonical_id"]: d for d in mapping["diseases"] if d.get("in_graph") and d.get("canonical_id")}
    zh = {}
    for group in ("leukemia", "aplastic_anemia"):
        for d in seeds_cfg[group]["diseases"]:
            if not d.get("canonical_id"):
                continue
            aliases = list(d.get("synonyms") or []) + list(d.get("aliases") or [])
            if d.get("abbrev"):
                aliases.append(d["abbrev"])
            zh[d["canonical_id"]] = {"name_zh": d.get("name_zh") or "", "synonyms": aliases}
    return in_graph, zh, dict(mapping.get("phenotype_name_zh") or {})


def load_versions() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    return {
        s["name"]: {
            "version": s.get("version"),
            "release_date": s.get("release_date"),
            "retrieved_at": s.get("retrieved_at"),
            "license": s.get("license"),
            "files": s.get("files", []),
        }
        for s in manifest["sources"]
    }


def monarch_nodes():
    meta: dict[str, tuple] = {}
    ensembl_to_hgnc: dict[str, str] = {}
    symbol_to_hgnc: dict[str, str] = {}
    symbol_multi: set[str] = set()
    t = tarfile.open(MONARCH_TAR)
    f = t.extractfile("monarch-kg_nodes.tsv")
    reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace", newline=""), delimiter="\t")
    header = next(reader)
    col = {name: i for i, name in enumerate(header)}

    def pick(row: list[str], name: str) -> str:
        i = col.get(name)
        return row[i] if i is not None and i < len(row) else ""

    scanned = 0
    for p in reader:
        scanned += 1
        nid = pick(p, "id")
        cat = pick(p, "category")
        if cat not in LABEL_BY_CATEGORY:
            continue
        if cat == "biolink:Gene" and pick(p, "in_taxon") != HUMAN_TAXON:
            continue
        prefixes = PREFIX_FILTER.get(cat)
        if prefixes and not nid.startswith(prefixes):
            continue
        xref = clean_list(pick(p, "xref"))
        meta[nid] = (
            LABEL_BY_CATEGORY[cat],
            pick(p, "name"),
            clean_list(pick(p, "synonym")),
            xref,
            pick(p, "description"),
        )
        if cat == "biolink:Gene":
            sym = pick(p, "symbol")
            if sym:
                if sym in symbol_to_hgnc and symbol_to_hgnc[sym] != nid:
                    symbol_multi.add(sym)
                else:
                    symbol_to_hgnc[sym] = nid
            for tok in xref.split("|"):
                if tok.startswith("ENSEMBL:ENSG"):
                    ensembl_to_hgnc.setdefault(tok.split(":", 1)[1], nid)
    f.close()
    for sym in symbol_multi:
        symbol_to_hgnc.pop(sym, None)
    print(f"节点表扫描 {scanned} 行；纳入索引 {len(meta)}；Ensembl 映射 {len(ensembl_to_hgnc)}；"
          f"符号唯一映射 {len(symbol_to_hgnc)}")
    return meta, ensembl_to_hgnc, symbol_to_hgnc


def init_db(path: Path) -> sqlite3.Connection:
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute(
        """
        CREATE TABLE edges(
            subject_id TEXT, predicate TEXT, object_id TEXT,
            original_predicate TEXT, source TEXT, source_dataset TEXT,
            source_version TEXT, source_record_id TEXT, evidence_score TEXT,
            pmid TEXT, doi TEXT, license TEXT, retrieved_at TEXT,
            status TEXT, staging_reason TEXT,
            PRIMARY KEY(subject_id, predicate, object_id, status)
        )
        """
    )
    return conn


UPSERT = """
INSERT INTO edges(subject_id,predicate,object_id,original_predicate,source,source_dataset,
                  source_version,source_record_id,evidence_score,pmid,doi,license,retrieved_at,
                  status,staging_reason)
VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(subject_id,predicate,object_id,status) DO UPDATE SET
  original_predicate = edges.original_predicate || '|' || excluded.original_predicate,
  source = edges.source || '|' || excluded.source,
  source_dataset = edges.source_dataset || '|' || excluded.source_dataset,
  source_version = edges.source_version || '|' || excluded.source_version,
  source_record_id = edges.source_record_id || '|' || excluded.source_record_id,
  evidence_score = CASE
      WHEN excluded.evidence_score = '' THEN edges.evidence_score
      WHEN edges.evidence_score = '' THEN excluded.evidence_score
      WHEN CAST(excluded.evidence_score AS REAL) > CAST(edges.evidence_score AS REAL)
        THEN excluded.evidence_score
      ELSE edges.evidence_score END,
  pmid = CASE WHEN excluded.pmid = '' THEN edges.pmid
              WHEN edges.pmid = '' THEN excluded.pmid
              ELSE edges.pmid || '|' || excluded.pmid END,
  doi = CASE WHEN excluded.doi = '' THEN edges.doi
             WHEN edges.doi = '' THEN excluded.doi
             ELSE edges.doi || '|' || excluded.doi END,
  license = CASE WHEN excluded.license = '' THEN edges.license
                 WHEN edges.license = '' THEN excluded.license
                 ELSE edges.license || '|' || excluded.license END,
  retrieved_at = MAX(edges.retrieved_at, excluded.retrieved_at),
  staging_reason = CASE WHEN excluded.staging_reason = '' THEN edges.staging_reason
                        ELSE excluded.staging_reason END
"""


def sanitize_record(text: str) -> str:
    return str(text).replace("|", "/")


def upsert(conn: sqlite3.Connection, rec: dict) -> None:
    conn.execute(UPSERT, (
        rec["subject_id"], rec["predicate"], rec["object_id"], rec["original_predicate"],
        rec["source"], rec["source_dataset"], rec["source_version"],
        sanitize_record(rec["source_record_id"]),
        rec["evidence_score"], rec["pmid"], rec["doi"], rec["license"],
        rec["retrieved_at"], rec["status"], rec["staging_reason"],
    ))


def build_ot_drug_index() -> None:
    for path in sorted(OT_DIR.glob("*.json")):
        if path.name == "drug_mechanisms.json":
            continue
        bundle = json.loads(path.read_text(encoding="utf-8"))
        if not bundle.get("in_graph"):
            continue
        for row in bundle["drug_candidates"]["rows"]:
            drug = row.get("drug") or {}
            if drug.get("id", "").startswith("CHEMBL") and drug.get("name"):
                OT_DRUG_BY_NAME.setdefault(drug["name"].upper().strip(), drug["id"])


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    STAGING.mkdir(parents=True, exist_ok=True)

    allowlist = yaml.safe_load((ROOT / "config" / "relation_allowlist.yaml").read_text(encoding="utf-8"))
    verify_config(allowlist)
    seeds, zh, pheno_zh = load_seeds()
    versions = load_versions()
    seed_ids = set(seeds)

    monarch_retrieved = versions.get("Monarch KG", {}).get("retrieved_at") or now_iso()
    ot_retrieved = versions.get("Open Targets", {}).get("retrieved_at") or now_iso()
    dismech_retrieved = versions.get("DisMech", {}).get("retrieved_at") or now_iso()
    monarch_license = versions.get("Monarch KG", {}).get("license") or "未声明统一许可；上游逐源许可保留"
    ot_license = versions.get("Open Targets", {}).get("license") or ""
    dismech_license = versions.get("DisMech", {}).get("license") or "BSD-3-Clause"

    meta, ensembl_to_hgnc, symbol_to_hgnc = monarch_nodes()
    label_of = {nid: v[0] for nid, v in meta.items()}

    created_nodes: dict[str, tuple] = {}
    # 种子兜底：个别种子在 Monarch 节点表中不存在（如 EFO:0006927 重型再障），
    # 用 Open Targets bundle 的 canonical_id/name 建 Disease 节点，避免 missing_metadata 丢节点。
    for sid, cfg in seeds.items():
        if sid not in meta:
            created_nodes.setdefault(sid, (
                "Disease", cfg.get("name") or sid, "", sid, "",
                "Open Targets", OT_VERSION, ot_retrieved,
            ))
    used: set[str] = set()
    report: dict = {
        "generated_at": now_iso(),
        "sources": {"monarch": {"version": MONARCH_VERSION, "edges_scanned": 0}},
        "monarch_drop": Counter(),
        "staged": Counter(),
        "staged_dropped": Counter(),
        "illegal_type_combo": Counter(),
        "ot_gene_mapping": Counter(),
        "dismech": Counter(),
        "missing_metadata": Counter(),
    }
    phenotype_counts: Counter = Counter()
    staged_treatments: list[list[str]] = []

    db_path = STAGING / ".dedupe.sqlite"
    conn = init_db(db_path)
    raw_rows = 0
    ot_rows: list[tuple] = []

    print("\n扫描 Monarch 边表 ...")
    t = tarfile.open(MONARCH_TAR)
    f = t.extractfile("monarch-kg_edges.tsv")
    reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace", newline=""), delimiter="\t")
    header = next(reader)
    ecol = {name: i for i, name in enumerate(header)}
    need = max(ecol[k] for k in ("id", "predicate", "subject", "object", "file_source", "publications"))

    def epick(row: list[str], name: str) -> str:
        i = ecol[name]
        return row[i] if i < len(row) else ""

    batch: list[tuple] = []

    def flush() -> None:
        nonlocal raw_rows
        if batch:
            raw_rows += len(batch)
            conn.executemany(UPSERT, batch)
            batch.clear()

    for p in reader:
        report["sources"]["monarch"]["edges_scanned"] += 1
        if len(p) <= need:
            continue
        pred = epick(p, "predicate")
        s = epick(p, "subject")
        o = epick(p, "object")
        rule = RULE_BY_PRED.get(pred)
        sm = meta.get(s)
        om = meta.get(o)

        if rule:
            _, _key, pred_out, s_type, o_type, _s_req, _o_req, o_prefix = rule
            if not sm or not om:
                report["monarch_drop"]["两端节点不在 V1 索引"] += 1
                continue
            if sm[0] == s_type and om[0] == o_type:
                if o_prefix and not o.startswith(o_prefix):
                    report["monarch_drop"]["object 前缀不符"] += 1
                    continue
                batch.append((
                    s, pred_out, o, pred, "Monarch KG",
                    epick(p, "file_source"), MONARCH_VERSION,
                    epick(p, "id"), "", parse_pmid(epick(p, "publications")),
                    "", monarch_license, monarch_retrieved, "allowed", "",
                ))
                used.add(s)
                used.add(o)
                if pred_out == "HAS_PHENOTYPE":
                    phenotype_counts[o] += 1
                if len(batch) >= 20000:
                    flush()
                continue

            # 白名单谓词但端点类型不符：任务指引第十七章要求进入异常报告，
            # 这里按“原谓词|subject类型->object类型”聚合计数；下方原有的
            # staging 逻辑照常执行，不改变历史行为，也不写正式图。
            report["illegal_type_combo"][f"{pred}|{sm[0]}->{om[0]}"] += 1

        if pred in STAGED_RULES and (s in seed_ids or o in seed_ids):
            if not sm or not om:
                report["staged_dropped"][f"{pred}|{STAGED_REASON.get(pred, '')}"] += 1
                continue
            batch.append((
                s, pred.replace("biolink:", "").upper(), o, pred, "Monarch KG",
                epick(p, "file_source"), MONARCH_VERSION,
                epick(p, "id"), "", parse_pmid(epick(p, "publications")),
                "", monarch_license, monarch_retrieved, "staged", STAGED_REASON.get(pred, ""),
            ))
            used.add(s)
            used.add(o)
            if len(batch) >= 20000:
                flush()
    f.close()
    flush()
    conn.commit()

    # ------------------------------------------------------------ DisMech
    print("处理 DisMech ...")
    for entry in versions["DisMech"]["files"]:
        if not entry.get("in_graph"):
            continue
        path = ROOT / entry["path"]
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        disease_id = (data.get("disease_term") or {}).get("term", {}).get("id")
        if disease_id not in seeds:
            report["dismech"]["疾病 ID 与种子不一致"] += 1
            continue
        fname = path.name

        for i, ph in enumerate(data.get("phenotypes") or []):
            hp = ((ph.get("phenotype_term") or {}).get("term") or {}).get("id")
            if not hp or not hp.startswith("HP") or hp not in meta:
                report["dismech"]["表型无法解析"] += 1
                continue
            rec = f"{fname}#phenotypes[{i}]"
            upsert(conn, {
                "subject_id": disease_id, "predicate": "HAS_PHENOTYPE", "object_id": hp,
                "original_predicate": "dismech:phenotypes", "source": "DisMech",
                "source_dataset": "dismech", "source_version": DISMECH_REF, "source_record_id": rec,
                "evidence_score": "", "pmid": "", "doi": "", "license": dismech_license,
                "retrieved_at": dismech_retrieved, "status": "allowed", "staging_reason": "",
            })
            used.add(disease_id)
            used.add(hp)
            phenotype_counts[hp] += 1

        for i, g in enumerate(data.get("genetic") or []):
            gid = ((g.get("gene_term") or {}).get("term") or {}).get("id")
            gene = gid.replace("hgnc:", "HGNC:") if gid else ""
            if gene not in meta:
                report["dismech"]["基因无法解析（无 ontology ID 或不在人类基因索引）"] += 1
                continue
            rec = f"{fname}#genetic[{i}]"
            upsert(conn, {
                "subject_id": gene, "predicate": "ASSOCIATED_WITH", "object_id": disease_id,
                "original_predicate": "dismech:genetic", "source": "DisMech",
                "source_dataset": "dismech", "source_version": DISMECH_REF, "source_record_id": rec,
                "evidence_score": "", "pmid": "", "doi": "", "license": dismech_license,
                "retrieved_at": dismech_retrieved, "status": "allowed", "staging_reason": "",
            })
            used.add(disease_id)
            used.add(gene)

        for i, ph in enumerate(data.get("pathophysiology") or []):
            genes, bps = [], []
            for g in ph.get("genes") or []:
                gid = (g.get("term") or {}).get("id")
                gene = gid.replace("hgnc:", "HGNC:") if gid else ""
                if gene in meta:
                    genes.append(gene)
            for b in ph.get("biological_processes") or []:
                bid = (b.get("term") or {}).get("id")
                if bid and bid.startswith("GO") and bid in meta:
                    bps.append(bid)
            for gene in genes:
                for bp in bps:
                    rec = f"{fname}#pathophysiology[{i}]"
                    upsert(conn, {
                        "subject_id": gene, "predicate": "INVOLVED_IN", "object_id": bp,
                        "original_predicate": "dismech:pathophysiology", "source": "DisMech",
                        "source_dataset": "dismech", "source_version": DISMECH_REF,
                        "source_record_id": rec, "evidence_score": "", "pmid": "", "doi": "",
                        "license": dismech_license, "retrieved_at": dismech_retrieved,
                        "status": "allowed", "staging_reason": "",
                    })
                    used.add(gene)
                    used.add(bp)
            report["dismech"]["pathophysiology 条目"] += 1

        for i, tr in enumerate(data.get("treatments") or []):
            tt = tr.get("treatment_term") or {}
            agents = tt.get("therapeutic_agent") or []
            if isinstance(agents, dict):
                agents = [agents]
            staged_treatments.append([
                disease_id, tr.get("name") or "", tt.get("preferred_term") or "",
                "|".join((a.get("term") or {}).get("id") or ""
                         for a in agents if isinstance(a, dict)),
                f"{fname}#treatments[{i}]",
            ])
            report["dismech"]["治疗条目"] += 1
            names = [tr.get("name") or ""] + [a.get("preferred_term") or "" for a in agents if isinstance(a, dict)]
            for name in names:
                did = OT_DRUG_BY_NAME.get(name.upper().strip())
                if not did:
                    continue
                ot_rows.append((
                    did, "TREATS", disease_id, "dismech:treatments", "DisMech", "dismech",
                    DISMECH_REF, f"{fname}#treatments[{i}]", "", "", "", dismech_license,
                    dismech_retrieved, "allowed", "",
                ))
                used.add(disease_id)
                used.add(did)
                report["dismech"]["治疗药精确匹配 OT"] += 1
                break

    # ------------------------------------------------------------ Open Targets
    print("处理 Open Targets ...")
    for path in sorted(OT_DIR.glob("*.json")):
        if path.name == "drug_mechanisms.json":
            continue
        bundle = json.loads(path.read_text(encoding="utf-8"))
        if not bundle.get("in_graph"):
            continue
        disease_id = bundle["canonical_id"]
        if disease_id not in seeds:
            report["dismech"]["OT 疾病与种子不一致"] += 1
            continue
        for row in bundle["associated_targets"]["rows"]:
            tg = row["target"]
            ensg = tg["id"]
            hgnc = ensembl_to_hgnc.get(ensg)
            if hgnc:
                report["ot_gene_mapping"]["ensembl 精确命中"] += 1
                gene = hgnc
            else:
                hgnc = symbol_to_hgnc.get(tg.get("approvedSymbol") or "")
                if hgnc:
                    report["ot_gene_mapping"]["symbol 唯一匹配"] += 1
                    gene = hgnc
                else:
                    gene = ensg
                    report["ot_gene_mapping"]["新建 Ensembl 节点"] += 1
                    created_nodes.setdefault(gene, (
                        "Gene", tg.get("approvedSymbol") or ensg, "", f"ENSEMBL:{ensg}",
                        tg.get("approvedName") or "", "Open Targets", OT_VERSION, ot_retrieved,
                    ))
            ot_rows.append((
                gene, "ASSOCIATED_WITH", disease_id, "open_targets:associatedTargets",
                "Open Targets", "open_targets", OT_VERSION, f"{path.stem}/{ensg}",
                "" if row.get("score") is None else str(row.get("score")),
                "", "", ot_license, ot_retrieved, "allowed", "",
            ))
            used.add(disease_id)
            used.add(gene)
        for row in bundle["drug_candidates"]["rows"]:
            drug = row.get("drug") or {}
            did = drug.get("id")
            if not did or not did.startswith("CHEMBL"):
                report["dismech"]["药物 ID 非 ChEMBL"] += 1
                continue
            created_nodes.setdefault(did, (
                "Drug", drug.get("name") or did, "", "", "", "Open Targets", OT_VERSION, ot_retrieved,
            ))
            ot_rows.append((
                did, "TREATS", disease_id, "open_targets:drugAndClinicalCandidates",
                "Open Targets", "open_targets", OT_VERSION,
                f"{path.stem}/{did}/{row.get('maxClinicalStage')}", "",
                "", "", ot_license, ot_retrieved, "allowed", "",
            ))
            used.add(disease_id)
            used.add(did)

    mech = json.loads((OT_DIR / "drug_mechanisms.json").read_text(encoding="utf-8"))["drugs"]
    for did, d in mech.items():
        if did not in created_nodes:
            continue
        for m in ((d.get("mechanismsOfAction") or {}).get("rows") or []):
            for tg in m.get("targets") or []:
                ensg = tg.get("id")
                if not ensg:
                    continue
                hgnc = ensembl_to_hgnc.get(ensg)
                if hgnc:
                    gene = hgnc
                else:
                    gene = symbol_to_hgnc.get(tg.get("approvedSymbol") or "")
                    if not gene:
                        gene = ensg
                        created_nodes.setdefault(gene, (
                            "Gene", tg.get("approvedSymbol") or ensg, "", f"ENSEMBL:{ensg}", "",
                            "Open Targets", OT_VERSION, ot_retrieved,
                        ))
                ot_rows.append((
                    did, "TARGETS", gene, "open_targets:mechanismsOfAction",
                    "Open Targets", "open_targets", OT_VERSION,
                    f"{did}/{m.get('actionType')}/{ensg}", "",
                    "", "", ot_license, ot_retrieved, "allowed", "",
                ))
                used.add(did)
                used.add(gene)

    raw_rows += len(ot_rows)
    conn.executemany(UPSERT, ot_rows)
    conn.commit()

    # ------------------------------------------------------------ 导出边
    print("导出并合并重复三元组 ...")
    label_of.update({nid: v[0] for nid, v in created_nodes.items()})

    counter: Counter = Counter()
    total_allowed = 0
    total_staged = 0
    staged_file = STAGING / "edges_staged.csv"
    with (STAGING / "edges.csv").open("w", encoding="utf-8", newline="\n") as f_out, \
            staged_file.open("w", encoding="utf-8", newline="\n") as f_staged:
        w_out = csv.writer(f_out)
        w_staged = csv.writer(f_staged)
        w_out.writerow(EDGE_COLUMNS)
        w_staged.writerow(STAGED_COLUMNS)
        cur = conn.execute(
            "SELECT subject_id,predicate,object_id,original_predicate,source,source_dataset,"
            "source_version,source_record_id,evidence_score,pmid,doi,license,retrieved_at,"
            "status,staging_reason FROM edges ORDER BY predicate,subject_id,object_id,status"
        )
        for row in cur:
            (s, pred, o, orig, src, ds, ver, rec, score, pmid, doi, lic, ret, status, reason) = row
            eid = hashlib.sha1(f"{s}|{pred}|{o}".encode("utf-8")).hexdigest()[:24]
            out_row = [
                eid, s, pred, o, uniq_join(orig), uniq_join(src), uniq_join(ds),
                uniq_join(ver), uniq_join(rec), score, uniq_join(pmid), uniq_join(doi),
                uniq_join(lic), ret,
            ]
            if status == "allowed":
                w_out.writerow(out_row)
                total_allowed += 1
                counter[f"{pred}|{label_of.get(s, '?')}->{label_of.get(o, '?')}"] += 1
            else:
                w_staged.writerow(out_row + [reason or ""])
                total_staged += 1
                report["staged"][pred] += 1
    conn.close()
    db_path.unlink(missing_ok=True)

    # ------------------------------------------------------------ 写节点
    print("写出 nodes.csv ...")
    nodes_written = 0
    with (STAGING / "nodes.csv").open("w", encoding="utf-8", newline="\n") as out:
        writer = csv.writer(out)
        writer.writerow(NODE_COLUMNS)
        for nid in sorted(used):
            if nid in meta:
                label, name, syn, xref, desc = meta[nid]
                source, version, retrieved = "Monarch KG", MONARCH_VERSION, monarch_retrieved
            elif nid in created_nodes:
                label, name, syn, xref, desc, source, version, retrieved = created_nodes[nid]
            else:
                report["missing_metadata"][nid] += 1
                continue
            zh_info = zh.get(nid) or {}
            name_zh = zh_info.get("name_zh", "") or pheno_zh.get(nid, "")
            synonyms = syn
            if zh_info.get("synonyms"):
                extra = "|".join(zh_info["synonyms"])
                synonyms = f"{synonyms}|{extra}" if synonyms else extra
            writer.writerow([nid, label, name, name_zh, nid, synonyms, nid, xref, desc,
                             source, version, retrieved])
            nodes_written += 1

    # ------------------------------------------------------------ 附表
    with (STAGING / "phenotype_candidates.csv").open("w", encoding="utf-8", newline="\n") as out:
        writer = csv.writer(out)
        writer.writerow(["hp_id", "label", "name_zh", "edge_count"])
        for hp, cnt in phenotype_counts.most_common():
            writer.writerow([hp, meta.get(hp, ("", "", "", "", ""))[1], pheno_zh.get(hp, ""), cnt])

    with (STAGING / "staged_dismech_treatments.csv").open("w", encoding="utf-8", newline="\n") as out:
        writer = csv.writer(out)
        writer.writerow(["disease_id", "treatment_name", "preferred_term", "agent_chebi_ids", "source_record"])
        writer.writerows(staged_treatments)

    report["nodes_written"] = nodes_written
    report["edges_allowed"] = total_allowed
    report["edges_staged"] = total_staged
    report["raw_edge_records"] = raw_rows
    report["edges_merged_duplicate_records"] = raw_rows - total_allowed - total_staged
    report["relation_counts"] = dict(sorted(counter.items()))
    report["staged_counts"] = dict(sorted(report["staged"].items()))
    report["staged_dropped"] = dict(report["staged_dropped"])
    report["illegal_type_combo"] = dict(sorted(report["illegal_type_combo"].items()))
    report["illegal_type_combo_total"] = sum(report["illegal_type_combo"].values())
    report["ot_gene_mapping"] = dict(report["ot_gene_mapping"])
    report["dismech"] = dict(report["dismech"])
    report["missing_metadata"] = dict(report["missing_metadata"])
    report["phenotype_candidates"] = len(phenotype_counts)
    report.pop("staged")
    (STAGING / "normalize_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8", newline="\n",
    )

    print("\n完成：")
    print("  nodes.csv:", nodes_written)
    print("  edges.csv:", total_allowed)
    print("  edges_staged.csv:", total_staged)
    print("  原始边记录:", raw_rows, "| 合并重复记录:", raw_rows - total_allowed - total_staged)
    print("  relation_counts:", json.dumps(report["relation_counts"], ensure_ascii=False))
    print("  ot_gene_mapping:", json.dumps(report["ot_gene_mapping"], ensure_ascii=False))
    print("  dismech:", json.dumps(report["dismech"], ensure_ascii=False))
    print("  staged_dropped:", json.dumps(report["staged_dropped"], ensure_ascii=False))
    print("  非法类型组合:", report["illegal_type_combo_total"], "条",
          json.dumps(report["illegal_type_combo"], ensure_ascii=False))
    print("  missing_metadata:", len(report["missing_metadata"]))
    return 0


if __name__ == "__main__":
    build_ot_drug_index()
    raise SystemExit(main())
