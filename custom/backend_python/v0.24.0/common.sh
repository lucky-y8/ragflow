#!/usr/bin/env bash
# 公共路径与代理设置；本文件由同目录脚本加载，不改变宿主机配置。
set -euo pipefail
PACKAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$PACKAGE_DIR/versions.env"
BUILD_ROOT="$(realpath -m "${RAGFLOW_BUILD_DIR:-$PACKAGE_DIR/.build}")"
# 始终读取本脚本所在仓库的工作目录，包含尚未提交的修改和新增文件。
SOURCE_DIR="$(cd "$PACKAGE_DIR/../../.." && pwd)"
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
    local required_file
    for required_file in pyproject.toml uv.lock web/package.json docker/entrypoint.sh docker/service_conf.yaml.template; do
        if [[ ! -f "$SOURCE_DIR/$required_file" ]]; then
            echo "当前仓库缺少 $required_file：$SOURCE_DIR；请同步完整仓库，不能只复制构建目录。" >&2
            exit 1
        fi
    done
    # 允许工作区修改，也允许没有 .git 的源码副本；仅防止误用其他版本。
    if ! awk -v expected="$RAGFLOW_VERSION" '
        /^[[:space:]]*\[/ { project = ($0 ~ /^[[:space:]]*\[project\][[:space:]]*(#.*)?$/) }
        project && /^[[:space:]]*version[[:space:]]*=/ {
            split($0, value, /["\047]/); matches = (value[2] == expected)
        }
        END { exit !matches }
    ' "$SOURCE_DIR/pyproject.toml"; then
        echo "当前仓库的 project.version 必须为 $RAGFLOW_VERSION，请确认使用 v0.24.0-arm64 分支。" >&2
        exit 1
    fi
}
