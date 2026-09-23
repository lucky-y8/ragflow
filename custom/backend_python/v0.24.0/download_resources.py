#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["huggingface-hub==1.3.1"]
# ///
"""下载 v0.24.0 的 ARM64 镜像资源，不调用 nltk.download()，避免代理环境中的 DNS 预检查。"""

import argparse
import hashlib
import json
import os
import shutil
import time
import urllib.request
import zipfile
from pathlib import Path

CHROME_VERSION = "153.0.8010.52"
UV_SHA256 = "a8e9e3f7e621e212d9663ea28827bd8fb9ec11c453ae88d520b48e969e9ff5db"
MODELS = {
    "InfiniFlow/deepdoc": "9c7aa2c730d7a242d7f04cf6109a6a239aefc717",
    "InfiniFlow/text_concat_xgb_v1.0": "722ed09a54f23f14fe0279ce6b74ce18e1960f54",
}

_NLTK_DATA_REVISION = "550b6625bcef1f2abff2ff770a5a0d272c9c6b2a"
_NLTK_PACKAGES = (
    # v0.24.0 锁定的 NLTK 3.9.2 使用 wordnet、punkt_tab；保留其多语言语料。
    ("corpora", "omw-1.4", "3b941e664852f3297b6040236626065796a2aaf7d7f9eec8779a3beaa1096c2d", False),
    ("corpora", "wordnet", "cbda5ea6eef7f36a97a43d4a75f85e07fccbb4f23657d27b4ccbc93e2646ab59", False),
    ("tokenizers", "punkt", "51c3078994aeaf650bfc8e028be4fb42b4a0d177d41c012b6a983979653660ec", True),
    ("tokenizers", "punkt_tab", "e57f64187974277726a3417ca6f181ec5403676c717672eef6a748a7b20e0106", True),
)


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_nltk_data(download_dir):
    for category, name, checksum, unzip in _NLTK_PACKAGES:
        directory = Path(download_dir) / category
        directory.mkdir(parents=True, exist_ok=True)
        archive = directory / f"{name}.zip"
        if not archive.is_file() or _sha256(archive) != checksum:
            url = f"https://raw.githubusercontent.com/nltk/nltk_data/{_NLTK_DATA_REVISION}/packages/{category}/{name}.zip"
            temporary = archive.with_suffix(".zip.part")
            print(f"Downloading nltk {name} from {url}...")
            urllib.request.urlretrieve(url, temporary)
            if _sha256(temporary) != checksum:
                raise ValueError(f"SHA-256 mismatch for NLTK {name}; incomplete or unexpected archive: {temporary}")
            temporary.replace(archive)
        else:
            print(f"Using verified nltk {name} archive")
        if unzip:
            # 从校验通过的压缩包重新解压，修复上次中断的分词器目录。
            with zipfile.ZipFile(archive) as package:
                destination = (directory / name).resolve()
                for member in package.infolist():
                    if not (directory / member.filename).resolve().is_relative_to(destination):
                        raise ValueError(f"Unexpected path in NLTK {name}: {member.filename}")
                package.extractall(directory)


def resource_urls():
    """只下载该版本实际用到的 ARM64 文件，不需要 Go 或 stagehand 二进制。"""
    maven = "https://repo1.maven.org/maven2/org/apache/tika/tika-server-standard/3.2.3/"
    files = {
        "tika-server-standard-3.2.3.jar": maven + "tika-server-standard-3.2.3.jar",
        "tika-server-standard-3.2.3.jar.md5": maven + "tika-server-standard-3.2.3.jar.md5",
        "cl100k_base.tiktoken": "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken",
        "libssl1.1_1.1.1f-1ubuntu2_arm64.deb": "http://ports.ubuntu.com/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2_arm64.deb",
        "uv-aarch64-unknown-linux-gnu.tar.gz": "https://github.com/astral-sh/uv/releases/download/0.9.16/uv-aarch64-unknown-linux-gnu.tar.gz",
    }
    for binary in ("chrome", "chromedriver"):
        files[f"{binary}-{CHROME_VERSION}-linux-arm64.zip"] = f"https://storage.googleapis.com/chrome-for-testing-public/{CHROME_VERSION}/linux-arm64/{binary}-linux-arm64.zip"
    return files


def download_file(url, destination, checksum=None):
    """先写 .part，再替换目标；校验失败不会把半成品当成可用缓存。"""
    if destination.is_file() and destination.stat().st_size and (checksum is None or _sha256(destination) == checksum):
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as stream:
                shutil.copyfileobj(response, stream)
            if not temporary.stat().st_size:
                raise ValueError(f"下载为空：{destination.name}")
            if checksum and _sha256(temporary) != checksum:
                raise ValueError(f"SHA-256 校验失败：{destination.name}")
            temporary.replace(destination)
            return
        except (OSError, ValueError):
            if attempt == 2:
                raise
            time.sleep(2**attempt)


def main():
    parser = argparse.ArgumentParser(description="下载 RAGFlow v0.24.0 ARM64 镜像依赖")
    parser.add_argument("--output", type=Path, required=True, help="资源目录，可用 RAGFLOW_RESOURCE_DIR 复用已有下载")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    ready = output / "resources.ready.json"
    # 重新准备时先取消完成标记，任何中途失败都不允许进入构建步骤。
    ready.unlink(missing_ok=True)
    opener = urllib.request.build_opener()
    opener.addheaders = [("User-Agent", "Mozilla/5.0")]
    urllib.request.install_opener(opener)
    for filename, url in resource_urls().items():
        print(f"准备资源：{filename}", flush=True)
        download_file(url, output / filename, UV_SHA256 if filename.startswith("uv-") else None)
        if filename.endswith(".zip"):
            with zipfile.ZipFile(output / filename) as archive:
                if archive.testzip() is not None:
                    raise ValueError(f"ZIP 校验失败：{filename}，请移走损坏文件后重试")
    tika = output / "tika-server-standard-3.2.3.jar"
    expected = (output / "tika-server-standard-3.2.3.jar.md5").read_text().split()[0].lower()
    if hashlib.md5(tika.read_bytes()).hexdigest() != expected:
        raise ValueError("Tika MD5 校验失败，请移走损坏的 jar 后重试")
    _download_nltk_data(output / "nltk_data")

    # 仅在执行下载时导入；本脚本的单元测试不需要下载模型或安装此依赖。
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    from huggingface_hub import snapshot_download

    for repository, revision in MODELS.items():
        print(f"准备模型：{repository} @ {revision}", flush=True)
        snapshot_download(repo_id=repository, revision=revision, local_dir=str(output / "huggingface.co" / repository))
    ready.write_text(json.dumps({"ragflow": "v0.24.0", "chrome": CHROME_VERSION, "models": MODELS}, indent=2) + "\n")
    print("全部 ARM64 资源准备完成。")


if __name__ == "__main__":
    main()
