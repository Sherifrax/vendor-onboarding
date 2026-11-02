"""Private document storage behind local and S3 implementations."""

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path

from app.config import Settings


class Storage(ABC):
    """Store private bytes and retrieve them only through an authorised path."""

    @abstractmethod
    async def put(self, key: str, content: bytes, mime: str) -> None:
        """Store one private object under a caller-generated key."""

    @abstractmethod
    async def get(self, key: str) -> bytes:
        """Read a private object after the application has authorised access."""

    @abstractmethod
    async def presigned_get_url(self, key: str) -> str:
        """Return an expiring direct URL when the backing store supports one."""


class LocalStorage(Storage):
    """Private filesystem storage; files are never mounted as public HTTP assets."""

    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if self.root.resolve() not in candidate.parents:
            raise ValueError("storage key escapes local document root")
        return candidate

    async def put(self, key: str, content: bytes, mime: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, content)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def presigned_get_url(self, key: str) -> str:
        raise RuntimeError("local documents require an application-signed download link")


class S3Storage(Storage):
    """Private S3 storage with SSE and short-lived presigned download URLs."""

    def __init__(self, bucket: str, region: str) -> None:
        if not bucket:
            raise ValueError("S3_BUCKET is required when STORAGE_MODE=s3")
        try:
            import boto3
            from botocore.config import Config
        except ImportError as error:  # pragma: no cover - optional deployment dependency.
            raise RuntimeError("boto3 is required when STORAGE_MODE=s3") from error
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            region_name=region or None,
            config=Config(retries={"total_max_attempts": 2, "mode": "adaptive"}),
        )

    async def put(self, key: str, content: bytes, mime: str) -> None:
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=mime,
            ServerSideEncryption="AES256",
        )

    async def get(self, key: str) -> bytes:
        def read() -> bytes:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            with response["Body"] as body:
                return body.read()

        return await asyncio.to_thread(read)

    async def presigned_get_url(self, key: str) -> str:
        return await asyncio.to_thread(
            self.client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=3600,
        )


def get_storage(settings: Settings) -> Storage:
    """Build the configured private storage backend once at application startup."""

    if settings.storage_mode == "s3":
        return S3Storage(settings.s3_bucket, settings.aws_region)
    return LocalStorage(settings.local_storage_dir)
