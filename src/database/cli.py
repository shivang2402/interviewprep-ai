"""
CLI for batch-loading processed documents from GCS into the database.
Run: python -m src.database.cli
"""

import json
import os

import psycopg2

from src.storage.gcs_backend import GCSBackend
from src.database.loader import BatchDBLoader


def main() -> None:
    storage = GCSBackend(
        bucket_name=os.environ.get("GCS_BUCKET", "interviewprep-ai-data"),
        project_id=os.environ.get("GCP_PROJECT", "professorbot-dovbsg"),
        secret_name=os.environ.get("GCS_SECRET", "gcs-service-account-key"),
    )
    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "34.148.0.165"),
        dbname=os.environ.get("DB_NAME", "interviewprep-ai-database"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", "admin"),
        port=int(os.environ.get("DB_PORT", "5432")),
        sslmode="require",
    )
    print("✅ Connected to DB!")
    loader = BatchDBLoader(gcs_backend=storage, db_conn=conn, batch_size=50)
    prefix = os.environ.get("GCS_LOAD_PREFIX", "processed/2026-02-16_bulk/")
    result = loader.load_batch(prefix)
    print(json.dumps(result, indent=2))
    conn.close()


if __name__ == "__main__":
    main()
