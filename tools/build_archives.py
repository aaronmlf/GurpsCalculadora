"""Build end-user and source ZIP archives using only the standard library."""

from __future__ import annotations

from pathlib import Path
import os
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE_EXCLUDED_PARTS = {
    ".git", ".agents", ".codex", "GURPS 4th Edition", "build", "dist",
    ".build-venv", "__pycache__", "GurpsCacul_Linux", "GurpsCacul_Windows",
}
SOURCE_EXCLUDED_NAMES = {
    "GurpsCacul_Linux.zip", "GurpsCacul_Windows.zip", "GurpsCalculadora_Codigo_Fonte.zip",
}
FORBIDDEN_SUFFIXES = {".pdf", ".epub", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pyc", ".tmp"}


def _archive(output: Path, files: list[tuple[Path, Path]]) -> None:
    for source, name in files:
        if source.is_symlink() or name.is_absolute() or ".." in name.parts:
            raise ValueError("unsafe_archive_member")
        if source.suffix.casefold() in FORBIDDEN_SUFFIXES or "GURPS 4th Edition" in name.parts:
            raise ValueError("forbidden_archive_member")
    with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for source, name in sorted(files, key=lambda item: str(item[1])):
                archive.write(source, name)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def package_directory(name: str) -> None:
    if name not in {"GurpsCacul_Linux", "GurpsCacul_Windows"}:
        raise ValueError("unknown_distribution")
    directory = ROOT / name
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("missing_distribution")
    files = [(path, Path(name) / path.relative_to(directory)) for path in directory.rglob("*") if path.is_file()]
    _archive(ROOT / f"{name}.zip", files)


def package_source() -> None:
    files = []
    for directory, children, names in os.walk(ROOT, followlinks=False):
        children[:] = [name for name in children if name not in SOURCE_EXCLUDED_PARTS
                       and not (Path(directory) / name).is_symlink()]
        for name in names:
            path = Path(directory) / name
            if path.is_symlink() or path.name in SOURCE_EXCLUDED_NAMES:
                continue
            if path.suffix.casefold() in FORBIDDEN_SUFFIXES | {".zip", ".exe"}:
                continue
            files.append((path, Path("GurpsCalculadora") / path.relative_to(ROOT)))
    _archive(ROOT / "GurpsCalculadora_Codigo_Fonte.zip", files)


if __name__ == "__main__":
    package_directory("GurpsCacul_Linux")
    package_directory("GurpsCacul_Windows")
    package_source()
