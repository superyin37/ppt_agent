from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from tool.image_gen.runninghub import (
    NodeOverride,
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
        workflow_id="wf-1",
        base_url="https://rh.test",
        poll_interval_seconds=0.0,
        poll_timeout_seconds=1.0,
        http_client=http,
        **kwargs,
    )


def _ok(payload: dict | list) -> httpx.Response:
    return httpx.Response(
        200,
        json={"code": 0, "msg": "ok", "data": payload},
    )


def test_init_requires_api_key_and_workflow() -> None:
    with pytest.raises(RunningHubError):
        RunningHubClient(api_key="", workflow_id="wf")
    with pytest.raises(RunningHubError):
        RunningHubClient(api_key="k", workflow_id="")


@pytest.mark.asyncio
async def test_upload_image_returns_file_name(tmp_path: Path) -> None:
    img = tmp_path / "ref.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["content_type"] = request.headers.get("content-type", "")
        return _ok({"fileName": "server-xyz.png"})

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
    client = _client(lambda req: _ok({}))
    try:
        with pytest.raises(RunningHubError):
            await client.upload_image(tmp_path / "nope.png")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_create_task_posts_node_info_list() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return _ok({"taskId": "task-42"})

    client = _client(handler)
    try:
        task_id = await client.create_task(
            [
                NodeOverride("6", "text", "positive"),
                NodeOverride("10", "image", "server.png"),
            ]
        )
    finally:
        await client.aclose()

    assert task_id == "task-42"
    assert captured["body"]["apiKey"] == "fake-key"
    assert captured["body"]["workflowId"] == "wf-1"
    assert captured["body"]["nodeInfoList"] == [
        {"nodeId": "6", "fieldName": "text", "fieldValue": "positive"},
        {"nodeId": "10", "fieldName": "image", "fieldValue": "server.png"},
    ]


@pytest.mark.asyncio
async def test_create_task_nonzero_code_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"code": 901, "msg": "quota exceeded", "data": {}}
        )

    client = _client(handler)
    try:
        with pytest.raises(RunningHubError):
            await client.create_task([])
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_poll_outputs_succeeds_after_running_status() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if url.endswith("/task/openapi/status"):
            if len([u for u in calls if u.endswith("/status")]) == 1:
                return _ok({"taskStatus": "RUNNING"})
            return _ok({"taskStatus": "SUCCEED"})
        if url.endswith("/task/openapi/outputs"):
            return _ok([{"fileUrl": "https://cdn/x.png", "fileType": "png"}])
        raise AssertionError(f"unexpected url {url}")

    client = _client(handler)
    try:
        outputs = await client.poll_outputs("task-42")
    finally:
        await client.aclose()

    assert outputs == [{"fileUrl": "https://cdn/x.png", "fileType": "png"}]
    assert sum(1 for u in calls if u.endswith("/status")) == 2


@pytest.mark.asyncio
async def test_poll_outputs_terminal_failure_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/status"):
            return _ok({"taskStatus": "FAILED"})
        raise AssertionError("outputs should not be fetched on failure")

    client = _client(handler)
    try:
        with pytest.raises(RunningHubTaskFailed):
            await client.poll_outputs("task-err")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_poll_outputs_times_out() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok({"taskStatus": "RUNNING"})

    client = _client(handler)
    try:
        with pytest.raises(RunningHubTimeout):
            await client.poll_outputs("task-slow")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_run_workflow_end_to_end(tmp_path: Path) -> None:
    dest = tmp_path / "out.png"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/task/openapi/create"):
            return _ok({"taskId": "task-99"})
        if url.endswith("/task/openapi/status"):
            return _ok({"taskStatus": "SUCCEED"})
        if url.endswith("/task/openapi/outputs"):
            return _ok([{"fileUrl": "https://cdn/final.png", "fileType": "png"}])
        if url == "https://cdn/final.png":
            return httpx.Response(200, content=b"BINARY")
        raise AssertionError(f"unexpected {url}")

    client = _client(handler)
    try:
        result = await client.run_workflow(
            [NodeOverride("6", "text", "p")], dest
        )
    finally:
        await client.aclose()

    assert result.task_id == "task-99"
    assert result.file_url == "https://cdn/final.png"
    assert result.local_path == dest
    assert dest.read_bytes() == b"BINARY"


@pytest.mark.asyncio
async def test_parse_ok_surfaces_http_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")

    client = _client(handler)
    try:
        with pytest.raises(RunningHubError):
            await client.create_task([])
    finally:
        await client.aclose()
