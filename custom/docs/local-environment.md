# RAGFlow 本地环境（WSL，无 Docker）

所有服务使用当前项目的 `.local-dev` 数据目录。Python 包在 `.venv`，前端包在 `web/node_modules`。未修改系统 Python、Conda、NVM 默认版本，也不使用 UVC 项目的 Redis/MinIO 数据。

## 日常启动

在 WSL 中：

```bash
cd /home/yanilo/bhyh/ragflow
./custom/scripts/manage.py start
./custom/scripts/manage.py status
```

打开 http://localhost:9222 。前端已通过 `.env.development.local` 切换到 Python。

```bash
./custom/scripts/manage.py stop
./custom/scripts/manage.py logs api
./custom/scripts/manage.py logs worker
```

启动/停止仅操作 `ragflow-local-*` 用户服务。不会自动随 WSL 启动；WSL 重启后重新运行 `start`。数据会保留。

## 本项目端口

| 服务 | 地址 |
|---|---|
| Web | 127.0.0.1:9222 |
| Python API | 127.0.0.1:9380 |
| Admin API | 127.0.0.1:9381 |
| MySQL 8.0.40 | 127.0.0.1:13306 |
| Redis | 127.0.0.1:16379 |
| MinIO API / 控制台 | 127.0.0.1:19000 / 19001 |
| Elasticsearch 8.11.3 | 127.0.0.1:19200 |

## 配置与凭据

- `conf/local.service_conf.yaml`：本项目实际服务连接配置，覆盖默认配置。
- `.local-dev/config/credentials.json`：新生成的数据库、Redis、MinIO、管理员密码；文件权限 0600。
- 管理员邮箱 `admin@ragflow.io`，密码为上述文件的 `admin_password` 字段。
- MinIO 控制台账户 `ragflow-local`，密码为 `minio_password`。
- `.local-dev/config/runtime.env`：用户服务进程的环境变量。
- `.local-dev/logs/`：安装和服务日志。

这些本地配置、数据和凭据均已被 Git 忽略，不应提交。

## 手动开发

```bash
cd /home/yanilo/bhyh/ragflow
source custom/scripts/activate.sh
python --version
node --version
```

这只改变当前 shell。启动脚本已使用项目内 Python 3.13 和现有 Linux Node 22，无需激活或修改 Conda。

`manage.py start` 会先检查基础服务，并针对独立的 `rag_flow` 数据库执行仓库自带的初始化和迁移。

## 网络与模型

下载代理当前使用 Windows 的 `192.168.0.1:7890`。本地地址通过 `NO_PROXY` 直连。若 WSL/Windows 代理地址变化，需同步更新本地 runtime 配置。

DeepDoc ONNX、文本拼接模型、NLTK、Tika 和 tokenizer 数据放在当前项目的运行目录中。

聊天和向量化使用的模型提供商/API Key 需要在页面中自行配置；环境初始化不会调用付费模型。

## Python 3.13 的本地依赖调整

仓库锁文件中的 NumPy 1.26.4 不支持 Python 3.13，且 infinity-emb 的元数据限制 NumPy <2。本环境在 `.local-dev/python-project/pyproject.toml` 中使用 NumPy 2.2.6 的显式覆盖；仓库原始 pyproject.toml、uv.lock 未修改。

重新同步本地环境请使用：

```bash
./custom/scripts/sync_python.py
```

不要在这个虚拟环境直接执行仓库根目录的 `uv sync`，否则会重新尝试安装原锁文件中的不兼容 NumPy。`uv run` 自动同步也有同样问题；日常命令使用激活后的 `python`，或 `uv run --no-sync`。

## 已完成的验证

- Python 3.13.15、Linux Node 22.23.2；前端依赖安装完成。
- MySQL 认证、独立 Redis 读写、MinIO 临时文件写入/读取/清理成功。
- Elasticsearch 健康检查正常；官方归档 SHA512 校验通过。
- NumPy 2.2.6、OpenCV 4.10、SciPy 1.17、XGBoost 1.6、ONNX Runtime 1.23.2 可加载；XGBoost NumPy 输入检查通过。
- DeepDoc det/rec/layout/tsr 四个 ONNX 模型使用 CPUExecutionProvider 加载成功。
- 数据库迁移完成；API、管理服务、worker 和前端均已启动。
- API `/api/v1/system/healthz` 的 db/doc_engine/redis/storage 均为 ok。
- 从前端 `/api/v1/language` 返回 python；管理员和普通登录均成功。
- Windows 端访问 http://localhost:9222 返回 HTTP 200。
- 原系统 Redis 和 uvc-minio 用户服务保持运行。

服务是开发模式。未进行付费模型调用或完整文档入库/问答测试；需先在界面添加模型提供商和 API Key。本地 PyTorch 推理与浏览器自动化等可选功能未在本次基础环境验证范围内。

本地锁文件使用官方 PyPI 包文件 URL，包版本和 SHA256 保持锁定。
