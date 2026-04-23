from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 数据库
    database_url: str = "postgresql://user:password@localhost:5432/ppt_agent"
    redis_url: str = "redis://localhost:6379/0"

    # LLM
    anthropic_api_key: str = ""
    llm_strong_model: str = "claude-opus-4-6"
    llm_fast_model: str = "claude-sonnet-4-6"
    llm_critic_model: str = "google/gemini-3.1-pro-preview"

    # OpenRouter (优先于 Anthropic 直连，设置后自动切换)
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # 地图
    amap_api_key: str = ""
    amap_secret: str = ""

    # 对象存储
    oss_endpoint: str = ""
    oss_bucket: str = "ppt-agent-assets"
    oss_access_key: str = ""
    oss_secret_key: str = ""
    oss_base_url: str = ""

    # 向量检索
    embedding_model: str = "text-embedding-3-small"
    vector_dim: int = 1536
    embedding_provider: str = "mock"   # mock / openai / voyage / qwen
    openai_api_key: str = ""
    voyage_api_key: str = ""
    qwen_api_key: str = ""
    qwen_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # 渲染
    playwright_headless: bool = True
    slide_width_px: int = 1920
    slide_height_px: int = 1080

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # 业务配置
    max_repair_attempts: int = 3
    max_slides_per_deck: int = 30
    case_library_min_size: int = 30

    # 图像生成 (runninghub) — env 变量约定 RUNNING_HUB_*
    concept_render_enabled: bool = True
    running_hub_key: str = ""
    running_hub_base_url: str = "https://www.runninghub.cn"
    running_hub_workflow_id: str = ""
    running_hub_prompt_node_id: str = "6"
    running_hub_negative_prompt_node_id: str = "7"
    running_hub_init_image_node_id: str = "10"
    running_hub_seed_node_id: str = ""
    running_hub_poll_interval_seconds: float = 3.0
    running_hub_poll_timeout_seconds: float = 180.0
    running_hub_asset_dir: str = "D:/tmp/assets"


settings = Settings()
