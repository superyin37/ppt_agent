"""
LLM 调用封装，统一使用 OpenRouter（openai.AsyncOpenAI，兼容 OpenAI 格式）。

模型名映射：OpenRouter 要求 provider 前缀（如 "anthropic/claude-opus-4-6"），
若 model 中不含 "/" 则自动添加 "anthropic/" 前缀。
"""
from pydantic import BaseModel
from typing import TypeVar, Type
from asyncio import Semaphore
import json
import logging

from config.settings import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

STRONG_MODEL = settings.llm_strong_model
FAST_MODEL = settings.llm_fast_model
CRITIC_MODEL = settings.llm_critic_model

# 并发限制
STRONG_MODEL_SEMAPHORE = Semaphore(2)
FAST_MODEL_SEMAPHORE = Semaphore(8)


def _model_name(model: str) -> str:
    """OpenRouter 需要 'provider/model-name' 格式，若未含 '/' 则自动补 'anthropic/' 前缀。"""
    if "/" not in model:
        return f"anthropic/{model}"
    return model


def _make_openrouter_client():
    from openai import AsyncOpenAI
    return AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )


class LLMError(Exception):
    pass


class LLMParseError(LLMError):
    def __init__(self, message: str, raw_output: str = ""):
        self.raw_output = raw_output
        super().__init__(message)


class LLMRateLimitError(LLMError):
    def __init__(self, retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(f"Rate limited, retry after {retry_after}s")


class LLMContextTooLongError(LLMError):
    pass


class LLMServiceUnavailableError(LLMError):
    pass


async def _call_once(
    model: str,
    system_prompt: str,
    user_message: str,
    temperature: float,
    max_tokens: int,
) -> str:
    """发起单次 LLM 调用，返回原始文本。统一走 OpenRouter。"""
    client = _make_openrouter_client()
    response = await client.chat.completions.create(
        model=_model_name(model),
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    return response.choices[0].message.content.strip()


async def call_llm_structured(
    system_prompt: str,
    user_message: str,
    output_schema: Type[T],
    model: str = FAST_MODEL,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    max_retries: int = 2,
) -> T:
    """调用 LLM 并将输出解析为 Pydantic 模型。失败时自动重试。"""
    schema_json = output_schema.model_json_schema()
    enhanced_system = (
        f"{system_prompt}\n\n"
        f"## 输出约束\n"
        f"你的输出必须是合法的 JSON，且严格符合以下 Schema：\n"
        f"```json\n{json.dumps(schema_json, ensure_ascii=False, indent=2)}\n```\n"
        f"不要输出任何 JSON 以外的内容，不要加 markdown 代码块标记。"
    )

    last_error = None
    current_user_message = user_message
    for attempt in range(max_retries + 1):
        try:
            raw_text = await _call_once(
                model=model,
                system_prompt=enhanced_system,
                user_message=current_user_message,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            # 清理可能的 markdown 包裹
            if raw_text.startswith("```"):
                parts = raw_text.split("```")
                raw_text = parts[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
                raw_text = raw_text.strip()

            # 尝试直接解析；若失败尝试 json.loads → model_validate（更宽容）
            try:
                parsed = output_schema.model_validate_json(raw_text)
            except Exception:
                import json as _json
                parsed = output_schema.model_validate(_json.loads(raw_text))
            logger.info(f"LLM call success: model={model}, attempt={attempt + 1}")
            return parsed

        except Exception as e:
            last_error = e
            logger.warning(f"LLM call attempt {attempt + 1} failed: {e}")
            if attempt < max_retries:
                current_user_message = (
                    f"{user_message}\n\n"
                    f"[上次输出解析失败，错误：{str(e)}，请严格按 JSON Schema 重新输出]"
                )

    raise LLMParseError(
        f"LLM 输出解析失败（{max_retries + 1}次尝试）: {last_error}",
        raw_output=str(last_error),
    )


async def call_llm_multimodal(
    system_prompt: str,
    text_message: str,
    image_url: str,
    output_schema: Type[T],
    model: str = FAST_MODEL,
    max_retries: int = 1,
    max_tokens: int = 2048,
    temperature: float = 0.1,
) -> T:
    """多模态调用（用于 Vision Review），统一走 OpenRouter。含 markdown 清理和解析重试。"""
    enhanced_system = (
        f"{system_prompt}\n\n"
        f"## 输出约束\n"
        f"你的输出必须是合法的 JSON。不要输出任何 JSON 以外的内容，不要加 markdown 代码块标记。"
    )

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            client = _make_openrouter_client()
            response = await client.chat.completions.create(
                model=_model_name(model),
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": enhanced_system},
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": image_url}},
                            {"type": "text", "text": text_message},
                        ],
                    },
                ],
            )
            raw_text = response.choices[0].message.content.strip()

            # Clean markdown wrappers
            if raw_text.startswith("```"):
                parts = raw_text.split("```")
                raw_text = parts[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
                raw_text = raw_text.strip()

            # Parse with fallback
            try:
                return output_schema.model_validate_json(raw_text)
            except Exception:
                return output_schema.model_validate(json.loads(raw_text))

        except Exception as e:
            last_error = e
            logger.warning(f"call_llm_multimodal attempt {attempt + 1} failed: {e}")

    raise LLMParseError(
        f"Multimodal LLM 输出解析失败（{max_retries + 1}次尝试）: {last_error}",
        raw_output=str(last_error),
    )


async def call_llm_with_limit(
    system_prompt: str,
    user_message: str,
    output_schema: Type[T],
    model: str = FAST_MODEL,
    **kwargs,
) -> T:
    sem = STRONG_MODEL_SEMAPHORE if "opus" in model else FAST_MODEL_SEMAPHORE
    async with sem:
        return await call_llm_structured(
            system_prompt=system_prompt,
            user_message=user_message,
            output_schema=output_schema,
            model=model,
            **kwargs,
        )
