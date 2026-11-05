"""Build, test and archive the current snapshot on the target operating system."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
if not __package__:
    sys.path.insert(0, str(ROOT))

from tools.release_inputs import (
    VERSION_PATTERN, declared_file, read_version, resource_paths, source_paths, validate_release_path,
)
from tools.verify_gui_launch import run_startup_check, validate_startup_report
from utils.startup_check import PROFILE_ENV


RELEASE_SCHEMA = 'gurps-calculadora.release.v1'
PLATFORMS = {'linux': ('Linux', 'GurpsCalculadora'), 'windows': ('Windows', 'GurpsCalculadora.exe')}
SOURCE_ZIP = 'GurpsCalculadora_Codigo_Fonte.zip'
SAFE_TAG = re.compile(r'v[0-9]+\.[0-9]+\.[0-9]+(?:-[a-zA-Z0-9]+(?:[.-][a-zA-Z0-9]+)*)?\Z')


def sha256(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def _add_file_hash(digest, name, checksum):
    digest.update(f'{name}\0{checksum}\n'.encode('ascii'))


def snapshot_hash(root, paths):
    digest = hashlib.sha256()
    for name in paths:
        _add_file_hash(digest, name, sha256(declared_file(root, name)))
    return digest.hexdigest()


def _archive(output, files):
    """Write only new ZIPs. Caller stages them out of the distribution directory."""
    files = sorted(files, key=lambda item: str(item[1]))
    seen = set()
    for source, member in files:
        name = str(member)
        path = validate_release_path(name)
        if (source.is_symlink() or not source.is_file()
                or source.suffix.casefold() != path.suffix.casefold() or name.casefold() in seen):
            raise ValueError(f'Invalid archive input: {name}')
        seen.add(name.casefold())
    if not files:
        raise ValueError('Refusing to make an empty ZIP')
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for source, member in files:
            info = zipfile.ZipInfo(str(member))
            info.create_system = 3  # preserve the Linux executable bit on every build host
            executable = info.filename.rsplit('/', 1)[-1] == 'GurpsCalculadora' or info.filename.endswith('.sh')
            info.external_attr = (0o100755 if executable else 0o100644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            with source.open('rb') as handle, archive.open(info, 'w') as entry:
                shutil.copyfileobj(handle, entry)


def package_source(root, output):
    _archive(output, [
        (declared_file(root, name), f'GurpsCalculadora/{name}') for name in source_paths(root)
    ])


def _check_binary(binary, target):
    if not binary.is_file() or binary.is_symlink():
        raise ValueError(f'Build did not create {binary.name}')
    with binary.open('rb') as stream:
        header = stream.read(64)
        if target == 'linux':
            if (len(header) != 64 or header[:6] != b'\x7fELF\x02\x01'
                    or header[16:18] not in {b'\x02\x00', b'\x03\x00'}
                    or header[18:20] != b'\x3e\x00' or not os.access(binary, os.X_OK)):
                raise ValueError('Expected an executable Linux x86-64 ELF file')
        else:
            if len(header) != 64 or header[:2] != b'MZ':
                raise ValueError('Expected a Windows executable')
            stream.seek(struct.unpack_from('<I', header, 60)[0])
            pe = stream.read(26)
            if (len(pe) != 26 or pe[:6] != b'PE\x00\x00\x64\x86'
                    or not pe[22] & 0x02 or pe[23] & 0x20 or pe[24:26] != b'\x0b\x02'):
                raise ValueError('Expected an executable Windows x86-64 PE32+ file')


def verify_embedded_resources(binary, root):
    """Verify the names *and contents* of packaged catalogs and translations."""
    from PyInstaller.archive.readers import CArchiveReader

    archive = CArchiveReader(str(binary))
    all_names = {name.replace('\\', '/'): name for name in archive.toc}
    expected = set(resource_paths(root))
    included = {name for name in all_names if name.startswith(('i18n/', 'data/'))}
    if included != expected:
        raise ValueError(f'Incorrect embedded resources: {sorted(expected ^ included)}')
    if any(name.casefold().endswith(('.pdf', '.epub')) or 'gurps 4th edition' in name.casefold()
           for name in all_names):
        raise ValueError('The executable contains a reference book')
    for name in expected:
        if hashlib.sha256(archive.extract(all_names[name])).hexdigest() != sha256(declared_file(root, name)):
            raise ValueError(f'Stale embedded resource: {name}')


def _host():
    target = platform.system().lower()
    if (sys.version_info < (3, 11) or target not in PLATFORMS
            or platform.machine().lower() not in {'amd64', 'x86_64'} or struct.calcsize('P') != 8):
        raise ValueError('Build with Python 3.11+ x86-64 on Linux or Windows')
    environment = 'native'
    if target == 'windows':
        if getattr(ctypes.WinDLL('ntdll'), 'wine_get_version', None):
            environment = 'wine'
    return target, environment


def _locked_tools(root, target):
    manifests = ['packaging/requirements-build.txt']
    if target == 'windows':
        manifests.append('packaging/requirements-build-windows.txt')
    versions = {}
    for manifest in manifests:
        for line in declared_file(root, manifest).read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            name, pin = line.split('==')
            try:
                installed = metadata.version(name)
            except metadata.PackageNotFoundError:
                installed = None
            if installed != pin:
                raise ValueError(f'{name}=={pin} required (found {installed}); use the platform build script')
            versions[name] = pin
    return versions


def _tag(tag, version):
    tag = tag or f'v{version}'
    if not SAFE_TAG.fullmatch(tag) or tag.split('-')[0] != f'v{version}':
        raise ValueError(f'The tag must match v{version}, with an optional pre-release suffix')
    return tag


def _source_zip_hash(path, paths):
    if not isinstance(paths, list) or not paths or any(not isinstance(name, str) for name in paths):
        raise ValueError('Missing source manifest in release.json')
    for name in paths:
        validate_release_path(name)
    if paths != sorted(paths) or len({name.casefold() for name in paths}) != len(paths):
        raise ValueError('Unsorted or duplicate source ZIP paths')
    digest = hashlib.sha256()
    with zipfile.ZipFile(path) as archive:
        names = [f'GurpsCalculadora/{name}' for name in paths]
        if archive.namelist() != names:
            raise ValueError('Unexpected contents in source ZIP')
        for name, entry in zip(paths, names):
            with archive.open(entry) as handle:
                _add_file_hash(digest, name, hashlib.file_digest(handle, 'sha256').hexdigest())
    return digest.hexdigest()


def _package_names(target):
    platform_name, executable = PLATFORMS[target]
    folder = f'GurpsCacul_{platform_name}'
    return folder, executable, f'LEIA-ME_{target.upper()}.txt'


def _output_directory(root, tag):
    directory = root
    for component in ('dist', 'releases', tag):
        directory /= component
        if directory.is_symlink() or directory.resolve() != directory:
            raise ValueError(f'Refusing a linked output directory: {directory}')
        directory.mkdir(exist_ok=True)
    return directory


def _checksums(artifacts):
    return ''.join(f'{checksum}  {name}\n' for name, checksum in sorted(artifacts.items()))


def verify_release(directory):
    """Check the staged/downloaded distribution without executing the binary."""
    directory = Path(directory)
    release = json.loads(declared_file(directory, 'release.json').read_text(encoding='utf-8'))
    if not isinstance(release, dict) or release.get('schema') != RELEASE_SCHEMA:
        raise ValueError('Unsupported release manifest')
    target, version = release.get('target'), release.get('version')
    if target not in PLATFORMS or not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        raise ValueError('Invalid target or version')
    if release.get('tag') != _tag(release.get('tag'), version):
        raise ValueError('Invalid tag')
    if release.get('environment') not in ({'native', 'wine'} if target == 'windows' else {'native'}):
        raise ValueError('Invalid build environment')
    validate_startup_report(release.get('startup_check'), version)
    folder, executable, instructions = _package_names(target)
    binary_zip = f'{folder}.zip'
    artifacts = release.get('archives')
    if not isinstance(artifacts, dict) or set(artifacts) != {binary_zip, SOURCE_ZIP}:
        raise ValueError('Unexpected release archives')
    for name, expected in artifacts.items():
        archive_path = directory / name
        if archive_path.is_symlink() or sha256(archive_path) != expected:
            raise ValueError(f'Checksum mismatch: {name}')
    if declared_file(directory, 'SHA256SUMS.txt').read_text(encoding='ascii') != _checksums(artifacts):
        raise ValueError('Checksum index differs from release.json')
    if _source_zip_hash(directory / SOURCE_ZIP, release.get('source_files')) != release.get('source_sha256'):
        raise ValueError('Source snapshot checksum mismatch')
    with zipfile.ZipFile(directory / binary_zip) as archive:
        exe_name = f'{folder}/{executable}'
        readme_name = f'{folder}/{instructions}'
        if sorted(archive.namelist()) != sorted([exe_name, readme_name]):
            raise ValueError('Unexpected files in binary ZIP')
        if target == 'linux' and not archive.getinfo(exe_name).external_attr >> 16 & 0o111:
            raise ValueError('The Linux ZIP does not preserve executable permission')
        with archive.open(exe_name) as handle:
            if hashlib.file_digest(handle, 'sha256').hexdigest() != release.get('binary_sha256'):
                raise ValueError('The zipped executable differs from the tested executable')
        readme = archive.read(readme_name)
        if not readme:
            raise ValueError('Missing package instructions')
    return release


def build_release(root=ROOT, tag=None):
    root = Path(root).resolve()
    target, environment = _host()
    version = read_version(root)
    tag = _tag(tag, version)
    pins = _locked_tools(root, target)
    paths = source_paths(root)
    initial_hash = snapshot_hash(root, paths)
    tag_dir = _output_directory(root, tag)
    destination = tag_dir / target
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f'{destination} already exists; choose a fresh tag')
    lock = tag_dir / f'.{target}.lock'
    # One writer per tag and platform; prior release directories are never reused.
    with lock.open('x', encoding='ascii') as handle:
        handle.write(f'{os.getpid()}\n')
    try:
        with tempfile.TemporaryDirectory(prefix='.building-', dir=tag_dir) as temporary:
            workspace = Path(temporary)
            snapshot = workspace / 'source'
            for name in paths:
                copy = snapshot / name
                copy.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(declared_file(root, name), copy)
            if snapshot_hash(snapshot, paths) != initial_hash or read_version(snapshot) != version:
                raise ValueError('Release inputs changed while making the snapshot')

            # Tests and PyInstaller both read the same immutable source snapshot.
            env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(workspace / 'pyinstaller-cache'))
            env[PROFILE_ENV] = str(workspace / 'test-profile')
            env['GURPS_REQUIRE_TK'] = '1'
            env.pop('PYTHONPATH', None)
            subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-q'],
                           cwd=snapshot, env=env, check=True, timeout=600)
            subprocess.run([sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm',
                            '--distpath', str(workspace / 'binary'), '--workpath', str(workspace / 'build'),
                            'packaging/GurpsCalculadora.spec'], cwd=snapshot, env=env, check=True, timeout=600)

            folder, executable, instructions = _package_names(target)
            binary = workspace / 'binary' / executable
            _check_binary(binary, target)
            verify_embedded_resources(binary, snapshot)
            startup = run_startup_check([binary], version)
            if source_paths(snapshot) != paths or snapshot_hash(snapshot, paths) != initial_hash:
                raise ValueError('Release inputs changed during testing or build')

            staged = workspace / 'release'
            staged.mkdir()
            binary_zip = f'{folder}.zip'
            _archive(staged / binary_zip, [
                (binary, f'{folder}/{executable}'),
                (declared_file(snapshot, f'packaging/{instructions}'), f'{folder}/{instructions}'),
            ])
            package_source(snapshot, staged / SOURCE_ZIP)
            artifacts = {name: sha256(staged / name) for name in (binary_zip, SOURCE_ZIP)}
            release = {
                'schema': RELEASE_SCHEMA, 'version': version, 'tag': tag, 'target': target,
                'environment': environment, 'python': platform.python_version(), 'build_tools': pins,
                'source_files': list(paths), 'source_sha256': initial_hash, 'archives': artifacts,
                'binary_sha256': sha256(binary), 'startup_check': startup,
            }
            (staged / 'release.json').write_text(json.dumps(release, indent=2, sort_keys=True) + '\n',
                                                encoding='utf-8')
            (staged / 'SHA256SUMS.txt').write_text(_checksums(artifacts), encoding='ascii')
            verify_release(staged)
            if destination.exists() or destination.is_symlink():
                raise FileExistsError(f'{destination} already exists; choose a fresh tag')
            staged.rename(destination)
    finally:
        lock.unlink()
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument('--tag', help='Git version tag (defaults to the current app version)')
    operation.add_argument('--verify', type=Path, help='Verify archives in an existing release directory')
    args = parser.parse_args()
    try:
        if args.verify is not None:
            result = verify_release(args.verify)
            print(f"Verified {result['tag']} ({result['target']}, {result['environment']}): {args.verify}")
        else:
            print(f'Verified release: {build_release(tag=args.tag)}')
    except (OSError, ValueError, TypeError, SyntaxError, zipfile.BadZipFile, subprocess.SubprocessError) as exc:
        print(f'Release failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
