---
tags: [schema, slide, database]
source: db/models/slide.py
---

# Slide

> 幻灯片完整模型，记录从编排到渲染的所有产出。

## 数据库模型

```
表名: slides
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | |
| `project_id` | UUID FK | |
| `outline_id` | UUID FK | 来源大纲 |
| `slide_no` | int | 1-based 页码 |
| `section` | str | 章节名称 |
| `title` | str | 页标题 |
| `purpose` | str | 页面目的 |
| `key_message` | str | 核心信息点 |
| `is_cover` | bool | 是否封面 |
| `is_chapter_divider` | bool | 是否章节分隔页 |
| `status` | str | SlideStatus 枚举（见下文） |
| `spec_json` | JSON | **LayoutSpec JSON** 或 `{html_mode:true, body_html:"..."}` |
| `html_content` | text | 渲染后的完整 HTML（上限 65535 字符） |
| `screenshot_url` | str | PNG 截图路径 |
| `source_refs_json` | JSON | 引用的 Asset UUID 列表 |
| `evidence_refs_json` | JSON | 文本证据摘录 |
| `review_result_json` | JSON | 审查结果（若经过审查阶段） |
| `version` | int | 修复迭代版本号 |

## `status` 字段

详见 [[enums/SlideStatus]]

```
pending
  → spec_ready      (ComposerAgent 完成 LayoutSpec)
  → rendered        (render/engine.py + Playwright 截图完成)
  → review_pending  (进入审查阶段)
  → review_passed   (审查通过)
  → repair_needed   (审查发现问题)
  → repair_in_progress
  → ready           (最终就绪)
  → failed          (不可恢复错误)
```

## `spec_json` 结构

### 结构化模式（v2，标准路径）

即 `LayoutSpec` 的序列化：

```json
{
  "layout": {
    "primitive": "split-h",
    "left_ratio": 6,
    "right_ratio": 4,
    ...
  },
  "region_bindings": [
    {
      "region_id": "left",
      "blocks": [
        { "block_id": "img", "content_type": "image", "content": "asset:uuid", "emphasis": "normal" }
      ]
    },
    {
      "region_id": "right",
      "blocks": [
        { "block_id": "title", "content_type": "heading", "content": "区位优势分析", "emphasis": "highlight" },
        { "block_id": "body", "content_type": "bullet-list", "content": ["地铁 3 号线直达", "距市中心 15 分钟"], "emphasis": "normal" }
      ]
    }
  ],
  "metadata": { "visual_focus": "left", "slide_no": 12 }
}
```

### HTML 模式（v3 降级路径）

```json
{
  "html_mode": true,
  "body_html": "<div class='slide-content'>...</div>",
  "asset_refs": ["uuid1", "uuid2"]
}
```

## `screenshot_url` 路径

```
tmp/e2e_output/slides/slide_01.png
tmp/e2e_output/slides/slide_02.png
...
```

分辨率：1920×1080 px（Playwright headless Chromium 截图）

## 相关

- [[agents/ComposerAgent]]
- [[schemas/LayoutSpec]]
- [[enums/SlideStatus]]
- [[stages/07-渲染]]
- [[stages/08-审查与修复]]
- `render/engine.py`
- `render/exporter.py`
