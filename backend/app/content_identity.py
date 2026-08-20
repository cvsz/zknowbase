from __future__ import annotations

import hashlib
from uuid import UUID, uuid5

# Stable namespace owned by zknowbase. Do not change it: changing it would alter
# document identity for already-ingested content.
_FILE_CONTENT_NAMESPACE = UUID("9e3692af-4346-5f98-a4a8-1a2717f26e3c")


def sha256_content(data: bytes) -> str:
    """Return the canonical lowercase SHA-256 fingerprint for uploaded bytes."""
    return hashlib.sha256(data).hexdigest()


def file_document_id(tenant_id: str, content_hash: str) -> str:
    """Derive a stable document UUID from authoritative tenant + content hash."""
    if not tenant_id:
        raise ValueError("tenant_id is required for content identity")
    if len(content_hash) != 64 or any(char not in "0123456789abcdef" for char in content_hash):
        raise ValueError("content_hash must be a lowercase SHA-256 hex digest")
    return str(uuid5(_FILE_CONTENT_NAMESPACE, f"{tenant_id}\0sha256:{content_hash}"))
