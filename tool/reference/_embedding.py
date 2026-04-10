"""
Embedding generation with multi-provider support.

Providers (configured via EMBEDDING_PROVIDER env var):
  - mock    : deterministic fake embeddings, no API needed (default for dev)
  - openai  : OpenAI text-embedding-3-small
  - voyage  : Voyage AI voyage-large-2
  - qwen    : Alibaba Qwen text-embedding-v4 (OpenAI-compatible via dashscope)

For development without API keys, "mock" generates reproducible embeddings
from text hash so relative similarity still has meaning.
"""
import hashlib
import logging
import math
from typing import Optional

from config.settings import settings

logger = logging.getLogger(__name__)

VECTOR_DIM = 1536   # matches EMBEDDING_MODEL dim


def build_embedding_text(case: dict) -> str:
    """拼接案例字段用于生成 embedding（规范见 docs/14）。"""
    parts = [
        f"建筑类型：{case.get('building_type', '')}",
        f"建筑师：{case.get('architect', '')}",
        f"地点：{case.get('location', '')} {case.get('country', '')}",
        f"风格：{'、'.join(case.get('style_tags', []))}",
        f"特征：{'、'.join(case.get('feature_tags', []))}",
        f"规模：{case.get('scale_category', '')}（{case.get('gfa_sqm', '')}㎡）",
        f"描述：{case.get('summary', '')}",
    ]
    return "\n".join(p for p in parts if p.split("：", 1)[1].strip())


def build_query_text(brief: dict) -> str:
    """将 ProjectBriefData dict 转为检索文本。"""
    parts = [
        f"建筑类型：{brief.get('building_type', '')}",
        f"风格偏好：{'、'.join(brief.get('style_preferences', []))}",
        f"项目地点：{brief.get('city', '')} {brief.get('district', '')}",
        f"建筑面积：{brief.get('gross_floor_area', '')}㎡",
        f"特殊要求：{brief.get('special_requirements', '')}",
    ]
    return "\n".join(p for p in parts if p.split("：", 1)[1].strip())


# ── Provider implementations ──────────────────────────────────────────────────

def _mock_embedding(text: str) -> list[float]:
    """
    Deterministic fake embedding from text hash.
    Not semantically meaningful, but reproducible across runs.
    Used for local development without an embedding API key.
    """
    seed_bytes = hashlib.sha256(text.encode("utf-8")).digest()
    # Expand to VECTOR_DIM floats via a simple LCG seeded by the hash
    state = int.from_bytes(seed_bytes[:8], "big")
    values = []
    for _ in range(VECTOR_DIM):
        state = (state * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        values.append((state / 0xFFFFFFFFFFFFFFFF) * 2 - 1)
    # L2-normalise
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


async def _openai_embedding(text: str) -> list[float]:
    try:
        import openai
        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        resp = await client.embeddings.create(
            input=text,
            model=settings.embedding_model,
        )
        return resp.data[0].embedding
    except ImportError:
        raise RuntimeError("openai package not installed. Run: pip install openai")


async def _voyage_embedding(text: str) -> list[float]:
    try:
        import voyageai
        vo = voyageai.AsyncClient(api_key=settings.voyage_api_key)
        result = await vo.embed([text], model="voyage-large-2")
        return result.embeddings[0]
    except ImportError:
        raise RuntimeError("voyageai package not installed. Run: pip install voyageai")


async def _qwen_embedding(text: str) -> list[float]:
    try:
        import openai
        client = openai.AsyncOpenAI(
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_url,
        )
        resp = await client.embeddings.create(
            input=text,
            model=settings.embedding_model,
            dimensions=settings.vector_dim,
            encoding_format="float",
        )
        return resp.data[0].embedding
    except ImportError:
        raise RuntimeError("openai package not installed. Run: pip install openai")


async def get_embedding(text: str) -> list[float]:
    """
    Generate embedding vector for the given text.
    Provider selection via settings.embedding_provider (default: mock).
    """
    provider = getattr(settings, "embedding_provider", "mock")
    if provider == "openai":
        return await _openai_embedding(text)
    elif provider == "voyage":
        return await _voyage_embedding(text)
    elif provider == "qwen":
        return await _qwen_embedding(text)
    else:
        # mock — always available
        return _mock_embedding(text)


def get_embedding_sync(text: str) -> list[float]:
    """Synchronous version (for seed scripts)."""
    provider = getattr(settings, "embedding_provider", "mock")
    if provider == "mock":
        return _mock_embedding(text)
    # For non-mock providers in sync context
    import asyncio
    return asyncio.run(get_embedding(text))
