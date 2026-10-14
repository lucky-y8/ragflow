"""用临时仓库和 Docker 替身检查源码选择，不下载依赖、不构建真实镜像。"""

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import unittest
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1]


class RepositoryDependencyTests(unittest.TestCase):
    def test_current_source_preserves_arm64_mini_racer_adaptation(self):
        # 防止同步业务源码时，用原版清单覆盖已迁移到根目录的 ARM64 排除项。
        source = PACKAGE.parents[2]
        project = tomllib.loads((source / "pyproject.toml").read_text())
        lock = tomllib.loads((source / "uv.lock").read_text())
        conflicts = {"akracer", "py-mini-racer"}
        self.assertTrue(conflicts <= set(project["tool"]["uv"].get("exclude-dependencies", [])), "根目录 pyproject.toml 缺少 MiniRacer 冲突包排除项")
        self.assertTrue(conflicts <= set(lock.get("manifest", {}).get("excludes", [])), "根目录 uv.lock 缺少 ARM64 排除项，请同步更新锁文件")
        packages = {package["name"]: package for package in lock["package"]}
        self.assertFalse(conflicts & packages.keys(), "锁文件重新引入了冲突包")
        self.assertEqual(packages["mini-racer"]["version"], "0.12.4")


@unittest.skipUnless(shutil.which("bash") and shutil.which("git"), "需要 Linux bash 和 git")
class BuildSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo with spaces"
        self.package = self.repo / "custom/backend_python/v0.24.0"
        self.package.mkdir(parents=True)
        for name in ("common.sh", "versions.env", "build.sh", "prepare.sh"):
            shutil.copyfile(PACKAGE / name, self.package / name)
        for name, content in {
            "pyproject.toml": '[project]\nname = "ragflow"\nversion = "0.24.0"\n',
            "uv.lock": "# fixture lock\n",
            "web/package.json": "{}",
            "docker/entrypoint.sh": "#!/bin/bash\n",
            "docker/service_conf.yaml.template": "{}",
            "api/edited.py": "original",
            "api/deleted.py": "delete me",
        }.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.write_command("uname", "print('aarch64' if '-m' in sys.argv else 'Linux')")
        self.write_command("curl", "raise SystemExit('Tests must not download anything')")
        self.write_command(
            "docker",
            """import json, os
from pathlib import Path
args = sys.argv[1:]
entry = {"args": args}
if args[:2] == ["buildx", "build"]:
    context = Path(args[-1])
    entry["edited"] = (context / "api/edited.py").read_text()
    entry["new_exists"] = (context / "new_business/module.py").is_file()
    entry["deleted_exists"] = (context / "api/deleted.py").exists()
with open(os.environ["FAKE_DOCKER_CALLS"], "a") as log:
    log.write(json.dumps(entry) + "\\n")
if args[:2] == ["image", "inspect"]:
    print("linux/arm64")
""",
        )
        self.cache = self.root / "existing cache"
        self.resources = self.cache / "resources"
        versions = dict(line.split("=", 1) for line in (self.package / "versions.env").read_text().splitlines() if line and not line.startswith("#"))
        for name in (
            "resources.ready.json",
            f"chrome-{versions['CHROME_VERSION']}-linux-arm64.zip",
            f"chromedriver-{versions['CHROME_VERSION']}-linux-arm64.zip",
            "uv-aarch64-unknown-linux-gnu.tar.gz",
            "libssl1.1_1.1.1f-1ubuntu2_arm64.deb",
            f"tika-server-standard-{versions['TIKA_VERSION']}.jar",
            f"tika-server-standard-{versions['TIKA_VERSION']}.jar.md5",
            "cl100k_base.tiktoken",
            "nltk_data/corpora/wordnet.zip",
            "nltk_data/tokenizers/punkt_tab",
            "huggingface.co/InfiniFlow/deepdoc",
            "huggingface.co/InfiniFlow/text_concat_xgb_v1.0",
        ):
            path = self.resources / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        self.calls = self.root / "docker-calls.jsonl"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("RAGFLOW_", "UV_", "NODE_BUILD_"))}
        self.env.update(
            PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            RAGFLOW_BUILD_DIR=str(self.cache),
            RAGFLOW_BUILDER="fixture-builder",
            FAKE_DOCKER_CALLS=str(self.calls),
        )

    def write_command(self, name, code):
        path = self.bin / name
        path.write_text(f"#!{sys.executable}\nimport sys\n{code}\n")
        path.chmod(0o755)

    def run_script(self, name):
        # 故意在仓库外执行，验证不是按当前命令目录或缓存目录选择源码。
        return subprocess.run(["bash", str(self.package / name)], cwd=self.root, env=self.env, capture_output=True, text=True, timeout=30)

    def build_call(self):
        return next(call for call in map(json.loads, self.calls.read_text().splitlines()) if call["args"][:2] == ["buildx", "build"])

    def test_build_uses_modified_untracked_and_deleted_working_files(self):
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"], check=True)
        (self.repo / "api/edited.py").write_text("working tree change")
        (self.repo / "api/deleted.py").unlink()
        (self.repo / "new_business").mkdir()
        (self.repo / "new_business/module.py").write_text("new untracked business code")
        old_source = self.cache / "source/api/edited.py"
        old_source.parent.mkdir(parents=True)
        old_source.write_text("obsolete downloaded source")
        result = self.run_script("build.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        call = self.build_call()
        self.assertEqual(call["args"][-1], str(self.repo))
        self.assertEqual(call["edited"], "working tree change")
        self.assertTrue(call["new_exists"])
        self.assertFalse(call["deleted_exists"])
        self.assertIn("SOURCE_STATE=modified", call["args"])
        self.assertIn(f"infiniflow/ragflow_deps:latest={self.resources}", call["args"])
        self.assertEqual(old_source.read_text(), "obsolete downloaded source")

    def test_complete_source_copy_without_git_is_supported(self):
        result = self.run_script("build.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SOURCE_REVISION=unknown", self.build_call()["args"])
        self.assertIn("SOURCE_STATE=unknown", self.build_call()["args"])

    def test_other_application_version_is_rejected_before_docker(self):
        (self.repo / "pyproject.toml").write_text('[project]\nversion = "0.27.0"\n')
        result = self.run_script("build.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("project.version", result.stderr)
        self.assertFalse(self.calls.exists())

    def test_missing_root_dependency_lock_is_rejected(self):
        (self.repo / "uv.lock").unlink()
        result = self.run_script("build.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("uv.lock", result.stderr)
        self.assertFalse(self.calls.exists())

    def test_prepare_reuses_resources_without_fetching_application_source(self):
        # 伪造已校验的 uv 下载包，仅记录调用。若 prepare 还执行 git clone 则测试失败。
        self.write_command("git", "raise SystemExit('prepare must not fetch application source')")
        uv_script = b'#!/bin/bash\nprintf "%s\\n" "$@" > "$RAGFLOW_BUILD_DIR/uv-call.txt"\n'
        archive = self.cache / "tools/uv-aarch64-unknown-linux-gnu.tar.gz"
        archive.parent.mkdir(parents=True)
        with tarfile.open(archive, "w:gz") as tar:
            info = tarfile.TarInfo("uv-aarch64-unknown-linux-gnu/uv")
            info.size = len(uv_script)
            info.mode = 0o755
            tar.addfile(info, io.BytesIO(uv_script))
        versions = self.package / "versions.env"
        versions.write_text(re.sub(r"UV_ARM64_SHA256=.*", f"UV_ARM64_SHA256={hashlib.sha256(archive.read_bytes()).hexdigest()}", versions.read_text()))
        result = self.run_script("prepare.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.cache / "source").exists())
        self.assertIn(str(self.package / "download_resources.py"), (self.cache / "uv-call.txt").read_text())
        self.assertEqual((self.repo / "api/edited.py").read_text(), "original")
        self.assertEqual((self.resources / archive.name).read_bytes(), archive.read_bytes())


if __name__ == "__main__":
    unittest.main()
