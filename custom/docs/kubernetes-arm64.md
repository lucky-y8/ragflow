# Python ARM64 容器平台部署

本模板使用已经构建的 `ragflow:python-arm64`，部署 Python API、一个任务执行器、数据同步进程和 Nginx 前端。数据库、Redis、对象存储和 Elasticsearch 全部连接平台现有服务；模板不创建这些中间件，也不启动 Go 服务。

当前镜像已在 ARM 主机通过 Python、原生依赖和浏览器自检。本文的 K8s 配置尚未连接实际平台验证。ONNX Runtime 的 GPU 探测警告不代表这次 CPU 自检失败；文档解析和模型调用仍需部署后验证。

## 交付文件

- `custom/backend_python/deploy/ragflow-arm64.yaml`：生成好的合并 YAML，占位符版本，可交平台填写和导入。包含 3 个 ConfigMap、1 个 Deployment、1 个 Service；不包含密码。
- `custom/backend_python/deploy/k8s/credentials.yaml.example`：Secret 示例，包含平台需要提供的 5 个密码/密钥变量。
- `custom/backend_python/deploy/k8s/connections.env`：中间件连接参数。
- `custom/backend_python/deploy/k8s/runtime.env`：Python 后端、存储类型、时区等应用参数。
- `custom/backend_python/deploy/k8s/kustomization.yaml`：namespace 和镜像地址的统一入口。

推荐维护 `k8s/` 源文件，然后重新生成合并 YAML。平台只接受 YAML 时，可以直接填写合并文件；此时后续重新生成会覆盖这些手工修改，需要同时更新源文件。不要把 `.env` 文件当 Shell 脚本执行；它们由 Kustomize 读取，值不加引号。

## 需要替换的信息

| 项目 | 位置/变量 | 填写要求 |
| --- | --- | --- |
| namespace | `kustomization.yaml` 的 `namespace` | 当前 `ragflow` 是示例，替换成平台分配的已存在 namespace；本模板不创建 namespace |
| 镜像 | 同文件 `images.newName/newTag` | 当前 `registry.example.com/replace-me/ragflow:python-arm64` 是占位符；init 和应用容器使用同一镜像 |
| 拉取凭据 | `deployment.yaml` 的 `imagePullSecrets` 注释 | 私有仓库需要时，引用同 namespace 下平台已有的镜像仓库 Secret；它与中间件 Secret 不同 |
| MySQL | `MYSQL_HOST/PORT/DBNAME/USER`，Secret `MYSQL_PASSWORD` | host 不含协议和端口；预先创建数据库并授予应用建表、变更表及读写权限；端口默认 3306，可修改 |
| Redis | `REDIS_HOST/PORT/DB/USERNAME`，Secret `REDIS_PASSWORD` | 单地址 DNS/IPv4；选择应用专用实例或逻辑 DB，默认 DB 1；无 ACL 用户名时留空，无密码时密码留空 |
| Elasticsearch | `ES_HOSTS/ES_USER/ES_VERIFY_CERTS`，Secret `ES_PASSWORD` | 完整 http(s) URL，可逗号分隔多个节点；无认证时用户名、密码都留空；默认校验证书 |
| 存储类型 | `runtime.env` 的 `STORAGE_IMPL` | MinIO 使用 `MINIO`，其他兼容 S3 服务使用 `AWS_S3`，不是 `S3` |
| 对象存储 | `OBJECT_STORAGE_ENDPOINT/BUCKET/REGION/PREFIX` | 完整 http(s) endpoint 及实际端口，不带桶路径；桶由平台预先创建；默认前缀 `ragflow`，不要留空 |
| 存储密钥 | Secret `OBJECT_STORAGE_ACCESS_KEY/SECRET_KEY` | 使用指定桶的访问凭据，授予读、写、列举、删除对象及检查桶权限 |
| S3 寻址 | `S3_ADDRESSING_STYLE` | 默认 `path`；平台要求虚拟主机寻址时改为 `virtual`；仅 AWS_S3 分支使用 |
| 访问入口 | Service `ragflow`，端口 80 | 由平台绑定域名、Ingress 或网关；外部 TLS 在平台入口配置 |

`MYSQL_MAX_CONNECTIONS=32` 是每个进程的连接池上限，API 和工作进程总连接数可能更高，需按平台额度调整。客户端的 `max_allowed_packet` 配置不能替代平台 MySQL 服务端的大小限制。

当前代码要求 Elasticsearch 主版本至少为 8，仓库默认部署版本为 8.11.3；平台提供不同版本时，应先确认向量检索和索引接口兼容性。Redis 会用于队列、锁和会话签名密钥，不应当作可随时清空的普通缓存，需要平台确认持久化和淘汰策略。

连接能力以当前镜像代码为准：Redis 尚未接入 TLS、Sentinel、Cluster；此模板未配置 MySQL TLS。HTTPS Elasticsearch、MinIO/S3 默认保留证书校验；如果平台使用内部 CA、双向 TLS、临时 S3 凭据或上述其他连接模式，应拿到要求后补充对应挂载/配置，不能只改端口认为已经支持。不要将这些连接变量额外注入主容器，平台应按模板注入 `render-config` 初始化容器。

## 提交镜像

以下命令在已构建镜像的 ARM 电脑上执行。

平台接收离线镜像文件时：

```bash
cd ~/Desktop/workcode/ragflow
set -o pipefail
sudo docker save ragflow:python-arm64 | gzip > ragflow-python-arm64.tar.gz
sha256sum ragflow-python-arm64.tar.gz > ragflow-python-arm64.tar.gz.sha256
```

将镜像压缩包和校验文件交平台导入其镜像仓库。镜像 tar 不包含本次新建的部署模板，应另外交付 YAML、Secret 示例和本文。

平台提供仓库账号后，可改用推送方式（替换示例域名、项目名和版本号）：

```bash
sudo docker login registry.example.com
sudo docker tag ragflow:python-arm64 registry.example.com/your-project/ragflow:python-arm64-20260922
sudo docker push registry.example.com/your-project/ragflow:python-arm64-20260922
```

同步修改 `kustomization.yaml` 中的镜像名和 tag。正式发布采用不同的版本 tag 或固定 digest，避免重复覆盖同一个 tag 后节点继续使用缓存镜像。仅在 ARM 电脑执行 `docker load` 不会让 Kubernetes 集群自动拥有镜像，平台必须完成仓库导入或集群节点镜像分发。

## 生成并部署

以下步骤由持有平台 kubeconfig 和 namespace 权限的人执行。没有平台权限时，只交付文件即可。不要将 kubeconfig 或实际密钥提交到仓库。

1. 修改 `kustomization.yaml`、`runtime.env`、`connections.env`，替换连接占位符；按需配置 `imagePullSecrets`。
2. 通过平台凭据界面创建同 namespace 的 `ragflow-credentials` Secret，键名严格按示例填写。也可以复制并填写本地 Secret 文件：

```bash
cp custom/backend_python/deploy/k8s/credentials.yaml.example custom/backend_python/deploy/k8s/credentials.local.yaml
# 编辑 credentials.local.yaml，填写真实值。该文件已被此目录 .gitignore 排除。
kubectl -n YOUR_NAMESPACE apply -f custom/backend_python/deploy/k8s/credentials.local.yaml
```

3. 从仓库根目录生成普通多文档 YAML 并部署：

```bash
kubectl kustomize custom/backend_python/deploy/k8s > custom/backend_python/deploy/ragflow-arm64.yaml
# 检查合并文件已替换占位符，且 namespace、镜像地址与平台一致。
kubectl apply --dry-run=server -f custom/backend_python/deploy/ragflow-arm64.yaml
kubectl apply -f custom/backend_python/deploy/ragflow-arm64.yaml
kubectl -n YOUR_NAMESPACE rollout status deployment/ragflow --timeout=20m
```

`kubectl kustomize` 在本地生成配置，不连接集群。服务端 dry-run 用于检查目标平台的 schema、资源额度和准入规则；通过仍不代表镜像、网络和账号一定可用。平台也可以直接导入已填好的合并 YAML，效果相同。

更改 `.env` 后重新生成并应用 YAML，ConfigMap 内容哈希会触发新 Pod。仅更新 Secret 时，需要重新创建 Pod 才会重新执行初始化容器：

```bash
kubectl -n YOUR_NAMESPACE rollout restart deployment/ragflow
```

## 资源和访问

模板固定调度到 Linux ARM64 节点，使用一个副本、一个任务执行器，并通过 `MAX_CONCURRENT_TASKS=1` 和 `MAX_CONCURRENT_CHUNK_BUILDERS=1` 限制初次联调并发。应用资源暂设 request 2 CPU / 4 GiB，limit 4 CPU / 8 GiB，供小规模联调起步；不是经过负载测试的容量承诺。OCR、浏览器、大文件和并发解析可能需要更高内存，按平台额度和实测调整。无需申请 GPU；构建时使用的 `192.168.229.39:7890` 代理没有写入运行配置。

Service 为 ClusterIP 80，前端和 `/api/v1` 共用入口。平台网关应支持较大的文档上传及较长的流式响应。暂不提供 Ingress，因为 ingressClass、域名和证书尚未确定。临时本地访问：

```bash
kubectl -n YOUR_NAMESPACE port-forward service/ragflow 9380:80
# 然后访问 http://127.0.0.1:9380
```

启动和存活探针调用 `/api/v1/system/ping`，初次启动预留约 15 分钟；就绪探针调用 `/api/v1/system/healthz`，检查数据库、Redis、文档引擎和对象存储。不把外部依赖健康检查作为存活探针，以免依赖故障触发持续重启。现有 healthz 不验证工作进程心跳，必须另做一次实际解析验收。

镜像沿用现有入口，需要 root 用户、可写根文件系统、Nginx 80 端口；没有申请 privileged 权限。如果平台强制非 root 或只读根文件系统，需要另行改造镜像。应用日志和临时文件随 Pod 重建丢失，应由平台采集/轮转日志；持久数据依赖外部 MySQL、对象存储、Elasticsearch 和 Redis，本模板不申请 PVC。

单副本 `Recreate` 更新会短暂停服。升级前安排维护窗口并等待解析任务结束；模板中的终止宽限时间并不能保证当前入口会优雅排空任务。暂不配置 HPA，也不承诺多副本高可用。

## 部署验收与排错

```bash
kubectl -n YOUR_NAMESPACE get pods -l app.kubernetes.io/name=ragflow -o wide
kubectl -n YOUR_NAMESPACE logs deployment/ragflow -c render-config
kubectl -n YOUR_NAMESPACE logs deployment/ragflow -c ragflow --tail=200
kubectl -n YOUR_NAMESPACE describe pods -l app.kubernetes.io/name=ragflow
```

- `ImagePullBackOff`：检查镜像导入、地址、tag、仓库凭据及 ARM64 manifest。
- `Pending`：检查 ARM64 节点、CPU/内存额度和节点污点；本模板没有猜测平台 tolerations。
- 初始化报 `Configuration error`：按日志指出的变量名补全占位符、格式或认证组合；脚本不打印密钥值。
- Pod 不 Ready：检查 `/api/v1/system/healthz` 响应和应用日志，确认网络、账号权限、服务版本及 TLS。

Pod Ready 后，访问页面并创建账号，在界面配置聊天模型和嵌入模型的 API 地址、模型名及凭据，再上传一份小文档，确认解析完成、可以检索和问答。这些模型服务不包含在镜像中；平台需要允许应用访问相应地址。确认账号管理方式后，可按需将 `REGISTER_ENABLED` 改成 `0`。

## 与现有代码的集成点

所有新文件位于 `custom/`，未改动业务代码、Dockerfile 或镜像入口：

- `render_config.py` 使用标准库读取初始化容器的环境变量，把完整连接配置写入共享内存卷，文件权限为 0600，内容用 JSON 编码以保留密码中的引号、换行和 `$` 等字符。JSON 可由现有 YAML 读取器解析。
- 主容器仅通过 `subPath` 挂载 `/ragflow/conf/local.service_conf.yaml`。`common/config_utils.py:read_config()` 将其中各顶层节覆盖默认配置；原有整个 `/ragflow/conf` 目录仍可使用。
- 主容器只接收 `runtime.env`，连接参数和 Secret 只注入初始化容器，避免 `docker/entrypoint.sh` 渲染原始模板时改变密码或 YAML 语法。
- `common/settings.py` 使用 `API_PROXY_SCHEME=python`（入口）、`DB_TYPE=mysql`、`DOC_ENGINE=elasticsearch`、`STORAGE_IMPL=MINIO/AWS_S3` 选择运行路径；适配字段对应 `rag/utils/{redis_conn,minio_conn,s3_conn}.py` 及 `common/doc_store/es_conn_pool.py`。
- `api/apps/restful_apis/system_api.py` 提供 ping/healthz。`user_default_llm` 覆盖为空，避免继承镜像中示例 TEI 地址；模型在部署后配置。

修改配置脚本后可运行不依赖中间件的检查：

```bash
python3 -m unittest discover -s custom/backend_python/deploy/k8s -p 'test_*.py' -v
kubectl kustomize custom/backend_python/deploy/k8s > custom/backend_python/deploy/ragflow-arm64.yaml
```

参考 [Kubernetes Kustomize 文档](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/)、[ConfigMap 环境变量](https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/)、[启动/就绪/存活探针](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)、[私有镜像仓库凭据](https://kubernetes.io/docs/tasks/configure-pod-container/pull-image-private-registry/)。
