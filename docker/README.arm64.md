# Python ARM64 镜像构建

本流程生成前端、Python API 和 Python Worker 所在的应用镜像。运行时默认
`API_PROXY_SCHEME=python`，MySQL、Redis、对象存储和 Elasticsearch 使用平台提供的服务。
本流程不启动这些中间件，也不编译 Go 服务。

## 构建环境

在 ARM64 电脑的完整 Git 仓库中执行下列命令。构建用 Ubuntu 24.04 容器和 Python 3.13，
不需要更换宿主机的系统 Python。必须先把本次仓库改动同步到 ARM 电脑。

已验证基础构建的环境是 UOS 20 / ARM64、Docker 19.03、Buildx 0.10.5、
BuildKit 0.12.5，Builder 名称为 `ragflow-arm64-proxy`。
这只是基础构建验证；完整 RAGFlow 镜像仍需实机构建和自检。
[RAGFlow 官方构建要求](https://ragflow.io/docs/v0.27.2/build_docker_image)列出
Docker 24+、16 GB 内存和至少 50 GB 磁盘。当前 8 GB / 旧版 Docker 的机器低于该要求。
先关闭占内存的程序，查看 `free -h`、`swapon --show` 和 `df -h /var/lib/docker`。
脚本将 Node 堆上限设为 4096 MB、Python 包并行构建数设为 1，但不保证 8 GB 能完成构建。

## 1. 下载构建资源

下面的代理沿用已验证可用的地址。代理必须同时能从宿主机及 BuildKit 容器访问。
BuildKit 的代理由创建 Builder 时的 `env.HTTP_PROXY` / `env.HTTPS_PROXY` 提供；
脚本只负责构建客户端和构建步骤的代理，不修改现有 Builder。

```bash
cd ~/Desktop/workcode/ragflow
export RAGFLOW_BUILD_PROXY='http://192.168.229.39:7890'
export HTTP_PROXY="$RAGFLOW_BUILD_PROXY" HTTPS_PROXY="$RAGFLOW_BUILD_PROXY"
export http_proxy="$RAGFLOW_BUILD_PROXY" https_proxy="$RAGFLOW_BUILD_PROXY"
mkdir -p build/arm64-tools
curl -fL --retry 3 https://github.com/astral-sh/uv/releases/download/0.9.16/uv-aarch64-unknown-linux-gnu.tar.gz -o build/arm64-tools/uv.tar.gz
tar -xzf build/arm64-tools/uv.tar.gz -C build/arm64-tools
export PATH="$PWD/build/arm64-tools/uv-aarch64-unknown-linux-gnu:$PATH"
uv run --python 3.13 --script ragflow_deps/download_deps.py --image-only --architecture arm64
```

`--script` 只安装下载脚本需要的包；不会在宿主机安装整套 RAGFlow。
`--image-only` 跳过 Go 原生库下载、解压和 Go 模型检查。
`--architecture arm64` 只下载 ARM64 的二进制资源，另含共享的模型、NLTK 和 Tika 资源。
下载失败可以重跑；未完成的普通文件保存在 `.part` 中，不会被当作完整缓存。
NLTK 语料通过代理直接下载官方固定提交中的 ZIP，并按官方索引校验 SHA-256；
不调用 `nltk.download()`，因此不会触发其代理下载前的本地 DNS 检查。
若旧脚本报 `SSRF attempt to restricted IP 0.0.0.0`，同步更新后的
`ragflow_deps/download_deps.py` 后重跑相同命令，已下载资源会复用。

Chrome 和 ChromeDriver 固定为同版本 `153.0.8010.52`，该版本包含[官方 ARM64 下载](https://googlechromelabs.github.io/chrome-for-testing/)。
更新版本时需同步 `Dockerfile`、`Dockerfile_base`、`ragflow_deps/Dockerfile`
和 `ragflow_deps/download_deps.py`。

## 2. 构建应用镜像

```bash
sudo env RAGFLOW_BUILD_PROXY="$RAGFLOW_BUILD_PROXY" bash docker/build_python_arm64.sh
```

默认输出 `ragflow:python-arm64`。可以用 `RAGFLOW_IMAGE`、`RAGFLOW_BUILDER`
覆盖镜像名和 Builder 名。失败后使用同一条命令重试会复用构建缓存。

脚本用 `--build-context infiniflow/ragflow_deps:latest=...` 将本地资源直接交给 BuildKit。
因此不需要单独构建或推送依赖镜像，也不会误拉 Docker Hub 上的旧资源镜像。
仅设置 `--load` 把依赖镜像导入 Docker Engine，不能让 `docker-container` Builder 自动读取它。
代理通过构建参数传入，不写入应用镜像的运行环境。

## 3. 检查镜像

以下检查跳过应用入口，不需要中间件连接信息。

```bash
sudo docker image inspect ragflow:python-arm64 --format '{{.Os}}/{{.Architecture}}'
sudo docker run --rm --entrypoint bash ragflow:python-arm64 -ec 'uname -m; python3 --version; chrome --version; chromedriver --version'
sudo docker run --rm -i --entrypoint python3 ragflow:python-arm64 - <<'PY'
import platform
import cv2
import onnxruntime
import quart
import peewee
from py_mini_racer import MiniRacer
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

assert platform.machine() == "aarch64", platform.machine()
with MiniRacer() as runtime:
    assert runtime.eval("1 + 1") == 2
options = Options()
options.binary_location = "/opt/chrome/chrome"
for flag in ("--headless", "--no-sandbox", "--disable-dev-shm-usage"):
    options.add_argument(flag)
with webdriver.Chrome(options=options) as browser:
    browser.get("data:text/html,<title>arm64-ok</title>")
    assert browser.title == "arm64-ok", browser.title
print("ARM64 Python imports, JavaScript engine and browser checks passed")
PY
```

应显示 `linux/arm64`、`aarch64`、Python 3.13，并通过导入和浏览器检查。
这些检查通过后，仍须配置外部服务连接，验证 API 启动及实际文档解析。
Kubernetes YAML 和外部服务环境变量需在后续部署时按平台连接信息填写。

## 4. 导出镜像

```bash
set -o pipefail
sudo docker save ragflow:python-arm64 | gzip > ragflow-python-arm64.tar.gz
```

将压缩文件导入平台镜像仓库，或按平台提供的仓库地址执行 `docker tag` / `docker push`。
