import json
import os
import tempfile
from unittest.mock import MagicMock, patch
import pytest
from src.storage.gcs_backend import GCSBackend, _load_credentials_from_secret_manager
from src.storage.storage_backend import StorageBackend

BUCKET = "interviewprep-ai-data"
PROJECT = "professorbot-dovbsg"
SECRET = "gcs-service-account-key"

@pytest.fixture()
def gcs_mocks():
    with patch("google.cloud.storage.Client") as MockClient:
        mock_client = MockClient.return_value
        mock_bucket = MagicMock()
        mock_bucket.exists.return_value = True
        mock_client.bucket.return_value = mock_bucket
        backend = GCSBackend(bucket_name=BUCKET)
        yield {"backend": backend, "client": mock_client, "bucket": mock_bucket}

class TestLoadCredentialsFromSecretManager:
    def _setup_mock_sm(self, payload: str) -> MagicMock:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.payload.data = payload.encode("UTF-8")
        mock_client.access_secret_version.return_value = mock_response
        return mock_client

    def test_returns_path_to_existing_temp_file(self):
        fake_key = json.dumps({"type": "service_account"})
        mock_client = self._setup_mock_sm(fake_key)
        # Patch the class directly where it is instantiated to avoid auth checks
        with patch("google.cloud.secretmanager.SecretManagerServiceClient", return_value=mock_client):
            path = _load_credentials_from_secret_manager(PROJECT, SECRET)
        try:
            assert os.path.isfile(path)
            assert path.endswith(".json")
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_temp_file_contains_secret_payload(self):
        fake_key = json.dumps({"type": "service_account", "project_id": PROJECT})
        mock_client = self._setup_mock_sm(fake_key)
        with patch("google.cloud.secretmanager.SecretManagerServiceClient", return_value=mock_client):
            path = _load_credentials_from_secret_manager(PROJECT, SECRET)
        try:
            with open(path) as f:
                loaded = json.load(f)
            assert loaded["project_id"] == PROJECT
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_temp_file_has_gcs_sa_prefix(self):
        mock_client = self._setup_mock_sm("{}")
        with patch("google.cloud.secretmanager.SecretManagerServiceClient", return_value=mock_client):
            path = _load_credentials_from_secret_manager(PROJECT, SECRET)
        try:
            assert os.path.basename(path).startswith("gcs_sa_")
        finally:
            if os.path.exists(path):
                os.unlink(path)

class TestGCSBackendInit:
    def test_is_storage_backend_subclass(self, gcs_mocks):
        assert isinstance(gcs_mocks["backend"], StorageBackend)

    def test_default_credentials_uses_gcs_client_directly(self):
        with patch("google.cloud.storage.Client") as MockClient:
            mock_client = MockClient.return_value
            mock_bucket = MagicMock()
            mock_bucket.exists.return_value = True
            mock_client.bucket.return_value = mock_bucket
            GCSBackend(bucket_name=BUCKET)
            MockClient.assert_called_once()

    def test_secret_manager_path_calls_from_service_account_json(self):
        fake_key_path = "/tmp/fake_gcs_sa.json"
        with patch("src.storage.gcs_backend._load_credentials_from_secret_manager", return_value=fake_key_path), \
             patch("google.cloud.storage.Client.from_service_account_json") as mock_from_sa:
            mock_client = MagicMock()
            mock_bucket = MagicMock()
            mock_bucket.exists.return_value = True
            mock_client.bucket.return_value = mock_bucket
            mock_from_sa.return_value = mock_client
            GCSBackend(bucket_name=BUCKET, project_id=PROJECT, secret_name=SECRET)
            mock_from_sa.assert_called_once_with(fake_key_path)
