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
from pathlib import Path
from uuid import UUID
from typing import Any, Optional, Union
from pydantic import BaseModel

from sqlalchemy.orm import Session

from config.llm import STRONG_MODEL, call_llm_with_limit
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
from db.models.project import Project, ProjectBrief
from db.models.outline import Outline
from db.models.slide import Slide
from db.models.asset import Asset
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
        f"请根据审查反馈修改 HTML，修复上述问题。保留整体布局和设计风格，只修正有问题的部分。"
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
    if is_cover:
        html = f"""<div class="slide-root" style="background:var(--color-cover-bg);display:flex;align-items:center;justify-content:center;flex-direction:column;padding:var(--safe-margin);">
  <h1 style="font-family:var(--font-heading);font-size:var(--text-display);color:#fff;text-align:center;">{entry.title}</h1>
  <p style="font-family:var(--font-body);font-size:var(--text-h2);color:rgba(255,255,255,0.8);margin-top:var(--element-gap);">{entry.key_message or ''}</p>
</div>"""
    elif entry.is_chapter_divider:
        html = f"""<div class="slide-root" style="background:var(--color-primary);display:flex;align-items:center;justify-content:center;flex-direction:column;">
  <h1 style="font-family:var(--font-heading);font-size:var(--text-display);color:#fff;">{entry.title}</h1>
  <p style="font-family:var(--font-en);font-size:var(--text-h3);color:rgba(255,255,255,0.6);margin-top:var(--element-gap);">{entry.section}</p>
</div>"""
    else:
        html = f"""<div class="slide-root" style="padding:var(--safe-margin);display:flex;flex-direction:column;justify-content:center;">
  <h2 style="font-family:var(--font-heading);font-size:var(--text-h1);color:var(--color-text-primary);margin-bottom:var(--section-gap);">{entry.title}</h2>
  <p style="font-family:var(--font-body);font-size:var(--text-body);color:var(--color-text-primary);line-height:var(--line-height-body);">{entry.key_message or ''}</p>
</div>"""
    return _ComposerHTMLOutput(
        slide_no=entry.slide_no,
        body_html=html,
        asset_refs=[],
        content_summary=f"Fallback: {entry.title}",
    )


async def compose_slide(
    entry: OutlineSlideEntry,
    theme: VisualTheme,
    brief_dict: dict,
    asset_summary: list[dict],
    binding: Optional[SlideMaterialBinding] = None,
    mode: ComposerMode = ComposerMode.STRUCTURED,
) -> LayoutSpec | _ComposerHTMLOutput:
    """
    单页合成入口（双模式）。

    mode=STRUCTURED: 返回 LayoutSpec（v2）
    mode=HTML:       返回 _ComposerHTMLOutput（v3）
    """
    if mode == ComposerMode.HTML:
        try:
            return await _compose_slide_html(entry, theme, brief_dict, asset_summary, binding)
        except Exception as e:
            logger.warning(f"Composer LLM (html) failed for slide {entry.slide_no}: {e}")
            return _html_fallback(entry)
    else:
        return await _compose_slide_structured(entry, theme, brief_dict, asset_summary, binding)


# ─────────────────────────────────────────────
# 主函数
# ─────────────────────────────────────────────

async def compose_all_slides(
    project_id: UUID,
    db: Session,
    mode: ComposerMode = ComposerMode.STRUCTURED,
) -> list[Slide]:
    """
    为项目所有幻灯片生成 LayoutSpec / HTML，保存到 slides 表。
    需要项目已有 Outline 和 VisualTheme。

    mode=STRUCTURED: v2 — 输出 LayoutSpec JSON
    mode=HTML:       v3 — 输出 body_html，spec_json 存 {"html_mode": true, "body_html": ...}
    """
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
    brief_dict = {
        "building_type": brief.building_type if brief else "",
        "client_name": brief.client_name if brief else "",
        "style_preferences": (brief.style_preferences or []) if brief else [],
        "city": brief.city if brief else "",
        "gross_floor_area": float(brief.gross_floor_area) if brief and brief.gross_floor_area else None,
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
         "title": a.title, "image_url": a.image_url, "asset_ref": f"asset:{a.id}"}
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
    tasks = [
        compose_slide(
            entry,
            theme,
            brief_dict,
            [asset for asset in all_asset_summary if not binding_by_slide_no.get(entry.slide_no) or asset["id"] in set(binding_by_slide_no[entry.slide_no].derived_asset_ids or [])],
            binding_by_slide_no.get(entry.slide_no),
            mode=mode,
        )
        for entry in outline_spec.slides
    ]
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
            if mode == ComposerMode.HTML:
                result = _html_fallback(entry)
            else:
                result = _fallback_layout_spec(entry)

        # 根据模式构造 spec_json
        if mode == ComposerMode.HTML and isinstance(result, _ComposerHTMLOutput):
            spec_json = {
                "html_mode": True,
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
    )
