"""Deterministic IDs.

document_id (per-person) = sha256(f"{source_file_sha256}:person:{person_index}")

Stable across re-runs and machines. Changes ONLY if (a) the source file
content changes, or (b) the confirmed split map changes person boundaries.
The split map is git-tracked, so any ID change is auditable — never silent.
"""
import hashlib
from pathlib import Path


def file_sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def person_document_id(source_sha256: str, person_index: int) -> str:
    return hashlib.sha256(
        f"{source_sha256}:person:{person_index}".encode()
    ).hexdigest()