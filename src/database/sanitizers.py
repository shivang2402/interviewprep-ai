"""Map Python model values to valid PostgreSQL enum values."""

from typing import Optional

# Valid DB enum values (Python model may have extra e.g. 'unknown')
DB_EXPERIENCE_VALID = {"intern", "entry", "mid", "senior", "staff", "leadership"}
DB_OUTCOME_VALID = {"offer", "reject", "pending"}
DB_DIFFICULTY_VALID = {"easy", "medium", "hard"}
DB_INTERVIEW_TYPE_VALID = {
    "phone_screen", "onsite", "online_assessment",
    "virtual", "on_campus", "off_campus", "walk_in",
}

# DB stores 'gfg', not 'geeksforgeeks'
PLATFORM_TO_DB = {
    "leetcode": "leetcode",
    "geeksforgeeks": "gfg",
    "medium": "medium",
}


def db_platform(value: str) -> str:
    """Map Python-normalized platform name → DB enum value."""
    return PLATFORM_TO_DB.get(value, value)


def db_enum(value: Optional[str], valid: set) -> Optional[str]:
    """Return value if it's in valid set, else None (so psycopg2 inserts NULL)."""
    if value is None:
        return None
    return value if value in valid else None
