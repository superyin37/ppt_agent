"""Prompt templates for concept render (3 views x 3 proposals).

Kept as plain strings so the runninghub client layer stays model-agnostic.
"""
from __future__ import annotations

from dataclasses import dataclass

from schema.concept_proposal import ConceptProposal, ConceptViewKind


AERIAL_TEMPLATE = (
    "Architectural rendering, aerial bird's-eye view, photorealistic 3D building. "
    "Preserve the reference image's red site boundary / user-selected plot outline: "
    "keep the red outline clearly visible, accurately aligned with the site, and "
    "place the proposed building design inside that boundary. "
    "Scheme name: {name} — {design_idea}. "
    "Building type: {building_type}. Site context: {site_context}. "
    "Massing: {massing}. Materials: {materials}. "
    "Keywords: {keywords}. "
    "Style: {mood}, {style_prefs}, cinematic lighting, ultra-detailed, "
    "architectural visualization, professional rendering, 4K. "
    "NOT a 2D map diagram — this is a 3D building massing rendering."
)

EXT_PERSPECTIVE_TEMPLATE = (
    "Architectural photography, human eye-level exterior view, photorealistic. "
    "Scheme name: {name} — {design_idea}. "
    "Building type: {building_type}. "
    "Facade & materials: {materials}. Massing cue: {massing}. "
    "Keywords: {keywords}. "
    "Style: {mood}, {style_prefs}, golden hour, cinematic depth of field, 35mm lens, "
    "editorial architectural photography, award-winning, magazine quality."
)

INT_PERSPECTIVE_TEMPLATE = (
    "Interior architectural photography, human eye-level view, photorealistic. "
    "Scheme name: {name} — {design_idea}. "
    "Building type: {building_type}. "
    "Interior materials & finishes: {materials}. Atmosphere: {mood}. "
    "Keywords: {keywords}. "
    "Style: {style_prefs}, natural light, 24mm lens, editorial interior photography, "
    "magazine quality, award-winning."
)

@dataclass
class ConceptPromptContext:
    building_type: str
    site_context: str
    style_prefs: str


def _format_keywords(proposal: ConceptProposal) -> str:
    if not proposal.design_keywords:
        return proposal.design_idea
    return ", ".join(proposal.design_keywords)


def _render(template: str, proposal: ConceptProposal, ctx: ConceptPromptContext) -> str:
    return template.format(
        name=proposal.name,
        design_idea=proposal.design_idea,
        building_type=ctx.building_type or "building",
        site_context=ctx.site_context or "urban site",
        massing=proposal.massing_hint,
        materials=proposal.material_hint,
        mood=proposal.mood_hint,
        keywords=_format_keywords(proposal),
        style_prefs=ctx.style_prefs or "contemporary",
    )


def build_prompt(
    proposal: ConceptProposal,
    view: ConceptViewKind,
    ctx: ConceptPromptContext,
) -> str:
    if view is ConceptViewKind.AERIAL:
        return _render(AERIAL_TEMPLATE, proposal, ctx)
    if view is ConceptViewKind.EXT_PERSPECTIVE:
        return _render(EXT_PERSPECTIVE_TEMPLATE, proposal, ctx)
    if view is ConceptViewKind.INT_PERSPECTIVE:
        return _render(INT_PERSPECTIVE_TEMPLATE, proposal, ctx)
    raise ValueError(f"unknown view kind: {view}")
