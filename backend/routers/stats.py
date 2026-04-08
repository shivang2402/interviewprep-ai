from fastapi import APIRouter

from db.connection import get_connection
from db import queries as q

router = APIRouter(tags=["stats"])


@router.get("/stats/overview")
def stats_overview():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(q.STATS_OVERVIEW)
            row = cur.fetchone()
            overview = {
                "total_documents": row[0],
                "total_companies": row[1],
                "total_roles": row[2],
            }

            cur.execute(q.STATS_PLATFORM_BREAKDOWN)
            platform_breakdown = [
                {"platform": r[0], "count": r[1]} for r in cur.fetchall()
            ]
            overview["platform_breakdown"] = platform_breakdown

    return {"data": overview}


@router.get("/stats/companies")
def stats_companies():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(q.STATS_COMPANIES)
            rows = [
                {"company": r[0], "document_count": r[1]} for r in cur.fetchall()
            ]

    return {"data": rows, "meta": {"total": len(rows)}}


@router.get("/stats/topics")
def stats_topics():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(q.STATS_TOPICS)
            rows = [{"topic": r[0], "frequency": r[1]} for r in cur.fetchall()]

    return {"data": rows, "meta": {"total": len(rows)}}


@router.get("/stats/outcomes")
def stats_outcomes():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(q.STATS_OUTCOMES)
            rows = [{"outcome": r[0], "count": r[1]} for r in cur.fetchall()]

    return {"data": rows, "meta": {"total": len(rows)}}


@router.get("/filters/options")
def filter_options():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(q.FILTER_PLATFORMS)
            platforms = [r[0] for r in cur.fetchall()]

            cur.execute(q.FILTER_COMPANIES)
            companies = [r[0] for r in cur.fetchall()]

            cur.execute(q.FILTER_ROLES)
            roles = [r[0] for r in cur.fetchall()]

            cur.execute(q.FILTER_DIFFICULTIES)
            difficulties = [r[0] for r in cur.fetchall()]

            cur.execute(q.FILTER_OUTCOMES)
            outcomes = [r[0] for r in cur.fetchall()]

    return {
        "data": {
            "platforms": platforms,
            "companies": companies,
            "roles": roles,
            "difficulties": difficulties,
            "outcomes": outcomes,
        }
    }
