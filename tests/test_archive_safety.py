import hashlib
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import zipfile

from tools import build_archives
from tools.release_inputs import RESOURCE_MANIFEST, SOURCE_MANIFEST, source_paths
from tools.verify_gui_launch import run_startup_check
from utils.startup_check import PROFILE_ENV, REPORT_NAME


STARTUP = dict(version='1.2.3', main_window=True, title='GURPS', tk='8.6.13', tool_count=4,
               encounter_map_ranged=True, languages_checked=['pt_BR', 'en_US'])


class ArchiveSafetyTests(unittest.TestCase):
    @staticmethod
    def make_project(root):
        files = {
            'main.py': '# test source\n',
            'version.py': '__version__ = "1.2.3"\n',
            'tools/build_archives.py': '# test source\n',
            'packaging/GurpsCalculadora.spec': '# test spec\n',
            'packaging/LEIA-ME_LINUX.txt': 'Run GurpsCalculadora\n',
            'packaging/LEIA-ME_WINDOWS.txt': 'Run GurpsCalculadora.exe\n',
            RESOURCE_MANIFEST: 'data/weapons.json\n',
            'data/weapons.json': '{}\n',
        }
        files[SOURCE_MANIFEST] = '\n'.join(name for name in (*files, SOURCE_MANIFEST)
                                           if name != 'data/weapons.json')
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
        return sorted(files)

    def test_source_excludes_unlisted_files_including_within_public_directories(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            files = self.make_project(root)
            for name in ('.env', 'notes.txt', 'data/private.json', 'tools/scratch.py', 'rules.PDF',
                         'map.png', 'old.zip', 'partial.tmp', 'GURPS 4th Edition/extract.txt'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('private', encoding='utf-8')
            build_archives.package_source(root, root / 'new.zip')
            with zipfile.ZipFile(root / 'new.zip') as archive:
                self.assertEqual(archive.namelist(), [f'GurpsCalculadora/{name}' for name in files])

    def test_rejects_invalid_manifest_paths_and_leaves_existing_archive_intact(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_project(root)
            source_list = root / SOURCE_MANIFEST
            declared = source_list.read_text(encoding='utf-8')
            output = root / 'existing.zip'
            output.write_bytes(b'previous archive')
            for path in ('../rules.txt', '/private.txt', 'unsafe/rules.pdf', 'MAIN.PY', 'not-there.txt'):
                with self.subTest(path=path):
                    source_list.write_text(declared + '\n' + path + '\n', encoding='utf-8')
                    with self.assertRaises(ValueError):
                        build_archives.package_source(root, output)
                    self.assertEqual(output.read_bytes(), b'previous archive')
            source_list.write_text(declared, encoding='utf-8')
            with self.assertRaises(FileExistsError):
                build_archives.package_source(root, output)
            self.assertEqual(output.read_bytes(), b'previous archive')

    def test_rejects_declared_symlinks_when_supported(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_project(root)
            try:
                (root / 'tools/linked.py').symlink_to(root / 'main.py')
            except OSError as exc:
                self.skipTest(f'symbolic links not supported: {exc}')
            with (root / SOURCE_MANIFEST).open('a', encoding='utf-8') as handle:
                handle.write('\ntools/linked.py\n')
            with self.assertRaisesRegex(ValueError, 'Linked release input'):
                build_archives.package_source(root, root / 'new.zip')

    def test_startup_rejects_missing_or_mismatched_report(self):
        with patch('tools.verify_gui_launch.subprocess.run'):
            with self.assertRaisesRegex(ValueError, 'did not produce a startup report'):
                run_startup_check(['app'], '1.2.3')

        def simulate_start(command, *, cwd, env, check, timeout):
            self.assertEqual(command, ['app', '--startup-check'])
            self.assertTrue(check)
            self.assertGreater(timeout, 0)
            self.assertEqual(Path(env[PROFILE_ENV]).parent, Path(cwd))
            report = Path(cwd) / REPORT_NAME
            self.assertFalse(report.exists())
            report.write_text(json.dumps(STARTUP), encoding='utf-8')

        with patch('tools.verify_gui_launch.subprocess.run', side_effect=simulate_start):
            self.assertEqual(run_startup_check(['app'], '1.2.3'), STARTUP)
            with self.assertRaisesRegex(ValueError, 'working window at v9.0.0'):
                run_startup_check(['app'], '9.0.0')

    @unittest.skipUnless(os.name == 'posix', 'This fixture tests Linux permission bits')
    def test_linux_release_uses_fresh_verified_binary_and_detects_tampering(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            files = self.make_project(root)
            legacy = root / 'dist/GurpsCalculadora'
            legacy.parent.mkdir()
            legacy.write_bytes(b'stale executable')

            def run(command, *, cwd, env, check, timeout):
                self.assertTrue(check)
                self.assertGreater(timeout, 0)
                self.assertNotEqual(cwd, root)
                self.assertEqual((cwd / 'main.py').read_bytes(), (root / 'main.py').read_bytes())
                self.assertNotIn('PYTHONPATH', env)
                self.assertEqual(Path(env[PROFILE_ENV]).parent, cwd.parent)
                if command[2] == 'PyInstaller':
                    destination = Path(command[command.index('--distpath') + 1])
                    destination.mkdir()
                    header = bytearray(64)
                    header[:6] = b'\x7fELF\x02\x01'
                    header[16:20] = b'\x02\x00\x3e\x00'
                    binary = destination / 'GurpsCalculadora'
                    binary.write_bytes(header + b'fresh executable')
                    binary.chmod(0o755)

            def checked_start(command, version):
                self.assertNotEqual(command[0], legacy)
                self.assertEqual(version, '1.2.3')
                self.assertTrue(command[0].read_bytes().endswith(b'fresh executable'))
                return STARTUP

            with (patch.object(build_archives, '_host', return_value=('linux', 'native')),
                  patch.object(build_archives, '_check_linux_build_host'),
                  patch.object(build_archives, '_locked_tools', return_value={'pyinstaller': 'test'}),
                  patch.object(build_archives, 'verify_embedded_resources'),
                  patch.object(build_archives, 'verify_linux_abi', return_value='2.36'),
                  patch.object(build_archives, 'run_startup_check', side_effect=checked_start),
                  patch.object(build_archives, 'refresh_current', wraps=build_archives.refresh_current) as refresh,
                  patch.object(build_archives.subprocess, 'run', side_effect=run) as process):
                release_path = build_archives.build_release(root)
                self.assertEqual([c.args[0][2] for c in process.call_args_list], ['unittest', 'PyInstaller'])
                with self.assertRaises(FileExistsError):
                    build_archives.build_release(root)

            self.assertEqual(legacy.read_bytes(), b'stale executable')
            release = build_archives.verify_release(release_path)
            refresh.assert_called_once_with(root.resolve(), 'v1.2.3', require_pair=False,
                                            expected_source=release['source_sha256'])
            self.assertFalse((root / 'dist/atuais').exists())
            self.assertEqual(release['source_files'], files)
            self.assertEqual(release['tag'], 'v1.2.3')
            self.assertEqual(release['startup_check'], STARTUP)
            self.assertEqual(release['glibc_required_by_elf'], '2.36')
            (release_path / build_archives.SOURCE_ZIP).write_bytes(b'damaged')
            with self.assertRaisesRegex(ValueError, 'Checksum mismatch'):
                build_archives.verify_release(release_path)

    def test_failed_build_cannot_package_existing_binary(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_project(root)
            legacy = root / 'dist/GurpsCalculadora'
            legacy.parent.mkdir()
            legacy.write_bytes(b'stale executable')
            destination = root / 'dist/releases/v1.2.3/linux'
            with (patch.object(build_archives, '_host', return_value=('linux', 'native')),
                  patch.object(build_archives, '_check_linux_build_host'),
                  patch.object(build_archives, '_locked_tools', return_value={}),
                  patch.object(build_archives.subprocess, 'run') as process):
                with self.assertRaisesRegex(ValueError, 'Build did not create'):
                    build_archives.build_release(root)
                process.side_effect = subprocess.CalledProcessError(1, 'unittest')
                with self.assertRaises(subprocess.CalledProcessError):
                    build_archives.build_release(root)
            self.assertFalse(destination.exists())
            self.assertEqual(legacy.read_bytes(), b'stale executable')

    def test_glibc_check_reads_requirements_not_definitions(self):
        output = (
            "Version definition section '.gnu.version_d' contains 1 entry:\n"
            "  0x0010: Name: GLIBC_2.44\n"
            "Version needs section '.gnu.version_r' contains 1 entry:\n"
            "  0x0010: Name: GLIBC_2.2.5\n"
            "  0x0020: Name: GLIBC_ABI_DT_RELR\n"
        )
        with patch.object(build_archives.subprocess, 'run') as run:
            run.return_value.stdout = output
            self.assertEqual(list(build_archives._read_glibc_needs('fake', 'module')), [(2, 2, 5), (2, 36)])
            for dependency in ('GLIBC_2.44', 'GLIBC_PRIVATE', 'GLIBC_ABI_UNREVIEWED'):
                with self.subTest(dependency=dependency):
                    run.return_value.stdout = output + f"  0x0030: Name: {dependency}\n"
                    with self.assertRaisesRegex(ValueError, f'module.*{dependency}'):
                        list(build_archives._read_glibc_needs('fake', 'module'))

    def test_linux_abi_checks_embedded_math_not_only_the_bootloader(self):
        modules = {
            'PYZ.pyz': b'PYZ',
            'libpython3.12.so.1.0': b'\x7fELFpython',
            'python3.12/lib-dynload/math.so': b'\x7fELFmath',
        }
        archive = SimpleNamespace(toc=modules, extract=modules.__getitem__)

        def read_elf(command, **kwargs):
            path = Path(command[-1])
            dependency = 'GLIBC_2.44' if path.name == 'module.elf' and path.read_bytes().endswith(b'math') else 'GLIBC_2.34'
            return SimpleNamespace(stdout=f'Version needs section:\n Name: {dependency}\n')

        with (patch.object(build_archives, '_check_binary'),
              patch.object(build_archives, '_pyinstaller_archive', return_value=archive),
              patch.object(build_archives.subprocess, 'run', side_effect=read_elf)):
            with self.assertRaisesRegex(ValueError, 'math.so requires GLIBC_2.44'):
                build_archives.verify_linux_abi(Path('GurpsCalculadora'))


class CurrentPackagesTests(unittest.TestCase):
    TAG = 'v1.2.3'
    PREVIOUS_TAG = 'v1.2.3-anterior.1'

    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory())).resolve()
        ArchiveSafetyTests.make_project(self.root)
        self.current = self.root / 'dist/atuais'
        self.current.mkdir(parents=True)
        (self.current / 'GurpsCalculadora').write_bytes(b'previous Linux build')
        (self.current / 'GurpsCalculadora').chmod(0o755)
        (self.current / 'GurpsCalculadora.exe').write_bytes(b'previous Windows build')
        (self.current / f'GurpsCacul_Linux_{self.PREVIOUS_TAG}.zip').write_bytes(b'previous ZIP')
        (self.current / 'notas-locais.txt').write_text('Keep this', encoding='utf-8')
        (self.current / 'current.json').write_text(
            json.dumps({'tag': self.PREVIOUS_TAG, 'source_sha256': '0' * 64}), encoding='utf-8')
        self.before = self.current_files()

    def current_files(self):
        return {path.name: path.read_bytes() for path in self.current.iterdir() if path.is_file()}

    @staticmethod
    def binary_payload(target):
        if target == 'linux':
            header = bytearray(64)
            header[:6] = b'\x7fELF\x02\x01'
            header[16:20] = b'\x02\x00\x3e\x00'
        else:
            header = bytearray(90)
            header[:2] = b'MZ'
            header[60:64] = (64).to_bytes(4, 'little')
            header[64:70] = b'PE\x00\x00\x64\x86'
            header[86] = 0x02
            header[88:90] = b'\x0b\x02'
        return bytes(header) + f'updated {target} executable'.encode('ascii')

    def make_platform(self, target, *, invalid_executable=False):
        """Publish a small valid fixture without mocking either archive verifier."""
        destination = self.root / 'dist/releases' / self.TAG / target
        destination.mkdir(parents=True)
        folder, executable, readme = build_archives._package_names(target)
        payload = self.binary_payload(target)
        if invalid_executable:
            payload = b'This is not an executable'
        with TemporaryDirectory() as staging:
            binary = Path(staging) / executable
            binary.write_bytes(payload)
            binary.chmod(0o755)
            build_archives._archive(destination / f'{folder}.zip', [
                (binary, f'{folder}/{executable}'),
                (self.root / 'packaging' / readme, f'{folder}/{readme}'),
            ])
        sources = source_paths(self.root)
        source_zip = destination / build_archives.SOURCE_ZIP
        build_archives.package_source(self.root, source_zip)
        if target == 'windows':
            # ZIP metadata/compression need not be byte-identical across
            # platforms. The source tree contents and fingerprint must match.
            with zipfile.ZipFile(source_zip, 'a') as archive:
                archive.comment = b'different Windows ZIP metadata'
        artifacts = {name: build_archives.sha256(destination / name)
                     for name in (f'{folder}.zip', build_archives.SOURCE_ZIP)}
        release = {
            'schema': build_archives.RELEASE_SCHEMA, 'target': target, 'tag': self.TAG,
            'version': '1.2.3', 'environment': 'wine' if target == 'windows' else 'native',
            'source_files': list(sources), 'source_sha256': build_archives.snapshot_hash(self.root, sources),
            'archives': artifacts, 'binary_sha256': hashlib.sha256(payload).hexdigest(),
            'startup_check': STARTUP,
        }
        if target == 'linux':
            release['glibc_required_by_elf'] = '2.36'
        (destination / 'release.json').write_text(json.dumps(release), encoding='utf-8')
        (destination / 'SHA256SUMS.txt').write_text(build_archives._checksums(artifacts), encoding='ascii')
        return destination, payload, release

    def test_waits_for_both_platforms_without_changing_current(self):
        self.make_platform('linux')
        self.assertIsNone(build_archives.refresh_current(self.root, self.TAG, require_pair=False))
        with self.assertRaises((FileNotFoundError, ValueError)):
            build_archives.refresh_current(self.root, self.TAG)
        self.assertEqual(self.current_files(), self.before)

    def test_rejects_different_individually_valid_snapshots(self):
        linux, _, first = self.make_platform('linux')
        (self.root / 'main.py').write_text('# newer source snapshot\n', encoding='utf-8')
        windows, _, second = self.make_platform('windows')
        self.assertNotEqual(first['source_sha256'], second['source_sha256'])
        self.assertEqual(build_archives.verify_release(linux), first)
        self.assertEqual(build_archives.verify_release(windows), second)
        with self.assertRaises(ValueError):
            build_archives.refresh_current(self.root, self.TAG)
        self.assertEqual(self.current_files(), self.before)

    def test_rejects_corrupt_archive_without_changing_current(self):
        self.make_platform('linux')
        windows, _, _ = self.make_platform('windows')
        (windows / 'GurpsCacul_Windows.zip').write_bytes(b'damaged')
        with self.assertRaisesRegex(ValueError, 'Checksum mismatch'):
            build_archives.refresh_current(self.root, self.TAG)
        self.assertEqual(self.current_files(), self.before)

    def test_rejects_pair_from_unexpected_source_snapshot(self):
        self.make_platform('linux')
        self.make_platform('windows')
        with self.assertRaises(ValueError):
            build_archives.refresh_current(self.root, self.TAG, expected_source='f' * 64)
        self.assertEqual(self.current_files(), self.before)

    def test_rejects_invalid_executable_even_if_manifest_hashes_match(self):
        self.make_platform('linux')
        windows, _, _ = self.make_platform('windows', invalid_executable=True)
        build_archives.verify_release(windows)
        with self.assertRaises(ValueError):
            build_archives.refresh_current(self.root, self.TAG)
        self.assertEqual(self.current_files(), self.before)

    def test_activates_real_binaries_and_versioned_archives_preserving_other_files(self):
        linux, elf, first = self.make_platform('linux')
        windows, pe, second = self.make_platform('windows')
        self.assertNotEqual(first['archives'][build_archives.SOURCE_ZIP],
                            second['archives'][build_archives.SOURCE_ZIP])
        self.assertEqual(build_archives.refresh_current(self.root, self.TAG), self.current)
        self.assertEqual((self.current / 'GurpsCalculadora').read_bytes(), elf)
        self.assertEqual((self.current / 'GurpsCalculadora.exe').read_bytes(), pe)
        for filename in ('GurpsCalculadora', 'GurpsCalculadora.exe'):
            self.assertFalse((self.current / filename).is_symlink())
        if os.name == 'posix':
            self.assertTrue(os.access(self.current / 'GurpsCalculadora', os.X_OK))
        metadata = json.loads((self.current / 'current.json').read_text(encoding='utf-8'))
        self.assertEqual(metadata['tag'], self.TAG)
        self.assertEqual(metadata['source_sha256'], first['source_sha256'])
        for archive, manifest in (('GurpsCacul_Linux', first), ('GurpsCacul_Windows', second)):
            self.assertEqual(build_archives.sha256(self.current / f'{archive}_{self.TAG}.zip'),
                             manifest['archives'][f'{archive}.zip'])
        self.assertIn(
            build_archives.sha256(self.current / f'GurpsCalculadora_Codigo_Fonte_{self.TAG}.zip'),
            {release['archives'][build_archives.SOURCE_ZIP] for release in (first, second)},
        )
        after = self.current_files()
        for name in (f'GurpsCacul_Linux_{self.PREVIOUS_TAG}.zip', 'notas-locais.txt'):
            self.assertEqual(after[name], self.before[name])
        self.assertEqual(build_archives.verify_release(linux), first)
        self.assertEqual(build_archives.verify_release(windows), second)
        build_archives.refresh_current(self.root, self.TAG)
        self.assertEqual(self.current_files(), after)

    def test_refuses_to_overwrite_divergent_versioned_zip(self):
        self.make_platform('linux')
        self.make_platform('windows')
        (self.current / f'GurpsCacul_Windows_{self.TAG}.zip').write_bytes(b'user copy')
        before = self.current_files()
        with self.assertRaises((OSError, ValueError)):
            build_archives.refresh_current(self.root, self.TAG)
        self.assertEqual(self.current_files(), before)

    def test_uses_regular_zip_copies_when_symlinks_are_unavailable(self):
        _, _, linux = self.make_platform('linux')
        _, _, windows = self.make_platform('windows')
        with patch.object(Path, 'symlink_to', side_effect=OSError('symlinks are unavailable')):
            self.assertEqual(build_archives.refresh_current(self.root, self.TAG), self.current)
        for name, checksum in (
            ('GurpsCacul_Linux', linux['archives']['GurpsCacul_Linux.zip']),
            ('GurpsCacul_Windows', windows['archives']['GurpsCacul_Windows.zip']),
            ('GurpsCalculadora_Codigo_Fonte', linux['archives'][build_archives.SOURCE_ZIP]),
        ):
            archive = self.current / f'{name}_{self.TAG}.zip'
            self.assertTrue(archive.is_file())
            self.assertFalse(archive.is_symlink())
            self.assertEqual(build_archives.sha256(archive), checksum)

    def test_building_second_platform_automatically_activates_pair(self):
        _, elf, linux = self.make_platform('linux')
        pe = self.binary_payload('windows')

        def simulate_build(command, **kwargs):
            if command[2] == 'PyInstaller':
                destination = Path(command[command.index('--distpath') + 1])
                destination.mkdir()
                (destination / 'GurpsCalculadora.exe').write_bytes(pe)

        with (patch.object(build_archives, '_host', return_value=('windows', 'wine')),
              patch.object(build_archives, '_locked_tools', return_value={}),
              patch.object(build_archives, 'verify_embedded_resources'),
              patch.object(build_archives, 'run_startup_check', return_value=STARTUP),
              patch.object(build_archives.subprocess, 'run', side_effect=simulate_build)):
            windows = build_archives.build_release(self.root, self.TAG)
        self.assertEqual(build_archives.verify_release(windows)['source_sha256'], linux['source_sha256'])
        self.assertEqual((self.current / 'GurpsCalculadora').read_bytes(), elf)
        self.assertEqual((self.current / 'GurpsCalculadora.exe').read_bytes(), pe)
        metadata = json.loads((self.current / 'current.json').read_text(encoding='utf-8'))
        self.assertEqual(metadata['tag'], self.TAG)
        self.assertEqual(metadata['source_sha256'], linux['source_sha256'])

    def test_rejects_linked_destination_without_touching_its_target(self):
        self.make_platform('linux')
        self.make_platform('windows')
        linked_file = self.current / 'GurpsCalculadora.exe'
        foreign_file = self.root / 'external.exe'
        linked_file.rename(foreign_file)
        try:
            linked_file.symlink_to(foreign_file)
        except OSError as exc:
            self.skipTest(f'symbolic links not supported: {exc}')
        with self.assertRaises((OSError, ValueError)):
            build_archives.refresh_current(self.root, self.TAG)
        self.assertTrue(linked_file.is_symlink())
        self.assertEqual(foreign_file.read_bytes(), self.before['GurpsCalculadora.exe'])
        self.assertEqual(self.current_files(), self.before)

    def test_rolls_back_if_windows_executable_is_in_use(self):
        _, elf, _ = self.make_platform('linux')
        self.make_platform('windows')
        replace = os.replace
        failed = False

        def deny_once(source, destination, *args, **kwargs):
            nonlocal failed
            if not failed and Path(destination) == self.current / 'GurpsCalculadora.exe':
                self.assertEqual((self.current / 'GurpsCalculadora').read_bytes(), elf)
                failed = True
                raise PermissionError('Windows executable is still open')
            return replace(source, destination, *args, **kwargs)

        with patch.object(build_archives.os, 'replace', side_effect=deny_once):
            with self.assertRaises(PermissionError):
                build_archives.refresh_current(self.root, self.TAG)
        self.assertTrue(failed)
        self.assertEqual(self.current_files(), self.before)
