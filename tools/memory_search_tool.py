#!/usr/bin/env python3
"""
Memory Search Tool v2 — 跨会话 Agent 长期记忆

统一检索三个记忆源：
  1. session_search（SQLite FTS5）— 过往会话（带 platform / role / days_back 过滤）
  2. rag_search（lobster Chroma）— 项目知识库
  3. memory_files（MEMORY.md / USER.md 全文）— 长期记忆

v2 改进（2026-06-20）：
  ✅ 三源合并（session / rag / memory_files）
  ✅ 统一评分：session 重要性 × recency + RAG distance + memory 命中数
  ✅ Recency 加权：<30 天 1.5x / 30-90 天 1.0x / >90 天 0.5x
  ✅ 过滤参数：platform / role / days_back / sources（白名单）
  ✅ Session 多 snippet 聚合（同 session 多处命中合并）
  ✅ 返回 results[] 按 unified_score 倒序

设计目的：替代"用 session_search 单点回忆"模式，给 agent 真正的跨会话长期记忆。
"""
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.registry import registry, tool_error

logger = logging.getLogger(__name__)

# === 路径配置 ===
RAG_INDEX_DIR = "/home/b4ac5686610a4ae2/rag_index/lobster"
RAG_MODEL = "BAAI/bge-small-zh-v1.5"
HERMES_HOME = Path("/home/b4ac5686610a4ae2/.hermes")
MEMORY_DIR = HERMES_HOME / "memories"


# === Recency 权重函数 ===
def _recency_weight(started_at_ts: int, now: float) -> float:
    """<30 天 1.5x / 30-90 天 1.0x / >90 天 0.5x"""
    if not started_at_ts:
        return 0.5
    age_days = (now - started_at_ts) / 86400
    if age_days < 30:
        return 1.5
    if age_days < 90:
        return 1.0
    return 0.5


# === Source 1: session_search ===
def _session_search(
    query: str,
    limit: int,
    platform: Optional[str] = None,
    role: Optional[str] = None,
    days_back: Optional[int] = None,
    current_session_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """FTS5 检索 session DB，按 session_id 聚合，按 unified_score 排序"""
    from hermes_state import SessionDB

    db = SessionDB()
    now = time.time()
    min_ts = int(now - days_back * 86400) if days_back else None

    # 转义/分词交给 SessionDB._sanitize_fts5_query
    raw = db.search_messages(
        query=query,
        source_filter=[platform] if platform else None,
        role_filter=[role] if role else None,
        limit=limit * 5,  # 多取用于聚合
    )

    # 按 session_id 聚合
    grouped: Dict[str, Dict[str, Any]] = {}
    for m in raw:
        sid = m.get("session_id", "")
        if not sid or sid == current_session_id:
            continue
        # days_back 过滤
        ts = m.get("session_started") or m.get("timestamp", 0)
        if min_ts and ts and ts < min_ts:
            continue

        if sid not in grouped:
            grouped[sid] = {
                "source": "session",
                "session_id": sid,
                "role": m.get("role", ""),
                "model": m.get("model", ""),
                "platform": m.get("source", ""),
                "started_at": _fmt_ts(ts),
                "started_at_ts": ts or 0,
                "snippets": [],
                "context_previews": [],
                "hit_count": 0,
            }
        g = grouped[sid]
        g["hit_count"] += 1
        # snippet 去重（保留前 3 个）
        snip = (m.get("snippet", "") or "").replace(">>>", "**").replace("<<<", "**")
        if snip and snip not in g["snippets"] and len(g["snippets"]) < 3:
            g["snippets"].append(snip[:300])
        # context preview（取首条）
        if not g["context_previews"]:
            for c in (m.get("context") or [])[:2]:
                g["context_previews"].append({
                    "role": c.get("role", ""),
                    "content": (c.get("content", "") or "")[:200],
                })

    # 计算 unified_score
    results = []
    for g in grouped.values():
        recency = _recency_weight(g["started_at_ts"], now)
        # importance = hit_count * recency
        importance = min(g["hit_count"] * recency, 5.0)
        # snippet 选最长一条
        best_snip = max(g["snippets"], key=len) if g["snippets"] else ""
        results.append({
            **g,
            "snippet": best_snip,
            "unified_score": round(importance, 2),
            "score_breakdown": {
                "hit_count": g["hit_count"],
                "recency_weight": recency,
            },
        })

    # 排序后截取
    results.sort(key=lambda r: r["unified_score"], reverse=True)
    return results[:limit]


# === Source 2: rag_search ===
def _rag_search(query: str, top_k: int, country: Optional[str] = None) -> List[Dict[str, Any]]:
    """Chroma 检索 lobster 知识库"""
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("HF_ENDPOINT", "hf-mirror.com")

    import chromadb
    from sentence_transformers import SentenceTransformer

    client = chromadb.PersistentClient(path=RAG_INDEX_DIR)
    collection = client.get_collection("lobster_md")
    model = SentenceTransformer(RAG_MODEL)

    q_emb = model.encode([query], normalize_embeddings=True).tolist()
    res = collection.query(query_embeddings=q_emb, n_results=top_k * 2)

    results = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        doc_country = meta.get("country", "")
        if country and doc_country and doc_country != country:
            continue
        # RAG 距离越小越好；转化为 0-1 score（1 - normalized dist）
        # BGE cosine distance 通常在 0.2-0.7 之间
        rag_score = max(0.0, 1.0 - float(dist))
        results.append({
            "source": "rag",
            "path": meta.get("path", ""),
            "country": doc_country,
            "top_dir": meta.get("top_dir", ""),
            "snippet": (doc or "")[:300],
            "unified_score": round(rag_score, 3),
            "score_breakdown": {
                "distance": round(float(dist), 3),
            },
        })

    results.sort(key=lambda r: r["unified_score"], reverse=True)
    return results[:top_k]


# === Source 3: memory_files（MEMORY.md + USER.md 全文） ===
# v3 改进（2026-06-20）：
#   - 解析 § section + section 标签 [事实]/[约定]/[工具]/[索引]/[陷阱]/[里程碑]
#   - importance 加权：[陷阱] ×2.0 / [事实][工具] ×1.5 / [约定] ×1.2 / [索引][里程碑] ×1.0 / USER ×0.8
#   - section 过滤参数：只召回指定 section
SECTION_LABELS = ("[事实]", "[约定]", "[工具]", "[索引]", "[陷阱]", "[里程碑]")

# section 重要性权重
SECTION_IMPORTANCE = {
    "[事实]":   1.5,
    "[约定]":   1.2,
    "[工具]":   1.5,
    "[索引]":   1.0,
    "[陷阱]":   2.0,  # 最高（避坑优先）
    "[里程碑]": 1.0,
}


def _parse_memory_sections(content: str) -> list:
    """解析 MEMORY.md/USER.md 的 § section，返回 [(section_label, content_text)]"""
    sections = []
    for entry in content.split("§"):
        entry = entry.strip()
        if not entry:
            continue
        # 检测 section 标签（[事实] / [约定] / ...）
        label = ""
        for lbl in SECTION_LABELS:
            if entry.startswith(lbl):
                label = lbl
                break
        if not label:
            # 检查 [USER] 等其他 label
            for lbl in SECTION_LABELS + ("[USER]",):
                if entry.startswith(lbl):
                    label = lbl
                    break
        sections.append((label, entry))
    return sections


def _memory_files_search(query: str, limit: int = 3, section_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """长期记忆文件全文检索（v3：section 解析 + importance 加权）"""
    results = []
    files = [
        ("MEMORY.md", "memory"),
        ("USER.md", "user"),
    ]
    # 提取 query 关键词
    keywords = _extract_keywords(query)
    if not keywords:
        return []

    # 解析 section 过滤
    filter_labels = set(section_filter) if section_filter else set()

    for fname, stype in files:
        fpath = MEMORY_DIR / fname
        if not fpath.is_file():
            continue
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        # 解析为 sections
        sections = _parse_memory_sections(content)
        for label, section_text in sections:
            # section 过滤
            if filter_labels and label not in filter_labels:
                continue
            # 计算关键词命中
            count = sum(1 for kw in keywords if kw in section_text)
            if count == 0:
                continue
            # importance 加权
            importance = SECTION_IMPORTANCE.get(label, 0.8 if stype == "user" else 1.0)
            score = min(count * 0.5 * importance, 3.0)
            # 取 section 中含关键词的 snippet
            lines = section_text.split("\n")
            best_snip = max(
                (line for line in lines if any(kw in line for kw in keywords)),
                key=len,
                default=section_text[:200]
            )
            results.append({
                "source": "memory_file",
                "memory_type": stype,  # "memory" or "user"
                "section_label": label or "(无标签)",
                "path": f"~/.hermes/memories/{fname}",
                "snippet": best_snip[:300],
                "full_section": section_text[:500],
                "unified_score": round(score, 2),
                "score_breakdown": {
                    "keyword_hits": count,
                    "importance_weight": importance,
                },
            })

    results.sort(key=lambda r: r["unified_score"], reverse=True)
    return results[:limit]


def _extract_keywords(query: str) -> List[str]:
    """提取 query 关键词（中文 2-gram + 英文 word）"""
    # 中文 2-gram
    cjk_pattern = re.compile(r'[\u4e00-\u9fff]+')
    keywords = []
    for m in cjk_pattern.finditer(query):
        text = m.group()
        for i in range(len(text) - 1):
            kw = text[i:i + 2]
            if kw not in keywords:
                keywords.append(kw)
    # 英文 word
    en_pattern = re.compile(r'[a-zA-Z]{3,}')
    for m in en_pattern.finditer(query):
        kw = m.group().lower()
        if kw not in keywords:
            keywords.append(kw)
    return keywords


def _fmt_ts(ts: int) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


# === 主入口 ===
def memory_search(
    query: str,
    limit: int = 5,
    platform: Optional[str] = None,
    role: Optional[str] = None,
    days_back: Optional[int] = None,
    country: Optional[str] = None,
    sources: Optional[List[str]] = None,
    section_filter: Optional[List[str]] = None,
    current_session_id: Optional[str] = None,
) -> str:
    """
    跨会话长期记忆检索（v3：section-aware + importance 加权）

    Args:
        query: 检索关键词
        limit: 每个 source 返回的最大条数（默认 5，最大 10）
        platform: session 平台过滤（feishu/telegram/cli/...）
        role: session 角色过滤（user/assistant）
        days_back: 只看最近 N 天的 session（默认不限）
        country: RAG 国别过滤（03_区域政策/ 下的 country metadata）
        sources: 白名单 list（["session", "rag", "memory_file"]），默认全开
        section_filter: 记忆文件 section 过滤（["[事实]", "[工具]", "[陷阱]", ...]），默认全开
    """
    if not query or not query.strip():
        return tool_error("query is required", success=False)

    limit = max(1, min(limit, 10))
    srcs = set(sources or ["session", "rag", "memory_file"])

    all_results: List[Dict[str, Any]] = []

    # Source 1: session
    if "session" in srcs:
        try:
            sessions = _session_search(
                query, limit, platform, role, days_back, current_session_id
            )
            all_results.extend(sessions)
        except Exception as e:
            logger.exception("session search failed")
            all_results.append({"source": "session", "error": str(e)})

    # Source 2: rag
    if "rag" in srcs:
        try:
            rag = _rag_search(query, limit, country)
            all_results.extend(rag)
        except Exception as e:
            logger.exception("rag search failed")
            all_results.append({"source": "rag", "error": str(e)})

    # Source 3: memory_files（v3：section_filter 透传）
    if "memory_file" in srcs:
        try:
            mem = _memory_files_search(query, limit=3, section_filter=section_filter)
            all_results.extend(mem)
        except Exception as e:
            logger.exception("memory_files search failed")
            all_results.append({"source": "memory_file", "error": str(e)})

    # 跨源 unified_score 排序
    all_results.sort(key=lambda r: r.get("unified_score", 0), reverse=True)

    return json.dumps({
        "success": True,
        "query": query,
        "filters": {
            "platform": platform,
            "role": role,
            "days_back": days_back,
            "country": country,
            "sources": list(srcs),
            "section_filter": section_filter,
        },
        "results": all_results[:limit * 3],  # 总条数限制
        "summary": {
            "total": len(all_results),
            "by_source": {
                "session": sum(1 for r in all_results if r.get("source") == "session"),
                "rag": sum(1 for r in all_results if r.get("source") == "rag"),
                "memory_file": sum(1 for r in all_results if r.get("source") == "memory_file"),
            },
        },
    }, ensure_ascii=False, indent=2)


MEMORY_SEARCH_SCHEMA: Dict[str, Any] = {
    "name": "memory_search",
    "description": (
        "跨会话长期记忆检索 v3：section-aware + importance 加权 + 三源合并。\n\n"
        "适用场景：\n"
        "  - 用户问'我们之前讨论过 X 吗' → 检索 session 找到对话历史\n"
        "  - 用户问'X 的最新数据/政策/文档' → 检索 RAG 找到项目知识\n"
        "  - 用户问'X 的方法论/约定/原则是什么' → 检索 memory_files（MEMORY.md / USER.md）\n"
        "  - 综合查询 → 三源合并，按 unified_score 倒序返回\n\n"
        "v3 改进（2026-06-20）：\n"
        "  - MEMORY.md 结构化（[事实]/[约定]/[工具]/[索引]/[陷阱]/[里程碑] 6 section 标签）\n"
        "  - importance 加权：[陷阱]×2.0 / [事实][工具]×1.5 / [约定]×1.2 / [索引][里程碑]×1.0 / USER×0.8\n"
        "  - section_filter 参数：只召回指定 section\n\n"
        "v2 改进（2026-06-20）：\n"
        "  - 新增 memory_files 源（MEMORY.md + USER.md 全文检索）\n"
        "  - 新增过滤参数：platform / role / days_back / country / sources\n"
        "  - 统一 unified_score：session 重要性×recency + RAG 距离 + memory 命中数\n"
        "  - Recency 加权：<30 天 1.5x / 30-90 天 1.0x / >90 天 0.5x\n"
        "  - Session 多 snippet 聚合（同 session 多处命中合并）\n\n"
        "返回格式：JSON 含 results[] 列表，按 unified_score 倒序，"
        "每条带 source 标签（session / rag / memory_file）。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "查询关键词，支持中文/英文/中英混合",
            },
            "limit": {
                "type": "integer",
                "description": "每个 source 返回的最大条数（默认 5，最大 10）",
                "default": 5,
            },
            "platform": {
                "type": "string",
                "description": "session 平台过滤（feishu/telegram/cli/discord/...）",
            },
            "role": {
                "type": "string",
                "description": "session 角色过滤（user/assistant）",
            },
            "days_back": {
                "type": "integer",
                "description": "只看最近 N 天的 session（默认不限）",
            },
            "country": {
                "type": "string",
                "description": "RAG 国别过滤（仅 03_区域政策/ 下 country metadata 匹配）",
            },
            "sources": {
                "type": "array",
                "items": {"type": "string", "enum": ["session", "rag", "memory_file"]},
                "description": "白名单（默认全开）",
            },
            "section_filter": {
                "type": "array",
                "items": {"type": "string", "enum": ["[事实]", "[约定]", "[工具]", "[索引]", "[陷阱]", "[里程碑]"]},
                "description": "MEMORY.md/USER.md section 过滤（默认全开，可指定 [陷阱] 只查避坑）",
            },
        },
        "required": ["query"],
    },
}


registry.register(
    name="memory_search",
    toolset="research",
    schema=MEMORY_SEARCH_SCHEMA,
    handler=lambda args, **kw: memory_search(
        query=args.get("query", ""),
        limit=args.get("limit", 5),
        platform=args.get("platform"),
        role=args.get("role"),
        days_back=args.get("days_back"),
        country=args.get("country"),
        sources=args.get("sources"),
        section_filter=args.get("section_filter"),
        current_session_id=kw.get("current_session_id"),
    ),
    check_fn=lambda: True,  # 永远可用（依赖 RAG 本地索引 + session DB + memory files）
)