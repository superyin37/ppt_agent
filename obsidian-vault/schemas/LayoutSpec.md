---
tags: [schema, layout, pydantic]
source: schema/visual_theme.py
---

# LayoutSpec & ContentBlock

> 幻灯片级版式规格，每页独立生成。由 [[agents/ComposerAgent]] 产出，由 `render/engine.py` 消费。

## LayoutSpec

```python
class LayoutSpec(BaseModel):
    layout:          LayoutPrimitive       # 11 种布局原语之一
    region_bindings: list[RegionBinding]   # 区域 → 内容块映射
    metadata:        dict = {}             # 附加元数据（如 visual_focus, title）
```

## RegionBinding

```python
class RegionBinding(BaseModel):
    region_id: str              # 区域标识，如 "left", "right", "content"
    blocks:    list[ContentBlock]
```

## ContentBlock

```python
class ContentBlock(BaseModel):
    block_id:     str
    content_type: str           # 13 种类型（见下表）
    content:      Any           # str / list[str] / None
    emphasis:     str = "normal"  # normal / highlight / muted
    asset_ref:    Optional[str] = None  # "asset:uuid" 格式
```

## 13 种 content_type

| 类型 | 内容格式 | 渲染 HTML |
|------|----------|-----------|
| `heading` | `str` | `<h1 class="block-heading">` |
| `body-text` | `str` | `<p class="block-body-text">` |
| `image` | `"asset:uuid"` | `<img src="...">` |
| `chart` | `"asset:uuid"` | `<img src="...">` + 图表容器 |
| `map` | `"asset:uuid"` | `<img class="map-asset">` |
| `table` | `str`（markdown 表格）| `<table>` |
| `kpi-value` | `[数值, 单位, 标签]` | `.kpi-value` + `.kpi-label` |
| `bullet-list` | `list[str]` | `<ul><li>` + accent 圆点 |
| `quote` | `str` | `<blockquote>` |
| `caption` | `str` | `<p class="caption">` |
| `icon-label` | `[图标, 标签]` | `.icon-label-pair` |
| `tag-cloud` | `list[str]` | `.tag` badges |
| `divider` | — | `<hr>` |

## 资产引用解析

```python
# render/engine.py → _render_block()
if content.startswith("asset:"):
    asset_id = content.split(":")[1]
    asset = find_asset_by_id(asset_id)
    src = asset.image_url  # file:// 本地路径
```

---

## LayoutPrimitive（11 种布局原语）

详见 [[schemas/LayoutPrimitive]]。

LayoutPrimitive 是以下 11 种布局类型的 Union：

```python
LayoutPrimitive = Union[
    FullBleedLayout,       # 全屏单区
    SplitHLayout,          # 左右分割
    SplitVLayout,          # 上下分割
    SingleColumnLayout,    # 单列居中
    GridLayout,            # 多列网格
    HeroStripLayout,       # 大图横条
    SidebarLayout,         # 侧边栏
    TriptychLayout,        # 三联
    OverlayMosaicLayout,   # 覆盖拼贴
    TimelineLayout,        # 时间线
    AsymmetricLayout,      # 不对称自定义
]
```

## 相关

- [[schemas/LayoutPrimitive]]
- [[agents/ComposerAgent]]
- [[schemas/Slide]]
- `render/engine.py` → `_render_layout()`, `_render_block()`
