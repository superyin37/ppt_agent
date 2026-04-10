# 14. 案例库数据规范

## 14.1 案例字段定义

| 字段 | 类型 | 必填 | 说明 |
|------|------|-----|------|
| title | string | ✅ | 案例全称，中英文均可 |
| architect | string | ✅ | 设计单位/建筑师 |
| location | string | ✅ | 所在城市 |
| country | string | ✅ | 所在国家 |
| building_type | enum | ✅ | 见 BuildingType 枚举 |
| style_tags | list[string] | ✅ | 至少 1 个，见标签体系 |
| feature_tags | list[string] | ✅ | 至少 2 个，见标签体系 |
| scale_category | enum | ✅ | small / medium / large |
| gfa_sqm | number | ✅ | 建筑面积（㎡） |
| year_completed | integer | ✅ | 竣工年份（4位数） |
| images | list[ImageItem] | ✅ | 至少 3 张，见图片规范 |
| summary | string | ✅ | 100~300 字摘要 |
| detail_url | string | ❌ | 原始来源页面 URL |
| source | string | ✅ | 数据来源平台 |

---

## 14.2 标签体系枚举

### 风格标签（style_tags）

```python
STYLE_TAGS = [
    "modern",           # 现代
    "minimal",          # 极简
    "traditional",      # 传统/古典
    "industrial",       # 工业风
    "biophilic",        # 自然/生态
    "luxury",           # 奢华
    "brutalist",        # 粗野主义
    "deconstructivist", # 解构主义
    "parametric",       # 参数化
    "vernacular",       # 地域主义
    "cultural",         # 文化性
    "futuristic",       # 未来主义
]
```

### 功能/特征标签（feature_tags）

```python
FEATURE_TAGS = [
    # 造型
    "造型",             # 独特形体/标志性外观
    "立面",             # 立面设计突出
    "材质",             # 材质运用特殊（木/石/金属/玻璃）
    "光线",             # 自然采光设计
    "屋顶",             # 屋顶花园/特殊屋顶形式

    # 功能组织
    "交通组织",         # 人行流线设计
    "功能配比",         # 功能分区合理性
    "公共空间",         # 公共中庭/广场
    "垂直动线",         # 楼梯/扶梯/电梯组织

    # 可持续性
    "绿色可持续",       # 绿色建筑认证
    "被动节能",         # 遮阳/通风等被动策略
    "景观融合",         # 建筑与景观一体化

    # 场地关系
    "在地性",           # 呼应地域文脉
    "地形融合",         # 与地形结合
    "城市关系",         # 与城市街道/广场关系

    # 技术
    "结构表现",         # 结构作为表现元素
    "数字建造",         # 数字化加工/特殊建造
]
```

---

## 14.3 图片规范

```python
class ImageItem(BaseModel):
    url: str                    # OSS 公开 URL
    caption: Optional[str]      # 图片描述
    image_type: str             # exterior / interior / plan / detail / aerial
    width_px: int               # 宽度（像素）
    height_px: int              # 高度（像素）
    is_primary: bool = False    # 是否为主图（封面图）

# 规范要求
IMAGE_RULES = {
    "min_count":        3,              # 最少3张
    "primary_required": True,           # 必须有1张主图
    "min_width":        1200,           # 最小宽度
    "min_height":       800,            # 最小高度
    "required_types":   ["exterior"],   # 必须包含外观图
    "format":           ["jpg", "png", "webp"],
}
```

---

## 14.4 规模分类标准

| 分类 | GFA 范围 | 建筑类型示例 |
|------|---------|------------|
| small | < 5,000 ㎡ | 小型文化馆、社区中心 |
| medium | 5,000 ~ 30,000 ㎡ | 中型博物馆、办公楼 |
| large | > 30,000 ㎡ | 大型综合体、国家级场馆 |

---

## 14.5 Embedding 生成规范

向量嵌入基于以下字段拼接生成（不包含图片）：

```python
def build_embedding_text(case: dict) -> str:
    """
    用于生成案例 embedding 的文本拼接规范。
    目的：确保语义检索与项目需求匹配。
    """
    parts = [
        f"建筑类型：{case['building_type']}",
        f"建筑师：{case.get('architect', '')}",
        f"地点：{case.get('location', '')} {case.get('country', '')}",
        f"风格：{'、'.join(case.get('style_tags', []))}",
        f"特征：{'、'.join(case.get('feature_tags', []))}",
        f"规模：{case.get('scale_category', '')}（{case.get('gfa_sqm', '')}㎡）",
        f"描述：{case.get('summary', '')}",
    ]
    return "\n".join(p for p in parts if p.split("：")[1].strip())
```

---

## 14.6 MVP 案例库要求

| 建筑类型 | 目标数量 | 优先地区 |
|---------|---------|---------|
| museum（博物馆） | 20 个 | 中国 10 + 国际 10 |
| cultural（文化建筑） | 15 个 | 中国 8 + 国际 7 |
| office（办公） | 10 个 | 中国为主 |

**数据来源优先级：**
1. ArchDaily（国际案例，英文）
2. 谷德设计网 gooood.cn（国内案例，中文）
3. 有方空间（中国建筑）
4. dezeen.com（国际案例）

---

## 14.7 案例库初始化脚本

```python
# scripts/seed_cases.py
import json
from db.session import get_db_context
from tool.reference._embedding import get_embedding

SEED_FILE = "scripts/seed_cases.json"


def seed_cases():
    with open(SEED_FILE, encoding="utf-8") as f:
        cases = json.load(f)

    with get_db_context() as db:
        for case in cases:
            # 校验必填字段
            validate_case(case)

            # 生成 embedding
            embed_text = build_embedding_text(case)
            embedding = get_embedding(embed_text)

            # 写入数据库
            db.execute("""
                INSERT INTO reference_cases
                    (title, architect, location, country, building_type,
                     style_tags, feature_tags, scale_category, gfa_sqm,
                     year_completed, images, summary, source, embedding)
                VALUES
                    (:title, :architect, :location, :country, :building_type,
                     :style_tags::jsonb, :feature_tags::jsonb, :scale_category,
                     :gfa_sqm, :year_completed, :images::jsonb, :summary,
                     :source, :embedding::vector)
                ON CONFLICT DO NOTHING
            """, {**case, "embedding": embedding})
        db.commit()
        print(f"✅ 已导入 {len(cases)} 个案例")
```

---

## 14.8 案例质量评估标准

| 评估维度 | 合格标准 |
|---------|---------|
| 图片质量 | 至少 1 张 1200px 以上外观图，清晰无水印 |
| 摘要质量 | 100~300 字，包含造型特点、功能亮点、材质 |
| 标签准确性 | style_tags 和 feature_tags 与案例实际相符 |
| 数据完整性 | 所有必填字段均有值 |
| 信息时效性 | 优先 2010 年以后竣工的项目 |
