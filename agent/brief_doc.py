"""
Brief Doc Agent.

Prefers the latest material package when available; falls back to legacy assets
for backward compatibility.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.orm import Session

from config.llm import STRONG_MODEL, call_llm_with_limit
from db.models.asset import Asset
from db.models.brief_doc import BriefDoc
from db.models.material_item import MaterialItem
from db.models.material_package import MaterialPackage
from db.models.project import ProjectBrief

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "brief_doc_system.md"


class _ChapterEntry(BaseModel):
    chapter_id: str
    title: str
    key_findings: list[str] = []
    narrative_direction: str = ""


class _RecommendedEmphasis(BaseModel):
    policy_focus: str = ""
    site_advantage: str = ""
    competitive_edge: str = ""
    case_inspiration: str = ""


class _BriefDocLLMOutput(BaseModel):
    brief_title: str
    executive_summary: str
    chapters: list[_ChapterEntry] = []
    positioning_statement: str
    design_principles: list[str] = []
    recommended_emphasis: _RecommendedEmphasis = _RecommendedEmphasis()
    narrative_arc: str


def _load_system_prompt(brief: ProjectBrief) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    return (
        template
        .replace("{building_type}", brief.building_type or "building")
        .replace("{project_name}", brief.client_name or "未命名项目")
        .replace("{client_name}", brief.client_name or "")
        .replace("{city}", brief.city or "")
        .replace("{province}", brief.province or "")
        .replace("{style_preferences}", "、".join(brief.style_preferences or []))
    )


def _build_legacy_assets_message(assets: list[Asset]) -> str:
    sections: dict[str, list[dict]] = {}
    for asset in assets:
        key = f"{asset.asset_type}/{asset.subtype or 'general'}"
        sections.setdefault(key, []).append({
            "id": str(asset.id),
            "title": asset.title,
            "data": asset.data_json,
            "summary": asset.summary,
        })

    lines = ["<available_data>"]
    for section_key, items in sections.items():
        lines.append(f"\n### {section_key}")
        for item in items[:5]:
            lines.append(json.dumps(item, ensure_ascii=False))
    lines.append("</available_data>")
    return "\n".join(lines)


def _build_material_package_message(package: MaterialPackage, items: list[MaterialItem]) -> str:
    payload = {
        "package_id": str(package.id),
        "version": package.version,
        "summary": package.summary_json or {},
        "manifest": package.manifest_json or {},
        "text_items": [
            {
                "logical_key": item.logical_key,
                "title": item.title,
                "snippet": (item.text_content or "")[:240],
            }
            for item in items
            if item.text_content
        ][:15],
    }
    return f"<material_package>\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n</material_package>"


async def generate_brief_doc(project_id: UUID, db: Session) -> BriefDoc:
    brief = (
        db.query(ProjectBrief)
        .filter(ProjectBrief.project_id == project_id)
        .order_by(ProjectBrief.version.desc())
        .first()
    )
    if not brief:
        raise ValueError(f"No brief found for project {project_id}")

    package = (
        db.query(MaterialPackage)
        .filter(MaterialPackage.project_id == project_id)
        .order_by(MaterialPackage.version.desc())
        .first()
    )
    items: list[MaterialItem] = []
    if package:
        items = db.query(MaterialItem).filter(MaterialItem.package_id == package.id).all()
        user_message = _build_material_package_message(package, items)
    else:
        assets = db.query(Asset).filter(Asset.project_id == project_id).all()
        user_message = _build_legacy_assets_message(assets)

    system_prompt = _load_system_prompt(brief)
    logger.info("generate_brief_doc: calling LLM for project=%s package=%s", project_id, getattr(package, "id", None))

    try:
        result: _BriefDocLLMOutput = await call_llm_with_limit(
            system_prompt=system_prompt,
            user_message=user_message,
            output_schema=_BriefDocLLMOutput,
            model=STRONG_MODEL,
            temperature=0.5,
            max_tokens=8192,
        )
    except Exception as exc:
        logger.error("Brief Doc LLM failed: %s", exc)
        result = _fallback_brief_doc(brief, package.summary_json if package else None)

    existing = (
        db.query(BriefDoc)
        .filter(BriefDoc.project_id == project_id)
        .order_by(BriefDoc.version.desc())
        .first()
    )
    new_version = (existing.version + 1) if existing else 1

    evidence_keys = sorted({item.logical_key for item in items})[:50] if package else []
    brief_doc = BriefDoc(
        project_id=project_id,
        package_id=package.id if package else None,
        version=new_version,
        status="draft",
        outline_json=result.model_dump(mode="json"),
        narrative_summary=result.executive_summary,
        material_summary_json=package.summary_json if package else None,
        evidence_keys_json=evidence_keys,
    )
    db.add(brief_doc)
    db.commit()
    db.refresh(brief_doc)
    return brief_doc


def get_latest_brief_doc(project_id: UUID, db: Session) -> Optional[BriefDoc]:
    return (
        db.query(BriefDoc)
        .filter(BriefDoc.project_id == project_id)
        .order_by(BriefDoc.version.desc())
        .first()
    )


def _fallback_brief_doc(brief: ProjectBrief, material_summary: dict | None = None) -> _BriefDocLLMOutput:
    building_type = brief.building_type or "building"
    client = brief.client_name or "项目"
    city = brief.city or "本地"
    case_count = (material_summary or {}).get("case_count", 0)
    chart_count = (material_summary or {}).get("chart_count", 0)
    snippets = material_summary.get("evidence_snippets", []) if material_summary else []

    findings = []
    if case_count:
        findings.append(f"素材包包含 {case_count} 组参考案例")
    if chart_count:
        findings.append(f"素材包包含 {chart_count} 个经济图表")
    if snippets:
        findings.append("素材包提供了可直接引用的文本证据")
    if not findings:
        findings = ["基于素材包和项目基础信息生成建议书结构"]

    return _BriefDocLLMOutput(
        brief_title=f"{client} {building_type.title()} 设计建议书",
        executive_summary="；".join(findings),
        chapters=[
            _ChapterEntry(
                chapter_id="background",
                title="背景研究",
                key_findings=findings[:2],
                narrative_direction="先建立政策、经济和区位背景，再引出场地机会",
            ),
            _ChapterEntry(
                chapter_id="site",
                title="场地分析",
                key_findings=["围绕区位、交通、POI 和竞品进行综合分析"],
                narrative_direction="将素材包中的地图、POI 和分析文本整合为场地判断",
            ),
            _ChapterEntry(
                chapter_id="strategy",
                title="设计策略",
                key_findings=["结合案例启发输出定位、策略与方案方向"],
                narrative_direction="从案例映射项目定位，形成策略和方案章节",
            ),
        ],
        positioning_statement=f"{city} 的 {building_type} 项目，强调基于素材证据的设计建议书",
        design_principles=[
            "优先使用素材包中的图表、图片和案例证据",
            "所有关键页面应具备可追溯的内容来源",
            "缺素材时使用降级布局，不伪造核心内容",
        ],
        recommended_emphasis=_RecommendedEmphasis(
            site_advantage="突出场地与交通条件",
            competitive_edge="用案例映射项目差异化定位",
            case_inspiration="提炼素材包中的案例启示用于后续方案章节",
        ),
        narrative_arc="从背景与场地出发，过渡到竞品和案例，再落到定位、策略与方案表达。",
    )
