import os
import logging
from typing import Optional

from fastapi import APIRouter, Query, HTTPException

from db.connection import get_connection
from db import queries as q

router = APIRouter(tags=["search"])
logger = logging.getLogger(__name__)

_embedding_model = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer

        model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        logger.info("Loading embedding model: %s", model_name)
        _embedding_model = SentenceTransformer(model_name)
    return _embedding_model


def _serialize_row(row, columns):
    result = {}
    for col, val in zip(columns, row):
        if hasattr(val, "isoformat"):
            val = val.isoformat()
        result[col] = val
    return result


@router.get("/search")
def fulltext_search(
    q_param: str = Query(..., alias="q", min_length=1),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    platform: Optional[str] = None,
    company: Optional[str] = None,
    difficulty: Optional[str] = None,
):
    sql = q.FULLTEXT_SEARCH
    params = [q_param, q_param, q_param, q_param]

    if platform:
        sql += " AND pd.source_platform = %s"
        params.append(platform)
    if company:
        sql += " AND LOWER(c.name) = LOWER(%s)"
        params.append(company)
    if difficulty:
        sql += " AND im.difficulty::text = %s"
        params.append(difficulty)

    count_sql = f"SELECT COUNT(*) FROM ({sql}) sub"
    sql += " ORDER BY rank DESC"
    offset = (page - 1) * limit
    sql += " LIMIT %s OFFSET %s"
    params_with_paging = params + [limit, offset]

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(count_sql, params)
            total = cur.fetchone()[0]

            cur.execute(sql, params_with_paging)
            columns = [desc[0] for desc in cur.description]
            rows = [_serialize_row(row, columns) for row in cur.fetchall()]

    return {
        "data": rows,
        "meta": {"total": total, "page": page, "limit": limit},
    }


@router.get("/search/semantic")
def semantic_search(
    q_param: str = Query(..., alias="q", min_length=1),
    limit: int = Query(20, ge=1, le=100),
    platform: Optional[str] = None,
    company: Optional[str] = None,
    difficulty: Optional[str] = None,
):
    model = _get_embedding_model()
    embedding = model.encode(q_param).tolist()
    embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

    sql = q.SEMANTIC_SEARCH
    params = [embedding_str]

    if platform:
        sql += " AND pd.source_platform = %s"
        params.append(platform)
    if company:
        sql += " AND LOWER(c.name) = LOWER(%s)"
        params.append(company)
    if difficulty:
        sql += " AND im.difficulty::text = %s"
        params.append(difficulty)

    sql += " ORDER BY similarity DESC LIMIT %s"
    params.append(limit)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            columns = [desc[0] for desc in cur.description]
            rows = [_serialize_row(row, columns) for row in cur.fetchall()]

    return {
        "data": rows,
        "meta": {"total": len(rows), "page": 1, "limit": limit},
    }
