from pydantic import Field
from typing import Optional
from uuid import UUID
from datetime import datetime
from .common import BaseSchema, ReviewSeverity, ReviewDecision


class ReviewIssue(BaseSchema):
    issue_id: str
    rule_code: str
    layer: str
    severity: ReviewSeverity
    message: str
    location: Optional[str] = None
    suggested_fix: str
    auto_fixable: bool = False


class RepairAction(BaseSchema):
    action_type: str
    target_block_id: Optional[str] = None
    params: dict = {}


class DesignDimension(BaseSchema):
    """单维度评分"""
    dimension: str          # "color" | "typography" | "layout" | "focal_point" | "polish"
    score: float            # 0.0 ~ 10.0
    comment: str            # 一句话评价


class DesignSuggestion(BaseSchema):
    """单条改善建议"""
    code: str               # "D001" ~ "D012"
    category: str           # "color" | "typography" | "layout" | "focal_point" | "polish"
    severity: str           # "critical" | "recommended" | "nice-to-have"
    message: str            # 人类可读描述
    css_hint: str = ""      # 可选：建议的 CSS 修改
    target_selector: str = ""  # 可选：目标 CSS 选择器


class DesignAdvice(BaseSchema):
    """设计顾问完整输出"""
    slide_no: int = 0
    dimensions: list[DesignDimension] = []
    overall_score: float = 0.0
    grade: str = "D"        # "A" | "B" | "C" | "D"
    suggestions: list[DesignSuggestion] = []
    one_liner: str = ""


class ReviewReport(BaseSchema):
    review_id: Optional[str] = None
    target_type: str
    target_id: UUID
    review_layer: str
    severity: ReviewSeverity
    issues: list[ReviewIssue] = []
    final_decision: ReviewDecision
    repair_plan: list[RepairAction] = []
    design_advice: Optional[DesignAdvice] = None


class ReviewRead(BaseSchema):
    id: UUID
    project_id: UUID
    target_type: str
    target_id: UUID
    review_layer: str
    severity: Optional[str] = None
    final_decision: Optional[str] = None
    issues_json: list[dict]
    repair_plan: Optional[dict] = None
    created_at: datetime
