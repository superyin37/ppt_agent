from __future__ import annotations

from schema.concept_proposal import ConceptProposal, ConceptViewKind
from tool.image_gen.concept_prompts import ConceptPromptContext, build_prompt


def _proposal() -> ConceptProposal:
    return ConceptProposal(
        index=1,
        name="Scheme A",
        design_idea="civic garden pavilion",
        narrative="A compact civic design with landscape integration.",
        design_keywords=["garden", "civic", "low-rise"],
        massing_hint="low-rise interlocking volumes",
        material_hint="light concrete, wood louvers, glass",
        mood_hint="warm and calm",
    )


def _ctx() -> ConceptPromptContext:
    return ConceptPromptContext(
        building_type="public facility",
        site_context="urban plaza",
        style_prefs="modern, minimal",
    )


def test_aerial_prompt_preserves_red_site_boundary() -> None:
    prompt = build_prompt(_proposal(), ConceptViewKind.AERIAL, _ctx())

    assert "red site boundary" in prompt
    assert "user-selected plot outline" in prompt
    assert "keep the red outline clearly visible" in prompt
    assert "inside that boundary" in prompt


def test_boundary_instruction_is_only_for_aerial_prompt() -> None:
    ext_prompt = build_prompt(_proposal(), ConceptViewKind.EXT_PERSPECTIVE, _ctx())
    int_prompt = build_prompt(_proposal(), ConceptViewKind.INT_PERSPECTIVE, _ctx())

    assert "red site boundary" not in ext_prompt
    assert "red site boundary" not in int_prompt
