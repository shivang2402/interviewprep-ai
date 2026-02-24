"""
Unit tests for src/storage/storage_backend.py

Verifies the ABC contract:
  - Cannot be instantiated directly
  - Partial implementations are rejected
  - A complete concrete implementation is accepted and works correctly
"""

import pytest
from typing import Optional, List
from src.storage.storage_backend import StorageBackend

# ─────────────────────────────────────────────────────────────────────────────
# Concrete implementations used across tests
# ─────────────────────────────────────────────────────────────────────────────

class FullyConcreteBackend(StorageBackend):
    """Minimal but complete implementation backed by an in-memory dict."""

    def __init__(self):
        self._store: dict[str, dict] = {}

    def write_json(self, path: str, data: dict) -> None:
        self._store[path] = data

    def read_json(self, path: str) -> Optional[dict]:
        return self._store.get(path)

    def file_exists(self, path: str) -> bool:
        return path in self._store

    def list_files(self, prefix: str, suffix: str = "") -> List[str]:
        return [
            k for k in self._store
            if k.startswith(prefix) and k.endswith(suffix)
        ]


class MissingWriteJson(StorageBackend):
    def read_json(self, path): return None
    def file_exists(self, path): return False
    def list_files(self, prefix, suffix=""): return []


class MissingReadJson(StorageBackend):
    def write_json(self, path, data): pass
    def file_exists(self, path): return False
    def list_files(self, prefix, suffix=""): return []


class MissingFileExists(StorageBackend):
    def write_json(self, path, data): pass
    def read_json(self, path): return None
    def list_files(self, prefix, suffix=""): return []


class MissingListFiles(StorageBackend):
    def write_json(self, path, data): pass
    def read_json(self, path): return None
    def file_exists(self, path): return False


# ─────────────────────────────────────────────────────────────────────────────
# ABC instantiation tests
# ─────────────────────────────────────────────────────────────────────────────

class TestStorageBackendABC:

    def test_cannot_instantiate_abc_directly(self):
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            StorageBackend()  # type: ignore[abstract]

    @pytest.mark.parametrize("cls,missing_method", [
        (MissingWriteJson,  "write_json"),
        (MissingReadJson,   "read_json"),
        (MissingFileExists, "file_exists"),
        (MissingListFiles,  "list_files"),
    ])
    def test_partial_implementation_raises_type_error(self, cls, missing_method):
        """Each abstract method must be implemented; any gap blocks instantiation."""
        with pytest.raises(TypeError):
            cls()

    def test_fully_concrete_subclass_instantiates(self):
        backend = FullyConcreteBackend()
        assert isinstance(backend, StorageBackend)

    def test_all_abstract_methods_defined_on_abc(self):
        expected = {"write_json", "read_json", "file_exists", "list_files"}
        assert StorageBackend.__abstractmethods__ == expected


# ─────────────────────────────────────────────────────────────────────────────
# Behavioural contract tests (via FullyConcreteBackend)
# ─────────────────────────────────────────────────────────────────────────────

class TestStorageBackendContract:
    """
    Exercises the interface contract using the in-memory concrete backend.
    These tests double as a specification that any new backend must satisfy.
    """

    @pytest.fixture()
    def backend(self) -> FullyConcreteBackend:
        return FullyConcreteBackend()

    # ── write_json / read_json round-trip ────────────────────────────────────

    def test_write_then_read_returns_same_data(self, backend):
        data = {"company": "Google", "role": "SWE", "difficulty": "hard"}
        backend.write_json("raw/google/doc1.json", data)
        assert backend.read_json("raw/google/doc1.json") == data

    def test_read_missing_path_returns_none(self, backend):
        assert backend.read_json("does/not/exist.json") is None

    def test_overwrite_replaces_existing_data(self, backend):
        backend.write_json("path.json", {"v": 1})
        backend.write_json("path.json", {"v": 2})
        assert backend.read_json("path.json") == {"v": 2}

    def test_write_empty_dict(self, backend):
        backend.write_json("empty.json", {})
        assert backend.read_json("empty.json") == {}

    def test_write_nested_dict(self, backend):
        data = {"meta": {"platform": "reddit", "tags": ["python", "google"]}}
        backend.write_json("nested.json", data)
        assert backend.read_json("nested.json") == data

    # ── file_exists ──────────────────────────────────────────────────────────

    def test_file_exists_true_after_write(self, backend):
        backend.write_json("exists.json", {"x": 1})
        assert backend.file_exists("exists.json") is True

    def test_file_exists_false_before_write(self, backend):
        assert backend.file_exists("phantom.json") is False

    def test_file_exists_returns_bool(self, backend):
        result = backend.file_exists("anything.json")
        assert isinstance(result, bool)

    # ── list_files ───────────────────────────────────────────────────────────

    def test_list_files_by_prefix(self, backend):
        backend.write_json("raw/reddit/a.json", {})
        backend.write_json("raw/reddit/b.json", {})
        backend.write_json("processed/reddit/c.json", {})

        results = backend.list_files("raw/reddit/")
        assert set(results) == {"raw/reddit/a.json", "raw/reddit/b.json"}

    def test_list_files_filtered_by_suffix(self, backend):
        backend.write_json("raw/reddit/doc.json", {})
        backend.write_json("raw/reddit/doc.txt", {})

        results = backend.list_files("raw/reddit/", suffix=".json")
        assert results == ["raw/reddit/doc.json"]

    def test_list_files_empty_when_no_match(self, backend):
        backend.write_json("raw/reddit/a.json", {})
        assert backend.list_files("processed/") == []

    def test_list_files_returns_list_type(self, backend):
        assert isinstance(backend.list_files("any/"), list)

    def test_list_files_empty_store_returns_empty(self, backend):
        assert backend.list_files("raw/") == []

    def test_list_files_no_suffix_returns_all_under_prefix(self, backend):
        backend.write_json("data/a.json", {})
        backend.write_json("data/b.csv", {})
        backend.write_json("other/c.json", {})

        results = backend.list_files("data/")
        assert set(results) == {"data/a.json", "data/b.csv"}