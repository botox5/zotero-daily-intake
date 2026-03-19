#!/usr/bin/env python3
"""
analyze_keywords.py
分析历史关键词数据，生成兴趣画像；或对输入文献进行兴趣预打分。

用法：
  # 生成/更新兴趣画像
  python3 analyze_keywords.py --mode build-profile \
      --input ~/.workbuddy/skills/zotero-daily-intake/data/keyword_history.jsonl \
      --output ~/.workbuddy/skills/zotero-daily-intake/data/interest_profile.json

  # 对今日文献预打分
  python3 analyze_keywords.py --mode score \
      --input /tmp/daily_papers_enriched.json \
      --profile ~/.workbuddy/skills/zotero-daily-intake/data/interest_profile.json \
      --output /tmp/daily_papers_enriched.json

  # 打印画像摘要（供人阅读）
  python3 analyze_keywords.py --mode summary \
      --profile ~/.workbuddy/skills/zotero-daily-intake/data/interest_profile.json
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

DEFAULT_HISTORY = (
    Path(__file__).resolve().parents[1] / "data" / "keyword_history.jsonl"
)
DEFAULT_PROFILE = (
    Path(__file__).resolve().parents[1] / "data" / "interest_profile.json"
)

# ── 标签映射到权重 ──────────────────────────────────────────────
LABEL_WEIGHT = {
    "必读": 3.0,
    "值得看": 1.5,
    "可跳过": -1.0,
    "": 0.5,   # 无标注（PDF 精读组）按正向处理
}

# ── 分类偏好权重（来自历史记录）──────────────────────────────────
CATEGORY_BASE_SCORE = 2.0


def load_history(history_path: Path) -> list[dict]:
    """加载 JSONL 历史记录。"""
    if not history_path.exists():
        return []
    records = []
    with open(history_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def build_profile(records: list[dict]) -> dict:
    """
    从历史记录构建兴趣画像。

    画像结构：
    {
      "version": 1,
      "built_at": "2026-03-19",
      "total_records": N,
      "keyword_scores": {"eeg": 12.5, "fatigue": 8.0, ...},   # 加权词频
      "category_scores": {"Human Factors/EEG": 5.0, ...},
      "blacklist_keywords": ["review", "survey", ...],          # "可跳过"高频词
      "label_distribution": {"必读": N, "值得看": N, "可跳过": N, "": N},
      "top_must_read_keywords": [...],   # 必读文献最高频关键词
      "top_skip_keywords": [...],        # 可跳过文献最高频关键词
    }
    """
    from datetime import date

    if not records:
        return {}

    # 统计各标签对应的关键词权重
    kw_score: dict[str, float] = defaultdict(float)
    must_read_kw: Counter = Counter()
    skip_kw: Counter = Counter()
    label_dist: dict[str, int] = Counter()
    category_cnt: dict[str, float] = defaultdict(float)

    for rec in records:
        label = rec.get("label", "")
        weight = LABEL_WEIGHT.get(label, 0.5)
        label_dist[label] += 1

        for kw_entry in rec.get("keywords", []):
            word = kw_entry.get("word", "")
            cnt = kw_entry.get("count", 1)
            if not word:
                continue
            kw_score[word] += weight * cnt
            if label == "必读":
                must_read_kw[word] += cnt
            elif label == "可跳过":
                skip_kw[word] += cnt

        for coll in rec.get("collections", []):
            if coll:
                category_cnt[coll] += max(weight, 0.5)

    # 计算"黑名单"：在"可跳过"中高频但在"必读"中低频的词
    blacklist = []
    for word, skip_cnt in skip_kw.most_common(50):
        must_cnt = must_read_kw.get(word, 0)
        if skip_cnt > 2 and skip_cnt > must_cnt * 2:
            blacklist.append(word)

    profile = {
        "version": 1,
        "built_at": date.today().isoformat(),
        "total_records": len(records),
        "keyword_scores": dict(
            sorted(kw_score.items(), key=lambda x: -x[1])[:300]
        ),
        "category_scores": dict(
            sorted(category_cnt.items(), key=lambda x: -x[1])
        ),
        "blacklist_keywords": blacklist[:30],
        "label_distribution": dict(label_dist),
        "top_must_read_keywords": [w for w, _ in must_read_kw.most_common(40)],
        "top_skip_keywords": [w for w, _ in skip_kw.most_common(40)],
    }
    return profile


def score_paper(paper: dict, profile: dict) -> tuple[float, list[str]]:
    """
    对单篇论文计算兴趣分（0-10）和命中的标签。
    """
    if not profile:
        return 5.0, []

    kw_scores = profile.get("keyword_scores", {})
    cat_scores = profile.get("category_scores", {})
    blacklist = set(profile.get("blacklist_keywords", []))
    must_kws = set(profile.get("top_must_read_keywords", []))

    # 提取论文词
    text = " ".join([
        paper.get("title", ""),
        paper.get("abstract", ""),
    ]).lower()
    en_words = set(re.findall(r'\b[a-z]{3,}\b', text))
    zh_words = set(re.findall(r'[\u4e00-\u9fff]{2,4}', text))
    all_words = en_words | zh_words

    # 关键词匹配得分
    kw_hit_score = 0.0
    hit_tags = []
    for w in all_words:
        if w in kw_scores:
            kw_hit_score += kw_scores[w]
            if w in must_kws:
                hit_tags.append(w)

    # 黑名单惩罚
    blacklist_hits = all_words & blacklist
    penalty = len(blacklist_hits) * 2.0

    # 分类偏好得分
    cat_score = 0.0
    for coll in paper.get("collections", []):
        if coll in cat_scores:
            cat_score += cat_scores[coll]

    # 综合得分（归一化到 0-10）
    raw_score = kw_hit_score * 0.01 + cat_score * 0.5 - penalty
    normalized = max(0.0, min(10.0, 5.0 + raw_score * 0.3))

    return round(normalized, 2), hit_tags[:10]


def mode_build_profile(args):
    history_path = Path(args.input) if args.input else DEFAULT_HISTORY
    output_path = Path(args.output) if args.output else DEFAULT_PROFILE

    records = load_history(history_path)
    if not records:
        print(f"[WARN] 历史记录为空（{history_path}），无法生成画像")
        return

    profile = build_profile(records)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2))
    print(f"[OK] 兴趣画像已生成 → {output_path}")
    print(f"     共 {profile['total_records']} 条记录")
    print(f"     标签分布: {profile['label_distribution']}")
    print(f"     Top 必读关键词: {profile['top_must_read_keywords'][:10]}")
    print(f"     黑名单词: {profile['blacklist_keywords'][:10]}")


def mode_score(args):
    input_path = Path(args.input)
    profile_path = Path(args.profile) if args.profile else DEFAULT_PROFILE

    if not input_path.exists():
        print(f"[ERROR] 输入文件不存在: {input_path}", file=sys.stderr)
        sys.exit(1)

    profile = {}
    if profile_path.exists():
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    else:
        print(f"[WARN] 兴趣画像不存在（{profile_path}），将跳过打分，所有文献得 5.0 分")

    data = json.loads(input_path.read_text(encoding="utf-8"))
    papers = data.get("papers", data if isinstance(data, list) else [])

    for p in papers:
        score, tags = score_paper(p, profile)
        p["interest_score"] = score
        p["interest_tags"] = tags

    # 原地写回
    output_path = Path(args.output) if args.output else input_path
    if isinstance(data, list):
        output_path.write_text(json.dumps(papers, ensure_ascii=False, indent=2))
    else:
        data["papers"] = papers
        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    print(f"[OK] 已对 {len(papers)} 篇文献打分 → {output_path}")
    # 打印得分分布
    scores = [p.get("interest_score", 5.0) for p in papers]
    hi = sum(1 for s in scores if s >= 7)
    mid = sum(1 for s in scores if 4 <= s < 7)
    lo = sum(1 for s in scores if s < 4)
    print(f"     高关注(≥7): {hi}篇  中关注(4-7): {mid}篇  低关注(<4): {lo}篇")


def mode_summary(args):
    profile_path = Path(args.profile) if args.profile else DEFAULT_PROFILE
    if not profile_path.exists():
        print(f"[INFO] 兴趣画像尚未生成（{profile_path}）")
        print("  运行 `python3 analyze_keywords.py --mode build-profile` 生成")
        return

    p = json.loads(profile_path.read_text(encoding="utf-8"))
    print(f"\n📊 兴趣画像摘要（构建于 {p.get('built_at','未知')}，共 {p.get('total_records',0)} 篇）")
    print(f"\n标签分布: {p.get('label_distribution', {})}")
    print(f"\nTop 必读关键词（前20）:")
    for i, kw in enumerate(p.get("top_must_read_keywords", [])[:20], 1):
        score = p.get("keyword_scores", {}).get(kw, 0)
        print(f"  {i:2d}. {kw:25s} (权重 {score:.1f})")
    print(f"\nTop 偏好分类:")
    for coll, score in list(p.get("category_scores", {}).items())[:10]:
        print(f"  {coll:40s} (权重 {score:.1f})")
    print(f"\n黑名单关键词（可跳过特征词）:")
    print(f"  {', '.join(p.get('blacklist_keywords', []))}")


def main():
    parser = argparse.ArgumentParser(description="Zotero 关键词兴趣画像分析工具")
    parser.add_argument("--mode", choices=["build-profile", "score", "summary"],
                        required=True, help="运行模式")
    parser.add_argument("--input", default=None,
                        help="输入文件路径（build-profile: JSONL历史；score: enriched JSON）")
    parser.add_argument("--output", default=None,
                        help="输出文件路径")
    parser.add_argument("--profile", default=None,
                        help="兴趣画像 JSON 路径（score/summary 模式使用）")
    args = parser.parse_args()

    if args.mode == "build-profile":
        mode_build_profile(args)
    elif args.mode == "score":
        mode_score(args)
    elif args.mode == "summary":
        mode_summary(args)


if __name__ == "__main__":
    main()
