"""Validate configuration boundaries without importing RAGFlow or contacting services."""

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from render_config import build_config, write_config


def environment():
    return {
        "MYSQL_HOST": "mysql.internal",
        "MYSQL_DBNAME": "ragflow_test",
        "MYSQL_USER": "ragflow",
        "MYSQL_PASSWORD": "test-mysql-password",
        "REDIS_HOST": "redis.internal",
        "REDIS_PASSWORD": "",
        "ES_HOSTS": "https://es.internal:9243",
        "OBJECT_STORAGE_ENDPOINT": "https://objects.internal:9443",
        "OBJECT_STORAGE_BUCKET": "ragflow-test",
        "OBJECT_STORAGE_ACCESS_KEY": "test-access-key",
        "OBJECT_STORAGE_SECRET_KEY": "test-secret-key",
    }


class DeploymentConfigTests(unittest.TestCase):
    def test_nonstandard_ports_tls_and_passwordless_services(self):
        env = environment() | {"MYSQL_PORT": "3307", "REDIS_PORT": "6380", "REDIS_DB": "0"}
        config = build_config(env)
        self.assertEqual(config["mysql"]["port"], 3307)
        self.assertEqual(config["redis"]["host"], "redis.internal:6380")
        self.assertEqual(config["redis"]["db"], 0)
        self.assertEqual(config["redis"]["password"], "")
        self.assertNotIn("username", config["es"])
        self.assertTrue(config["es"]["verify_certs"])
        self.assertEqual(config["minio"]["host"], "objects.internal:9443")
        self.assertTrue(config["minio"]["secure"])
        self.assertTrue(config["minio"]["verify"])

    def test_s3_single_bucket_preserves_prefix_and_uses_sdk_signature(self):
        env = environment() | {"STORAGE_IMPL": "AWS_S3", "OBJECT_STORAGE_PREFIX": "/tenant-a/"}
        config = build_config(env)
        self.assertNotIn("minio", config)
        self.assertEqual(config["s3"]["prefix_path"], "tenant-a")
        self.assertEqual(config["s3"]["signature_version"], "s3v4")
        self.assertEqual(config["s3"]["addressing_style"], "path")

    def test_secret_characters_survive_rendering_and_file_replacement(self):
        secret = "a'\"#:$`$(touch never-run)\\unicode-密钥\nsecond line"
        env = environment() | {
            "MYSQL_PASSWORD": secret,
            "REDIS_PASSWORD": secret,
            "ES_USER": "reader",
            "ES_PASSWORD": secret,
            "OBJECT_STORAGE_SECRET_KEY": secret,
        }
        config = build_config(env)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local.service_conf.yaml"
            write_config(config, path)
            loaded = json.loads(path.read_text(encoding="utf-8"))
            for section in ("mysql", "redis", "es", "minio"):
                self.assertEqual(loaded[section]["password"], secret)
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            write_config(build_config(environment()), path)
            self.assertNotIn(secret, path.read_text(encoding="utf-8"))
            self.assertFalse(path.with_name(path.name + ".tmp").exists())

    def test_s3_secret_is_not_interpolated(self):
        secret = "'\"#:$()\\\n"
        config = build_config(environment() | {"STORAGE_IMPL": "AWS_S3", "OBJECT_STORAGE_SECRET_KEY": secret})
        self.assertEqual(config["s3"]["secret_key"], secret)

    def test_missing_or_placeholder_input_fails_without_exposing_secrets(self):
        for override in ({"MYSQL_HOST": "REPLACE_ME_MYSQL_HOST"}, {"MYSQL_PASSWORD": ""}, {"ES_PASSWORD": "REPLACE_ME_ES_PASSWORD"}):
            with self.subTest(override=next(iter(override))):
                with self.assertRaises(ValueError):
                    build_config(environment() | override)
        env = environment() | {"ES_PASSWORD": "private-password-must-not-appear"}
        with self.assertRaises(ValueError) as caught:
            build_config(env)
        self.assertNotIn(env["ES_PASSWORD"], str(caught.exception))

    def test_urls_do_not_accept_embedded_credentials(self):
        for key in ("ES_HOSTS", "OBJECT_STORAGE_ENDPOINT"):
            for url in ("https://name:private-password@host:443", "host:9200", "https://host:bad", "https://host/path", "https://host:0"):
                with self.subTest(key=key, url=url):
                    with self.assertRaises(ValueError) as caught:
                        build_config(environment() | {key: url})
                    self.assertNotIn("private-password", str(caught.exception))

    def test_invalid_ports_and_flags_are_rejected(self):
        for override in ({"MYSQL_PORT": "0"}, {"REDIS_PORT": "65536"}, {"REDIS_DB": "-1"}, {"ES_VERIFY_CERTS": "maybe"}):
            with self.subTest(override=override):
                with self.assertRaises(ValueError):
                    build_config(environment() | override)

    def test_multiple_es_nodes_and_authentication(self):
        config = build_config(environment() | {"ES_HOSTS": "https://es-1:9200, https://es-2:9200", "ES_USER": "elastic", "ES_PASSWORD": "password"})
        self.assertEqual(config["es"]["hosts"], "https://es-1:9200,https://es-2:9200")
        self.assertEqual(config["es"]["username"], "elastic")

    def test_unsupported_runtime_and_redis_endpoints_fail(self):
        for override in ({"API_PROXY_SCHEME": "go"}, {"DB_TYPE": "postgres"}, {"DOC_ENGINE": "infinity"}, {"STORAGE_IMPL": "S3"}, {"REDIS_HOST": "rediss://redis:6379"}, {"REDIS_HOST": "::1"}):
            with self.subTest(override=override):
                with self.assertRaises(ValueError):
                    build_config(environment() | override)

    def test_s3_single_bucket_cannot_silently_drop_object_prefixes(self):
        for prefix in ("", "/"):
            with self.subTest(prefix=prefix):
                with self.assertRaises(ValueError):
                    build_config(environment() | {"STORAGE_IMPL": "AWS_S3", "OBJECT_STORAGE_PREFIX": prefix})


if __name__ == "__main__":
    unittest.main()
