"""
Summarise user's selection preferences into a narrative hint for the Outline Agent.
"""
import json
import logging
from pydantic import BaseModel

from config.llm import call_llm_structured, FAST_MODEL
from schema.reference import PreferenceSummary

logger = logging.getLogger(__name__)

PREFERENCE_SYSTEM_PROMPT = """你是一位建筑设计偏好分析专家。
分析用户选择的参考案例及其勾选的标签，总结设计偏好，为后续大纲规划提供方向。

## 输出格式（严格 JSON）
{
  "dominant_styles": ["主要风格，最多3个"],
  "dominant_features": ["主要特征，最多4个"],
  "scale_preference": "small/medium/large",
  "narrative_hint": "叙事方向建议，50字以内，传给大纲Agent",
  "design_keywords": ["设计关键词，最多5个"]
}"""


class _PreferenceOutput(BaseModel):
    dominant_styles: list[str]
    dominant_features: list[str]
    scale_preference: str = "medium"
    narrative_hint: str
    design_keywords: list[str] = []


class PreferenceSummaryInput(BaseModel):
    selections: list[dict]  # [{case_id, case_title, selected_tags, selection_reason}]
    brief: dict


class PreferenceSummaryOutput(BaseModel):
    dominant_styles: list[str]
    dominant_features: list[str]
    narrative_hint: str
    design_keywords: list[str] = []


async def summarise_preferences(input: PreferenceSummaryInput) -> PreferenceSummaryOutput:
    """
    LLM call to summarise case selection into preference profile.
    Falls back to tag frequency analysis on failure.
    timeout: 20s
    """
    if not input.selections:
        return PreferenceSummaryOutput(
            dominant_styles=[],
            dominant_features=[],
            narrative_hint="用户尚未选择参考案例",
        )

    user_msg = (
        f"<project_brief>\n{json.dumps(input.brief, ensure_ascii=False)}\n</project_brief>\n\n"
        f"<selections>\n{json.dumps(input.selections, ensure_ascii=False, indent=2)}\n</selections>\n\n"
        "请分析用户的选择偏好，生成设计方向摘要。"
    )

    try:
        result = await call_llm_structured(
            system_prompt=PREFERENCE_SYSTEM_PROMPT,
            user_message=user_msg,
            output_schema=_PreferenceOutput,
            model=FAST_MODEL,
            temperature=0.2,
            max_tokens=512,
        )
        return PreferenceSummaryOutput(
            dominant_styles=result.dominant_styles,
            dominant_features=result.dominant_features,
            narrative_hint=result.narrative_hint,
            design_keywords=result.design_keywords,
        )
    except Exception as e:
        logger.warning(f"Preference summary LLM failed, using tag frequency: {e}")
        return _fallback_summary(input)


def _fallback_summary(input: PreferenceSummaryInput) -> PreferenceSummaryOutput:
    """Count tag frequencies as fallback."""
    from collections import Counter
    tag_counter: Counter = Counter()
    for sel in input.selections:
        for tag in sel.get("selected_tags", []):
            tag_counter[tag] += 1

    top_tags = [t for t, _ in tag_counter.most_common(6)]
    # Rough split: style-like vs feature-like tags
    style_keywords = {"modern", "minimal", "traditional", "industrial",
                      "biophilic", "luxury", "brutalist", "cultural", "vernacular"}
    styles = [t for t in top_tags if t in style_keywords][:3]
    features = [t for t in top_tags if t not in style_keywords][:4]

    return PreferenceSummaryOutput(
        dominant_styles=styles,
        dominant_features=features,
        narrative_hint="基于用户案例选择标签归纳的设计偏好",
    )
