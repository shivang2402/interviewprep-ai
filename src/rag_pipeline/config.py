"""
Configuration loader for the generation pipeline.
"""

import os
from pathlib import Path
import yaml


CONFIG_PATH = Path(__file__).resolve().parents[2] / "generation_config.yaml"


def load_generation_config(path: str = None) -> dict:
    config_file = Path(path) if path else CONFIG_PATH
    with open(config_file) as f:
        return yaml.safe_load(f)


def get_db_params(config: dict) -> dict:
    db = config["database"]
    return {
        "host": db["host"],
        "port": db["port"],
        "dbname": db["dbname"],
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
    }