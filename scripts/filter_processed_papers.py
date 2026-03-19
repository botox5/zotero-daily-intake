#!/usr/bin/env python3
"""
filter_processed_papers.py
过滤已处理的论文，检测 PDF 更新，返回需要处理的论文列表。

功能：
1. 读取当天抓取的论文列表
2. 与历史记录比对，过滤已处理的论文
3. 检测 PDF 更新：之前无 PDF、现在有 PDF → 标记为需要重新处理
4. 输出待处理论文 + 更新检测结果

用法：
  python3 filter_processed_papers.py --input /tmp/zotero_today.json --output /tmp/zotero_todo.json
"""

import json
import argparse
import sys
from pathlib import Path
from datetime import datetime

# ── 路径设置 ──────────────────────────────────────────────
_SHARED_DIR = Path(__file__).resolve().parents[2] / "_shared"

# 从配置读取 vault 路径
import json as _json
config_path = _SHARED_DIR / "user-config.json"
if config_path.exists():
    config = _json.loads(config_path.read_text())
    vault_path = Path(config.get("paths", {}).get("obsidian_vault", "")).expanduser()
else:
    vault_path = Path.home() / "Library/CloudStorage/OneDrive-个人/文档/2026踏实肯干/龙虾养殖基地/Zotero 文献阅读"

HISTORY_FILE = vault_path / "Daily Papers" / ".history.json"


def load_history() -> dict:
    """加载历史处理记录"""
    if not HISTORY_FILE.exists():
        return {"processed": {}, "pdf_status": {}}
    
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        # 兼容旧格式（数组）和新格式（对象）
        if isinstance(data, list):
            processed = {}
            pdf_status = {}
            for item in data:
                item_id = str(item.get("id", ""))
                if item_id:
                    processed[item_id] = {
                        "date": item.get("date", ""),
                        "title": item.get("title", ""),
                    }
                    # 历史记录中没有 PDF 状态，默认设为 None
                    pdf_status[item_id] = None
            return {"processed": processed, "pdf_status": pdf_status}
        return data
    except Exception as e:
        print(f"[WARN] 读取历史记录失败: {e}", file=sys.stderr)
        return {"processed": {}, "pdf_status": {}}


def normalize_id(item_id: str) -> str:
    """统一 ID 格式：去掉 zotero- 前缀"""
    if item_id.startswith("zotero-"):
        return item_id[7:]  # 去掉 "zotero-" 前缀
    return item_id


def filter_papers(papers: list[dict], history: dict) -> dict:
    """
    过滤论文，返回待处理列表
    
    返回结构：
    {
        "total_fetched": N,
        "already_processed": M,      # 已处理且无需更新的
        "need_reprocess": K,          # 需要重新处理的（PDF 有更新）
        "new_papers": L,              # 新论文
        "papers": [...]               # 合并后的待处理论文列表
    }
    """
    processed = history.get("processed", {})
    pdf_status = history.get("pdf_status", {})
    
    # 标准化处理：统一 ID 格式
    normalized_processed = {normalize_id(k): v for k, v in processed.items()}
    normalized_pdf_status = {normalize_id(k): v for k, v in pdf_status.items()}
    
    already_processed = []
    need_reprocess = []
    new_papers = []
    
    # 有效论文类型
    valid_item_types = {"journalArticle", "book", "bookSection", "conferencePaper", "report", "preprint", "thesis"}
    
    for paper in papers:
        item_id = str(paper.get("item_id", ""))
        current_pdf = paper.get("pdf_path")  # 当前 PDF 路径
        item_type = paper.get("item_type", "")
        
        if not item_id:
            continue
        
        # 跳过无效论文类型（note, attachment 等）
        if item_type not in valid_item_types:
            continue
        
        # 标准化 ID 用于匹配
        norm_id = normalize_id(item_id)
        
        # 情况1：之前已处理过
        if norm_id in normalized_processed:
            old_pdf = normalized_pdf_status.get(norm_id)
            
            # 情况1a：PDF 从无到有 → 需要重新处理
            if old_pdf is None and current_pdf is not None:
                paper["_reprocess_reason"] = "pdf_added"
                paper["_reprocess_note"] = "之前无 PDF，现已添加 PDF"
                need_reprocess.append(paper)
            # 情况1b：PDF 状态没变化 → 跳过
            else:
                already_processed.append(paper)
        # 情况2：新论文
        else:
            new_papers.append(paper)
    
    # 合并待处理论文（新论文 + 需要重新处理的）
    todo_papers = new_papers + need_reprocess
    
    return {
        "total_fetched": len(papers),
        "already_processed_count": len(already_processed),
        "need_reprocess_count": len(need_reprocess),
        "new_papers_count": len(new_papers),
        "papers": todo_papers,
        "skipped": already_processed,
        "reprocess_details": need_reprocess,
    }


def save_history_update(new_items: list[dict], pdf_updates: dict = None):
    """
    更新历史记录，追加新处理的论文和 PDF 状态
    pdf_updates: {item_id: pdf_path}  # 当前处理的论文的 PDF 状态
    """
    if not HISTORY_FILE.exists():
        history_data = []
    else:
        try:
            history_data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            if not isinstance(history_data, list):
                history_data = []
        except Exception:
            history_data = []
    
    # 构建 ID 到条目的映射（用于快速查找）- 标准化 ID
    existing_map = {normalize_id(item.get("id")): item for item in history_data if item.get("id")}
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    for paper in new_items:
        item_id = str(paper.get("item_id", ""))
        if not item_id:
            continue
        
        title = paper.get("title", "")
        
        # 标准化 ID
        norm_id = normalize_id(item_id)
        
        if norm_id in existing_map:
            # 更新现有条目
            existing_map[norm_id]["title"] = title
            # 不更新 date，保持最早的日期
        else:
            # 添加新条目
            history_data.append({
                "id": norm_id,  # 使用标准化 ID
                "date": today,
                "title": title,
            })
    
    # 更新 PDF 状态
    if pdf_updates:
        # 读取完整的 PDF 状态历史
        pdf_history_file = HISTORY_FILE.parent / ".pdf_history.json"
        if pdf_history_file.exists():
            try:
                pdf_history = json.loads(pdf_history_file.read_text(encoding="utf-8"))
            except Exception:
                pdf_history = {}
        else:
            pdf_history = {}
        
        for item_id, pdf_path in pdf_updates.items():
            # 标准化 ID
            norm_id = normalize_id(item_id)
            pdf_history[norm_id] = pdf_path
        
        pdf_history_file.write_text(
            json.dumps(pdf_history, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    
    # 保存更新后的历史（只保留最近 30 天）
    cutoff_date = datetime.now()
    from datetime import timedelta
    cutoff = cutoff_date - timedelta(days=30)
    
    filtered_history = []
    for item in history_data:
        try:
            item_date = datetime.strptime(item.get("date", ""), "%Y-%m-%d")
            if item_date >= cutoff:
                filtered_history.append(item)
        except Exception:
            filtered_history.append(item)
    
    HISTORY_FILE.write_text(
        json.dumps(filtered_history, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description="过滤已处理的论文，检测 PDF 更新")
    parser.add_argument("--input", required=True, help="当天抓取的论文 JSON 文件")
    parser.add_argument("--output", required=True, help="输出待处理论文 JSON 文件")
    parser.add_argument("--skip-update", action="store_true", help="跳过历史记录更新")
    args = parser.parse_args()
    
    # 读取输入
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[ERROR] 输入文件不存在: {input_path}", file=sys.stderr)
        sys.exit(1)
    
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[ERROR] 解析输入文件失败: {e}", file=sys.stderr)
        sys.exit(1)
    
    papers = data.get("papers", [])
    
    # 加载历史记录
    history = load_history()
    
    # 过滤
    result = filter_papers(papers, history)
    
    # 输出
    output_data = {
        "query_date": data.get("query_date", ""),
        "filter_result": {
            "total_fetched": result["total_fetched"],
            "already_processed": result["already_processed_count"],
            "need_reprocess": result["need_reprocess_count"],
            "new_papers": result["new_papers_count"],
            "will_process": len(result["papers"]),
        },
        "papers": result["papers"],
    }
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # 打印摘要
    print(f"[OK] 论文过滤完成")
    print(f"     抓取总数: {result['total_fetched']}")
    print(f"     已处理(跳过): {result['already_processed_count']}")
    print(f"     PDF 更新需重新处理: {result['need_reprocess_count']}")
    print(f"     新论文: {result['new_papers_count']}")
    print(f"     待处理总计: {len(result['papers'])}")
    
    if result["need_reprocess_count"] > 0:
        print(f"\n[!] 以下论文 PDF 有更新，需要重新处理:")
        for p in result["reprocess_details"]:
            print(f"    - {p['item_id']}: {p['title'][:50]}...")
    
    # 更新历史记录
    if not args.skip_update and result["papers"]:
        pdf_updates = {str(p["item_id"]): p.get("pdf_path") for p in result["papers"]}
        save_history_update(result["papers"], pdf_updates)
        print(f"\n[OK] 历史记录已更新")


if __name__ == "__main__":
    main()
