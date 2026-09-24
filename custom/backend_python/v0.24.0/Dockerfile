# 基于官方 v0.24.0 Dockerfile（Apache-2.0），来源与改动见 README.md。
# RAGFlow v0.24.0 专用 ARM64 镜像；使用本目录 build.sh 传入固定源码和资源上下文。
# 基础阶段：Ubuntu 24.04 和 Python 运行依赖。
FROM ubuntu:24.04 AS base
USER root
SHELL ["/bin/bash", "-c"]

ARG NEED_MIRROR=0
# ARM64 使用 ubuntu-ports；此参数只替换 Ubuntu APT 源。
ARG UBUNTU_APT_MIRROR=https://ports.ubuntu.com/ubuntu-ports

WORKDIR /ragflow

# 将 prepare.sh 下载的模型打包，运行时无需再下载这些基础模型。
RUN mkdir -p /ragflow/rag/res/deepdoc /root/.ragflow
RUN --mount=type=bind,from=infiniflow/ragflow_deps:latest,source=/huggingface.co,target=/huggingface.co \
    tar --exclude='.*' -cf - \
        /huggingface.co/InfiniFlow/text_concat_xgb_v1.0 \
        /huggingface.co/InfiniFlow/deepdoc \
        | tar -xf - --strip-components=3 -C /ragflow/rag/res/deepdoc

# 固定 Tika jar 路径，沿用 v0.24.0 的 3.2.3 版本。
RUN --mount=type=bind,from=infiniflow/ragflow_deps:latest,source=/,target=/deps \
    cp -r /deps/nltk_data /root/ && \
    cp /deps/tika-server-standard-3.2.3.jar /deps/tika-server-standard-3.2.3.jar.md5 /ragflow/ && \
    cp /deps/cl100k_base.tiktoken /ragflow/9b5ad71b2ce5302211f9c61530b329a4922fc6a4

ENV TIKA_SERVER_JAR="file:///ragflow/tika-server-standard-3.2.3.jar"
ENV DEBIAN_FRONTEND=noninteractive

# 系统依赖：下载失败最多重试 5 次，缓存已下载的 deb，安装失败立即停止。
RUN --mount=type=cache,id=ragflow_apt,target=/var/cache/apt,sharing=locked \
    set -eu; \
    rm -f /etc/apt/apt.conf.d/docker-clean; \
    printf '%s\n' 'Acquire::Retries "5";' \
        'Acquire::http::Timeout "60";' 'Acquire::https::Timeout "60";' \
        'APT::Update::Error-Mode "any";' \
        'APT::Keep-Downloaded-Packages "true";' \
        'Binary::apt::APT::Keep-Downloaded-Packages "true";' \
        > /etc/apt/apt.conf.d/80ragflow-downloads; \
    chmod 1777 /tmp; \
    # Ubuntu 基础镜像需要先从原 HTTP 源安装证书，再启用 HTTPS 镜像源。 \
    apt-get update; \
    apt-get --no-install-recommends install -y ca-certificates; \
    # 仅修改 URI，保留 noble、更新/安全仓库、组件及 Ubuntu 签名校验配置。 \
    mirror="${UBUNTU_APT_MIRROR%/}"; \
    sed -i -E "s|https?://ports\.ubuntu\.com/ubuntu-ports/?|${mirror}|g" \
        /etc/apt/sources.list.d/ubuntu.sources; \
    apt-get update; \
    apt-get install -y \
        libglib2.0-0 libglx-mesa0 libgl1 pkg-config libicu-dev libgdiplus \
        default-jdk libatk-bridge2.0-0 libpython3-dev libgtk-4-1 libnss3 \
        libasound2t64 xdg-utils libgbm-dev zlib1g-dev libjemalloc-dev \
        gnupg unzip curl wget git vim less ghostscript pandoc texlive \
        fonts-freefont-ttf fonts-noto-cjk postgresql-client

ARG NGINX_VERSION=1.29.5-1~noble
RUN --mount=type=cache,id=ragflow_apt,target=/var/cache/apt,sharing=locked \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://nginx.org/keys/nginx_signing.key | gpg --dearmor -o /etc/apt/keyrings/nginx-archive-keyring.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nginx-archive-keyring.gpg] https://nginx.org/packages/mainline/ubuntu/ noble nginx" > /etc/apt/sources.list.d/nginx.list && \
    apt update && \
    apt install -y nginx=${NGINX_VERSION} && \
    apt-mark hold nginx

# 安装已校验的 ARM64 uv，再安装固定 Python 3.12.12。
RUN --mount=type=bind,from=infiniflow/ragflow_deps:latest,source=/,target=/deps \
    if [ "$NEED_MIRROR" == "1" ]; then \
        mkdir -p /etc/uv && \
        echo 'python-install-mirror = "https://registry.npmmirror.com/-/binary/python-build-standalone/"' > /etc/uv/uv.toml && \
        echo '[[index]]' >> /etc/uv/uv.toml && \
        echo 'url = "https://pypi.tuna.tsinghua.edu.cn/simple"' >> /etc/uv/uv.toml && \
        echo 'default = true' >> /etc/uv/uv.toml; \
    fi; \
    uv_arch="aarch64"; \
    tar xzf "/deps/uv-${uv_arch}-unknown-linux-gnu.tar.gz" \
    && cp "uv-${uv_arch}-unknown-linux-gnu/"* /usr/local/bin/ \
    && rm -rf "uv-${uv_arch}-unknown-linux-gnu" \
    && uv python install 3.12.12

ENV PYTHONDONTWRITEBYTECODE=1 DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1 UV_HTTP_TIMEOUT=200 UV_HTTP_RETRIES=3
ENV PATH=/root/.local/bin:$PATH

# 前端沿用 v0.24.0 的 Node.js 20 构建环境。
RUN --mount=type=cache,id=ragflow_apt,target=/var/cache/apt,sharing=locked \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt purge -y nodejs npm cargo && \
    apt autoremove -y && \
    apt update && \
    apt install -y nodejs

# 为需要从源码安装的原生 Python 依赖准备 Rust 编译器。
RUN apt update && apt install -y curl build-essential \
    && if [ "$NEED_MIRROR" == "1" ]; then \
         # 可选 Rust 下载镜像设置。 \
         export RUSTUP_DIST_SERVER="https://mirrors.tuna.tsinghua.edu.cn/rustup"; \
         export RUSTUP_UPDATE_ROOT="https://mirrors.tuna.tsinghua.edu.cn/rustup/rustup"; \
         echo "Using TUNA mirrors for Rustup."; \
       fi; \
    # 使用 HTTP/1.1 下载 Rust 安装器。 \
    curl --proto '=https' --tlsv1.2 --http1.1 -sSf https://sh.rustup.rs | bash -s -- -y --profile minimal \
    && echo 'export PATH="/root/.cargo/bin:${PATH}"' >> /root/.bashrc

ENV PATH="/root/.cargo/bin:${PATH}"

RUN cargo --version && rustc --version

# 为 ARM64 安装 ODBC 18，保留原版的数据源连接能力。
RUN --mount=type=cache,id=ragflow_apt,target=/var/cache/apt,sharing=locked \
    curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
    curl https://packages.microsoft.com/config/ubuntu/22.04/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt update && \
    ACCEPT_EULA=Y apt install -y unixodbc-dev msodbcsql18

# v0.24.0 原有 Chrome 121 文件仅适用于 x86_64；这里使用已在 ARM 主机验证的浏览器版本。
ARG CHROME_VERSION=153.0.8010.52
RUN --mount=type=bind,from=infiniflow/ragflow_deps:latest,source=/,target=/deps \
    test "$(uname -m)" = aarch64 && \
    unzip -q "/deps/chrome-${CHROME_VERSION}-linux-arm64.zip" -d /opt && \
    mv /opt/chrome-linux-arm64 /opt/chrome && \
    ln -s /opt/chrome/chrome /usr/local/bin/chrome && \
    unzip -j "/deps/chromedriver-${CHROME_VERSION}-linux-arm64.zip" chromedriver-linux-arm64/chromedriver -d /usr/local/bin && \
    chmod +x /usr/local/bin/chromedriver
ENV SE_CHROMEDRIVER=/usr/local/bin/chromedriver

RUN --mount=type=bind,from=infiniflow/ragflow_deps:latest,source=/,target=/deps \
    dpkg -i /deps/libssl1.1_1.1.1f-1ubuntu2_arm64.deb

# 编译阶段：安装锁定的 Python 依赖并构建前端。
FROM base AS builder
USER root

WORKDIR /ragflow

# 使用本包校验过的 v0.24.0 锁文件，单次只编译一个依赖以降低峰值内存。
ARG UV_CONCURRENT_BUILDS=1
ENV UV_CONCURRENT_BUILDS=${UV_CONCURRENT_BUILDS}
COPY --from=packaging /build/pyproject.toml /build/uv.lock ./
COPY --from=packaging /runtime/check_mini_racer.py /opt/ragflow-deploy/check_mini_racer.py

# 只调整 Python 安装层，避免让已完成的系统依赖层重新构建。
ARG PYPI_MIRROR=pypi
ARG PYTHON_DOWNLOAD_CONCURRENCY=4
ARG PYTHON_DOWNLOAD_TIMEOUT=600
RUN --mount=type=cache,id=ragflow_uv,target=/root/.cache/uv,sharing=locked \
    set -eu; \
    case "$PYPI_MIRROR" in \
        pypi) ;; \
        aliyun) \
            # frozen 安装使用锁文件中的下载地址，因此索引和文件地址必须一起替换。
            # 保持版本、依赖关系及 SHA-256 不变，由 uv 继续校验下载内容。
            sed -i \
                -e 's|https://pypi.org/simple|https://mirrors.aliyun.com/pypi/simple|g' \
                -e 's|https://files.pythonhosted.org/packages/|https://mirrors.aliyun.com/pypi/packages/|g' \
                pyproject.toml uv.lock ;; \
        *) echo "PYPI_MIRROR must be pypi or aliyun" >&2; exit 1 ;; \
    esac; \
    # uv 的 Git 依赖由 git 子进程拉取；构建阶段使用 HTTP/1.1 避开代理的 HTTP/2 流中断。
    git config --global http.version HTTP/1.1; \
    UV_CONCURRENT_DOWNLOADS="$PYTHON_DOWNLOAD_CONCURRENCY" \
    UV_HTTP_TIMEOUT="$PYTHON_DOWNLOAD_TIMEOUT" \
        uv sync --python 3.12.12 --frozen --no-dev; \
    # 保留原版在运行时安装扩展依赖所需的 pip。
    .venv/bin/python3 -m ensurepip --upgrade; \
    # 安装后立即检查同名模块冲突和原生 JavaScript 引擎，避免到交付自检才失败。
    .venv/bin/python3 /opt/ragflow-deploy/check_mini_racer.py

COPY web web
COPY docs docs
ARG NODE_BUILD_MAX_OLD_SPACE_SIZE=4096
RUN --mount=type=cache,id=ragflow_npm,target=/root/.npm,sharing=locked \
    export NODE_OPTIONS="--max-old-space-size=${NODE_BUILD_MAX_OLD_SPACE_SIZE}" && \
    cd web && npm install && npm run build

# 源码提交由宿主机构建脚本校验，版本文件不依赖当前工作区的 Git 标签。
RUN echo v0.24.0 > /ragflow/VERSION

# 运行阶段：打包官方 v0.24.0 源码、前端产物和本包的部署适配器。
FROM base AS production
USER root

WORKDIR /ragflow

# 复制与基础阶段解释器匹配的虚拟环境。
ENV VIRTUAL_ENV=/ragflow/.venv
COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

ENV PYTHONPATH=/ragflow/

COPY web web
COPY admin admin
COPY api api
COPY conf conf
COPY deepdoc deepdoc
COPY rag rag
COPY agent agent
COPY --from=packaging /build/pyproject.toml /build/uv.lock ./
COPY mcp mcp
COPY common common
COPY memory memory

COPY docker/service_conf.yaml.template ./conf/service_conf.yaml.template
COPY docker/entrypoint.sh ./
# 仅删除入口中固定的 x86_64 库路径，继续使用官方启动流程。
RUN sed -i '/^export LD_LIBRARY_PATH="\/usr\/lib\/x86_64-linux-gnu\/"$/d' /ragflow/entrypoint.sh && \
    chmod +x /ragflow/entrypoint.sh
# 官方 Compose 原本通过挂载提供 Nginx 配置；K8s 镜像将这三份配置直接打包。
COPY docker/nginx/nginx.conf /etc/nginx/nginx.conf
COPY docker/nginx/ragflow.conf /etc/nginx/conf.d/ragflow.conf
COPY docker/nginx/proxy.conf /etc/nginx/proxy.conf
COPY --from=packaging /runtime/ /opt/ragflow-deploy/
LABEL org.opencontainers.image.version="v0.24.0-arm64" \
      org.opencontainers.image.revision="392ec99651da78f6a8e1a2f60fe4818a95a8651d"

# 用已构建的前端产物覆盖源码中的 dist 目录。
COPY --from=builder /ragflow/web/dist /ragflow/web/dist

COPY --from=builder /ragflow/VERSION /ragflow/VERSION
ENTRYPOINT ["./entrypoint.sh"]
