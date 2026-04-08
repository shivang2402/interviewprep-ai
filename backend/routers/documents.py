from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from db.connection import get_connection
from db import queries as q

router = APIRouter(tags=["documents"])


def _serialize_row(row, columns):
    result = {}
    for col, val in zip(columns, row):
        if hasattr(val, "isoformat"):
            val = val.isoformat()
        result[col] = val
    return result


@router.get("/documents")
def list_documents(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    platform: Optional[str] = None,
    company: Optional[str] = None,
    role: Optional[str] = None,
    outcome: Optional[str] = None,
    difficulty: Optional[str] = None,
):
    sql = q.LIST_DOCUMENTS
    params = []

    if platform:
        sql += " AND pd.source_platform = %s"
        params.append(platform)
    if company:
        sql += " AND LOWER(c.name) = LOWER(%s)"
        params.append(company)
    if role:
        sql += " AND LOWER(r.title) = LOWER(%s)"
        params.append(role)
    if outcome:
        sql += " AND im.interview_outcome::text = %s"
        params.append(outcome)
    if difficulty:
        sql += " AND im.difficulty::text = %s"
        params.append(difficulty)

    count_sql = f"SELECT COUNT(*) FROM ({sql}) sub"
    sql += " ORDER BY pd.scraped_at DESC NULLS LAST"
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


@router.get("/documents/{document_id}")
def get_document(document_id: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(q.GET_DOCUMENT, (document_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Document not found")
            columns = [desc[0] for desc in cur.description]
            doc = _serialize_row(row, columns)

    return {"data": doc}


@router.get("/documents/{document_id}/chunks")
def get_document_chunks(document_id: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(q.GET_DOCUMENT, (document_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Document not found")

            cur.execute(q.GET_DOCUMENT_CHUNKS, (document_id,))
            columns = [desc[0] for desc in cur.description]
            chunks = [_serialize_row(row, columns) for row in cur.fetchall()]

    return {"data": chunks, "meta": {"total": len(chunks)}}
