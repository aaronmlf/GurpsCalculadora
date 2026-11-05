import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import zipfile

from tools import build_archives
from tools.release_inputs import RESOURCE_MANIFEST, SOURCE_MANIFEST
from tools.verify_gui_launch import run_startup_check
from utils.startup_check import PROFILE_ENV, REPORT_NAME


STARTUP = dict(version='1.2.3', main_window=True, title='GURPS', tk='8.6.13', tool_count=4)


class ArchiveSafetyTests(unittest.TestCase):
    def make_project(self, root):
        files = {
            'main.py': '# test source\n',
            'version.py': '__version__ = "1.2.3"\n',
            'tools/build_archives.py': '# test source\n',
            'packaging/GurpsCalculadora.spec': '# test spec\n',
            'packaging/LEIA-ME_LINUX.txt': 'Run GurpsCalculadora\n',
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
                  patch.object(build_archives, '_locked_tools', return_value={'pyinstaller': 'test'}),
                  patch.object(build_archives, 'verify_embedded_resources'),
                  patch.object(build_archives, 'run_startup_check', side_effect=checked_start),
                  patch.object(build_archives.subprocess, 'run', side_effect=run) as process):
                release_path = build_archives.build_release(root)
                self.assertEqual([c.args[0][2] for c in process.call_args_list], ['unittest', 'PyInstaller'])
                with self.assertRaises(FileExistsError):
                    build_archives.build_release(root)

            self.assertEqual(legacy.read_bytes(), b'stale executable')
            release = build_archives.verify_release(release_path)
            self.assertEqual(release['source_files'], files)
            self.assertEqual(release['tag'], 'v1.2.3')
            self.assertEqual(release['startup_check'], STARTUP)
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
                  patch.object(build_archives, '_locked_tools', return_value={}),
                  patch.object(build_archives.subprocess, 'run') as process):
                with self.assertRaisesRegex(ValueError, 'Build did not create'):
                    build_archives.build_release(root)
                process.side_effect = subprocess.CalledProcessError(1, 'unittest')
                with self.assertRaises(subprocess.CalledProcessError):
                    build_archives.build_release(root)
            self.assertFalse(destination.exists())
            self.assertEqual(legacy.read_bytes(), b'stale executable')
