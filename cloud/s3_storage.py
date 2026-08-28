import os
from pathlib import Path
import boto3


def enviar(origem: Path) -> str:
    bucket = os.environ["S3_BUCKET"]
    prefix = os.getenv("S3_PREFIX", "APPfndeDOWELEVER").strip("/")
    key = f"{prefix}/{origem.name}"
    boto3.client("s3").upload_file(str(origem), bucket, key)
    return f"s3://{bucket}/{key}"
