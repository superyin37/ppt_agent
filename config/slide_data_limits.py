"""SlideData per-component length / count constraints.

Centralised here so designers and engineers can tune limits without touching
schema or template code. Schema fields read from this dict via Annotated +
StringConstraints / Field max_length.

Tweaking guidance:
- Lower the limit if a component visually overflows on real LLM output.
- Raise the limit only after verifying the component still renders cleanly.
- Each "*_max" suffix means a list length cap; bare keys are string char caps.
"""
from __future__ import annotations


LIMITS: dict[str, dict[str, int]] = {
    "cover": {
        "title": 24,
        "slogan": 80,
        "en": 60,
        "meta_lines_max": 3,
        "meta_label": 16,
        "meta_value": 24,
        "signature_line1": 40,
        "signature_role": 24,
        "signature_date": 16,
    },
    "toc": {
        "title": 24,
        "entries_max": 6,
        "entry_label": 18,
        "entry_en": 40,
        "entry_sub": 30,
        "entry_no": 4,
        "entry_page_range": 16,
    },
    "transition": {
        "title": 18,
        "subtitle_en": 60,
        "sub": 40,
        "section_no": 4,
    },
    "policy_list": {
        "title": 40,
        "policies_max": 5,
        "policy_title": 60,
        "policy_publish_year": 16,
        "policy_content": 120,
        "policy_impact": 60,
        "policy_source_url": 200,
    },
    "chart": {
        "title": 28,
        "bullets_max": 4,
        "bullet": 80,
    },
    "table": {
        "title": 28,
        "headers_max": 6,
        "rows_max": 8,
        "header_cell": 24,
        "body_cell": 36,
        "note": 80,
    },
    "image_grid": {
        "title": 28,
        "images_max": 4,
        "image_caption": 30,
        "footer_caption": 140,
    },
    "content_bullets": {
        "title": 28,
        "lede": 140,
        "bullets_max": 6,
        "bullets_min": 3,
        "bullet_title": 18,
        "bullet_body": 90,
    },
    "case_card": {
        "title": 28,
        "case_name": 32,
        "scale": 60,
        "highlights": 100,
        "inspiration": 100,
    },
    "concept_scheme": {
        "scheme_name": 16,
        "view_label": 24,
        "idea": 40,
        "analysis": 220,
    },
    "ending": {
        "title": 16,
        "en": 40,
        "tagline": 80,
        "signature_parts_max": 4,
        "signature_part": 24,
    },
}
