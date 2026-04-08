import os
import logging
from contextlib import contextmanager

import psycopg2
import psycopg2.pool

logger = logging.getLogger(__name__)

_pool = None


def _get_secret(secret_id: str) -> str:
    from google.cloud import secretmanager

    project_id = os.environ["GCP_PROJECT_ID"]
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")


def _resolve_credentials() -> dict:
    use_sm = os.getenv("USE_SECRET_MANAGER", "false").lower() == "true"
    if use_sm:
        logger.info("Loading DB credentials from Secret Manager")
        return {
            "user": _get_secret(os.getenv("SECRET_DB_USER", "db-user")),
            "password": _get_secret(os.getenv("SECRET_DB_PASSWORD", "db-password")),
        }
    return {
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
    }


def _init_pool():
    global _pool
    if _pool is not None:
        return

    mode = os.getenv("DB_CONNECTION_MODE", "tcp")
    creds = _resolve_credentials()
    db_name = os.environ["DB_NAME"]

    if mode == "socket":
        instance = os.environ["CLOUD_SQL_INSTANCE_CONNECTION_NAME"]
        socket_path = f"/cloudsql/{instance}"
        logger.info("Connecting via Unix socket: %s", socket_path)
        _pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            dbname=db_name,
            user=creds["user"],
            password=creds["password"],
            host=socket_path,
        )
    else:
        host = os.getenv("DB_HOST", "127.0.0.1")
        port = os.getenv("DB_PORT", "5432")
        logger.info("Connecting via TCP: %s:%s", host, port)
        _pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            dbname=db_name,
            user=creds["user"],
            password=creds["password"],
            host=host,
            port=port,
        )

    logger.info("Connection pool initialized (mode=%s)", mode)


@contextmanager
def get_connection():
    _init_pool()
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)
