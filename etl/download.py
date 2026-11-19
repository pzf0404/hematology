#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载 V1 原始数据并登记 manifest。

用法：
    python etl/download.py
    python etl/download.py --force

设计约束：
- 幂等：已存在且已登记的文件默认跳过；--force 强制重下
- 可追溯：每个文件记录 URL、版本、SHA256、字节数、许可
- 不伪造：下载失败即报错退出，不生成占位文件
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
MANIFEST_PATH = RAW / "manifest.json"
MAPPING_PATH = ROOT / "config" / "entity_mapping.yaml"

MONARCH_VERSION = "2026-11-11"
MONARCH_FILE = RAW / "monarch-kg" / MONARCH_VERSION / "monarch-kg.tar.gz"
MONARCH_URL = f"https://data.monarchinitiative.org/monarch-kg/{MONARCH_VERSION}/monarch-kg.tar.gz"
MONARCH_SIZE = 368326109
MONARCH_SHA256 = "74B9CD49DE6D03E1F7B7BDF62CD3935C70D412D90B30B7792E4437FAA18694C2"

MONDO_URL = "https://purl.obolibrary.org/obo/mondo.json"

OT_ENDPOINT = "https://api.platform.opentargets.org/api/v4/graphql"
OT_PAGE_SIZE = 1000
OT_MAX_PAGES = 100
OT_DRUG_BATCH = 25

UA = "hematology-kg-v1/1.0 (+local research pipeline)"
# 任务指引第十六章：manifest 至少保存 URL、下载时间、版本、SHA256、License、文件大小和处理脚本版本
SCRIPT_VERSION = "1.1.0"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {"generated_at": now_iso(), "script_version": SCRIPT_VERSION, "sources": []}
    with MANIFEST_PATH.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def get_source(manifest: dict, name: str) -> dict | None:
    for s in manifest.get("sources", []):
        if s.get("name") == name:
            return s
    return None


def upsert_source(manifest: dict, entry: dict) -> None:
    sources = [s for s in manifest.get("sources", []) if s.get("name") != entry["name"]]
    sources.append(entry)
    manifest["sources"] = sorted(sources, key=lambda s: s["name"])


def save_manifest(manifest: dict) -> None:
    manifest["generated_at"] = now_iso()
    manifest["script_version"] = SCRIPT_VERSION
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    MANIFEST_PATH.write_text(text, encoding="utf-8", newline="\n")


def http_request(url: str, *, accept: str | None = None, data: bytes | None = None, timeout: int = 120):
    headers = {"User-Agent": UA}
    if accept:
        headers["Accept"] = accept
    if data is not None:
        headers["Content-Type"] = "application/json"
    return urllib.request.Request(url, data=data, headers=headers)


def fetch_bytes(url: str, *, accept: str | None = None, retries: int = 5, timeout: int = 120) -> bytes:
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(http_request(url, accept=accept, timeout=timeout), timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"  重试 {attempt}/{retries}: {type(e).__name__}: {e}")
            time.sleep(min(2 ** attempt, 12))
    raise RuntimeError(f"下载失败: {url}") from last


def replace_with_retry(src: Path, dest: Path, *, attempts: int = 5) -> None:
    """改名（先确保 src 的文件句柄已关闭）。

    Windows 上文件仍被本进程或其他程序（杀毒/索引服务）持有句柄时，
    os.replace 会抛 PermissionError [WinError 32]，这里做短间隔重试。
    """
    for i in range(attempts):
        try:
            os.replace(src, dest)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.5 * (i + 1))


def download_to(url: str, dest: Path, *, retries: int = 5) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        headers: dict = {}
        try:
            # 清掉上一轮残留的 .part（被占用时留给下一轮）
            if tmp.exists():
                try:
                    tmp.unlink()
                except PermissionError:
                    pass

            # 关键：写句柄必须在 with 块结束、文件关闭之后才能改名，
            # 否则 Windows 下 os.replace 必然报 WinError 32
            with urllib.request.urlopen(http_request(url, timeout=180), timeout=180) as r:
                total = 0
                with tmp.open("wb") as f:
                    while True:
                        chunk = r.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        total += len(chunk)
                        if total // (10 * 1024 * 1024) != (total - len(chunk)) // (10 * 1024 * 1024):
                            print(f"  已下载 {total / (1024 * 1024):.0f} MB")
                headers = dict(r.headers)

            replace_with_retry(tmp, dest)
            return headers
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"  重试 {attempt}/{retries}: {type(e).__name__}: {e}")
            time.sleep(min(2 ** attempt, 12))
    raise RuntimeError(f"下载失败: {url}") from last


def file_entry(path: Path, url: str, **extra) -> dict:
    entry = {
        "path": rel(path),
        "url": url,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "script_version": SCRIPT_VERSION,
    }
    entry.update(extra)
    return entry


# ---------------------------------------------------------------- Monarch

def register_monarch(manifest: dict, force: bool) -> dict:
    print("\n[1/4] Monarch KG")
    fresh = force or not MONARCH_FILE.exists()
    if fresh:
        print(f"  下载: {MONARCH_URL}")
        download_to(MONARCH_URL, MONARCH_FILE)
    size = MONARCH_FILE.stat().st_size
    digest = sha256_file(MONARCH_FILE)
    if size != MONARCH_SIZE:
        raise ValueError(f"Monarch 大小不符: {size} != {MONARCH_SIZE}")
    if digest != MONARCH_SHA256:
        raise ValueError(f"Monarch SHA256 不符: {digest} != {MONARCH_SHA256}")
    print(f"  通过: {size} 字节, SHA256={digest}")

    old = get_source(manifest, "Monarch KG") or {}
    changed = old.get("version") != MONARCH_VERSION
    entry = {
        "name": "Monarch KG",
        "type": "knowledge_graph",
        "source_url": MONARCH_URL,
        "version": MONARCH_VERSION,
        "upstream_channel": "versioned",
        "release_date": MONARCH_VERSION,
        "license": "未声明统一许可；上游逐源许可保留",
        "retrieved_at": now_iso() if (fresh or changed) else (old.get("retrieved_at") or now_iso()),
        "retrieved_by": "etl/download.py" if (fresh or changed) else old.get("retrieved_by", "manual"),
        "files": [file_entry(MONARCH_FILE, MONARCH_URL, role="monarch-kg")],
        "notes": {
            "provided_by_count": 39,
            "primary_knowledge_source_count": 195,
            "edge_rows": 16961180,
            "node_rows": 2006605,
        },
    }
    if old.get("archived_at"):
        entry["archived_at"] = old["archived_at"]
    upsert_source(manifest, entry)
    return entry


# ---------------------------------------------------------------- MONDO

def register_mondo(manifest: dict, force: bool) -> dict:
    print("\n[2/4] MONDO 本体")
    old = get_source(manifest, "MONDO")
    if old and not force:
        files = old.get("files") or []
        if files and (ROOT / files[0]["path"]).exists():
            print(f"  已登记，跳过: {files[0]['path']}")
            return old

    release = None
    if old and old.get("release_date"):
        release = old["release_date"]
    dest = None
    headers = None
    if old and not force and (ROOT / old["files"][0]["path"]).exists():
        dest = ROOT / old["files"][0]["path"]
    else:
        headers = None
        tmp_dest_dir = RAW / "mondo" / "pending"
        dest = tmp_dest_dir / "mondo.json"
        headers = download_to(MONDO_URL, dest)
        last_modified = headers.get("Last-Modified")
        if last_modified:
            release = parsedate_to_datetime(last_modified).date().isoformat()
        release = release or datetime.now().date().isoformat()
        final_dir = RAW / "mondo" / release
        final_dir.mkdir(parents=True, exist_ok=True)
        dest = final_dir / "mondo.json"
        replace_with_retry(tmp_dest_dir / "mondo.json", dest)
        try:
            tmp_dest_dir.rmdir()
        except OSError:
            pass

    print(f"  文件: {rel(dest)} ({dest.stat().st_size} 字节)")
    entry = {
        "name": "MONDO",
        "type": "ontology",
        "source_url": MONDO_URL,
        "version": release,
        "release_date": release,
        "license": "CC BY 4.0",
        "retrieved_at": now_iso(),
        "files": [file_entry(dest, MONDO_URL, role="disease_ontology")],
    }
    upsert_source(manifest, entry)
    return entry


# ---------------------------------------------------------------- DisMech

def register_dismech(manifest: dict, mapping: dict, force: bool) -> dict:
    print("\n[3/4] DisMech（按 commit 定向下载）")
    cfg = mapping["dismech"]
    ref = cfg["ref"]
    old = get_source(manifest, "DisMech")
    if old and old.get("version") == ref and not force:
        print("  已登记同一 commit，跳过")
        return old

    base = RAW / "dismech" / ref
    files = []
    for item in cfg["files"]:
        path = item["path"]
        name = Path(path).name
        url = f"https://api.github.com/repos/monarch-initiative/dismech/contents/{path}?ref={ref}"
        dest = base / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"  - {name}")
        dest.write_bytes(fetch_bytes(url, accept="application/vnd.github.raw"))
        files.append(
            file_entry(
                dest,
                url,
                role="dismech_yaml",
                disease_id=item.get("disease_id"),
                in_graph=bool(item.get("in_graph")),
            )
        )

    entry = {
        "name": "DisMech",
        "type": "mechanism_knowledge_base",
        "source_url": cfg["repository"],
        "version": ref,
        "release_date": None,
        "license": "BSD-3-Clause (repository); AI-curated content",
        "retrieved_at": now_iso(),
        "files": files,
    }
    upsert_source(manifest, entry)
    return entry


# ---------------------------------------------------------------- Open Targets

def ot_query(query: str, retries: int = 5) -> dict:
    payload = json.dumps({"query": query}).encode("utf-8")
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(
                http_request(OT_ENDPOINT, data=payload, timeout=120), timeout=120
            ) as r:
                data = json.loads(r.read().decode("utf-8"))
            if data.get("errors"):
                raise RuntimeError(f"GraphQL 错误: {data['errors']}")
            return data["data"]
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"  重试 {attempt}/{retries}: {type(e).__name__}: {e}")
            time.sleep(min(2 ** attempt, 12))
    raise RuntimeError("Open Targets 查询失败") from last


def ot_meta() -> dict:
    d = ot_query("{ meta { name product dataVersion { year month iteration } apiVersion { x y z suffix } } }")
    return d["meta"]


def ot_disease_bundle(ot_id: str) -> dict:
    basic = ot_query('{ disease(efoId:"%s"){ id name } }' % ot_id)["disease"]

    rows: list[dict] = []
    total = None
    for page in range(OT_MAX_PAGES):
        q = (
            '{ disease(efoId:"%s"){ associatedTargets(page:{index:%d,size:%d}){'
            " count rows{ target{ id approvedSymbol approvedName biotype } score "
            "datatypeScores{ id score } } } } }"
        ) % (ot_id, page, OT_PAGE_SIZE)
        at = ot_query(q)["disease"]["associatedTargets"]
        total = at["count"]
        rows.extend(at["rows"])
        print(f"    靶点页 {page + 1}: 累计 {len(rows)}/{total}")
        if not at["rows"] or len(rows) >= total:
            break

    drugs = ot_query(
        '{ disease(efoId:"%s"){ drugAndClinicalCandidates{ count rows{ id maxClinicalStage drug{ id name drugType } } } } }'
        % ot_id
    )["disease"]["drugAndClinicalCandidates"]

    return {
        "disease": basic,
        "associated_targets": {"count": total, "rows": rows},
        "drug_candidates": drugs,
    }


def ot_drug_mechanisms(unique_ids: list[str]) -> dict:
    """批量查询药物机制与靶点；GraphQL alias 每批 OT_DRUG_BATCH 个。"""
    results: dict[str, object] = {}
    total = len(unique_ids)
    for start in range(0, total, OT_DRUG_BATCH):
        batch = unique_ids[start:start + OT_DRUG_BATCH]
        parts = []
        for i, did in enumerate(batch):
            parts.append(
                'd%d: drug(chemblId:"%s"){ id name mechanismsOfAction{'
                " rows{ mechanismOfAction actionType targetName targets{ id approvedSymbol } } } }"
                % (i, did)
            )
        data = ot_query("{ " + " ".join(parts) + " }")
        for i, did in enumerate(batch):
            results[did] = data.get(f"d{i}")
        print(f"    药物机制批 {start // OT_DRUG_BATCH + 1}: 累计 {len(results)}/{total}")
    return results


def register_open_targets(manifest: dict, mapping: dict, force: bool) -> dict:
    print("\n[4/4] Open Targets Platform")
    meta = ot_meta()
    dv = meta.get("dataVersion") or {}
    version = f"{str(dv.get('year')).zfill(2)}.{str(dv.get('month')).zfill(2)}"
    print(f"  数据版本: {version} | API: {meta.get('apiVersion')}")

    old = get_source(manifest, "Open Targets")
    base = RAW / "open-targets" / version
    base.mkdir(parents=True, exist_ok=True)

    expected = [item for item in mapping["diseases"] if item.get("open_targets_id")]
    files: list[dict] = []
    # 只要本轮真的重新抓取了任一数据，就更新 retrieved_at；全部复用则保留原下载时间
    reused_all = True

    # 1) 疾病 bundle：同版本可复用，避免重复翻页
    old_bundles = [
        f for f in (old or {}).get("files", [])
        if f.get("role") == "open_targets_bundle" and (ROOT / f["path"]).exists()
    ] if old and old.get("version") == version and not force else []
    if len(old_bundles) == len(expected):
        print(f"  复用已有疾病 bundle: {len(old_bundles)} 个")
        files.extend(old_bundles)
    else:
        reused_all = False
        for item in expected:
            seed = item["seed_key"]
            ot_id = item["open_targets_id"]
            print(f"  - {seed} ({ot_id})")
            bundle = ot_disease_bundle(ot_id)
            dest = base / f"{seed}.json"
            payload = {
                "source": "Open Targets Platform GraphQL v4",
                "endpoint": OT_ENDPOINT,
                "data_version": version,
                "api_version": meta.get("apiVersion"),
                "seed_key": seed,
                "canonical_id": item.get("canonical_id"),
                "open_targets_id": ot_id,
                "in_graph": bool(item.get("in_graph")),
                "retrieved_at": now_iso(),
                **bundle,
            }
            dest.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
                newline="\n",
            )
            files.append(
                file_entry(
                    dest,
                    f"{OT_ENDPOINT}#disease(efoId:{ot_id})",
                    role="open_targets_bundle",
                    disease_id=item.get("canonical_id"),
                    in_graph=bool(item.get("in_graph")),
                )
            )

    # 2) 药物机制：Drug -> TARGETS -> Gene 必需数据
    mech_path = base / "drug_mechanisms.json"
    old_mech = next(
        (f for f in (old or {}).get("files", []) if f.get("role") == "drug_mechanisms"),
        None,
    )
    if not force and mech_path.exists() and old_mech:
        print("  复用已有药物机制文件")
        files.append(old_mech)
    else:
        reused_all = False
        unique_drugs: dict[str, str] = {}
        for f in files:
            if f.get("role") != "open_targets_bundle":
                continue
            d = json.loads((ROOT / f["path"]).read_text(encoding="utf-8"))
            if not d.get("in_graph"):
                continue
            for row in d.get("drug_candidates", {}).get("rows", []):
                drug = row.get("drug") or {}
                if drug.get("id"):
                    unique_drugs[drug["id"]] = drug.get("name")
        print(f"  去重药物: {len(unique_drugs)} 个")
        mech = ot_drug_mechanisms(sorted(unique_drugs))
        payload = {
            "source": "Open Targets Platform GraphQL v4",
            "endpoint": OT_ENDPOINT,
            "data_version": version,
            "retrieved_at": now_iso(),
            "drug_count": len(unique_drugs),
            "drugs": mech,
        }
        mech_path.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
            newline="\n",
        )
        files.append(
            file_entry(
                mech_path,
                f"{OT_ENDPOINT}#drug.mechanismsOfAction",
                role="drug_mechanisms",
                drug_count=len(unique_drugs),
            )
        )

    previous_retrieved = (old or {}).get("retrieved_at") if (old or {}).get("version") == version else None
    entry = {
        "name": "Open Targets",
        "type": "evidence_platform",
        "source_url": OT_ENDPOINT,
        "version": version,
        "release_date": f"20{version.split('.')[0]}-{version.split('.')[1]}",
        "license": "平台数据 CC0；上游逐源条款见 docs/02_license_review.md",
        # 全量复用缓存时保留真实下载时间；本轮有重新抓取才更新
        "retrieved_at": previous_retrieved if reused_all and previous_retrieved else now_iso(),
        "files": files,
    }
    upsert_source(manifest, entry)
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description="下载 V1 原始数据并登记 manifest")
    parser.add_argument("--force", action="store_true", help="强制重新下载")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if not MAPPING_PATH.exists():
        print(f"缺少实体映射文件: {MAPPING_PATH}", file=sys.stderr)
        return 2
    mapping = yaml.safe_load(MAPPING_PATH.read_text(encoding="utf-8"))

    manifest = load_manifest()
    register_monarch(manifest, args.force)
    register_mondo(manifest, args.force)
    register_dismech(manifest, mapping, args.force)
    register_open_targets(manifest, mapping, args.force)
    save_manifest(manifest)

    print("\n完成。manifest:", rel(MANIFEST_PATH))
    for s in manifest["sources"]:
        total = sum(f["size_bytes"] for f in s.get("files", []))
        print(f"  - {s['name']}: {len(s.get('files', []))} 个文件, {total / (1024 * 1024):.1f} MB, 版本={s.get('version')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
