"""Explicit inputs for source ZIPs and PyInstaller's data table."""
import ast
import re
from pathlib import Path, PurePosixPath


RESOURCE_MANIFEST = 'packaging/resources.txt'
SOURCE_MANIFEST = 'packaging/source-files.txt'
PATH_PATTERN = re.compile(r'[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)*\Z')
VERSION_PATTERN = re.compile(r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z')
FORBIDDEN_SUFFIXES = {
    '.pdf', '.epub', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.pyc', '.tmp',
    '.zip', '.pem', '.key', '.p12', '.pfx',
}
FORBIDDEN_DIRECTORIES = {'.git', '.agents', '.codex', '.aws', 'build', 'dist', '__pycache__',
                         '.build-venv'}


def validate_release_path(name):
    if (not isinstance(name, str) or not PATH_PATTERN.fullmatch(name)
            or any(part in ('.', '..') for part in name.split('/'))):
        raise ValueError(f'Invalid release path: {name!r}')
    path = PurePosixPath(name)
    if (path.suffix.casefold() in FORBIDDEN_SUFFIXES
            or {part.casefold() for part in path.parts} & FORBIDDEN_DIRECTORIES
            or path.name.casefold().startswith('.env')):
        raise ValueError(f'Forbidden release path: {name}')
    return path


def declared_file(root, name):
    """Resolve an allowed relative file without traversing links or junctions."""
    root = Path(root).resolve()
    path = root
    for part in validate_release_path(name).parts:
        path = path / part
        if path.is_symlink() or path.resolve() != path:
            raise ValueError(f'Linked release input: {name}')
    if not path.is_file():
        raise ValueError(f'Missing release input: {name}')
    return path


def _manifest(root, name):
    seen = set()
    paths = []
    for line in declared_file(root, name).read_text(encoding='utf-8').splitlines():
        relative = line.strip()
        if not relative or relative.startswith('#'):
            continue
        if relative.casefold() in seen:
            raise ValueError(f'Duplicate release input in {name}: {relative}')
        seen.add(relative.casefold())
        declared_file(root, relative)
        paths.append(relative)
    if not paths:
        raise ValueError(f'Empty release manifest: {name}')
    return tuple(paths)


def resource_paths(root):
    """Only the reviewed catalogs and translations, never arbitrary JSON."""
    paths = _manifest(root, RESOURCE_MANIFEST)
    for name in paths:
        path = PurePosixPath(name)
        if path.parent.as_posix() not in {'data', 'i18n'} or path.suffix != '.json':
            raise ValueError(f'Invalid runtime resource: {name}')
    return paths


def source_paths(root):
    """Source files are individually listed; extra files are not distributed."""
    paths = (*_manifest(root, SOURCE_MANIFEST), *resource_paths(root))
    if len({name.casefold() for name in paths}) != len(paths):
        raise ValueError('A release input occurs in both manifests')
    required = {SOURCE_MANIFEST, RESOURCE_MANIFEST, 'main.py', 'version.py',
                'packaging/GurpsCalculadora.spec', 'tools/build_archives.py'}
    if not required <= set(paths):
        raise ValueError(f'Missing required source paths: {sorted(required - set(paths))}')
    return tuple(sorted(paths))


def read_version(root):
    """Read the version without importing or executing project code."""
    source = declared_file(root, 'version.py').read_text(encoding='utf-8')
    versions = [
        statement.value.value for statement in ast.parse(source).body
        if isinstance(statement, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == '__version__'
                for target in statement.targets)
        and isinstance(statement.value, ast.Constant)
    ]
    if len(versions) != 1 or not isinstance(versions[0], str) or not VERSION_PATTERN.fullmatch(versions[0]):
        raise ValueError('version.py must declare a single numeric __version__')
    return versions[0]
