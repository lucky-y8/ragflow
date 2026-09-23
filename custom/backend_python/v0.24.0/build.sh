#!/usr/bin/env bash
# 在原生 ARM64 主机上使用已有的代理 Builder 构建；不会修改当前仓库的源码。
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
require_arm64
verify_source
if [[ ! -f "$RESOURCE_DIR/resources.ready.json" ]]; then
    echo "依赖资源未准备完成，请先执行 bash prepare.sh。" >&2
    exit 1
fi
required=("chrome-$CHROME_VERSION-linux-arm64.zip" "chromedriver-$CHROME_VERSION-linux-arm64.zip"
    uv-aarch64-unknown-linux-gnu.tar.gz libssl1.1_1.1.1f-1ubuntu2_arm64.deb
    "tika-server-standard-$TIKA_VERSION.jar" "tika-server-standard-$TIKA_VERSION.jar.md5"
    cl100k_base.tiktoken nltk_data/corpora/wordnet.zip nltk_data/tokenizers/punkt_tab
    huggingface.co/InfiniFlow/deepdoc huggingface.co/InfiniFlow/text_concat_xgb_v1.0)
for resource in "${required[@]}"; do
    [[ -e "$RESOURCE_DIR/$resource" ]] || { echo "缺少资源：$resource，请重新运行 prepare.sh。" >&2; exit 1; }
done
proxy_args=()
if [[ -n "$proxy" ]]; then
    proxy_args=(--build-arg "http_proxy=$proxy" --build-arg "https_proxy=$proxy")
fi
# 软件源只接受不含认证信息的 HTTP(S) 地址，避免错误替换源文件。
apt_mirror="${RAGFLOW_APT_MIRROR:-https://ports.ubuntu.com/ubuntu-ports}"
if [[ ! "$apt_mirror" =~ ^https?://[A-Za-z0-9.-]+(:[0-9]+)?(/[A-Za-z0-9._~/-]+)?/?$ ]]; then
    echo "RAGFLOW_APT_MIRROR 必须是完整的 HTTP(S) 软件源地址。" >&2
    exit 1
fi
# Python 镜像源独立于 APT；低并发减少多个大包同时争用代理带宽。
pypi_mirror="${RAGFLOW_PYPI_MIRROR:-pypi}"
case "$pypi_mirror" in
    pypi|aliyun) ;;
    *) echo "RAGFLOW_PYPI_MIRROR 只支持 pypi 或 aliyun。" >&2; exit 1 ;;
esac
download_concurrency="${UV_CONCURRENT_DOWNLOADS:-4}"
http_timeout="${UV_HTTP_TIMEOUT:-600}"
if [[ ! "$download_concurrency" =~ ^[1-9][0-9]*$ || ! "$http_timeout" =~ ^[1-9][0-9]*$ ]]; then
    echo "UV_CONCURRENT_DOWNLOADS 和 UV_HTTP_TIMEOUT 必须为正整数。" >&2
    exit 1
fi
echo "Python 软件源：$pypi_mirror；下载并发：$download_concurrency；读取超时：${http_timeout}s"
docker buildx inspect "$BUILDER" --bootstrap
# 主上下文是固定提交源码；packaging 是本目录，资源上下文替代在线依赖镜像。
docker buildx build --builder "$BUILDER" --platform linux/arm64 --provenance=false --load \
    --file "$PACKAGE_DIR/Dockerfile" --target production \
    --build-context "packaging=$PACKAGE_DIR" \
    --build-context "infiniflow/ragflow_deps:latest=$RESOURCE_DIR" \
    --build-arg "NODE_BUILD_MAX_OLD_SPACE_SIZE=${NODE_BUILD_MAX_OLD_SPACE_SIZE:-4096}" \
    --build-arg "UV_CONCURRENT_BUILDS=${UV_CONCURRENT_BUILDS:-1}" \
    --build-arg "UBUNTU_APT_MIRROR=$apt_mirror" \
    --build-arg "PYPI_MIRROR=$pypi_mirror" \
    --build-arg "PYTHON_DOWNLOAD_CONCURRENCY=$download_concurrency" \
    --build-arg "PYTHON_DOWNLOAD_TIMEOUT=$http_timeout" \
    "${proxy_args[@]}" --tag "$IMAGE" "$SOURCE_DIR"
[[ "$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$IMAGE")" == linux/arm64 ]]
echo "镜像已构建：$IMAGE；下一步执行 bash smoke_test.sh。"
