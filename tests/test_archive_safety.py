from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import zipfile

from tools import build_archives


class ArchiveSafetyTests(unittest.TestCase):
    def test_source_excludes_books_images_temporaries_and_links(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("main.py", "rules.PDF", "map.png", "old.zip", "partial.tmp"):
                (root / name).write_text("test")
            books = root / "GURPS 4th Edition"
            books.mkdir()
            (books / "extract.txt").write_text("private reference")
            (root / "linked.py").symlink_to(root / "main.py")
            with patch.object(build_archives, "ROOT", root):
                build_archives.package_source()
            with zipfile.ZipFile(root / "GurpsCalculadora_Codigo_Fonte.zip") as archive:
                self.assertEqual(archive.namelist(), ["GurpsCalculadora/main.py"])

    def test_rejection_preserves_existing_archive(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "existing.zip"
            output.write_bytes(b"previous archive")
            book = root / "rules.pdf"
            book.write_bytes(b"private")
            with self.assertRaises(ValueError):
                build_archives._archive(output, [(book, Path("rules.pdf"))])
            self.assertEqual(output.read_bytes(), b"previous archive")

    def test_missing_distribution_does_not_make_empty_zip(self):
        with TemporaryDirectory() as directory, patch.object(build_archives, "ROOT", Path(directory)):
            with self.assertRaises(ValueError):
                build_archives.package_directory("GurpsCacul_Windows")
            self.assertFalse((Path(directory) / "GurpsCacul_Windows.zip").exists())
