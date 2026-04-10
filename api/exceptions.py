from fastapi import HTTPException
from typing import Optional


class AppError(Exception):
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


class CaseNotFoundError(AppError):
    def __init__(self, case_id: str):
        super().__init__(
            error_code="CASE_NOT_FOUND",
            message=f"案例 {case_id} 不存在",
            http_status=404,
        )


class SelectionTooFewError(AppError):
    def __init__(self):
        super().__init__(
            error_code="SELECTION_TOO_FEW",
            message="至少需要选择一个参考案例",
            http_status=422,
        )


class OutlineNotConfirmedError(AppError):
    def __init__(self):
        super().__init__(
            error_code="OUTLINE_NOT_CONFIRMED",
            message="大纲尚未确认，无法进入页面规划阶段",
            http_status=409,
        )


class RepairLimitExceededError(AppError):
    def __init__(self, slide_no: int, attempts: int):
        super().__init__(
            error_code="REPAIR_LIMIT_EXCEEDED",
            message=f"第 {slide_no} 页已修复 {attempts} 次，超出上限",
            http_status=409,
            detail={"slide_no": slide_no, "attempts": attempts},
        )


class InvalidGeoJSONError(AppError):
    def __init__(self, reason: str = ""):
        super().__init__(
            error_code="INVALID_GEOJSON",
            message=f"GeoJSON 格式非法: {reason}",
            http_status=422,
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


class GeocodeFailedError(AppError):
    def __init__(self, address: str):
        super().__init__(
            error_code="GEOCODE_FAILED",
            message=f"地址 '{address}' 地理编码失败",
            http_status=502,
        )
