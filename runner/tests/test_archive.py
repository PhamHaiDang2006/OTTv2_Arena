import io
import stat
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from ottv2_runner.archive import extract_source
from ottv2_runner.errors import BotBuildError


def make_zip(entries, symlink=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, data in entries:
            archive.writestr(name, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "../escaped")
    return output.getvalue()


class SafeExtractionTests(unittest.TestCase):
    def test_extracts_supported_utf8_source_without_following_paths(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            files = extract_source(make_zip([("main.py", "print('ok')"), ("helper.py", "# helper")]), root, "python")
            self.assertEqual(len(files), 2)
            self.assertEqual((root / "main.py").read_text(encoding="utf-8"), "print('ok')")

    def test_rejects_traversal_duplicate_normalized_paths_and_symlinks(self):
        cases = [
            make_zip([("../main.py", "bad")]),
            make_zip([("main.py", "one"), ("MAIN.py", "two")]),
            make_zip([("x/../main.py", "two")]),
            make_zip([("main.py", "ok")], symlink="link.py"),
        ]
        for archive in cases:
            with self.subTest(archive_length=len(archive)), TemporaryDirectory() as directory:
                with self.assertRaises(BotBuildError):
                    extract_source(archive, Path(directory) / "source", "python")

    def test_rejects_wrong_entrypoint_nested_archives_and_limits(self):
        cases = [
            make_zip([("Dockerfile", "FROM bad"), ("main.py", "x")]),
            make_zip([("main.py", "x"), ("source.zip", "data")]),
            make_zip([("main.py", "x" * (1024 * 1024 + 1))]),
            make_zip([(f"{index}.txt", "x" * (1024 * 1024)) for index in range(6)] + [("main.py", "x")]),
            make_zip([(f"{index}.txt", "x") for index in range(51)] + [("main.py", "x")]),
        ]
        for archive in cases:
            with self.subTest(archive_length=len(archive)), TemporaryDirectory() as directory:
                with self.assertRaises(BotBuildError):
                    extract_source(archive, Path(directory) / "source", "python")

    def test_rejects_invalid_utf8(self):
        with TemporaryDirectory() as directory:
            with self.assertRaises(BotBuildError):
                extract_source(make_zip([("main.py", b"\xff")]), Path(directory) / "source", "python")


if __name__ == "__main__":
    unittest.main()
