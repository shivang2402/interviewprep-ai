"""Database package: GCS → PostgreSQL batch loading for processed interview docs."""

from src.database.loader import BatchDBLoader

__all__ = ["BatchDBLoader"]
