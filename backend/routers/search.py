import os
import logging
import difflib
from typing import Optional

from fastapi import APIRouter, Query

from db.connection import get_connection
from db import queries as q

router = APIRouter(tags=["search"])
logger = logging.getLogger(__name__)

_embedding_model = None
_company_cache: list[str] | None = None
_role_cache: list[str] | None = None

EXPERIENCE_LEVELS = {
    "intern", "entry", "mid", "senior", "staff", "leadership",
}


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer

        model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        logger.info("Loading embedding model: %s", model_name)
        _embedding_model = SentenceTransformer(model_name)
    return _embedding_model


def _load_caches():
    global _company_cache, _role_cache
    if _company_cache is not None:
        return
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM public.companies ORDER BY name")
            _company_cache = [r[0] for r in cur.fetchall()]
            cur.execute("SELECT title FROM public.roles ORDER BY title")
            _role_cache = [r[0] for r in cur.fetchall()]
    logger.info(
        "Fuzzy cache loaded: %d companies, %d roles",
        len(_company_cache),
        len(_role_cache),
    )


def _fuzzy_match(word: str, candidates: list[str], cutoff: float = 0.6) -> str | None:
    matches = difflib.get_close_matches(word, candidates, n=1, cutoff=cutoff)
    return matches[0] if matches else None


def _parse_query(raw_query: str) -> dict:
    _load_caches()

    words = raw_query.strip().split()
    detected_company = None
    detected_role = None
    detected_level = None
    remaining = []
    consumed = set()

    # Try multi-word matches first (2-word and 3-word phrases)
    i = 0
    while i < len(words):
        matched = False
        for window in (3, 2):
            if i + window <= len(words):
                phrase = " ".join(words[i : i + window])
                phrase_lower = phrase.lower()

                if not detected_company:
                    m = _fuzzy_match(phrase_lower, [c.lower() for c in _company_cache])
                    if m:
                        idx = [c.lower() for c in _company_cache].index(m)
                        detected_company = _company_cache[idx]
                        consumed.update(range(i, i + window))
                        i += window
                        matched = True
                        break

                if not detected_role:
                    m = _fuzzy_match(phrase_lower, [r.lower() for r in _role_cache])
                    if m:
                        idx = [r.lower() for r in _role_cache].index(m)
                        detected_role = _role_cache[idx]
                        consumed.update(range(i, i + window))
                        i += window
                        matched = True
                        break

        if not matched:
            i += 1

    # Single-word pass for anything not yet consumed
    for i, word in enumerate(words):
        if i in consumed:
            continue

        word_lower = word.lower()

        # Experience level (exact match)
        if not detected_level and word_lower in EXPERIENCE_LEVELS:
            detected_level = word_lower
            continue

        # Fuzzy company match (single word)
        if not detected_company:
            m = _fuzzy_match(word_lower, [c.lower() for c in _company_cache])
            if m:
                idx = [c.lower() for c in _company_cache].index(m)
                detected_company = _company_cache[idx]
                continue

        # Fuzzy role match (single word)
        if not detected_role:
            m = _fuzzy_match(word_lower, [r.lower() for r in _role_cache])
            if m:
                idx = [r.lower() for r in _role_cache].index(m)
                detected_role = _role_cache[idx]
                continue

        remaining.append(word)

    search_query = " ".join(remaining) if remaining else raw_query

    parsed = {}
    if detected_company:
        parsed["company"] = detected_company
    if detected_role:
        parsed["role"] = detected_role
    if detected_level:
        parsed["level"] = detected_level
    parsed["query"] = search_query

    return parsed


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
    parsed = _parse_query(q_param)
    search_text = parsed["query"]

    # Fuzzy-detected values are used unless the caller already set explicit filters
    effective_company = company or parsed.get("company")

    sql = q.FULLTEXT_SEARCH
    params = [search_text, search_text, search_text, search_text]

    if platform:
        sql += " AND pd.source_platform = %s"
        params.append(platform)
    if effective_company:
        sql += " AND LOWER(c.name) = LOWER(%s)"
        params.append(effective_company)
    if difficulty:
        sql += " AND im.difficulty::text = %s"
        params.append(difficulty)
    if parsed.get("level"):
        sql += " AND im.experience_level::text = %s"
        params.append(parsed["level"])
    if parsed.get("role"):
        sql += " AND LOWER(r.title) = LOWER(%s)"
        params.append(parsed["role"])

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
        "parsed_as": parsed,
    }


@router.get("/search/semantic")
def semantic_search(
    q_param: str = Query(..., alias="q", min_length=1),
    limit: int = Query(20, ge=1, le=100),
    platform: Optional[str] = None,
    company: Optional[str] = None,
    difficulty: Optional[str] = None,
):
    parsed = _parse_query(q_param)
    effective_company = company or parsed.get("company")

    model = _get_embedding_model()
    embedding = model.encode(q_param).tolist()
    embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

    sql = q.SEMANTIC_SEARCH
    params = [embedding_str]

    if platform:
        sql += " AND pd.source_platform = %s"
        params.append(platform)
    if effective_company:
        sql += " AND LOWER(c.name) = LOWER(%s)"
        params.append(effective_company)
    if difficulty:
        sql += " AND im.difficulty::text = %s"
        params.append(difficulty)
    if parsed.get("level"):
        sql += " AND im.experience_level::text = %s"
        params.append(parsed["level"])
    if parsed.get("role"):
        sql += " AND LOWER(r.title) = LOWER(%s)"
        params.append(parsed["role"])

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
        "parsed_as": parsed,
    }
