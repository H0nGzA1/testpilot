"""Artifact storage. Uploads mp4 / trace.zip / history.json to RustFS (S3) and returns
a URL. Falls back to local disk when S3_ENDPOINT is empty (dev)."""

from __future__ import annotations

import asyncio
import os
import shutil

from app.config import get_settings


def _upload_sync(local_path: str, key: str) -> str:
    s = get_settings()
    if not s.s3_endpoint:
        dest = os.path.join(s.artifact_dir, key)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(local_path, dest)
        # app-relative path served by StaticFiles at /artifacts (browser-loadable)
        return f"/artifacts/{key}"

    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint,
        aws_access_key_id=s.s3_access_key,
        aws_secret_access_key=s.s3_secret_key,
        region_name=s.s3_region,
    )
    client.upload_file(local_path, s.s3_bucket, key)
    # presigned GET so the API layer can hand a short-lived URL to the UI (design doc §4 NFR-4)
    return client.generate_presigned_url(
        "get_object", Params={"Bucket": s.s3_bucket, "Key": key}, ExpiresIn=3600
    )


async def upload(local_path: str, key: str) -> str:
    return await asyncio.to_thread(_upload_sync, local_path, key)
