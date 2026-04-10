# 13. 外部 API 集成清单

## 13.1 高德地图 API

### 使用功能

| 功能 | API 接口 | 用途 | 调用频率 |
|------|---------|------|---------|
| 地理编码 | `/v3/geocode/geo` | 地址 → 经纬度 | 每项目 1~3 次 |
| 逆地理编码 | `/v3/geocode/regeo` | 经纬度 → 地址 | 每项目 1 次 |
| POI 检索 | `/v3/place/around` | 周边兴趣点 | 每项目 3~5 次 |
| 静态地图 | `/v3/staticmap` | 生成地图图片 | 每资产 1 次 |
| 路线规划 | `/v3/direction/transit/integrated` | 公共交通可达性 | 每项目 2~3 次 |

### 接入规范

```python
# tool/site/_amap_client.py
import httpx
from config.settings import settings

AMAP_BASE = "https://restapi.amap.com"

async def amap_get(endpoint: str, params: dict) -> dict:
    """统一的高德 API 调用封装，含错误处理和日志"""
    params["key"] = settings.AMAP_API_KEY
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{AMAP_BASE}{endpoint}", params=params)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "1":
            raise ToolError(
                code="AMAP_API_ERROR",
                message=f"高德API错误: {data.get('info', 'unknown')}",
                retryable=False,
            )
        return data
```

### 配额与限流

| 接口 | 免费配额（QPS） | 超出后策略 |
|------|--------------|----------|
| 地理编码 | 50 QPS | 队列降速 |
| POI 检索 | 50 QPS | 队列降速 |
| 静态地图 | 30 QPS | 结果缓存（TTL 7天） |

### 缓存策略

```python
# 对地理编码结果缓存，避免重复调用
# key: f"geocode:{address_md5}"
# TTL: 7 天（地址坐标不会频繁变化）
```

---

## 13.2 LLM API（Anthropic Claude）

### 使用模型

| 模型 | 用途 | 预估单项目消耗 |
|------|------|-------------|
| claude-opus-4-6 | 大纲生成、Critic Agent | ~$0.15 |
| claude-haiku-4-5-20251001 | 信息抽取、Composer、语义审查 | ~$0.05 |

### 接入规范

```python
# 使用官方 Anthropic SDK
from anthropic import AsyncAnthropic

# 统一通过 config/llm.py 的 call_llm_structured 调用
# 禁止在 tool/ 或 agent/ 层直接实例化 Anthropic client
```

### 速率限制处理

```python
# 捕获 anthropic.RateLimitError，指数退避重试
import asyncio
from anthropic import RateLimitError

async def call_with_retry(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await func()
        except RateLimitError as e:
            wait = 2 ** attempt * 10  # 10s, 20s, 40s
            await asyncio.sleep(wait)
    raise LLMRateLimitError()
```

---

## 13.3 对象存储（阿里云 OSS）

### 文件路径规范

```
{bucket}/
├── assets/
│   ├── {project_id}/
│   │   ├── charts/
│   │   │   └── {asset_id}.png
│   │   └── maps/
│   │       └── {asset_id}.png
├── slides/
│   └── {project_id}/
│       └── {slide_id}.png
└── exports/
    └── {project_id}/
        ├── deck_{timestamp}.pdf
        └── deck_{timestamp}.pptx
```

### 接入规范

```python
# tool/_oss_client.py
import oss2
from config.settings import settings

auth = oss2.Auth(settings.OSS_ACCESS_KEY, settings.OSS_SECRET_KEY)
bucket = oss2.Bucket(auth, settings.OSS_ENDPOINT, settings.OSS_BUCKET)

def upload_bytes(data: bytes, key: str, content_type: str = "image/png") -> str:
    """上传字节流，返回公开访问 URL"""
    bucket.put_object(
        key, data,
        headers={"Content-Type": content_type}
    )
    return f"{settings.OSS_BASE_URL}/{key}"

def upload_file(local_path: str, key: str) -> str:
    bucket.put_object_from_file(key, local_path)
    return f"{settings.OSS_BASE_URL}/{key}"
```

### 签名 URL（私有文件）

```python
# 导出文件使用私有 bucket + 临时签名 URL（1小时有效）
def get_signed_url(key: str, expires: int = 3600) -> str:
    return bucket.sign_url("GET", key, expires)
```

---

## 13.4 向量检索（pgvector）

### Embedding 生成

```python
# tool/reference/_embedding.py
from anthropic import Anthropic

client = Anthropic()

def get_embedding(text: str) -> list[float]:
    """
    使用 Voyage AI 或 OpenAI text-embedding-3-small 生成向量。
    注：Anthropic 目前不直接提供 Embedding API，推荐使用 Voyage AI。
    """
    # 示例：使用 voyage-large-2
    import voyageai
    vo = voyageai.Client(api_key=settings.VOYAGE_API_KEY)
    result = vo.embed([text], model="voyage-large-2")
    return result.embeddings[0]
```

### 向量检索 SQL

```python
# tool/reference/search.py
from db.session import get_db_context

async def vector_search_cases(
    query_embedding: list[float],
    building_type: str,
    top_k: int = 10,
    exclude_ids: list[str] = [],
) -> list[dict]:
    with get_db_context() as db:
        result = db.execute("""
            SELECT
                id, title, architect, location, building_type,
                style_tags, feature_tags, images, summary,
                1 - (embedding <=> :query_vec::vector) AS similarity
            FROM reference_cases
            WHERE is_active = true
              AND building_type = :building_type
              AND id NOT IN :exclude_ids
            ORDER BY embedding <=> :query_vec::vector
            LIMIT :top_k
        """, {
            "query_vec": query_embedding,
            "building_type": building_type,
            "exclude_ids": tuple(exclude_ids) or ("",),
            "top_k": top_k,
        })
        return [dict(row) for row in result]
```

---

## 13.5 Playwright（截图服务）

### 启动配置

```python
# render/exporter.py
from playwright.async_api import async_playwright

async def screenshot_slide(
    html: str,
    width: int = 1920,
    height: int = 1080,
) -> bytes:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            viewport={"width": width, "height": height},
        )

        # 设置字体（容器内需预装中文字体）
        await page.set_content(html, wait_until="networkidle")

        # 等待图片加载
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(500)  # 额外等待动画完成

        screenshot = await page.screenshot(
            type="png",
            full_page=False,
            clip={"x": 0, "y": 0, "width": width, "height": height},
        )
        await browser.close()
        return screenshot
```

### Docker 字体安装

```dockerfile
# Dockerfile（节选）
RUN apt-get update && apt-get install -y \
    fonts-noto-cjk \
    fonts-noto-cjk-extra \
    && fc-cache -fv

# 安装 Playwright 浏览器
RUN playwright install chromium --with-deps
```

---

## 13.6 PDF 导出（WeasyPrint / Chromium）

```python
# render/exporter.py
async def compile_pdf(screenshot_urls: list[str]) -> bytes:
    """
    将多张截图合并为 PDF。
    方案：使用 Playwright 将截图嵌入 HTML 后导出 PDF。
    """
    slides_html = "\n".join([
        f'<div style="page-break-after: always;">'
        f'<img src="{url}" style="width:100%;height:100%;object-fit:contain;"></div>'
        for url in screenshot_urls
    ])
    full_html = f"""
    <html><head>
    <style>
        @page {{ size: 1920px 1080px; margin: 0; }}
        body {{ margin: 0; padding: 0; }}
        div {{ width: 1920px; height: 1080px; }}
        img {{ display: block; }}
    </style>
    </head><body>{slides_html}</body></html>
    """

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(full_html, wait_until="networkidle")
        pdf_bytes = await page.pdf(
            width="1920px",
            height="1080px",
            print_background=True,
        )
        await browser.close()
    return pdf_bytes
```
