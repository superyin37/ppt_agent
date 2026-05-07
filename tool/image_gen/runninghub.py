"""RunningHub standard model API client.

This client intentionally uses the direct image-to-image model endpoint:
- Authorization: Bearer <RUNNING_HUB_KEY>
- imageUrls + prompt + aspectRatio + resolution

Local files are first uploaded through RunningHub's upload endpoint, then
converted to a `/view?filename=...` URL for the standard model API.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)


class RunningHubError(RuntimeError):
    pass


class RunningHubTimeout(RunningHubError):
    pass


class RunningHubTaskFailed(RunningHubError):
    pass


@dataclass
class RunningHubResult:
    task_id: str
    file_url: str
    file_type: str
    local_path: Optional[Path] = None


_USER_AGENT = "PPT-Agent-RunningHub-Client/1.0"
_TERMINAL_SUCCESS = {"SUCCEED", "SUCCESS", "SUCCEEDED"}
_TERMINAL_FAILURE = {"FAILED", "ERROR", "CANCELLED", "CANCELED"}
_RETRYABLE_HTTP_STATUS = {408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524, 525}
_RETRYABLE_ERROR_CODES = {"1003"}
_DEFAULT_RETRY_ATTEMPTS = 3


class RunningHubClient:
    """Async client for RunningHub's standard image-to-image model API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://www.runninghub.cn",
        model_path: str = "/openapi/v2/rhart-image-n-g31-flash/image-to-image",
        query_path: str = "/openapi/v2/query",
        poll_interval_seconds: float = 3.0,
        poll_timeout_seconds: float = 180.0,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        if not api_key:
            raise RunningHubError("runninghub api_key is empty")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_path = _normalize_path(model_path)
        self.query_path = _normalize_path(query_path)
        self.poll_interval = poll_interval_seconds
        self.poll_timeout = poll_timeout_seconds
        self._external_client = http_client is not None
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(60.0),
            headers={"User-Agent": _USER_AGENT},
        )

    async def __aenter__(self) -> "RunningHubClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if not self._external_client:
            await self._client.aclose()

    async def upload_image(self, image_path: Path) -> str:
        """Upload a local image and return the server-side fileName."""
        image_path = Path(image_path)
        if not image_path.exists():
            raise RunningHubError(f"image not found: {image_path}")

        url = f"{self.base_url}/task/openapi/upload"
        files = {
            "file": (
                image_path.name,
                image_path.read_bytes(),
                _guess_mime(image_path),
            )
        }
        data = {"apiKey": self.api_key, "fileType": "image"}
        response = await self._client.post(url, data=data, files=files)
        payload = self._parse_upload_response(response, context="upload_image")
        file_name = payload.get("fileName") or payload.get("fileUrl")
        if not file_name:
            raise RunningHubError(
                f"runninghub upload returned no fileName: {payload!r}"
            )
        return file_name

    async def run_image_to_image(
        self,
        *,
        image_path: Path,
        prompt: str,
        dest_path: Path,
        aspect_ratio: str = "16:9",
        resolution: str = "1k",
    ) -> RunningHubResult:
        file_name = await self.upload_image(image_path)
        image_url = self.uploaded_file_to_view_url(file_name)
        task_id, initial = await self.create_image_to_image_task(
            image_url=image_url,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
        )
        final = (
            initial
            if (initial.get("status") or "").upper() in _TERMINAL_SUCCESS
            else await self.poll_result(task_id)
        )
        results = final.get("results") or []
        image_output = next((r for r in results if r.get("url")), None)
        if not image_output:
            raise RunningHubError(f"runninghub task returned no image url: {final!r}")
        file_url = image_output["url"]
        local_path = await self.download(file_url, dest_path)
        return RunningHubResult(
            task_id=task_id,
            file_url=file_url,
            file_type=image_output.get("outputType", "image"),
            local_path=local_path,
        )

    async def create_image_to_image_task(
        self,
        *,
        image_url: str,
        prompt: str,
        aspect_ratio: str = "16:9",
        resolution: str = "1k",
    ) -> tuple[str, dict[str, Any]]:
        url = f"{self.base_url}{self.model_path}"
        payload: dict[str, Any] | None = None
        for attempt in range(_DEFAULT_RETRY_ATTEMPTS):
            try:
                response = await self._client.post(
                    url,
                    json={
                        "imageUrls": [image_url],
                        "prompt": prompt,
                        "aspectRatio": aspect_ratio,
                        "resolution": resolution,
                    },
                    headers=self._bearer_headers(),
                )
                payload = self._parse_standard_response(response, context="image_to_image")
                break
            except Exception as exc:
                if not self._should_retry(exc) or attempt >= _DEFAULT_RETRY_ATTEMPTS - 1:
                    raise
                logger.warning(
                    "runninghub image_to_image transient failure, retrying "
                    "(attempt %d/%d): %s",
                    attempt + 1,
                    _DEFAULT_RETRY_ATTEMPTS,
                    exc,
                )
                await self._sleep_before_retry(attempt)

        if payload is None:
            raise RunningHubError("runninghub image_to_image returned no payload")
        task_id = payload.get("taskId")
        if not task_id:
            raise RunningHubError(f"runninghub task returned no taskId: {payload!r}")
        return str(task_id), payload

    async def poll_result(self, task_id: str) -> dict[str, Any]:
        deadline = asyncio.get_event_loop().time() + self.poll_timeout
        url = f"{self.base_url}{self.query_path}"
        last_status = "UNKNOWN"
        while True:
            try:
                response = await self._client.post(
                    url,
                    json={"taskId": task_id},
                    headers=self._bearer_headers(),
                )
                payload = self._parse_standard_response(response, context="query")
            except Exception as exc:
                if not self._should_retry(exc) or asyncio.get_event_loop().time() >= deadline:
                    raise
                logger.warning(
                    "runninghub query transient failure for task %s, retrying: %s",
                    task_id,
                    exc,
                )
                await self._sleep_before_retry(0)
                continue

            status = (payload.get("status") or last_status).upper()
            last_status = status
            logger.debug("runninghub task %s status=%s", task_id, status)

            if status in _TERMINAL_FAILURE:
                raise RunningHubTaskFailed(
                    f"runninghub task {task_id} terminal status={status}: "
                    f"{payload.get('errorMessage') or payload.get('failedReason')}"
                )
            if status in _TERMINAL_SUCCESS:
                return payload
            if asyncio.get_event_loop().time() >= deadline:
                raise RunningHubTimeout(
                    f"runninghub task {task_id} not finished within "
                    f"{self.poll_timeout}s (last status={last_status})"
                )
            await asyncio.sleep(self.poll_interval)

    async def download(self, file_url: str, dest: Path) -> Path:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        async with self._client.stream("GET", file_url) as resp:
            resp.raise_for_status()
            with dest.open("wb") as fh:
                async for chunk in resp.aiter_bytes():
                    fh.write(chunk)
        return dest

    def uploaded_file_to_view_url(self, file_name: str) -> str:
        return (
            f"{self.base_url}/view?filename={quote(file_name, safe='/')}"
            "&type=input&subfolder="
        )

    def _parse_upload_response(
        self,
        response: httpx.Response,
        *,
        context: str,
    ) -> dict[str, Any]:
        if response.status_code >= 400:
            raise RunningHubError(
                f"runninghub {context} HTTP {response.status_code}: {response.text[:300]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RunningHubError(
                f"runninghub {context} non-JSON response: {response.text[:300]}"
            ) from exc
        if not isinstance(payload, dict):
            raise RunningHubError(f"runninghub {context} unexpected payload: {payload!r}")
        code = payload.get("code")
        if code not in (0, "0", None):
            raise RunningHubError(
                f"runninghub {context} code={code} msg={payload.get('msg')}"
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise RunningHubError(f"runninghub {context} missing data object: {payload!r}")
        return data

    def _parse_standard_response(
        self,
        response: httpx.Response,
        *,
        context: str,
    ) -> dict[str, Any]:
        if response.status_code >= 400:
            raise RunningHubError(
                f"runninghub {context} HTTP {response.status_code}: {response.text[:300]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RunningHubError(
                f"runninghub {context} non-JSON response: {response.text[:300]}"
            ) from exc
        if not isinstance(payload, dict):
            raise RunningHubError(f"runninghub {context} unexpected payload: {payload!r}")
        error_code = payload.get("errorCode")
        if error_code:
            raise RunningHubError(
                f"runninghub {context} errorCode={error_code} "
                f"errorMessage={payload.get('errorMessage')}"
            )
        return payload

    def _bearer_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _should_retry(self, exc: Exception) -> bool:
        if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
            return True
        if not isinstance(exc, RunningHubError):
            return False
        message = str(exc)
        if any(f"HTTP {status}" in message for status in _RETRYABLE_HTTP_STATUS):
            return True
        return any(f"errorCode={code}" in message for code in _RETRYABLE_ERROR_CODES)

    async def _sleep_before_retry(self, attempt: int) -> None:
        delay = min(max(self.poll_interval, 0.0) * (attempt + 1), 10.0)
        if delay > 0:
            await asyncio.sleep(delay)


def _guess_mime(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "application/octet-stream")


def _normalize_path(path: str) -> str:
    if not path:
        return ""
    return path if path.startswith("/") else f"/{path}"
