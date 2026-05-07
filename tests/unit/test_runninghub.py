from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from tool.image_gen.runninghub import (
    RunningHubClient,
    RunningHubError,
    RunningHubTaskFailed,
    RunningHubTimeout,
)


def _client(handler, **kwargs) -> RunningHubClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    return RunningHubClient(
        api_key="fake-key",
        base_url="https://rh.test",
        poll_interval_seconds=0.0,
        poll_timeout_seconds=1.0,
        http_client=http,
        **kwargs,
    )


def _upload_ok(payload: dict) -> httpx.Response:
    return httpx.Response(200, json={"code": 0, "msg": "ok", "data": payload})


def _standard(
    *,
    task_id: str = "std-1",
    status: str = "SUCCESS",
    results: list[dict] | None = None,
    error_code: str = "",
    error_message: str = "",
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "taskId": task_id,
            "status": status,
            "errorCode": error_code,
            "errorMessage": error_message,
            "results": results,
            "clientId": "",
            "promptTips": "",
        },
    )


def test_init_requires_api_key() -> None:
    with pytest.raises(RunningHubError):
        RunningHubClient(api_key="")
    RunningHubClient(api_key="k")


@pytest.mark.asyncio
async def test_upload_image_returns_file_name(tmp_path: Path) -> None:
    img = tmp_path / "ref.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["content_type"] = request.headers.get("content-type", "")
        return _upload_ok({"fileName": "server-xyz.png"})

    client = _client(handler)
    try:
        name = await client.upload_image(img)
    finally:
        await client.aclose()

    assert name == "server-xyz.png"
    assert seen["url"].endswith("/task/openapi/upload")
    assert "multipart/form-data" in seen["content_type"]


@pytest.mark.asyncio
async def test_upload_image_missing_file_raises(tmp_path: Path) -> None:
    client = _client(lambda req: _upload_ok({}))
    try:
        with pytest.raises(RunningHubError):
            await client.upload_image(tmp_path / "nope.png")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_create_image_to_image_posts_standard_payload() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return _standard(task_id="std-42", status="QUEUED", results=None)

    client = _client(handler)
    try:
        task_id, payload = await client.create_image_to_image_task(
            image_url="https://rh.test/view?filename=api/ref.png&type=input&subfolder=",
            prompt="make architecture",
            aspect_ratio="16:9",
            resolution="1k",
        )
    finally:
        await client.aclose()

    assert task_id == "std-42"
    assert payload["status"] == "QUEUED"
    assert captured["url"].endswith("/openapi/v2/rhart-image-n-g31-flash/image-to-image")
    assert captured["auth"] == "Bearer fake-key"
    assert captured["body"] == {
        "imageUrls": ["https://rh.test/view?filename=api/ref.png&type=input&subfolder="],
        "prompt": "make architecture",
        "aspectRatio": "16:9",
        "resolution": "1k",
    }


@pytest.mark.asyncio
async def test_poll_result_succeeds_after_running_status() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return _standard(task_id="std-1", status="RUNNING", results=None)
        return _standard(
            task_id="std-1",
            status="SUCCESS",
            results=[{"url": "https://cdn/final.jpg", "outputType": "jpg", "text": None}],
        )

    client = _client(handler)
    try:
        payload = await client.poll_result("std-1")
    finally:
        await client.aclose()

    assert payload["status"] == "SUCCESS"
    assert payload["results"][0]["url"] == "https://cdn/final.jpg"


@pytest.mark.asyncio
async def test_poll_result_retries_transient_http_errors() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(525, text="")
        return _standard(
            task_id="std-1",
            status="SUCCESS",
            results=[{"url": "https://cdn/final.jpg", "outputType": "jpg", "text": None}],
        )

    client = _client(handler)
    try:
        payload = await client.poll_result("std-1")
    finally:
        await client.aclose()

    assert calls == 2
    assert payload["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_poll_result_terminal_failure_raises() -> None:
    client = _client(lambda req: _standard(status="FAILED", results=None))
    try:
        with pytest.raises(RunningHubTaskFailed):
            await client.poll_result("std-err")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_poll_result_times_out() -> None:
    client = _client(lambda req: _standard(status="RUNNING", results=None))
    try:
        with pytest.raises(RunningHubTimeout):
            await client.poll_result("std-slow")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_run_image_to_image_end_to_end(tmp_path: Path) -> None:
    ref = tmp_path / "ref.png"
    ref.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    dest = tmp_path / "out.jpg"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/task/openapi/upload"):
            return _upload_ok({"fileName": "api/ref.png"})
        if url.endswith("/openapi/v2/rhart-image-n-g31-flash/image-to-image"):
            return _standard(task_id="std-99", status="RUNNING", results=None)
        if url.endswith("/openapi/v2/query"):
            return _standard(
                task_id="std-99",
                status="SUCCESS",
                results=[{"url": "https://cdn/final.jpg", "outputType": "jpg", "text": None}],
            )
        if url == "https://cdn/final.jpg":
            return httpx.Response(200, content=b"JPEG")
        raise AssertionError(f"unexpected {url}")

    client = _client(handler)
    try:
        result = await client.run_image_to_image(
            image_path=ref,
            prompt="make architecture",
            dest_path=dest,
            aspect_ratio="16:9",
            resolution="1k",
        )
    finally:
        await client.aclose()

    assert result.task_id == "std-99"
    assert result.file_url == "https://cdn/final.jpg"
    assert result.file_type == "jpg"
    assert dest.read_bytes() == b"JPEG"


@pytest.mark.asyncio
async def test_standard_api_error_code_raises() -> None:
    client = _client(
        lambda req: _standard(error_code="1007", error_message="bad image")
    )
    try:
        with pytest.raises(RunningHubError):
            await client.create_image_to_image_task(
                image_url="https://example.test/ref.png",
                prompt="p",
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_create_image_to_image_retries_rate_limit() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return _standard(error_code="1003", error_message="rate limit")
        return _standard(task_id="std-retry", status="QUEUED", results=None)

    client = _client(handler)
    try:
        task_id, payload = await client.create_image_to_image_task(
            image_url="https://example.test/ref.png",
            prompt="p",
        )
    finally:
        await client.aclose()

    assert calls == 2
    assert task_id == "std-retry"
    assert payload["status"] == "QUEUED"


@pytest.mark.asyncio
async def test_parse_surfaces_http_errors() -> None:
    client = _client(lambda req: httpx.Response(502, text="bad gateway"))
    try:
        with pytest.raises(RunningHubError):
            await client.create_image_to_image_task(
                image_url="https://example.test/ref.png",
                prompt="p",
            )
    finally:
        await client.aclose()
