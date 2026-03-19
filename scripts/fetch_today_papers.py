#!/usr/bin/env python3
"""
fetch_today_papers.py
查询 Zotero 数据库中今天（或指定日期）新添加的文献，输出 JSON 供后续 skill 使用。

用法：
  python3 fetch_today_papers.py                    # 查询今天
  python3 fetch_today_papers.py --date 2026-03-19  # 指定日期
  python3 fetch_today_papers.py --days 2           # 最近 N 天
  python3 fetch_today_papers.py --json             # 输出 JSON 格式
  python3 fetch_today_papers.py --output /tmp/zotero_today.json  # 写入文件
"""

import sqlite3
import shutil
import argparse
import json
import sys
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── 路径设置 ──────────────────────────────────────────────
_SHARED_DIR = Path(__file__).resolve().parents[2] / "_shared"

def _load_zotero_paths():
    """从 user-config.json 读取 Zotero 路径，若未配置则自动探测。"""
    config_path = _SHARED_DIR / "user-config.json"
    local_config_path = _SHARED_DIR / "user-config.local.json"

    config = {}
    if config_path.exists():
        try:
            import json as _json
            config = _json.loads(config_path.read_text())
            if local_config_path.exists():
                local = _json.loads(local_config_path.read_text())
                # 深度合并 paths 节
                config.get("paths", {}).update(local.get("paths", {}))
        except Exception:
            pass

    paths = config.get("paths", {})
    zotero_db_str = paths.get("zotero_db", "")

    # ── 自动探测 ──
    if not zotero_db_str:
        candidates = [
            Path.home() / "Zotero" / "zotero.sqlite",
            Path.home() / "Library" / "Application Support" / "Zotero" / "zotero.sqlite",
        ]
        for c in candidates:
            if c.exists():
                zotero_db_str = str(c)
                break

    if not zotero_db_str:
        print("[ERROR] 找不到 Zotero 数据库，请在 _shared/user-config.json 中设置 zotero_db 路径", file=sys.stderr)
        sys.exit(1)

    zotero_db = Path(zotero_db_str).expanduser()
    storage_dir = zotero_db.parent / "storage"
    return zotero_db, storage_dir

ZOTERO_DB, STORAGE_DIR = _load_zotero_paths()

TEMP_DB = Path("/tmp/zotero_today_readonly.sqlite")


def copy_db() -> sqlite3.Connection:
    """复制数据库副本以避免锁"""
    if not ZOTERO_DB.exists():
        print(f"[ERROR] Zotero 数据库不存在: {ZOTERO_DB}", file=sys.stderr)
        sys.exit(1)
    shutil.copy(ZOTERO_DB, TEMP_DB)
    return sqlite3.connect(TEMP_DB)


def get_collection_path(conn: sqlite3.Connection, collection_id: int) -> str:
    """获取分类的完整路径，如 '3-Robotics/VLA'"""
    cursor = conn.cursor()
    cursor.execute("SELECT collectionID, collectionName, parentCollectionID FROM collections")
    collections = {row[0]: {"name": row[1], "parent": row[2]} for row in cursor.fetchall()}
    path_parts = []
    current = collection_id
    while current:
        if current in collections:
            path_parts.insert(0, collections[current]["name"])
            current = collections[current]["parent"]
        else:
            break
    return "/".join(path_parts)


def get_item_info(conn: sqlite3.Connection, item_id: int) -> dict:
    """获取单篇文献的详细字段"""
    cursor = conn.cursor()

    # 所有 metadata 字段
    cursor.execute("""
        SELECT f.fieldName, idv.value
        FROM itemData id
        JOIN itemDataValues idv ON id.valueID = idv.valueID
        JOIN fields f ON id.fieldID = f.fieldID
        WHERE id.itemID = ?
    """, (item_id,))
    fields = {row[0]: row[1] for row in cursor.fetchall()}

    # 作者
    cursor.execute("""
        SELECT c.lastName, c.firstName
        FROM itemCreators ic
        JOIN creators c ON ic.creatorID = c.creatorID
        JOIN creatorTypes ct ON ic.creatorTypeID = ct.creatorTypeID
        WHERE ic.itemID = ? AND ct.creatorType = 'author'
        ORDER BY ic.orderIndex
    """, (item_id,))
    authors = [f"{r[0]}, {r[1]}" if r[1] else r[0] for r in cursor.fetchall()]

    # 所在分类
    cursor.execute("""
        SELECT c.collectionID
        FROM collections c
        JOIN collectionItems ci ON c.collectionID = ci.collectionID
        WHERE ci.itemID = ?
    """, (item_id,))
    collection_ids = [r[0] for r in cursor.fetchall()]
    collection_paths = [get_collection_path(conn, cid) for cid in collection_ids]

    # PDF 附件
    cursor.execute("""
        SELECT ia.path, items.key
        FROM itemAttachments ia
        JOIN items ON ia.itemID = items.itemID
        WHERE ia.parentItemID = ? AND ia.contentType = 'application/pdf'
        LIMIT 1
    """, (item_id,))
    pdf_row = cursor.fetchone()
    pdf_path = None
    if pdf_row:
        path, key = pdf_row
        if path:
            # 处理两种类型的 PDF：
            # 1. storage:xxx - Zotero storage 目录中的文件
            # 2. /absolute/path - 外部链接的文件
            if path.startswith("storage:"):
                filename = path.replace("storage:", "")
                full_path = STORAGE_DIR / key / filename
                pdf_path = str(full_path) if full_path.exists() else None
            elif path.startswith("/"):
                # 外部链接的文件（绝对路径）
                full_path = Path(path)
                pdf_path = str(full_path) if full_path.exists() else None

    # 摘要单独获取（可能很长）
    abstract = fields.pop("abstractNote", "") or ""

    return {
        "item_id": item_id,
        "title": fields.get("title", "Unknown"),
        "authors": authors,
        "date": fields.get("date", ""),
        "url": fields.get("url", ""),
        "doi": fields.get("DOI", ""),
        "abstract": abstract,
        "publication": fields.get("publicationTitle", fields.get("bookTitle", "")),
        "extra": fields.get("extra", ""),   # 含 arXiv ID 等附加信息
        "collections": collection_paths,
        "pdf_path": pdf_path,
    }


def fetch_papers_added_since(conn: sqlite3.Connection, since_dt: datetime, until_dt: datetime | None = None) -> list[dict]:
    """
    查询在 [since_dt, until_dt) 时间段内添加到 Zotero 的所有文献。
    dateAdded 字段格式为 ISO8601 UTC，如 '2026-03-19 10:23:45'。
    """
    cursor = conn.cursor()

    since_str = since_dt.strftime("%Y-%m-%d %H:%M:%S")
    if until_dt is None:
        until_dt = since_dt + timedelta(days=1)
    until_str = until_dt.strftime("%Y-%m-%d %H:%M:%S")

    # 只查主文献条目（排除附件 itemTypeID=14、注释 itemTypeID=1 等）
    # 常见主文献 itemTypeID: 2=journalArticle, 3=book, 4=bookSection, 16=conferencePaper, 17=report, 35=preprint
    cursor.execute("""
        SELECT i.itemID, i.dateAdded, it.typeName
        FROM items i
        JOIN itemTypes it ON i.itemTypeID = it.itemTypeID
        WHERE i.dateAdded >= ? AND i.dateAdded < ?
          AND i.itemTypeID NOT IN (1, 14)   -- 排除 note 和 attachment
          AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
        ORDER BY i.dateAdded DESC
    """, (since_str, until_str))

    rows = cursor.fetchall()
    papers = []
    for row in rows:
        item_id, date_added, type_name = row
        info = get_item_info(conn, item_id)
        info["date_added"] = date_added
        info["item_type"] = type_name
        papers.append(info)

    return papers


def print_table(papers: list[dict]) -> None:
    """控制台表格输出"""
    print(f"\n共找到 {len(papers)} 篇文献\n")
    print(f"{'ID':>6}  {'添加时间':>19}  {'分类':30}  标题")
    print("-" * 110)
    for p in papers:
        coll = " / ".join(p["collections"])[:28] if p["collections"] else "无分类"
        title = p["title"][:55] if p["title"] else "?"
        print(f"{p['item_id']:>6}  {p['date_added']:>19}  {coll:30}  {title}")


def main():
    parser = argparse.ArgumentParser(
        description="查询 Zotero 当天（或指定日期/天数）新添加的文献"
    )
    parser.add_argument("--date", default=None,
                        help="指定日期 YYYY-MM-DD（默认今天）")
    parser.add_argument("--days", type=int, default=1,
                        help="查询最近 N 天（默认 1 = 仅今天）")
    parser.add_argument("--json", action="store_true",
                        help="以 JSON 格式输出到 stdout")
    parser.add_argument("--output", default=None,
                        help="将 JSON 结果写入文件（如 /tmp/zotero_today.json）")
    args = parser.parse_args()

    # 确定时间范围（使用北京时间 UTC+8）
    if args.date:
        base = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        from datetime import timezone as _tz
        CST = _tz(timedelta(hours=8))
        now_cst = datetime.now(_tz(timedelta(hours=8)))
        base = now_cst.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)

    since_dt = base - timedelta(days=args.days - 1)
    until_dt = base + timedelta(days=1)  # 包含当天结束

    conn = copy_db()
    try:
        papers = fetch_papers_added_since(conn, since_dt, until_dt)
    finally:
        conn.close()

    result = {
        "query_date": base.strftime("%Y-%m-%d"),
        "days": args.days,
        "total": len(papers),
        "papers": papers,
    }

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"[OK] 已写入 {out_path}，共 {len(papers)} 篇文献")
    elif args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_table(papers)
        if not papers:
            print("（今天暂无新添加的文献）")


if __name__ == "__main__":
    main()
