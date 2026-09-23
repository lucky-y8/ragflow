# RAGFlow v0.24.0：ARM64 构建与 K8s 交付包

本仓库的 `v0.24.0-arm64` 分支直接基于官方 `v0.24.0` 标签（提交 `392ec99651da78f6a8e1a2f60fe4818a95a8651d`）创建。上游应用源码保持原样，新增内容仅为本目录中的 ARM64 构建和 K8s 交付配置，不包含 admin 分支的业务改动。

此文件夹可以单独拷贝到 ARM 电脑使用，包含构建脚本、Dockerfile、锁定依赖、资源下载器、自检脚本、K8s YAML 和环境变量/密码示例。普通配置均有中文注释。

构建对象固定为官方 **v0.24.0** 提交 `392ec99651da78f6a8e1a2f60fe4818a95a8651d`。准备脚本另行下载该提交源码；应用内容来自官方版本，构建适配来自本文件夹。默认输出 **`ragflow:v0.24.0-arm64`**，包含 Python 后端、前端 Nginx、一个任务执行器和数据同步进程。MySQL、Redis、对象存储、Elasticsearch 全部接平台现有服务。

本包已完成锁文件校验、Linux ARM64 / Python 3.12 依赖安装模拟、14 项单元测试、脚本语法和 YAML 离线检查。**尚未在你的 ARM 电脑上构建这一版镜像，也未连接实际 K8s 平台。** 前一次成功的镜像自检属于之前的版本，v0.24.0 需要重新构建、自检和联调。

## 文件说明

```text
v0.24.0/
├── README.md                       本说明
├── LICENSE                         上游 Apache-2.0 许可证
├── versions.env                    官方源码提交和主要工具版本
├── prepare.sh                      下载固定版本源码、uv、模型和浏览器等资源
├── build.sh                        使用已有 Buildx Builder 构建并导入 Docker
├── smoke_test.sh                   检查镜像版本、原生依赖、NLTK、Nginx 和浏览器
├── common.sh                       公共路径、代理与源码校验
├── Dockerfile                      ARM64 多阶段镜像构建文件
├── Dockerfile.dockerignore          官方源码构建上下文的忽略规则
├── .dockerignore                   本构建包上下文的忽略规则
├── .gitignore                      排除下载缓存、镜像压缩包和真实密码文件
├── download_resources.py           仅下载 Python 镜像需要的资源
├── build/
│   ├── pyproject.toml              v0.24.0 的依赖定义及 ARM64 排除项
│   └── uv.lock                     对应的锁文件
├── runtime/
│   ├── render_config.py            环境变量 → local.service_conf.yaml
│   └── smoke_test.py               镜像内执行的自检
├── k8s/
│   ├── ragflow.yaml                两个 ConfigMap、Deployment、Service
│   └── credentials.yaml.example    密码和密钥 Secret 示例
└── tests/                          无外部服务依赖的测试
```

`.build/` 在执行准备命令后生成，保存源码、工具和资源，不进入 Git。无需复制当前开发分支的应用代码进本目录，也无需切换当前仓库分支。构建时会检查独立源码目录的提交及修改状态；源码不符或有修改就退出，不会自动重置文件。

## 1. 在 ARM 电脑准备资源

把整个 `v0.24.0` 文件夹同步到 ARM 电脑。下面命令假设它仍位于原仓库的 `custom/backend_python/` 中；单独复制到了其他地方，只需调整 `cd` 路径。

```bash
cd ~/Desktop/workcode/ragflow/custom/backend_python/v0.24.0
uname -m
# 应为 aarch64。需要 git、curl、tar、sha256sum、bash、realpath 和可用网络。
env RAGFLOW_BUILD_PROXY='http://192.168.235.138:7890' bash prepare.sh
```

不需要在宿主机安装整套 RAGFlow。脚本下载独立的 uv 0.9.16（校验官方 SHA-256），用它管理 Python 3.12.12 和下载脚本依赖。这里不调用旧版 `nltk.download()`，不会触发之前遇到的 NLTK 代理 DNS 安全检查。

资源包括 Tika **3.2.3**、Chrome/ChromeDriver **153.0.8010.52 ARM64**、NLTK 和固定提交的 DeepDoc 模型。Chrome 版本沿用已在你的 ARM 电脑上验证过的版本，配合 v0.24.0 的 Python 3.12 环境仍须再跑自检。普通资源先写 `.part`，完成后再替换；失败可重跑，已下载文件会复用。

默认下载位置为本目录 `.build/`。可通过 `RAGFLOW_BUILD_DIR` 指定另一个工作目录，或通过 `RAGFLOW_RESOURCE_DIR` 指向已有资源目录以复用同名文件；后续运行 `prepare.sh` 与 `build.sh` 时必须传入相同路径。指定已有资源目录后，脚本会下载缺失资源，并同步本包固定的模型版本。仍缺少的 v0.24.0 Tika 3.2.3 会另外下载，不使用 3.3.0 代替。

## 2. 构建镜像

使用已配置新代理的 `ragflow-arm64-proxy-235` Builder（脚本默认值仍为原 Builder，因此这里显式指定）：

```bash
sudo env \
  RAGFLOW_BUILD_PROXY='http://192.168.235.138:7890' \
  RAGFLOW_BUILDER='ragflow-arm64-proxy-235' \
  bash build.sh
```

构建成功后输出 `ragflow:v0.24.0-arm64`，并检查镜像架构为 `linux/arm64`。脚本通过本地资源上下文提供模型和二进制文件，不需要下载 `infiniflow/ragflow_deps:latest` 镜像。使用 `--provenance=false --load`，沿用此前 Buildx 0.10.5 / BuildKit 0.12.5 的构建方式。

代理同时用于下载、Buildx 客户端鉴权和构建步骤。Builder 容器自身仍需已有的代理配置；脚本不会创建或修改 Builder。Builder 名称不同时，用 `RAGFLOW_BUILDER` 指定实际名称。

APT 下载配置了 5 次重试、60 秒连接/传输超时和 deb 缓存；更新索引或安装失败会立即退出，不使用 `--fix-missing` 跳过依赖。默认安装证书后使用官方 HTTPS `ubuntu-ports` 源。基础镜像缺少证书，最初的索引更新和证书安装仍使用原 HTTP 源，并同样启用重试。

若 Ubuntu 包下载出现代理 `502 Bad Gateway`，可以单独指定 ARM64 软件源重试（不改变 Python、Node.js 等下载源）：

```bash
sudo env \
  RAGFLOW_BUILD_PROXY='http://192.168.235.138:7890' \
  RAGFLOW_BUILDER='ragflow-arm64-proxy-235' \
  RAGFLOW_APT_MIRROR='https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports' \
  bash build.sh
```

这里必须是 `ubuntu-ports`。参数会替换 Ubuntu 普通、更新和安全仓库的下载地址，保留 Ubuntu 的发行版及签名校验；镜像站同步可能有延迟。参考[清华 Ubuntu Ports 说明](https://mirrors.tuna.tsinghua.edu.cn/help/ubuntu-ports/)。该设置不能修复代理自身的持续故障。之前准备完成的 `.build/` 资源可以复用，无需重新执行 `prepare.sh` 或清理 Builder 缓存。

`graspologic` 是固定提交的 Git 依赖。若日志出现 `curl 92 HTTP/2 stream ... CANCEL`、`early EOF` 或 `invalid index-pack output`，说明 Git 下载连接中断，不能据此判断为 ARM64 编译不支持。Dockerfile 已在 Python 依赖安装层设置 `git config --global http.version HTTP/1.1`；该设置只写入构建阶段容器，不修改宿主机配置，依赖提交及 TLS 校验保持原样。参考 [Git http.version 文档](https://git-scm.com/docs/git-config#Documentation/git-config.txt-httpversion)。更新后使用相同 Builder、APT 镜像源和构建命令重试，已成功的基础层及 uv 下载缓存可继续复用。持续网络故障仍需检查代理链路。

默认 Node 构建堆上限 4096 MB、Python 包并行构建数 1，可通过 `NODE_BUILD_MAX_OLD_SPACE_SIZE` 和 `UV_CONCURRENT_BUILDS` 调整。你的 8 GB 机器仍可能在复杂原生编译时内存不足，应关闭其他占内存程序，检查实际可用内存、Swap，以及源码/资源目录和 `/var/lib/docker` 的可用空间。这里只确认依赖可解析，尚不保证该硬件能完成这一版全量构建。

不要只运行目录外旧的 `docker/build_python_arm64.sh`；本版本要运行本目录的 `build.sh`，由它传入固定源码、专用锁文件与资源。若需自定义镜像名，构建和自检都传入相同 `RAGFLOW_IMAGE`。

## 3. 镜像自检

```bash
sudo bash smoke_test.sh
```

自检不连接中间件，检查：镜像架构、`VERSION=v0.24.0`、Python 3.12、OpenCV/NumPy/XGBoost/ONNX Runtime 等依赖、MiniRacer JavaScript 引擎、NLTK 分词和词典、Nginx 配置、Chrome 与 ChromeDriver 配合运行。

ONNX Runtime 的 GPU 探测警告需要结合退出结果判断；本模板按 CPU 部署，没有申请 GPU。自检通过后还需在平台验证数据库连接、文件上传、实际文档解析和模型问答。

## 4. 向平台交付镜像

离线导出方式，在 ARM 电脑的本目录执行：

```bash
set -o pipefail
sudo docker save ragflow:v0.24.0-arm64 | gzip > ragflow-v0.24.0-arm64.tar.gz
sha256sum ragflow-v0.24.0-arm64.tar.gz > ragflow-v0.24.0-arm64.tar.gz.sha256
```

交给平台：镜像压缩包、SHA-256 文件、`k8s/ragflow.yaml`、`k8s/credentials.yaml.example` 和本文。平台将镜像导入仓库后，需要把 YAML 中两处 `image` 改成实际仓库地址。

平台提供仓库账号时，也可以推送（替换示例域名和项目路径）：

```bash
sudo docker login registry.example.com
sudo docker tag ragflow:v0.24.0-arm64 registry.example.com/your-project/ragflow:v0.24.0-arm64
sudo docker push registry.example.com/your-project/ragflow:v0.24.0-arm64
```

每次重新发布建议采用新 tag 或固定 digest，并同步 YAML 中初始化容器和应用容器的镜像地址。仅在构建电脑执行 `docker load` 不会让集群自动获得镜像。

## 5. 填写 K8s 和环境变量

本包没有 Kustomize 依赖，普通变量直接修改 `k8s/ragflow.yaml` 开头的两个 ConfigMap，密码由 Secret 提供。所有 `namespace: ragflow-v0240` 都是示例，统一改成平台分配的已存在 namespace。

| 参数 | 填写方式 |
| --- | --- |
| 两处 `image` | 平台已导入/已推送的本版本 ARM64 镜像地址，保持一致 |
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
kubectl -n YOUR_NAMESPACE apply -f k8s/credentials.local.yaml
```

## 6. 部署与验收

以下由持有平台 kubeconfig 的人员执行，所有占位符需已替换。没有集群权限时，交付文件即可。

```bash
kubectl apply --dry-run=server -f k8s/ragflow.yaml
kubectl apply -f k8s/ragflow.yaml
kubectl -n YOUR_NAMESPACE rollout status deployment/ragflow-v0240 --timeout=20m
kubectl -n YOUR_NAMESPACE get pods -l app.kubernetes.io/name=ragflow-v0240 -o wide
kubectl -n YOUR_NAMESPACE logs deployment/ragflow-v0240 -c render-config
kubectl -n YOUR_NAMESPACE logs deployment/ragflow-v0240 -c ragflow --tail=200
```

ConfigMap 和 Secret 更新后，必须重建 Pod，才能重新读取变量并执行配置生成：

```bash
kubectl -n YOUR_NAMESPACE rollout restart deployment/ragflow-v0240
```

应用默认一个副本、一个任务执行器，解析并发为 1。资源起始值 request 2 CPU / 4 GiB、limit 4 CPU / 8 GiB，属于联调配置，实际容量需验证。镜像固定调度到 Linux ARM64 节点；Pod Pending 时检查架构、资源配额、节点污点。

Service 是集群内 80 端口，前端页面和 API 走同一入口。外部域名、Ingress、网关 TLS 由平台配置，需支持文件上传和较长的流式响应。临时测试可用：

```bash
kubectl -n YOUR_NAMESPACE port-forward service/ragflow-v0240 9380:80
# 浏览器访问 http://127.0.0.1:9380
```

**v0.24.0 的探针路径是 `/v1/system/ping` 和 `/v1/system/healthz`。** 启动探针约预留 15 分钟，存活探针只检查 API，避免把外部依赖故障直接当作进程故障重启。旧版 healthz 调用了对象存储检查，但没有判断 MinIO 返回的 `False`，并且 AWS_S3 的健康检查会写入 `_t@@@1` 测试对象；所以 Ready 不能代替文件读写和文档解析验收。其接口也不保证任务执行器健康。

部署后按顺序验证：页面打开 → 创建账号 → 配置聊天和嵌入模型 → 上传小文档 → 解析完成 → 检索及问答正常。模型服务需要平台允许访问，模型 API 凭据在应用中配置。

镜像使用原有 root 入口和可写根文件系统，不申请 privileged 权限；平台若强制非 root 或只读根文件系统，需要另行改造。临时配置、日志和浏览器共享内存随 Pod 删除，长期日志由平台采集，业务数据保存在外部服务。本模板不申请 PVC。单副本 Recreate 更新会短暂停服，终止宽限不能保证旧版入口排空任务，更新前应安排维护窗口。

## 7. 构建适配与集成点

- 基于[官方 v0.24.0 Dockerfile](https://github.com/infiniflow/ragflow/blob/v0.24.0/Dockerfile)，保持 Python 3.12、Node.js 20、Tika 3.2.3，增加 ARM64 Chrome/ChromeDriver 和系统库。
- 以官方 `pyproject.toml`、`uv.lock` 为基础，仅排除没有 ARM64 wheel 且与 `mini-racer` 共享模块名的 `py-mini-racer`，其余锁定包版本保留；索引地址统一使用 PyPI。镜像使用 `--frozen` 安装。
- 镜像内删除 `docker/entrypoint.sh` 写死的 x86_64 `LD_LIBRARY_PATH`，保留其 Python API、工作进程和数据同步启动流程。没有改动应用业务代码。
- 官方 Compose 挂载的 `docker/nginx/` 三份配置改为直接打包进镜像，使 K8s Service 80 端口能够访问页面和 API。
- `runtime/render_config.py` 打包到 `/opt/ragflow-deploy/`。初始化容器读取 ConfigMap/Secret，写入权限为 0600 的 JSON 文件；JSON 可由原版 YAML 解析器读取，密码中的引号、换行和 `$` 等字符会原样保留。
- 主容器仅挂载 `/ragflow/conf/local.service_conf.yaml`，使用 `common/config_utils.py:read_config()` 的顶层配置覆盖机制，不覆盖整个 conf 目录。连接 Secret 不再注入主容器的原始 Shell 模板渲染过程。
- 存储配置按 v0.24.0 的 `rag/utils/minio_conn.py`、`s3_conn.py` 和 `common/settings.py` 映射；探针对应 `api/apps/system_app.py` 注册的旧版路径。

本目录是独立交付包，没有依赖旁边的其他部署目录。源码、构建资源和镜像的网络下载仍发生在准备/构建阶段，这不是完全离线的构建包。

维护时的本地检查：

```bash
python3 -m unittest discover -s tests -v
for script in common.sh prepare.sh build.sh smoke_test.sh; do bash -n "$script" || exit; done
# uv 使用本包依赖定义，不要对仓库根目录执行 uv sync。
uv lock --project build --python 3.12 --check
uv sync --project build --python 3.12 --python-platform aarch64-unknown-linux-gnu --frozen --no-dev --dry-run
```
