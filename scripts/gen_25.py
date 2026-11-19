# -*- coding: utf-8 -*-
"""由 RAGFlow 运行结果 res JSON 生成逐条答案存档（与 2026-11-12 既有格式一致）。

用法:
    python3 gen_25.py res25.json acceptance_cases_ragflow.json <输出目录>
"""
import json, sys, os, datetime

res_path, cases_path, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
cases = {c['id']: c for c in json.load(open(cases_path, encoding='utf-8'))['cases']}
res = json.load(open(res_path, encoding='utf-8'))
os.makedirs(out_dir, exist_ok=True)

CN = {'AML': 'AML', 'APL': 'APL', 'ALL': 'ALL', 'CML': 'CML', 'CLL': 'CLL', 'AA': 'AA'}

def ts(v):
    try:
        return datetime.datetime.fromtimestamp(int(v)).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return str(v)

def cell(x):
    return (x or '').replace('|', '\\|').replace('\n', ' ').strip()

for r in res:
    cid = r['id']
    c = cases[cid]
    route = r.get('triage') or ''
    route_ids = ', '.join(r.get('route_ids') or [])
    paths = r.get('paths') or []
    chunks = r.get('chunks') or []
    ans = r.get('answer') or ''
    refusal = ('现有证据不足' in ans) or ('证据不足以回答' in ans)

    lines = []
    lines.append(f"# {cid}｜{CN.get(c['route'], c['route'])}：{c['question']}")
    lines.append('')
    lines.append('> RAGFlow 画布 `hematology_kg_rag_v1` 实际运行产出，原文存档。')
    meta = r.get('meta') or {}
    lines.append(f"> 运行时间：{ts(meta.get('created_at'))}（Asia/Shanghai）｜session_id：`{meta.get('session_id')}`"
                 f"｜请求体：`{json.dumps({'user_input': c['question']}, ensure_ascii=False)}`")
    lines.append('')
    lines.append('## 1. 期望命中（第十八章口径）')
    lines.append('')
    lines.append(f"- 病种路由：`{c['route']}`")
    lines.append(f"- 实体：{'；'.join(c.get('expected_entities') or [])}")
    lines.append(f"- 关系：{'；'.join(c.get('expected_relations') or [])}")
    lines.append(f"- 来源：{', '.join(c.get('expected_sources') or [])}")
    lines.append(f"- 回答关键词（任一）：{', '.join(c.get('expected_keywords') or [])}")
    lines.append('')
    lines.append('## 2. 实际命中')
    lines.append('')
    lines.append(f"- 分诊输出：`{route}`；检索词：`{r.get('term')}`")
    lines.append(f"- `disease_route`：`{r.get('disease_route')}`；route ids：`{route_ids}`")
    et = json.dumps(r.get('evidence_types'), ensure_ascii=False)
    lines.append(f"- 路径数：{len(paths)}；`evidence_types`：`{et}`；context：{len(r.get('context') or '')} 字符")
    lines.append(f"- 指南证据：`formalized_content` {len(r.get('formalized_content') or '')} 字符，chunks {len(chunks)}；"
                 f"命中来源：{', '.join(r.get('src_hit') or []) or '无'}")
    lines.append(f"- 关键词命中：{', '.join(r.get('kw_hit') or []) or '无'}")
    lines.append('')
    lines.append('路径明细：')
    lines.append('')
    lines.append('| # | 起点 | 终点 | 关系 | 来源 |')
    lines.append('|---|---|---|---|---|')
    for i, p in enumerate(paths, 1):
        nodes = p.get('nodes') or []
        rels = p.get('relationships') or []
        s = nodes[0] if nodes else {}
        o = nodes[-1] if nodes else {}
        rel = rels[0] if rels else {}
        sname = f"`{s.get('id')}` {s.get('name_zh') or s.get('name') or ''}"
        oname = f"`{o.get('id')}` {o.get('name_zh') or o.get('name') or ''}"
        lines.append(f"| {i} | {cell(sname)} | {cell(oname)} | {rel.get('type','')} | {rel.get('source','')} {rel.get('source_version','')} |")
    lines.append('')
    lines.append('检索 chunk：')
    lines.append('')
    lines.append('| # | 来源文档 | 相似度 | 摘录 |')
    lines.append('|---|---|---|---|')
    for i, ch in enumerate(chunks, 1):
        score = ch.get('score')
        score_s = f'{score:.4f}' if isinstance(score, (int, float)) else ''
        head = cell(ch.get('head') or '')[:90]
        lines.append(f"| {i} | {cell(ch.get('doc'))} | {score_s} | {head}… |")
    lines.append('')
    lines.append('## 3. 完整回答（原文）')
    lines.append('')
    lines.append('> 注：API 返回 `[ID:<chunk_id>]` 引用标记；最终分析 Agent 的 `cite=false`（2026-11-12），'
                 'UI 不再转成 `[1]`…`[n]` 编号卡片，回答中保留原始 chunk ID 以便回溯。')
    lines.append('')
    lines.append(ans.rstrip())
    lines.append('')
    lines.append('## 4. 判定')
    lines.append('')
    checks = r.get('checks') or {}
    marks = '、'.join(f"{k}={'✅' if v else '❌'}" for k, v in checks.items())
    lines.append(f"- 判定：**{r.get('status')}**（{marks}）")
    lines.append(f"- 节点 `error`：{r.get('node_errors') or '无'}")
    lines.append(f"- 回答长度 {len(ans)} 字符；与 `Message` 输出一致：{'是' if ans == (r.get('message') or '') else '否'}")
    if refusal:
        lines.append('- 备注：按证据优先规则弃答（现有证据不足以回答该问题）')
    lines.append('')

    with open(os.path.join(out_dir, f'{cid}.md'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines))

print('written', len(res), 'files to', out_dir)
