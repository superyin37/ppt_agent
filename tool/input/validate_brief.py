from pydantic import BaseModel
from schema.project import ProjectBriefData


class ValidateBriefInput(BaseModel):
    brief: ProjectBriefData


class ValidateBriefOutput(BaseModel):
    is_valid: bool
    errors: list[str]
    warnings: list[str]


def validate_project_brief(input: ValidateBriefInput) -> ValidateBriefOutput:
    """
    纯本地校验项目信息完整性，无 LLM 调用。
    timeout: 1s
    """
    errors: list[str] = []
    warnings: list[str] = []
    data = input.brief

    if not data.building_type:
        errors.append("building_type 为必填项")
    if not data.client_name:
        errors.append("client_name 为必填项")
    if not data.site_address:
        errors.append("site_address 为必填项")

    # 指标三选二
    metric_count = sum([
        data.gross_floor_area is not None,
        data.site_area is not None,
        data.far is not None,
    ])
    if metric_count < 2:
        errors.append("建筑面积/用地面积/容积率至少需要填写两项")

    if data.gross_floor_area and data.gross_floor_area > 500_000:
        warnings.append("建筑面积超过50万㎡，请确认是否正确")

    if data.far and (data.far < 0.1 or data.far > 15):
        warnings.append(f"容积率 {data.far} 超出常规范围（0.1～15），请确认是否正确")

    return ValidateBriefOutput(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )
