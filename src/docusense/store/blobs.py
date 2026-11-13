"""Content-addressed blob store: store/blobs/sha256/<2 hex>/<62 hex>."""

import hashlib
import os
from pathlib import Path

from docusense.config import get_settings


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class BlobStore:
    def __init__(self, root: Path | None = None):
        self.root = root or get_settings().blob_dir

    def path_for(self, digest: str) -> Path:
        return self.root / "sha256" / digest[:2] / digest[2:]

    def put(self, data: bytes) -> str:
        digest = sha256_hex(data)
        path = self.path_for(digest)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, path)
        return digest

    def get(self, digest: str) -> bytes:
        """Return raw bytes. No integrity check here: verification is the caller's job."""
        return self.path_for(digest).read_bytes()

    def exists(self, digest: str) -> bool:
        return self.path_for(digest).exists()
