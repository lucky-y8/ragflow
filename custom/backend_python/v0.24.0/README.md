# RAGFlow v0.24.0：ARM64 构建与 K8s 交付包

本仓库的 `v0.24.0-arm64` 分支基于官方 `v0.24.0` 标签（提交 `392ec99651da78f6a8e1a2f60fe4818a95a8651d`）创建，支持在此基础上修改应用并构建 ARM64 镜像。

**构建使用本脚本所在仓库的当前工作目录。请同步完整仓库到 ARM 电脑，不能只复制此文件夹。** 已保存但未提交的修改、新增业务文件和删除操作都会参与构建；无需先 `git commit`。Python 依赖统一使用仓库根目录的 `pyproject.toml` 和 `uv.lock`，不再维护本目录的重复清单。

`prepare.sh` 只准备工具和依赖资源，不再下载应用源码，也不重置现有文件。脚本检查根目录 `project.version` 为 **0.24.0**，默认输出 **`ragflow:v0.24.0-arm64`**，包含 Python 后端、前端 Nginx、一个任务执行器和数据同步进程。MySQL、Redis、对象存储、Elasticsearch 全部接平台现有服务。

完整 ARM64 运行验证须以当前镜像执行下文自检的结果为准；脚本检查和单元测试不能代替镜像构建、自检或实际 K8s 联调。

## 文件说明

```text
v0.24.0/
├── README.md                       本说明
├── LICENSE                         上游 Apache-2.0 许可证
├── versions.env                    应用版本基线和主要工具版本
├── prepare.sh                      下载 uv、模型和浏览器等资源
├── build.sh                        使用已有 Buildx Builder 构建并导入 Docker
├── smoke_test.sh                   检查镜像版本、原生依赖、NLTK、Nginx 和浏览器
├── common.sh                       公共路径、代理与源码校验
├── Dockerfile                      ARM64 多阶段镜像构建文件
├── Dockerfile.dockerignore          当前仓库构建上下文的忽略规则
├── .dockerignore                   本构建包上下文的忽略规则
├── .gitignore                      排除下载缓存、镜像压缩包和真实密码文件
├── download_resources.py           仅下载 Python 镜像需要的资源
├── runtime/
│   ├── render_config.py            环境变量 → local.service_conf.yaml
│   ├── check_mini_racer.py          构建和自检共用的 JavaScript 引擎检查
│   └── smoke_test.py               镜像内执行的自检
├── k8s/
│   ├── ragflow.yaml                两个 ConfigMap、Deployment、Service
│   └── credentials.yaml.example    密码和密钥 Secret 示例
└── tests/                          无外部服务依赖的测试
```

`.build/` 保存工具和资源，不进入 Git。旧版留下的 `.build/source` 不再参与构建，保留或删除都不影响新的源码选择；无需重新下载已准备好的资源。脚本根据自身位置找到仓库根目录，不受执行命令时所在目录影响。

## 1. 在 ARM 电脑准备资源

把包含手动修改的完整 `v0.24.0-arm64` 仓库同步到 ARM 电脑，保持 `custom/backend_python/v0.24.0/` 的目录结构。已准备好资源时可直接跳到第 2 步。

```bash
cd ~/Desktop/workcode/ragflow/custom/backend_python/v0.24.0
uname -m
# 应为 aarch64。需要 curl、tar、sha256sum、bash、realpath、awk 和可用网络。
env RAGFLOW_BUILD_PROXY='http://192.168.36.203:7890' bash prepare.sh
```

不需要在宿主机安装整套 RAGFlow。脚本下载独立的 uv 0.9.16（校验官方 SHA-256），用它管理 Python 3.12.12 和下载脚本依赖。这里不调用旧版 `nltk.download()`，不会触发之前遇到的 NLTK 代理 DNS 安全检查。

资源包括 Tika **3.2.3**、Chrome/ChromeDriver **153.0.8010.52 ARM64**、NLTK 和固定提交的 DeepDoc 模型。Chrome 版本沿用已在你的 ARM 电脑上验证过的版本，配合 v0.24.0 的 Python 3.12 环境仍须再跑自检。普通资源先写 `.part`，完成后再替换；失败可重跑，已下载文件会复用。

默认下载位置为本目录 `.build/`。可通过 `RAGFLOW_BUILD_DIR` 指定另一个工作目录，或通过 `RAGFLOW_RESOURCE_DIR` 指向已有资源目录以复用同名文件；后续运行 `prepare.sh` 与 `build.sh` 时必须传入相同路径。指定已有资源目录后，脚本会下载缺失资源，并同步本包固定的模型版本。仍缺少的 v0.24.0 Tika 3.2.3 会另外下载，不使用 3.3.0 代替。

## 2. 构建镜像

当前代理为 `http://192.168.36.203:7890`。首次切换到此代理时，创建独立的 `ragflow-arm64-proxy-36` Builder，让 BuildKit 拉取基础镜像时也使用新代理（只需创建一次）：

```bash
sudo env DOCKER_CLI_EXPERIMENTAL=enabled docker buildx create \
  --name ragflow-arm64-proxy-36 \
  --driver docker-container \
  --driver-opt image=moby/buildkit:v0.12.5 \
  --driver-opt env.HTTP_PROXY=http://192.168.36.203:7890 \
  --driver-opt env.HTTPS_PROXY=http://192.168.36.203:7890 \
  --driver-opt env.http_proxy=http://192.168.36.203:7890 \
  --driver-opt env.https_proxy=http://192.168.36.203:7890
sudo env DOCKER_CLI_EXPERIMENTAL=enabled docker buildx inspect \
  ragflow-arm64-proxy-36 --bootstrap
```

同名 Builder 已存在时，跳过 `create`，执行 `inspect` 确认 `Driver Options` 中的代理地址为上述新地址、状态为 `running`。新 Builder 的构建缓存独立，首次构建可能需要重新下载和构建；原 Builder 及其缓存保留。

随后显式指定此 Builder 构建（脚本默认值仍为原 Builder）：

```bash
sudo env \
  RAGFLOW_BUILD_PROXY='http://192.168.36.203:7890' \
  RAGFLOW_BUILDER='ragflow-arm64-proxy-36' \
  bash build.sh
```

构建成功后输出 `ragflow:v0.24.0-arm64`，并检查镜像架构为 `linux/arm64`。脚本通过本地资源上下文提供模型和二进制文件，不需要下载 `infiniflow/ragflow_deps:latest` 镜像。使用 `--provenance=false --load`，沿用此前 Buildx 0.10.5 / BuildKit 0.12.5 的构建方式。

### 源码全量覆盖规则

构建日志会输出实际的“应用源码”路径。它应是你的 `ragflow` 仓库根目录，而不是 `.build/source`。构建阶段和最终镜像都复制当前工作目录，既有的 `api/`、`rag/`、`agent/`、`common/`、`conf/`、`web/` 等文件，以及新增业务目录和根目录文件均包含在内。已经删除的源码不会从官方仓库补回来；Git 是否跟踪文件不决定是否打包。

| 修改内容 | 构建行为 |
| --- | --- |
| 后端、配置模板、新增业务模块 | 使用当前磁盘上的文件；需先在编辑器中保存，并同步到 ARM 构建电脑 |
| 前端源码、`web/package.json` 和锁文件 | 在容器内重新安装前端依赖并执行 `npm run build`；本地旧 `web/dist` 不使用 |
| 根目录 `pyproject.toml`、`uv.lock` | 使用当前依赖清单；修改依赖后先更新锁文件，清单与锁不一致会使构建失败 |
| `docker/entrypoint.sh`、`docker/nginx/` | 使用当前版本，并保留入口的 ARM64 库路径适配 |
| 本目录 `runtime/` | 打包到 `/opt/ragflow-deploy/`；构建脚本在宿主机执行，K8s YAML 单独部署 |

全量覆盖仍有明确的排除项：虚拟环境、`node_modules`、`.build`、下载资源、日志/会话、旧前端产物、镜像归档，以及 `credentials.local.*`、`local.service_conf.yaml`、部署目录中的 K8s 配置等。完整规则见 `Dockerfile.dockerignore`；`.gitignore` 不能代替它。前端公开的 `.env`、`.env.development`、`.env.production` 和 `web/.npmrc` 保留，后者提供 npm 镜像源和 Node 引擎检查；`.env.*.local` 等本地环境文件排除。不要在这些公开构建配置中填写令牌或密码。真实连接密码继续通过 K8s Secret 提供；自定义命名的私密文件需要补充排除规则。

如果修改了 Python 依赖，在本目录使用准备脚本下载的 uv 更新仓库根锁文件，再构建（如自定义了构建缓存路径，相应调整 uv 路径）：

```bash
.build/tools/uv-aarch64-unknown-linux-gnu/uv lock --project ../../.. --python 3.12.12
```

原 ARM64 的 `akracer` / `py-mini-racer` 排除项已合并到根目录，避免同名模块冲突。构建使用 `uv sync --locked`，不会静默忽略新依赖或自动升级锁定版本；区别见 [uv 锁文件说明](https://docs.astral.sh/uv/concepts/projects/sync/)。源码修改会重新执行 Python 安装层，但已有 uv 下载缓存和未变动的基础系统层可以复用。无需每次清空缓存或添加 `--no-cache`。

镜像的 `org.opencontainers.image.revision` 记录当前 Git 提交，`io.ragflow.source.state` 记录 `clean` / `modified`；完整源码副本没有 Git 信息时为 `unknown`。提交号不能单独代表未提交改动，交付时仍建议为每次构建使用不同镜像标签。

脚本明确使用 **`custom/backend_python/v0.24.0/Dockerfile`**。修改仓库根目录的 `Dockerfile` 不会改变这条构建命令的步骤；ARM64 构建步骤应修改本目录 Dockerfile，软件源使用下文的 `RAGFLOW_APT_MIRROR` / `RAGFLOW_PYPI_MIRROR` 参数。同步业务代码时，也要保留根目录依赖文件中的 ARM64 排除项；不要用未适配的原版清单覆盖它们。

代理同时用于下载、Buildx 客户端鉴权和构建步骤。Builder 容器自身使用创建时的代理配置；仅修改 `RAGFLOW_BUILD_PROXY` 不会更新旧 Builder，脚本也不会创建或修改 Builder。Builder 名称不同时，用 `RAGFLOW_BUILDER` 指定实际名称，并确认它的代理配置一致。

APT 下载配置了 5 次重试、60 秒连接/传输超时和 deb 缓存；更新索引或安装失败会立即退出，不使用 `--fix-missing` 跳过依赖。默认安装证书后使用官方 HTTPS `ubuntu-ports` 源。基础镜像缺少证书，最初的索引更新和证书安装仍使用原 HTTP 源，并同样启用重试。

若 Ubuntu 包下载出现代理 `502 Bad Gateway`，可以单独指定 ARM64 软件源重试（不改变 Python、Node.js 等下载源）：

```bash
sudo env \
  RAGFLOW_BUILD_PROXY='http://192.168.36.203:7890' \
  RAGFLOW_BUILDER='ragflow-arm64-proxy-36' \
  RAGFLOW_APT_MIRROR='https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports' \
  bash build.sh
```

这里必须是 `ubuntu-ports`。参数会替换 Ubuntu 普通、更新和安全仓库的下载地址，保留 Ubuntu 的发行版及签名校验；镜像站同步可能有延迟。参考[清华 Ubuntu Ports 说明](https://mirrors.tuna.tsinghua.edu.cn/help/ubuntu-ports/)。该设置不能修复代理自身的持续故障。之前准备完成的 `.build/` 资源可以复用，无需重新执行 `prepare.sh` 或清理 Builder 缓存。

`graspologic` 是固定提交的 Git 依赖。若日志出现 `curl 92 HTTP/2 stream ... CANCEL`、`early EOF` 或 `invalid index-pack output`，说明 Git 下载连接中断，不能据此判断为 ARM64 编译不支持。Dockerfile 已在 Python 依赖安装层设置 `git config --global http.version HTTP/1.1`；该设置只写入构建阶段容器，不修改宿主机配置，依赖提交及 TLS 校验保持原样。参考 [Git http.version 文档](https://git-scm.com/docs/git-config#Documentation/git-config.txt-httpversion)。更新后使用相同 Builder、APT 镜像源和构建命令重试，已成功的基础层及 uv 下载缓存可继续复用。持续网络故障仍需检查代理链路。

如果普通 Python 包出现 `Failed to download distribution due to network timeout`，可使用阿里 PyPI 镜像：

```bash
sudo env \
  RAGFLOW_BUILD_PROXY='http://192.168.36.203:7890' \
  RAGFLOW_BUILDER='ragflow-arm64-proxy-36' \
  RAGFLOW_APT_MIRROR='https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports' \
  RAGFLOW_PYPI_MIRROR=aliyun \
  UV_CONCURRENT_DOWNLOADS=4 \
  UV_HTTP_TIMEOUT=600 \
  bash build.sh
```

`RAGFLOW_PYPI_MIRROR` 支持 `pypi`（默认）和 `aliyun`。此参数独立于 `RAGFLOW_APT_MIRROR`；APT 保持上次的值以复用基础层。镜像构建时会同时替换 `pyproject.toml` 和 `uv.lock` 中的清华/PyPI 索引、包文件下载地址，保留锁定版本、SHA-256 校验以及 Git 依赖的 URL/固定提交。仅设置宿主机 pip 镜像或修改索引地址，不能覆盖锁文件内的包文件地址。宿主机文件不受镜像源替换影响。

Python 安装阶段默认最多同时下载 4 个包，HTTP 读取超时 600 秒；这两个参数须为正整数。基础阶段的工具下载设置不变，避免使已完成的系统安装缓存失效。新镜像地址可能需要重新下载部分普通 Python 包；现有 Git 缓存保留。GitHub 源码依赖仍通过原代理获取，阿里 PyPI 不替代 GitHub。若代理继续拥堵，可将 `UV_CONCURRENT_DOWNLOADS` 降到 `2`。参考[阿里 PyPI 镜像说明](https://developer.aliyun.com/mirror/pypi)和 [uv 下载参数](https://docs.astral.sh/uv/reference/environment/#uv_concurrent_downloads)。

默认 Node 构建堆上限 4096 MB、Python 包并行构建数 1，可通过 `NODE_BUILD_MAX_OLD_SPACE_SIZE` 和 `UV_CONCURRENT_BUILDS` 调整。你的 8 GB 机器仍可能在复杂原生编译时内存不足，应关闭其他占内存程序，检查实际可用内存、Swap，以及源码/资源目录和 `/var/lib/docker` 的可用空间。构建所需资源仍以实际执行结果为准。

本版本运行本目录的 `build.sh`，由它传入当前仓库源码和依赖资源。若需自定义镜像名，构建和自检都传入相同 `RAGFLOW_IMAGE`。

## 3. 镜像自检

```bash
sudo bash smoke_test.sh
```

自检不连接中间件，检查：镜像架构、`VERSION=v0.24.0`、Python 3.12、OpenCV/NumPy/XGBoost/ONNX Runtime 等依赖、MiniRacer JavaScript 引擎、NLTK 分词和词典、Nginx 配置、Chrome 与 ChromeDriver 配合运行。

若遇到 `MiniRacer object does not support the context manager protocol`，须检查同名模块冲突。锁定的 `mini-racer 0.12.4` 支持 `with`；但 AkShare 的 Linux 依赖 `akracer 0.0.14` 也提供 `py_mini_racer/__init__.py`，会使实际导入的实现受安装顺序影响。本包排除 `akracer` 和 `py-mini-racer`，统一由 `mini-racer` 提供引擎，保留 AkShare 及其余依赖版本。构建时和镜像自检都会检查冲突包，并执行 `eval`、`call`、`execute`。参考 [MiniRacer 版本说明](https://pypi.org/project/mini-racer/0.12.4/)和 [AKRacer 源码](https://github.com/akfamily/akracer/blob/main/py_mini_racer/__init__.py)。

更新后需要使用与上次相同的 Builder、APT/PyPI 镜像和参数重新运行 `build.sh`，再运行 `sudo bash smoke_test.sh`。无需重跑 `prepare.sh` 或清缓存；系统层可继续复用，Python 安装层及后续阶段会重新构建。只更新本地脚本不会改变已生成镜像中的依赖和自检文件，不要通过删掉 `with` 来跳过冲突。

ONNX Runtime 的 GPU 探测警告需要结合退出结果判断；本模板按 CPU 部署，没有申请 GPU。自检通过后还需在平台验证数据库连接、文件上传、实际文档解析和模型问答。

## 4. 向平台交付镜像

`build.sh` 使用 `--load`，构建成功后镜像已存在于构建电脑的 Docker 中。如果构建电脑可以直接连接平台仓库，可直接执行第 4.3 步；通过文件传到内网时，按第 4.1 → 4.2 → 4.3 步执行。

### 4.1 在构建电脑导出镜像

在 ARM 构建电脑的本目录执行，压缩包名称自动加入导出当天的日期（`YYYYMMDD`），导出成功后生成同名校验文件：

```bash
set -o pipefail
archive="ragflow-v0.24.0-arm64-$(date +%Y%m%d).tar.gz"
sudo docker save ragflow:v0.24.0-arm64 | gzip > "$archive" && \
sha256sum "$archive" > "$archive.sha256"
```

例如 2026 年 10 月 14 日导出得到 `ragflow-v0.24.0-arm64-20261014.tar.gz` 和 `ragflow-v0.24.0-arm64-20261014.tar.gz.sha256`。日期只用于归档文件名，包内镜像标签仍为 `ragflow:v0.24.0-arm64`。同一天多次导出会覆盖同名文件；需要保留多份时，将日期格式改为 `date +%Y%m%d-%H%M%S`。

### 4.2 在内网机器校验并导入镜像

将 `.tar.gz` 和 `.tar.gz.sha256` 两个文件一起传到内网机器，并在文件所在目录执行。导入前确认 Docker 数据目录所在分区有足够的容量和 inode；镜像层解压及临时文件需要额外空间，不能只按压缩包大小估算。

```bash
# 改为收到的实际文件名，日期取导出日期，不是导入当天的日期。
archive='ragflow-v0.24.0-arm64-20261014.tar.gz'
sha256sum -c "$archive.sha256" && \
sudo docker load -i "$archive" && \
sudo docker image inspect ragflow:v0.24.0-arm64 --format '{{.Os}}/{{.Architecture}}'
```

校验应显示 `OK`，导入完成应显示 `Loaded image: ragflow:v0.24.0-arm64`，架构应为 `linux/arm64`。`.tar.gz` 可以直接交给 `docker load -i`，无需先手动解压。校验失败或导入报错时先排查，不继续打标签和推送，以免误用机器上已有的旧镜像。

### 4.3 登录平台仓库、打标签并推送

在镜像已成功构建或导入、并且能够连接平台仓库的机器上执行。下面使用当前平台地址和测试标签：

```bash
sudo docker login 10.224.32.103:32443 && \
sudo docker tag ragflow:v0.24.0-arm64 10.224.32.103:32443/maas/ragflow:v0.24.0-arm64-test && \
sudo docker push 10.224.32.103:32443/maas/ragflow:v0.24.0-arm64-test
```

每次重新发布建议采用新 tag 或固定 digest，并同步 `k8s/ragflow.yaml` 中初始化容器和应用容器的两处 `image`。`docker load` 只把镜像导入当前连接的 Docker，不会自动上传仓库或分发给 Kubernetes 节点；本部署流程还需要完成 `docker push`。

交给平台：镜像压缩包、SHA-256 文件、`k8s/ragflow.yaml`、`k8s/credentials.yaml.example` 和本文。若由平台人员负责导入及上传仓库，同样执行第 4.2 和第 4.3 步。

## 5. 填写 K8s 和环境变量

本包没有 Kustomize 依赖，普通变量直接修改 `k8s/ragflow.yaml` 开头的两个 ConfigMap，密码由 Secret 提供。应用资源和凭据 Secret 的命名空间统一为 `maas-view`，请确认平台已创建该命名空间；本模板不创建 namespace。

| 参数 | 填写方式 |
| --- | --- |
| 两处 `image` | 当前为 `10.224.32.103:32443/maas/ragflow:v0.24.0-arm64-test`；平台仓库中需已存在该镜像，初始化容器与应用容器保持一致 |
| `imagePullSecrets` | 私有仓库需要时取消注释，引用同 namespace 的仓库凭据；与中间件密码 Secret 不同 |
| `DB_TYPE` / `DOC_ENGINE` | 本模板固定 `mysql` / `elasticsearch` |
| `MYSQL_HOST/PORT/DBNAME/USER` | 主机名或 IPv4、实际端口、预先创建的专用库、应用账号；密码放 `MYSQL_PASSWORD` |
| `MYSQL_MAX_CONNECTIONS` | 每个进程的连接池上限，默认 32；总连接数可能更高 |
| `REDIS_HOST/PORT/DB/USERNAME` | 单地址、端口、专用逻辑 DB、可选 ACL 用户名；密码放 `REDIS_PASSWORD` |
| `ES_HOSTS` | 完整 http(s) 地址，多个节点逗号分隔；仓库基线为 ES 8.11.3，其他版本需确认向量检索兼容性 |
| `ES_USER` / `ES_PASSWORD` | 有认证时同时填写，无认证时两者都留空 |
| `ES_VERIFY_CERTS` | 默认 `true`；内部 CA 或双向 TLS 需另行配置 |
| `STORAGE_IMPL` | HTTP MinIO 填 `MINIO`；HTTPS 或其他 S3 服务填 `AWS_S3` |
| `OBJECT_STORAGE_ENDPOINT` | 完整服务地址，含协议和实际端口，不含桶路径 |
| `OBJECT_STORAGE_BUCKET` | 平台预先创建的桶，账号需有桶检查及对象读写、列举、删除权限 |
| `OBJECT_STORAGE_PREFIX` | 非空前缀，默认 `ragflow-v0240`，避免与其他版本数据混用 |
| `OBJECT_STORAGE_REGION` | 按平台填写区域；S3 分支映射到旧版使用的 `region_name` 字段 |
| `OBJECT_STORAGE_ACCESS_KEY/SECRET_KEY` | 存放在 Secret 中的对象存储访问凭据 |
| `S3_ADDRESSING_STYLE` | 默认 `path`，平台要求时可改 `virtual` 或 `auto` |
| `REGISTER_ENABLED` | `1` 开启注册，`0` 关闭；先确认账号创建方式再关闭 |

v0.24.0 的 MinIO 客户端固定 `secure=False`，因此适配器会拒绝 `MINIO + https://`，避免连接看似配置成功却被按 HTTP 使用。需要 HTTPS MinIO 时，使用 `AWS_S3` 和其 S3 接口；应先在独立桶/前缀验收，不应直接切换已有生产数据的存储模式。Redis TLS、Cluster、Sentinel 与 MySQL TLS 尚未在本模板接入；平台若要求这些连接方式，需要另行适配。

请为此版本准备独立数据库、Redis 逻辑 DB、索引/存储数据空间。不要让旧版直接连接新版本已有的生产数据库并把它当作降级方案；本包不提供数据库降级迁移。MySQL 账号需要建表、变更表和应用读写权限，相关权限由平台按实际范围授予。Redis 用于任务队列、锁和登录等状态，持久化、备份和淘汰策略也需平台确认。

通过平台凭据界面创建名为 `ragflow-v0240-credentials` 的 Secret，或者执行：

```bash
cp k8s/credentials.yaml.example k8s/credentials.local.yaml
# 编辑 credentials.local.yaml，填写真实密码/密钥；此文件已被 .gitignore 排除。
kubectl -n maas-view apply -f k8s/credentials.local.yaml
```

## 6. 部署与验收

以下由持有平台 kubeconfig 的人员执行，所有占位符需已替换。没有集群权限时，交付文件即可。

```bash
kubectl apply --dry-run=server -f k8s/ragflow.yaml
kubectl apply -f k8s/ragflow.yaml
kubectl -n maas-view rollout status deployment/ragflow-v0240 --timeout=20m
kubectl -n maas-view get pods -l app.kubernetes.io/name=ragflow-v0240 -o wide
kubectl -n maas-view logs deployment/ragflow-v0240 -c render-config
kubectl -n maas-view logs deployment/ragflow-v0240 -c ragflow --tail=200
```

ConfigMap 和 Secret 更新后，必须重建 Pod，才能重新读取变量并执行配置生成：

```bash
kubectl -n maas-view rollout restart deployment/ragflow-v0240
```

应用默认一个副本、一个任务执行器，解析并发为 1。资源起始值 request 2 CPU / 4 GiB、limit 4 CPU / 8 GiB，属于联调配置，实际容量需验证。镜像固定调度到 Linux ARM64 节点；Pod Pending 时检查架构、资源配额、节点污点。

主容器显式设置工作目录 `/ragflow`、启动命令 `["/ragflow/entrypoint.sh"]` 和参数 `["--workers=1"]`，与镜像原有启动方式一致。容器端口名称为 `http`、端口为 `80`、协议为 `TCP`，Service 也显式使用 `TCP`。初始化容器仍通过 Python 执行配置生成脚本。

Service 是集群内 80 端口，前端页面和 API 走同一入口。外部域名、Ingress、网关 TLS 由平台配置，需支持文件上传和较长的流式响应。临时测试可用：

```bash
kubectl -n maas-view port-forward service/ragflow-v0240 9380:80
# 浏览器访问 http://127.0.0.1:9380
```

**v0.24.0 的探针路径是 `/v1/system/ping` 和 `/v1/system/healthz`。** 启动探针约预留 15 分钟，存活探针只检查 API，避免把外部依赖故障直接当作进程故障重启。旧版 healthz 调用了对象存储检查，但没有判断 MinIO 返回的 `False`，并且 AWS_S3 的健康检查会写入 `_t@@@1` 测试对象；所以 Ready 不能代替文件读写和文档解析验收。其接口也不保证任务执行器健康。

部署后按顺序验证：页面打开 → 创建账号 → 配置聊天和嵌入模型 → 上传小文档 → 解析完成 → 检索及问答正常。模型服务需要平台允许访问，模型 API 凭据在应用中配置。

镜像使用原有 root 入口和可写根文件系统，不申请 privileged 权限；平台若强制非 root 或只读根文件系统，需要另行改造。临时配置、日志和浏览器共享内存随 Pod 删除，长期日志由平台采集，业务数据保存在外部服务。本模板不申请 PVC。单副本 Recreate 更新会短暂停服，终止宽限不能保证旧版入口排空任务，更新前应安排维护窗口。

## 7. 构建适配与集成点

- 基于[官方 v0.24.0 Dockerfile](https://github.com/infiniflow/ragflow/blob/v0.24.0/Dockerfile)，保持 Python 3.12、Node.js 20、Tika 3.2.3，增加 ARM64 Chrome/ChromeDriver 和系统库。
- 根目录 `pyproject.toml`、`uv.lock` 保留 ARM64 适配，排除与 `mini-racer` 共享模块名的 `akracer`、`py-mini-racer`，其余锁定包版本保留。镜像使用 `--locked` 安装当前依赖。
- 镜像内删除当前 `docker/entrypoint.sh` 写死的 x86_64 `LD_LIBRARY_PATH`，保留其 Python API、工作进程和数据同步启动流程。
- 官方 Compose 挂载的 `docker/nginx/` 三份配置改为直接打包进镜像，使 K8s Service 80 端口能够访问页面和 API。
- `runtime/render_config.py` 打包到 `/opt/ragflow-deploy/`。初始化容器读取 ConfigMap/Secret，写入权限为 0600 的 JSON 文件；JSON 可由原版 YAML 解析器读取，密码中的引号、换行和 `$` 等字符会原样保留。
- 主容器仅挂载 `/ragflow/conf/local.service_conf.yaml`，使用 `common/config_utils.py:read_config()` 的顶层配置覆盖机制，不覆盖整个 conf 目录。连接 Secret 不再注入主容器的原始 Shell 模板渲染过程。
- 存储配置按 v0.24.0 的 `rag/utils/minio_conn.py`、`s3_conn.py` 和 `common/settings.py` 映射；探针对应 `api/apps/system_app.py` 注册的旧版路径。

构建依赖当前完整仓库，不依赖其他部署目录。工具、依赖资源和基础镜像的下载仍发生在准备/构建阶段，这不是完全离线的构建包。

维护时的本地检查：

```bash
# Python 3.11+；依赖清单检查使用标准库 tomllib。
python3 -m unittest discover -s tests -v
for script in common.sh prepare.sh build.sh smoke_test.sh; do bash -n "$script" || exit; done
# 从本目录检查仓库根目录的当前依赖，不安装应用环境。
uv lock --project ../../.. --python 3.12 --check
uv sync --project ../../.. --python 3.12 --python-platform aarch64-unknown-linux-gnu --locked --no-dev --dry-run
```
