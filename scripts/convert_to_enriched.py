#!/usr/bin/env python3
"""
convert_to_enriched.py
将 zotero_today.json 转换为 daily_papers_enriched.json 格式，
使 daily-papers-review / daily-papers-notes skill 能直接消费。

用法：
  python3 convert_to_enriched.py \
    --input /tmp/zotero_today.json \
    --output /tmp/daily_papers_enriched.json
"""

import json
import argparse
import re
import sys
from pathlib import Path
from datetime import datetime


def extract_arxiv_id(paper: dict) -> str | None:
    """从 extra 字段或 url 字段提取 arXiv ID"""
    extra = paper.get("extra", "") or ""
    url = paper.get("url", "") or ""

    # 常见格式: "arXiv:2603.05312" 或 "arXiv:2603.05312v1"
    m = re.search(r"arXiv[:\s]+(\d{4}\.\d{4,5}(?:v\d+)?)", extra, re.I)
    if m:
        return m.group(1).split("v")[0]  # 去掉版本号

    # 从 URL 提取
    m = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", url, re.I)
    if m:
        return m.group(1)

    return None


def paper_to_enriched(paper: dict) -> dict:
    """将 Zotero 文献条目转换为 enriched 格式"""
    arxiv_id = extract_arxiv_id(paper)
    title = paper.get("title", "Unknown")
    abstract = paper.get("abstract", "") or ""
    authors = paper.get("authors", [])
    publication = paper.get("publication", "") or ""
    collections = paper.get("collections", [])

    # 构造链接
    arxiv_link = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else paper.get("url", "")
    pdf_link = f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else ""

    # 来源标记（Zotero 本地添加）
    source = "zotero"

    # 简单评分：有 arXiv ID 的论文更容易处理
    score = 50
    if arxiv_id:
        score += 20
    if paper.get("pdf_path"):
        score += 10
    if abstract and len(abstract) > 100:
        score += 10

    # 机构信息（Zotero 通常没有，留空）
    affiliations = []

    # 从 collections 推断 zotero_collection
    zotero_collection = collections[0] if collections else ""

    return {
        # ── 基础信息 ──
        "arxiv_id": arxiv_id or f"zotero-{paper['item_id']}",
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "affiliations": affiliations,
        "source": source,
        "hf_upvotes": 0,
        "score": score,

        # ── 链接 ──
        "arxiv_link": arxiv_link,
        "pdf_link": pdf_link,
        "pdf_path": paper.get("pdf_path"),   # 本地 PDF（paper-reader 可直接用）

        # ── 富化字段（由 Zotero 元数据填充）──
        "method_names": [],          # paper-reader 会在阅读时提取
        "method_summary": "",        # 暂无，paper-reader 阅读后填充
        "figure_url": "",
        "has_real_world": False,
        "is_re_recommend": False,
        "last_recommend_date": None,

        # ── Zotero 专属字段 ──
        "zotero_item_id": paper["item_id"],
        "zotero_collection": zotero_collection,
        "item_type": paper.get("item_type", ""),
        "publication": publication,
        "doi": paper.get("doi", ""),
        "date_added": paper.get("date_added", ""),
    }


def main():
    parser = argparse.ArgumentParser(description="Zotero JSON → enriched JSON 格式转换")
    parser.add_argument("--input", default="/tmp/zotero_today.json",
                        help="输入文件路径（默认 /tmp/zotero_today.json）")
    parser.add_argument("--output", default="/tmp/daily_papers_enriched.json",
                        help="输出文件路径（默认 /tmp/daily_papers_enriched.json）")
    parser.add_argument("--no-pdf-only", action="store_true",
                        help="只转换无本地 PDF 的文献（用于 Step 4 批量点评）")
    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"[ERROR] 输入文件不存在: {in_path}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(in_path.read_text(encoding="utf-8"))
    papers = data.get("papers", [])

    # 分流：只处理无 PDF 的文献
    if args.no_pdf_only:
        papers = [p for p in papers if not p.get("pdf_path")]
        print(f"[INFO] 过滤后：无 PDF 文献 {len(papers)} 篇")

    enriched_papers = [paper_to_enriched(p) for p in papers]

    # 按 score 降序排列
    enriched_papers.sort(key=lambda x: x["score"], reverse=True)

    result = {
        "generated_at": datetime.now().isoformat(),
        "query_date": data.get("query_date", ""),
        "source": "zotero-daily-intake",
        "total": len(enriched_papers),
        "papers": enriched_papers,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"[OK] 已写入 {out_path}，共 {len(enriched_papers)} 篇文献")


if __name__ == "__main__":
    main()
