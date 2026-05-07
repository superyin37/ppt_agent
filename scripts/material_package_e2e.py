"""
End-to-end validator for the material-package driven PPT pipeline.

Usage:
  .venv\\Scripts\\python.exe scripts/material_package_e2e.py test_material/project1

By default the script runs in mock-LLM mode so it can validate the full
pipeline without external model calls. Use --real-llm to exercise live LLMs.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.brief_doc import generate_brief_doc
from agent.composer import ComposerMode, _default_theme, compose_all_slides, recompose_slide_html
from agent.concept_render import ConceptRenderStrictError, run_concept_render
from agent.critic import review_slide
from agent.material_binding import bind_outline_slides
from agent.outline import generate_outline
from agent.visual_theme import build_theme_input_from_package, generate_visual_theme, get_latest_theme
from db.models.asset import Asset
from db.models.brief_doc import BriefDoc
from db.models.project import Project, ProjectBrief
from db.models.slide import Slide
from db.session import SessionLocal
from render.engine import render_slide_html, render_slide_html_direct, render_slide_template
from render.exporter import compile_pdf, screenshot_slide
from schema.common import ProjectStatus, ReviewDecision, ReviewSeverity, SlideStatus
from schema.outline import OutlineSlideEntry, OutlineSpec
from schema.review import ReviewReport
from schema.visual_theme import LayoutSpec
from tool.material_pipeline import ingest_local_material_package

LOGGER = logging.getLogger("material_package_e2e")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the local material-package PPT pipeline.")
    parser.add_argument("material_path", help="Path to a local material package directory.")
    parser.add_argument(
        "--output-dir",
        default="tmp/material_package_e2e",
        help="Directory for generated artifacts and reports.",
    )
    parser.add_argument(
        "--project-name",
        default="Material Package E2E",
        help="Project name used for the temporary validation project.",
    )
    parser.add_argument(
        "--max-slides",
        type=int,
        default=None,
        help="Optional cap for rendered/reviewed slides to speed up smoke validation.",
    )
    parser.add_argument(
        "--real-llm",
        action="store_true",
        help="Use live LLM calls instead of fallback/mock mode.",
    )
    parser.add_argument(
        "--composer-mode",
        choices=["structured", "html", "template"],
        default="html",
        help=(
            "Composer output mode: 'structured' (v2 LayoutSpec), "
            "'html' (v3 direct HTML), or 'template' (v4 Jinja2 templates). "
            "Default: html."
        ),
    )
    parser.add_argument(
        "--design-review",
        action="store_true",
        help="Enable design advisor review (scores + improvement suggestions for each slide).",
    )
    parser.add_argument(
        "--skip-concept-render",
        action="store_true",
        help="Skip the concept render step (useful when runninghub is unreachable).",
    )
    parser.add_argument(
        "--allow-concept-placeholders",
        action="store_true",
        help=(
            "Allow concept_render placeholders to pass. By default real-LLM "
            "template E2E treats concept placeholders as a failure."
        ),
    )
    return parser.parse_args()


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def _ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _write_design_summary(path: Path, advices: list[dict]) -> None:
    """Write a human-readable design score summary."""
    if not advices:
        return
    scores = [a["overall_score"] for a in advices]
    avg = sum(scores) / len(scores)
    grade_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for a in advices:
        grade_counts[a.get("grade", "D")] = grade_counts.get(a.get("grade", "D"), 0) + 1

    # Count suggestion codes
    from collections import Counter
    code_counter: Counter[str] = Counter()
    for a in advices:
        for s in a.get("suggestions", []):
            code_counter[s.get("code", "D000")] += 1

    lines = [
        "=== Design Review Summary ===",
        f"Total slides reviewed: {len(advices)}",
        f"Average score: {avg:.1f} / 10",
        "",
        "Score distribution:",
    ]
    for grade in ["A", "B", "C", "D"]:
        cnt = grade_counts[grade]
        pct = cnt * 100 // len(advices) if advices else 0
        lines.append(f"  {grade}: {cnt:3d} slides ({pct}%)")

    if code_counter:
        lines.append("")
        lines.append("Top issues:")
        for code, count in code_counter.most_common(5):
            lines.append(f"  {code}: {count} occurrences")

    sorted_advices = sorted(advices, key=lambda a: a["overall_score"])
    lines.append("")
    lines.append("Weakest slides:")
    for a in sorted_advices[:3]:
        lines.append(f"  Slide {a['slide_no']:02d}: {a['overall_score']:.1f} ({a['grade']})")
    lines.append("")
    lines.append("Strongest slides:")
    for a in sorted_advices[-3:][::-1]:
        lines.append(f"  Slide {a['slide_no']:02d}: {a['overall_score']:.1f} ({a['grade']})")
    lines.append("")
    lines.append("Per-slide scores:")
    for a in advices:
        lines.append(f"  Slide {a['slide_no']:02d}: {a['overall_score']:.1f} ({a['grade']}) — {a.get('one_liner', '')}")

    _write_text(path, "\n".join(lines) + "\n")


def _audit_template_specs(specs: list[dict[str, Any]]) -> dict[str, Any]:
    critical: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    image_grid_refs: dict[tuple[str, ...], list[int]] = {}

    for spec in specs:
        slide_no = int(spec.get("slide_no") or 0)
        mode = spec.get("mode")
        data = spec.get("data") or {}
        component_type = spec.get("component_type") or data.get("component_type")
        text_blob = json.dumps(spec, ensure_ascii=False)

        if _contains_prompt_instruction(text_blob):
            critical.append({
                "slide_no": slide_no,
                "code": "prompt_text_leak",
                "message": f"slide {slide_no:02d} contains task/prompt text in final spec",
            })

        if mode == "html" and str(spec.get("content_summary") or "").startswith("Fallback"):
            critical.append({
                "slide_no": slide_no,
                "code": "html_fallback",
                "message": f"slide {slide_no:02d} fell back to generic HTML",
            })

        if component_type == "concept_scheme" and not data.get("image"):
            critical.append({
                "slide_no": slide_no,
                "code": "concept_image_missing",
                "message": f"slide {slide_no:02d} concept_scheme has no image",
            })

        refs = tuple(spec.get("asset_refs") or [])
        if component_type == "image_grid" and refs:
            image_grid_refs.setdefault(refs, []).append(slide_no)

    for refs, pages in image_grid_refs.items():
        if len(pages) > 1:
            critical.append({
                "slide_no": pages[0],
                "code": "repeated_image_grid_assets",
                "message": f"image_grid slides {pages} reuse the same asset set",
                "asset_refs": list(refs),
            })

    return {"critical_issues": critical, "warnings": warnings}


def _contains_prompt_instruction(text: str) -> bool:
    lowered = (text or "").lower()
    markers = (
        "[material package e2e",
        "调用 nanobanana",
        "nanobanana",
        "联网搜索",
        "生成封面",
        "生成目录",
        "请为该页面",
        "分析设计建议书大纲",
        "提供政策来源",
    )
    return any(marker in lowered for marker in markers)


def _mock_llm_stack() -> ExitStack:
    stack = ExitStack()
    mocked_error = RuntimeError("mock llm enabled for e2e validation")
    stack.enter_context(patch("agent.brief_doc.call_llm_with_limit", new=AsyncMock(side_effect=mocked_error)))
    stack.enter_context(patch("agent.outline.call_llm_with_limit", new=AsyncMock(side_effect=mocked_error)))
    stack.enter_context(patch("agent.composer.call_llm_with_limit", new=AsyncMock(side_effect=mocked_error)))
    stack.enter_context(patch("agent.composer_template.call_llm_with_limit", new=AsyncMock(side_effect=mocked_error)))
    stack.enter_context(patch("agent.visual_theme.call_llm_structured", new=AsyncMock(side_effect=mocked_error)))
    stack.enter_context(patch("tool.review.semantic_check.call_llm_with_limit", new=AsyncMock(side_effect=mocked_error)))
    return stack


def _trim_outline(outline, max_slides: int, db) -> None:
    spec = OutlineSpec.model_validate(outline.spec_json)
    slides = spec.slides[:max_slides]
    trimmed = spec.model_copy(
        update={
            "slides": slides,
            "total_pages": len(slides),
            "sections": list(dict.fromkeys(slide.section for slide in slides)),
        }
    )
    outline.spec_json = trimmed.model_dump(mode="json")
    outline.total_pages = trimmed.total_pages
    if outline.coverage_json:
        outline.coverage_json = {k: v for k, v in outline.coverage_json.items() if int(k) <= max_slides}
    if outline.slot_binding_hints_json:
        outline.slot_binding_hints_json = {
            k: v for k, v in outline.slot_binding_hints_json.items() if int(k) <= max_slides
        }
    db.flush()


def _asset_lookup(project_id, db) -> dict[str, dict]:
    assets = db.query(Asset).filter(Asset.project_id == project_id).all()
    return {
        str(asset.id): {
            "image_url": asset.image_url,
            "data_json": asset.data_json,
            "config_json": asset.config_json,
            "source_info": asset.source_info,
            "logical_key": asset.logical_key,
            "variant": asset.variant,
        }
        for asset in assets
    }


def _binding_payload(bindings) -> list[dict[str, Any]]:
    return [
        {
            "id": str(binding.id),
            "slide_no": binding.slide_no,
            "slot_id": binding.slot_id,
            "version": binding.version,
            "status": binding.status,
            "must_use_item_ids": binding.must_use_item_ids or [],
            "optional_item_ids": binding.optional_item_ids or [],
            "derived_asset_ids": binding.derived_asset_ids or [],
            "coverage_score": binding.coverage_score,
            "missing_requirements": binding.missing_requirements or [],
            "evidence_snippets": binding.evidence_snippets or [],
            "binding_reason": binding.binding_reason,
        }
        for binding in bindings
    ]


def _brief_dict(project_id, db) -> dict[str, Any]:
    brief = (
        db.query(ProjectBrief)
        .filter(ProjectBrief.project_id == project_id)
        .order_by(ProjectBrief.version.desc())
        .first()
    )
    if not brief:
        return {}
    brief_doc = (
        db.query(BriefDoc)
        .filter(BriefDoc.project_id == project_id)
        .order_by(BriefDoc.version.desc())
        .first()
    )
    return {
        "building_type": brief.building_type,
        "client_name": brief.client_name,
        "style_preferences": brief.style_preferences or [],
        "province": brief.province,
        "city": brief.city,
        "district": brief.district,
        "site_address": brief.site_address,
        "gross_floor_area": float(brief.gross_floor_area) if brief.gross_floor_area else None,
        "site_area": float(brief.site_area) if brief.site_area else None,
        "far": float(brief.far) if brief.far else None,
        "brief_doc_outline": brief_doc.outline_json if brief_doc else {},
        "brief_doc_summary": brief_doc.narrative_summary if brief_doc else "",
    }


async def _render_and_review(
    project_id,
    outline,
    output_dir: Path,
    db,
    *,
    design_review: bool = False,
    skip_review: bool = False,
) -> dict[str, Any]:
    MAX_REPAIR_ROUNDS = 2
    slides_dir = _ensure_directory(output_dir / "slides")
    slides = (
        db.query(Slide)
        .filter(Slide.project_id == project_id, Slide.outline_id == outline.id)
        .order_by(Slide.slide_no.asc())
        .all()
    )
    theme = get_latest_theme(project_id, db) or _default_theme(project_id)
    assets = _asset_lookup(project_id, db)
    brief = _brief_dict(project_id, db)
    deck_meta = {
        "deck_title": outline.deck_title,
        "client_name": brief.get("client_name", ""),
        "total_slides": len(slides),
    }

    # Build outline entry lookup for recompose
    outline_spec = OutlineSpec.model_validate(outline.spec_json)
    entry_by_slide_no: dict[int, OutlineSlideEntry] = {
        e.slide_no: e for e in outline_spec.slides
    }

    plan = None
    brief_orm = (
        db.query(ProjectBrief)
        .filter(ProjectBrief.project_id == project_id)
        .order_by(ProjectBrief.version.desc())
        .first()
    )
    if brief_orm:
        try:
            from agent.slide_plan import build_slide_plan

            section_colors = list(getattr(theme, "section_colors", None) or [])
            plan = build_slide_plan(outline, brief_orm, section_colors=section_colors)
        except Exception as exc:
            LOGGER.warning("failed to build SlidePlan for template render: %s", exc)

    # Build theme colors dict for design advisor
    theme_colors = {}
    if hasattr(theme, 'palette'):
        p = theme.palette
        theme_colors = {
            "primary": getattr(p, 'primary', ''),
            "secondary": getattr(p, 'secondary', ''),
            "accent": getattr(p, 'accent', ''),
        }

    review_reports: list[dict[str, Any]] = []
    design_advices: list[dict[str, Any]] = []
    png_bytes_list: list[bytes] = []
    rendered_count = 0
    for slide in slides:
        spec_json = slide.spec_json or {}
        mode = spec_json.get("mode")
        is_template_mode = mode == "template"
        is_html_mode = mode == "html" or spec_json.get("html_mode", False)

        # ── initial render ──
        if is_template_mode:
            html = render_slide_template(
                spec_json=spec_json,
                theme=theme,
                plan=plan,
                assets=assets,
            )
        elif is_html_mode:
            html = render_slide_html_direct(
                body_html=spec_json.get("body_html", ""),
                theme=theme,
                assets=assets,
                deck_meta=deck_meta,
                slide_no=slide.slide_no or 0,
                total_slides=len(slides),
            )
        else:
            spec = LayoutSpec.model_validate(spec_json)
            html = render_slide_html(spec, theme=theme, assets=assets, deck_meta=deck_meta)
        html_path = slides_dir / f"slide_{slide.slide_no:02d}.html"
        png_path = slides_dir / f"slide_{slide.slide_no:02d}.png"

        png_bytes = await screenshot_slide(html)
        html_path.write_text(html, encoding="utf-8")
        png_path.write_bytes(png_bytes)

        slide.html_content = html[:65535]
        slide.screenshot_url = str(png_path.resolve())
        slide.status = SlideStatus.RENDERED.value
        rendered_count += 1

        # Determine page_type and content_summary for design advisor
        page_type = "content"
        content_summary = spec_json.get("content_summary", slide.title or "")
        if spec_json.get("is_cover") or (slide.slide_no == 1):
            page_type = "cover"
        elif spec_json.get("is_chapter_divider"):
            page_type = "chapter_divider"

        # ── review → recompose → re-render loop ──
        repair_round = 0
        report = None
        while True:
            if skip_review:
                report = ReviewReport(
                    target_type="slide",
                    target_id=UUID(int=0),
                    review_layer="mock",
                    severity=ReviewSeverity.PASS,
                    issues=[],
                    final_decision=ReviewDecision.PASS,
                    repair_plan=[],
                )
                break

            # Only run design_advisor on the final round
            design_advisor_kwargs = {}
            if design_review and repair_round >= MAX_REPAIR_ROUNDS:
                design_advisor_kwargs = {
                    "design_advisor": True,
                    "page_type": page_type,
                    "content_summary": content_summary,
                    "theme_colors": theme_colors,
                }

            if is_html_mode or is_template_mode:
                # HTML/template 模式：跳过 rule lint（fallback_spec 是假数据，会产生 phantom issues），只用 vision
                from schema.visual_theme import SingleColumnLayout, ContentBlock, RegionBinding
                fallback_spec = LayoutSpec(
                    slide_no=slide.slide_no or 0,
                    primitive=SingleColumnLayout(primitive="single-column", max_width_ratio=0.8, v_align="top", has_pull_quote=False),
                    region_bindings=[RegionBinding(region_id="content", blocks=[
                        ContentBlock(block_id="title", content_type="heading", content=slide.title or ""),
                    ])],
                    visual_focus="content",
                    section=slide.section or "",
                    title=slide.title or "",
                )
                repaired_spec, report = await review_slide(
                    spec=fallback_spec,
                    brief=brief,
                    layers=["vision"],
                    screenshot_url=str(png_path.resolve()),
                    **design_advisor_kwargs,
                )
            else:
                repaired_spec, report = await review_slide(
                    spec=spec,
                    brief=brief,
                    layers=["rule", "semantic", "vision"],
                    screenshot_url=str(png_path.resolve()),
                    **design_advisor_kwargs,
                )
                slide.spec_json = repaired_spec.model_dump(mode="json")
                slide.source_refs_json = repaired_spec.source_refs
                slide.evidence_refs_json = repaired_spec.evidence_refs

            # If PASS or max rounds reached, exit loop
            if report.final_decision == ReviewDecision.PASS or repair_round >= MAX_REPAIR_ROUNDS:
                break

            # ── HTML recompose ──
            if is_html_mode:
                entry = entry_by_slide_no.get(slide.slide_no or 0)
                if entry and report.issues:
                    try:
                        LOGGER.info(
                            "slide_%02d: REPAIR_REQUIRED (round %d/%d), recomposing HTML...",
                            slide.slide_no, repair_round + 1, MAX_REPAIR_ROUNDS,
                        )
                        new_output = await recompose_slide_html(
                            original_html=spec_json.get("body_html", ""),
                            issues=[iss.model_dump(mode="json") for iss in report.issues],
                            entry=entry,
                            theme=theme,
                            brief_dict=brief,
                        )
                        # Update spec_json with recomposed HTML
                        spec_json = {
                            **spec_json,
                            "body_html": new_output.body_html,
                            "asset_refs": new_output.asset_refs,
                            "content_summary": new_output.content_summary,
                        }
                        slide.spec_json = spec_json

                        # Re-render
                        html = render_slide_html_direct(
                            body_html=new_output.body_html,
                            theme=theme,
                            assets=assets,
                            deck_meta=deck_meta,
                            slide_no=slide.slide_no or 0,
                            total_slides=len(slides),
                        )
                        png_bytes = await screenshot_slide(html)
                        html_path.write_text(html, encoding="utf-8")
                        png_path.write_bytes(png_bytes)
                        slide.html_content = html[:65535]
                        slide.screenshot_url = str(png_path.resolve())
                    except Exception as exc:
                        LOGGER.warning("Recompose failed for slide %s (round %d): %s", slide.slide_no, repair_round + 1, exc)
                        break
                else:
                    break  # no entry or no issues, nothing to recompose
            elif is_template_mode:
                # Template-mode local repair is not implemented in this brief.
                # Keep the rendered screenshot and record the review result.
                break
            else:
                # v2 structured: spec already updated by review_slide, re-render
                spec = LayoutSpec.model_validate(slide.spec_json)
                html = render_slide_html(spec, theme=theme, assets=assets, deck_meta=deck_meta)
                png_bytes = await screenshot_slide(html)
                html_path.write_text(html, encoding="utf-8")
                png_path.write_bytes(png_bytes)
                slide.html_content = html[:65535]

            repair_round += 1

        # Ensure the final accepted screenshot gets a design score when requested.
        if design_review and report and not report.design_advice:
            _, da_report = await review_slide(
                spec=fallback_spec if (is_html_mode or is_template_mode) else LayoutSpec.model_validate(slide.spec_json),
                brief=brief,
                layers=[],
                screenshot_url=str(png_path.resolve()),
                design_advisor=True,
                page_type=page_type,
                content_summary=content_summary,
                theme_colors=theme_colors,
            )
            if da_report.design_advice:
                report.design_advice = da_report.design_advice

        # Use the last screenshot for PDF
        png_bytes_list.append(png_bytes)

        slide.status = (
            SlideStatus.REVIEW_PASSED.value
            if report.final_decision == ReviewDecision.PASS
            else SlideStatus.REPAIR_NEEDED.value
        )
        review_reports.append(report.model_dump(mode="json"))
        if report.design_advice:
            design_advices.append(report.design_advice.model_dump(mode="json"))

    project = db.get(Project, project_id)
    if project:
        project.status = ProjectStatus.READY_FOR_EXPORT.value
        project.current_phase = "review_complete"
    db.commit()

    pdf_bytes = await compile_pdf(png_bytes_list)
    pdf_path = output_dir / "deck.pdf"
    pdf_path.write_bytes(pdf_bytes)

    _write_json(output_dir / "review_reports.json", review_reports)

    # Write design advisor outputs
    if design_advices:
        _write_json(output_dir / "design_scores.json", design_advices)
        _write_design_summary(output_dir / "design_scores_summary.txt", design_advices)

    return {
        "rendered_slide_count": rendered_count,
        "review_reports": review_reports,
        "design_advices": design_advices,
        "pdf_path": str(pdf_path.resolve()),
    }


async def run_validation(args: argparse.Namespace) -> int:
    material_path = Path(args.material_path).resolve()
    if not material_path.exists() or not material_path.is_dir():
        raise FileNotFoundError(f"Material package path not found or not a directory: {material_path}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = _ensure_directory(Path(args.output_dir).resolve() / f"run_{timestamp}")
    _ensure_directory(output_dir / "slides")

    summary: dict[str, Any] = {
        "material_path": str(material_path),
        "output_dir": str(output_dir),
        "mode": "real-llm" if args.real_llm else "mock-llm",
        "steps": [],
    }

    db = SessionLocal()
    llm_stack = ExitStack()
    if not args.real_llm:
        llm_stack = _mock_llm_stack()

    try:
        project = Project(name=args.project_name, status=ProjectStatus.INIT.value)
        db.add(project)
        db.commit()
        db.refresh(project)
        summary["project_id"] = str(project.id)
        summary["steps"].append({"step": "create_project", "status": "ok"})
        LOGGER.info("created project %s", project.id)

        package = ingest_local_material_package(project.id, str(material_path), db)
        db.commit()
        db.refresh(package)
        summary["package_id"] = str(package.id)
        summary["steps"].append(
            {
                "step": "ingest_material_package",
                "status": "ok",
                "item_count": package.summary_json.get("item_count", 0) if package.summary_json else 0,
            }
        )
        _write_json(output_dir / "material_package_manifest.json", package.manifest_json or {})
        _write_json(output_dir / "material_package_summary.json", package.summary_json or {})

        brief_doc = await generate_brief_doc(project.id, db)
        summary["steps"].append({"step": "generate_brief_doc", "status": "ok"})
        _write_json(output_dir / "brief_doc.json", brief_doc.outline_json)

        # --- Visual Theme Generation ---
        try:
            theme_input = build_theme_input_from_package(project.id, db)
            theme_orm = await generate_visual_theme(inp=theme_input, db=db)
            summary["steps"].append({
                "step": "generate_visual_theme",
                "status": "ok",
                "style_keywords": theme_orm.theme_json.get("style_keywords", []) if theme_orm.theme_json else [],
            })
            _write_json(output_dir / "visual_theme.json", theme_orm.theme_json or {})
            LOGGER.info("visual theme generated for project %s", project.id)
        except Exception as e:
            LOGGER.warning("visual theme generation failed, will use default: %s", e)
            summary["steps"].append({"step": "generate_visual_theme", "status": "fallback", "error": str(e)})

        outline = await generate_outline(project.id, db)
        if args.max_slides and args.max_slides > 0:
            _trim_outline(outline, args.max_slides, db)
            db.commit()
            db.refresh(outline)
        outline.status = "confirmed"
        outline.confirmed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(outline)
        summary["steps"].append(
            {
                "step": "generate_outline",
                "status": "ok",
                "total_pages": outline.total_pages,
            }
        )
        _write_json(output_dir / "outline.json", outline.spec_json)

        if args.skip_concept_render:
            summary["steps"].append({"step": "concept_render", "status": "skipped"})
        else:
            strict_concept_render = bool(args.real_llm and not args.allow_concept_placeholders)
            try:
                cr_stats = await run_concept_render(
                    project.id,
                    db,
                    strict=strict_concept_render,
                    reuse_existing=True,
                )
                db.commit()
                summary["steps"].append(
                    {
                        "step": "concept_render",
                        "status": "ok",
                        "total": cr_stats.total,
                        "generated": cr_stats.generated,
                        "placeholders": cr_stats.placeholders,
                        "reused": cr_stats.reused,
                        "strict": strict_concept_render,
                    }
                )
                if strict_concept_render and cr_stats.total and cr_stats.placeholders:
                    raise RuntimeError(
                        "strict concept render failed: "
                        f"{cr_stats.placeholders}/{cr_stats.total} placeholders"
                    )
            except ConceptRenderStrictError as exc:
                db.rollback()
                cr_stats = exc.stats
                summary["steps"].append(
                    {
                        "step": "concept_render",
                        "status": "failed",
                        "total": cr_stats.total,
                        "generated": cr_stats.generated,
                        "placeholders": cr_stats.placeholders,
                        "reused": cr_stats.reused,
                        "strict": strict_concept_render,
                        "failures": cr_stats.failures or [],
                        "error": str(exc),
                    }
                )
                raise
            except Exception as exc:
                db.rollback()
                if strict_concept_render:
                    LOGGER.exception("strict concept_render failed")
                    raise
                LOGGER.warning("concept_render failed, continuing without images: %s", exc)
                summary["steps"].append({"step": "concept_render", "status": "failed", "error": str(exc)})

        bindings = bind_outline_slides(project.id, outline.id, db)
        db.commit()
        summary["steps"].append(
            {
                "step": "bind_slides",
                "status": "ok",
                "binding_count": len(bindings),
            }
        )
        _write_json(output_dir / "bindings.json", _binding_payload(bindings))

        composer_mode = ComposerMode(args.composer_mode)
        slides = await compose_all_slides(project.id, db, mode=composer_mode)
        db.commit()
        mode_counts: dict[str, int] = {}
        for slide in slides:
            mode = (slide.spec_json or {}).get("mode") or "layout_spec"
            mode_counts[mode] = mode_counts.get(mode, 0) + 1
        summary["steps"].append(
            {
                "step": "compose_slides",
                "status": "ok",
                "slide_count": len(slides),
                "mode_counts": mode_counts,
            }
        )
        _write_json(output_dir / "slides_spec.json", [slide.spec_json for slide in slides])
        if composer_mode == ComposerMode.TEMPLATE:
            quality_report = _audit_template_specs([slide.spec_json for slide in slides])
            _write_json(output_dir / "template_quality_report.json", quality_report)
            summary["steps"].append({
                "step": "template_quality",
                "status": "ok" if not quality_report["critical_issues"] else "failed",
                "critical_issue_count": len(quality_report["critical_issues"]),
            })
            if quality_report["critical_issues"]:
                raise RuntimeError(
                    "template quality gate failed: "
                    + "; ".join(issue["message"] for issue in quality_report["critical_issues"][:5])
                )

        render_result = await _render_and_review(
            project.id,
            outline,
            output_dir,
            db,
            design_review=args.design_review,
            skip_review=not args.real_llm,
        )
        summary["steps"].append(
            {
                "step": "render_and_review",
                "status": "ok",
                "rendered_slide_count": render_result["rendered_slide_count"],
            }
        )
        summary["steps"].append(
            {
                "step": "export_pdf",
                "status": "ok",
                "pdf_path": render_result["pdf_path"],
            }
        )

        _write_json(output_dir / "summary.json", summary)
        _write_text(
            output_dir / "summary.txt",
            "\n".join(
                [
                    f"project_id: {summary['project_id']}",
                    f"package_id: {summary['package_id']}",
                    f"mode: {summary['mode']}",
                    f"output_dir: {summary['output_dir']}",
                    *[
                        f"{step['step']}: {step['status']}"
                        + (
                            f" ({step['slide_count']} slides)"
                            if "slide_count" in step
                            else f" ({step['binding_count']} bindings)"
                            if "binding_count" in step
                            else f" ({step['rendered_slide_count']} rendered)"
                            if "rendered_slide_count" in step
                            else f" ({step['pdf_path']})"
                            if "pdf_path" in step
                            else f" ({step['item_count']} items)"
                            if "item_count" in step
                            else f" ({step['total_pages']} pages)"
                            if "total_pages" in step
                            else ""
                        )
                        for step in summary["steps"]
                    ],
                ]
            ),
        )

        LOGGER.info("validation succeeded, output in %s", output_dir)
        return 0
    except Exception as exc:
        db.rollback()
        summary["steps"].append({"step": "pipeline", "status": "failed", "error": str(exc)})
        _write_json(output_dir / "summary.json", summary)
        LOGGER.exception("validation failed")
        return 1
    finally:
        llm_stack.close()
        db.close()


def main() -> int:
    _setup_logging()
    args = _parse_args()
    return asyncio.run(run_validation(args))


if __name__ == "__main__":
    raise SystemExit(main())
