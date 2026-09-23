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
docker buildx inspect "$BUILDER" --bootstrap
# 主上下文是固定提交源码；packaging 是本目录，资源上下文替代在线依赖镜像。
docker buildx build --builder "$BUILDER" --platform linux/arm64 --provenance=false --load \
    --file "$PACKAGE_DIR/Dockerfile" --target production \
    --build-context "packaging=$PACKAGE_DIR" \
    --build-context "infiniflow/ragflow_deps:latest=$RESOURCE_DIR" \
    --build-arg "NODE_BUILD_MAX_OLD_SPACE_SIZE=${NODE_BUILD_MAX_OLD_SPACE_SIZE:-4096}" \
    --build-arg "UV_CONCURRENT_BUILDS=${UV_CONCURRENT_BUILDS:-1}" \
    "${proxy_args[@]}" --tag "$IMAGE" "$SOURCE_DIR"
[[ "$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$IMAGE")" == linux/arm64 ]]
echo "镜像已构建：$IMAGE；下一步执行 bash smoke_test.sh。"
