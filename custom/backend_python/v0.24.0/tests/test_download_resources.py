"""只验证缓存完整性和压缩包路径，不连接下载站点。"""

import hashlib
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import download_resources as resources


class ResourceDownloadTests(unittest.TestCase):
    def test_failed_checksum_does_not_publish_partial_download(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "artifact"
            with patch.object(resources.urllib.request, "urlopen", side_effect=lambda *args, **kwargs: io.BytesIO(b"bad")), patch.object(resources.time, "sleep"):
                with self.assertRaises(ValueError):
                    resources.download_file("https://example.invalid/artifact", target, hashlib.sha256(b"good").hexdigest())
            self.assertFalse(target.exists())
            self.assertTrue(target.with_name("artifact.part").exists())

    def test_good_download_replaces_corrupt_cache_and_reuses_verified_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "artifact"
            target.write_bytes(b"bad")
            checksum = hashlib.sha256(b"good").hexdigest()
            with patch.object(resources.urllib.request, "urlopen", return_value=io.BytesIO(b"good")) as network:
                resources.download_file("https://example.invalid/artifact", target, checksum)
                resources.download_file("https://example.invalid/artifact", target, checksum)
            self.assertEqual(target.read_bytes(), b"good")
            self.assertEqual(network.call_count, 1)
            self.assertFalse(target.with_name("artifact.part").exists())

    def test_nltk_extraction_rejects_paths_outside_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "tokenizers/punkt_tab.zip"
            target.parent.mkdir()
            with zipfile.ZipFile(target, "w") as archive:
                archive.writestr("../escape.txt", "not allowed")
            packages = (("tokenizers", "punkt_tab", resources._sha256(target), True),)
            with patch.object(resources, "_NLTK_PACKAGES", packages):
                with self.assertRaisesRegex(ValueError, "Unexpected path"):
                    resources._download_nltk_data(root)
            self.assertFalse((root / "escape.txt").exists())


if __name__ == "__main__":
    unittest.main()
