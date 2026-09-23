"""读取部署环境变量，生成 RAGFlow 已有机制支持的本地 YAML 覆盖配置。"""

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit


def _value(env, key, default=None, *, allow_empty=False):
    """检查必填值和未替换的占位符；异常只指出变量名，不输出密钥值。"""
    value = env.get(key, default)
    if value is None or (not allow_empty and not value.strip()):
        raise ValueError(f"{key} is required")
    if "REPLACE_ME" in value:
        raise ValueError(f"Replace the placeholder in {key}")
    return value


def _integer(env, key, default, minimum=1, maximum=65535):
    try:
        value = int(_value(env, key, str(default)))
        if not minimum <= value <= maximum:
            raise ValueError
    except ValueError:
        raise ValueError(f"{key} must be an integer in [{minimum}, {maximum}]") from None
    return value


def _boolean(env, key, default):
    value = _value(env, key, default).lower()
    if value not in ("true", "false"):
        raise ValueError(f"{key} must be true or false")
    return value == "true"


def _host(env, key):
    """MySQL 和 Redis 的地址与端口分开填写，这里只接收主机名或 IPv4。"""
    value = _value(env, key)
    if any(char.isspace() or char in ":/@?#" for char in value):
        raise ValueError(f"{key} must be a DNS name or IPv4 address, without scheme or port")
    return value


def _endpoint(value, key):
    """校验 ES 和存储完整地址；账号密码必须单独传入，不能嵌在 URL 中。"""
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or any(char.isspace() for char in value)
            or parsed.port == 0
        ):
            raise ValueError
    except ValueError:
        raise ValueError(f"{key} must be an http(s) endpoint without credentials, path or query") from None
    return parsed


def build_config(env):
    """把平台环境变量映射成当前 Python 后端实际读取的配置字段。"""
    for key, expected in (("DB_TYPE", "mysql"), ("DOC_ENGINE", "elasticsearch")):
        if _value(env, key, expected) != expected:
            raise ValueError(f"This deployment requires {key}={expected}")

    mysql = {
        "name": _value(env, "MYSQL_DBNAME"),
        "host": _host(env, "MYSQL_HOST"),
        "port": _integer(env, "MYSQL_PORT", 3306),
        "user": _value(env, "MYSQL_USER"),
        "password": _value(env, "MYSQL_PASSWORD"),
        "max_connections": _integer(env, "MYSQL_MAX_CONNECTIONS", 32, maximum=10000),
        "stale_timeout": 300,
        "max_allowed_packet": 1073741824,
    }
    redis = {
        "host": f"{_host(env, 'REDIS_HOST')}:{_integer(env, 'REDIS_PORT', 6379)}",
        "db": _integer(env, "REDIS_DB", 1, minimum=0, maximum=2147483647),
        "username": _value(env, "REDIS_USERNAME", "", allow_empty=True),
        "password": _value(env, "REDIS_PASSWORD", "", allow_empty=True),
    }
    if redis["username"] and not redis["password"]:
        raise ValueError("REDIS_PASSWORD is required when REDIS_USERNAME is set")

    hosts = [value.strip() for value in _value(env, "ES_HOSTS").split(",")]
    for host in hosts:
        _endpoint(host, "ES_HOSTS")
    es = {"hosts": ",".join(hosts), "verify_certs": _boolean(env, "ES_VERIFY_CERTS", "true")}
    es_user = _value(env, "ES_USER", "", allow_empty=True)
    es_password = _value(env, "ES_PASSWORD", "", allow_empty=True)
    if bool(es_user) != bool(es_password):
        raise ValueError("Set both ES_USER and ES_PASSWORD, or leave both empty")
    if es_user:
        es.update(username=es_user, password=es_password)

    storage = _value(env, "STORAGE_IMPL", "MINIO")
    if storage not in ("MINIO", "AWS_S3"):
        raise ValueError("STORAGE_IMPL must be MINIO or AWS_S3")
    endpoint = _value(env, "OBJECT_STORAGE_ENDPOINT")
    parsed = _endpoint(endpoint, "OBJECT_STORAGE_ENDPOINT")
    bucket = _value(env, "OBJECT_STORAGE_BUCKET")
    prefix = _value(env, "OBJECT_STORAGE_PREFIX", "ragflow").strip("/")
    if not prefix:
        raise ValueError("OBJECT_STORAGE_PREFIX must contain a non-slash character")
    access_key = _value(env, "OBJECT_STORAGE_ACCESS_KEY")
    secret_key = _value(env, "OBJECT_STORAGE_SECRET_KEY")
    region = _value(env, "OBJECT_STORAGE_REGION", "", allow_empty=True)

    config = {
        "ragflow": {"host": "0.0.0.0", "http_port": 9380},
        "mysql": mysql,
        "redis": redis,
        "es": es,
        # 模型和供应商凭据在应用启动后通过界面配置，不继承镜像中的示例模型地址。
        "user_default_llm": {},
    }
    # v0.24.0 的 MinIO 客户端固定 HTTP；S3 客户端读取完整地址和 region_name。
    if storage == "MINIO":
        if parsed.scheme != "http":
            raise ValueError("v0.24.0 MINIO only supports HTTP; use STORAGE_IMPL=AWS_S3 for HTTPS")
        config["minio"] = {
            "host": parsed.netloc,
            "user": access_key,
            "password": secret_key,
            "bucket": bucket,
            "prefix_path": prefix,
        }
    else:
        style = _value(env, "S3_ADDRESSING_STYLE", "path")
        if style not in ("path", "virtual", "auto"):
            raise ValueError("S3_ADDRESSING_STYLE must be path, virtual or auto")
        config["s3"] = {
            "endpoint_url": endpoint.rstrip("/"),
            "access_key": access_key,
            "secret_key": secret_key,
            "region_name": region,
            "bucket": bucket,
            "prefix_path": prefix,
            "signature_version": "s3v4",
            "addressing_style": style,
        }
    return config


def write_config(config, path):
    """用 0600 权限写入临时文件后替换目标，避免应用读取半写入的密码配置。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        # JSON 可被现有 YAML 读取器解析；原样保存密码，不经过 Shell 插值或拼接。
        json.dump(config, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    temporary.replace(path)


def main():
    """由初始化容器执行；配置错误时退出，阻止主应用带着错误参数启动。"""
    try:
        config = build_config(os.environ)
    except ValueError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 1
    write_config(config, Path("/generated/local.service_conf.yaml"))
    print("External-service configuration generated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
