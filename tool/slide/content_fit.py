from pydantic import BaseModel
from schema.slide import SlideSpec, BlockContent, SlideConstraints


class ContentDensityResult(BaseModel):
    density_level: str          # low / medium / high / overflow
    total_text_chars: int
    total_images: int
    total_bullets: int
    exceeds_text_limit: bool
    exceeds_image_limit: bool
    exceeds_bullet_limit: bool
    recommendations: list[str]


def check_content_density(spec: SlideSpec) -> ContentDensityResult:
    """
    检查页面内容密度是否在约束范围内。
    纯本地计算，无 LLM 调用。
    timeout: 0.1s
    """
    c = spec.constraints
    total_text = 0
    total_images = 0
    total_bullets = 0
    recommendations = []

    for block in spec.blocks:
        if block.block_type == "text":
            total_text += len(str(block.content))
        elif block.block_type == "image":
            total_images += 1
        elif block.block_type == "bullet":
            if isinstance(block.content, list):
                total_bullets += len(block.content)
                # Also count text chars in bullets
                for item in block.content:
                    total_text += len(str(item))
            else:
                total_text += len(str(block.content))

    exceeds_text = total_text > c.max_text_chars
    exceeds_image = total_images > c.max_image_count
    exceeds_bullet = total_bullets > c.max_bullet_points

    # Compute density level
    text_ratio = total_text / c.max_text_chars if c.max_text_chars > 0 else 0
    image_ratio = total_images / max(c.max_image_count, 1)
    combined_ratio = (text_ratio + image_ratio) / 2

    if combined_ratio <= 0.3:
        density_level = "low"
    elif combined_ratio <= 0.75:
        density_level = "medium"
    elif combined_ratio <= 1.0:
        density_level = "high"
    else:
        density_level = "overflow"

    if exceeds_text:
        recommendations.append(
            f"文字超出上限（{total_text}/{c.max_text_chars}字），建议精简或拆分"
        )
    if exceeds_image:
        recommendations.append(
            f"图片超出上限（{total_images}/{c.max_image_count}张），建议移除次要图片"
        )
    if exceeds_bullet:
        recommendations.append(
            f"bullet 条目超出上限（{total_bullets}/{c.max_bullet_points}条），建议合并或删减"
        )
    if density_level == "low":
        recommendations.append("内容偏少，建议补充关键数据或图片")

    return ContentDensityResult(
        density_level=density_level,
        total_text_chars=total_text,
        total_images=total_images,
        total_bullets=total_bullets,
        exceeds_text_limit=exceeds_text,
        exceeds_image_limit=exceeds_image,
        exceeds_bullet_limit=exceeds_bullet,
        recommendations=recommendations,
    )
