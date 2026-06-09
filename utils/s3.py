import os
import mimetypes
from pathlib import Path
from typing import Optional
import boto3

BUCKET = os.environ.get("S3_BUCKET", "fieldlens-atlas-demo")
REGION = os.environ.get("AWS_REGION", "us-east-1")


def _s3():
    return boto3.client(
        "s3",
        region_name=REGION,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )


def upload_video(local_path: str, s3_key: Optional[str] = None) -> str:
    """Upload a local video file to S3. Returns the s3:// URI."""
    path = Path(local_path)
    if not path.exists():
        raise FileNotFoundError(f"Video not found: {local_path}")

    key = s3_key or f"videos/{path.name}"
    content_type, _ = mimetypes.guess_type(str(path))
    content_type = content_type or "video/mp4"

    client = _s3()
    client.upload_file(
        str(path),
        BUCKET,
        key,
        ExtraArgs={"ContentType": content_type},
    )
    return f"s3://{BUCKET}/{key}"


def generate_presigned_url(s3_key: str, expires_in: int = 3600) -> str:
    """Return a time-limited presigned URL for browser playback."""
    client = _s3()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": s3_key},
        ExpiresIn=expires_in,
    )


def key_from_uri(s3_uri: str) -> str:
    """Extract the S3 key from an s3:// URI."""
    return s3_uri.removeprefix(f"s3://{BUCKET}/")
