"""
Visual Theme Agent

案例偏好确认后触发，生成项目级 VisualTheme，存入 visual_themes 表。
"""
import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from config.llm import call_llm_structured, STRONG_MODEL
from schema.visual_theme import VisualTheme, VisualThemeInput
from db.models.visual_theme import VisualTheme as VisualThemeORM

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "visual_theme_system.md"


def _load_system_prompt() -> str:
    return _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def _build_user_message(inp: VisualThemeInput) -> str:
    return f"""请为以下建筑项目生成完整的视觉主题：

## 项目信息
- 项目名称：{inp.project_name}
- 委托方：{inp.client_name or "未知"}
- 建筑类型：{inp.building_type}

## 用户风格偏好
{chr(10).join(f"- {p}" for p in inp.style_preferences) if inp.style_preferences else "- 无特别指定"}

## 案例审美倾向
主要风格标签：{", ".join(inp.dominant_styles) if inp.dominant_styles else "未指定"}
主要特征标签：{", ".join(inp.dominant_features) if inp.dominant_features else "未指定"}

## 叙事基调
{inp.narrative_hint or "标准建筑汇报风格"}

请生成完整 VisualTheme JSON。project_id 使用：{inp.project_id}"""


async def generate_visual_theme(
    inp: VisualThemeInput,
    db: Session,
) -> VisualThemeORM:
    """
    生成 VisualTheme 并存入数据库。
    若该项目已有 draft 主题，则递增 version 覆盖。
    """
    system_prompt = _load_system_prompt()
    user_message = _build_user_message(inp)

    logger.info(f"Generating VisualTheme for project {inp.project_id}")

    theme: VisualTheme = await call_llm_structured(
        system_prompt=system_prompt,
        user_message=user_message,
        output_schema=VisualTheme,
        model=STRONG_MODEL,
        temperature=0.7,        # 允许一定创意
        max_tokens=4096,
    )

    # 确保 project_id 一致
    theme = theme.model_copy(update={"project_id": inp.project_id})

    # 字号安全护栏：1920×1080 画布上 base_size 不得低于 20px
    t = theme.typography
    clamped = {}
    if t.base_size < 20:
        clamped["base_size"] = 20
    elif t.base_size > 28:
        clamped["base_size"] = 28
    if t.scale_ratio < 1.2:
        clamped["scale_ratio"] = 1.25
    elif t.scale_ratio > 1.5:
        clamped["scale_ratio"] = 1.5
    if clamped:
        new_typo = t.model_copy(update=clamped)
        theme = theme.model_copy(update={"typography": new_typo})
        logger.info(f"Typography clamped: {clamped}")

    # 计算版本号
    existing = (
        db.query(VisualThemeORM)
        .filter(VisualThemeORM.project_id == inp.project_id)
        .order_by(VisualThemeORM.version.desc())
        .first()
    )
    version = (existing.version + 1) if existing else 1

    orm = VisualThemeORM(
        project_id=inp.project_id,
        version=version,
        status="draft",
        theme_json=theme.model_dump(mode="json"),
    )
    db.add(orm)
    db.commit()
    db.refresh(orm)

    logger.info(
        f"VisualTheme saved: id={orm.id}, project={inp.project_id}, "
        f"version={version}, keywords={theme.style_keywords}"
    )
    return orm


def get_latest_theme(project_id: UUID, db: Session) -> VisualTheme | None:
    """从 DB 读取最新 VisualTheme，反序列化为 Pydantic 模型。"""
    orm = (
        db.query(VisualThemeORM)
        .filter(VisualThemeORM.project_id == project_id)
        .order_by(VisualThemeORM.version.desc())
        .first()
    )
    if not orm:
        return None
    return VisualTheme.model_validate(orm.theme_json)


def build_theme_input_from_package(
    project_id: UUID,
    db: Session,
) -> VisualThemeInput:
    """
    从素材包和 ProjectBrief 构建 VisualThemeInput，
    用于在不经过 Reference Agent 的素材包管线中驱动主题生成。
    """
    from db.models.project import Project, ProjectBrief
    from db.models.material_item import MaterialItem
    from db.models.material_package import MaterialPackage

    project = db.get(Project, project_id)
    project_name = project.name if project else "未命名项目"

    brief = (
        db.query(ProjectBrief)
        .filter(ProjectBrief.project_id == project_id)
        .order_by(ProjectBrief.version.desc())
        .first()
    )
    building_type = brief.building_type if brief else "mixed"
    client_name = brief.client_name if brief else project_name
    style_prefs = (brief.style_preferences or []) if brief else []
    city = brief.city if brief else None

    package = (
        db.query(MaterialPackage)
        .filter(MaterialPackage.project_id == project_id)
        .order_by(MaterialPackage.version.desc())
        .first()
    )

    dominant_styles: list[str] = []
    dominant_features: list[str] = []
    narrative_hint = "标准建筑汇报风格"

    if package:
        analysis_items = (
            db.query(MaterialItem)
            .filter(
                MaterialItem.package_id == package.id,
                MaterialItem.logical_key.like("reference.case.%.analysis"),
            )
            .all()
        )
        analysis_texts = [item.text_content for item in analysis_items if item.text_content]

        if analysis_texts:
            dominant_styles = _extract_style_tags(analysis_texts)
            dominant_features = _extract_feature_tags(analysis_texts)

        design_outline = (
            db.query(MaterialItem)
            .filter(
                MaterialItem.package_id == package.id,
                MaterialItem.logical_key == "brief.design_outline",
            )
            .first()
        )
        if design_outline and design_outline.text_content:
            text = design_outline.text_content[:1000]
            if "文化特征" in text or "设计理念" in text or "风格" in text:
                narrative_hint = f"{building_type}类建筑方案汇报，{city or ''}项目"
                if style_prefs:
                    narrative_hint += f"，风格倾向：{'、'.join(style_prefs[:3])}"

    if not dominant_styles:
        dominant_styles = style_prefs[:3] if style_prefs else ["现代"]
    if not dominant_features:
        dominant_features = ["专业", "清晰"]

    return VisualThemeInput(
        project_id=project_id,
        building_type=building_type,
        style_preferences=style_prefs,
        dominant_styles=dominant_styles,
        dominant_features=dominant_features,
        narrative_hint=narrative_hint,
        project_name=project_name,
        client_name=client_name,
    )


_STYLE_KEYWORDS = [
    "极简", "简约", "现代", "参数化", "有机", "解构", "新中式", "中式",
    "工业", "粗野", "后现代", "古典", "巴洛克", "包豪斯", "北欧",
    "日式", "侘寂", "禅意", "自然", "生态", "可持续", "绿色",
    "科技", "未来", "数字", "通透", "开放", "内向", "围合",
]

_FEATURE_KEYWORDS = [
    "清水混凝土", "玻璃幕墙", "木结构", "钢结构", "坡屋顶", "平屋顶",
    "绿色屋顶", "庭院", "天井", "中庭", "连廊", "架空层", "悬挑",
    "错落", "层叠", "通高", "采光", "景观", "水景", "灰空间",
    "模块化", "装配式", "被动式", "光伏", "雨水回收",
]


def _extract_style_tags(texts: list[str]) -> list[str]:
    combined = " ".join(t[:500] for t in texts)
    found = [kw for kw in _STYLE_KEYWORDS if kw in combined]
    return found[:5] if found else []


def _extract_feature_tags(texts: list[str]) -> list[str]:
    combined = " ".join(t[:500] for t in texts)
    found = [kw for kw in _FEATURE_KEYWORDS if kw in combined]
    return found[:5] if found else []
