# 12. 错误码与异常设计

## 12.1 HTTP 错误响应格式

```json
{
  "success": false,
  "error": "人类可读的错误描述",
  "error_code": "ERROR_CODE_CONSTANT",
  "detail": {}
}
```

---

## 12.2 错误码枚举

### 4xx 用户侧错误

| 错误码 | HTTP 状态 | 含义 | 常见触发场景 |
|-------|---------|------|------------|
| PROJECT_NOT_FOUND | 404 | 项目不存在 | project_id 无效 |
| BRIEF_INCOMPLETE | 422 | 项目信息不完整 | 强制 confirm 但字段缺失 |
| INVALID_GEOJSON | 422 | GeoJSON 格式非法 | 地块提交格式错误 |
| INVALID_STATUS_TRANSITION | 409 | 状态流转非法 | 在错误阶段调用接口 |
| CASE_NOT_FOUND | 404 | 案例不存在 | 选择了无效 case_id |
| SELECTION_TOO_FEW | 422 | 案例选择不足 | 未选任何案例就推进 |
| OUTLINE_NOT_CONFIRMED | 409 | 大纲未确认 | 跳过大纲确认直接规划页面 |
| EXPORT_TYPE_UNSUPPORTED | 400 | 不支持的导出格式 | 传入 pptx 但尚未实现 |
| REPAIR_LIMIT_EXCEEDED | 409 | 修复次数超限 | 单页修复超过 3 次 |

### 5xx 系统侧错误

| 错误码 | HTTP 状态 | 含义 | 处理建议 |
|-------|---------|------|---------|
| LLM_PARSE_FAILED | 502 | LLM 输出解析失败 | 自动重试，超限后报告 |
| LLM_RATE_LIMITED | 503 | LLM API 限流 | 指数退避重试 |
| LLM_SERVICE_DOWN | 503 | LLM 服务不可用 | 降级或等待 |
| GEOCODE_FAILED | 502 | 地理编码失败 | 返回错误，让用户确认地址 |
| RENDER_TIMEOUT | 504 | 页面渲染超时 | 标记页面 failed，继续其他页 |
| ASSET_GENERATION_FAILED | 500 | 资产生成失败 | 跳过非关键资产 |
| OSS_UPLOAD_FAILED | 500 | 文件上传失败 | 重试 3 次后报告 |
| DB_WRITE_FAILED | 500 | 数据库写入失败 | 事务回滚，报告 |
| CELERY_TASK_LOST | 500 | Celery 任务丢失 | 重新入队 |

---

## 12.3 异常类定义

```python
# api/exceptions.py
from fastapi import HTTPException
from typing import Any, Optional


class AppError(Exception):
    """业务异常基类"""
    def __init__(
        self,
        error_code: str,
        message: str,
        http_status: int = 500,
        detail: Optional[dict] = None,
        retryable: bool = False,
    ):
        self.error_code = error_code
        self.message = message
        self.http_status = http_status
        self.detail = detail or {}
        self.retryable = retryable
        super().__init__(message)

    def to_http_exception(self) -> HTTPException:
        return HTTPException(
            status_code=self.http_status,
            detail={
                "success": False,
                "error": self.message,
                "error_code": self.error_code,
                "detail": self.detail,
            }
        )


# === 用户侧错误（4xx）===

class ProjectNotFoundError(AppError):
    def __init__(self, project_id: str):
        super().__init__(
            error_code="PROJECT_NOT_FOUND",
            message=f"项目 {project_id} 不存在",
            http_status=404,
        )

class BriefIncompleteError(AppError):
    def __init__(self, missing_fields: list[str]):
        super().__init__(
            error_code="BRIEF_INCOMPLETE",
            message="项目信息不完整，无法进入下一阶段",
            http_status=422,
            detail={"missing_fields": missing_fields},
        )

class InvalidStatusTransitionError(AppError):
    def __init__(self, current: str, target: str):
        super().__init__(
            error_code="INVALID_STATUS_TRANSITION",
            message=f"不能从 {current} 状态跳转到 {target}",
            http_status=409,
            detail={"current_status": current, "target_status": target},
        )

class RepairLimitExceededError(AppError):
    def __init__(self, slide_no: int, attempts: int):
        super().__init__(
            error_code="REPAIR_LIMIT_EXCEEDED",
            message=f"第 {slide_no} 页已修复 {attempts} 次，超出上限",
            http_status=409,
            detail={"slide_no": slide_no, "attempts": attempts},
        )


# === 系统侧错误（5xx）===

class LLMParseError(AppError):
    def __init__(self, raw_output: str = ""):
        super().__init__(
            error_code="LLM_PARSE_FAILED",
            message="LLM 输出解析失败",
            http_status=502,
            detail={"raw_output_preview": raw_output[:200]},
            retryable=True,
        )

class LLMRateLimitError(AppError):
    def __init__(self, retry_after: int = 60):
        super().__init__(
            error_code="LLM_RATE_LIMITED",
            message="LLM API 请求频率超限",
            http_status=503,
            detail={"retry_after_seconds": retry_after},
            retryable=True,
        )

class RenderTimeoutError(AppError):
    def __init__(self, slide_no: int):
        super().__init__(
            error_code="RENDER_TIMEOUT",
            message=f"第 {slide_no} 页渲染超时",
            http_status=504,
            detail={"slide_no": slide_no},
            retryable=True,
        )

class OSSUploadError(AppError):
    def __init__(self, filename: str):
        super().__init__(
            error_code="OSS_UPLOAD_FAILED",
            message=f"文件上传失败：{filename}",
            http_status=500,
            retryable=True,
        )
```

---

## 12.4 全局异常处理器

```python
# api/middleware.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from .exceptions import AppError
import logging

logger = logging.getLogger(__name__)


def setup_middleware(app: FastAPI):
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        logger.warning(
            f"AppError: {exc.error_code} | {exc.message} | "
            f"path={request.url.path} | retryable={exc.retryable}"
        )
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "success": False,
                "error": exc.message,
                "error_code": exc.error_code,
                "detail": exc.detail,
            }
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "服务内部错误",
                "error_code": "INTERNAL_ERROR",
                "detail": {},
            }
        )
```

---

## 12.5 前端错误处理约定

```typescript
// 前端统一错误处理示例（Next.js）
interface APIError {
  success: false;
  error: string;
  error_code: string;
  detail: Record<string, any>;
}

const ERROR_MESSAGES: Record<string, string> = {
  PROJECT_NOT_FOUND:          "项目不存在，请刷新页面",
  BRIEF_INCOMPLETE:           "请补充完整项目信息后再继续",
  INVALID_STATUS_TRANSITION:  "当前阶段不支持该操作",
  REPAIR_LIMIT_EXCEEDED:      "该页面修复次数已达上限，请人工处理",
  LLM_PARSE_FAILED:           "AI 处理异常，正在重试...",
  LLM_RATE_LIMITED:           "系统繁忙，请稍后重试",
  RENDER_TIMEOUT:             "页面渲染超时，已跳过该页",
};

function handleAPIError(error: APIError): string {
  return ERROR_MESSAGES[error.error_code] ?? error.error ?? "未知错误";
}
```
