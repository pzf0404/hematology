#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载 V1 文档库（指南/规范）并登记 sources.json。

用法：
    python etl/fetch_guidelines.py
    python etl/fetch_guidelines.py --force

设计约束（对应任务指引第十四章、第十六章）：
- 只从发布机构官方渠道下载：国家卫生健康委（nhc.gov.cn）、
  欧洲白血病网（leukemia-net.org）、中华医学会杂志社文章存储（rcastoragev2）
- 幂等：已存在且已登记的文件默认跳过；--force 强制重下
- 可追溯：每个文件记录发布机构、版本、URL、下载时间、SHA256、字节数、许可、
  覆盖疾病、证据类型
- 不伪造：下载失败即报错退出，不生成占位文件
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDE_DIR = ROOT / "data" / "raw" / "guidelines"
SOURCES_PATH = GUIDE_DIR / "sources.json"

SCRIPT_VERSION = "1.0.0"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

NHC_2018 = "https://www.nhc.gov.cn/yzygj/c100068/201812/a7f5161869164dbb879df3782a144aec.shtml"
NHC_2019 = "https://www.nhc.gov.cn/yzygj/c100068/201909/6612d8cd14494c2bb9d99142c2f7b290.shtml"
NHC_2022 = "https://www.nhc.gov.cn/yzygj/c100068/202204/0c1f7d3aca0545abbeb02030ce255930.shtml"
ELN_AML = (
    "https://www.leukemia-net.org/sites/leukemia-net/content/e58/e480/e481/e11514/"
    "Doehner_H.etal_Blood2022.DiagnosisandmanagementofAMLinadults-2022recommendations"
    "fromaninternationalexpertpanelonbehalfoftheELN.pdf"
)
ELN_CML = (
    "https://www.leukemia-net.org/leukemias/cml/recommendations/e8078/"
    "infoboxContent11504/ApperleyetalLeukemia2025CMLELN2025GuidelinesforRx.pdf"
)

# evidence_type 统一为 guideline_text：与知识图谱的 knowledge_graph 证据区分
DOCUMENTS = [
    {
        "doc_id": "G01",
        "filename": "NHC_成人急性髓系白血病诊疗规范_2018.doc",
        "title": "成人急性髓系白血病诊疗规范（2018年版）",
        "issuer": "国家卫生健康委员会办公厅",
        "version": "2018年版",
        "published_at": "2018-12-13",
        "url": "https://www.nhc.gov.cn/yzygj/c100068/201812/a7f5161869164dbb879df3782a144aec/files/1732871423292_49233.doc",
        "referer": NHC_2018,
        "license": "政府主动公开信息（国卫办医函〔2018〕1125号），供公众免费下载",
        "diseases": ["AML"],
        "evidence_type": "guideline_text",
    },
    {
        "doc_id": "G02",
        "filename": "NHC_成人急性淋巴细胞白血病诊疗规范_2018.docx",
        "title": "成人急性淋巴细胞白血病诊疗规范（2018年版）",
        "issuer": "国家卫生健康委员会办公厅",
        "version": "2018年版",
        "published_at": "2018-12-13",
        "url": "https://www.nhc.gov.cn/yzygj/c100068/201812/a7f5161869164dbb879df3782a144aec/files/1732871423342_35012.docx",
        "referer": NHC_2018,
        "license": "政府主动公开信息（国卫办医函〔2018〕1125号），供公众免费下载",
        "diseases": ["ALL"],
        "evidence_type": "guideline_text",
    },
    {
        "doc_id": "G03",
        "filename": "NHC_儿童急性淋巴细胞白血病诊疗规范_2018.doc",
        "title": "儿童急性淋巴细胞白血病诊疗规范（2018年版）",
        "issuer": "国家卫生健康委员会办公厅",
        "version": "2018年版",
        "published_at": "2018-10-08",
        "url": "https://www.nhc.gov.cn/ewebeditor/uploadfile/2018/10/20181016180401747.doc",
        "referer": "https://www.nhc.gov.cn/",
        "license": "政府主动公开信息（国卫办医函〔2018〕868号），供公众免费下载",
        "diseases": ["ALL"],
        "evidence_type": "guideline_text",
    },
    {
        "doc_id": "G04",
        "filename": "NHC_儿童急性早幼粒细胞白血病诊疗规范_2018.doc",
        "title": "儿童急性早幼粒细胞白血病诊疗规范（2018年版）",
        "issuer": "国家卫生健康委员会办公厅",
        "version": "2018年版",
        "published_at": "2018-10-08",
        "url": "https://www.nhc.gov.cn/ewebeditor/uploadfile/2018/10/20181016180416637.doc",
        "referer": "https://www.nhc.gov.cn/",
        "license": "政府主动公开信息（国卫办医函〔2018〕868号），供公众免费下载",
        "diseases": ["APL"],
        "evidence_type": "guideline_text",
    },
    {
        "doc_id": "G05",
        "filename": "NHC_儿童再生障碍性贫血诊疗规范_2019.pdf",
        "title": "儿童再生障碍性贫血诊疗规范（2019年版）",
        "issuer": "国家卫生健康委员会办公厅",
        "version": "2019年版",
        "published_at": "2019-09-04",
        "url": "https://www.nhc.gov.cn/yzygj/c100068/201909/6612d8cd14494c2bb9d99142c2f7b290/files/1732863953782_28435.pdf",
        "referer": NHC_2019,
        "license": "政府主动公开信息（国卫办医函〔2019〕716号），供公众免费下载",
        "diseases": ["AA"],
        "evidence_type": "guideline_text",
    },
    {
        "doc_id": "G06",
        "filename": "NHC_慢性髓性白血病诊疗指南_2022.pdf",
        "title": "慢性髓性白血病诊疗指南（2022年版）",
        "issuer": "国家卫生健康委员会办公厅",
        "version": "2022年版",
        "published_at": "2022-04-03",
        "url": "https://www.nhc.gov.cn/yzygj/c100068/202204/0c1f7d3aca0545abbeb02030ce255930/files/1732863054519_15977.pdf",
        "referer": NHC_2022,
        "license": "政府主动公开信息（国卫办医函〔2022〕104号），供公众免费下载",
        "diseases": ["CML"],
        "evidence_type": "guideline_text",
    },
    {
        "doc_id": "G07",
        "filename": "NHC_慢性淋巴细胞白血病-小淋巴细胞淋巴瘤诊疗指南_2022.pdf",
        "title": "慢性淋巴细胞白血病/小淋巴细胞淋巴瘤诊疗指南（2022年版）",
        "issuer": "国家卫生健康委员会办公厅",
        "version": "2022年版",
        "published_at": "2022-04-03",
        "url": "https://www.nhc.gov.cn/yzygj/c100068/202204/0c1f7d3aca0545abbeb02030ce255930/files/1732863055385_61833.pdf",
        "referer": NHC_2022,
        "license": "政府主动公开信息（国卫办医函〔2022〕104号），供公众免费下载",
        "diseases": ["CLL"],
        "evidence_type": "guideline_text",
    },
    {
        "doc_id": "G08",
        "filename": "ELN_2022_AML_recommendations.pdf",
        "title": "Diagnosis and management of AML in adults: 2022 recommendations from an international expert panel on behalf of the ELN",
        "issuer": "European LeukemiaNet（ELN）",
        "version": "2022（Blood 2022;140:1345-1377）",
        "published_at": "2022-09-22",
        "url": ELN_AML,
        "referer": "https://www.leukemia-net.org/leukemias/aml/recommendations",
        "license": "ELN 官网免费下载，版权归 ELN 及 Blood/ASH；仅内部研究使用，不再分发",
        "diseases": ["AML"],
        "evidence_type": "guideline_text",
    },
    {
        "doc_id": "G09",
        "filename": "ELN_2025_CML_recommendations.pdf",
        "title": "2025 European LeukemiaNet recommendations for the management of chronic myeloid leukemia",
        "issuer": "European LeukemiaNet（ELN）",
        "version": "2025（Leukemia, open access）",
        "published_at": "2025-01-01",
        "url": ELN_CML,
        "referer": "https://www.leukemia-net.org/leukemias/cml/recommendations",
        "license": "期刊 Open Access（CC BY），ELN 官网提供下载",
        "diseases": ["CML"],
        "evidence_type": "guideline_text",
    },
    {
        "doc_id": "G10",
        "filename": "CMA_再生障碍性贫血诊断与治疗中国指南_2022.pdf",
        "title": "再生障碍性贫血诊断与治疗中国指南（2022年版）",
        "issuer": "中华医学会血液学分会红细胞疾病（贫血）学组",
        "version": "2022（中华血液学杂志 2022;43(11):881-888，DOI 10.3760/cma.j.issn.0253-2727.2022.11.001）",
        "published_at": "2022-11-14",
        "url": "https://rcastoragev2.blob.core.windows.net/308060e1d83f57a2ea9d4a88acadb9cf/cjh-43-11-881.pdf",
        "referer": "https://rs.yiigle.com/cmaid/1442979",
        "license": "中华医学会杂志社正式发表版（中华医学期刊网 rs.yiigle.com/cmaid/1442979），仅内部研究使用",
        "diseases": ["AA"],
        "evidence_type": "guideline_text",
    },
]

# 已转换的 docx（RAGFlow 上传用）；doc/docx 统一转成 docx 以稳定解析
CONVERTED = {
    "NHC_成人急性髓系白血病诊疗规范_2018.doc": "NHC_成人急性髓系白血病诊疗规范_2018.docx",
    "NHC_儿童急性淋巴细胞白血病诊疗规范_2018.doc": "NHC_儿童急性淋巴细胞白血病诊疗规范_2018.docx",
    "NHC_儿童急性早幼粒细胞白血病诊疗规范_2018.doc": "NHC_儿童急性早幼粒细胞白血病诊疗规范_2018.docx",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def download(url: str, referer: str, dest: Path) -> int:
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Referer": referer, "Accept": "*/*"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    if not data:
        raise RuntimeError(f"空响应：{url}")
    dest.write_bytes(data)
    return len(data)


def page_count(path: Path) -> int | None:
    try:
        import fitz  # PyMuPDF
    except Exception:
        return None
    try:
        with fitz.open(path) as doc:
            return doc.page_count
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    GUIDE_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    failures = []

    for item in DOCUMENTS:
        dest = GUIDE_DIR / item["filename"]
        if args.force or not dest.exists():
            try:
                size = download(item["url"], item.get("referer", ""), dest)
                print(f"downloaded {item['doc_id']} {item['filename']} ({size} bytes)")
            except (urllib.error.URLError, RuntimeError) as exc:
                failures.append({"doc_id": item["doc_id"], "url": item["url"], "error": str(exc)})
                print(f"FAILED {item['doc_id']} {item['url']}: {exc}", file=sys.stderr)
                continue
        else:
            print(f"skip {item['doc_id']} {item['filename']} (exists)")

        rec = dict(item)
        rec["size_bytes"] = dest.stat().st_size
        rec["sha256"] = sha256_of(dest)
        rec["retrieved_at"] = now_iso()
        if dest.suffix.lower() == ".pdf":
            rec["pages"] = page_count(dest)
        if item["filename"] in CONVERTED:
            rec["upload_filename"] = CONVERTED[item["filename"]]
            rec["converted_format"] = "docx (Microsoft Word 另存为 .docx，正文未改动)"
        else:
            rec["upload_filename"] = item["filename"]
        records.append(rec)

    manifest = {
        "script_version": SCRIPT_VERSION,
        "generated_at": now_iso(),
        "purpose": "阶段 5 文档知识库（指南/共识/长文本证据），与知识图谱证据并列",
        "evidence_type": "guideline_text",
        "documents": records,
        "failures": failures,
    }
    SOURCES_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"manifest -> {SOURCES_PATH.relative_to(ROOT).as_posix()} ({len(records)} docs)")
    if failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
