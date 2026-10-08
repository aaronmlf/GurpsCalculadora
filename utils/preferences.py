"""Small, atomic user preferences; independent of combat and weapon schemas."""
import json
import os
from pathlib import Path
import tempfile


def load_preferences(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return {key: data[key] for key, allowed in {
            "language": {"pt_BR", "en_US"}, "units": {"metric", "imperial"}
        }.items() if data.get(key) in allowed}
    except (OSError, ValueError, TypeError):
        return {}


def save_preferences(path, language, units):
    if language not in {"pt_BR", "en_US"} or units not in {"metric", "imperial"}:
        raise ValueError("invalid_preferences")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = handle.name
            json.dump({"language": language, "units": units}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)
