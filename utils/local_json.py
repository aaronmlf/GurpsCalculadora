"""Small helpers for durable, private application data files."""

import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4


def write_atomic_json(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(document, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def quarantine_json(path):
    """Never overwrite an earlier backup; propagate a failed move."""
    path = Path(path)
    backup = path.with_name(f"{path.stem}.invalid-{uuid4().hex}{path.suffix}")
    path.replace(backup)
    return backup
