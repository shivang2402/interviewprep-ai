"""
Storage backends for the interview scraper.
Supports local filesystem and Google Cloud Storage.

Usage:
    # Local storage (default, for development)
    storage = LocalStorageBackend(base_dir=Path("data"))

    # GCS storage (for production)
    storage = GCSStorageBackend(bucket_name="interview-scraper-data")

    # Use in scraper
    scraper = GFGScraper(scrape_type="bulk", storage=storage)
    scraper.run()
"""

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, List



# ============== ABSTRACT BACKEND ==============
class StorageBackend(ABC):
    """Abstract interface for storing scraper output files."""

    @abstractmethod
    def write_json(self, path: str, data: dict) -> None:
        """Write a dict as JSON to the given path (relative to base)."""
        pass

    @abstractmethod
    def read_json(self, path: str) -> Optional[dict]:
        """Read JSON from the given path. Returns None if not found."""
        pass

    @abstractmethod
    def file_exists(self, path: str) -> bool:
        """Check if a file exists at the given path."""
        pass

    @abstractmethod
    def list_files(self, prefix: str, suffix: str = "") -> List[str]:
        """List files under a prefix, optionally filtered by suffix."""
        pass


# ============== GCS BACKEND ==============
class GCSStorageBackend(StorageBackend):
    """
    Stores files in a Google Cloud Storage bucket.

    Setup:
        1. pip install google-cloud-storage
        2. Set GOOGLE_APPLICATION_CREDENTIALS env var to your service account key path
           OR pass credentials_path to this class

    Bucket structure mirrors the local directory structure:
        raw/gfg/2025-01-15/google-sde-interview.json
        manifests/scrape_2025-01-15.json
    """

    def __init__(self, bucket_name: str, credentials_path: Optional[str] = None):
        try:
            from google.cloud import storage as gcs
        except ImportError:
            raise ImportError(
                "google-cloud-storage is required for GCS backend.\n"
                "Install it with: pip install google-cloud-storage"
            )

        # If credentials_path provided, use it; otherwise rely on
        # GOOGLE_APPLICATION_CREDENTIALS env var (set during setup)
        if credentials_path:
            self.client = gcs.Client.from_service_account_json(credentials_path)
        else:
            self.client = gcs.Client()

        self.bucket = self.client.bucket(bucket_name)
        self.bucket_name = bucket_name

        # Verify bucket exists and is accessible
        if not self.bucket.exists():
            raise ValueError(
                f"Bucket '{bucket_name}' does not exist or is not accessible. "
                f"Create it in the GCS console first."
            )
        print(f"[GCS] Connected to bucket: {bucket_name}")

    def write_json(self, path: str, data: dict) -> None:
        """Upload JSON to GCS. Path becomes the object key (blob name)."""
        blob = self.bucket.blob(path)
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        blob.upload_from_string(json_str, content_type="application/json")

    def read_json(self, path: str) -> Optional[dict]:
        """Download and parse JSON from GCS."""
        blob = self.bucket.blob(path)
        if not blob.exists():
            return None
        content = blob.download_as_text()
        return json.loads(content)

    def file_exists(self, path: str) -> bool:
        """Check if a blob exists in the bucket."""
        return self.bucket.blob(path).exists()

    def list_files(self, prefix: str, suffix: str = "") -> List[str]:
        """
        List blobs under a prefix.
        GCS doesn't have real directories — everything is a flat key.
        Prefix acts like a directory filter.

        Example: list_files("manifests/", ".json")
        Returns: ["manifests/scrape_2025-01-15.json", ...]
        """
        blobs = self.client.list_blobs(self.bucket_name, prefix=prefix)
        results = []
        for blob in blobs:
            if blob.name.endswith(suffix) if suffix else True:
                results.append(blob.name)
        return sorted(results, reverse=True)

# if __name__ == "__main__":

#     storage = GCSStorageBackend(bucket_name="interviewprep-ai-data", credentials_path=rf"C:\Users\heetk\Downloads\interviewprep-ai\connection_string.json")
#     storage.write_json("test/hello.json", {"status": "it works!"})
#     print(storage.read_json("test/hello.json"))  # {'status': "it works!"}