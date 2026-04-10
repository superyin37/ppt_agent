---
tags: [stage, export, pdf, playwright]
status-after: EXPORTED
source: render/exporter.py, api/routers/exports.py
---

# 阶段九：PDF 导出

> 将所有幻灯片 PNG 拼合为 PDF 文件，支持 Playwright 方式和 Pillow 降级方式。

## 触发

```
POST /projects/{project_id}/export
→ api/routers/exports.py (line 80)
→ 后台线程: _export_worker() (line 23)
  → compile_pdf(project_id, output_path, db)
```

## 执行流程

```python
# render/exporter.py line 126
async def compile_pdf(project_id, output_path, db):
    # 1. 按 slide_no 顺序加载所有 Slide
    slides = db.query(Slide).filter(...).order_by(Slide.slide_no).all()

    # 2. 收集每页 PNG
    png_list = []
    for slide in slides:
        if existing_file(slide.screenshot_url):
            png_bytes = read(slide.screenshot_url)     # 优先磁盘缓存
        else:
            html = render_slide_html(slide, theme, assets)
            png_bytes = await screenshot_slide(html)   # 即时生成
        png_list.append(png_bytes)

    # 3a. Playwright 拼合 PDF（主路径）
    try:
        pdf_bytes = await _playwright_compile_pdf(png_list)
    # 3b. Pillow 降级（Playwright 失败时）
    except:
        pdf_bytes = _pillow_compile_pdf(png_list)

    # 4. 保存
    write(output_path, pdf_bytes)
```

## Playwright PDF 拼合

```python
async def _playwright_compile_pdf(png_list: list[bytes]) -> bytes:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()

        # 每张 PNG 转为 data URL，构建 HTML
        data_urls = [f"data:image/png;base64,{b64encode(png)}" for png in png_list]
        html = "\n".join([
            f'<img src="{url}" style="width:100%;page-break-after:always;">'
            for url in data_urls
        ])
        await page.set_content(f"<html><body>{html}</body></html>")
        pdf_bytes = await page.pdf(
            format="A4",
            landscape=True,
            margin={"top":"0","right":"0","bottom":"0","left":"0"}
        )
        return pdf_bytes
```

## 输出路径

```
tmp/e2e_output/export/{project_id}.pdf
```

## 降级路径（Pillow）

```python
def _pillow_compile_pdf(png_list: list[bytes]) -> bytes:
    from PIL import Image
    images = [Image.open(BytesIO(p)).convert("RGB") for p in png_list]
    first, rest = images[0], images[1:]
    buf = BytesIO()
    first.save(buf, format="PDF", save_all=True, append_images=rest)
    return buf.getvalue()
```

## 状态变更

```
Project.status → EXPORTED
```

## 输出文件示例

```
tmp/e2e_output/slides/slide_01.png    (1920×1080)
tmp/e2e_output/slides/slide_02.png
...
tmp/e2e_output/export/projectUUID.pdf  (最终 PDF)
```

## 相关

- [[schemas/Slide]]
- [[stages/07-渲染]]（PNG 来源）
- [[enums/ProjectStatus]]
- `render/exporter.py` — `compile_pdf()`, `screenshot_slides_batch()`
