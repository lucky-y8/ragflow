"""Offline regressions for build-time NLTK resource downloads."""

import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import download_deps


class NltkDownloadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("punkt_tab/english/abbrev_types.txt", "test")
        self.payload = stream.getvalue()
        self.checksum = hashlib.sha256(self.payload).hexdigest()
        self.packages = (("tokenizers", "punkt_tab", self.checksum, True),)
        self.archive = self.root / "tokenizers/punkt_tab.zip"
        self.extracted = self.root / "tokenizers/punkt_tab/english/abbrev_types.txt"

    def download(self, url, filename):
        self.assertEqual(
            url,
            f"https://raw.githubusercontent.com/nltk/nltk_data/{download_deps._NLTK_DATA_REVISION}/packages/tokenizers/punkt_tab.zip",
        )
        Path(filename).write_bytes(self.payload)

    def test_verified_download_and_cached_extraction_repair(self):
        with patch.object(download_deps, "_NLTK_PACKAGES", self.packages):
            with patch.object(download_deps.urllib.request, "urlretrieve", side_effect=self.download) as fetch:
                download_deps._download_nltk_data(self.root)
                fetch.assert_called_once()
            self.assertEqual(self.extracted.read_text(), "test")
            self.extracted.unlink()
            with patch.object(download_deps.urllib.request, "urlretrieve", side_effect=AssertionError("cache should avoid network")):
                download_deps._download_nltk_data(self.root)
            self.assertEqual(self.extracted.read_text(), "test")

    def test_bad_checksum_is_not_promoted_or_extracted(self):
        def corrupt(url, filename):
            Path(filename).write_bytes(b"not the official archive")

        with patch.object(download_deps, "_NLTK_PACKAGES", self.packages), patch.object(download_deps.urllib.request, "urlretrieve", side_effect=corrupt):
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                download_deps._download_nltk_data(self.root)
        self.assertFalse(self.archive.exists())
        self.assertFalse(self.extracted.exists())

    def test_interrupted_download_can_be_retried(self):
        def interrupted(url, filename):
            Path(filename).write_bytes(self.payload[:10])
            raise OSError("interrupted")

        with patch.object(download_deps, "_NLTK_PACKAGES", self.packages):
            with patch.object(download_deps.urllib.request, "urlretrieve", side_effect=interrupted):
                with self.assertRaises(OSError):
                    download_deps._download_nltk_data(self.root)
            self.assertFalse(self.archive.exists())
            with patch.object(download_deps.urllib.request, "urlretrieve", side_effect=self.download):
                download_deps._download_nltk_data(self.root)
        self.assertEqual(self.extracted.read_text(), "test")
        self.assertFalse(self.archive.with_suffix(".zip.part").exists())

    def test_corrupt_cached_archive_is_replaced(self):
        self.archive.parent.mkdir(parents=True)
        self.archive.write_bytes(b"old incomplete download")
        with patch.object(download_deps, "_NLTK_PACKAGES", self.packages), patch.object(download_deps.urllib.request, "urlretrieve", side_effect=self.download) as fetch:
            download_deps._download_nltk_data(self.root)
            fetch.assert_called_once()
        self.assertEqual(self.archive.read_bytes(), self.payload)

    def test_corpora_stay_zipped(self):
        packages = (("corpora", "wordnet", self.checksum, False),)
        with patch.object(download_deps, "_NLTK_PACKAGES", packages), patch.object(download_deps.urllib.request, "urlretrieve", side_effect=lambda url, path: Path(path).write_bytes(self.payload)):
            download_deps._download_nltk_data(self.root)
        self.assertEqual((self.root / "corpora/wordnet.zip").read_bytes(), self.payload)
        self.assertFalse((self.root / "corpora/wordnet").exists())

    def test_zip_cannot_write_outside_package(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("../escaped.txt", "unexpected")
        payload = stream.getvalue()
        packages = (("tokenizers", "punkt_tab", hashlib.sha256(payload).hexdigest(), True),)
        with patch.object(download_deps, "_NLTK_PACKAGES", packages), patch.object(download_deps.urllib.request, "urlretrieve", side_effect=lambda url, path: Path(path).write_bytes(payload)):
            with self.assertRaisesRegex(ValueError, "Unexpected path"):
                download_deps._download_nltk_data(self.root)
        self.assertFalse((self.root / "escaped.txt").exists())


if __name__ == "__main__":
    unittest.main()
