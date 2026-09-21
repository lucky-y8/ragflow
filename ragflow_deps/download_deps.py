#!/usr/bin/env python3

# PEP 723 metadata
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "huggingface-hub"
# ]
# ///

# This script downloads every artifact that the `infiniflow/ragflow_deps`
# Docker image bakes in. Run it from anywhere — the `__main__` block
# chdir's into this file's own directory, so all outputs land under
# `ragflow_deps/` regardless of the caller's CWD.
#
# Build-context relationship: `ragflow_deps/Dockerfile` is built with
# `ragflow_deps/` as its build context, so the files written here MUST
# sit at the top of `ragflow_deps/`. The Dockerfile's COPY lines assume
# top-level paths (`huggingface.co`, `nltk_data`, `cl100k_base.tiktoken`,
# `*.deb`, `*.jar`, `*.tar.gz`, `stagehand-server-v3-linux-<arch>`).
#
# Typical workflow:
#
#   uv run python3 ragflow_deps/download_deps.py            # download
#   cd ragflow_deps
#   docker build -f Dockerfile -t infiniflow/ragflow_deps .
#
# The main `Dockerfile` (built from the project root) pulls this image
# via `--mount=type=bind,from=infiniflow/ragflow_deps:latest,...` and
# is unaffected by where these files live locally.

import argparse
import hashlib
import os
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

# mirrors internal/common.DeepDocORTVersion (Go in-process backend). Single
# source for the onnxruntime native release: the download URL, .tgz name,
# extracted dir name, and SONAME below are all derived from it. The pip
# onnxruntime== pin (pyproject.toml) and the onnxruntime_go binding minor
# (go.mod) must stay on the same minor line.
ORT_VERSION = "1.23.2"


CHROME_VERSION = "153.0.8010.52"
NATIVE_ARCHIVES = [
    ("pdfium-linux-x64-static.tgz", "pdfium-static"),
    ("pdf_oxide-go-ffi-linux-amd64.tar.gz", "pdf_oxide"),
    ("office_oxide-linux-x86_64.tar.gz", "office_oxide"),
    (f"onnxruntime-linux-x64-static_lib-{ORT_VERSION}-glibc2_28.zip", os.path.join("onnxruntime", "static_lib")),
]


def get_urls(use_china_mirrors=False, *, image_only=False, architecture="all") -> list[str | list[str]]:
    architectures = {"amd64": ("x86_64", "linux64", "x64"), "arm64": ("aarch64", "linux-arm64", "arm64")}
    selected = architectures if architecture == "all" else {architecture: architectures[architecture]}
    maven = "https://repo.huaweicloud.com/repository/maven" if use_china_mirrors else "https://repo1.maven.org/maven2"
    chrome = "https://registry.npmmirror.com/-/binary/chrome-for-testing" if use_china_mirrors else "https://storage.googleapis.com/chrome-for-testing-public"
    urls = [
        f"{maven}/org/apache/tika/tika-server-standard/3.3.0/tika-server-standard-3.3.0.jar",
        f"{maven}/org/apache/tika/tika-server-standard/3.3.0/tika-server-standard-3.3.0.jar.md5",
        "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken",
    ]
    for arch, (uv_arch, chrome_platform, stagehand_arch) in selected.items():
        ubuntu = "http://archive.ubuntu.com/ubuntu" if arch == "amd64" else "http://ports.ubuntu.com"
        if use_china_mirrors:
            ubuntu = "http://mirrors.tuna.tsinghua.edu.cn/" + ("ubuntu" if arch == "amd64" else "ubuntu-ports")
        urls.extend(
            [
                f"{ubuntu}/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2_{arch}.deb",
                f"https://github.com/astral-sh/uv/releases/download/0.9.16/uv-{uv_arch}-unknown-linux-gnu.tar.gz",
                f"https://github.com/browserbase/stagehand/releases/download/stagehand-server-v3/v3.7.2/stagehand-server-v3-linux-{stagehand_arch}",
            ]
        )
        for binary in ("chrome", "chromedriver"):
            urls.append(
                [
                    f"{chrome}/{CHROME_VERSION}/{chrome_platform}/{binary}-{chrome_platform}.zip",
                    f"{binary}-{CHROME_VERSION}-{chrome_platform}.zip",
                ]
            )
    if not image_only:
        # Go native archives are Linux x86_64; Python images do not use them.
        urls.extend(
            [
                ["https://github.com/kognitos/pdfium-static/releases/download/chromium%2F7809/pdfium-linux-x64-static.tgz", NATIVE_ARCHIVES[0][0]],
                ["https://github.com/yfedoseev/pdf_oxide/releases/download/v0.3.73/pdf_oxide-go-ffi-linux-amd64.tar.gz", NATIVE_ARCHIVES[1][0]],
                ["https://github.com/yfedoseev/office_oxide/releases/download/v0.1.9/native-linux-x86_64.tar.gz", NATIVE_ARCHIVES[2][0]],
                [f"https://github.com/csukuangfj/onnxruntime-libs/releases/download/v{ORT_VERSION}/{NATIVE_ARCHIVES[3][0]}", NATIVE_ARCHIVES[3][0]],
            ]
        )
    return urls


# Official nltk_data index.xml at this revision supplies the archive checksums.
# Fixed URLs work through the build proxy without NLTK's local DNS preflight.
_NLTK_DATA_REVISION = "550b6625bcef1f2abff2ff770a5a0d272c9c6b2a"
_NLTK_PACKAGES = (
    # api/validation.py requests omw-1.4; locked NLTK 3.10.3 reads omw-2.0.
    ("corpora", "omw-2.0", "049c0de0a2d097f6d4d1c97394ea8422bba1faaa30f92e054f18efdb534423ed", False),
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
            # Re-extract verified tokenizers so interrupted extraction is repaired.
            with zipfile.ZipFile(archive) as package:
                destination = (directory / name).resolve()
                for member in package.infolist():
                    if not (directory / member.filename).resolve().is_relative_to(destination):
                        raise ValueError(f"Unexpected path in NLTK {name}: {member.filename}")
                package.extractall(directory)


repos = [
    "InfiniFlow/text_concat_xgb_v1.0",
    "InfiniFlow/deepdoc",
]


def download_model(repository_id):
    from huggingface_hub import snapshot_download

    local_directory = os.path.abspath(os.path.join("huggingface.co", repository_id))
    os.makedirs(local_directory, exist_ok=True)
    snapshot_download(repo_id=repository_id, local_dir=local_directory)


if __name__ == "__main__":
    # Anchor CWD to this file's directory so all relative outputs
    # (huggingface.co/, nltk_data/, *.deb, *.jar, *.tar.gz, etc.) land
    # at the top of ragflow_deps/ regardless of where the user invokes
    # the script from. This is the build context for `ragflow_deps/Dockerfile`.
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    parser = argparse.ArgumentParser(description="Download dependencies with optional China mirror support")
    parser.add_argument("--china-mirrors", action="store_true", help="Use China-accessible mirrors for downloads")
    parser.add_argument("--image-only", action="store_true", help="Skip Go native libraries and Go model checks")
    parser.add_argument("--architecture", choices=("all", "amd64", "arm64"), default="all", help="Architecture of image resources to download")
    args = parser.parse_args()

    urls = get_urls(args.china_mirrors, image_only=args.image_only, architecture=args.architecture)

    # Some mirrors (e.g. archive.ubuntu.com) reject the default urllib
    # User-Agent with HTTP 403, so install an opener with a browser-like UA.
    opener = urllib.request.build_opener()
    opener.addheaders = [("User-Agent", "Mozilla/5.0")]
    urllib.request.install_opener(opener)

    for url in urls:
        download_url = url[0] if isinstance(url, list) else url
        filename = url[1] if isinstance(url, list) else url.split("/")[-1]
        print(f"Downloading {filename} from {download_url}...")
        if not os.path.exists(filename):
            temporary = filename + ".part"
            urllib.request.urlretrieve(download_url, temporary)
            os.replace(temporary, filename)

    if not args.image_only:
        # Extract native static libraries to ~/ragflow-native-libs for Go build.
        # Ensures build.sh can find them without network access.
        native_deps_dir = os.path.expanduser("~/ragflow-native-libs")
        extractions = NATIVE_ARCHIVES
        import tarfile

        def _prune_stale_onnxruntime(static_lib_dir, version):
            """Remove ONNX Runtime version dirs under static_lib that do NOT match
            `version`. Without this, a version bump leaves the stale dir next to
            the new one and build.sh's `find ... -name '*.a'` links BOTH (duplicate
            symbols / wrong version, silently)."""
            if not os.path.isdir(static_lib_dir):
                return
            expected = f"onnxruntime-linux-x64-static_lib-{version}-glibc2_28"
            for name in os.listdir(static_lib_dir):
                if not name.startswith("onnxruntime-linux-x64-static_lib-"):
                    continue
                if name == expected:
                    continue
                stale = os.path.join(static_lib_dir, name)
                print(f"  Removing stale ONNX Runtime dir: {stale}")
                shutil.rmtree(stale)

        for archive, subdir in extractions:
            archive_path = os.path.join(os.getcwd(), archive)
            if not os.path.isfile(archive_path):
                print(f"  Skipping extraction: {archive} not found")
                continue
            target = os.path.join(native_deps_dir, subdir)

            # ONNX Runtime ships a version-stamped top-level dir inside the zip
            # (onnxruntime-linux-x64-static_lib-<ORT_VERSION>-glibc2_28/). A plain
            # "any .a present?" skip would keep a STALE version in place after a
            # bump: the new zip downloads, but extraction is skipped because the
            # old .a is still under static_lib, so the bump silently does nothing.
            # Prune stale version dirs and only skip when the matching version is
            # already extracted.
            if subdir == os.path.join("onnxruntime", "static_lib"):
                _prune_stale_onnxruntime(target, ORT_VERSION)
                version_dir = os.path.join(target, f"onnxruntime-linux-x64-static_lib-{ORT_VERSION}-glibc2_28")
                if os.path.isdir(version_dir) and any(f.endswith(".a") for _, _, files in os.walk(version_dir) for f in files):
                    print(f"  ✓ {subdir} ({ORT_VERSION}) already extracted to {version_dir}")
                    continue

            if os.path.isdir(target) and any(f.endswith(".a") for _, _, files in os.walk(target) for f in files):
                print(f"  ✓ {subdir} already extracted to {target}")
                continue
            os.makedirs(target, exist_ok=True)
            print(f"  Extracting {archive} → {target}")
            if archive_path.endswith(".zip"):
                with zipfile.ZipFile(archive_path) as zf:
                    zf.extractall(target)
            else:
                with tarfile.open(archive_path) as tf:
                    tf.extractall(target)

        # ONNX Runtime is statically linked into the server binary, so there is no
        # runtime .so to surface. Log where build.sh (ONNXRUNTIME_STATIC_PREFIX) will
        # find the archives — the .a files live under
        # ~/ragflow-native-libs/onnxruntime/static_lib. The in-process backend
        # resolves OrtGetApiBase via dlopen(NULL); there is no dynamic .so fallback.
        ort_static_dir = os.path.join(native_deps_dir, "onnxruntime", "static_lib")
        ort_a_files = [os.path.join(root, f) for root, _, files in os.walk(ort_static_dir) for f in files if f.endswith(".a")]
        if ort_a_files:
            print(f"  ✓ onnxruntime static archives ready: {len(ort_a_files)} .a under {ort_static_dir}")
        else:
            print(f"  Skipping onnxruntime static check: no .a found under {ort_static_dir}")

    _download_nltk_data(Path("nltk_data"))

    for repo_id in repos:
        print(f"Downloading huggingface repo {repo_id}...")
        download_model(repo_id)

    if not args.image_only:
        # Guard: the Go in-process DeepDoc backend loads the .ort weights from the
        # InfiniFlow/deepdoc snapshot pulled above. snapshot_download fetches the
        # whole repo, so these must be present; fail loudly if a future repo layout
        # drops them, so the Go backend can never silently ship without its models.
        # (internal/common.DeepDocModelFiles is the authoritative list.)
        deepdoc_local = os.path.abspath(os.path.join("huggingface.co", "InfiniFlow", "deepdoc"))
        go_model_files = ["det.ort", "layout.ort", "tsr.ort", "rec.ort", "ocr.res"]
        if not os.path.isdir(deepdoc_local):
            print(
                f"  ERROR: {deepdoc_local} does not exist; the InfiniFlow/deepdoc snapshot did not materialize.",
                file=sys.stderr,
            )
            sys.exit(1)
        missing_models = [f for f in go_model_files if not os.path.isfile(os.path.join(deepdoc_local, f))]
        if missing_models:
            for f in missing_models:
                print(
                    f"  ERROR: expected Go model file {f} missing from {deepdoc_local}; the InfiniFlow/deepdoc snapshot no longer ships .ort weights.",
                    file=sys.stderr,
                )
            sys.exit(1)
        print(f"  ✓ Go .ort model files present under {deepdoc_local}")
