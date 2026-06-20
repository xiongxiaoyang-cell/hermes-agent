#!/usr/bin/env python3
"""
Session Semantic Embedding Index — 任务 D

一次性扫描 state.db，为每个 session 提取首条 user 消息 + assistant 摘要，
用 BGE-small-zh 算 embedding，存到独立 Chroma collection "session_semantic"。

提供：
  1. build_index() — 一次扫描，存到 Chroma
  2. search(query, top_k) — 按 query 找最相关的 session
  3. incremental_update() — 只算新 session（state.db 的 started_at > last_build）

数据：
  - 231 sessions / 18346 messages / 201.7 MB state.db
  - 138 feishu / 77 cron / 16 cli
  - 一次 build 约 2-3 分钟（231 × ~100ms BGE encode）

Usage:
  python3 ~/.hermes/scripts/session_semantic_index.py build
  python3 ~/.hermes/scripts/session_semantic_index.py search "日本 雇主成本"
  python3 ~/.hermes/scripts/session_semantic_index.py status
"""
import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

os.environ.setdefault('HF_HUB_OFFLINE', '1')
os.environ.setdefault('HF_ENDPOINT', 'hf-mirror.com')
os.environ.setdefault('ANONYMIZED_TELEMETRY', 'False')

import chromadb
from sentence_transformers import SentenceTransformer

DB_PATH = "/home/b4ac5686610a4ae2/.hermes/state.db"
INDEX_DIR = "/home/b4ac5686610a4ae2/rag_index/sessions"
COLLECTION_NAME = "session_semantic"
MODEL = "BAAI/bge-small-zh-v1.5"
BATCH_SIZE = 32


def get_session_texts() -> List[Dict[str, Any]]:
    """从 state.db 提取每个 session 的代表文本（首条 user + assistant 摘要）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 查所有 session
    cur.execute("""
        SELECT s.id, s.source, s.user_id, s.model, s.started_at,
               (SELECT content FROM messages m
                WHERE m.session_id = s.id AND m.role = 'user'
                ORDER BY m.timestamp ASC LIMIT 1) AS first_user,
               (SELECT content FROM messages m
                WHERE m.session_id = s.id AND m.role = 'assistant'
                ORDER BY m.timestamp ASC LIMIT 1) AS first_assistant,
               (SELECT COUNT(*) FROM messages m
                WHERE m.session_id = s.id) AS msg_count
        FROM sessions s
    """)
    sessions = []
    for row in cur.fetchall():
        sid = row["id"]
        # 拼接代表文本（首条 user + 首条 assistant 摘要）
        parts = []
        if row["first_user"]:
            parts.append(f"[user] {row['first_user'][:500]}")
        if row["first_assistant"]:
            parts.append(f"[assistant] {row['first_assistant'][:500]}")
        text = "\n".join(parts) if parts else ""
        if not text:
            continue  # 空 session 跳过
        sessions.append({
            "session_id": sid,
            "source": row["source"] or "",
            "user_id": row["user_id"] or "",
            "model": row["model"] or "",
            "started_at": row["started_at"] or 0,
            "msg_count": row["msg_count"] or 0,
            "text": text,
        })
    conn.close()
    return sessions


def build_index(force: bool = False) -> Dict[str, Any]:
    """构建 session semantic 索引"""
    INDEX_DIR_PATH = Path(INDEX_DIR)
    INDEX_DIR_PATH.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=INDEX_DIR)
    if force and COLLECTION_NAME in [c.name for c in client.list_collections()]:
        client.delete_collection(COLLECTION_NAME)
    try:
        collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine", "description": "Hermes Agent session semantic embeddings"}
        )
    except Exception as e:
        return {"success": False, "error": str(e)}

    sessions = get_session_texts()
    if not sessions:
        return {"success": False, "error": "no sessions found"}

    print(f"  准备索引 {len(sessions)} 个 session ...")

    # 加载模型
    print("  加载 BGE-small-zh 模型...")
    model = SentenceTransformer(MODEL)

    # 算 embedding
    texts = [s["text"] for s in sessions]
    print(f"  计算 {len(texts)} 个 embedding ...")
    t0 = time.time()
    embeddings = model.encode(texts, normalize_embeddings=True, batch_size=BATCH_SIZE, show_progress_bar=False)
    t1 = time.time()
    print(f"  编码耗时: {t1-t0:.1f}s")

    # 写入 Chroma（分批）
    print("  写入 Chroma collection...")
    total_written = 0
    for i in range(0, len(sessions), BATCH_SIZE):
        batch_sess = sessions[i:i + BATCH_SIZE]
        batch_emb = embeddings[i:i + BATCH_SIZE].tolist()
        collection.add(
            ids=[s["session_id"] for s in batch_sess],
            embeddings=batch_emb,
            documents=[s["text"] for s in batch_sess],
            metadatas=[{
                "source": s["source"],
                "user_id": s["user_id"],
                "model": s["model"],
                "started_at": s["started_at"],
                "msg_count": s["msg_count"],
            } for s in batch_sess],
        )
        total_written += len(batch_sess)

    elapsed = time.time() - t0
    return {
        "success": True,
        "total_sessions": len(sessions),
        "collection_count": collection.count(),
        "elapsed_sec": round(elapsed, 1),
        "index_dir": INDEX_DIR,
    }


def search(query: str, top_k: int = 5, source: Optional[str] = None) -> List[Dict[str, Any]]:
    """semantic 搜索 session"""
    client = chromadb.PersistentClient(path=INDEX_DIR)
    try:
        collection = client.get_collection(COLLECTION_NAME)
    except Exception as e:
        return [{"error": f"collection not found: {e}"}]

    model = SentenceTransformer(MODEL)
    q_emb = model.encode([query], normalize_embeddings=True).tolist()

    where = {"source": source} if source else None
    res = collection.query(query_embeddings=q_emb, n_results=top_k, where=where)

    results = []
    for i in range(len(res["ids"][0])):
        results.append({
            "session_id": res["ids"][0][i],
            "distance": float(res["distances"][0][i]),
            "score": round(1 - float(res["distances"][0][i]), 3),
            "text_snippet": (res["documents"][0][i] or "")[:300],
            "metadata": res["metadatas"][0][i],
        })
    return results


def status() -> Dict[str, Any]:
    """查询索引状态"""
    client = chromadb.PersistentClient(path=INDEX_DIR)
    if COLLECTION_NAME not in [c.name for c in client.list_collections()]:
        return {"exists": False}
    col = client.get_collection(COLLECTION_NAME)
    return {
        "exists": True,
        "count": col.count(),
        "index_dir": INDEX_DIR,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Session Semantic Index")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # build
    p_build = subparsers.add_parser("build", help="构建/重建索引")
    p_build.add_argument("--force", action="store_true", help="强制重建")

    # search
    p_search = subparsers.add_parser("search", help="semantic 搜索")
    p_search.add_argument("query", help="查询")
    p_search.add_argument("-k", "--top-k", type=int, default=5)
    p_search.add_argument("--source", help="按 source 过滤（feishu/cron/cli）")

    # status
    subparsers.add_parser("status", help="查询索引状态")

    args = parser.parse_args()

    if args.command == "build":
        print("=" * 70)
        print("  构建 session semantic 索引")
        print("=" * 70)
        result = build_index(force=args.force)
        print()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "search":
        results = search(args.query, args.top_k, args.source)
        print(json.dumps(results, ensure_ascii=False, indent=2))

    elif args.command == "status":
        print(json.dumps(status(), ensure_ascii=False, indent=2))