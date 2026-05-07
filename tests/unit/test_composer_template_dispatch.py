"""Unit tests for Composer template-mode dispatch (PR-2 / ADR-006).

Verifies:
- TEMPLATE mode routes through compose_template_slide when blueprint
  declares a template_component
- TEMPLATE mode falls back to v3 HTML when slot has no template_component
- TEMPLATE mode falls back to v3 HTML on TemplateModeError
- spec_json is shaped correctly for each output type
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from types import SimpleNamespace

import pytest

from agent.composer import (
    ComposerMode,
    _ComposerHTMLOutput,
    _ComposerTemplateOutput,
    _assets_for_entry,
    _compose_policy_list_data,
    _looks_like_task_instruction,
    _preview_rows_from_asset,
    _select_image_grid_assets,
    compose_slide,
    resolve_composer_mode,
)
from agent.composer_template import TemplateModeError
from schema.outline import OutlineSlideEntry, OutlineSpec
from schema.slide_data import Bullet, ComponentType, ContentBulletsData, EndingData


def _entry(slot_id: str, slide_no: int = 1) -> OutlineSlideEntry:
    return OutlineSlideEntry(
        slot_id=slot_id,
        slide_no=slide_no,
        section="结尾",
        title="谢谢",
        purpose="closing slide",
        key_message="see you next time",
    )


def _outline(pid, entries: list[OutlineSlideEntry]) -> OutlineSpec:
    return OutlineSpec(
        project_id=pid,
        deck_title="Template Deck",
        theme="architecture",
        total_pages=len(entries),
        sections=list(dict.fromkeys(e.section for e in entries)),
        slides=entries,
    )


def _theme():
    from agent.composer import _default_theme
    return _default_theme(uuid4())


def _ending_data() -> EndingData:
    return EndingData(
        title="THANK YOU",
        en="GRACIAS",
        tagline="see you next time",
        signature_parts=["Test", "Agent", "2026"],
    )


def _content_bullets_data() -> ContentBulletsData:
    return ContentBulletsData(
        title="项目定位",
        lede="综合场地与政策背景形成设计判断。",
        bullets=[
            Bullet(title="区位", body="核心片区具备稳定公共服务需求。"),
            Bullet(title="文化", body="地域符号可转译为材料与空间语言。"),
            Bullet(title="运营", body="紧凑面积下强调高效维护和智慧管理。"),
        ],
    )


def test_resolve_composer_mode_accepts_template():
    assert resolve_composer_mode("template") is ComposerMode.TEMPLATE
    assert resolve_composer_mode(ComposerMode.TEMPLATE) is ComposerMode.TEMPLATE


def test_template_mode_routes_to_template_when_slot_has_component():
    """When PageSlot.template_component != None, TEMPLATE mode should call
    compose_template_slide and return _ComposerTemplateOutput."""
    entry = _entry("project-positioning")  # CONTENT_BULLETS, not deterministic
    theme = _theme()
    fake = _content_bullets_data()

    # Patch at the source module — composer.py imports it lazily inside the
    # _compose_slide_template helper, so we target composer_template directly.
    with patch("agent.composer_template.compose_template_slide", new=AsyncMock(return_value=fake)) as mock_tpl, \
         patch("agent.composer._compose_slide_html", new=AsyncMock()) as mock_html:
        result = asyncio.run(compose_slide(
            entry, theme, brief_dict={}, asset_summary=[], mode=ComposerMode.TEMPLATE,
        ))
        # Composer template-mode goes through composer_template; verify import path.
        assert mock_tpl.called
        assert not mock_html.called
        assert isinstance(result, _ComposerTemplateOutput)
        assert result.component_type == "content_bullets"
        assert result.data["title"] == "项目定位"


def test_template_mode_falls_back_to_html_when_no_template_component():
    """An unknown / None-template slot should bypass compose_template_slide
    and route to v3 HTML mode."""
    entry = _entry("totally-unknown-slot")
    theme = _theme()

    fake_html = _ComposerHTMLOutput(slide_no=1, body_html="<div>fake</div>")
    with patch("agent.composer_template.compose_template_slide", new=AsyncMock()) as mock_tpl, \
         patch("agent.composer._compose_slide_html", new=AsyncMock(return_value=fake_html)) as mock_html:
        result = asyncio.run(compose_slide(
            entry, theme, brief_dict={}, asset_summary=[], mode=ComposerMode.TEMPLATE,
        ))
        assert not mock_tpl.called  # never reached for unknown slots
        assert mock_html.called
        assert isinstance(result, _ComposerHTMLOutput)


def test_template_mode_falls_back_to_html_on_template_error():
    """If compose_template_slide raises TemplateModeError, the dispatcher
    must fall back to v3 HTML for that slide rather than failing the page."""
    entry = _entry("project-positioning")  # has CONTENT_BULLETS component
    theme = _theme()

    fake_html = _ComposerHTMLOutput(slide_no=1, body_html="<div>fallback</div>")
    with patch(
        "agent.composer_template.compose_template_slide",
        new=AsyncMock(side_effect=TemplateModeError("LLM truly failed")),
    ) as mock_tpl, patch(
        "agent.composer._compose_slide_html", new=AsyncMock(return_value=fake_html)
    ) as mock_html:
        result = asyncio.run(compose_slide(
            entry, theme, brief_dict={}, asset_summary=[], mode=ComposerMode.TEMPLATE,
        ))
        assert mock_tpl.called
        assert mock_html.called
        assert isinstance(result, _ComposerHTMLOutput)


def test_html_mode_unaffected_by_template_changes():
    """Sanity: HTML mode still routes straight to v3, ignoring template path."""
    entry = _entry("closing")
    theme = _theme()
    fake_html = _ComposerHTMLOutput(slide_no=1, body_html="<div>v3</div>")
    with patch("agent.composer_template.compose_template_slide", new=AsyncMock()) as mock_tpl, \
         patch("agent.composer._compose_slide_html", new=AsyncMock(return_value=fake_html)) as mock_html:
        result = asyncio.run(compose_slide(
            entry, theme, brief_dict={}, asset_summary=[], mode=ComposerMode.HTML,
        ))
        assert not mock_tpl.called
        assert mock_html.called
        assert isinstance(result, _ComposerHTMLOutput)


def test_template_mode_concept_aerial_uses_concept_asset_without_llm():
    """concept-aerial is the PR-3 deterministic path: proposal text comes
    from outline.spec_json and the image comes from Asset.logical_key.
    """
    pid = uuid4()
    theme = _theme()
    entries = [
        _entry("concept-aerial-1", slide_no=29),
        _entry("concept-aerial-2", slide_no=30),
        _entry("concept-aerial-3", slide_no=31),
    ]
    outline_spec = OutlineSpec(
        project_id=pid,
        deck_title="Concept Deck",
        theme="architecture",
        total_pages=3,
        sections=["概念方案"],
        slides=entries,
    )
    outline_json = {
        **outline_spec.model_dump(mode="json"),
        "concept_proposals": [
            {
                "index": 1,
                "name": "云上之城",
                "design_idea": "漂浮庭院与退台城市客厅",
                "narrative": "以层叠退台组织公共界面，形成连续的城市客厅与空中花园。",
                "design_keywords": ["terrace", "garden"],
                "massing_hint": "退台体量",
                "material_hint": "玻璃与金属格栅",
                "mood_hint": "轻盈",
            },
            {
                "index": 2,
                "name": "山水院落",
                "design_idea": "围合院落与山水界面",
                "narrative": "以院落组织动线，将场地记忆转译为空间序列。",
                "design_keywords": ["courtyard"],
                "massing_hint": "围合体量",
                "material_hint": "石材与木格栅",
                "mood_hint": "温润",
            },
            {
                "index": 3,
                "name": "光影廊桥",
                "design_idea": "廊桥串联开放公共层",
                "narrative": "以连桥连接功能簇，形成具有识别度的公共空间骨架。",
                "design_keywords": ["bridge"],
                "massing_hint": "连桥体量",
                "material_hint": "清水混凝土",
                "mood_hint": "克制",
            },
        ],
    }
    fake_asset_id = uuid4()
    fake_asset = SimpleNamespace(id=fake_asset_id)

    with patch("agent.composer_template.compose_template_slide", new=AsyncMock()) as mock_tpl, \
         patch("agent.composer._compose_slide_html", new=AsyncMock()) as mock_html, \
         patch("agent.composer._find_concept_asset", return_value=fake_asset) as mock_find:
        result = asyncio.run(compose_slide(
            entries[1],
            theme,
            brief_dict={},
            asset_summary=[],
            mode=ComposerMode.TEMPLATE,
            project_id=pid,
            db=object(),
            outline_spec=outline_spec,
            outline_json=outline_json,
        ))

    assert isinstance(result, _ComposerTemplateOutput)
    assert not mock_tpl.called
    assert not mock_html.called
    assert mock_find.call_args.kwargs["proposal_index"] == 2
    assert result.component_type == ComponentType.CONCEPT_SCHEME.value
    assert result.data["scheme_idx"] == 1
    assert result.data["scheme_name"] == "山水院落"
    assert result.data["view"] == "aerial"
    assert result.data["image"] == str(fake_asset_id)
    assert result.asset_refs == [f"asset:{fake_asset_id}"]


def test_template_mode_concept_perspective_uses_image_grid_without_llm():
    theme = _theme()
    entry = OutlineSlideEntry(
        slot_id="concept-perspective-2",
        slide_no=31,
        section="概念方案",
        title="概念方案人视图",
        purpose="展示室外人视图和室内人视图。",
        key_message="",
    )
    ext_id = uuid4()
    int_id = uuid4()
    binding = SimpleNamespace(
        derived_asset_ids=[str(ext_id), str(int_id)],
        evidence_snippets=["concept.2.ext_perspective", "concept.2.int_perspective"],
    )
    assets = [
        {
            "id": str(ext_id),
            "type": "image",
            "subtype": "image",
            "title": "方案二 室外人视图",
            "logical_key": "concept.2.ext_perspective",
            "image_url": "file:///tmp/ext.png",
            "asset_ref": f"asset:{ext_id}",
        },
        {
            "id": str(int_id),
            "type": "image",
            "subtype": "image",
            "title": "方案二 室内人视图",
            "logical_key": "concept.2.int_perspective",
            "image_url": "file:///tmp/int.png",
            "asset_ref": f"asset:{int_id}",
        },
    ]

    with patch("agent.composer_template.compose_template_slide", new=AsyncMock()) as mock_tpl, \
         patch("agent.composer._compose_slide_html", new=AsyncMock()) as mock_html:
        result = asyncio.run(compose_slide(
            entry,
            theme,
            brief_dict={},
            asset_summary=assets,
            binding=binding,
            mode=ComposerMode.TEMPLATE,
        ))

    assert isinstance(result, _ComposerTemplateOutput)
    assert not mock_tpl.called
    assert not mock_html.called
    assert result.component_type == ComponentType.IMAGE_GRID.value
    assert [image["path"] for image in result.data["images"]] == [str(ext_id), str(int_id)]
    assert result.asset_refs == [f"asset:{ext_id}", f"asset:{int_id}"]


def test_template_mode_transition_is_deterministic_without_llm():
    pid = uuid4()
    theme = _theme()
    entry = OutlineSlideEntry(
        slot_id="chapter-2-divider",
        slide_no=13,
        section="场地分析",
        title="场地分析",
        purpose="chapter divider",
        key_message="深入解读场地现状",
        is_chapter_divider=True,
    )
    outline_spec = _outline(pid, [
        _entry("cover", slide_no=1),
        entry,
    ])

    with patch("agent.composer_template.compose_template_slide", new=AsyncMock()) as mock_tpl, \
         patch("agent.composer._compose_slide_html", new=AsyncMock()) as mock_html:
        result = asyncio.run(compose_slide(
            entry,
            theme,
            brief_dict={},
            asset_summary=[],
            mode=ComposerMode.TEMPLATE,
            outline_spec=outline_spec,
        ))

    assert isinstance(result, _ComposerTemplateOutput)
    assert not mock_tpl.called
    assert not mock_html.called
    assert result.component_type == ComponentType.TRANSITION.value
    assert result.data["title"] == "场地分析"
    assert result.data["subtitle_en"] == "SITE ANALYSIS"
    assert result.data["section_no"] == "02"
    assert result.data["sub"] is None


def test_template_mode_toc_uses_chapter_dividers_without_llm():
    pid = uuid4()
    theme = _theme()
    entries = [
        _entry("cover", slide_no=1),
        _entry("toc", slide_no=2),
        OutlineSlideEntry(
            slot_id="chapter-1-divider",
            slide_no=3,
            section="背景研究",
            title="背景研究",
            purpose="chapter divider",
            key_message="",
            is_chapter_divider=True,
        ),
        _entry("policy-1", slide_no=4),
        OutlineSlideEntry(
            slot_id="chapter-2-divider",
            slide_no=13,
            section="场地分析",
            title="场地分析",
            purpose="chapter divider",
            key_message="",
            is_chapter_divider=True,
        ),
        _entry("site-location-1", slide_no=14),
        OutlineSlideEntry(
            slot_id="chapter-4-divider",
            slide_no=28,
            section="设计策略",
            title="设计策略",
            purpose="chapter divider",
            key_message="",
            is_chapter_divider=True,
        ),
        OutlineSlideEntry(
            slot_id="design-strategies",
            slide_no=29,
            section="设计策略",
            title="设计策略",
            purpose="strategy",
            key_message="",
        ),
        _entry("closing", slide_no=41),
    ]
    outline_spec = _outline(pid, entries)

    with patch("agent.composer_template.compose_template_slide", new=AsyncMock()) as mock_tpl, \
         patch("agent.composer._compose_slide_html", new=AsyncMock()) as mock_html:
        result = asyncio.run(compose_slide(
            entries[1],
            theme,
            brief_dict={},
            asset_summary=[],
            mode=ComposerMode.TEMPLATE,
            outline_spec=outline_spec,
        ))

    assert isinstance(result, _ComposerTemplateOutput)
    assert not mock_tpl.called
    assert not mock_html.called
    assert result.component_type == ComponentType.TOC.value
    assert [e["label"] for e in result.data["entries"]] == ["背景研究", "场地分析", "设计策略"]
    assert [e["page_range"] for e in result.data["entries"]] == ["03-12", "13-27", "28-29"]


def test_template_mode_cover_uses_brief_and_outline_without_llm():
    pid = uuid4()
    theme = _theme()
    entry = OutlineSlideEntry(
        slot_id="cover",
        slide_no=1,
        section="封面",
        title="生态文化微地标",
        purpose="cover",
        key_message="项目名称'十堰市张湾区人民广场公共厕所'，副标题'生态文化微地标 · 建筑方案汇报'",
        is_cover=True,
    )
    outline_spec = OutlineSpec(
        project_id=pid,
        deck_title="十堰市张湾区人民广场公共厕所建筑方案汇报",
        theme="architecture",
        total_pages=1,
        sections=["封面"],
        slides=[entry],
    )

    with patch("agent.composer_template.compose_template_slide", new=AsyncMock()) as mock_tpl, \
         patch("agent.composer._compose_slide_html", new=AsyncMock()) as mock_html:
        result = asyncio.run(compose_slide(
            entry,
            theme,
            brief_dict={
                "client_name": "张湾区城管局",
                "building_type": "公共厕所",
                "province": "湖北省",
                "city": "十堰市",
                "district": "张湾区",
                "gross_floor_area": 300,
                "far": 1.0,
            },
            asset_summary=[],
            mode=ComposerMode.TEMPLATE,
            outline_spec=outline_spec,
        ))

    assert isinstance(result, _ComposerTemplateOutput)
    assert not mock_tpl.called
    assert not mock_html.called
    assert result.component_type == ComponentType.COVER.value
    assert result.data["title"] == "十堰市张湾区人民广场公共厕所"
    assert result.data["slogan"] == "生态文化微地标 · 建筑方案汇报"
    assert result.data["logo"] is None
    assert result.data["meta_lines"][0] == {"label": "项目地点", "value": "湖北省十堰市张湾区"}
    assert {"label": "建筑面积", "value": "300 m²"} in result.data["meta_lines"]
    assert result.data["signature"]["line1"] == "张湾区城管局"


def test_template_mode_ending_is_deterministic_without_llm():
    theme = _theme()
    entry = _entry("closing", slide_no=41)

    with patch("agent.composer_template.compose_template_slide", new=AsyncMock()) as mock_tpl, \
         patch("agent.composer._compose_slide_html", new=AsyncMock()) as mock_html:
        result = asyncio.run(compose_slide(
            entry,
            theme,
            brief_dict={"client_name": "十堰市"},
            asset_summary=[],
            mode=ComposerMode.TEMPLATE,
        ))

    assert isinstance(result, _ComposerTemplateOutput)
    assert not mock_tpl.called
    assert not mock_html.called
    assert result.component_type == ComponentType.ENDING.value
    assert result.data["title"] == "谢谢"
    assert result.data["en"] == "THANK YOU"
    assert result.data["tagline"] == "Thank you for your attention."
    assert "十堰市" in result.data["signature_parts"]


def test_template_mode_image_grid_uses_bound_visual_assets_without_llm():
    theme = _theme()
    entry = _entry("site-location-2", slide_no=15)
    asset_id = uuid4()
    binding = SimpleNamespace(derived_asset_ids=[str(asset_id)], evidence_snippets=["外部交通_285"])
    assets = [
        {
            "id": str(asset_id),
            "type": "map",
            "subtype": "image",
            "title": "外部交通_285",
            "image_url": "tmp/external.png",
            "logical_key": "site.transport.external.image",
            "asset_ref": f"asset:{asset_id}",
        }
    ]

    with patch("agent.composer_template.compose_template_slide", new=AsyncMock()) as mock_tpl, \
         patch("agent.composer._compose_slide_html", new=AsyncMock()) as mock_html:
        result = asyncio.run(compose_slide(
            entry,
            theme,
            brief_dict={},
            asset_summary=assets,
            binding=binding,
            mode=ComposerMode.TEMPLATE,
        ))

    assert isinstance(result, _ComposerTemplateOutput)
    assert not mock_tpl.called
    assert not mock_html.called
    assert result.component_type == ComponentType.IMAGE_GRID.value
    assert result.data["images"][0]["path"] == str(asset_id)
    assert result.data["caption"] == "外部交通285"
    assert result.asset_refs == [f"asset:{asset_id}"]


def test_template_mode_case_card_uses_reference_assets_without_llm():
    pid = uuid4()
    theme = _theme()
    entries = [
        _entry("reference-case-1", slide_no=23),
        _entry("reference-case-2", slide_no=24),
    ]
    outline_spec = _outline(pid, entries)
    thumb_id = uuid4()

    def fake_find(*, logical_key, **_kwargs):
        if logical_key == "reference.case.2.thumbnail":
            return SimpleNamespace(id=thumb_id, summary="", title="thumb")
        if logical_key == "reference.case.2.source":
            return SimpleNamespace(
                id=uuid4(),
                summary=(
                    "# 西班牙生态公共厕所Trado / MOL Arquitectura\n"
                    "**地点**: TRADO, 西班牙\n**年份**: 2018\n"
                    "**面积**: 56.00 m²\n**建筑师**: MOL Arquitectura"
                ),
                title="source",
            )
        if logical_key == "reference.case.2.card":
            return SimpleNamespace(id=uuid4(), summary="绿色屋面和自然采光形成低能耗公共空间。", title="card")
        if logical_key == "reference.case.2.analysis":
            return SimpleNamespace(id=uuid4(), summary="生态策略可转译到本项目。", title="analysis")
        return None

    with patch("agent.composer_template.compose_template_slide", new=AsyncMock()) as mock_tpl, \
         patch("agent.composer._compose_slide_html", new=AsyncMock()) as mock_html, \
         patch("agent.composer._find_asset_by_logical_key", side_effect=fake_find):
        result = asyncio.run(compose_slide(
            entries[1],
            theme,
            brief_dict={},
            asset_summary=[],
            mode=ComposerMode.TEMPLATE,
            project_id=pid,
            db=object(),
            outline_spec=outline_spec,
        ))

    assert isinstance(result, _ComposerTemplateOutput)
    assert not mock_tpl.called
    assert not mock_html.called
    assert result.component_type == ComponentType.CASE_CARD.value
    assert result.data["case_idx"] == 1
    assert result.data["thumbnail"] == str(thumb_id)
    assert "西班牙生态公共厕所Trado" in result.data["case_name"]
    assert result.asset_refs == [f"asset:{thumb_id}"]


def test_template_mode_concept_intro_uses_proposal_without_llm():
    pid = uuid4()
    theme = _theme()
    entries = [
        _entry("concept-intro-1", slide_no=29),
        _entry("concept-intro-2", slide_no=30),
    ]
    outline_spec = _outline(pid, entries)
    outline_json = {
        **outline_spec.model_dump(mode="json"),
        "concept_proposals": [
            {
                "index": 1,
                "name": "山水院落",
                "design_idea": "围合院落与山水界面",
                "narrative": "以院落组织动线，将场地记忆转译为空间序列。",
                "design_keywords": ["courtyard", "garden"],
                "massing_hint": "围合体量",
                "material_hint": "石材与木格栅",
                "mood_hint": "温润",
            },
            {
                "index": 2,
                "name": "光影廊桥",
                "design_idea": "廊桥串联开放公共层",
                "narrative": "以连桥连接功能簇，形成具有识别度的公共空间骨架。",
                "design_keywords": ["bridge"],
                "massing_hint": "连桥体量",
                "material_hint": "清水混凝土",
                "mood_hint": "克制",
            },
        ],
    }

    with patch("agent.composer_template.compose_template_slide", new=AsyncMock()) as mock_tpl, \
         patch("agent.composer._compose_slide_html", new=AsyncMock()) as mock_html:
        result = asyncio.run(compose_slide(
            entries[1],
            theme,
            brief_dict={},
            asset_summary=[],
            mode=ComposerMode.TEMPLATE,
            outline_spec=outline_spec,
            outline_json=outline_json,
        ))

    assert isinstance(result, _ComposerTemplateOutput)
    assert not mock_tpl.called
    assert not mock_html.called
    assert result.component_type == ComponentType.CONTENT_BULLETS.value
    assert result.data["title"] == "光影廊桥"
    assert result.data["bullets"][0]["title"] == "设计理念"
    assert "廊桥串联开放公共层" in result.data["bullets"][0]["body"]


def test_template_mode_content_bullets_uses_brief_doc_without_llm():
    theme = _theme()
    entry = OutlineSlideEntry(
        slot_id="design-strategies",
        slide_no=29,
        section="设计策略",
        title="设计策略",
        purpose="形成场地、文化与运营协同的设计策略。",
        key_message="以公共性、在地性和维护效率组织方案表达。",
    )
    brief_outline = {
        "positioning_statement": "十堰张湾区公共厕所应成为兼具服务效率与城市识别度的微地标。",
        "design_principles": [
            "优先保障高峰时段的动线效率",
            "将地域文化符号转译为空间与材料语言",
            "采用易维护、耐久的外立面系统",
        ],
        "recommended_emphasis": {
            "site_advantage": "突出人民广场周边公共服务需求",
            "competitive_edge": "以精细化运营形成差异化",
            "case_inspiration": "借鉴参考案例的自然采光和绿色屋面策略",
        },
    }

    with patch("agent.composer_template.compose_template_slide", new=AsyncMock()) as mock_tpl, \
         patch("agent.composer._compose_slide_html", new=AsyncMock()) as mock_html:
        result = asyncio.run(compose_slide(
            entry,
            theme,
            brief_dict={"brief_doc_outline": brief_outline},
            asset_summary=[],
            mode=ComposerMode.TEMPLATE,
        ))

    assert isinstance(result, _ComposerTemplateOutput)
    assert not mock_tpl.called
    assert not mock_html.called
    assert result.component_type == ComponentType.CONTENT_BULLETS.value
    assert result.data["title"] == "设计策略"
    assert len(result.data["bullets"]) >= 3
    assert result.data["lede"] == "以公共性、在地性和维护效率组织方案表达。"
    assert result.data["bullets"][0]["title"] == "场地回应"


def test_template_mode_content_bullets_prefers_design_outline_asset():
    theme = _theme()
    entry = OutlineSlideEntry(
        slot_id="design-strategies",
        slide_no=29,
        section="设计策略",
        title="设计策略",
        purpose="[Material Package E2E] 分析设计建议书大纲中的设计策略内容。",
        key_message="[Material Package E2E] 提炼 3-5 条策略。",
    )
    asset = {
        "id": str(uuid4()),
        "type": "text",
        "subtype": "markdown",
        "title": "设计建议书大纲_285",
        "logical_key": "brief.design_outline",
        "summary": (
            "### 设计策略\n"
            "1. **文化融合策略**：将武当、车城文化元素转化为檐口弧度、格栅纹理和展示墙面。\n"
            "2. **功能复合策略**：叠加便民休息、直饮水、手机充电和文化科普等复合功能。\n"
            "3. **生态低耗策略**：采用自然通风采光、屋顶绿化和节水洁具降低运营能耗。\n"
        ),
        "asset_ref": "asset:outline",
    }

    with patch("agent.composer_template.compose_template_slide", new=AsyncMock()) as mock_tpl, \
         patch("agent.composer._compose_slide_html", new=AsyncMock()) as mock_html:
        result = asyncio.run(compose_slide(
            entry,
            theme,
            brief_dict={},
            asset_summary=[asset],
            mode=ComposerMode.TEMPLATE,
        ))

    assert isinstance(result, _ComposerTemplateOutput)
    assert not mock_tpl.called
    assert not mock_html.called
    assert result.component_type == ComponentType.CONTENT_BULLETS.value
    assert result.data["bullets"][0]["title"] == "文化融合策略"
    assert "武当" in result.data["bullets"][0]["body"]
    assert all("Material Package E2E" not in bullet["body"] for bullet in result.data["bullets"])


def test_template_mode_content_bullets_reads_full_design_outline_source():
    theme = _theme()
    entry = OutlineSlideEntry(
        slot_id="cultural-analysis",
        slide_no=9,
        section="背景研究",
        title="文化特征分析",
        purpose="分析设计建议书大纲中的文化特征信息。",
        key_message="",
    )
    asset = {
        "id": str(uuid4()),
        "type": "text_summary",
        "subtype": "document",
        "title": "设计建议书大纲_285",
        "logical_key": "brief.design_outline",
        "summary": "### 政策分析\n1. **《城市公共厕所设计标准》**：基础依据。",
        "config_json": {"source_path": str(Path("test_material/project1/设计建议书大纲_285.md"))},
        "asset_ref": "asset:outline",
    }

    with patch("agent.composer_template.compose_template_slide", new=AsyncMock()) as mock_tpl, \
         patch("agent.composer._compose_slide_html", new=AsyncMock()) as mock_html:
        result = asyncio.run(compose_slide(
            entry,
            theme,
            brief_dict={},
            asset_summary=[asset],
            mode=ComposerMode.TEMPLATE,
        ))

    assert isinstance(result, _ComposerTemplateOutput)
    assert not mock_tpl.called
    assert not mock_html.called
    bodies = [bullet["body"] for bullet in result.data["bullets"]]
    assert any("武当" in body for body in bodies)
    assert any("齿轮" in body for body in bodies)


def test_template_mode_policy_list_uses_policy_evidence_without_llm():
    theme = _theme()
    entry = OutlineSlideEntry(
        slot_id="policy-1",
        slide_no=4,
        section="背景研究",
        title="政策分析",
        purpose="梳理政策约束",
        key_message="政策要求应转化为公共服务、运营维护和空间品质目标。",
    )
    brief_outline = {
        "recommended_emphasis": {
            "policy_focus": "《城市公共厕所设计标准》（2024）要求提升公共卫生设施服务半径与无障碍配置。"
        }
    }

    with patch("agent.composer_template.compose_template_slide", new=AsyncMock()) as mock_tpl, \
         patch("agent.composer._compose_slide_html", new=AsyncMock()) as mock_html:
        result = asyncio.run(compose_slide(
            entry,
            theme,
            brief_dict={"brief_doc_outline": brief_outline},
            asset_summary=[],
            mode=ComposerMode.TEMPLATE,
        ))

    assert isinstance(result, _ComposerTemplateOutput)
    assert not mock_tpl.called
    assert not mock_html.called
    assert result.component_type == ComponentType.POLICY_LIST.value
    assert result.data["policies"][0]["title"] == "城市公共厕所设计标准"
    assert result.data["policies"][0]["publish_year"] == "2024"
    assert result.data["policies"][0]["source_url"] is None


def test_template_mode_table_uses_spreadsheet_preview_without_llm():
    theme = _theme()
    entry = OutlineSlideEntry(
        slot_id="competitor-local",
        slide_no=22,
        section="竞品分析",
        title="本地竞品分析",
        purpose="竞品对比",
        key_message="以周边同类产品形成定位差异。",
    )
    asset_id = uuid4()
    binding = SimpleNamespace(derived_asset_ids=[str(asset_id)], evidence_snippets=["附近同类型产品分析_POI_285"])
    assets = [
        {
            "id": str(asset_id),
            "type": "kpi_table",
            "subtype": "spreadsheet",
            "title": "附近同类型产品分析_POI_285",
            "logical_key": "site.competitor.table",
            "data_json": {
                "preview_rows": [
                    {
                        "sheet": "Sheet1",
                        "rows": [
                            ["名称", "距离", "规模", "特色"],
                            ["人民广场公厕", "120m", "小型", "高频公共服务"],
                            ["商圈配套公厕", "350m", "中型", "客流稳定"],
                        ],
                    }
                ]
            },
            "asset_ref": f"asset:{asset_id}",
        }
    ]

    with patch("agent.composer_template.compose_template_slide", new=AsyncMock()) as mock_tpl, \
         patch("agent.composer._compose_slide_html", new=AsyncMock()) as mock_html:
        result = asyncio.run(compose_slide(
            entry,
            theme,
            brief_dict={},
            asset_summary=assets,
            binding=binding,
            mode=ComposerMode.TEMPLATE,
        ))

    assert isinstance(result, _ComposerTemplateOutput)
    assert not mock_tpl.called
    assert not mock_html.called
    assert result.component_type == ComponentType.TABLE.value
    assert result.data["headers"] == ["名称", "距离", "规模", "特色"]
    assert result.data["rows"][0] == ["人民广场公厕", "120m", "小型", "高频公共服务"]


def test_template_mode_material_economic_table_uses_concept_proposals_without_llm():
    pid = uuid4()
    theme = _theme()
    entry = OutlineSlideEntry(
        slot_id="material-economic",
        slide_no=40,
        section="深化比选",
        title="材质分析与经济技术指标",
        purpose="方案比选",
        key_message="比较三个方案的材料与经济技术指标。",
    )
    outline_spec = _outline(pid, [entry])
    outline_json = {
        **outline_spec.model_dump(mode="json"),
        "concept_proposals": [
            {
                "index": 1,
                "name": "山水院落",
                "design_idea": "围合院落与山水界面",
                "narrative": "以院落组织动线。",
                "design_keywords": ["courtyard"],
                "massing_hint": "围合体量",
                "material_hint": "石材与木格栅",
                "mood_hint": "温润",
            },
            {
                "index": 2,
                "name": "光影廊桥",
                "design_idea": "廊桥串联开放公共层",
                "narrative": "以连桥连接功能簇。",
                "design_keywords": ["bridge"],
                "massing_hint": "连桥体量",
                "material_hint": "清水混凝土",
                "mood_hint": "克制",
            },
            {
                "index": 3,
                "name": "城市折板",
                "design_idea": "折板屋面形成入口识别",
                "narrative": "以折板回应城市界面。",
                "design_keywords": ["fold"],
                "massing_hint": "折板体量",
                "material_hint": "金属板与玻璃",
                "mood_hint": "轻盈",
            },
        ],
    }

    with patch("agent.composer_template.compose_template_slide", new=AsyncMock()) as mock_tpl, \
         patch("agent.composer._compose_slide_html", new=AsyncMock()) as mock_html:
        result = asyncio.run(compose_slide(
            entry,
            theme,
            brief_dict={"gross_floor_area": 300, "far": 1.0},
            asset_summary=[],
            mode=ComposerMode.TEMPLATE,
            outline_spec=outline_spec,
            outline_json=outline_json,
        ))

    assert isinstance(result, _ComposerTemplateOutput)
    assert not mock_tpl.called
    assert not mock_html.called
    assert result.component_type == ComponentType.TABLE.value
    assert result.data["headers"] == ["方案", "材质策略", "建筑面积", "容积率", "综合判断"]
    assert result.data["rows"][0][0] == "山水院落"
    assert result.data["rows"][0][2] == "300 m²"


def test_template_mode_chart_uses_bound_chart_asset_without_llm():
    theme = _theme()
    entry = OutlineSlideEntry(
        slot_id="policy-impact",
        slide_no=6,
        section="背景研究",
        title="政策影响分析",
        purpose="展示政策影响图表",
        key_message="政策对用地、运营和公共性形成综合影响。",
    )
    asset_id = uuid4()
    binding = SimpleNamespace(derived_asset_ids=[str(asset_id)], evidence_snippets=["政策影响矩阵"])
    assets = [
        {
            "id": str(asset_id),
            "type": "chart",
            "subtype": "chart_bundle",
            "title": "政策影响矩阵",
            "image_url": "file:///tmp/policy.svg",
            "logical_key": "policy.impact.chart.0",
            "summary": "用地影响较高，运营影响中等。",
            "asset_ref": f"asset:{asset_id}",
        }
    ]

    with patch("agent.composer_template.compose_template_slide", new=AsyncMock()) as mock_tpl, \
         patch("agent.composer._compose_slide_html", new=AsyncMock()) as mock_html:
        result = asyncio.run(compose_slide(
            entry,
            theme,
            brief_dict={},
            asset_summary=assets,
            binding=binding,
            mode=ComposerMode.TEMPLATE,
        ))

    assert isinstance(result, _ComposerTemplateOutput)
    assert not mock_tpl.called
    assert not mock_html.called
    assert result.component_type == ComponentType.CHART.value
    assert result.data["chart_path"] == str(asset_id)
    assert result.asset_refs == [f"asset:{asset_id}"]


def test_template_mode_poi_chart_materializes_from_table_without_llm():
    theme = _theme()
    entry = OutlineSlideEntry(
        slot_id="poi-analysis",
        slide_no=20,
        section="场地分析",
        title="场地 POI 业态分析",
        purpose="分析周边业态结构",
        key_message="周边业态以餐饮、零售和交通服务为主。",
    )
    asset_id = uuid4()
    binding = SimpleNamespace(derived_asset_ids=[str(asset_id)], evidence_snippets=["场地poi_285"])
    assets = [
        {
            "id": str(asset_id),
            "type": "kpi_table",
            "subtype": "spreadsheet",
            "title": "场地poi_285",
            "logical_key": "site.poi.table",
            "data_json": {
                "preview_rows": [
                    {
                        "sheet": "Sheet1",
                        "rows": [
                            ["业态", "数量"],
                            ["餐饮", 12],
                            ["零售", 8],
                            ["交通", 5],
                        ],
                    }
                ]
            },
            "asset_ref": f"asset:{asset_id}",
        }
    ]

    with patch("agent.composer_template.compose_template_slide", new=AsyncMock()) as mock_tpl, \
         patch("agent.composer._compose_slide_html", new=AsyncMock()) as mock_html, \
         patch("agent.chart_materialize.materialize_chart_png", return_value="tmp/chart_materialized/poi.png") as mock_mat:
        result = asyncio.run(compose_slide(
            entry,
            theme,
            brief_dict={},
            asset_summary=assets,
            binding=binding,
            mode=ComposerMode.TEMPLATE,
        ))

    assert isinstance(result, _ComposerTemplateOutput)
    assert not mock_tpl.called
    assert not mock_html.called
    assert mock_mat.called
    assert result.component_type == ComponentType.CHART.value
    assert result.data["chart_path"] == "tmp/chart_materialized/poi.png"


def test_preview_rows_falls_back_to_xlsx_source_path():
    asset = {
        "id": str(uuid4()),
        "type": "kpi_table",
        "subtype": "spreadsheet",
        "title": "场地poi_285",
        "logical_key": "site.poi.table",
        "data_json": {"file_size": 1},
        "config_json": {"source_path": str(Path("test_material/project1/场地poi_285.xlsx"))},
    }

    rows = _preview_rows_from_asset(asset)

    assert rows
    assert any("名称" in str(cell) or "类型" in str(cell) for cell in rows[0])


def test_template_mode_chart_spec_is_materialized_after_llm():
    from schema.slide_data import ChartData

    theme = _theme()
    entry = OutlineSlideEntry(
        slot_id="policy-impact",
        slide_no=6,
        section="背景研究",
        title="政策影响分析",
        purpose="展示政策影响图表",
        key_message="政策对用地、运营和公共性形成综合影响。",
    )
    fake = ChartData(
        title="政策影响分析",
        bullets=["用地影响高"],
        chart_spec={
            "chart_type": "bar",
            "chart_title": "政策影响矩阵",
            "data": [{"维度": "用地", "影响程度": 90}],
        },
    )

    with patch("agent.composer_template.compose_template_slide", new=AsyncMock(return_value=fake)) as mock_tpl, \
         patch("agent.composer._compose_slide_html", new=AsyncMock()) as mock_html, \
         patch("agent.chart_materialize.materialize_chart_png", return_value="tmp/chart_materialized/policy.png") as mock_mat:
        result = asyncio.run(compose_slide(
            entry,
            theme,
            brief_dict={},
            asset_summary=[],
            mode=ComposerMode.TEMPLATE,
        ))

    assert isinstance(result, _ComposerTemplateOutput)
    assert mock_tpl.called
    assert not mock_html.called
    assert mock_mat.call_args.kwargs["data"] == [{"label": "用地", "value": 90.0}]
    assert result.component_type == ComponentType.CHART.value
    assert result.data["chart_path"] == "tmp/chart_materialized/policy.png"


def test_task_instruction_text_is_filtered_from_content_candidates():
    assert _looks_like_task_instruction("[Material Package E2E cultural] 调用 Nanobanana 生成室外人视图")
    assert not _looks_like_task_instruction("人民广场核心节点，日均人流密集")


def test_policy_list_parses_design_outline_asset_before_prompt_fallback():
    entry = OutlineSlideEntry(
        slot_id="policy-1",
        slide_no=4,
        section="背景研究",
        title="政策分析",
        purpose="[Material Package E2E cultural] 分析设计建议书大纲中相关政策信息",
        key_message="[Material Package E2E cultural] 提供政策来源网页链接。",
    )
    assets = [
        {
            "id": str(uuid4()),
            "type": "text",
            "subtype": "markdown",
            "title": "设计建议书大纲_285",
            "logical_key": "brief.design_outline",
            "summary": (
                "### 政策分析\n"
                "1. **《城市公共厕所设计标准》CJJ14-2016**：国家层面明确二类以上公厕需配置第三卫生间、无障碍设施、通风除臭系统等要求。\n"
                "> 来源链接：http://openstd.samr.gov.cn/bzgk/gb/newGbInfo?hcno=080901B2016000027\n"
                "2. **《湖北省“十四五”城乡人居环境建设规划》**：推动城乡公厕品质提升与公共服务完善。\n"
            ),
            "asset_ref": "asset:outline",
        }
    ]

    result = _compose_policy_list_data(
        entry=entry,
        brief_dict={},
        asset_summary=assets,
        binding=None,
    )

    assert result is not None
    data, _ = result
    titles = [policy.title for policy in data.policies]
    assert "城市公共厕所设计标准" in titles
    assert "湖北省“十四五”城乡人居环境建设规划" in titles
    assert all("Material Package E2E" not in policy.impact for policy in data.policies)


def test_policy_list_slices_repeated_policy_pages_without_duplication():
    assets = [
        {
            "id": str(uuid4()),
            "type": "text",
            "subtype": "markdown",
            "title": "设计建议书大纲_285",
            "logical_key": "brief.design_outline",
            "summary": (
                "### 政策分析\n"
                "1. **《城市公共厕所设计标准》CJJ14-2016**：基础配置要求。\n"
                "2. **《湖北省“十四五”城乡人居环境建设规划》**：品质化升级要求。\n"
                "3. **《十堰市城市公共空间品质提升三年行动方案（2023-2025）》**：地域文化要求。\n"
            ),
            "asset_ref": "asset:outline",
        }
    ]
    page_1 = OutlineSlideEntry(
        slot_id="policy-1",
        slide_no=4,
        section="背景研究",
        title="政策分析 1/2",
        purpose="",
        key_message="",
    )
    page_2 = OutlineSlideEntry(
        slot_id="policy-2",
        slide_no=5,
        section="背景研究",
        title="政策分析 2/2",
        purpose="",
        key_message="",
    )

    result_1 = _compose_policy_list_data(entry=page_1, brief_dict={}, asset_summary=assets, binding=None)
    result_2 = _compose_policy_list_data(entry=page_2, brief_dict={}, asset_summary=assets, binding=None)

    assert result_1 is not None
    assert result_2 is not None
    data_1, _ = result_1
    data_2, _ = result_2
    titles_1 = {policy.title for policy in data_1.policies}
    titles_2 = {policy.title for policy in data_2.policies}
    assert titles_1 == {
        "城市公共厕所设计标准",
        "湖北省“十四五”城乡人居环境建设规划",
    }
    assert titles_2 == {"十堰市城市公共空间品质提升三年行动方案（2023-2025）"}
    assert titles_1.isdisjoint(titles_2)


def test_image_grid_selects_slot_specific_assets():
    assets = [
        {
            "id": f"id-{idx}",
            "type": "chart",
            "subtype": "image",
            "title": title,
            "logical_key": logical_key,
            "image_url": f"file:///{idx}.png",
            "asset_ref": f"asset:id-{idx}",
        }
        for idx, (logical_key, title) in enumerate([
            ("economy.city.chart.0", "城市经济 chart 0"),
            ("economy.industry.chart.0", "产业发展 chart 0"),
            ("economy.consumption.chart.0", "消费民生 chart 0"),
        ])
    ]

    selected = _select_image_grid_assets("economic-2", assets)

    assert [asset["logical_key"] for asset in selected][:1] == ["economy.industry.chart.0"]


def test_assets_for_entry_adds_brief_outline_for_policy_empty_binding():
    entry = OutlineSlideEntry(
        slot_id="policy-1",
        slide_no=4,
        section="背景研究",
        title="政策分析",
        purpose="",
        key_message="",
    )
    outline_asset = {
        "id": "outline-id",
        "type": "text",
        "subtype": "markdown",
        "title": "设计建议书大纲_285",
        "logical_key": "brief.design_outline",
        "summary": "### 政策分析\n1. **《城市公共厕所设计标准》CJJ14-2016**：...",
        "asset_ref": "asset:outline-id",
    }
    unrelated = {
        "id": "other-id",
        "type": "image",
        "subtype": "image",
        "title": "其它图片",
        "logical_key": "other.image",
        "image_url": "file:///other.png",
        "asset_ref": "asset:other-id",
    }
    binding = SimpleNamespace(derived_asset_ids=[])

    selected = _assets_for_entry(entry=entry, all_asset_summary=[unrelated, outline_asset], binding=binding)

    assert [asset["id"] for asset in selected] == ["outline-id"]
