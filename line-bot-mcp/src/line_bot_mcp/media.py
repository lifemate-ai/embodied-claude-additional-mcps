"""Media helpers for outbound LINE image/audio (ffmpeg + S3 presigned URLs).

ffmpeg/ffprobe and boto3 are isolated behind small functions (`_run`,
`_s3_client`) so the senders can be unit-tested without invoking real binaries
or touching AWS. Objects are uploaded private; delivery is via short-lived
presigned GET URLs (LINE fetches them anonymously).
"""

from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path


def ensure_tools() -> None:
    """Raise a human-readable error if ffmpeg/ffprobe are not on PATH."""
    missing = [t for t in ("ffmpeg", "ffprobe") if shutil.which(t) is None]
    if missing:
        raise RuntimeError(
            f"{'/'.join(missing)} not found on PATH. Install ffmpeg "
            "(e.g. `brew install ffmpeg` or `apt install ffmpeg`)."
        )


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run a command capturing output; raise CalledProcessError on failure."""
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def ffprobe_duration_ms(path: str | Path) -> int:
    """Return the media duration in milliseconds via ffprobe."""
    result = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    out = result.stdout.strip()
    try:
        return int(round(float(out) * 1000))
    except ValueError:
        return 0  # ffprobe printed 'N/A' or empty -> caller emits a clean error


def to_m4a(src: str | Path, dst: str | Path) -> Path:
    """Transcode audio to m4a (AAC). If src is already m4a, copy it to dst."""
    src, dst = Path(src), Path(dst)
    if src.suffix.lower() == ".m4a":
        if src != dst:
            shutil.copyfile(src, dst)
        return dst
    _run(["ffmpeg", "-y", "-i", str(src), "-c:a", "aac", "-b:a", "128k", str(dst)])
    return dst


def make_preview(src: str | Path, dst: str | Path, max_px: int = 240) -> Path:
    """Downscaled JPEG preview (longest side <= max_px) for previewImageUrl.

    ffmpeg autorotates per EXIF by default and JPEG output drops any alpha, so
    the preview stays within LINE's 1MB/240px thumbnail constraint.
    """
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-vf",
            f"scale={max_px}:{max_px}:force_original_aspect_ratio=decrease",
            "-q:v",
            "7",
            str(dst),
        ]
    )
    return Path(dst)


def _s3_client(region: str):
    """Build an S3 client pinned to SigV4 (required for presigned GET)."""
    import boto3
    from botocore.config import Config as BotoConfig

    return boto3.client("s3", region_name=region, config=BotoConfig(signature_version="s3v4"))


def s3_upload(bucket: str, key: str, path: str | Path, content_type: str, region: str) -> None:
    """Upload a file to S3 as a private object (no ACL set)."""
    _s3_client(region).upload_file(str(path), bucket, key, ExtraArgs={"ContentType": content_type})


def s3_presigned_get(bucket: str, key: str, region: str, expires: int = 900) -> str:
    """Generate a presigned GET URL for a private object."""
    return _s3_client(region).generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires
    )


def upload_and_sign(
    bucket: str, path: str | Path, content_type: str, region: str, expires: int, ext: str
) -> str:
    """Upload under a random ``media/<uuid>.<ext>`` key and return a presigned GET URL."""
    key = f"media/{uuid.uuid4().hex}.{ext}"
    s3_upload(bucket, key, path, content_type, region)
    return s3_presigned_get(bucket, key, region, expires)
