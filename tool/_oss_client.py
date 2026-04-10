"""
OSS (Object Storage Service) upload helper.
Supports: mock (local filesystem) / aliyun oss2.

Provider selection via settings.oss_endpoint:
  empty → mock (saves to /tmp/ppt_agent_assets/)
  set   → Aliyun OSS via oss2
"""
import logging
import os
import uuid
from config.settings import settings

logger = logging.getLogger(__name__)

_MOCK_DIR = "/tmp/ppt_agent_assets"


def upload_bytes(data: bytes, key: str, content_type: str = "image/png") -> str:
    """
    Upload bytes to OSS (or mock filesystem).
    Returns the public-accessible URL (or local file:// path for mock).
    """
    if not settings.oss_endpoint:
        return _mock_upload(data, key)
    return _oss_upload(data, key, content_type)


def _mock_upload(data: bytes, key: str) -> str:
    """Save to local /tmp directory; return a placeholder URL."""
    full_path = os.path.join(_MOCK_DIR, key.lstrip("/"))
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "wb") as f:
        f.write(data)
    logger.debug(f"OSS mock: saved {len(data)} bytes → {full_path}")
    # Return a placeholder URL that front-ends can recognise as mock
    return f"file://{full_path}"


def _oss_upload(data: bytes, key: str, content_type: str) -> str:
    try:
        import oss2
        auth = oss2.Auth(settings.oss_access_key, settings.oss_secret_key)
        bucket = oss2.Bucket(auth, settings.oss_endpoint, settings.oss_bucket)
        bucket.put_object(key, data, headers={"Content-Type": content_type})
        base = settings.oss_base_url.rstrip("/")
        return f"{base}/{key}"
    except ImportError:
        raise RuntimeError("oss2 package not installed. Run: pip install oss2")
