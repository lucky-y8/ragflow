#!/usr/bin/env bash
# 不需要中间件，只检查镜像版本、原生依赖、Nginx 和浏览器。
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
require_arm64
[[ "$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$IMAGE")" == linux/arm64 ]]
docker run --rm --entrypoint bash "$IMAGE" -ec \
    'nginx -t; python3 /opt/ragflow-deploy/smoke_test.py'
