#!/usr/bin/env bash
# 公共路径与代理设置；本文件由同目录脚本加载，不改变宿主机配置。
set -euo pipefail
PACKAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$PACKAGE_DIR/versions.env"
BUILD_ROOT="$(realpath -m "${RAGFLOW_BUILD_DIR:-$PACKAGE_DIR/.build}")"
SOURCE_DIR="$BUILD_ROOT/source"
RESOURCE_DIR="$(realpath -m "${RAGFLOW_RESOURCE_DIR:-$BUILD_ROOT/resources}")"
IMAGE="${RAGFLOW_IMAGE:-ragflow:v0.24.0-arm64}"
BUILDER="${RAGFLOW_BUILDER:-ragflow-arm64-proxy}"
export DOCKER_CLI_EXPERIMENTAL=enabled
proxy="${RAGFLOW_BUILD_PROXY:-${HTTPS_PROXY:-${HTTP_PROXY:-}}}"
if [[ -n "$proxy" ]]; then
    export HTTP_PROXY="$proxy" HTTPS_PROXY="$proxy" http_proxy="$proxy" https_proxy="$proxy"
fi

require_arm64() {
    if [[ "$(uname -s)" != Linux || "$(uname -m)" != aarch64 ]]; then
        echo "请在 Linux ARM64（uname -m 为 aarch64）的构建电脑上执行。" >&2
        exit 1
    fi
}

verify_source() {
    if [[ ! -d "$SOURCE_DIR/.git" ]]; then
        echo "缺少独立源码目录，请先执行 bash prepare.sh。" >&2
        exit 1
    fi
    if [[ "$(git -c safe.directory="$SOURCE_DIR" -C "$SOURCE_DIR" rev-parse HEAD)" != "$RAGFLOW_COMMIT" ]]; then
        echo "源码不是版本清单中的 v0.24.0 提交，停止构建。" >&2
        exit 1
    fi
    if [[ -n "$(git -c safe.directory="$SOURCE_DIR" -C "$SOURCE_DIR" status --porcelain --untracked-files=normal)" ]]; then
        echo "独立源码目录有修改，请使用新的 RAGFLOW_BUILD_DIR 重新准备；脚本不会重置已有修改。" >&2
        exit 1
    fi
}
