# 08. LLM 调用规范

> 最后更新：2026-04-10

---

## 8.1 LLM 接入方式

所有 LLM 调用统一通过 **OpenRouter** 代理，使用 **OpenAI 兼容格式**（`openai.AsyncOpenAI`）。

```python
# config/llm.py
from openai import AsyncOpenAI
from config.settings import settings

client = AsyncOpenAI(
    api_key=settings.openrouter_api_key,
    base_url=settings.openrouter_base_url,   # https://openrouter.ai/api/v1
)
```

> **注意**：早期文档记录使用 `anthropic.AsyncAnthropic` 直连 Anthropic API，
> 当前实际实现已改为 OpenRouter，走 OpenAI 兼容协议。

---

## 8.2 模型配置

模型名通过 `config/settings.py` 环境变量配置，**非硬编码**：

```python
# config/settings.py
class Settings(BaseSettings):
    llm_strong_model: str = "claude-opus-4-6"
    llm_fast_model: str = "claude-sonnet-4-6"
    llm_critic_model: str = "google/gemini-3.1-pro-preview"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

# config/llm.py
STRONG_MODEL = settings.llm_strong_model    # 复杂推理
FAST_MODEL = settings.llm_fast_model        # 简单抽取、按页并发
CRITIC_MODEL = settings.llm_critic_model    # 审查专用
```

OpenRouter 要求 `provider/model-name` 格式，`_model_name()` 自动补前缀：
```python
def _model_name(model: str) -> str:
    if "/" not in model:
        return f"anthropic/{model}"
    return model
```

### 模型选型策略

| 场景 | 模型变量 | 默认值 | 原因 |
|------|---------|--------|------|
| BriefDoc 生成 | STRONG_MODEL | claude-opus-4-6 | 叙事框架 + 建筑领域推理 |
| Outline 生成 | STRONG_MODEL | claude-opus-4-6 | 蓝图槽位分配 + 素材覆盖率分析 |
| Composer（逐页） | STRONG_MODEL | claude-opus-4-6 | LayoutSpec 结构化 + HTML 生成 |
| Visual Theme | STRONG_MODEL | claude-opus-4-6 | 配色 / 字体 / 空间设计推理 |
| Intake Agent | FAST_MODEL | claude-sonnet-4-6 | 结构化抽取，成本敏感 |
| 语义审查 | FAST_MODEL | claude-sonnet-4-6 | 规则明确，不需强推理 |
| Vision 审查（多模态） | CRITIC_MODEL | gemini-3.1-pro | 视觉理解 + 设计审美判断 |

---

## 8.3 核心调用函数

### `call_llm_structured()`

结构化输出的主入口：调用 LLM → JSON 解析 → Pydantic 模型。

```python
async def call_llm_structured(
    system_prompt: str,
    user_message: str,
    output_schema: Type[T],        # Pydantic BaseModel 子类
    model: str = FAST_MODEL,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    max_retries: int = 2,
) -> T:
```

**工作流**：
1. 将 `output_schema.model_json_schema()` 注入 system prompt 尾部（输出约束段）
2. 调用 `_call_once()` → OpenRouter → 获取原始文本
3. 清理 markdown 包裹（\`\`\`json ... \`\`\`）
4. 解析：先 `model_validate_json()`，失败回退 `json.loads()` → `model_validate()`
5. 失败时将错误信息追加到 user\_message，重试（最多 `max_retries` 次）
6. 全部失败抛出 `LLMParseError`

---

### `call_llm_multimodal()`

多模态调用（用于 Vision Review），支持图片 + 文本输入。

```python
async def call_llm_multimodal(
    system_prompt: str,
    text_message: str,
    image_url: str,                # 截图 URL
    output_schema: Type[T],
    model: str = FAST_MODEL,
    max_retries: int = 1,
    max_tokens: int = 2048,
    temperature: float = 0.1,
) -> T:
```

**消息格式**（OpenAI vision 兼容）：
```python
messages=[
    {"role": "system", "content": enhanced_system},
    {"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": image_url}},
        {"type": "text", "text": text_message},
    ]},
]
```

---

### `call_llm_with_limit()`

带信号量限流的封装，自动选择并发限制器。

```python
async def call_llm_with_limit(
    system_prompt: str,
    user_message: str,
    output_schema: Type[T],
    model: str = FAST_MODEL,
    **kwargs,
) -> T:
    sem = STRONG_MODEL_SEMAPHORE if "opus" in model else FAST_MODEL_SEMAPHORE
    async with sem:
        return await call_llm_structured(...)
```

---

## 8.4 并发限流

```python
from asyncio import Semaphore

STRONG_MODEL_SEMAPHORE = Semaphore(2)   # STRONG_MODEL 同时最多 2 个并发
FAST_MODEL_SEMAPHORE   = Semaphore(8)   # FAST_MODEL 同时最多 8 个并发
```

Composer 逐页并发时通过 `call_llm_with_limit()` 自动限流，避免触发 OpenRouter 速率限制。

---

## 8.5 Temperature 设置原则

| 任务类型 | Temperature | 原因 |
|---------|------------|------|
| 信息抽取（Intake） | 0.0 | 需要确定性，避免幻觉 |
| 字段校验 | 0.0 | 纯逻辑判断 |
| 内容生成（Composer） | 0.3 | 轻微创意，但格式约束严格 |
| 大纲生成（Outline） | 0.5 | 需要一定叙事创意 |
| 修复建议（Critic） | 0.2 | 需要明确判断，略有灵活性 |
| 多模态审查（Vision） | 0.1 | 视觉判断需精确 |

---

## 8.6 Token 预算规划

| Agent | System Prompt | 上下文输入 | 最大输出 |
|-------|-------------|----------|---------|
| Intake | ~800 tokens | ~500 tokens | 1024 |
| Reference | ~600 tokens | ~2000 tokens | 1024 |
| BriefDoc | ~1200 tokens | ~3000 tokens | 4096 |
| Outline | ~1000 tokens | ~3000 tokens | 4096 |
| Composer（单页） | ~800 tokens | ~1500 tokens | 2048 |
| Critic（单页） | ~800 tokens | ~1000 tokens | 2048 |
| Visual Theme | ~1000 tokens | ~1500 tokens | 2048 |

---

## 8.7 错误分类与处理

```python
# config/llm.py
class LLMError(Exception): ...
class LLMParseError(LLMError):       raw_output: str
class LLMRateLimitError(LLMError):   retry_after: int
class LLMContextTooLongError(LLMError): ...
class LLMServiceUnavailableError(LLMError): ...
```

| 错误类型 | 策略 | 说明 |
|---------|------|------|
| `LLMParseError` | retry\_with\_hint | 将解析错误追加到 user\_message，重试 |
| `LLMRateLimitError` | retry\_with\_backoff | 指数退避重试 |
| `LLMContextTooLongError` | truncate\_context | 截断上下文 |
| `LLMServiceUnavailableError` | fallback\_or\_fail | 降级或失败 |

---

## 8.8 成本估算（单项目）

| 阶段 | 模型 | 预估调用次数 | 预估 Token | 预估成本 |
|------|------|------------|----------|---------|
| Intake（多轮） | FAST | 3~5 次 | ~5k | $0.02 |
| BriefDoc | STRONG | 1 次 | ~8k | $0.12 |
| Outline | STRONG | 1 次 | ~7k | $0.10 |
| Composer（12页） | STRONG | 12 次 | ~42k | $0.60 |
| Semantic Review（12页） | FAST | 12 次 | ~20k | $0.03 |
| Vision Review（可选） | CRITIC | 12 次 | ~30k | 视模型定价 |
| **合计（不含 Vision）** | | | | **~$0.87/项目** |
