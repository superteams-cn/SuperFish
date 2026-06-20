"""
S3 兼容对象存储客户端（RustFS）。

封装上传文件 / 提取文本等二进制与大文本的读写，使其不再依赖本地磁盘，
从而支持多副本部署与重启后恢复。源码部署默认连本机 RustFS（localhost:9000）。
"""

import threading
from typing import Any

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

from ..config import Config
from .logger import get_logger

logger = get_logger("superfish.object_store")

_client = None
_client_lock = threading.Lock()


def _get_client() -> Any:
    """返回共享的 boto3 S3 客户端（懒加载，线程安全）。"""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = boto3.client(
                    "s3",
                    endpoint_url=Config.S3_ENDPOINT_URL,
                    aws_access_key_id=Config.S3_ACCESS_KEY,
                    aws_secret_access_key=Config.S3_SECRET_KEY,
                    region_name=Config.S3_REGION,
                    config=BotoConfig(
                        signature_version="s3v4",
                        s3={"addressing_style": "path"},
                        # 止血：单次 S3 操作设连接/读取超时且不重试，避免回源卡死
                        # 时累积阻塞线程（历史接口的 30s 墙钟超时依赖它释放工作线程）。
                        connect_timeout=5,
                        read_timeout=30,
                        retries={"max_attempts": 1},
                    ),
                )
    return _client


def ensure_bucket() -> None:
    """确保桶存在（幂等）。应用启动时调用。"""
    client = _get_client()
    bucket = Config.S3_BUCKET
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        try:
            client.create_bucket(Bucket=bucket)
            logger.info(f"已创建对象存储桶: {bucket}")
        except ClientError as exc:
            # 并发创建或已存在时忽略
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                raise


def put_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """上传字节对象，返回对象 key。"""
    _get_client().put_object(Bucket=Config.S3_BUCKET, Key=key, Body=data, ContentType=content_type)
    return key


def put_text(key: str, text: str) -> str:
    """上传 UTF-8 文本对象。"""
    return put_bytes(key, text.encode("utf-8"), content_type="text/plain; charset=utf-8")


def get_bytes(key: str) -> bytes | None:
    """读取字节对象；不存在返回 None。"""
    try:
        resp = _get_client().get_object(Bucket=Config.S3_BUCKET, Key=key)
        return resp["Body"].read()
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("NoSuchKey", "404", "NoSuchBucket"):
            return None
        raise


def get_text(key: str) -> str | None:
    """读取文本对象；不存在返回 None。"""
    data = get_bytes(key)
    return data.decode("utf-8") if data is not None else None


def delete_prefix(prefix: str) -> None:
    """删除某前缀下的所有对象（用于删除项目时清理其文件）。"""
    client = _get_client()
    bucket = Config.S3_BUCKET
    paginator = client.get_paginator("list_objects_v2")
    to_delete: list[dict[str, str]] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []) or []:
            to_delete.append({"Key": obj["Key"]})
            if len(to_delete) == 1000:
                client.delete_objects(Bucket=bucket, Delete={"Objects": to_delete})
                to_delete = []
    if to_delete:
        client.delete_objects(Bucket=bucket, Delete={"Objects": to_delete})


def upload_file(key: str, local_path: str, content_type: str = "application/octet-stream") -> str:
    """把本地文件上传到对象存储。"""
    with open(local_path, "rb") as f:
        return put_bytes(key, f.read(), content_type=content_type)


def download_prefix_to_dir(prefix: str, local_dir: str) -> int:
    """把某前缀下的所有对象下载到本地目录（保留相对路径）。

    用于「prepare 在 A 节点、start 在 B 节点」时，把模拟所需文件物化到运行节点。
    返回下载的对象数量。
    """
    import os

    client = _get_client()
    bucket = Config.S3_BUCKET
    paginator = client.get_paginator("list_objects_v2")
    count = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []) or []:
            key = obj["Key"]
            rel = key[len(prefix) :].lstrip("/")
            if not rel:
                continue
            dest = os.path.join(local_dir, rel)
            os.makedirs(os.path.dirname(dest) or local_dir, exist_ok=True)
            data = get_bytes(key)
            if data is not None:
                with open(dest, "wb") as f:
                    f.write(data)
                count += 1
    return count
