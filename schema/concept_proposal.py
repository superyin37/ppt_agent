"""Concept proposal schema — 3 方案 × 3 视图的结构化描述。

由 Outline Agent 生成,供 Concept Render 阶段消费(见 ADR-005)。
"""
from __future__ import annotations

from enum import Enum
from pydantic import Field

from .common import BaseSchema


class ConceptViewKind(str, Enum):
    AERIAL = "aerial"
    EXT_PERSPECTIVE = "ext_perspective"
    INT_PERSPECTIVE = "int_perspective"


class ConceptProposal(BaseSchema):
    index: int = Field(ge=1, le=3, description="方案序号 1/2/3")
    name: str = Field(max_length=20, description="方案名称,如「云上之城」")
    design_idea: str = Field(max_length=30, description="一句设计理念 ≤20 字")
    narrative: str = Field(description="理念解析 100~150 字")
    design_keywords: list[str] = Field(
        default_factory=list,
        description="≤5 个关键词,中英文皆可,用于生图 prompt",
    )
    massing_hint: str = Field(description="体量描述,如 L 形退台 + 中庭")
    material_hint: str = Field(description="材质描述,如玻璃 + 素水泥 + 金属格栅")
    mood_hint: str = Field(description="氛围,如温润 / 冷峻 / 未来感")


def concept_logical_key(index: int, view: ConceptViewKind) -> str:
    """统一生成 Asset.logical_key,如 concept.1.aerial。"""
    return f"concept.{index}.{view.value}"
