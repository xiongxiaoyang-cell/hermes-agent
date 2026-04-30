---
name: wiki-ingest-gene
description: "llm-wiki Layer 2 批量 ingest 标准流程 — Gene式紧凑版。扁平目录 → wiki 页面，Stub-first + Lint循环 + Index同步。"
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [wiki, knowledge-base, ingest, lint, llm-wiki]
    category: research
    related_skills: [llm-wiki, hermes-sync]
signals_match: ingest
strategy: batch-compile raw sources into Layer 2 wiki pages with frontmatter + wikilinks
AVOID: [orphan-pages, broken-links, partial-index-updates, single-pass-lint]
constraints:
  - 所有新页面必须有 YAML frontmatter (title/created/updated/type/tags/sources/confidence)
  - 每个页面至少2个出站 [[wikilinks]]
  - ingest 完成后必须 lint 检查
  - index.md 和 log.md 同步更新
validation:
  - lint: 0 broken links, 0 orphans, all pages ≥2 outbound links
  - index.md: Total pages 计数与实际 Layer 2 文件数一致
  - log.md: 每批 ingest 有独立 entry
---

# Wiki Ingest — Layer 2 批量编译流程

## 适用场景
将 `raw/sources/` 中的原始资料（扁平 markdown 目录）批量编译成 llm-wiki Layer 2 页面（entities/concepts/comparisons/queries）。

## 核心原则

1. **Stub-first**：遇到被引用但不存在的 wikilink → 创建 stub 页面（内容精简但结构合规）→ 保持链路完整
2. **Lint 循环**：每批 ingest 后立即 lint → 修复死链/孤立页 → 验证清零
3. **Index+Log 同步**：每批 ingest 必须更新 index.md（+计数）和 log.md（+entry）

## 标准流程

### Step 1 — Scan Sources
扫描 `raw/sources/` 目录结构，确定内容分布：
```bash
for d in ~/wiki/raw/sources/*/; do echo "=== $(basename "$d") ==="; ls "$d" | head -5; done
```
优先级：先高价值目录（战略方法论、人力资源、用友产品），再自媒体、行业案例。

### Step 2 — Read & Extract
读取源文件前 50-80 行，判断：
- 内容类型（entity / concept / comparison / query）
- 核心数据点（数字、日期、政策名称）
- 可被现有页面引用的机会

### Step 3 — Write Wiki Pages
每个新页面必须包含：
```yaml
---
title: Page Title
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: entity | concept | comparison | query
tags: [from SCHEMA taxonomy]
sources: [raw/sources/path.md]
confidence: high | medium | low
---
```
Wikilinks 策略：链接到已有页面 ≥2 个，避免孤儿。

### Step 4 — Lint (Critical)
```python
# 伪代码 — 用 execute_code 执行
import os, re
from collections import defaultdict
wiki = "~/wiki"
wiki_dirs = ["entities", "concepts", "comparisons", "queries"]
# 1. 构建 all_pages {slug: (fpath, outbound_links)}
# 2. 构建 inbound map
# 3. 检测 broken links / orphans / <2 outbound
# 4. 输出报告
```
**必须清零才能继续**：0 broken links, 0 orphans, all ≥2 outbound。

### Step 5 — Fix
- **死链**：替换为正确 slug，或创建 stub 页面
- **孤立页**：在已有页面（如 quyu-guihua / yonyou-xinfushe）中补引用
- **<2 outbound**：补充相关页面链接

### Step 6 — Update index.md + log.md
```markdown
# index.md — 追加新页面，更新 Total count
## Entities
- [[slug]] — 一句话摘要
```
```markdown
# log.md — 追加 ingest entry
## [YYYY-MM-DD] ingest | Batch description
- 创建: [[slug1]], [[slug2]], ...
- index.md 更新：N pages total
```

## 常见错误处理

| 错误 | 原因 | 修复 |
|------|------|------|
| sibling subagent 警告 | 并发写入 index.md | 先读再写，或用 patch 替换而非 write_file 覆盖 |
| stub 页面内容单薄 | stub 被当作最终页面 | stub 创建时即填入基本数据和2个链接，后续可扩充 |
| 新页面孤立 | 现有页面未引用 | 在 `quyu-guihua`、`yonyou-xinfushe`、`zhongqi-chuhai-hr-tixi` 等 hub 页补链接 |
| 错误 slug 大量出现 | 早期 wikilink 写错 | 搜索所有含该错误 slug 的文件，patch_all 替换 |
| 新入库页面引用了 raw sources 文件名作为 wikilink | 误以为 `共创会整体框架整合.md` 是 wiki 页面 | ingest 前先确认：raw sources 文件 ≠ wiki 页面；引用时用纯文本或链接到已有的 wiki entity/concept 页，不要新建 wikilink 指向不存在的 slug |

## 关键经验：链接网络维护是迭代循环

**Lint 通过标准必须同时满足三个：0 broken links + 0 orphans + all ≥2 outbound**

每次修复操作都可能产生新的孤立节点，必须多次 re-lint 直到收敛：

```
创建新页面 → re-lint → 发现孤立页（新建stub被引用但无人引用它）
  → 从已有页面补链接 → re-lint
  → 又发现新孤立页 → 再补 → ... → 收敛（三个指标同时清零）
```

典型循环次数：3-5次（每批 ingest 后）。stub 页创建后立即补链接，不要"先创建一堆stub再统一补"。

## 验证清单
- [ ] lint: 0 broken, 0 orphans, all ≥2 outbound
- [ ] index.md Total pages 与 Layer 2 目录文件数一致
- [ ] log.md 有本次 ingest entry
- [ ] 新页面 wikilinks 指向实际存在的 slug

---

## 关键发现：LLM 分类调用在子进程失效（2026-04-25）

**问题**：`wiki-ingest.py` 的 `llm_classify()` 调用失败（Connection refused / 401 Unauthorized）。
- 根因：API key 注入在父进程环境变量，子进程（`urllib.urlopen`）不可见
- 现象：`localhost:8080` 硬编码（旧版）或 401 无认证（新版）

**修复**：
1. 端点改为 `MINIMAX_CN_BASE_URL` 环境变量（支持任意 provider）
2. 添加 `Authorization: Bearer {api_key}` header
3. **Fallback 逻辑强化**（API 不可用时）：
   - 国家名检测 → 复用已有 entity slug（避免 `new-concept` 污染）
   - 通用文件 → 文件名衍生 slug（`re.sub(r'[^a-z0-9]+', '-', fname_lower)[:40]`）
   - 禁止创建 `new-concept` / `new-compare` 等泛名垃圾文件

**验证**：2026-04-25 实测 — fallback 对越南文件正确映射到 `yuenan`，无垃圾文件创建。

**教训**：禁止创建 `new-concept` / `new-compare` 等泛名 stub。正确做法：
- 国家文件 → 指向已有 entity（复用不新建）
- 通用文件 → `re.sub(r'[^a-z0-9]+', '-', fname_lower)[:40]` 生成 safe_slug
- 重复文件 → skip（已有页面不覆盖）
