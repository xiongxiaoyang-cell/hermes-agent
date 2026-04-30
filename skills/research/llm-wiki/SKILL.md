---
name: llm-wiki-gene
description: LLM Wiki 知识库全能力 — Gene式。五大能力（ingest/compile/query/lint/audit）统一触发入口，每次wiki操作强制执行。
version: 2.0.0
category: research
tags: [wiki, knowledge-base, llm-wiki, ingest, compile, query, lint, audit]
signals: [llm-wiki, wiki, 知识库, 笔记, knowledge base]
---

# LLM Wiki · 全能力 Gene

## 🗺️ 五大能力全景

| # | 能力 | 触发语境 | 产出 |
|---|------|---------|------|
| 1 | **ingest** | "入库"、"归档到知识库" | 新建 concepts/entities + 更新 index/log |
| 2 | **compile** | "整理知识库"、"梳理结构" | 重构 index + hub页补链接 + 修复孤立 |
| 3 | **query** | "查一下XXX"、"请问" | 有据可查的回答 + [[wikilink]] 来源标注 |
| 4 | **lint** | "检查死链"、"跑知识库检查" | 诊断报告（断链/孤立/<2出站）|
| 5 | **audit** | "修正"、"第X条过时了" | 接受/拒绝/延期 + audit归档 |

## 🔬 Gene对象

### signals_match（触发信号）
```
"llm-wiki"|"wiki"|"知识库"|"入库"|"整理"|"检查知识库"|
"查一下"|"请问"|"帮我修正"|"lint"|"ingest"|"compile"
```

### strategy（执行步骤）

**ingest → compile → lint 循环（不可跳过）**
1. 读源文件 → 识别 entity/concept 类型
2. 写入 `~/wiki/concepts/` 或 `~/wiki/entities/`
3. 同步更新 `~/wiki/index.md`（+1计数 + 条目）
4. 追加 `~/wiki/log.md`
5. hub页（如 `longxia-ai-agent`）补出站链接
6. **立即运行 lint**：0断链 + 0孤立 + 全部≥2出站，否则修复

**query（强制流程）**
1. 扫 `~/wiki/index.md` 定位相关页面
2. 读目标页面（entities/ + concepts/ + comparisons/）
3. 组织答案 → 关键数据必须附 [[wikilink]]
4. 结尾一行：来源：[[页面名]]

**audit**
1. 接收反馈 → `~/wiki/audit/inbox/<timestamp>.md`
2. 运行 `python3 ~/wiki/scripts/wiki-audit-review.py ~/wiki/ --open`
3. 三类决策：accept（执行+patch页面+AUDIT marker）/ reject / defer
4. 归档至 `~/wiki/audit/resolved/`

### AVOID
```
禁止：
• ingest后不跑lint → 断链会累积
• query不读wiki直接凭记忆回答政策数据
• 创建wikilink指向不存在的slug（非raw/sources路径）
• 新建页面孤立（无其他页引用）
• 修改raw/层（Layer1不可变）
```

### constraints
```
• wiki根目录：~/wiki/
• 脚本目录：~/wiki/scripts/
• 新页必须：YAML frontmatter + ≥2个wikilinks + index.md条目 + log.md记录
• ingest完成标准：lint三指标清零
• query答案必须附wikilink来源，不许"一般来说"
• audit反馈必须含reporter和具体页面
```

### validation
```
ingest：✓ 新页在 ~/wiki/ ✓ index有条目 ✓ log有记录 ✓ hub页有链接 ✓ lint清零
query：✓ 读了wiki页面 ✓ 关键数据有wikilink ✓ 知识库无覆盖时主动说明
lint：✓ 0 broken links ✓ 0 orphans ✓ all ≥2 outbound
audit：✓ inbox→resolved完整 ✓ accept有AUDIT marker ✓ 决策可追溯
```

## 📊 知识库现状（2026-05-01）

| 维度 | 数量 |
|------|------|
| Total pages | 77 |
| Entities | 22国 + 品牌/人物 |
| Concepts | ~26 |
| Comparisons | 4 |
| raw/sources | 大量原始资料 |

**Hub页**：`zhongqi-chuhai-hr-tixi`（出海HR全体系）、`longxia-ai-agent`（龙虾AI智能体）

**Scripts**：`wiki-lint.py` / `wiki-audit-review.py` / `wiki-ingest.py` / `wiki-compile.py`

## 关键路径
```
~/wiki/index.md      — 全局目录（首次必须读）
~/wiki/log.md       — 操作历史（append-only）
~/wiki/SCHEMA.md    — 结构约定/tag taxonomy
~/wiki/audit/       — 审核反馈归档
```
