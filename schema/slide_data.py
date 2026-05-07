"""SlideData — typed payload for each Jinja2 template component.

Composer's `template` mode produces one of these per slide. Pydantic enforces
the length / count constraints declared in `config.slide_data_limits.LIMITS`.

If validation fails, Composer retries once with the offending field lengths
echoed back into the prompt. If still failing, `truncate_to_schema` performs
a last-resort hard truncation.

The `SlideData` discriminated union (by `component_type`) lets us serialise to
`Slide.spec_json` without losing the variant.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union, Optional
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field, StringConstraints

from config.slide_data_limits import LIMITS as L


# ─────────────────────────────────────────────
# ComponentType enum — single source of truth
# ─────────────────────────────────────────────


class ComponentType(str, Enum):
    COVER = "cover"
    TOC = "toc"
    TRANSITION = "transition"
    POLICY_LIST = "policy_list"
    CHART = "chart"
    TABLE = "table"
    IMAGE_GRID = "image_grid"
    CONTENT_BULLETS = "content_bullets"
    CASE_CARD = "case_card"
    CONCEPT_SCHEME = "concept_scheme"
    ENDING = "ending"


# ─────────────────────────────────────────────
# Helper aliases for terse field declarations
# ─────────────────────────────────────────────


def _str(max_len: int, *, min_len: int = 0):
    return Annotated[str, StringConstraints(min_length=min_len, max_length=max_len)]


def _opt_str(max_len: int):
    return Annotated[Optional[str], StringConstraints(max_length=max_len)]


# ─────────────────────────────────────────────
# Sub-models shared between component data
# ─────────────────────────────────────────────


class MetaLine(BaseModel):
    label: _str(L["cover"]["meta_label"])
    value: _str(L["cover"]["meta_value"])


class CoverSignature(BaseModel):
    line1: _str(L["cover"]["signature_line1"])
    role: _opt_str(L["cover"]["signature_role"]) = None
    date: _opt_str(L["cover"]["signature_date"]) = None


class TocEntry(BaseModel):
    no: _str(L["toc"]["entry_no"])
    label: _str(L["toc"]["entry_label"])
    en: _str(L["toc"]["entry_en"])
    sub: _opt_str(L["toc"]["entry_sub"]) = None
    page_range: _opt_str(L["toc"]["entry_page_range"]) = None


class PolicyItem(BaseModel):
    title: _str(L["policy_list"]["policy_title"])
    publish_year: _opt_str(L["policy_list"]["policy_publish_year"]) = None
    content: _opt_str(L["policy_list"]["policy_content"]) = None
    impact: _opt_str(L["policy_list"]["policy_impact"]) = None
    source_url: _opt_str(L["policy_list"]["policy_source_url"]) = None


class GridImage(BaseModel):
    path: str  # asset id (UUID-as-str) or file path
    caption: _opt_str(L["image_grid"]["image_caption"]) = None


class Bullet(BaseModel):
    title: _opt_str(L["content_bullets"]["bullet_title"]) = None
    body: _str(L["content_bullets"]["bullet_body"])


class ChartSpec(BaseModel):
    """Subset of tool.asset.chart_generation.ChartGenerationInput.

    Composer outputs this when raw chart data is available; chart_materialize
    consumes it to produce a PNG and back-fills `ChartData.chart_path`.
    """

    chart_type: Literal["bar", "line", "pie", "radar"]
    chart_title: str = Field(max_length=64)
    data: list[dict]
    x_label: Optional[str] = None
    y_label: Optional[str] = None


# ─────────────────────────────────────────────
# Component data models (11 total)
# ─────────────────────────────────────────────


class CoverData(BaseModel):
    component_type: Literal[ComponentType.COVER] = ComponentType.COVER
    title: _str(L["cover"]["title"])
    slogan: _str(L["cover"]["slogan"])
    en: _str(L["cover"]["en"])
    meta_lines: list[MetaLine] = Field(
        default_factory=list, max_length=L["cover"]["meta_lines_max"]
    )
    logo: Optional[str] = None  # asset id or file path
    year: int = Field(ge=1900, le=2999)
    signature: Optional[CoverSignature] = None


class TocData(BaseModel):
    component_type: Literal[ComponentType.TOC] = ComponentType.TOC
    title: _str(L["toc"]["title"])
    entries: list[TocEntry] = Field(min_length=1, max_length=L["toc"]["entries_max"])
    illustration: Optional[str] = None  # asset id or file path


class TransitionData(BaseModel):
    component_type: Literal[ComponentType.TRANSITION] = ComponentType.TRANSITION
    title: _str(L["transition"]["title"])
    subtitle_en: _opt_str(L["transition"]["subtitle_en"]) = None
    sub: _opt_str(L["transition"]["sub"]) = None
    section_no: _str(L["transition"]["section_no"])


class PolicyListData(BaseModel):
    component_type: Literal[ComponentType.POLICY_LIST] = ComponentType.POLICY_LIST
    title: _str(L["policy_list"]["title"])
    policies: list[PolicyItem] = Field(
        default_factory=list, max_length=L["policy_list"]["policies_max"]
    )


class ChartData(BaseModel):
    component_type: Literal[ComponentType.CHART] = ComponentType.CHART
    title: _str(L["chart"]["title"])
    bullets: list[_str(L["chart"]["bullet"])] = Field(
        default_factory=list, max_length=L["chart"]["bullets_max"]
    )
    # OneOf — chart_path wins if both present; chart_materialize fills it from chart_spec.
    chart_path: Optional[str] = None
    chart_spec: Optional[ChartSpec] = None


class TableData(BaseModel):
    component_type: Literal[ComponentType.TABLE] = ComponentType.TABLE
    title: _str(L["table"]["title"])
    headers: list[_str(L["table"]["header_cell"])] = Field(
        default_factory=list, max_length=L["table"]["headers_max"]
    )
    rows: list[list[_str(L["table"]["body_cell"])]] = Field(
        default_factory=list, max_length=L["table"]["rows_max"]
    )
    note: _opt_str(L["table"]["note"]) = None


class ImageGridData(BaseModel):
    component_type: Literal[ComponentType.IMAGE_GRID] = ComponentType.IMAGE_GRID
    title: _str(L["image_grid"]["title"])
    images: list[GridImage] = Field(
        default_factory=list, max_length=L["image_grid"]["images_max"]
    )
    caption: _opt_str(L["image_grid"]["footer_caption"]) = None


class ContentBulletsData(BaseModel):
    component_type: Literal[ComponentType.CONTENT_BULLETS] = ComponentType.CONTENT_BULLETS
    title: _str(L["content_bullets"]["title"])
    lede: _opt_str(L["content_bullets"]["lede"]) = None
    bullets: list[Bullet] = Field(
        min_length=L["content_bullets"]["bullets_min"],
        max_length=L["content_bullets"]["bullets_max"],
    )
    illustration: Optional[str] = None


class CaseCardData(BaseModel):
    component_type: Literal[ComponentType.CASE_CARD] = ComponentType.CASE_CARD
    title: _str(L["case_card"]["title"])
    case_idx: int = Field(ge=0, le=20)
    case_name: _str(L["case_card"]["case_name"])
    thumbnail: Optional[str] = None
    scale: _opt_str(L["case_card"]["scale"]) = None
    highlights: _opt_str(L["case_card"]["highlights"]) = None
    inspiration: _opt_str(L["case_card"]["inspiration"]) = None


class ConceptSchemeData(BaseModel):
    component_type: Literal[ComponentType.CONCEPT_SCHEME] = ComponentType.CONCEPT_SCHEME
    scheme_idx: int = Field(ge=0, le=20)
    scheme_name: _str(L["concept_scheme"]["scheme_name"])
    view: Literal["aerial", "ext_perspective", "int_perspective"]
    view_label: _str(L["concept_scheme"]["view_label"])
    image: Optional[str] = None
    idea: _opt_str(L["concept_scheme"]["idea"]) = None
    analysis: _opt_str(L["concept_scheme"]["analysis"]) = None


class EndingData(BaseModel):
    component_type: Literal[ComponentType.ENDING] = ComponentType.ENDING
    title: _str(L["ending"]["title"])
    en: _str(L["ending"]["en"])
    tagline: _opt_str(L["ending"]["tagline"]) = None
    signature_parts: list[_str(L["ending"]["signature_part"])] = Field(
        default_factory=list, max_length=L["ending"]["signature_parts_max"]
    )


# ─────────────────────────────────────────────
# Discriminated union
# ─────────────────────────────────────────────


SlideData = Annotated[
    Union[
        CoverData,
        TocData,
        TransitionData,
        PolicyListData,
        ChartData,
        TableData,
        ImageGridData,
        ContentBulletsData,
        CaseCardData,
        ConceptSchemeData,
        EndingData,
    ],
    Field(discriminator="component_type"),
]


COMPONENT_SCHEMA: dict[ComponentType, type[BaseModel]] = {
    ComponentType.COVER: CoverData,
    ComponentType.TOC: TocData,
    ComponentType.TRANSITION: TransitionData,
    ComponentType.POLICY_LIST: PolicyListData,
    ComponentType.CHART: ChartData,
    ComponentType.TABLE: TableData,
    ComponentType.IMAGE_GRID: ImageGridData,
    ComponentType.CONTENT_BULLETS: ContentBulletsData,
    ComponentType.CASE_CARD: CaseCardData,
    ComponentType.CONCEPT_SCHEME: ConceptSchemeData,
    ComponentType.ENDING: EndingData,
}


# ─────────────────────────────────────────────
# Truncation fallback
# ─────────────────────────────────────────────


def truncate_to_schema(data: dict, schema_cls: type[BaseModel]) -> dict:
    """Hard-truncate `data` to fit `schema_cls` field constraints.

    Last resort after LLM retry fails. Walks fields, applies max_length to
    strings (with ellipsis suffix when truncated), max_length to lists, then
    recurses into nested BaseModel fields. Missing required fields are left
    alone — Pydantic will raise downstream and the slide will degrade.
    """
    if not isinstance(data, dict):
        return data

    out: dict = dict(data)
    for field_name, field_info in schema_cls.model_fields.items():
        if field_name not in out:
            continue
        value = out[field_name]
        out[field_name] = _truncate_field(value, field_info.metadata, field_info.annotation)
    return out


def _truncate_field(value, metadata, annotation):
    from typing import get_args, get_origin

    if value is None:
        return None

    str_max = _extract_max_len(metadata, str)
    if isinstance(value, str) and str_max is not None and len(value) > str_max:
        if str_max <= 1:
            return value[:str_max]
        return value[: str_max - 1] + "…"

    list_max = _extract_max_len(metadata, list)
    if isinstance(value, list) and list_max is not None and len(value) > list_max:
        value = value[:list_max]

    if isinstance(value, list):
        inner = _list_inner(annotation)
        if inner is not None:
            value = [_truncate_field(v, [], inner) for v in value]

    if isinstance(value, dict):
        nested_cls = _resolve_basemodel(annotation)
        if nested_cls is not None:
            value = truncate_to_schema(value, nested_cls)

    return value


def _extract_max_len(metadata, kind: type) -> Optional[int]:
    for m in metadata or []:
        max_len = getattr(m, "max_length", None)
        if max_len is None:
            continue
        if kind is str and isinstance(m, StringConstraints):
            return max_len
        if kind is list and not isinstance(m, StringConstraints):
            return max_len
    return None


def _list_inner(annotation):
    from typing import get_args, get_origin

    if get_origin(annotation) is list:
        args = get_args(annotation)
        return args[0] if args else None
    return None


def _resolve_basemodel(annotation) -> Optional[type[BaseModel]]:
    from typing import get_args, get_origin

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    for arg in get_args(annotation) or ():
        if isinstance(arg, type) and issubclass(arg, BaseModel):
            return arg
    return None
