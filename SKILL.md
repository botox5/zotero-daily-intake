---
name: zotero-daily-intake
description: |
  读取 Zotero 数据库，找到当天（或指定日期/最近 N 天）新添加的所有文献，
  依次调用 paper-reader 阅读每篇文献、daily-papers-review 生成点评推荐、
  daily-papers-notes 补充概念库并生成完整笔记、generate-mocs 刷新目录索引。

  触发词：
  - "处理今天的 Zotero 新文献"
  - "读一下今天 Zotero 新加的论文"
  - "Zotero 今日文献入库"
  - "今天 Zotero 添加了哪些文献"
  - "跑一下 Zotero 文献处理流水线"
---

# Zotero 当日文献处理流水线

从 Zotero 数据库抓取当天（或指定时间段）新添加的文献，按"有无 PDF"分流处理，完成阅读→笔记→点评→索引的全自动流水线，并记录关键词兴趣画像以优化长期筛选。

---

## Step 0：读取共享配置

先读取 `../_shared/user-config.json`；若 `../_shared/user-config.local.json` 存在，用它覆盖默认值。

生成并在后续统一使用的变量：

- `VAULT_PATH`
- `NOTES_PATH = {VAULT_PATH}/{paper_notes_folder}`
- `CONCEPTS_PATH = {VAULT_PATH}/{concepts_folder}`  # Concepts 在 vault 根目录下
- `DAILY_PAPERS_PATH = {VAULT_PATH}/{daily_papers_folder}`
- `ZOTERO_DB`
- `ZOTERO_STORAGE`
- `AUTO_REFRESH_INDEXES`
- `GIT_COMMIT_ENABLED`
- `GIT_PUSH_ENABLED`（只有在 `GIT_COMMIT_ENABLED=true` 时才可能为真）

同时读取关键词兴趣画像配置：

```python
keyword_profile = load_keyword_profile()  # 读 /tmp/zotero_keyword_profile.json（若存在）
```

---

## Step 1：抓取 Zotero 当日新增文献

运行抓取脚本，使用**北京时间（UTC+8）**判断"今天"：

```bash
python3 scripts/fetch_today_papers.py --output /tmp/zotero_today.json
```

**支持的参数**：
- 默认：查询今天（北京时间）新添加的文献
- `--date YYYY-MM-DD`：指定日期
- `--days N`：最近 N 天（如 `--days 3`）

**输出结构**（`/tmp/zotero_today.json`）：

```json
{
  "query_date": "2026-03-19",
  "days": 1,
  "total": 5,
  "papers": [
    {
      "item_id": 12345,
      "title": "...",
      "authors": ["Smith, John", "..."],
      "date": "2026",
      "url": "https://...",
      "doi": "10.xxxx/...",
      "abstract": "...",
      "publication": "...",
      "extra": "arXiv:2603.xxxxx",
      "collections": ["3-Robotics/VLA", "..."],
      "pdf_path": "/path/to/paper.pdf",
      "date_added": "2026-03-19 08:23:45",
      "item_type": "journalArticle"
    }
  ]
}
```

若 `total == 0`，告知用户今日 Zotero 暂无新增文献，流程终止。

---

## Step 1.5：过滤已处理论文（避免重复）

运行过滤脚本，自动跳过已处理的论文：

```bash
python3 scripts/filter_processed_papers.py \
  --input /tmp/zotero_today.json \
  --output /tmp/zotero_todo.json
```

**过滤逻辑**：
1. 读取历史记录（`.history.json`），找出之前已处理的论文
2. **已处理且 PDF 无变化**：跳过，不重复处理
3. **之前无 PDF、现在有 PDF**：标记为需要重新处理（生成完整笔记）
4. **新论文**：正常处理

**输出**（`/tmp/zotero_todo.json`）：

```json
{
  "query_date": "2026-03-19",
  "filter_result": {
    "total_fetched": 10,
    "already_processed": 5,
    "need_reprocess": 1,
    "new_papers": 4,
    "will_process": 5
  },
  "papers": [...]
}
```

**如果 `will_process == 0`**，说明今天没有需要处理的新论文，告知用户"今日 Zotero 无新论文需要处理"，流程终止。

---

## Step 2：展示文献列表，按 PDF 分流

读取 `/tmp/zotero_todo.json` 后，**自动按 `pdf_path` 是否存在分为两组**：

> **注意**：展示的是过滤后的待处理论文，不包含已跳过的重复论文。

```
📚 今日 Zotero 新增文献（共 N 篇）

【有本地 PDF - 完整阅读】共 A 篇
 # | 分类                  | 标题
---+-----------------------+----------------------------------------------------
 1 | Human Factors/EEG     | EEG-based driver fatigue detection using ...
 2 | ...                   | ...

【无本地 PDF - 摘要推荐】共 B 篇
 # | 有DOI | 有摘要 | 分类              | 标题
---+-------+--------+-------------------+--------------------------------------------
 1 |  ✓   |   ✓   | 无分类            | 基于 DeepSeek 与 RAG 的事故调查...
 2 |  ✓   |   ✓   | 无分类            | 非机动车道路交通安全研究现状...
```

**不需要等待用户确认，直接进入 Step 3/4 开始处理。** 若用户之前已明确"全部处理"，则跳过确认直接执行。

---

## Step 3：有 PDF 的文献 → paper-reader 完整笔记

对 `pdf_path` 不为空的每篇文献，调用 `paper-reader` skill 生成完整 Obsidian 笔记：

**来源优先级**（按顺序尝试）：
1. **本地 PDF**：直接传 `pdf_path`（最优先，质量最好）
2. **arXiv 链接**：从 `extra` 提取 `arXiv:XXXXXXX`，构造 `https://arxiv.org/abs/XXXXXXX`
3. **DOI 链接**：`https://doi.org/{doi}`
4. **原始 URL**：直接用 `url` 字段

**处理方式**：
- 使用 Task agent 调用 paper-reader（在独立 context 中运行，不消耗主 agent context）
- 每篇完成后记录：笔记文件名、提取的关键词/标签

**批量策略**：
- ≤ 5 篇：串行处理
- > 5 篇：默认串行，但每完成 5 篇输出一次进度报告

---

## Step 4：无 PDF 的文献 → 摘要推荐点评

对 `pdf_path` 为空的文献，**基于摘要和标题**生成批量推荐点评：

### 4a. 准备数据

```bash
python3 scripts/convert_to_enriched.py \
  --input /tmp/zotero_todo.json \
  --no-pdf-only \
  --output /tmp/daily_papers_enriched.json
```

### 4b. 关键词兴趣匹配（若有历史画像）

若 `scripts/analyze_keywords.py` 已生成过兴趣画像，用它对每篇论文预打分：

```bash
python3 scripts/analyze_keywords.py \
  --mode score \
  --input /tmp/daily_papers_enriched.json \
  --output /tmp/daily_papers_enriched.json
```

每篇论文会增加 `interest_score`（0-10）和 `interest_tags` 字段，供 daily-papers-review 参考。

### 4c. 调用 daily-papers-review 生成点评

调用 `daily-papers-review` skill，生成今日推荐点评，要求：
- 每篇标注 **必读 / 值得看 / 可跳过**（结合 `interest_score` 和内容判断）
- 必读：与核心研究方向高度相关，有新方法或重要发现
- 值得看：相关领域但偏外围，或有趣但非核心
- 可跳过：重复性工作、相关度低、或无摘要/信息太少
- 保存到 `{DAILY_PAPERS_PATH}/YYYY-MM-DD-Zotero入库.md`

---

## Step 5：记录关键词兴趣数据

每次处理完成后，运行关键词记录脚本，把本次处理的关键词、标题词频、分类等元数据追加到历史数据库：

```bash
python3 scripts/record_keywords.py \
  --input /tmp/zotero_todo.json \
  --review-file {DAILY_PAPERS_PATH}/YYYY-MM-DD-Zotero入库.md \
  --output ~/.workbuddy/skills/zotero-daily-intake/data/keyword_history.jsonl
```

**记录内容**：
- 日期、论文数量
- 每篇论文的：标题词频、摘要关键词（TF-IDF 提取）、分类路径、DOI、最终标注（必读/值得看/可跳过）
- PDF 组文献的：paper-reader 提取的关键词/标签

**每累计 7 天**，自动触发一次关键词分析：

```bash
python3 scripts/analyze_keywords.py \
  --mode build-profile \
  --input ~/.workbuddy/skills/zotero-daily-intake/data/keyword_history.jsonl \
  --output ~/.workbuddy/skills/zotero-daily-intake/data/interest_profile.json
```

生成兴趣画像文件 `interest_profile.json`，包含高频关键词权重、偏好分类、"可跳过"词黑名单等，供下次处理时预筛选。

---

## Step 6：补充概念库（daily-papers-notes）

若 Step 3 或 Step 4 生成了新笔记/推荐文件，调用 `daily-papers-notes` skill：
- 概念库补充（提取 `[[双链]]` 并创建缺失概念笔记）
- 笔记质量验证
- 链接回填

---

## Step 7：刷新 MOC 目录索引

完成所有笔记后，调用 `generate-mocs` skill 刷新 Obsidian 目录页。

只有在 `AUTO_REFRESH_INDEXES=true` 时自动执行（手动触发此 skill 时不受此开关影响）。

---

## Step 8：Git 提交（可选）

仅当 `GIT_COMMIT_ENABLED=true` 且有 staged changes 时执行：

```bash
cd {VAULT_PATH} && git add -A && git commit -m "zotero intake: YYYY-MM-DD (A+B papers)"
```

---

## 完成汇报

```
✅ Zotero 文献处理完成（YYYY-MM-DD）

📊 过滤统计：
   ├─ 抓取总数：N 篇
   ├─ 已处理(跳过)：M 篇
   └─ 实际处理：K 篇

📥 本次处理：K 篇文献
   ├─ 有 PDF → 完整笔记：A 篇
   └─ 无 PDF → 摘要推荐：B 篇（必读 X / 值得看 Y / 可跳过 Z）

📝 新增笔记：A 篇
📋 推荐点评：{DAILY_PAPERS_PATH}/YYYY-MM-DD-Zotero入库.md
💡 新增概念：N 个
🔄 更新目录：N 个 MOC
🏷  关键词记录：已追加到 data/keyword_history.jsonl
```

---

## 错误处理

| 情况 | 处理方式 |
|------|----------|
| Zotero DB 路径未配置 | 提示用户在 `user-config.json` 设置 `zotero_db` |
| Zotero DB 不存在 | 提示路径，建议检查 Zotero 是否安装 |
| 文献无 PDF 且无 URL/DOI/摘要 | 记为"信息不足"，在汇报中列出 |
| paper-reader 生成笔记失败 | 记录失败原因，继续处理剩余文献，汇报时列出失败条目 |
| context 接近上限 | 先落盘已完成内容，明确告知用户剩余篇数，建议新会话继续 |

---

## 脚本说明

### `scripts/fetch_today_papers.py`

查询 Zotero 数据库中当天（北京时间 UTC+8）新添加的文献，输出 JSON。

```bash
python3 scripts/fetch_today_papers.py --help
```

### `scripts/convert_to_enriched.py`

将 `zotero_today.json` 转换为 `daily_papers_enriched.json` 格式（兼容 daily-papers-review）。

支持 `--no-pdf-only` 参数，只转换无 PDF 的文献。

### `scripts/record_keywords.py`

提取本次处理文献的关键词并追加到 `data/keyword_history.jsonl`。

```bash
python3 scripts/record_keywords.py --help
```

### `scripts/analyze_keywords.py`

分析历史关键词数据，生成兴趣画像；或对输入文献进行兴趣预打分。

```bash
python3 scripts/analyze_keywords.py --mode build-profile  # 生成画像
python3 scripts/analyze_keywords.py --mode score          # 打分
```

---

## 与其他 skill 的关系

| Skill | 调用时机 | 说明 |
|-------|----------|------|
| `paper-reader` | Step 3（有 PDF 的每篇） | 阅读全文、生成 Obsidian 笔记、维护概念库 |
| `daily-papers-review` | Step 4（无 PDF 的批量） | 基于摘要生成推荐点评，标注必读/值得看/可跳过 |
| `daily-papers-notes` | Step 6 | 概念补充、质量验证、链接回填 |
| `generate-mocs` | Step 7 | 刷新论文和概念的 MOC 目录索引 |
