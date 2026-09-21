#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
BUILDER="${RAGFLOW_BUILDER:-ragflow-arm64-proxy}"
IMAGE="${RAGFLOW_IMAGE:-ragflow:python-arm64}"
export DOCKER_CLI_EXPERIMENTAL=enabled

# Registry authentication uses the buildx client's proxy; RUN downloads use args.
proxy="${RAGFLOW_BUILD_PROXY:-${HTTPS_PROXY:-${HTTP_PROXY:-}}}"
proxy_args=()
if [[ -n "$proxy" ]]; then
    export HTTP_PROXY="$proxy" HTTPS_PROXY="$proxy" http_proxy="$proxy" https_proxy="$proxy"
    proxy_args=(--build-arg "http_proxy=$proxy" --build-arg "https_proxy=$proxy")
fi

chrome_version="$(sed -n 's/^ARG CHROME_VERSION=//p' Dockerfile)"
required=(
    "chrome-${chrome_version}-linux-arm64.zip"
    "chromedriver-${chrome_version}-linux-arm64.zip"
    uv-aarch64-unknown-linux-gnu.tar.gz
    stagehand-server-v3-linux-arm64
    libssl1.1_1.1.1f-1ubuntu2_arm64.deb
    tika-server-standard-3.3.0.jar
    tika-server-standard-3.3.0.jar.md5
    cl100k_base.tiktoken
    nltk_data/corpora/wordnet.zip
    nltk_data/tokenizers/punkt_tab
    huggingface.co/InfiniFlow/deepdoc
    huggingface.co/InfiniFlow/text_concat_xgb_v1.0
)
for resource in "${required[@]}"; do
    if [[ ! -e "ragflow_deps/$resource" ]]; then
        echo "Missing resource: ragflow_deps/$resource" >&2
        echo "Run: uv run --python 3.13 --script ragflow_deps/download_deps.py --image-only --architecture arm64" >&2
        exit 1
    fi
done
if [[ ! -d .git ]]; then
    echo "Build from a Git checkout with a .git directory (needed for VERSION)." >&2
    exit 1
fi

docker buildx inspect "$BUILDER" --bootstrap
# The container builder cannot read images loaded only into Docker Engine.
# Override the resource image with a local named context instead.
docker buildx build \
    --builder "$BUILDER" \
    --platform linux/arm64 \
    --provenance=false \
    --build-context "infiniflow/ragflow_deps:latest=$PWD/ragflow_deps" \
    --build-arg "NODE_BUILD_MAX_OLD_SPACE_SIZE=${NODE_BUILD_MAX_OLD_SPACE_SIZE:-4096}" \
    --build-arg "UV_CONCURRENT_BUILDS=${UV_CONCURRENT_BUILDS:-1}" \
    "${proxy_args[@]}" \
    --target production --load -t "$IMAGE" .

architecture="$(docker image inspect --format '{{.Architecture}}' "$IMAGE")"
if [[ "$architecture" != arm64 ]]; then
    echo "Unexpected image architecture: $architecture" >&2
    exit 1
fi
echo "Built $IMAGE ($architecture). Run the checks in docker/README.arm64.md before deployment."
