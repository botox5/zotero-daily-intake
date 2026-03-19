#!/usr/bin/env python3
"""
record_keywords.py
提取本次处理文献的关键词，追加到 data/keyword_history.jsonl 中。

用法：
  python3 record_keywords.py --input /tmp/zotero_today.json
  python3 record_keywords.py --input /tmp/zotero_today.json \
      --review-file ~/Obsidian/DailyPapers/2026-03-19-Zotero入库.md \
      --output ~/.workbuddy/skills/zotero-daily-intake/data/keyword_history.jsonl
"""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

# ── 停用词（中英混合） ─────────────────────────────────────────
STOPWORDS_EN = {
    "a","an","the","and","or","but","in","on","at","to","for","of","with","by",
    "from","is","are","was","were","be","been","being","have","has","had",
    "do","does","did","will","would","could","should","may","might","can",
    "this","that","these","those","it","its","we","our","their","they",
    "study","paper","result","results","method","methods","approach","based",
    "using","used","use","also","however","thus","therefore","propose",
    "proposed","show","shown","shows","analysis","model","system","data",
    "research","review","novel","new","high","low","large","small","two",
    "one","three","four","five","six","seven","eight","nine","ten","between",
    "performance","compared","comparison","different","various","multiple",
    "significantly","improved","improvement","evaluation","experiment",
    "experimental","existing","proposed","present","future","current",
    "related","work","works","task","tasks","dataset","datasets",
    "test","train","training","testing","validation",
}
STOPWORDS_ZH = {
    "的","了","在","是","与","和","对","中","基于","通过","利用","采用",
    "本文","研究","分析","方法","系统","模型","结果","实验","提出","探讨",
    "综述","评述","进展","现状","应用","问题","影响","因素","关系",
    "具有","能够","可以","由于","因此","从而","但是","然而","此外",
    "为了","以及","或者","不同","多种","各种","相关","相比","改善",
    "提高","降低","增加","减少","验证","有效","较高","较低",
}

def extract_keywords(text: str, top_n: int = 30) -> list[tuple[str, int]]:
    """
    简单 TF-based 关键词提取（不依赖外部库）。
    对英文按空格/标点分词，对中文提取 2-4 字词。
    返回 [(词, 频次), ...] 按频次降序。
    """
    text = text.lower()

    # 英文词：字母序列，长度 ≥ 3
    en_words = re.findall(r'\b[a-z]{3,}\b', text)
    en_filtered = [w for w in en_words if w not in STOPWORDS_EN]

    # 中文词：2-4 字汉字序列
    zh_words = re.findall(r'[\u4e00-\u9fff]{2,4}', text)
    zh_filtered = [w for w in zh_words if w not in STOPWORDS_ZH]

    counter = Counter(en_filtered + zh_filtered)
    return counter.most_common(top_n)


def parse_review_labels(review_file: Path) -> dict[str, str]:
    """
    从 daily-papers-review 生成的 Markdown 文件中解析每篇论文的推荐标签。
    识别格式：
      ### [必读] 标题  /  **必读** 标题  /  > 推荐级别：必读
    返回 {title_keyword: "必读" | "值得看" | "可跳过"}
    """
    labels = {}
    if not review_file or not Path(review_file).exists():
        return labels

    content = Path(review_file).read_text(encoding="utf-8")
    patterns = [
        # 格式 1：### [必读] 标题
        r'#{1,4}\s*\[?(必读|值得看|可跳过)\]?\s+(.+)',
        # 格式 2：**必读**：标题 / **必读** 标题
        r'\*\*(必读|值得看|可跳过)\*\*[：:]\s*(.+)',
        # 格式 3：- **必读** 标题
        r'-\s+\*\*(必读|值得看|可跳过)\*\*\s+(.+)',
    ]
    for pat in patterns:
        for m in re.finditer(pat, content):
            label, title_fragment = m.group(1), m.group(2).strip()
            # 取标题前 20 字作为 key（容忍格式差异）
            key = re.sub(r'[^\w\u4e00-\u9fff]', '', title_fragment[:30]).lower()
            if key:
                labels[key] = label

    return labels


def record(papers: list[dict], review_file: str | None, output_path: Path, date_str: str):
    """提取关键词并追加记录到 JSONL 文件。"""
    review_labels = parse_review_labels(Path(review_file) if review_file else None)

    records = []
    for p in papers:
        # 拼接可用文本
        text_parts = [p.get("title", ""), p.get("abstract", "")]
        full_text = " ".join(filter(None, text_parts))

        keywords = extract_keywords(full_text, top_n=25)

        # 尝试匹配推荐标签
        title_key = re.sub(r'[^\w\u4e00-\u9fff]', '', (p.get("title","")[:30]).lower())
        label = review_labels.get(title_key, "")
        if not label:
            # 用关键词模糊匹配
            for k, v in review_labels.items():
                if k and title_key and (k in title_key or title_key in k):
                    label = v
                    break

        rec = {
            "date": date_str,
            "item_id": p.get("item_id"),
            "title": p.get("title", ""),
            "doi": p.get("doi", ""),
            "has_pdf": bool(p.get("pdf_path")),
            "item_type": p.get("item_type", ""),
            "collections": p.get("collections", []),
            "keywords": [{"word": kw, "count": cnt} for kw, cnt in keywords],
            "label": label,   # 必读 / 值得看 / 可跳过 / ""（未标注）
        }
        records.append(rec)

    # 追加写入 JSONL
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"[OK] 已追加 {len(records)} 条记录到 {output_path}")
    return records


def main():
    parser = argparse.ArgumentParser(description="记录 Zotero 文献处理关键词到历史数据库")
    parser.add_argument("--input", required=True,
                        help="zotero_today.json 路径")
    parser.add_argument("--review-file", default=None,
                        help="daily-papers-review 生成的 Markdown 文件（用于读取必读/值得看/可跳过标签）")
    parser.add_argument("--output", default=None,
                        help="输出 JSONL 路径（默认：~/.workbuddy/skills/zotero-daily-intake/data/keyword_history.jsonl）")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    papers = data.get("papers", [])
    date_str = data.get("query_date", datetime.now().strftime("%Y-%m-%d"))

    if not papers:
        print("[INFO] 无文献记录，跳过关键词提取")
        return

    default_output = (
        Path(__file__).resolve().parents[1] / "data" / "keyword_history.jsonl"
    )
    output_path = Path(args.output) if args.output else default_output

    record(papers, args.review_file, output_path, date_str)


if __name__ == "__main__":
    main()
