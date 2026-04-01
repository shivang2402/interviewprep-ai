"""
Conftest for rag_pipeline tests.

Stubs out heavy third-party imports that aren't installed in the test
environment so that test collection doesn't fail with ImportError.
"""
import sys
from unittest.mock import MagicMock

# Modules to stub if not already installed
_STUBS = [
    "openai",
    "sentence_transformers",
    "google.cloud.aiplatform",
    "google.cloud",
    "google",
    "dotenv",
    "psycopg2",
    "mlflow",
]

for mod_name in _STUBS:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()
