import os
import logging
import difflib
from typing import Dict, List, Optional

from fastapi import APIRouter, Query

from db.connection import get_connection
from db import queries as q

router = APIRouter(tags=["search"])
logger = logging.getLogger(__name__)

_embedding_model = None
_company_cache: Optional[List[str]] = None
_company_lower_map: Optional[Dict[str, str]] = None
_role_cache: Optional[List[str]] = None
_role_lower_map: Optional[Dict[str, str]] = None

EXPERIENCE_LEVELS = {
    "intern", "entry", "mid", "senior", "staff", "leadership",
}

FUZZY_CUTOFF = 0.85


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer

        model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        logger.info("Loading embedding model: %s", model_name)
        _embedding_model = SentenceTransformer(model_name)
    return _embedding_model


def _load_caches():
    global _company_cache, _company_lower_map, _role_cache, _role_lower_map
    if _company_cache is not None:
        return
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM public.companies ORDER BY name")
            _company_cache = [r[0] for r in cur.fetchall()]
            cur.execute("SELECT title FROM public.roles ORDER BY title")
            _role_cache = [r[0] for r in cur.fetchall()]
    _company_lower_map = {c.lower(): c for c in _company_cache}
    _role_lower_map = {r.lower(): r for r in _role_cache}
    logger.info(
        "Fuzzy cache loaded: %d companies, %d roles",
        len(_company_cache),
        len(_role_cache),
    )


def _match_company(text: str) -> Optional[str]:
    """Try exact case-insensitive match first, then fuzzy with high threshold."""
    lower = text.lower()
    if lower in _company_lower_map:
        return _company_lower_map[lower]
    matches = difflib.get_close_matches(
        lower, list(_company_lower_map.keys()), n=1, cutoff=FUZZY_CUTOFF
    )
    if matches:
        return _company_lower_map[matches[0]]
    return None


def _match_role(text: str) -> Optional[str]:
    """Try exact case-insensitive match first, then fuzzy with high threshold."""
    lower = text.lower()
    if lower in _role_lower_map:
        return _role_lower_map[lower]
    matches = difflib.get_close_matches(
        lower, list(_role_lower_map.keys()), n=1, cutoff=FUZZY_CUTOFF
    )
    if matches:
        return _role_lower_map[matches[0]]
    return None


def _parse_query(raw_query: str) -> dict:
    _load_caches()

    words = raw_query.strip().split()
    detected_company = None
    detected_role = None
    detected_level = None
    consumed = set()

    # Try multi-word matches first (3-word then 2-word phrases)
    i = 0
    while i < len(words):
        matched = False
        for window in (3, 2):
            if i + window <= len(words):
                phrase = " ".join(words[i : i + window])

                if not detected_company:
                    m = _match_company(phrase)
                    if m:
                        detected_company = m
                        consumed.update(range(i, i + window))
                        i += window
                        matched = True
                        break

                if not detected_role:
                    m = _match_role(phrase)
                    if m:
                        detected_role = m
                        consumed.update(range(i, i + window))
                        i += window
                        matched = True
                        break

        if not matched:
            i += 1

    # Single-word pass for anything not yet consumed
    remaining = []
    for i, word in enumerate(words):
        if i in consumed:
            continue

        word_lower = word.lower()

        # Experience level (exact match only)
        if not detected_level and word_lower in EXPERIENCE_LEVELS:
            detected_level = word_lower
            continue

        # Company match (single word)
        if not detected_company:
            m = _match_company(word)
            if m:
                detected_company = m
                continue

        # Role match (single word)
        if not detected_role:
            m = _match_role(word)
            if m:
                detected_role = m
                continue

        remaining.append(word)

    search_query = " ".join(remaining) if remaining else raw_query

    parsed = {}  # type: Dict
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


def _build_fulltext_sql(search_text, platform, company, difficulty, parsed):
    """Build the fulltext SQL and params. Returns (sql, params)."""
    sql = q.FULLTEXT_SEARCH
    params = [search_text, search_text, search_text, search_text]

    if platform:
        sql += " AND pd.source_platform = %s"
        params.append(platform)
    if company:
        sql += " AND LOWER(c.name) = LOWER(%s)"
        params.append(company)
    if difficulty:
        sql += " AND im.difficulty::text = %s"
        params.append(difficulty)
    if parsed.get("level"):
        sql += " AND im.experience_level::text = %s"
        params.append(parsed["level"])
    if parsed.get("role"):
        sql += " AND LOWER(r.title) = LOWER(%s)"
        params.append(parsed["role"])

    return sql, params


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
    effective_company = company or parsed.get("company")

    sql, params = _build_fulltext_sql(
        search_text, platform, effective_company, difficulty, parsed
    )

    count_sql = "SELECT COUNT(*) FROM (%s) sub" % sql
    paged_sql = sql + " ORDER BY rank DESC LIMIT %s OFFSET %s"
    offset = (page - 1) * limit

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(count_sql, params)
            total = cur.fetchone()[0]

            # Fallback: if company filter yielded zero results, retry without it
            if total == 0 and effective_company and not company:
                fallback_sql, fallback_params = _build_fulltext_sql(
                    search_text, platform, None, difficulty, parsed
                )
                fallback_count = "SELECT COUNT(*) FROM (%s) sub" % fallback_sql
                fallback_paged = fallback_sql + " ORDER BY rank DESC LIMIT %s OFFSET %s"

                cur.execute(fallback_count, fallback_params)
                total = cur.fetchone()[0]

                cur.execute(fallback_paged, fallback_params + [limit, offset])
                columns = [desc[0] for desc in cur.description]
                rows = [_serialize_row(row, columns) for row in cur.fetchall()]

                parsed["company_not_found"] = True
                return {
                    "data": rows,
                    "meta": {"total": total, "page": page, "limit": limit},
                    "parsed_as": parsed,
                }

            cur.execute(paged_sql, params + [limit, offset])
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

    def _build_semantic(comp):
        sql = q.SEMANTIC_SEARCH
        p = [embedding_str]
        if platform:
            sql += " AND pd.source_platform = %s"
            p.append(platform)
        if comp:
            sql += " AND LOWER(c.name) = LOWER(%s)"
            p.append(comp)
        if difficulty:
            sql += " AND im.difficulty::text = %s"
            p.append(difficulty)
        if parsed.get("level"):
            sql += " AND im.experience_level::text = %s"
            p.append(parsed["level"])
        if parsed.get("role"):
            sql += " AND LOWER(r.title) = LOWER(%s)"
            p.append(parsed["role"])
        sql += " ORDER BY similarity DESC LIMIT %s"
        p.append(limit)
        return sql, p

    sql, params = _build_semantic(effective_company)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            columns = [desc[0] for desc in cur.description]
            rows = [_serialize_row(row, columns) for row in cur.fetchall()]

            # Fallback: if company filter yielded zero results, retry without it
            if len(rows) == 0 and effective_company and not company:
                fallback_sql, fallback_params = _build_semantic(None)
                cur.execute(fallback_sql, fallback_params)
                columns = [desc[0] for desc in cur.description]
                rows = [_serialize_row(row, columns) for row in cur.fetchall()]
                parsed["company_not_found"] = True

    return {
        "data": rows,
        "meta": {"total": len(rows), "page": 1, "limit": limit},
        "parsed_as": parsed,
    }
