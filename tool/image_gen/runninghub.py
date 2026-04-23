"""RunningHub REST API client — ComfyUI cloud workflow runner.

Endpoints used (see ADR-005 brief):
- POST {base}/task/openapi/upload       multipart file upload → returns data.fileName
- POST {base}/task/openapi/create       create workflow task → returns data.taskId
- POST {base}/task/openapi/outputs      poll task outputs → returns list of {fileUrl, fileType}
- POST {base}/task/openapi/status       (fallback) poll task status → returns taskStatus string

Auth: apiKey is passed in the JSON body / form data, never as an HTTP header.
Workflow parameter overrides use `nodeInfoList = [{nodeId, fieldName, fieldValue}, ...]`.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class RunningHubError(RuntimeError):
    pass


class RunningHubTimeout(RunningHubError):
    pass


class RunningHubTaskFailed(RunningHubError):
    pass


@dataclass
class NodeOverride:
    node_id: str
    field_name: str
    field_value: Any

    def to_payload(self) -> dict:
        return {
            "nodeId": self.node_id,
            "fieldName": self.field_name,
            "fieldValue": self.field_value,
        }


@dataclass
class RunningHubResult:
    task_id: str
    file_url: str
    file_type: str
    local_path: Optional[Path] = None


_USER_AGENT = "PPT-Agent-RunningHub-Client/1.0"
_TERMINAL_SUCCESS = {"SUCCEED", "SUCCESS", "SUCCEEDED"}
_TERMINAL_FAILURE = {"FAILED", "ERROR", "CANCELLED", "CANCELED"}


class RunningHubClient:
    """Thin async client wrapping the runninghub standard API."""

    def __init__(
        self,
        api_key: str,
        workflow_id: str,
        base_url: str = "https://www.runninghub.cn",
        poll_interval_seconds: float = 3.0,
        poll_timeout_seconds: float = 180.0,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        if not api_key:
            raise RunningHubError("runninghub api_key is empty")
        if not workflow_id:
            raise RunningHubError("runninghub workflow_id is empty")
        self.api_key = api_key
        self.workflow_id = workflow_id
        self.base_url = base_url.rstrip("/")
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
        """Upload a local image, return the server-side fileName."""
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
        payload = self._parse_ok(response, context="upload_image")
        file_name = payload.get("fileName") or payload.get("fileUrl")
        if not file_name:
            raise RunningHubError(
                f"runninghub upload returned no fileName: {payload!r}"
            )
        return file_name

    async def create_task(
        self,
        node_overrides: list[NodeOverride],
        *,
        instance_type: Optional[str] = None,
    ) -> str:
        """Create a workflow task, return the runninghub taskId."""
        url = f"{self.base_url}/task/openapi/create"
        body: dict[str, Any] = {
            "apiKey": self.api_key,
            "workflowId": self.workflow_id,
            "nodeInfoList": [override.to_payload() for override in node_overrides],
        }
        if instance_type:
            body["instanceType"] = instance_type
        response = await self._client.post(url, json=body)
        payload = self._parse_ok(response, context="create_task")
        task_id = payload.get("taskId")
        if not task_id:
            raise RunningHubError(f"runninghub create_task returned no taskId: {payload!r}")
        return str(task_id)

    async def poll_outputs(self, task_id: str) -> list[dict]:
        """Poll the task until it has outputs or fails. Returns list of {fileUrl, fileType, ...}."""
        deadline = asyncio.get_event_loop().time() + self.poll_timeout
        status_url = f"{self.base_url}/task/openapi/status"
        outputs_url = f"{self.base_url}/task/openapi/outputs"
        body = {"apiKey": self.api_key, "taskId": task_id}

        last_status = "UNKNOWN"
        while True:
            response = await self._client.post(status_url, json=body)
            payload = self._parse_ok(response, context="poll_status", allow_list=True)
            status = _extract_status(payload) or last_status
            last_status = status
            logger.debug("runninghub task %s status=%s", task_id, status)

            if status.upper() in _TERMINAL_FAILURE:
                raise RunningHubTaskFailed(
                    f"runninghub task {task_id} terminal status={status}"
                )

            if status.upper() in _TERMINAL_SUCCESS:
                outputs_resp = await self._client.post(outputs_url, json=body)
                outputs_payload = self._parse_ok(
                    outputs_resp, context="get_outputs", allow_list=True
                )
                outputs = _normalize_outputs(outputs_payload)
                if not outputs:
                    raise RunningHubError(
                        f"runninghub task {task_id} succeeded but returned no outputs"
                    )
                return outputs

            if asyncio.get_event_loop().time() >= deadline:
                raise RunningHubTimeout(
                    f"runninghub task {task_id} not finished within {self.poll_timeout}s "
                    f"(last status={last_status})"
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

    async def run_workflow(
        self,
        node_overrides: list[NodeOverride],
        dest_path: Path,
        *,
        instance_type: Optional[str] = None,
    ) -> RunningHubResult:
        """End-to-end: create → poll → download first image output."""
        task_id = await self.create_task(node_overrides, instance_type=instance_type)
        outputs = await self.poll_outputs(task_id)
        image_output = next(
            (o for o in outputs if (o.get("fileType") or "").lower() in {"png", "jpg", "jpeg", "webp", "image"}),
            outputs[0],
        )
        file_url = image_output.get("fileUrl")
        if not file_url:
            raise RunningHubError(f"runninghub output missing fileUrl: {image_output!r}")
        local_path = await self.download(file_url, dest_path)
        return RunningHubResult(
            task_id=task_id,
            file_url=file_url,
            file_type=image_output.get("fileType", "png"),
            local_path=local_path,
        )

    def _parse_ok(
        self,
        response: httpx.Response,
        *,
        context: str,
        allow_list: bool = False,
    ) -> Any:
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
        if data is None:
            raise RunningHubError(f"runninghub {context} missing data field: {payload!r}")
        if isinstance(data, list):
            if allow_list:
                return data
            raise RunningHubError(
                f"runninghub {context} got list, expected dict: {data!r}"
            )
        return data


def _extract_status(data: Any) -> Optional[str]:
    if isinstance(data, dict):
        return data.get("taskStatus") or data.get("status")
    if isinstance(data, str):
        return data
    if isinstance(data, list) and data:
        return "SUCCEED"
    return None


def _normalize_outputs(data: Any) -> list[dict]:
    if isinstance(data, list):
        return [o for o in data if isinstance(o, dict)]
    if isinstance(data, dict):
        if "fileUrl" in data:
            return [data]
        outputs = data.get("outputs") or data.get("data")
        if isinstance(outputs, list):
            return [o for o in outputs if isinstance(o, dict)]
    return []


def _guess_mime(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "application/octet-stream")
