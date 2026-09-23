#!/usr/bin/env bash
# 下载固定版本的源码和 ARM64 资源；不安装应用到宿主机，不启动任何中间件。
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
require_arm64
for command_name in git curl tar sha256sum; do
    command -v "$command_name" >/dev/null || { echo "缺少工具：$command_name" >&2; exit 1; }
done
mkdir -p "$BUILD_ROOT/tools" "$RESOURCE_DIR"
if [[ ! -e "$SOURCE_DIR" ]]; then
    git clone --depth 1 --branch "$RAGFLOW_REF" https://github.com/infiniflow/ragflow.git "$SOURCE_DIR"
fi
verify_source

# 使用单独缓存的 uv 0.9.16；不依赖用户 PATH，也不覆盖已安装的 uv。
uv_archive="$BUILD_ROOT/tools/uv-aarch64-unknown-linux-gnu.tar.gz"
if [[ ! -f "$uv_archive" ]] || ! echo "$UV_ARM64_SHA256  $uv_archive" | sha256sum --check --status; then
    curl -fL --retry 3 "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-aarch64-unknown-linux-gnu.tar.gz" -o "$uv_archive.part"
    echo "$UV_ARM64_SHA256  $uv_archive.part" | sha256sum --check --status
    mv "$uv_archive.part" "$uv_archive"
fi
tar -xzf "$uv_archive" -C "$BUILD_ROOT/tools"
cp "$uv_archive" "$RESOURCE_DIR/uv-aarch64-unknown-linux-gnu.tar.gz"
"$BUILD_ROOT/tools/uv-aarch64-unknown-linux-gnu/uv" run --python "$PYTHON_VERSION" --script \
    "$PACKAGE_DIR/download_resources.py" --output "$RESOURCE_DIR"
echo "资源准备完成：$BUILD_ROOT"
echo "下一步：使用具备 Docker 权限的用户运行 bash build.sh。"
