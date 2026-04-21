"""
Shared utilities for src/monitoring/ modules.
YAML config loading with ${ENV_VAR} resolution.
"""
 
import os
import re
from pathlib import Path
 
import yaml
from dotenv import load_dotenv
 
_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")
 
 
def _resolve_env_vars(value):
    """Replace ${VAR_NAME} placeholders with environment variable values."""
    if isinstance(value, str):
        def _replace(match):
            var_name = match.group(1)
            env_val = os.getenv(var_name)
            if env_val is None:
                raise ValueError(
                    f"Environment variable '{var_name}' not set "
                    f"(required by config.yaml)"
                )
            return env_val
        return _ENV_VAR_PATTERN.sub(_replace, value)
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    return value
 
 
def load_config() -> dict:
    """Load config.yaml with env var resolution."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
 
    config_path = Path(__file__).resolve().parent / "config.yaml"
    with open(config_path, "r") as f:
        raw = yaml.safe_load(f)
    return _resolve_env_vars(raw)
 
 
def get_db_params(cfg: dict) -> dict:
    """Extract psycopg2-compatible connection params from config."""
    db = cfg["database"]
    return {
        "host": db["host"],
        "port": int(db["port"]),
        "dbname": db["dbname"],
        "user": db["user"],
        "password": db["password"],
    }