#!/usr/bin/env python3
"""
Memory Search Tool — 跨会话 Agent 长期记忆

统一检索两个记忆源：
  1. session_search（SQLite FTS5）— 过往会话
  2. rag_search（lobster Chroma）— 项目知识库

返回结果按 source 字段分类（session / rag），让 agent 一次性获得"对话历史 + 知识库"全貌。

设计目的：替代"用 session_search 单点回忆"模式，给 agent 真正的跨会话长期记忆。
"""
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

from tools.registry import registry, tool_error

logger = logging.getLogger(__name__)

# === 路径配置（与 ~/.hermes/scripts/rag_search.py 一致） ===
RAG_INDEX_DIR = "/home/b4ac5686610a4ae2/rag_index/lobster"
RAG_MODEL = "BAAI/bge-small-zh-v1.5"


def _session_search(query: str, limit: int, current_session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """FTS5 检索 session DB，返回 [{session_id, role, snippet, context, timestamp, source}, ...]"""
    from hermes_state import SessionDB  # hermes-agent 根目录模块
    import datetime

    db = SessionDB()
    raw = db.search_messages(query=query, limit=limit * 3)  # 多取用于去重

    # 按 session_id 分组，保留每 session 第一条（最高匹配）
    seen = {}
    for m in raw:
        sid = m.get("session_id", "")
        if not sid or sid == current_session_id:
            continue
        if sid in seen:
            continue
        # 时间戳 → 可读
        ts = m.get("session_started") or m.get("timestamp", 0)
        try:
            dt = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        except Exception:
            dt = ""
        # 清理 snippet 高亮标记 >>>xxx<<<
        snippet = (m.get("snippet", "") or "").replace(">>>", "**").replace("<<<", "**")[:400]
        seen[sid] = {
            "source": "session",
            "session_id": sid,
            "role": m.get("role", ""),
            "model": m.get("model", ""),
            "platform": m.get("source", ""),  # feishu/cli/cron
            "started_at": dt,
            "snippet": snippet,
            "context_preview": [
                {
                    "role": c.get("role", ""),
                    "content": (c.get("content", "") or "")[:200],
                }
                for c in (m.get("context") or [])[:2]
            ],
        }
    return list(seen.values())[:limit]


def _rag_search(query: str, top_k: int) -> List[Dict[str, Any]]:
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
    res = collection.query(query_embeddings=q_emb, n_results=top_k)

    results = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        results.append({
            "source": "rag",
            "path": meta.get("path", ""),
            "country": meta.get("country", ""),
            "top_dir": meta.get("top_dir", ""),
            "snippet": (doc or "")[:300],
            "distance": float(dist),
        })
    return results


def memory_search(
    query: str,
    limit: int = 5,
    db=None,                            # 兼容 session_search 风格的 db 参数（暂时不用，工具自管）
    current_session_id: Optional[str] = None,
) -> str:
    """
    跨会话长期记忆检索：同时返回 session 历史 + RAG 知识库结果。
    """
    if not query or not query.strip():
        return tool_error("query is required", success=False)

    limit = max(1, min(limit, 10))

    try:
        sessions = _session_search(query, limit, current_session_id)
    except Exception as e:
        logger.exception("session search failed")
        sessions = [{"source": "session", "error": str(e)}]

    try:
        rag = _rag_search(query, limit)
    except Exception as e:
        logger.exception("rag search failed")
        rag = [{"source": "rag", "error": str(e)}]

    return json.dumps({
        "success": True,
        "query": query,
        "session_results": sessions,
        "rag_results": rag,
        "summary": {
            "session_hits": len(sessions),
            "rag_hits": len(rag),
        },
    }, ensure_ascii=False, indent=2)


MEMORY_SEARCH_SCHEMA: Dict[str, Any] = {
    "name": "memory_search",
    "description": (
        "跨会话长期记忆检索：同时查询过往会话（SQLite FTS5）和项目知识库（lobster Chroma RAG），"
        "返回带 source 标签（session / rag）的合并结果。\n\n"
        "适用场景：\n"
        "  - 用户问'我们之前讨论过 X 吗' → 检索 session 找到对话历史\n"
        "  - 用户问'X 的最新数据/政策/文档' → 检索 RAG 找到项目知识\n"
        "  - 用户问'我们做 X 的方法论是什么' → 同时命中 session（决策过程）+ RAG（方法论文档）\n\n"
        "返回格式：JSON 含 session_results / rag_results 两个列表，agent 可按需引用。"
        "如不需要区分来源，可只用 session_search 或 RAG 单独查询。"
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
                "description": "每个来源返回的最大条数（默认 5，最大 10）",
                "default": 5,
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
        current_session_id=kw.get("current_session_id"),
    ),
    check_fn=lambda: True,  # 永远可用（依赖 RAG 本地索引 + session DB）
)
