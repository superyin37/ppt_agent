"""
Composer Agent v2/v3

v2: 将 OutlineSlideEntry 扩展为 LayoutSpec（布局原语 + 内容块绑定）。
v3: HTML 直出模式 — LLM 直接输出 HTML，由渲染引擎包装成完整页面。

需要 VisualTheme 作为视觉决策上下文。
"""
from __future__ import annotations

import enum
import json
import logging
import asyncio
import re
import hashlib
import html as html_lib
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from uuid import UUID
from urllib.parse import unquote, urlparse
from zipfile import ZipFile
from typing import Any, Optional, Union
from pydantic import BaseModel

from sqlalchemy.orm import Session

from config.llm import STRONG_MODEL, call_llm_with_limit
from config.settings import settings
from schema.visual_theme import (
    VisualTheme,
    LayoutSpec, ContentBlock, RegionBinding,
    FullBleedLayout, SplitHLayout, SplitVLayout,
    SingleColumnLayout, GridLayout, HeroStripLayout,
    SidebarLayout, TriptychLayout, OverlayMosaicLayout,
    TimelineLayout, AsymmetricLayout, AsymmetricRegion,
    LayoutPrimitive,
)
from schema.outline import OutlineSlideEntry, OutlineSpec
from schema.common import ProjectStatus, SlideStatus
from schema.concept_proposal import ConceptProposal, ConceptViewKind, concept_logical_key
from schema.page_slot import normalize_slot_id
from schema.slide_data import (
    ChartData,
    ContentBulletsData,
    CaseCardData,
    ComponentType,
    ConceptSchemeData,
    CoverData,
    EndingData,
    GridImage,
    ImageGridData,
    PolicyListData,
    TableData,
    TocData,
    TocEntry,
    TransitionData,
    truncate_to_schema,
)
from db.models.project import Project, ProjectBrief
from db.models.outline import Outline
from db.models.slide import Slide
from db.models.asset import Asset
from db.models.brief_doc import BriefDoc
from db.models.material_package import MaterialPackage
from db.models.slide_material_binding import SlideMaterialBinding
from agent.visual_theme import get_latest_theme

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "composer_system_v2.md"
_SYSTEM_PROMPT_V3_PATH = Path(__file__).parent.parent / "prompts" / "composer_system_v3.md"
_REPAIR_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "composer_repair.md"


class ComposerMode(str, enum.Enum):
    STRUCTURED = "structured"   # v2: 输出 LayoutSpec JSON
    HTML = "html"               # v3: 输出 body_html
    TEMPLATE = "template"       # v4: 输出 SlideData → Jinja2 渲染（ADR-006）


def resolve_composer_mode(mode: ComposerMode | str | None = None) -> ComposerMode:
    """Resolve configured Composer mode, defaulting to HTML for product flow."""
    raw = mode.value if isinstance(mode, ComposerMode) else (mode or settings.composer_mode)
    try:
        return ComposerMode(str(raw).lower())
    except ValueError:
        logger.warning("Unknown composer_mode '%s', falling back to html", raw)
        return ComposerMode.HTML


def _load_system_prompt() -> str:
    return _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def _load_system_prompt_v3() -> str:
    return _SYSTEM_PROMPT_V3_PATH.read_text(encoding="utf-8")


def _load_repair_prompt() -> str:
    return _REPAIR_PROMPT_PATH.read_text(encoding="utf-8")


# ─────────────────────────────────────────────
# LLM 中间输出格式
# ─────────────────────────────────────────────

class _BlockLLM(BaseModel):
    block_id: str
    content_type: str
    content: Union[str, list[str], None] = None
    emphasis: str = "normal"


class _RegionLLM(BaseModel):
    region_id: str
    blocks: list[_BlockLLM]


class _ComposerLLMOutput(BaseModel):
    slide_no: int
    section: str
    title: str
    is_cover: bool = False
    is_chapter_divider: bool = False
    primitive_type: str
    primitive_params: dict[str, Any]
    region_bindings: list[_RegionLLM]
    visual_focus: str


class _ComposerHTMLOutput(BaseModel):
    """v3 HTML 直出模式的 LLM 输出格式。"""
    slide_no: int
    body_html: str
    asset_refs: list[str] = []
    content_summary: str = ""


class _ComposerTemplateOutput(BaseModel):
    """v4 template-mode wrapper: marks the output as having gone through the
    SlideData/Jinja2 path. The `data` payload is the dict-serialised
    ComponentData and is what the renderer feeds to the Jinja2 template.
    """
    slide_no: int
    component_type: str          # ComponentType.value
    data: dict
    asset_refs: list[str] = []
    content_summary: str = ""


# ─────────────────────────────────────────────
# primitive_type + primitive_params → LayoutPrimitive
# ─────────────────────────────────────────────

_FALLBACK_PRIMITIVE = SingleColumnLayout(
    primitive="single-column", max_width_ratio=0.7, v_align="center", has_pull_quote=False,
)


def _build_primitive(primitive_type: str, params: dict) -> LayoutPrimitive:
    """将 LLM 输出的 primitive_type + params 转为 LayoutPrimitive 对象。失败时返回 single-column。"""
    builders = {
        "full-bleed":     lambda p: FullBleedLayout(primitive="full-bleed", **p),
        "split-h":        lambda p: SplitHLayout(primitive="split-h", **p),
        "split-v":        lambda p: SplitVLayout(primitive="split-v", **p),
        "single-column":  lambda p: SingleColumnLayout(primitive="single-column", **p),
        "grid":           lambda p: GridLayout(primitive="grid", **p),
        "hero-strip":     lambda p: HeroStripLayout(primitive="hero-strip", **p),
        "sidebar":        lambda p: SidebarLayout(primitive="sidebar", **p),
        "triptych":       lambda p: TriptychLayout(primitive="triptych", **p),
        "overlay-mosaic": lambda p: OverlayMosaicLayout(primitive="overlay-mosaic", **p),
        "timeline":       lambda p: TimelineLayout(primitive="timeline", **p),
        "asymmetric":     _build_asymmetric,
    }
    builder = builders.get(primitive_type)
    if not builder:
        logger.warning(f"Unknown primitive_type '{primitive_type}', using single-column")
        return _FALLBACK_PRIMITIVE
    try:
        return builder(params)
    except Exception as e:
        logger.warning(f"Failed to build primitive '{primitive_type}': {e}, using single-column")
        return _FALLBACK_PRIMITIVE


def _build_asymmetric(params: dict) -> AsymmetricLayout:
    regions_raw = params.get("regions", [])
    regions = []
    for r in regions_raw:
        try:
            regions.append(AsymmetricRegion(**r))
        except Exception:
            pass
    if not regions:
        raise ValueError("asymmetric requires at least one region")
    return AsymmetricLayout(primitive="asymmetric", regions=regions)


# ─────────────────────────────────────────────
# LLM 输出 → LayoutSpec
# ─────────────────────────────────────────────

def _llm_to_layout_spec(
    result: _ComposerLLMOutput,
    entry: OutlineSlideEntry,
    binding: Optional[SlideMaterialBinding] = None,
    bound_assets: Optional[list[dict]] = None,
) -> LayoutSpec:
    primitive = _build_primitive(result.primitive_type, result.primitive_params)

    region_bindings = []
    layout_source_refs: list[str] = []
    layout_evidence_refs: list[str] = list(binding.evidence_snippets or []) if binding else []
    for rb in result.region_bindings:
        blocks = []
        for b in rb.blocks:
            # content_type 校验
            valid_types = {
                "heading", "subheading", "body-text", "bullet-list",
                "kpi-value", "image", "chart", "map", "table",
                "quote", "caption", "label", "accent-element",
            }
            ct = b.content_type if b.content_type in valid_types else "body-text"
            em = b.emphasis if b.emphasis in {"normal", "highlight", "muted"} else "normal"
            blocks.append(ContentBlock(
                block_id=b.block_id,
                content_type=ct,
                content=b.content,
                emphasis=em,
                source_refs=[],
                evidence_refs=[],
            ))
        region_bindings.append(RegionBinding(region_id=rb.region_id, blocks=blocks))

    if binding and bound_assets:
        allowed_asset_ids = {asset["id"] for asset in bound_assets}
        allowed_source_refs = [f"asset:{asset_id}" for asset_id in allowed_asset_ids]
        updated_bindings = []
        for rb in region_bindings:
            new_blocks = []
            for block in rb.blocks:
                source_refs = list(block.source_refs)
                if isinstance(block.content, str) and block.content.startswith("asset:") and block.content.removeprefix("asset:") in allowed_asset_ids:
                    source_refs.append(block.content)
                elif block.content_type in {"image", "chart", "map", "table"} and allowed_source_refs:
                    block = block.model_copy(update={"content": allowed_source_refs[0]})
                    source_refs.append(allowed_source_refs[0])
                source_refs = list(dict.fromkeys(source_refs))
                layout_source_refs.extend(source_refs)
                new_blocks.append(block.model_copy(update={
                    "source_refs": source_refs,
                    "evidence_refs": layout_evidence_refs,
                }))
            updated_bindings.append(rb.model_copy(update={"blocks": new_blocks}))
        region_bindings = updated_bindings

    return LayoutSpec(
        slide_no=result.slide_no,
        primitive=primitive,
        region_bindings=region_bindings,
        visual_focus=result.visual_focus or "content",
        is_cover=result.is_cover,
        is_chapter_divider=result.is_chapter_divider,
        section=result.section,
        title=result.title,
        slot_id=entry.slot_id,
        binding_id=str(binding.id) if binding else "",
        source_refs=list(dict.fromkeys(layout_source_refs)),
        evidence_refs=layout_evidence_refs,
    )


# ─────────────────────────────────────────────
# 兜底 LayoutSpec（LLM 失败时使用）
# ─────────────────────────────────────────────

def _fallback_layout_spec(
    entry: OutlineSlideEntry,
    binding: Optional[SlideMaterialBinding] = None,
    bound_assets: Optional[list[dict]] = None,
) -> LayoutSpec:
    """最小化 LayoutSpec，确保渲染不崩溃。"""
    is_cover = entry.is_cover or entry.slide_no == 1
    is_divider = entry.is_chapter_divider

    if is_cover:
        primitive = FullBleedLayout(
            primitive="full-bleed", content_anchor="bottom-left",
            use_overlay=True, overlay_direction="bottom", background_type="gradient",
        )
        blocks = [
            ContentBlock(block_id="title", content_type="heading", content=entry.title),
            ContentBlock(block_id="msg", content_type="subheading", content=entry.key_message),
        ]
    elif is_divider:
        primitive = FullBleedLayout(
            primitive="full-bleed", content_anchor="center",
            use_overlay=False, background_type="color",
        )
        blocks = [
            ContentBlock(block_id="title", content_type="heading", content=entry.title),
            ContentBlock(block_id="subtitle", content_type="subheading", content=entry.section),
        ]
    else:
        media_asset = None
        if bound_assets:
            media_asset = next((asset for asset in bound_assets if asset["type"] in {"image", "chart", "map", "case_card", "kpi_table"} and asset.get("asset_ref")), None)
        evidence_refs = list(binding.evidence_snippets or []) if binding else []
        source_ref = media_asset["asset_ref"] if media_asset else ""
        if media_asset:
            primitive = SplitHLayout(
                primitive="split-h",
                left_ratio=5,
                right_ratio=5,
                left_content_type="text",
                right_content_type="image" if media_asset["type"] in {"image", "case_card", "map"} else ("chart" if media_asset["type"] == "chart" else "text"),
                divider="gap",
                dominant_side="right",
            )
            blocks = [
                ContentBlock(block_id="title", content_type="heading", content=entry.title, evidence_refs=evidence_refs),
                ContentBlock(block_id="body", content_type="body-text", content=entry.key_message, evidence_refs=evidence_refs),
            ]
            media_block = ContentBlock(
                block_id="visual",
                content_type="chart" if media_asset["type"] == "chart" else ("map" if media_asset["type"] == "map" else ("table" if media_asset["type"] == "kpi_table" else "image")),
                content=source_ref,
                source_refs=[source_ref] if source_ref else [],
                evidence_refs=evidence_refs,
            )
            return LayoutSpec(
                slide_no=entry.slide_no,
                primitive=primitive,
                region_bindings=[
                    RegionBinding(region_id="left", blocks=blocks),
                    RegionBinding(region_id="right", blocks=[media_block]),
                ],
                visual_focus="right",
                is_cover=is_cover,
                is_chapter_divider=is_divider,
                section=entry.section,
                title=entry.title,
                slot_id=entry.slot_id,
                binding_id=str(binding.id) if binding else "",
                source_refs=[source_ref] if source_ref else [],
                evidence_refs=evidence_refs,
            )
        primitive = SingleColumnLayout(
            primitive="single-column", max_width_ratio=0.72, v_align="top", has_pull_quote=False,
        )
        blocks = [
            ContentBlock(block_id="title", content_type="heading", content=entry.title, evidence_refs=evidence_refs if binding else []),
            ContentBlock(block_id="body", content_type="body-text", content=entry.key_message, evidence_refs=evidence_refs if binding else []),
        ]

    return LayoutSpec(
        slide_no=entry.slide_no,
        primitive=primitive,
        region_bindings=[RegionBinding(region_id="content", blocks=blocks)],
        visual_focus="content",
        is_cover=is_cover,
        is_chapter_divider=is_divider,
        section=entry.section,
        title=entry.title,
        slot_id=entry.slot_id,
        binding_id=str(binding.id) if binding else "",
        source_refs=[asset["asset_ref"] for asset in (bound_assets or []) if asset.get("asset_ref")],
        evidence_refs=list(binding.evidence_snippets or []) if binding else [],
    )


# ─────────────────────────────────────────────
# 单页合成（v2 结构化模式）
# ─────────────────────────────────────────────

def _build_user_message(
    entry: OutlineSlideEntry,
    theme: VisualTheme,
    brief_dict: dict,
    asset_summary: list[dict],
    binding: Optional[SlideMaterialBinding] = None,
) -> str:
    """构建 composer 的 user message（两种模式共用大部分上下文）。"""
    theme_context = {
        "style_keywords": theme.style_keywords,
        "color_mode": getattr(theme, "color_mode", "mixed"),
        "contrast_level": getattr(theme, "contrast_level", "high"),
        "accent_saturation": getattr(theme, "accent_saturation", "high"),
        "font_mood": getattr(theme, "font_mood", "modern"),
        "visual_intensity": getattr(theme, "visual_intensity", "bold"),
        "color_strategy": getattr(theme, "color_strategy", "high-contrast"),
        "composition_style": getattr(theme, "composition_style", "editorial"),
        "decorative_motif": getattr(theme, "decorative_motif", "architectural-lines"),
        "cover_layout_mood": theme.cover.layout_mood,
        "density": theme.spacing.density,
        "color_fill_usage": theme.decoration.color_fill_usage,
        "generation_hint": theme.generation_prompt_hint,
    }
    return (
        f"<visual_theme>\n{json.dumps(theme_context, ensure_ascii=False)}\n</visual_theme>\n\n"
        f"<outline_entry>\n{entry.model_dump_json(indent=2)}\n</outline_entry>\n\n"
        f"<project_brief>\n{json.dumps(brief_dict, ensure_ascii=False)}\n</project_brief>\n\n"
        f"<slide_material_binding>\n{json.dumps({'binding_id': str(binding.id) if binding else '', 'derived_asset_ids': binding.derived_asset_ids if binding else [], 'evidence_snippets': binding.evidence_snippets if binding else [], 'missing_requirements': binding.missing_requirements if binding else []}, ensure_ascii=False, indent=2)}\n</slide_material_binding>\n\n"
        f"<available_assets>\n{json.dumps(asset_summary[:20], ensure_ascii=False, indent=2)}\n</available_assets>\n\n"
    )


async def _compose_slide_structured(
    entry: OutlineSlideEntry,
    theme: VisualTheme,
    brief_dict: dict,
    asset_summary: list[dict],
    binding: Optional[SlideMaterialBinding] = None,
) -> LayoutSpec:
    """v2 结构化模式：输出 LayoutSpec。"""
    user_message = _build_user_message(entry, theme, brief_dict, asset_summary, binding)
    user_message += "请为此页面生成完整的 LayoutSpec JSON。"

    try:
        result = await call_llm_with_limit(
            system_prompt=_load_system_prompt(),
            user_message=user_message,
            output_schema=_ComposerLLMOutput,
            model=STRONG_MODEL,
            temperature=0.3,
            max_tokens=1500,
        )
        return _llm_to_layout_spec(result, entry=entry, binding=binding, bound_assets=asset_summary)
    except Exception as e:
        logger.warning(f"Composer LLM (structured) failed for slide {entry.slide_no}: {e}")
        return _fallback_layout_spec(entry, binding=binding, bound_assets=asset_summary)


# ─────────────────────────────────────────────
# 单页合成（v3 HTML 直出模式）
# ─────────────────────────────────────────────

async def _compose_slide_html(
    entry: OutlineSlideEntry,
    theme: VisualTheme,
    brief_dict: dict,
    asset_summary: list[dict],
    binding: Optional[SlideMaterialBinding] = None,
) -> _ComposerHTMLOutput:
    """v3 HTML 直出模式：LLM 输出 body_html。"""
    user_message = _build_user_message(entry, theme, brief_dict, asset_summary, binding)
    user_message += "请为此页面设计 HTML 幻灯片。"

    result = await call_llm_with_limit(
        system_prompt=_load_system_prompt_v3(),
        user_message=user_message,
        output_schema=_ComposerHTMLOutput,
        model=STRONG_MODEL,
        temperature=0.5,
        max_tokens=4000,
    )
    return result


async def recompose_slide_html(
    original_html: str,
    issues: list[dict],
    entry: OutlineSlideEntry,
    theme: VisualTheme,
    brief_dict: dict,
) -> _ComposerHTMLOutput:
    """根据 review feedback 重写 HTML slide（专用 repair prompt，最小改动）。"""
    issues_text = "\n".join(
        f"- [{iss.get('rule_code')}] {iss.get('message')}" for iss in issues
    )
    theme_context = {
        "style_keywords": theme.style_keywords,
        "color_mode": getattr(theme, "color_mode", "mixed"),
        "contrast_level": getattr(theme, "contrast_level", "high"),
        "accent_saturation": getattr(theme, "accent_saturation", "high"),
        "font_mood": getattr(theme, "font_mood", "modern"),
        "visual_intensity": getattr(theme, "visual_intensity", "bold"),
        "color_strategy": getattr(theme, "color_strategy", "high-contrast"),
        "composition_style": getattr(theme, "composition_style", "editorial"),
        "decorative_motif": getattr(theme, "decorative_motif", "architectural-lines"),
        "density": theme.spacing.density,
        "color_fill_usage": theme.decoration.color_fill_usage,
        "generation_hint": theme.generation_prompt_hint,
    }
    user_message = (
        f"<original_html>\n{original_html}\n</original_html>\n\n"
        f"<review_issues>\n{issues_text}\n</review_issues>\n\n"
        f"<outline_entry>\n{entry.model_dump_json(indent=2)}\n</outline_entry>\n\n"
        f"<visual_theme>\n{json.dumps(theme_context, ensure_ascii=False)}\n</visual_theme>\n\n"
        f"<project_brief>\n{json.dumps(brief_dict, ensure_ascii=False)}\n</project_brief>\n\n"
        f"请根据审查反馈修改 HTML。若问题来自视觉焦点、完成度、图文比例、空白浪费或重点页冲击力不足，可以进行结构性增强；必须保留事实、数字和素材引用。"
    )
    return await call_llm_with_limit(
        system_prompt=_load_repair_prompt(),
        user_message=user_message,
        output_schema=_ComposerHTMLOutput,
        model=STRONG_MODEL,
        temperature=0.3,
        max_tokens=8000,
    )


def _html_fallback(entry: OutlineSlideEntry) -> _ComposerHTMLOutput:
    """HTML 模式的兜底输出。"""
    is_cover = entry.is_cover or entry.slide_no == 1
    title = html_lib.escape(entry.title or "内容待补充")
    fallback_message = html_lib.escape(_safe_entry_message(entry) or "本页所需资料尚未完成结构化绑定。")
    if is_cover:
        html = f"""<div class="slide-root" style="background:var(--color-cover-bg);display:flex;align-items:center;justify-content:center;flex-direction:column;padding:var(--safe-margin);">
  <h1 style="font-family:var(--font-heading);font-size:var(--text-display);color:#fff;text-align:center;">{title}</h1>
  <p style="font-family:var(--font-body);font-size:var(--text-h2);color:rgba(255,255,255,0.8);margin-top:var(--element-gap);">{fallback_message}</p>
</div>"""
    elif entry.is_chapter_divider:
        html = f"""<div class="slide-root" style="background:var(--color-primary);display:flex;align-items:center;justify-content:center;flex-direction:column;">
  <h1 style="font-family:var(--font-heading);font-size:var(--text-display);color:#fff;">{title}</h1>
  <p style="font-family:var(--font-en);font-size:var(--text-h3);color:rgba(255,255,255,0.6);margin-top:var(--element-gap);">{html_lib.escape(entry.section or '')}</p>
</div>"""
    else:
        html = f"""<div class="slide-root" style="padding:var(--safe-margin);display:flex;flex-direction:column;justify-content:center;">
  <h2 style="font-family:var(--font-heading);font-size:var(--text-h1);color:var(--color-text-primary);margin-bottom:var(--section-gap);">{title}</h2>
  <p style="font-family:var(--font-body);font-size:var(--text-h2);color:var(--color-text-secondary);line-height:1.45;">{fallback_message}</p>
</div>"""
    return _ComposerHTMLOutput(
        slide_no=entry.slide_no,
        body_html=html,
        asset_refs=[],
        content_summary=f"Fallback: {entry.title}",
    )


async def _compose_slide_template(
    entry: OutlineSlideEntry,
    theme: VisualTheme,
    brief_dict: dict,
    asset_summary: list[dict],
    binding: Optional[SlideMaterialBinding] = None,
    *,
    project_id: Optional[UUID] = None,
    db: Optional[Session] = None,
    outline_spec: Optional[OutlineSpec] = None,
    outline_json: Optional[dict] = None,
) -> Optional[_ComposerTemplateOutput]:
    """v4 template mode: produce SlideData JSON for Jinja2 rendering.

    Returns None when the slot has no template_component (caller should fall
    back to v3 HTML mode for this slide). Raises on unrecoverable failure
    so the caller can decide how to degrade.
    """
    from agent.composer_template import compose_template_slide, TemplateModeError
    from agent.slide_plan import _component_for_slot

    component_type = _component_for_slot(entry.slot_id)
    if component_type is None:
        return None

    deterministic = _compose_deterministic_template_data(
        entry=entry,
        component_type=component_type,
        brief_dict=brief_dict,
        asset_summary=asset_summary,
        binding=binding,
        project_id=project_id,
        db=db,
        outline_spec=outline_spec,
        outline_json=outline_json,
    )
    if deterministic is not None:
        slide_data, asset_refs = deterministic
        return _ComposerTemplateOutput(
            slide_no=entry.slide_no,
            component_type=component_type.value,
            data=slide_data.model_dump(mode="json"),
            asset_refs=asset_refs,
            content_summary=f"Template[{component_type.value}]: {entry.title}",
        )

    try:
        slide_data = await compose_template_slide(
            entry=entry,
            component_type=component_type,
            theme=theme,
            brief_dict=brief_dict,
            asset_summary=asset_summary,
            binding=binding,
        )
        slide_data = _postprocess_template_data(entry=entry, slide_data=slide_data)
    except TemplateModeError:
        return None  # caller falls back to html_free

    asset_refs = [a["asset_ref"] for a in asset_summary if a.get("asset_ref")]
    return _ComposerTemplateOutput(
        slide_no=entry.slide_no,
        component_type=component_type.value,
        data=slide_data.model_dump(mode="json"),
        asset_refs=asset_refs,
        content_summary=f"Template[{component_type.value}]: {entry.title}",
    )


def _compose_deterministic_template_data(
    *,
    entry: OutlineSlideEntry,
    component_type: ComponentType,
    brief_dict: dict,
    asset_summary: list[dict],
    binding: Optional[SlideMaterialBinding],
    project_id: Optional[UUID],
    db: Optional[Session],
    outline_spec: Optional[OutlineSpec],
    outline_json: Optional[dict],
) -> Optional[tuple[BaseModel, list[str]]]:
    """Return template data for slots whose payload is already deterministic.

    PR-3 starts with `concept-aerial`: concept_render has already persisted
    `concept.{N}.aerial` assets, and the Outline carries the matching
    ConceptProposal text. Using those directly avoids another LLM call and
    keeps image/proposal ordering stable.
    """
    if component_type == ComponentType.TRANSITION:
        return _compose_transition_data(entry=entry, outline_spec=outline_spec)

    if component_type == ComponentType.TOC:
        return _compose_toc_data(outline_spec=outline_spec)

    if component_type == ComponentType.COVER:
        return _compose_cover_data(
            entry=entry,
            brief_dict=brief_dict,
            outline_spec=outline_spec,
        )

    if component_type == ComponentType.ENDING:
        return _compose_ending_data(entry=entry, brief_dict=brief_dict)

    if component_type == ComponentType.IMAGE_GRID:
        return _compose_image_grid_data(
            entry=entry,
            asset_summary=asset_summary,
            binding=binding,
        )

    if component_type == ComponentType.CASE_CARD:
        return _compose_case_card_data(
            entry=entry,
            project_id=project_id,
            db=db,
            outline_spec=outline_spec,
        )

    if component_type == ComponentType.POLICY_LIST:
        return _compose_policy_list_data(
            entry=entry,
            brief_dict=brief_dict,
            asset_summary=asset_summary,
            binding=binding,
        )

    if component_type == ComponentType.TABLE:
        return _compose_table_data(
            entry=entry,
            brief_dict=brief_dict,
            asset_summary=asset_summary,
            binding=binding,
            outline_spec=outline_spec,
            outline_json=outline_json or {},
        )

    if component_type == ComponentType.CHART:
        return _compose_chart_data(
            entry=entry,
            asset_summary=asset_summary,
            binding=binding,
        )

    if component_type == ComponentType.CONTENT_BULLETS:
        return _compose_content_bullets_data(
            entry=entry,
            brief_dict=brief_dict,
            asset_summary=asset_summary,
            binding=binding,
            outline_spec=outline_spec,
            outline_json=outline_json or {},
        )

    if component_type != ComponentType.CONCEPT_SCHEME:
        return None
    if normalize_slot_id(entry.slot_id) != "concept-aerial":
        return None
    if project_id is None or db is None or outline_spec is None:
        return None

    proposal = _concept_proposal_for_entry(entry, outline_spec, outline_json or {})
    if proposal is None:
        logger.warning("concept-aerial slide %s has no matching proposal", entry.slide_no)
        return None

    asset = _find_concept_asset(
        db=db,
        project_id=project_id,
        proposal_index=proposal.index,
        view=ConceptViewKind.AERIAL,
    )
    if asset is None:
        logger.warning(
            "concept-aerial slide %s missing asset %s",
            entry.slide_no,
            concept_logical_key(proposal.index, ConceptViewKind.AERIAL),
        )
        return None

    raw_data = {
        "component_type": ComponentType.CONCEPT_SCHEME.value,
        "scheme_idx": proposal.index - 1,
        "scheme_name": proposal.name,
        "view": ConceptViewKind.AERIAL.value,
        "view_label": "AERIAL VIEW",
        "image": str(asset.id),
        "idea": proposal.design_idea,
        "analysis": proposal.narrative,
    }
    try:
        data = ConceptSchemeData.model_validate(raw_data)
    except Exception:
        data = ConceptSchemeData.model_validate(truncate_to_schema(raw_data, ConceptSchemeData))
    return data, [f"asset:{asset.id}"]


def _assets_for_entry(
    *,
    entry: OutlineSlideEntry,
    all_asset_summary: list[dict],
    binding: Optional[SlideMaterialBinding],
) -> list[dict]:
    """Return assets visible to a slide composer.

    Bindings can be intentionally broad or empty in smoke/mock runs. Template
    mode still needs deterministic access to canonical material keys, otherwise
    it falls back to outline task text. This helper keeps the normal binding
    scope, then adds slot-specific evidence assets by logical_key.
    """
    selected: list[dict] = []
    bound_ids = set(binding.derived_asset_ids or []) if binding else set()
    if bound_ids:
        selected.extend(asset for asset in all_asset_summary if asset["id"] in bound_ids)

    slot_id = entry.slot_id or normalize_slot_id(entry.slot_id)
    supplemental_tokens = _supplemental_asset_tokens(slot_id)
    supplemental_assets: list[dict] = []
    if supplemental_tokens:
        for asset in all_asset_summary:
            logical_key = str(asset.get("logical_key") or "").lower()
            haystack = " ".join(str(asset.get(k) or "") for k in ("logical_key", "title")).lower()
            if any(token in logical_key or token in haystack for token in supplemental_tokens):
                supplemental_assets.append(asset)

    if supplemental_assets and _prefer_supplemental_assets(slot_id):
        selected = supplemental_assets
    else:
        selected.extend(supplemental_assets)

    if not selected and binding is None:
        selected = list(all_asset_summary)

    return _dedupe_assets(selected)


def _supplemental_asset_tokens(slot_id: str) -> tuple[str, ...]:
    if slot_id.startswith("policy") or slot_id == "upper-planning":
        return ("brief.design_outline", "政策", "规划", "公厕", "cjj14")
    if slot_id in {
        "cultural-analysis",
        "site-summary",
        "project-positioning",
        "design-strategies",
        "design-brief-doc",
    }:
        return ("brief.design_outline", "设计建议书大纲")
    if slot_id == "economic-1":
        return ("economy.city", "城市经济")
    if slot_id == "economic-2":
        return ("economy.industry", "产业发展")
    if slot_id == "economic-3":
        return ("economy.consumption", "消费", "民生")
    if slot_id == "transport-map":
        return ("site.transport", "site.infrastructure", "交通", "基础设施")
    if slot_id == "site-location-1":
        return ("site.boundary", "场地四至")
    if slot_id == "site-location-2":
        return ("site.transport.external", "site.transport.station", "外部交通")
    if slot_id == "site-location-3":
        return ("site.transport.hub", "枢纽站点", "site.infrastructure")
    if slot_id == "site-location-4":
        return ("site.development", "site.infrastructure", "区域开发")
    if slot_id == "poi-analysis":
        return ("site.poi", "场地poi", "poi")
    return ()


def _prefer_supplemental_assets(slot_id: str) -> bool:
    return (
        slot_id.startswith("economic-")
        or slot_id.startswith("site-location-")
        or slot_id == "transport-map"
        or slot_id == "poi-analysis"
    )


def _dedupe_assets(assets: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for asset in assets:
        asset_id = str(asset.get("id") or "")
        if not asset_id or asset_id in seen:
            continue
        seen.add(asset_id)
        out.append(asset)
    return out


def _postprocess_template_data(
    *,
    entry: OutlineSlideEntry,
    slide_data: BaseModel,
) -> BaseModel:
    if isinstance(slide_data, ChartData):
        return _materialize_chart_spec_if_needed(entry=entry, data=slide_data)
    return slide_data


def _compose_transition_data(
    *,
    entry: OutlineSlideEntry,
    outline_spec: Optional[OutlineSpec],
) -> Optional[tuple[TransitionData, list[str]]]:
    section_no = _section_no_for_entry(entry, outline_spec)
    raw_data = {
        "component_type": ComponentType.TRANSITION.value,
        "title": entry.title or entry.section or "章节",
        "subtitle_en": _section_en(entry.section),
        "sub": None,
        "section_no": f"{section_no:02d}",
    }
    try:
        data = TransitionData.model_validate(raw_data)
    except Exception:
        data = TransitionData.model_validate(truncate_to_schema(raw_data, TransitionData))
    return data, []


def _compose_toc_data(
    *,
    outline_spec: Optional[OutlineSpec],
) -> Optional[tuple[TocData, list[str]]]:
    if outline_spec is None:
        return None

    slides = sorted(outline_spec.slides, key=lambda s: s.slide_no)
    chapter_slides = [
        slide for slide in slides
        if re.search(r"chapter-\d+-divider", slide.slot_id or "")
    ]
    if not chapter_slides:
        return None

    entries: list[dict] = []
    for idx, chapter in enumerate(chapter_slides, start=1):
        next_chapter = chapter_slides[idx] if idx < len(chapter_slides) else None
        start = chapter.slide_no
        end = (next_chapter.slide_no - 1) if next_chapter else _last_content_page(slides)
        entries.append({
            "no": f"{idx:02d}",
            "label": chapter.title or chapter.section or f"章节 {idx}",
            "en": _section_en(chapter.section),
            "sub": None,
            "page_range": f"{start:02d}-{end:02d}" if end > start else f"{start:02d}",
        })

    raw_data = {
        "component_type": ComponentType.TOC.value,
        "title": "目录",
        "entries": entries,
        "illustration": None,
    }
    try:
        data = TocData.model_validate(raw_data)
    except Exception:
        data = TocData.model_validate(truncate_to_schema(raw_data, TocData))
    return data, []


def _compose_cover_data(
    *,
    entry: OutlineSlideEntry,
    brief_dict: dict,
    outline_spec: Optional[OutlineSpec],
) -> Optional[tuple[CoverData, list[str]]]:
    title = _cover_title(entry=entry, outline_spec=outline_spec)
    client = brief_dict.get("client_name") or "PPT Agent"
    raw_data = {
        "component_type": ComponentType.COVER.value,
        "title": title,
        "slogan": f"{entry.title or '建筑方案'} · 建筑方案汇报",
        "en": "ARCHITECTURAL PROPOSAL",
        "meta_lines": _cover_meta_lines(brief_dict),
        "logo": None,
        "year": datetime.now().year,
        "signature": {
            "line1": str(client),
            "role": "委托方" if brief_dict.get("client_name") else "PRESENTED BY",
            "date": str(datetime.now().year),
        },
    }
    try:
        data = CoverData.model_validate(raw_data)
    except Exception:
        data = CoverData.model_validate(truncate_to_schema(raw_data, CoverData))
    return data, []


def _cover_title(
    *,
    entry: OutlineSlideEntry,
    outline_spec: Optional[OutlineSpec],
) -> str:
    deck_title = (outline_spec.deck_title if outline_spec else "") or ""
    for suffix in ("建筑方案汇报", "方案汇报", "设计建议书", "设计方案"):
        if suffix in deck_title:
            return deck_title.split(suffix, 1)[0].strip(" ·-—")
    match = re.search(r"项目名称['\"“”‘’]?([^'\"“”‘’，,。]+)", entry.key_message or "")
    if match:
        return match.group(1).strip()
    return entry.title or deck_title or "建筑方案"


def _cover_meta_lines(brief_dict: dict) -> list[dict]:
    lines: list[dict] = []
    location = _project_location(brief_dict)
    if location:
        lines.append({"label": "项目地点", "value": location})

    building_type = brief_dict.get("building_type")
    if building_type:
        lines.append({"label": "建筑类型", "value": _display_building_type(str(building_type))})

    gross_floor_area = brief_dict.get("gross_floor_area")
    if gross_floor_area:
        lines.append({"label": "建筑面积", "value": _format_area(gross_floor_area)})

    far = brief_dict.get("far")
    if far and len(lines) < 3:
        lines.append({"label": "容积率", "value": str(far)})

    client = brief_dict.get("client_name")
    if client and len(lines) < 3:
        lines.append({"label": "委托方", "value": str(client)})

    return lines[:3]


def _project_location(brief_dict: dict) -> str:
    site_address = brief_dict.get("site_address")
    if site_address and _looks_like_site_address(str(site_address)):
        return str(site_address)
    parts = [
        brief_dict.get("province"),
        brief_dict.get("city"),
        brief_dict.get("district"),
    ]
    return "".join(str(p) for p in parts if p)


def _looks_like_site_address(value: str) -> bool:
    if not value or len(value) > 28:
        return False
    bad_tokens = ("方案", "大纲", "汇报", "建议书", "PPT")
    return not any(token in value for token in bad_tokens)


def _display_building_type(value: str) -> str:
    mapping = {
        "museum": "博物馆",
        "office": "办公建筑",
        "residential": "居住建筑",
        "mixed": "综合体",
        "hotel": "酒店",
        "commercial": "商业建筑",
        "cultural": "文化建筑",
        "education": "教育建筑",
    }
    return mapping.get(value, value)


def _format_area(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return f"{int(number)} m²"
    return f"{number:g} m²"


def _compose_ending_data(
    *,
    entry: OutlineSlideEntry,
    brief_dict: dict,
) -> Optional[tuple[EndingData, list[str]]]:
    client = brief_dict.get("client_name") or brief_dict.get("building_type") or "PROJECT"
    raw_data = {
        "component_type": ComponentType.ENDING.value,
        "title": "谢谢",
        "en": "THANK YOU",
        "tagline": "Thank you for your attention.",
        "signature_parts": [
            str(client),
            "PPT AGENT",
            str(datetime.now().year),
        ],
    }
    try:
        data = EndingData.model_validate(raw_data)
    except Exception:
        data = EndingData.model_validate(truncate_to_schema(raw_data, EndingData))
    return data, []


def _last_content_page(slides: list[OutlineSlideEntry]) -> int:
    for slide in reversed(slides):
        if normalize_slot_id(slide.slot_id) not in {"closing"} and slide.section != "结尾":
            return slide.slide_no
    return slides[-1].slide_no if slides else 1


def _compose_image_grid_data(
    *,
    entry: OutlineSlideEntry,
    asset_summary: list[dict],
    binding: Optional[SlideMaterialBinding],
) -> Optional[tuple[ImageGridData, list[str]]]:
    # Without a binding, `asset_summary` may contain every project asset; avoid
    # accidentally building a noisy grid from unrelated materials.
    if binding is None or not (binding.derived_asset_ids or []):
        return None

    usable_assets = _select_image_grid_assets(
        slot_id=entry.slot_id or normalize_slot_id(entry.slot_id),
        asset_summary=asset_summary,
    )
    if not usable_assets:
        return None

    raw_data = {
        "component_type": ComponentType.IMAGE_GRID.value,
        "title": entry.title,
        "images": [
            {
                "path": asset["id"],
                "caption": _asset_caption(asset),
            }
            for asset in usable_assets
        ],
        "caption": _join_snippets(binding.evidence_snippets or [], max_chars=120),
    }
    try:
        data = ImageGridData.model_validate(raw_data)
    except Exception:
        data = ImageGridData.model_validate(truncate_to_schema(raw_data, ImageGridData))
    return data, [asset["asset_ref"] for asset in usable_assets if asset.get("asset_ref")]


def _select_image_grid_assets(slot_id: str, asset_summary: list[dict]) -> list[dict]:
    visual_assets = [asset for asset in asset_summary if _asset_is_visual(asset)]
    if not visual_assets:
        return []

    token_groups = _image_grid_token_groups(slot_id)
    if not token_groups:
        return visual_assets[:4]

    if len(token_groups) == 1:
        matched = _assets_matching_tokens(visual_assets, token_groups[0])
        if matched:
            return matched[:4]

    selected: list[dict] = []
    for tokens in token_groups:
        match = _best_asset_for_tokens(visual_assets, tokens, exclude={str(a.get("id")) for a in selected})
        if match is not None:
            selected.append(match)

    if len(selected) < min(2, len(visual_assets)):
        for asset in visual_assets:
            if str(asset.get("id")) not in {str(a.get("id")) for a in selected}:
                selected.append(asset)
            if len(selected) >= 4:
                break
    return selected[:4]


def _assets_matching_tokens(assets: list[dict], tokens: tuple[str, ...]) -> list[dict]:
    out: list[dict] = []
    for asset in assets:
        haystack = " ".join(str(asset.get(k) or "") for k in ("logical_key", "title", "summary")).lower()
        if any(token.lower() in haystack for token in tokens):
            out.append(asset)
    return out


def _image_grid_token_groups(slot_id: str) -> list[tuple[str, ...]]:
    groups_by_slot = {
        "economic-1": [("economy.city", "城市经济")],
        "economic-2": [("economy.industry", "产业发展")],
        "economic-3": [("economy.consumption", "消费", "民生")],
        "transport-map": [
            ("site.transport.hub", "枢纽站点"),
            ("site.transport.external", "外部交通"),
            ("site.transport.station", "交通站点"),
            ("site.infrastructure", "基础设施"),
        ],
        "site-location-1": [("site.boundary", "场地四至")],
        "site-location-2": [("site.transport.external", "外部交通"), ("site.transport.station", "交通站点")],
        "site-location-3": [("site.transport.hub", "枢纽站点"), ("site.infrastructure", "基础设施")],
        "site-location-4": [("site.development", "区域开发"), ("site.infrastructure", "基础设施")],
    }
    return groups_by_slot.get(slot_id, [])


def _best_asset_for_tokens(
    assets: list[dict],
    tokens: tuple[str, ...],
    *,
    exclude: set[str],
) -> Optional[dict]:
    best: Optional[dict] = None
    best_score = 0
    for asset in assets:
        asset_id = str(asset.get("id") or "")
        if asset_id in exclude:
            continue
        haystack = " ".join(str(asset.get(k) or "") for k in ("logical_key", "title", "summary")).lower()
        score = sum(1 for token in tokens if token.lower() in haystack)
        if score > best_score:
            best = asset
            best_score = score
    return best


def _compose_case_card_data(
    *,
    entry: OutlineSlideEntry,
    project_id: Optional[UUID],
    db: Optional[Session],
    outline_spec: Optional[OutlineSpec],
) -> Optional[tuple[CaseCardData, list[str]]]:
    if project_id is None or db is None or outline_spec is None:
        return None

    case_no = _repeat_position_for_slot(entry, outline_spec)
    if case_no is None:
        return None

    thumbnail = _find_asset_by_logical_key(
        db=db,
        project_id=project_id,
        logical_key=f"reference.case.{case_no}.thumbnail",
    )
    source = _find_asset_by_logical_key(
        db=db,
        project_id=project_id,
        logical_key=f"reference.case.{case_no}.source",
    )
    analysis = _find_asset_by_logical_key(
        db=db,
        project_id=project_id,
        logical_key=f"reference.case.{case_no}.analysis",
    )
    card = _find_asset_by_logical_key(
        db=db,
        project_id=project_id,
        logical_key=f"reference.case.{case_no}.card",
    )

    text = (card and card.summary) or (analysis and analysis.summary) or (source and source.summary) or ""
    source_text = (source and source.summary) or ""
    raw_data = {
        "component_type": ComponentType.CASE_CARD.value,
        "title": entry.title or f"参考案例 {case_no}",
        "case_idx": case_no - 1,
        "case_name": _case_name(source_text) or entry.title or f"参考案例 {case_no}",
        "thumbnail": str(thumbnail.id) if thumbnail else None,
        "scale": _case_scale(source_text),
        "highlights": _compact_markdown_text(text, max_chars=95),
        "inspiration": _compact_markdown_text(entry.key_message or text, max_chars=95),
    }
    try:
        data = CaseCardData.model_validate(raw_data)
    except Exception:
        data = CaseCardData.model_validate(truncate_to_schema(raw_data, CaseCardData))

    asset_refs = [f"asset:{thumbnail.id}"] if thumbnail else []
    return data, asset_refs


def _compose_content_bullets_data(
    *,
    entry: OutlineSlideEntry,
    brief_dict: dict,
    asset_summary: list[dict],
    binding: Optional[SlideMaterialBinding],
    outline_spec: Optional[OutlineSpec],
    outline_json: dict,
) -> Optional[tuple[ContentBulletsData, list[str]]]:
    slot_id = normalize_slot_id(entry.slot_id)
    if slot_id == "concept-intro":
        if outline_spec is None:
            return None
        proposal = _concept_proposal_for_entry(entry, outline_spec, outline_json)
        if proposal is None:
            return None
        return _compose_concept_intro_bullets(entry=entry, proposal=proposal)

    outline_rows = _content_rows_from_design_outline_assets(asset_summary, slot_id=slot_id)
    if outline_rows:
        raw_data = {
            "component_type": ComponentType.CONTENT_BULLETS.value,
            "title": entry.title or entry.section or "内容分析",
            "lede": _content_lede_from_rows(outline_rows),
            "bullets": outline_rows[:6],
            "illustration": _first_visual_asset_id(asset_summary, binding=binding),
        }
        try:
            data = ContentBulletsData.model_validate(raw_data)
        except Exception:
            data = ContentBulletsData.model_validate(truncate_to_schema(raw_data, ContentBulletsData))

        asset_refs = [f"asset:{data.illustration}"] if data.illustration else []
        return data, asset_refs

    brief_outline = brief_dict.get("brief_doc_outline") or {}
    source_items = _content_source_items(
        entry=entry,
        brief_outline=brief_outline,
        binding=binding,
        asset_summary=asset_summary,
        brief_dict=brief_dict,
    )
    bullets = _bullet_rows_for_slot(slot_id, source_items)
    if len(bullets) < 3:
        return None

    raw_data = {
        "component_type": ComponentType.CONTENT_BULLETS.value,
        "title": entry.title or entry.section or "内容分析",
        "lede": _content_lede(entry=entry, brief_outline=brief_outline, source_items=source_items),
        "bullets": bullets[:6],
        "illustration": _first_visual_asset_id(asset_summary, binding=binding),
    }
    try:
        data = ContentBulletsData.model_validate(raw_data)
    except Exception:
        data = ContentBulletsData.model_validate(truncate_to_schema(raw_data, ContentBulletsData))

    asset_refs = [f"asset:{data.illustration}"] if data.illustration else []
    return data, asset_refs


def _compose_policy_list_data(
    *,
    entry: OutlineSlideEntry,
    brief_dict: dict,
    asset_summary: list[dict],
    binding: Optional[SlideMaterialBinding],
) -> Optional[tuple[PolicyListData, list[str]]]:
    policies = _policy_items_from_design_outline_assets(asset_summary, entry=entry)
    if policies:
        policies = _slice_repeated_items_for_slot(
            policies,
            slot_id=entry.slot_id or normalize_slot_id(entry.slot_id),
            page_size=2,
        )
        if not policies:
            return None
        raw_data = {
            "component_type": ComponentType.POLICY_LIST.value,
            "title": entry.title or "政策分析",
            "policies": policies,
        }
        try:
            data = PolicyListData.model_validate(raw_data)
        except Exception:
            data = PolicyListData.model_validate(truncate_to_schema(raw_data, PolicyListData))
        return data, []

    policy_sources = _policy_source_items(
        entry=entry,
        brief_dict=brief_dict,
        asset_summary=asset_summary,
        binding=binding,
    )
    policies = [_policy_item_from_text(text, entry=entry) for text in policy_sources[:5]]
    policies = [policy for policy in policies if policy.get("title")]
    if not policies:
        return None

    raw_data = {
        "component_type": ComponentType.POLICY_LIST.value,
        "title": entry.title or "政策分析",
        "policies": policies,
    }
    try:
        data = PolicyListData.model_validate(raw_data)
    except Exception:
        data = PolicyListData.model_validate(truncate_to_schema(raw_data, PolicyListData))
    return data, []


def _compose_table_data(
    *,
    entry: OutlineSlideEntry,
    brief_dict: dict,
    asset_summary: list[dict],
    binding: Optional[SlideMaterialBinding],
    outline_spec: Optional[OutlineSpec],
    outline_json: dict,
) -> Optional[tuple[TableData, list[str]]]:
    slot_id = normalize_slot_id(entry.slot_id)
    preferred_asset = _preferred_table_asset(slot_id, asset_summary, binding)
    if preferred_asset is not None:
        table = _table_from_asset(entry=entry, asset=preferred_asset)
        if table is not None:
            return table

    if slot_id == "material-economic":
        table = _material_economic_table(
            entry=entry,
            brief_dict=brief_dict,
            outline_spec=outline_spec,
            outline_json=outline_json,
        )
        if table is not None:
            return table

    source_items = _content_source_items(
        entry=entry,
        brief_outline=brief_dict.get("brief_doc_outline") or {},
        binding=binding,
        asset_summary=asset_summary,
        brief_dict=brief_dict,
    )
    if len(source_items) < 2:
        return None

    headers = ["项目", "核心要求", "对本项目影响"]
    rows = [
        [
            _compact_markdown_text(entry.title or entry.section or "分析项", max_chars=20),
            _compact_markdown_text(item, max_chars=34),
            _compact_markdown_text(_safe_entry_message(entry) or item, max_chars=34),
        ]
        for item in source_items[:4]
    ]
    return _validate_table_payload({
        "component_type": ComponentType.TABLE.value,
        "title": entry.title or "对比分析",
        "headers": headers,
        "rows": rows,
        "note": _table_note_from_binding(binding),
    })


def _compose_concept_intro_bullets(
    *,
    entry: OutlineSlideEntry,
    proposal: ConceptProposal,
) -> tuple[ContentBulletsData, list[str]]:
    rows = [
        {"title": "设计理念", "body": proposal.design_idea},
        {"title": "体量组织", "body": proposal.massing_hint},
        {"title": "材料表达", "body": proposal.material_hint},
        {"title": "氛围关键词", "body": "、".join([*proposal.design_keywords, proposal.mood_hint])},
    ]
    bullets = [
        {
            "title": _compact_markdown_text(row["title"], max_chars=18),
            "body": _compact_markdown_text(row["body"], max_chars=86),
        }
        for row in rows
        if row["body"]
    ]
    while len(bullets) < 3:
        bullets.append({
            "title": "方案线索",
            "body": _compact_markdown_text(proposal.name or _safe_entry_message(entry) or entry.title, max_chars=86),
        })

    raw_data = {
        "component_type": ComponentType.CONTENT_BULLETS.value,
        "title": proposal.name or entry.title or "概念方案",
        "lede": _compact_markdown_text(proposal.narrative, max_chars=130),
        "bullets": bullets[:4],
        "illustration": None,
    }
    try:
        data = ContentBulletsData.model_validate(raw_data)
    except Exception:
        data = ContentBulletsData.model_validate(truncate_to_schema(raw_data, ContentBulletsData))
    return data, []


def _content_source_items(
    *,
    entry: OutlineSlideEntry,
    brief_outline: dict,
    binding: Optional[SlideMaterialBinding],
    asset_summary: list[dict],
    brief_dict: dict,
) -> list[str]:
    items: list[str] = []
    for value in (
        _safe_entry_message(entry),
        brief_outline.get("positioning_statement"),
        brief_outline.get("narrative_arc"),
        brief_dict.get("site_address"),
    ):
        _append_source_item(items, value)

    emphasis = brief_outline.get("recommended_emphasis") or {}
    if isinstance(emphasis, dict):
        for key in ("site_advantage", "competitive_edge", "case_inspiration"):
            _append_source_item(items, emphasis.get(key))

    for principle in brief_outline.get("design_principles") or []:
        _append_source_item(items, principle)

    if binding is not None:
        for snippet in binding.evidence_snippets or []:
            _append_source_item(items, snippet)

    for asset in asset_summary:
        _append_source_item(items, asset.get("summary"))
        _append_source_item(items, asset.get("title"))

    return _dedupe_source_items(items)


def _append_source_item(items: list[str], value) -> None:
    if value is None:
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _append_source_item(items, item)
        return
    if _looks_like_task_instruction(str(value)):
        return
    text = _compact_markdown_text(str(value), max_chars=160)
    if text:
        items.append(text)


def _dedupe_source_items(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _bullet_rows_for_slot(slot_id: str, source_items: list[str]) -> list[dict]:
    labels_by_slot = {
        "cultural-analysis": ["文化线索", "空间转译", "设计影响", "表达重点"],
        "site-summary": ["区位判断", "场地条件", "设计注意", "机会总结"],
        "project-positioning": ["定位主张", "社会价值", "运营价值", "差异化"],
        "design-strategies": ["场地回应", "文化表达", "运营效率", "体验组织"],
        "design-brief-doc": ["项目概述", "设计目标", "功能需求", "技术要求"],
    }
    labels = labels_by_slot.get(slot_id, ["核心判断", "设计线索", "实施要点", "表达重点"])
    rows: list[dict] = []
    for idx, item in enumerate(source_items[:6]):
        rows.append({
            "title": labels[idx] if idx < len(labels) else f"要点{idx + 1}",
            "body": _compact_markdown_text(item, max_chars=86),
        })
    return rows


def _content_lede(
    *,
    entry: OutlineSlideEntry,
    brief_outline: dict,
    source_items: list[str],
) -> Optional[str]:
    for value in (
        _safe_entry_message(entry),
        brief_outline.get("positioning_statement"),
        brief_outline.get("executive_summary"),
        source_items[0] if source_items else None,
    ):
        text = _compact_markdown_text(str(value or ""), max_chars=130)
        if text:
            return text
    return None


def _first_visual_asset_id(
    asset_summary: list[dict],
    *,
    binding: Optional[SlideMaterialBinding],
) -> Optional[str]:
    if binding is None or not (binding.derived_asset_ids or []):
        return None
    for asset in asset_summary:
        if _asset_is_visual(asset):
            return str(asset["id"])
    return None


def _policy_source_items(
    *,
    entry: OutlineSlideEntry,
    brief_dict: dict,
    asset_summary: list[dict],
    binding: Optional[SlideMaterialBinding],
) -> list[str]:
    brief_outline = brief_dict.get("brief_doc_outline") or {}
    emphasis = brief_outline.get("recommended_emphasis") or {}
    candidates: list[str] = []

    if isinstance(emphasis, dict):
        _append_policy_candidate(candidates, emphasis.get("policy_focus"))

    for chapter in brief_outline.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        text = "；".join(str(v) for v in [
            chapter.get("title"),
            *(chapter.get("key_findings") or []),
            chapter.get("narrative_direction"),
        ] if v)
        _append_policy_candidate(candidates, text)

    if binding is not None:
        for snippet in binding.evidence_snippets or []:
            _append_policy_candidate(candidates, snippet)

    for asset in asset_summary:
        haystack = " ".join(str(asset.get(k) or "") for k in ("logical_key", "type", "title", "summary"))
        if _looks_policy_related(haystack):
            _append_policy_candidate(candidates, asset.get("summary") or asset.get("title"))

    _append_policy_candidate(candidates, entry.key_message)
    return [item for item in _dedupe_source_items(candidates) if _looks_policy_related(item)]


def _policy_items_from_design_outline_assets(
    asset_summary: list[dict],
    *,
    entry: OutlineSlideEntry,
) -> list[dict]:
    policies: list[dict] = []
    for text in _design_outline_texts(asset_summary):
        policies.extend(_parse_policy_markdown(text, entry=entry))
    return _dedupe_policy_items(policies)


def _content_rows_from_design_outline_assets(asset_summary: list[dict], *, slot_id: str) -> list[dict]:
    rows: list[dict] = []
    for text in _design_outline_texts(asset_summary):
        rows.extend(_content_rows_from_design_outline_text(text, slot_id=slot_id))
    return _dedupe_bullet_rows(rows)


def _design_outline_texts(asset_summary: list[dict]) -> list[str]:
    texts: list[str] = []
    for asset in asset_summary:
        logical_key = str(asset.get("logical_key") or "").lower()
        title = str(asset.get("title") or "")
        if logical_key == "brief.design_outline" or "设计建议书大纲" in title:
            source_text = _read_text_asset_source(asset)
            summary = str(asset.get("summary") or "")
            if source_text:
                texts.append(source_text)
            elif summary:
                texts.append(summary)
    return texts


def _read_text_asset_source(asset: dict) -> str:
    path = _asset_source_path(asset)
    if path is None or path.suffix.lower() not in {".md", ".txt"} or not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _content_rows_from_design_outline_text(text: str, *, slot_id: str) -> list[dict]:
    sections_by_slot = {
        "cultural-analysis": ("文化特征",),
        "site-summary": ("场地四至分析", "设计限制条件汇总", "周边产业分析 - 区域开发情况"),
        "project-positioning": ("项目定位总结", "地块优劣势对比"),
        "design-strategies": ("设计策略",),
        "design-brief-doc": ("建筑设计任务书（一）", "建筑设计任务书（二）", "功能布局分析图"),
    }
    headings = sections_by_slot.get(slot_id)
    if not headings:
        return []

    rows: list[dict] = []
    for heading in headings:
        section = _markdown_section(text, heading)
        if not section:
            continue
        if heading == "设计限制条件汇总":
            rows.extend(_rows_from_markdown_table(section, title_col=0, body_col=2))
        else:
            rows.extend(_rows_from_markdown_list(section))

    return rows[:6]


def _markdown_section(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"^[^\S\r\n]*#{{2,4}}[^\S\r\n]+{re.escape(heading)}[^\S\r\n]*\r?$\n?(?P<body>.*?)(?=^[^\S\r\n]*#{{2,4}}[^\S\r\n]+|\Z)",
        flags=re.M | re.S,
    )
    match = pattern.search(text or "")
    return match.group("body").strip() if match else ""


def _rows_from_markdown_list(section: str) -> list[dict]:
    rows: list[dict] = []
    for line in section.splitlines():
        raw = line.strip()
        if not raw or raw.startswith(">") or raw.startswith("|"):
            continue
        raw = re.sub(r"^\s*(?:[-*]|\d+[.\、])\s*", "", raw)
        raw = raw.strip()
        if not raw:
            continue

        title = None
        body = raw
        bold_match = re.match(r"\*\*(.+?)\*\*[：:]\s*(.+)", raw)
        if bold_match:
            title = bold_match.group(1).strip()
            body = bold_match.group(2).strip()
        elif "：" in raw:
            head, tail = raw.split("：", 1)
            if 2 <= len(head) <= 18:
                title = head.strip()
                body = tail.strip()

        body = _compact_markdown_text(body, max_chars=90)
        if body:
            rows.append({
                "title": _compact_markdown_text(title, max_chars=18) if title else None,
                "body": body,
            })
    return rows


def _rows_from_markdown_table(section: str, *, title_col: int, body_col: int) -> list[dict]:
    rows: list[dict] = []
    for line in section.splitlines():
        raw = line.strip()
        if not raw.startswith("|") or "---" in raw:
            continue
        cells = [cell.strip() for cell in raw.strip("|").split("|")]
        if len(cells) <= max(title_col, body_col):
            continue
        if cells[title_col] in {"限制条件", "指标项", "部位"}:
            continue
        rows.append({
            "title": _compact_markdown_text(cells[title_col], max_chars=18),
            "body": _compact_markdown_text(cells[body_col], max_chars=90),
        })
    return rows


def _dedupe_bullet_rows(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for row in rows:
        body = str(row.get("body") or "")
        key = f"{row.get('title') or ''}|{body}".lower()
        if not body or key in seen or _looks_like_task_instruction(body):
            continue
        seen.add(key)
        out.append(row)
    return out


def _content_lede_from_rows(rows: list[dict]) -> Optional[str]:
    if not rows:
        return None
    return _compact_markdown_text("；".join(str(row.get("body") or "") for row in rows[:2]), max_chars=130)


def _parse_policy_markdown(text: str, *, entry: OutlineSlideEntry) -> list[dict]:
    if not text:
        return []
    section_match = re.search(
        r"(?:#{2,4}\s*)?政策分析(?P<body>.*?)(?:\n#{2,4}\s|\Z)",
        text,
        flags=re.S,
    )
    body = section_match.group("body") if section_match else text
    chunks = re.split(r"\n\s*(?=\d+\.\s*\*\*《)", body)
    policies: list[dict] = []
    for chunk in chunks:
        if not _looks_policy_related(chunk):
            continue
        name_match = re.search(r"《([^》]+)》", chunk)
        if not name_match:
            continue
        name = name_match.group(1).strip()
        source_url = _first_url(chunk)
        year = _first_year(chunk)
        content_text = re.sub(r"^\s*\d+\.\s*", "", chunk.strip())
        content_text = re.sub(r"\*\*", "", content_text)
        content_text = re.sub(r">?\s*来源链接[:：].*", "", content_text, flags=re.S)
        content_text = re.sub(r"《[^》]+》[：:]", "", content_text, count=1)
        content = _compact_markdown_text(content_text, max_chars=112)
        impact = _policy_impact_from_text(name, content, entry=entry)
        policies.append({
            "title": name,
            "publish_year": year,
            "content": content,
            "impact": impact,
            "source_url": source_url,
        })
    return policies


def _policy_impact_from_text(name: str, content: str, *, entry: OutlineSlideEntry) -> str:
    haystack = f"{name} {content}"
    if any(token in haystack for token in ("无障碍", "第三卫生间", "通风", "除臭", "CJJ")):
        return "转化为第三卫生间、无障碍、通风除臭等刚性配置要求。"
    if any(token in haystack for token in ("十四五", "人居环境", "品质")):
        return "支撑公厕从基础功能向品质化、生态化公共服务升级。"
    if any(token in haystack for token in ("国土空间", "控规", "用地", "规划")):
        return "约束选址、规模与公共服务设施配套边界。"
    return _compact_markdown_text(_safe_entry_message(entry) or "作为本项目定位、指标与运营策略的约束条件。", max_chars=56)


def _dedupe_policy_items(policies: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for policy in policies:
        key = str(policy.get("title") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(policy)
    return out


def _slice_repeated_items_for_slot(items: list[dict], *, slot_id: str, page_size: int) -> list[dict]:
    match = re.search(r"-(\d+)$", slot_id)
    if not match:
        return items[:page_size]
    idx = max(0, int(match.group(1)) - 1)
    start = idx * page_size
    return items[start:start + page_size]


def _append_policy_candidate(items: list[str], value) -> None:
    if not value:
        return
    if _looks_like_task_instruction(str(value)):
        return
    text = _compact_markdown_text(str(value), max_chars=180)
    if text:
        items.append(text)


def _looks_policy_related(text: str) -> bool:
    tokens = ("政策", "规划", "条例", "导则", "指引", "标准", "规范", "更新", "控规", "专项", "行动方案", "国土空间", "policy", "planning")
    lowered = (text or "").lower()
    return any(token in lowered for token in tokens)


def _policy_item_from_text(text: str, *, entry: OutlineSlideEntry) -> dict:
    source_url = _first_url(text)
    publish_year = _first_year(text)
    cleaned = _compact_markdown_text(text, max_chars=160)
    title = _policy_title(cleaned)
    content = _compact_markdown_text(_strip_url(cleaned), max_chars=110)
    impact_seed = _safe_entry_message(entry) or "作为本项目定位、指标与运营策略的约束条件。"
    return {
        "title": title,
        "publish_year": publish_year,
        "content": content if content != title else None,
        "impact": _compact_markdown_text(impact_seed, max_chars=56),
        "source_url": source_url,
    }


def _policy_title(text: str) -> str:
    quoted = re.search(r"[《「](.+?)[》」]", text or "")
    if quoted:
        return quoted.group(1).strip()
    head = re.split(r"[。；;\n]", text or "", maxsplit=1)[0]
    head = re.sub(r"^\d+[\.\、]\s*", "", head).strip(" ：:，,")
    return _compact_markdown_text(head or "相关政策", max_chars=56)


def _first_url(text: str) -> Optional[str]:
    match = re.search(r"https?://\S+", text or "")
    return match.group(0).rstrip("，。；;") if match else None


def _strip_url(text: str) -> str:
    return re.sub(r"https?://\S+", "", text or "").strip()


def _first_year(text: str) -> Optional[str]:
    match = re.search(r"(?:19|20)\d{2}", text or "")
    return match.group(0) if match else None


def _preferred_table_asset(
    slot_id: str,
    asset_summary: list[dict],
    binding: Optional[SlideMaterialBinding],
) -> Optional[dict]:
    table_assets = [asset for asset in asset_summary if _asset_is_table(asset)]
    if not table_assets:
        return None

    slot_tokens = {
        "upper-planning": ("planning", "plan", "规划", "infrastructure"),
        "competitor-local": ("competitor", "同类型", "竞品"),
        "material-economic": ("economic", "material", "kpi", "指标", "经济"),
        "poi-analysis": ("site.poi", "poi", "场地poi", "业态"),
    }.get(slot_id, ())

    def score(asset: dict) -> int:
        haystack = " ".join(str(asset.get(k) or "") for k in ("logical_key", "title", "summary")).lower()
        value = 0
        if binding and asset.get("id") in set(binding.derived_asset_ids or []):
            value += 10
        for token in slot_tokens:
            if token.lower() in haystack:
                value += 5
        if asset.get("data_json"):
            value += 1
        return value

    return max(table_assets, key=score)


def _asset_is_table(asset: dict) -> bool:
    asset_type = str(asset.get("type") or "").lower()
    subtype = str(asset.get("subtype") or "").lower()
    logical_key = str(asset.get("logical_key") or "").lower()
    return asset_type in {"kpi_table", "table"} or subtype in {"spreadsheet", "csv", "xlsx"} or logical_key.endswith(".table")


def _table_from_asset(
    *,
    entry: OutlineSlideEntry,
    asset: dict,
) -> Optional[tuple[TableData, list[str]]]:
    preview = _preview_rows_from_asset(asset)
    if not preview:
        return None

    headers, rows = _headers_rows_from_preview(preview)
    if not headers or not rows:
        return None

    return _validate_table_payload({
        "component_type": ComponentType.TABLE.value,
        "title": entry.title or asset.get("title") or "表格分析",
        "headers": headers,
        "rows": rows,
        "note": _compact_markdown_text(str(asset.get("title") or asset.get("logical_key") or ""), max_chars=70),
    })


def _preview_rows_from_asset(asset: dict) -> list[list]:
    data = asset.get("data_json") or {}
    if not isinstance(data, dict):
        return _preview_rows_from_asset_source(asset)
    preview_rows = data.get("preview_rows") or []
    if preview_rows and isinstance(preview_rows[0], dict):
        rows = preview_rows[0].get("rows") or []
        return [row for row in rows if isinstance(row, list)]
    if isinstance(data.get("rows"), list):
        return data["rows"]
    return _preview_rows_from_asset_source(asset)


def _preview_rows_from_asset_source(asset: dict) -> list[list]:
    source_path = _asset_source_path(asset)
    if source_path is None or source_path.suffix.lower() != ".xlsx" or not source_path.exists():
        return []
    return _read_xlsx_preview_rows(source_path)


def _asset_source_path(asset: dict) -> Optional[Path]:
    config = asset.get("config_json") or {}
    candidates = [
        config.get("source_path"),
        (config.get("metadata_json") or {}).get("source_path") if isinstance(config.get("metadata_json"), dict) else None,
        config.get("content_url"),
        asset.get("image_url"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        raw = str(candidate)
        if raw.startswith("file:"):
            parsed = urlparse(raw)
            path = Path(unquote(parsed.path.lstrip("/")))
        else:
            path = Path(raw)
        if path.exists():
            return path
    return None


def _read_xlsx_preview_rows(path: Path, *, max_rows: int = 8, max_cols: int = 8) -> list[list]:
    try:
        with ZipFile(path) as zf:
            shared_strings = _xlsx_shared_strings(zf)
            worksheet_names = sorted(
                name for name in zf.namelist()
                if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
            )
            if not worksheet_names:
                return []
            with zf.open(worksheet_names[0]) as fh:
                root = ET.parse(fh).getroot()
    except Exception:
        return []

    rows: list[list] = []
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    for row_el in root.findall(".//x:sheetData/x:row", ns):
        row: list[str] = []
        for cell in row_el.findall("x:c", ns)[:max_cols]:
            col_idx = _xlsx_col_idx(str(cell.get("r") or ""))
            while len(row) < col_idx:
                row.append("")
            row.append(_xlsx_cell_value(cell, shared_strings, ns))
        if any(str(cell).strip() for cell in row):
            rows.append(row[:max_cols])
        if len(rows) >= max_rows:
            break
    return rows


def _xlsx_shared_strings(zf: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    try:
        with zf.open("xl/sharedStrings.xml") as fh:
            root = ET.parse(fh).getroot()
    except Exception:
        return []
    values: list[str] = []
    for item in root.findall(".//x:si", ns):
        text = "".join(node.text or "" for node in item.findall(".//x:t", ns))
        values.append(text)
    return values


def _xlsx_cell_value(cell: ET.Element, shared_strings: list[str], ns: dict[str, str]) -> str:
    value_el = cell.find("x:v", ns)
    raw = value_el.text if value_el is not None else None
    if cell.get("t") == "s" and raw is not None:
        try:
            return shared_strings[int(raw)]
        except (ValueError, IndexError):
            return raw
    if cell.get("t") == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//x:t", ns))
    return raw or ""


def _xlsx_col_idx(cell_ref: str) -> int:
    letters = re.match(r"([A-Z]+)", cell_ref.upper())
    if not letters:
        return 0
    value = 0
    for char in letters.group(1):
        value = value * 26 + (ord(char) - ord("A") + 1)
    return max(0, value - 1)


def _headers_rows_from_preview(preview: list[list]) -> tuple[list[str], list[list[str]]]:
    cleaned = [
        [_compact_markdown_text(str(cell), max_chars=32) for cell in row if cell is not None and str(cell).strip()]
        for row in preview
    ]
    cleaned = [row for row in cleaned if row]
    if len(cleaned) < 2:
        return [], []

    first = cleaned[0][:6]
    if _looks_like_header(first):
        headers = first
        data_rows = cleaned[1:]
    else:
        width = min(max(len(row) for row in cleaned), 6)
        headers = [f"字段{i + 1}" for i in range(width)]
        data_rows = cleaned

    width = min(len(headers), 6)
    headers = [_compact_markdown_text(cell, max_chars=22) for cell in headers[:width]]
    rows: list[list[str]] = []
    for row in data_rows[:8]:
        normalized = [_compact_markdown_text(cell, max_chars=34) for cell in row[:width]]
        if len(normalized) < width:
            normalized.extend([""] * (width - len(normalized)))
        rows.append(normalized)
    return headers, rows


def _looks_like_header(row: list[str]) -> bool:
    header_tokens = ("名称", "项目", "类型", "距离", "规模", "特色", "要求", "影响", "指标", "数值", "年份")
    return any(any(token in cell for token in header_tokens) for cell in row)


def _material_economic_table(
    *,
    entry: OutlineSlideEntry,
    brief_dict: dict,
    outline_spec: Optional[OutlineSpec],
    outline_json: dict,
) -> Optional[tuple[TableData, list[str]]]:
    proposals: list[ConceptProposal] = []
    if outline_spec is not None:
        for raw in outline_json.get("concept_proposals") or []:
            try:
                proposals.append(ConceptProposal.model_validate(raw))
            except Exception:
                continue
    if not proposals:
        return None

    area = _format_area(brief_dict.get("gross_floor_area")) if brief_dict.get("gross_floor_area") else "待测算"
    far = str(brief_dict.get("far")) if brief_dict.get("far") else "待测算"
    rows = [
        [
            _compact_markdown_text(proposal.name, max_chars=18),
            _compact_markdown_text(proposal.material_hint, max_chars=34),
            area,
            far,
            _compact_markdown_text(proposal.design_idea, max_chars=34),
        ]
        for proposal in sorted(proposals, key=lambda p: p.index)[:3]
    ]
    return _validate_table_payload({
        "component_type": ComponentType.TABLE.value,
        "title": entry.title or "材质与经济技术指标",
        "headers": ["方案", "材质策略", "建筑面积", "容积率", "综合判断"],
        "rows": rows,
        "note": "指标为当前方案阶段测算口径",
    })


def _table_note_from_binding(binding: Optional[SlideMaterialBinding]) -> Optional[str]:
    if binding is None:
        return None
    return _join_snippets(binding.evidence_snippets or [], max_chars=70)


def _validate_table_payload(raw_data: dict) -> Optional[tuple[TableData, list[str]]]:
    try:
        data = TableData.model_validate(raw_data)
    except Exception:
        data = TableData.model_validate(truncate_to_schema(raw_data, TableData))
    if not data.headers or not data.rows:
        return None
    width = len(data.headers)
    if any(len(row) != width for row in data.rows):
        return None
    return data, []


def _compose_chart_data(
    *,
    entry: OutlineSlideEntry,
    asset_summary: list[dict],
    binding: Optional[SlideMaterialBinding],
) -> Optional[tuple[ChartData, list[str]]]:
    chart_asset = _preferred_chart_asset(asset_summary, binding)
    if chart_asset is not None:
        raw_data = {
            "component_type": ComponentType.CHART.value,
            "title": entry.title or chart_asset.get("title") or "图表分析",
            "bullets": _chart_bullets(entry=entry, asset=chart_asset, binding=binding),
            "chart_path": str(chart_asset["id"]),
            "chart_spec": None,
        }
        try:
            data = ChartData.model_validate(raw_data)
        except Exception:
            data = ChartData.model_validate(truncate_to_schema(raw_data, ChartData))
        return data, [chart_asset["asset_ref"]] if chart_asset.get("asset_ref") else []

    slot_id = normalize_slot_id(entry.slot_id)
    if slot_id == "policy-impact":
        policy_items = _policy_items_from_design_outline_assets(asset_summary, entry=entry)
        if policy_items:
            bullets = [
                _compact_markdown_text(
                    f"{policy['title']}：{policy.get('impact') or policy.get('content')}",
                    max_chars=74,
                )
                for policy in policy_items[:4]
            ]
            raw_data = {
                "component_type": ComponentType.CHART.value,
                "title": entry.title or "政策影响分析",
                "bullets": bullets,
                "chart_path": None,
                "chart_spec": {
                    "chart_type": "bar",
                    "chart_title": "核心政策对项目影响强度",
                    "data": [
                        {"label": "设施配置", "value": 90},
                        {"label": "品质升级", "value": 82},
                        {"label": "文化表达", "value": 74},
                        {"label": "运营管理", "value": 68},
                    ],
                    "x_label": "影响维度",
                    "y_label": "影响强度",
                },
            }
            try:
                data = ChartData.model_validate(raw_data)
            except Exception:
                data = ChartData.model_validate(truncate_to_schema(raw_data, ChartData))
            return data, []

    if slot_id == "poi-analysis":
        table_asset = _preferred_table_asset(slot_id, asset_summary, binding)
        if table_asset is not None:
            chart_path = _materialize_bar_chart_from_table(entry=entry, asset=table_asset)
            if chart_path:
                raw_data = {
                    "component_type": ComponentType.CHART.value,
                    "title": entry.title or "场地 POI 业态分析",
                    "bullets": _chart_bullets(entry=entry, asset=table_asset, binding=binding),
                    "chart_path": chart_path,
                    "chart_spec": None,
                }
                try:
                    data = ChartData.model_validate(raw_data)
                except Exception:
                    data = ChartData.model_validate(truncate_to_schema(raw_data, ChartData))
                return data, []

    return None


def _materialize_chart_spec_if_needed(
    *,
    entry: OutlineSlideEntry,
    data: ChartData,
) -> ChartData:
    if data.chart_path or data.chart_spec is None:
        return data

    spec = data.chart_spec
    normalized_points = _normalize_chart_points(spec.data)
    if not normalized_points:
        return data

    digest_payload = {
        "slide_no": entry.slide_no,
        "chart_type": spec.chart_type,
        "title": spec.chart_title,
        "data": normalized_points,
    }
    digest = hashlib.sha1(json.dumps(digest_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:10]
    output_path = Path("tmp") / "chart_materialized" / f"slide_{entry.slide_no}_{digest}.png"

    from agent.chart_materialize import materialize_chart_png

    chart_path = materialize_chart_png(
        chart_type=spec.chart_type,
        title=spec.chart_title,
        data=normalized_points,
        output_path=output_path,
        x_label=spec.x_label,
        y_label=spec.y_label,
    )
    if not chart_path:
        return data
    return data.model_copy(update={"chart_path": chart_path})


def _normalize_chart_points(raw_points: list[dict]) -> list[dict]:
    out: list[dict] = []
    for idx, point in enumerate(raw_points or []):
        if not isinstance(point, dict):
            continue
        label = _first_present(point, ("label", "x", "category", "类别", "维度", "名称", "项目"))
        value = _first_present(point, ("value", "y", "数量", "数值", "占比", "影响程度", "score"))
        if value is None:
            value = _first_numeric_value(point)
        numeric_value = _to_float(str(value)) if value is not None else None
        if numeric_value is None:
            continue
        out.append({
            "label": str(label if label is not None else idx + 1),
            "value": numeric_value,
        })
    return out


def _first_present(point: dict, keys: tuple[str, ...]):
    for key in keys:
        if key in point and point[key] not in (None, ""):
            return point[key]
    return None


def _first_numeric_value(point: dict):
    for value in point.values():
        if _to_float(str(value)) is not None:
            return value
    return None


def _preferred_chart_asset(
    asset_summary: list[dict],
    binding: Optional[SlideMaterialBinding],
) -> Optional[dict]:
    chart_assets = [asset for asset in asset_summary if _asset_is_chart(asset)]
    if not chart_assets:
        return None

    def score(asset: dict) -> int:
        value = 0
        if binding and asset.get("id") in set(binding.derived_asset_ids or []):
            value += 10
        if asset.get("image_url"):
            value += 3
        if (asset.get("config_json") or {}).get("preview_url"):
            value += 3
        return value

    return max(chart_assets, key=score)


def _asset_is_chart(asset: dict) -> bool:
    asset_type = str(asset.get("type") or "").lower()
    subtype = str(asset.get("subtype") or "").lower()
    logical_key = str(asset.get("logical_key") or "").lower()
    return asset_type == "chart" or subtype == "chart_bundle" or ".chart." in logical_key


def _chart_bullets(
    *,
    entry: OutlineSlideEntry,
    asset: dict,
    binding: Optional[SlideMaterialBinding],
) -> list[str]:
    candidates: list[str] = []
    if binding is not None:
        candidates.extend(binding.evidence_snippets or [])
    candidates.extend([
        _safe_entry_message(entry),
        asset.get("summary"),
        asset.get("title"),
    ])
    bullets = [
        _compact_markdown_text(str(item), max_chars=74)
        for item in candidates
        if item and str(item).strip()
    ]
    bullets = _dedupe_source_items(bullets)
    while len(bullets) < 1:
        bullets.append(entry.title or "图表用于支撑本页分析判断。")
    return bullets[:4]


def _materialize_bar_chart_from_table(
    *,
    entry: OutlineSlideEntry,
    asset: dict,
) -> Optional[str]:
    preview = _preview_rows_from_asset(asset)
    headers, rows = _headers_rows_from_preview(preview)
    if not headers or not rows:
        return None

    data = _numeric_series_from_rows(headers, rows)
    if not data:
        return None

    digest = hashlib.sha1(json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:10]
    output_path = Path("tmp") / "chart_materialized" / f"slide_{entry.slide_no}_{digest}.png"
    from agent.chart_materialize import materialize_chart_png

    return materialize_chart_png(
        chart_type="bar",
        title=entry.title or "图表分析",
        data=data[:8],
        output_path=output_path,
        x_label=headers[0] if headers else None,
        y_label="数量",
    )


def _numeric_series_from_rows(headers: list[str], rows: list[list[str]]) -> list[dict]:
    numeric_col = None
    for col_idx in range(1, len(headers)):
        values = [_to_float(row[col_idx]) for row in rows if col_idx < len(row)]
        if any(value is not None for value in values):
            numeric_col = col_idx
            break
    if numeric_col is None:
        return []

    data: list[dict] = []
    for row in rows:
        if len(row) <= numeric_col:
            continue
        value = _to_float(row[numeric_col])
        if value is None:
            continue
        data.append({"label": row[0], "value": value})
    return data


def _to_float(value: str) -> Optional[float]:
    match = re.search(r"-?\d+(?:\.\d+)?", value or "")
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _section_no_for_entry(
    entry: OutlineSlideEntry,
    outline_spec: Optional[OutlineSpec],
) -> int:
    match = re.search(r"chapter-(\d+)-divider", entry.slot_id or "")
    if match:
        return int(match.group(1))
    if outline_spec is None:
        return 1
    chapter_no = 0
    for slide in sorted(outline_spec.slides, key=lambda s: s.slide_no):
        if re.search(r"chapter-\d+-divider", slide.slot_id or ""):
            chapter_no += 1
        if slide.slide_no == entry.slide_no:
            return max(1, chapter_no)
    return 1


_SECTION_EN_FALLBACKS = {
    "背景研究": "BACKGROUND RESEARCH",
    "场地分析": "SITE ANALYSIS",
    "竞品分析": "COMPETITOR ANALYSIS",
    "参考案例": "REFERENCE CASES",
    "项目定位": "PROJECT POSITIONING",
    "设计策略": "DESIGN STRATEGY",
    "概念方案": "CONCEPT PROPOSALS",
    "深化比选": "COMPARISON",
    "设计任务书": "DESIGN BRIEF",
    "结尾": "CLOSING",
}


def _section_en(section: str) -> str:
    return _SECTION_EN_FALLBACKS.get(section or "", "CHAPTER")


def _asset_is_visual(asset: dict) -> bool:
    if not asset.get("id"):
        return False
    if not asset.get("image_url"):
        return False
    asset_type = str(asset.get("type") or "").lower()
    subtype = str(asset.get("subtype") or "").lower()
    return asset_type in {"image", "chart", "map", "case_card"} or subtype in {"image", "chart_bundle"}


def _asset_caption(asset: dict) -> str:
    title = str(asset.get("title") or "")
    return _clean_caption(title or str(asset.get("logical_key") or "") or "IMAGE")


def _clean_caption(text: str) -> str:
    cleaned = re.sub(r"_?\d{2,}$", "", text or "")
    cleaned = cleaned.replace("_", " ").replace("-", " ").strip()
    return cleaned or "IMAGE"


def _safe_entry_message(entry: OutlineSlideEntry) -> str:
    for value in (entry.key_message, entry.purpose):
        if value and not _looks_like_task_instruction(str(value)):
            return str(value)
    return ""


def _looks_like_task_instruction(text: str) -> bool:
    text = text or ""
    lowered = text.lower()
    markers = (
        "[material package e2e",
        "调用 nanobanana",
        "nanobanana",
        "联网搜索",
        "生成封面",
        "生成目录",
        "生成室外",
        "生成符合",
        "请为该页面",
        "分析设计建议书大纲",
        "绘制",
        "提供政策来源",
        "要求：",
        "①",
        "②",
    )
    return any(marker in lowered for marker in markers)


def _join_snippets(snippets: list[str], *, max_chars: int) -> str:
    text = "；".join(
        s.strip()
        for s in snippets
        if s and s.strip() and not _looks_like_task_instruction(s)
    )
    return _compact_markdown_text(text, max_chars=max_chars)


def _compact_markdown_text(text: str, *, max_chars: int) -> str:
    cleaned = re.sub(r"https?://\S+", "", text or "")
    cleaned = re.sub(r"[#*_`>|-]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ：:;；")
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "…"


def _case_name(source_text: str) -> Optional[str]:
    match = re.search(r"^\s*#\s*(.+?)(?:\s*/|\n|$)", source_text or "", re.MULTILINE)
    if match:
        return match.group(1).strip(" 「」")
    return None


def _case_scale(source_text: str) -> Optional[str]:
    if not source_text:
        return None
    parts: list[str] = []
    for label in ("地点", "年份", "面积", "建筑师"):
        match = re.search(rf"\*\*{label}\*\*:\s*([^\n]+)", source_text)
        if match:
            parts.append(match.group(1).strip())
    return "｜".join(parts) if parts else None


def _find_asset_by_logical_key(
    *,
    db: Session,
    project_id: UUID,
    logical_key: str,
) -> Optional[Asset]:
    return (
        db.query(Asset)
        .filter(
            Asset.project_id == project_id,
            Asset.logical_key == logical_key,
        )
        .order_by(Asset.version.desc(), Asset.created_at.desc())
        .first()
    )


def _concept_proposal_for_entry(
    entry: OutlineSlideEntry,
    outline_spec: OutlineSpec,
    outline_json: dict,
) -> Optional[ConceptProposal]:
    proposal_index = _repeat_position_for_slot(entry, outline_spec)
    if proposal_index is None:
        return None

    proposals: list[ConceptProposal] = []
    for raw in outline_json.get("concept_proposals") or []:
        try:
            proposals.append(ConceptProposal.model_validate(raw))
        except Exception as exc:
            logger.warning("invalid concept_proposal skipped: %s", exc)
    proposals.sort(key=lambda p: p.index)

    for proposal in proposals:
        if proposal.index == proposal_index:
            return proposal
    return None


def _repeat_position_for_slot(
    entry: OutlineSlideEntry,
    outline_spec: OutlineSpec,
) -> Optional[int]:
    repeated = sorted(
        (
            slide for slide in outline_spec.slides
            if normalize_slot_id(slide.slot_id) == normalize_slot_id(entry.slot_id)
        ),
        key=lambda slide: slide.slide_no,
    )
    for idx, slide in enumerate(repeated, start=1):
        if slide.slide_no == entry.slide_no:
            return idx
    return None


def _find_concept_asset(
    *,
    db: Session,
    project_id: UUID,
    proposal_index: int,
    view: ConceptViewKind,
) -> Optional[Asset]:
    logical_key = concept_logical_key(proposal_index, view)
    return (
        db.query(Asset)
        .filter(
            Asset.project_id == project_id,
            Asset.logical_key == logical_key,
        )
        .order_by(Asset.version.desc(), Asset.created_at.desc())
        .first()
    )


async def compose_slide(
    entry: OutlineSlideEntry,
    theme: VisualTheme,
    brief_dict: dict,
    asset_summary: list[dict],
    binding: Optional[SlideMaterialBinding] = None,
    mode: ComposerMode | str | None = None,
    *,
    project_id: Optional[UUID] = None,
    db: Optional[Session] = None,
    outline_spec: Optional[OutlineSpec] = None,
    outline_json: Optional[dict] = None,
) -> LayoutSpec | _ComposerHTMLOutput | _ComposerTemplateOutput:
    """
    单页合成入口（三模式 + 自动回退）。

    mode=STRUCTURED: v2 LayoutSpec
    mode=HTML:       v3 body_html
    mode=TEMPLATE:   v4 SlideData JSON（蓝图 template_component 决定哪个组件）
                     若 slot 未声明 template_component 或装配失败 → 自动回退 HTML
    """
    resolved_mode = resolve_composer_mode(mode)

    if resolved_mode == ComposerMode.TEMPLATE:
        try:
            tmpl_result = await _compose_slide_template(
                entry,
                theme,
                brief_dict,
                asset_summary,
                binding,
                project_id=project_id,
                db=db,
                outline_spec=outline_spec,
                outline_json=outline_json,
            )
        except Exception as exc:
            logger.warning(
                "Composer (template) crashed for slide %s, falling back to html: %s",
                entry.slide_no, exc,
            )
            tmpl_result = None
        if tmpl_result is not None:
            return tmpl_result
        # fall through to HTML mode for this slide
        resolved_mode = ComposerMode.HTML

    if resolved_mode == ComposerMode.HTML:
        try:
            return await _compose_slide_html(entry, theme, brief_dict, asset_summary, binding)
        except Exception as e:
            logger.warning(f"Composer LLM (html) failed for slide {entry.slide_no}: {e}")
            return _html_fallback(entry)

    return await _compose_slide_structured(entry, theme, brief_dict, asset_summary, binding)


# ─────────────────────────────────────────────
# 主函数
# ─────────────────────────────────────────────

async def compose_all_slides(
    project_id: UUID,
    db: Session,
    mode: ComposerMode | str | None = None,
) -> list[Slide]:
    """
    为项目所有幻灯片生成 LayoutSpec / HTML，保存到 slides 表。
    需要项目已有 Outline 和 VisualTheme。

    mode=STRUCTURED: v2 — 输出 LayoutSpec JSON
    mode=HTML:       v3 — 输出 body_html，spec_json 存 {"html_mode": true, "body_html": ...}
    """
    mode = resolve_composer_mode(mode)

    # 1. 加载 Outline
    outline = (
        db.query(Outline)
        .filter(Outline.project_id == project_id)
        .order_by(Outline.version.desc())
        .first()
    )
    if not outline:
        raise ValueError(f"No outline found for project {project_id}")
    outline_spec = OutlineSpec.model_validate(outline.spec_json)

    # 2. 加载 VisualTheme（无则使用默认主题）
    theme = get_latest_theme(project_id, db)
    if not theme:
        logger.warning(f"No VisualTheme found for project {project_id}, using default")
        theme = _default_theme(project_id)

    # 3. 加载项目 Brief
    brief = (
        db.query(ProjectBrief)
        .filter(ProjectBrief.project_id == project_id)
        .order_by(ProjectBrief.version.desc())
        .first()
    )
    brief_doc = (
        db.query(BriefDoc)
        .filter(BriefDoc.project_id == project_id)
        .order_by(BriefDoc.version.desc())
        .first()
    )
    brief_dict = {
        "building_type": brief.building_type if brief else "",
        "client_name": brief.client_name if brief else "",
        "style_preferences": (brief.style_preferences or []) if brief else [],
        "city": brief.city if brief else "",
        "province": brief.province if brief else "",
        "district": brief.district if brief else "",
        "site_address": brief.site_address if brief else "",
        "gross_floor_area": float(brief.gross_floor_area) if brief and brief.gross_floor_area else None,
        "far": float(brief.far) if brief and brief.far else None,
        "site_area": float(brief.site_area) if brief and brief.site_area else None,
        "brief_doc_outline": brief_doc.outline_json if brief_doc else {},
        "brief_doc_summary": brief_doc.narrative_summary if brief_doc else "",
    }

    package = (
        db.query(MaterialPackage)
        .filter(MaterialPackage.project_id == project_id)
        .order_by(MaterialPackage.version.desc())
        .first()
    )

    # 4. 加载资产摘要
    assets = db.query(Asset).filter(Asset.project_id == project_id).all()
    all_asset_summary = [
        {"id": str(a.id), "key": str(a.id), "type": a.asset_type, "subtype": a.subtype,
         "title": a.title, "image_url": a.image_url, "logical_key": a.logical_key,
         "summary": a.summary, "data_json": a.data_json, "config_json": a.config_json,
         "asset_ref": f"asset:{a.id}"}
        for a in assets
    ]

    bindings = []
    if package:
        bindings = (
            db.query(SlideMaterialBinding)
            .filter(
                SlideMaterialBinding.project_id == project_id,
                SlideMaterialBinding.outline_id == outline.id,
                SlideMaterialBinding.package_id == package.id,
            )
            .order_by(SlideMaterialBinding.slide_no.asc(), SlideMaterialBinding.version.desc())
            .all()
        )
    binding_by_slide_no = {}
    for binding in bindings:
        binding_by_slide_no.setdefault(binding.slide_no, binding)

    # 5. 并发合成所有幻灯片
    tasks = []
    for entry in outline_spec.slides:
        binding = binding_by_slide_no.get(entry.slide_no)
        tasks.append(
            compose_slide(
                entry,
                theme,
                brief_dict,
                _assets_for_entry(entry=entry, all_asset_summary=all_asset_summary, binding=binding),
                binding,
                mode=mode,
                project_id=project_id,
                db=db,
                outline_spec=outline_spec,
                outline_json=outline.spec_json or {},
            )
        )
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 6. 保存到 DB
    # 清理本版本的旧 slides
    db.query(Slide).filter(
        Slide.project_id == project_id,
        Slide.outline_id == outline.id,
    ).delete(synchronize_session=False)

    saved_slides = []
    for i, result in enumerate(results):
        entry = outline_spec.slides[i]
        binding = binding_by_slide_no.get(entry.slide_no)

        if isinstance(result, Exception):
            logger.error(f"Slide {entry.slide_no} compose failed: {result}")
            if mode in (ComposerMode.HTML, ComposerMode.TEMPLATE):
                result = _html_fallback(entry)
            else:
                result = _fallback_layout_spec(entry)

        # 根据结果类型构造 spec_json（不只看 mode，因为 TEMPLATE 模式可能回退）
        if isinstance(result, _ComposerTemplateOutput):
            spec_json = {
                "mode": "template",
                "component_type": result.component_type,
                "data": result.data,
                "asset_refs": result.asset_refs,
                "content_summary": result.content_summary,
                "slide_no": result.slide_no,
                "section": entry.section,
                "title": entry.title,
                "is_cover": entry.is_cover or entry.slide_no == 1,
                "is_chapter_divider": entry.is_chapter_divider,
            }
            slide_orm = Slide(
                project_id=project_id,
                package_id=package.id if package else None,
                outline_id=outline.id,
                binding_id=binding.id if binding else None,
                slide_no=result.slide_no,
                section=entry.section,
                title=entry.title,
                purpose=entry.purpose,
                key_message=entry.key_message,
                layout_template=None,
                spec_json=spec_json,
                source_refs_json=result.asset_refs,
                evidence_refs_json=list(binding.evidence_snippets or []) if binding else [],
                status=SlideStatus.SPEC_READY.value,
            )
        elif isinstance(result, _ComposerHTMLOutput):
            spec_json = {
                "mode": "html",
                "html_mode": True,  # legacy marker, kept for backwards compat
                "body_html": result.body_html,
                "asset_refs": result.asset_refs,
                "content_summary": result.content_summary,
                "slide_no": result.slide_no,
                "section": entry.section,
                "title": entry.title,
                "is_cover": entry.is_cover or entry.slide_no == 1,
                "is_chapter_divider": entry.is_chapter_divider,
            }
            slide_orm = Slide(
                project_id=project_id,
                package_id=package.id if package else None,
                outline_id=outline.id,
                binding_id=binding.id if binding else None,
                slide_no=result.slide_no,
                section=entry.section,
                title=entry.title,
                purpose=entry.purpose,
                key_message=entry.key_message,
                layout_template=None,
                spec_json=spec_json,
                source_refs_json=result.asset_refs,
                evidence_refs_json=list(binding.evidence_snippets or []) if binding else [],
                status=SlideStatus.SPEC_READY.value,
            )
        else:
            layout_spec = result
            slide_orm = Slide(
                project_id=project_id,
                package_id=package.id if package else None,
                outline_id=outline.id,
                binding_id=binding.id if binding else None,
                slide_no=layout_spec.slide_no,
                section=layout_spec.section,
                title=layout_spec.title,
                purpose=entry.purpose,
                key_message=entry.key_message,
                layout_template=None,
                spec_json=layout_spec.model_dump(mode="json"),
                source_refs_json=layout_spec.source_refs,
                evidence_refs_json=layout_spec.evidence_refs,
                status=SlideStatus.SPEC_READY.value,
            )

        db.add(slide_orm)
        saved_slides.append(slide_orm)

    # 7. 推进项目状态
    project = db.get(Project, project_id)
    if project:
        project.status = ProjectStatus.RENDERING.value
        project.current_phase = "rendering"

    db.commit()
    logger.info(
        f"compose_all_slides: saved {len(saved_slides)} slides "
        f"for project {project_id} (theme={theme.style_keywords})"
    )
    return saved_slides


def _default_theme(project_id: UUID) -> VisualTheme:
    """无 VisualTheme 时的兜底主题（避免崩溃）。"""
    from schema.visual_theme import (
        ColorSystem, TypographySystem, SpacingSystem, DecorationStyle, CoverStyle,
    )
    return VisualTheme(
        project_id=project_id,
        colors=ColorSystem(
            primary="#1C3A5F", secondary="#2D6A8F", accent="#E8A020",
            background="#F8F6F1", surface="#EDEAE3",
            text_primary="#1C1C1C", text_secondary="#6B6B6B",
            border="#D4D0C8", overlay="rgba(0,0,0,0.55)",
            cover_bg="linear-gradient(135deg, #1C3A5F 0%, #2D6A8F 100%)",
        ),
        typography=TypographySystem(
            font_heading="思源黑体", font_body="思源宋体", font_en="Inter",
            base_size=20, scale_ratio=1.25, heading_weight=700, body_weight=400,
            line_height_body=1.6, line_height_heading=1.15, letter_spacing_label="0.08em",
        ),
        spacing=SpacingSystem(base_unit=8, safe_margin=80, section_gap=48, element_gap=24, density="normal"),
        decoration=DecorationStyle(
            use_divider_lines=True, divider_weight="thin",
            color_fill_usage="subtle", border_radius="small",
            image_treatment="natural", accent_shape="line",
            background_texture="flat",
        ),
        cover=CoverStyle(layout_mood="split", title_on_dark=True, show_brief_metrics=True),
        style_keywords=["现代简约"],
        generation_prompt_hint="系统默认主题",
        color_mode="mixed",
        contrast_level="high",
        accent_saturation="high",
        font_mood="modern",
        visual_intensity="bold",
        color_strategy="high-contrast",
        composition_style="editorial",
        decorative_motif="architectural-lines",
        image_treatment="natural",
    )
