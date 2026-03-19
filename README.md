# zotero-daily-intake
Zotero 论文归档完整解决方案：自动抓取 Zotero 新增文献，生成 Obsidian 笔记，更新概念库和 MOC 索引。
  - 感谢huangkiki 制作的 dailypaper-skills ，在本技能中我做了引用，大家可以去这里膜拜一下。
---
# name: zotero-daily-intake
# description: |
  Zotero 论文归档完整解决方案：自动抓取 Zotero 新增文献，生成 Obsidian 笔记，更新概念库和 MOC 索引。
  
  触发词：
  - "处理今天的 Zotero 新文献"
  - "跑一下 Zotero 文献处理流水线"
  - "Zotero 今日文献入库"
---

# Zotero 论文归档完整解决方案

本文档详细介绍如何配置和使用 Zotero + Obsidian 论文归档流水线。

---

## 第一部分：软件安装与配置

### 1.1 Zotero 安装与配置

#### 安装 Zotero

1. **下载 Zotero**：
   - 官网：https://www.zotero.org/
   - 选择对应操作系统的版本（Windows/macOS/Linux）
   - macOS 推荐使用 `.dmg` 安装包

2. **安装步骤**：
   ```bash
   # macOS 也可以用 Homebrew 安装
   brew install --cask zotero
   ```

3. **首次启动配置**：
   - 创建免费 Zotero 账户（用于同步）
   - 登录后设置同步
   - 安装 Zotero Connector 浏览器插件（Chrome/Firefox/Edge）

#### Zotero 数据库位置

Zotero 使用 SQLite 数据库存储所有文献数据：

| 操作系统 | 默认路径 |
|---------|---------|
| **macOS** | `~/Zotero/zotero.sqlite` |
| **Windows** | `C:\Users\{用户名}\Zotero\zotero.sqlite` |
| **Linux** | `~/.zotero/zotero.sqlite` |

**Zotero 存储目录结构**：

```
~/Zotero/
├── zotero.sqlite          # 主数据库（文献元数据）
├── storage/               # PDF 附件存储
│   ├── XXXXXXX/          # 每个条目一个文件夹
│   │   └── *.pdf         # PDF 文件
│   └── ...
├── favorites/             # 收藏
├── groups/                # 组同步数据
└── ...                    # 其他配置
```

#### 外部链接 PDF 配置

如果你的 PDF 不在 Zotero storage 目录，可以创建**外部链接**：

1. 在 Zotero 中右键文献 →「添加附件」→「链接已存在的文件」
2. 选择本地 PDF（如 `~/Documents/papers/xxx.pdf`）
3. 数据库中记录的是**绝对路径**，格式如 `/Users/xxx/Documents/papers/xxx.pdf`

**本流水线支持两种 PDF 路径**：
- `storage:XXXXXXX/xxx.pdf` → Zotero storage 目录
- `/absolute/path/to/xxx.pdf` → 外部链接文件

---

### 1.2 Obsidian 安装与配置

#### 安装 Obsidian

1. **下载 Obsidian**：
   - 官网：https://obsidian.md/
   - 选择对应操作系统版本

2. **创建Vault（知识库）**：
   - 首次启动选择「创建新库」
   - 选择库存储位置（如 `~/Documents/Obsidian`）

#### 推荐目录结构

```
~/Documents/Obsidian/
├── INDEX.md                    # 知识库首页
├── Concepts/                   # 概念笔记目录
│   ├── 概念A.md
│   ├── 概念B.md
│   └── MOC-概念.md            # 概念索引
├── Paper Notes/                # 论文笔记目录
│   ├── _待整理/               # 待整理笔记
│   ├── MOC-论文笔记.md        # 论文索引
│   └── 论文A.md
└── Daily Papers/              # 每日推荐
    ├── 2026-03-19-Zotero入库.md
    └── .history.json          # 处理历史
```

---

## 第二部分：配置文件设置

### 2.1 配置文件位置

配置文件位于 `~/.workbuddy/skills/_shared/`：

```
~/.workbuddy/skills/_shared/
├── user-config.json           # 主配置文件
├── user-config.local.json     # 本地覆盖配置（可选）
├── generate_concept_mocs.py   # 概念 MOC 生成
├── generate_paper_mocs.py    # 论文 MOC 生成
└── convert_concepts.py        # 概念格式转换
```

### 2.2 配置文件详解

#### user-config.json

```json
{
  "paths": {
    "obsidian_vault": "~/Documents/Obsidian",
    "zotero_db": "~/Zotero/zotero.sqlite",
    "paper_notes_folder": "Paper Notes",
    "concepts_folder": "Concepts",
    "daily_papers_folder": "Daily Papers"
  },
  "automation": {
    "auto_refresh_indexes": true,
    "git_commit_enabled": false,
    "git_push_enabled": false
  }
}
```

#### 配置项说明

| 配置项 | 说明 | 示例 |
|-------|------|------|
| `obsidian_vault` | Obsidian 库根目录 | `~/Documents/Obsidian` |
| `zotero_db` | Zotero SQLite 数据库路径 | `~/Zotero/zotero.sqlite` |
| `paper_notes_folder` | 论文笔记文件夹名 | `Paper Notes` |
| `concepts_folder` | 概念笔记文件夹名 | `Concepts` |
| `daily_papers_folder` | 每日推荐文件夹名 | `Daily Papers` |
| `auto_refresh_indexes` | 处理完成后自动刷新 MOC | `true`/`false` |
| `git_commit_enabled` | 自动 Git 提交 | `true`/`false` |
| `git_push_enabled` | 自动 Git 推送 | `true`/`false` |

### 2.3 关键词兴趣配置（可选）

在 `user-config.json` 的 `daily_papers.keywords` 中配置你的研究兴趣：

```json
{
  "daily_papers": {
    "keywords": [
      "driver fatigue", "drowsiness detection",
      "cognitive load", "mental workload",
      "emotional labor", "occupational safety"
    ],
    "negative_keywords": [
      "drug discovery", "cancer", "surgery"
    ],
    "domain_boost_keywords": [
      "state of the art", "sota", "novel method"
    ]
  }
}
```

---

## 第三部分：数据库详解

### 3.1 Zotero 数据库结构

Zotero 使用 SQLite 数据库，主要表结构：

#### items 表（文献）

```sql
-- 主要字段
itemID          -- 唯一ID
key             -- 全局唯一键（用于同步）
itemTypeID      -- 文献类型（journalArticle, book, etc.）
dateAdded       -- 添加日期
dateModified    -- 修改日期
```

#### itemTypes 表（文献类型）

```sql
itemTypeID      -- 类型ID
typeName        -- 类型名：journalArticle, book, conferencePaper, etc.
```

#### itemsData 表（文献数据）

```sql
itemID          -- 关联的 items 表
fieldID         -- 字段ID
value           -- 值（可能是文本或外键）
```

#### itemAttachments 表（附件）

```sql
itemID          -- 附件ID
parentItemID    -- 父文献ID
contentType     -- 内容类型（application/pdf）
path            -- 存储路径
linkMode        -- 链接模式：0=导入, 1=链接文件, 2=外部链接
```

**linkMode 说明**：
- `0`：导入模式（PDF 复制到 storage）
- `1`：链接模式（PDF 在 storage 目录）
- `2`：外部链接（PDF 在其他位置）

### 3.2 本流水线如何读取 PDF

```python
# 伪代码：fetch_today_papers.py 中的 PDF 路径处理
def get_pdf_path(attachment_row):
    path = attachment_row['path']
    
    if path.startswith("storage:"):
        # 模式 0/1: Zotero storage 目录
        filename = path.replace("storage:", "")
        return STORAGE_DIR / item_key / filename
    
    elif path.startswith("/"):
        # 模式 2: 外部链接文件
        return Path(path)  # 直接使用绝对路径
    
    return None
```

---

## 第四部分：流水线使用

### 4.1 触发流水线

对 AI 说以下任意一句即可触发：

- "处理今天的 Zotero 新文献"
- "读一下今天 Zotero 新加的论文"
- "Zotero 今日文献入库"
- "今天 Zotero 添加了哪些文献"
- "跑一下 Zotero 文献处理流水线"

### 4.2 流水线工作流程

```
┌─────────────────────────────────────────────────────────────┐
│                    Zotero 论文归档流水线                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ Step 1: 抓取    │
                    │ Zotero 新文献    │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ Step 1.5: 过滤  │
                    │ 去除已处理文献   │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
     ┌────────────┐  ┌────────────┐  ┌────────────┐
     │ 有 PDF     │  │ 有 PDF     │  │ 无 PDF     │
     │ → 完整阅读  │  │ → 重新阅读  │  │ → 摘要推荐  │
     └─────┬──────┘  └─────┬──────┘  └─────┬──────┘
           │                │                │
           ▼                ▼                ▼
     ┌──────────────────────────────────────────────┐
     │ Step 6: 补充概念库 + Step 7: 刷新 MOC      │
     └──────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ 完成汇报        │
                    └─────────────────┘
```

### 4.3 处理结果

#### 有 PDF 的论文

- 调用 `paper-reader` 生成完整笔记
- 保存到 `Paper Notes/_待整理/{论文标题}.md`
- 包含：摘要、结构化分析、图表、公式

#### 无 PDF 的论文

- 生成摘要推荐点评
- 保存到 `Daily Papers/YYYY-MM-DD-Zotero入库.md`
- 标注：必读 / 值得看 / 可跳过

#### 自动更新

- 概念库：提取 `[[概念]]` 链接，创建缺失概念
- MOC 索引：刷新论文和概念的目录页

---

## 第五部分：故障排查

### 5.1 常见问题

| 问题 | 原因 | 解决方案 |
|-----|------|---------|
| 无法读取 Zotero | 数据库路径错误 | 检查 `user-config.json` 中的 `zotero_db` 路径 |
| PDF 找不到 | 外部链接路径失效 | 确认 PDF 文件仍在原位置 |
| 笔记未生成 | PDF 文本提取失败 | 检查 PDF 是否是扫描版 |
| MOC 未刷新 | `auto_refresh_indexes=false` | 设置为 `true` 或手动刷新 |

### 5.2 调试命令

```bash
# 测试 Zotero 数据库连接
python3 -c "
import sqlite3
db = sqlite3.connect('~/Zotero/zotero.sqlite')
print('连接成功，版本:', sqlite3.sqlite_version)
"

# 查看今天新增文献
python3 ~/.workbuddy/skills/zotero-daily-intake/scripts/fetch_today_papers.py

# 查看 PDF 附件
python3 -c "
import sqlite3
conn = sqlite3.connect('~/Zotero/zotero.sqlite')
cursor = conn.cursor()
cursor.execute('SELECT itemID, path, linkMode FROM itemAttachments WHERE parentItemID = <论文ID>')
for row in cursor.fetchall():
    print(row)
"
```

---

## 第六部分：扩展配置

### 6.1 支持的数据源

流水线支持从多个来源获取论文：

| 数据源 | 说明 | 配置 |
|-------|------|------|
| **Zotero** | 本地数据库 | 必选 |
| **arXiv** | 预印本论文 | 可选 |
| **HuggingFace** | 论文 | 可选 |
| **Semantic Scholar** | 学术论文 | 可选 |
| **PubMed** | 医学论文 | 可选 |

### 6.2 自动化定时执行

可以使用 WorkBuddy 自动化功能设置定时执行：

```toml
# 自动化配置示例
name = "每日 Zotero 文献处理"
prompt = "处理今天的 Zotero 新文献"
rrule = "FREQ=DAILY;BYHOUR=9;BYMINUTE=0"
cwds = ["/path/to/workspace"]
status = "ACTIVE"
```

---

## 附录：文件路径速查

| 用途 | 路径 |
|-----|------|
| Zotero 数据库 | `~/Zotero/zotero.sqlite` |
| Zotero 存储 | `~/Zotero/storage/` |
| Obsidian 库 | `~/Documents/Obsidian/` |
| 配置文件 | `~/.workbuddy/skills/_shared/user-config.json` |
| 技能脚本 | `~/.workbuddy/skills/zotero-daily-intake/scripts/` |
| 每日推荐 | `~/Documents/Obsidian/Daily Papers/` |
| 论文笔记 | `~/Documents/Obsidian/Paper Notes/_待整理/` |
| 概念笔记 | `~/Documents/Obsidian/Concepts/` |

---

> **维护者**：botox5 
> **更新日期**：2026-03-19  
> **版本**：v1.0
