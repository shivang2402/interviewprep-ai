"""
Unit tests for src/storage/gcs_backend.py

All GCS and Secret Manager network calls are mocked — no real GCP
credentials are required to run this test suite.

Run with:
    pytest tests/storage/test_gcs_backend.py -v
"""

import json
import os
import tempfile
from unittest.mock import ANY, MagicMock, call, patch

import pytest

from src.storage.gcs_backend import GCSBackend, _load_credentials_from_secret_manager
from src.storage.storage_backend import StorageBackend

# ─────────────────────────────────────────────────────────────────────────────
# Shared constants
# ─────────────────────────────────────────────────────────────────────────────

BUCKET = "interviewprep-ai-data"
PROJECT = "professorbot-dovbsg"
SECRET = "gcs-service-account-key"

SAMPLE_DOC = {
    "id": "abc123",
    "platform": "reddit",
    "company": "Google",
    "content": "Great system design round.",
}


# ─────────────────────────────────────────────────────────────────────────────
# Shared fixture: a GCSBackend wired to a fully mocked GCS client
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def gcs_mocks():
    """
    Yields a dict with keys:
        backend   – GCSBackend instance
        client    – the mock gcs.Client()
        bucket    – the mock bucket object
    """
    with patch("src.storage.gcs_backend.gcs.Client") as MockClient:
        mock_client = MockClient.return_value
        mock_bucket = MagicMock()
        mock_bucket.exists.return_value = True
        mock_client.bucket.return_value = mock_bucket

        backend = GCSBackend(bucket_name=BUCKET)
        yield {"backend": backend, "client": mock_client, "bucket": mock_bucket}


def _blob(exists: bool = True, text: str = "") -> MagicMock:
    """Helper: create a mock blob with configurable exists() and download text."""
    b = MagicMock()
    b.exists.return_value = exists
    b.download_as_text.return_value = text
    return b


# ─────────────────────────────────────────────────────────────────────────────
# _load_credentials_from_secret_manager
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadCredentialsFromSecretManager:
    """Tests for the module-level helper that fetches a SA key from Secret Manager."""

    def _setup_mock_sm(self, payload: str) -> MagicMock:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.payload.data = payload.encode("UTF-8")
        mock_client.access_secret_version.return_value = mock_response
        return mock_client

    @patch("src.storage.gcs_backend.secretmanager", create=True)
    def test_returns_path_to_existing_temp_file(self, _):
        fake_key = json.dumps({"type": "service_account"})
        mock_client = self._setup_mock_sm(fake_key)

        with patch(
            "src.storage.gcs_backend.secretmanager.SecretManagerServiceClient",
            return_value=mock_client,
        ):
            path = _load_credentials_from_secret_manager(PROJECT, SECRET)

        try:
            assert os.path.isfile(path)
            assert path.endswith(".json")
        finally:
            if os.path.exists(path):
                os.unlink(path)

    @patch("src.storage.gcs_backend.secretmanager", create=True)
    def test_temp_file_contains_secret_payload(self, _):
        fake_key = json.dumps({"type": "service_account", "project_id": PROJECT})
        mock_client = self._setup_mock_sm(fake_key)

        with patch(
            "src.storage.gcs_backend.secretmanager.SecretManagerServiceClient",
            return_value=mock_client,
        ):
            path = _load_credentials_from_secret_manager(PROJECT, SECRET)

        try:
            with open(path) as f:
                loaded = json.load(f)
            assert loaded["type"] == "service_account"
            assert loaded["project_id"] == PROJECT
        finally:
            if os.path.exists(path):
                os.unlink(path)

    @patch("src.storage.gcs_backend.secretmanager", create=True)
    def test_temp_file_has_gcs_sa_prefix(self, _):
        mock_client = self._setup_mock_sm("{}")

        with patch(
            "src.storage.gcs_backend.secretmanager.SecretManagerServiceClient",
            return_value=mock_client,
        ):
            path = _load_credentials_from_secret_manager(PROJECT, SECRET)

        try:
            assert os.path.basename(path).startswith("gcs_sa_")
        finally:
            if os.path.exists(path):
                os.unlink(path)


# ─────────────────────────────────────────────────────────────────────────────
# GCSBackend — __init__ / authentication
# ─────────────────────────────────────────────────────────────────────────────

class TestGCSBackendInit:

    def test_is_storage_backend_subclass(self, gcs_mocks):
        assert isinstance(gcs_mocks["backend"], StorageBackend)

    def test_default_credentials_uses_gcs_client_directly(self):
        with patch("src.storage.gcs_backend.gcs.Client") as MockClient:
            mock_client = MockClient.return_value
            mock_bucket = MagicMock()
            mock_bucket.exists.return_value = True
            mock_client.bucket.return_value = mock_bucket

            GCSBackend(bucket_name=BUCKET)

            MockClient.assert_called_once_with()

    def test_secret_manager_path_calls_from_service_account_json(self):
        fake_key_path = "/tmp/fake_gcs_sa.json"

        with patch(
            "src.storage.gcs_backend._load_credentials_from_secret_manager",
            return_value=fake_key_path,
        ) as mock_load, patch(
            "src.storage.gcs_backend.gcs.Client.from_service_account_json"
        ) as mock_from_sa:
            mock_client = MagicMock()
            mock_bucket = MagicMock()
            mock_bucket.exists.return_value = True
            mock_client.bucket.return_value = mock_bucket
            mock_from_sa.return_value = mock_client

            GCSBackend(bucket_name=BUCKET, project_id=PROJECT, secret_name=SECRET)

            mock_load.assert_called_once_with(project_id=PROJECT, secret_name=SECRET)
            mock_from_sa.assert_called_once_with(fake_key_path)

    def test_only_project_id_without_secret_falls_back_to_default(self):
        """Providing project_id alone (no secret_name) should use default credentials."""
        with patch("src.storage.gcs_backend.gcs.Client") as MockClient:
            mock_client = MockClient.return_value
            mock_bucket = MagicMock()
            mock_bucket.exists.return_value = True
            mock_client.bucket.return_value = mock_bucket

            GCSBackend(bucket_name=BUCKET, project_id=PROJECT)  # no secret_name

            MockClient.assert_called_once_with()

    def test_bucket_name_stored(self, gcs_mocks):
        assert gcs_mocks["backend"].bucket_name == BUCKET

    def test_bucket_existence_checked_on_init(self, gcs_mocks):
        gcs_mocks["bucket"].exists.assert_called()

    def test_raises_value_error_when_bucket_not_found(self):
        with patch("src.storage.gcs_backend.gcs.Client") as MockClient:
            mock_client = MockClient.return_value
            mock_bucket = MagicMock()
            mock_bucket.exists.return_value = False
            mock_client.bucket.return_value = mock_bucket

            with pytest.raises(ValueError, match="does not exist or is not accessible"):
                GCSBackend(bucket_name="ghost-bucket")

    def test_error_message_contains_bucket_name(self):
        with patch("src.storage.gcs_backend.gcs.Client") as MockClient:
            mock_client = MockClient.return_value
            mock_bucket = MagicMock()
            mock_bucket.exists.return_value = False
            mock_client.bucket.return_value = mock_bucket

            with pytest.raises(ValueError, match="ghost-bucket"):
                GCSBackend(bucket_name="ghost-bucket")

    def test_temp_key_cleaned_up_when_bucket_not_found(self):
        """_cleanup_temp_key must be called even when bucket validation fails."""
        # Create a real temp file to verify it gets deleted
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        fake_key_path = tmp.name

        with patch(
            "src.storage.gcs_backend._load_credentials_from_secret_manager",
            return_value=fake_key_path,
        ), patch(
            "src.storage.gcs_backend.gcs.Client.from_service_account_json"
        ) as mock_from_sa:
            mock_client = MagicMock()
            mock_bucket = MagicMock()
            mock_bucket.exists.return_value = False
            mock_client.bucket.return_value = mock_bucket
            mock_from_sa.return_value = mock_client

            with pytest.raises(ValueError):
                GCSBackend(bucket_name=BUCKET, project_id=PROJECT, secret_name=SECRET)

        assert not os.path.exists(fake_key_path), "Temp key file should be deleted"


# ─────────────────────────────────────────────────────────────────────────────
# GCSBackend — write_json
# ─────────────────────────────────────────────────────────────────────────────

class TestGCSBackendWriteJson:

    def test_calls_bucket_blob_with_path(self, gcs_mocks):
        mock_blob = _blob()
        gcs_mocks["bucket"].blob.return_value = mock_blob

        gcs_mocks["backend"].write_json("raw/reddit/doc1.json", SAMPLE_DOC)

        gcs_mocks["bucket"].blob.assert_called_with("raw/reddit/doc1.json")

    def test_calls_upload_from_string(self, gcs_mocks):
        mock_blob = _blob()
        gcs_mocks["bucket"].blob.return_value = mock_blob

        gcs_mocks["backend"].write_json("raw/reddit/doc1.json", SAMPLE_DOC)

        mock_blob.upload_from_string.assert_called_once()

    def test_uploaded_string_is_valid_json(self, gcs_mocks):
        mock_blob = _blob()
        gcs_mocks["bucket"].blob.return_value = mock_blob

        gcs_mocks["backend"].write_json("path.json", SAMPLE_DOC)

        raw_str = mock_blob.upload_from_string.call_args[0][0]
        parsed = json.loads(raw_str)
        assert parsed == SAMPLE_DOC

    def test_content_type_is_application_json(self, gcs_mocks):
        mock_blob = _blob()
        gcs_mocks["bucket"].blob.return_value = mock_blob

        gcs_mocks["backend"].write_json("path.json", SAMPLE_DOC)

        _, kwargs = mock_blob.upload_from_string.call_args
        assert kwargs.get("content_type") == "application/json"

    def test_non_ascii_preserved_in_upload(self, gcs_mocks):
        """ensure_ascii=False must be respected."""
        mock_blob = _blob()
        gcs_mocks["bucket"].blob.return_value = mock_blob
        data = {"company": "日本電気", "role": "エンジニア"}

        gcs_mocks["backend"].write_json("path.json", data)

        raw_str = mock_blob.upload_from_string.call_args[0][0]
        assert "日本電気" in raw_str
        assert "エンジニア" in raw_str

    def test_json_is_indented(self, gcs_mocks):
        """Output should be pretty-printed (indent=2)."""
        mock_blob = _blob()
        gcs_mocks["bucket"].blob.return_value = mock_blob

        gcs_mocks["backend"].write_json("path.json", {"k": "v"})

        raw_str = mock_blob.upload_from_string.call_args[0][0]
        assert "\n" in raw_str  # indented output always contains newlines

    def test_write_empty_dict(self, gcs_mocks):
        mock_blob = _blob()
        gcs_mocks["bucket"].blob.return_value = mock_blob

        gcs_mocks["backend"].write_json("empty.json", {})

        raw_str = mock_blob.upload_from_string.call_args[0][0]
        assert json.loads(raw_str) == {}


# ─────────────────────────────────────────────────────────────────────────────
# GCSBackend — read_json
# ─────────────────────────────────────────────────────────────────────────────

class TestGCSBackendReadJson:

    def test_returns_parsed_dict_when_blob_exists(self, gcs_mocks):
        mock_blob = _blob(exists=True, text=json.dumps(SAMPLE_DOC))
        gcs_mocks["bucket"].blob.return_value = mock_blob

        result = gcs_mocks["backend"].read_json("raw/reddit/doc1.json")

        assert result == SAMPLE_DOC

    def test_returns_none_when_blob_missing(self, gcs_mocks):
        mock_blob = _blob(exists=False)
        gcs_mocks["bucket"].blob.return_value = mock_blob

        result = gcs_mocks["backend"].read_json("missing/file.json")

        assert result is None

    def test_download_not_called_when_blob_missing(self, gcs_mocks):
        mock_blob = _blob(exists=False)
        gcs_mocks["bucket"].blob.return_value = mock_blob

        gcs_mocks["backend"].read_json("missing/file.json")

        mock_blob.download_as_text.assert_not_called()

    def test_calls_blob_with_correct_path(self, gcs_mocks):
        mock_blob = _blob(exists=True, text="{}")
        gcs_mocks["bucket"].blob.return_value = mock_blob

        gcs_mocks["backend"].read_json("some/specific/path.json")

        gcs_mocks["bucket"].blob.assert_called_with("some/specific/path.json")

    def test_returns_nested_structure_correctly(self, gcs_mocks):
        data = {"meta": {"tags": ["oop", "system-design"], "rounds": 3}}
        mock_blob = _blob(exists=True, text=json.dumps(data))
        gcs_mocks["bucket"].blob.return_value = mock_blob

        result = gcs_mocks["backend"].read_json("path.json")

        assert result == data


# ─────────────────────────────────────────────────────────────────────────────
# GCSBackend — file_exists
# ─────────────────────────────────────────────────────────────────────────────

class TestGCSBackendFileExists:

    def test_returns_true_when_blob_exists(self, gcs_mocks):
        mock_blob = _blob(exists=True)
        gcs_mocks["bucket"].blob.return_value = mock_blob

        assert gcs_mocks["backend"].file_exists("some/path.json") is True

    def test_returns_false_when_blob_missing(self, gcs_mocks):
        mock_blob = _blob(exists=False)
        gcs_mocks["bucket"].blob.return_value = mock_blob

        assert gcs_mocks["backend"].file_exists("missing/path.json") is False

    def test_calls_blob_with_exact_path(self, gcs_mocks):
        mock_blob = _blob(exists=True)
        gcs_mocks["bucket"].blob.return_value = mock_blob

        gcs_mocks["backend"].file_exists("exact/path/here.json")

        gcs_mocks["bucket"].blob.assert_called_with("exact/path/here.json")

    def test_return_type_is_bool(self, gcs_mocks):
        mock_blob = _blob(exists=True)
        gcs_mocks["bucket"].blob.return_value = mock_blob

        result = gcs_mocks["backend"].file_exists("anything.json")

        assert isinstance(result, bool)


# ─────────────────────────────────────────────────────────────────────────────
# GCSBackend — list_files
# ─────────────────────────────────────────────────────────────────────────────

def _make_blobs(*names: str) -> list[MagicMock]:
    blobs = []
    for name in names:
        b = MagicMock()
        b.name = name
        blobs.append(b)
    return blobs


class TestGCSBackendListFiles:

    def test_passes_bucket_name_and_prefix_to_list_blobs(self, gcs_mocks):
        gcs_mocks["client"].list_blobs.return_value = []

        gcs_mocks["backend"].list_files("raw/reddit/")

        gcs_mocks["client"].list_blobs.assert_called_once_with(
            BUCKET, prefix="raw/reddit/"
        )

    def test_returns_sorted_descending(self, gcs_mocks):
        blob_names = [
            "manifests/2025-01-01.json",
            "manifests/2025-03-01.json",
            "manifests/2025-02-01.json",
        ]
        gcs_mocks["client"].list_blobs.return_value = _make_blobs(*blob_names)

        result = gcs_mocks["backend"].list_files("manifests/")

        assert result == sorted(blob_names, reverse=True)

    def test_suffix_filter_excludes_non_matching(self, gcs_mocks):
        gcs_mocks["client"].list_blobs.return_value = _make_blobs(
            "raw/a.json", "raw/b.txt", "raw/c.json"
        )

        result = gcs_mocks["backend"].list_files("raw/", suffix=".json")

        assert set(result) == {"raw/a.json", "raw/c.json"}
        assert "raw/b.txt" not in result

    def test_no_suffix_returns_all_blobs(self, gcs_mocks):
        gcs_mocks["client"].list_blobs.return_value = _make_blobs(
            "raw/a.json", "raw/b.csv", "raw/c.txt"
        )

        result = gcs_mocks["backend"].list_files("raw/")

        assert len(result) == 3

    def test_empty_bucket_returns_empty_list(self, gcs_mocks):
        gcs_mocks["client"].list_blobs.return_value = []

        result = gcs_mocks["backend"].list_files("raw/")

        assert result == []

    def test_returns_list_type(self, gcs_mocks):
        gcs_mocks["client"].list_blobs.return_value = []

        result = gcs_mocks["backend"].list_files("prefix/")

        assert isinstance(result, list)

    def test_suffix_filter_all_match(self, gcs_mocks):
        gcs_mocks["client"].list_blobs.return_value = _make_blobs(
            "data/x.json", "data/y.json"
        )

        result = gcs_mocks["backend"].list_files("data/", suffix=".json")

        assert len(result) == 2

    def test_suffix_filter_none_match_returns_empty(self, gcs_mocks):
        gcs_mocks["client"].list_blobs.return_value = _make_blobs(
            "data/x.json", "data/y.json"
        )

        result = gcs_mocks["backend"].list_files("data/", suffix=".csv")

        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# GCSBackend — _cleanup_temp_key & __del__
# ─────────────────────────────────────────────────────────────────────────────

class TestGCSBackendCleanup:

    def test_cleanup_deletes_temp_file(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()

        with patch("src.storage.gcs_backend.gcs.Client") as MockClient:
            mock_client = MockClient.return_value
            mock_bucket = MagicMock()
            mock_bucket.exists.return_value = True
            mock_client.bucket.return_value = mock_bucket

            backend = GCSBackend(bucket_name=BUCKET)
            backend._tmp_key_path = tmp.name

            backend._cleanup_temp_key()

        assert not os.path.exists(tmp.name)

    def test_cleanup_sets_path_to_none(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()

        with patch("src.storage.gcs_backend.gcs.Client") as MockClient:
            mock_client = MockClient.return_value
            mock_bucket = MagicMock()
            mock_bucket.exists.return_value = True
            mock_client.bucket.return_value = mock_bucket

            backend = GCSBackend(bucket_name=BUCKET)
            backend._tmp_key_path = tmp.name
            backend._cleanup_temp_key()

        assert backend._tmp_key_path is None

    def test_cleanup_is_idempotent(self, gcs_mocks):
        """Calling _cleanup_temp_key when no temp file exists should not raise."""
        gcs_mocks["backend"]._tmp_key_path = None
        gcs_mocks["backend"]._cleanup_temp_key()  # should not raise

    def test_cleanup_does_not_raise_if_file_already_deleted(self, gcs_mocks):
        gcs_mocks["backend"]._tmp_key_path = "/tmp/already_gone.json"
        gcs_mocks["backend"]._cleanup_temp_key()  # file doesn't exist — should not raise