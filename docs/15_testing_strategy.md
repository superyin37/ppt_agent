# 15. 测试策略文档

## 15.1 测试层次划分

```
tests/
├── unit/               # 单元测试（无外部依赖，纯逻辑）
│   ├── test_schema_validation.py
│   ├── test_compute_far.py
│   ├── test_layout_lint.py
│   ├── test_content_fit.py
│   ├── test_repair_executor.py
│   └── test_state_machine.py
├── integration/        # 集成测试（真实 DB + 真实 Redis，Mock 外部 API）
│   ├── test_intake_flow.py
│   ├── test_reference_flow.py
│   ├── test_asset_generation.py
│   ├── test_render_pipeline.py
│   └── test_review_repair.py
└── e2e/                # 端到端测试（完整流程，有限 LLM 调用）
    └── test_full_pipeline.py
```

---

## 15.2 单元测试

### Schema 校验测试

```python
# tests/unit/test_schema_validation.py
import pytest
from schema.project import ProjectBriefData
from schema.slide import SlideSpec, SlideConstraints
from schema.common import BuildingType, LayoutTemplate


class TestProjectBriefData:
    def test_auto_compute_far(self):
        """验证：gfa + site_area → 自动计算 far"""
        brief = ProjectBriefData(
            building_type=BuildingType.MUSEUM,
            gross_floor_area=12000,
            site_area=10000,
        )
        assert brief.far == 1.2

    def test_auto_compute_site_area(self):
        brief = ProjectBriefData(
            building_type=BuildingType.MUSEUM,
            gross_floor_area=12000,
            far=1.5,
        )
        assert brief.site_area == 8000.0

    def test_missing_two_metrics_raises(self):
        """验证：只有一个指标时不报错（校验在 validate_tool 中）"""
        brief = ProjectBriefData(
            building_type=BuildingType.OFFICE,
            gross_floor_area=5000,
        )
        assert brief.far is None
        assert brief.site_area is None


class TestSlideSpec:
    def test_valid_slide_spec(self):
        spec = SlideSpec(
            project_id="00000000-0000-0000-0000-000000000001",
            slide_no=1,
            section="封面",
            title="天津博物馆概念方案",
            purpose="建立项目形象",
            key_message="现代、简约、文化",
            layout_template=LayoutTemplate.COVER_HERO,
        )
        assert spec.slide_no == 1
        assert spec.review_status == "pending"
```

---

### 规则审查测试

```python
# tests/unit/test_layout_lint.py
import pytest
from tool.review.layout_lint import layout_lint
from schema.slide import SlideSpec, BlockContent, SlideConstraints
from schema.common import LayoutTemplate


def make_spec(**kwargs) -> SlideSpec:
    defaults = {
        "project_id": "00000000-0000-0000-0000-000000000001",
        "slide_no": 1,
        "section": "封面",
        "title": "测试标题",
        "purpose": "测试",
        "key_message": "测试信息",
        "layout_template": LayoutTemplate.OVERVIEW_KPI,
        "blocks": [],
    }
    defaults.update(kwargs)
    return SlideSpec(**defaults)


class TestLayoutLint:
    def test_clean_slide_passes(self):
        spec = make_spec(blocks=[
            BlockContent(block_id="kpi_items", block_type="table",
                         content=[{"value": "12000", "unit": "㎡", "label": "建筑面积"}])
        ])
        result = layout_lint(spec)
        assert result.fail_count == 0

    def test_text_overflow_detected(self):
        long_text = "A" * 300
        spec = make_spec(
            constraints=SlideConstraints(max_text_chars=200),
            blocks=[BlockContent(block_id="body", block_type="text", content=long_text)]
        )
        result = layout_lint(spec)
        codes = [i.rule_code for i in result.issues]
        assert "TEXT_OVERFLOW" in codes

    def test_missing_required_block(self):
        spec = make_spec(
            layout_template=LayoutTemplate.COVER_HERO,
            blocks=[]  # cover-hero 需要 hero_image
        )
        result = layout_lint(spec)
        codes = [i.rule_code for i in result.issues]
        assert "MISSING_REQUIRED_BLOCK" in codes

    def test_empty_slide_detected(self):
        spec = make_spec(blocks=[
            BlockContent(block_id="empty", block_type="text", content="   ")
        ])
        result = layout_lint(spec)
        codes = [i.rule_code for i in result.issues]
        assert "EMPTY_SLIDE" in codes

    def test_title_too_long(self):
        spec = make_spec(title="这是一个超过二十五个字符的超长标题文字内容超出限制")
        result = layout_lint(spec)
        codes = [i.rule_code for i in result.issues]
        assert "TITLE_TOO_LONG" in codes
```

---

### FAR 计算测试

```python
# tests/unit/test_compute_far.py
from tool.input.compute_far import compute_far_metrics, ComputeFARInput
from api.exceptions import ToolError
import pytest


class TestComputeFAR:
    def test_compute_far_from_gfa_and_site(self):
        result = compute_far_metrics(ComputeFARInput(gross_floor_area=12000, site_area=10000))
        assert result.far == 1.2
        assert result.computed_field == "far"

    def test_compute_site_from_gfa_and_far(self):
        result = compute_far_metrics(ComputeFARInput(gross_floor_area=15000, far=1.5))
        assert result.site_area == 10000.0
        assert result.computed_field == "site_area"

    def test_insufficient_metrics_raises(self):
        with pytest.raises(ToolError) as exc:
            compute_far_metrics(ComputeFARInput(gross_floor_area=5000))
        assert exc.value.code == "INSUFFICIENT_METRICS"
```

---

## 15.3 集成测试

### 测试环境配置

```python
# tests/conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.base import Base
from config.settings import settings

# 使用独立测试数据库
TEST_DB_URL = settings.DATABASE_URL.replace("/ppt_agent", "/ppt_agent_test")

@pytest.fixture(scope="session")
def test_engine():
    engine = create_engine(TEST_DB_URL)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture
def db_session(test_engine):
    Session = sessionmaker(bind=test_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()

@pytest.fixture
def mock_llm(monkeypatch):
    """Mock LLM 调用，返回预设响应"""
    from unittest.mock import AsyncMock
    import config.llm as llm_module

    async def mock_call(system_prompt, user_message, output_schema, **kwargs):
        # 根据 output_schema 返回预设数据
        return output_schema.model_validate(MOCK_RESPONSES.get(output_schema.__name__, {}))

    monkeypatch.setattr(llm_module, "call_llm_structured", mock_call)

@pytest.fixture
def mock_amap(monkeypatch):
    """Mock 高德地图 API"""
    from unittest.mock import AsyncMock
    import tool.site._amap_client as amap

    async def mock_get(endpoint, params):
        if "geocode/geo" in endpoint:
            return {"status": "1", "geocodes": [{"location": "117.19,39.13", "formatted_address": "天津市河西区..."}]}
        return {"status": "1"}

    monkeypatch.setattr(amap, "amap_get", mock_get)
```

---

### Intake 流程集成测试

```python
# tests/integration/test_intake_flow.py
import pytest
from httpx import AsyncClient
from main import app

MOCK_RESPONSES = {
    "ExtractBriefOutput": {
        "extracted": {
            "building_type": "museum",
            "client_name": "天津文化集团",
            "gross_floor_area": 12000,
            "site_area": 10000,
            "style_preferences": ["modern", "minimal"],
            "site_address": "天津市河西区...",
            "missing_fields": [],
            "is_complete": True,
        },
        "missing_fields": [],
        "is_complete": True,
        "confirmation_summary": "项目信息已确认：天津博物馆，12000㎡，现代简约风格。"
    }
}


@pytest.mark.asyncio
async def test_intake_full_flow(mock_llm, mock_amap, db_session):
    async with AsyncClient(app=app, base_url="http://test") as client:
        # 1. 创建项目
        resp = await client.post("/projects", json={"name": "测试项目"})
        assert resp.status_code == 201
        project_id = resp.json()["data"]["id"]

        # 2. 提交项目信息
        resp = await client.patch(f"/projects/{project_id}/brief", json={
            "raw_text": "天津文化集团博物馆项目，建筑面积12000平米，用地10000平米，现代简约风格"
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["brief"]["is_complete"] is True

        # 3. 确认信息
        resp = await client.post(f"/projects/{project_id}/confirm-brief")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "INTAKE_CONFIRMED"
```

---

## 15.4 端到端测试

```python
# tests/e2e/test_full_pipeline.py
"""
端到端测试：完整走一遍流程，使用真实 LLM（限制模型用 haiku 降低成本）。
仅在 CI 的 nightly 任务中运行，不在每次 PR 时运行。
"""
import pytest
import asyncio
from httpx import AsyncClient
from main import app


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_pipeline_museum():
    async with AsyncClient(app=app, base_url="http://test") as client:
        # 1. 创建项目
        resp = await client.post("/projects", json={"name": "E2E 测试博物馆"})
        project_id = resp.json()["data"]["id"]

        # 2. Intake（使用预设完整信息，避免多轮）
        await client.patch(f"/projects/{project_id}/brief", json={
            "raw_text": (
                "甲方：天津文化集团。建筑类型：博物馆。"
                "建筑面积12000平米，用地面积10000平米，容积率1.2。"
                "地址：天津市河西区友谊路。风格：现代、极简。"
            )
        })
        await client.post(f"/projects/{project_id}/confirm-brief")

        # 3. 场地
        await client.post(f"/projects/{project_id}/site/point",
                          json={"longitude": 117.19, "latitude": 39.13})

        # 4. 案例推荐与选择（使用种子数据中的真实案例）
        resp = await client.post(f"/projects/{project_id}/references/recommend",
                                 json={"top_k": 5})
        cases = resp.json()["data"]["cases"]
        assert len(cases) > 0
        await client.post(f"/projects/{project_id}/references/select", json={
            "project_id": project_id,
            "selections": [{"case_id": cases[0]["id"], "selected_tags": ["造型"]}]
        })

        # 5. 资产生成（等待完成）
        resp = await client.post(f"/projects/{project_id}/assets/generate")
        job_id = resp.json()["data"]["job_id"]
        await wait_for_job(client, job_id, timeout=120)

        # 6. 大纲生成与确认
        resp = await client.post(f"/projects/{project_id}/outline/generate")
        await wait_for_job(client, resp.json()["data"]["job_id"], timeout=60)
        await client.post(f"/projects/{project_id}/outline/confirm")

        # 7. 页面规划
        resp = await client.post(f"/projects/{project_id}/slides/plan")
        await wait_for_job(client, resp.json()["data"]["job_id"], timeout=120)

        # 8. 渲染
        resp = await client.post(f"/projects/{project_id}/render")
        await wait_for_job(client, resp.json()["data"]["job_id"], timeout=300)

        # 9. 审查
        await client.post(f"/projects/{project_id}/review",
                          json={"layers": ["rule", "semantic"]})

        # 10. 导出
        resp = await client.post(f"/projects/{project_id}/export",
                                 json={"export_type": "pdf"})
        job_id = resp.json()["data"]["job_id"]
        await wait_for_job(client, job_id, timeout=120)

        # 验证导出结果
        project = (await client.get(f"/projects/{project_id}")).json()["data"]
        assert project["status"] == "EXPORTED"


async def wait_for_job(client, job_id: str, timeout: int = 120, poll_interval: int = 3):
    """轮询任务状态直到完成或超时"""
    for _ in range(timeout // poll_interval):
        resp = await client.get(f"/jobs/{job_id}")
        status = resp.json()["data"]["status"]
        if status == "success":
            return
        if status == "failed":
            raise AssertionError(f"Job {job_id} failed")
        await asyncio.sleep(poll_interval)
    raise TimeoutError(f"Job {job_id} timed out after {timeout}s")
```

---

## 15.5 测试数据 Fixture

```python
# tests/fixtures/project_brief.py

COMPLETE_MUSEUM_BRIEF = {
    "building_type": "museum",
    "client_name": "天津文化集团",
    "style_preferences": ["modern", "minimal"],
    "site_address": "天津市河西区友谊路",
    "province": "天津市",
    "city": "天津市",
    "district": "河西区",
    "gross_floor_area": 12000,
    "site_area": 10000,
    "far": 1.2,
    "missing_fields": [],
    "is_complete": True,
}

MINIMAL_OUTLINE_SPEC = {
    "deck_title": "天津博物馆概念方案汇报",
    "theme": "modern-cultural-minimal",
    "total_pages": 8,
    "sections": ["封面", "项目概述", "场地分析", "案例参考", "设计策略", "结束"],
    "slides": [
        {"slide_no": 1, "section": "封面", "title": "天津博物馆概念方案",
         "purpose": "建立形象", "key_message": "现代、简约、文化",
         "required_assets": [], "recommended_template": "cover-hero",
         "estimated_content_density": "low"},
        # ... 其余页
    ]
}
```

---

## 15.6 CI 流水线配置

```yaml
# .github/workflows/test.yml
name: Test

on: [push, pull_request]

jobs:
  unit-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.11"}
      - run: pip install poetry && poetry install
      - run: poetry run pytest tests/unit/ -v --tb=short

  integration-test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_DB: ppt_agent_test
          POSTGRES_USER: user
          POSTGRES_PASSWORD: password
        ports: ["5432:5432"]
      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.11"}
      - run: pip install poetry && poetry install
      - run: playwright install chromium --with-deps
      - run: poetry run pytest tests/integration/ -v --tb=short
        env:
          DATABASE_URL: postgresql://user:password@localhost:5432/ppt_agent_test
          REDIS_URL: redis://localhost:6379/0

  e2e-test:
    runs-on: ubuntu-latest
    if: github.event_name == 'schedule'   # 仅 nightly 运行
    # ... （同上，加 ANTHROPIC_API_KEY）
```

---

## 15.7 测试覆盖率目标

| 模块 | 目标覆盖率 | 说明 |
|------|---------|------|
| schema/ | 95%+ | 所有校验逻辑必须覆盖 |
| tool/input/ | 90%+ | 核心计算逻辑 |
| tool/review/ | 90%+ | 所有规则 ID 需有对应测试用例 |
| tool/render/ | 70%+ | HTML 渲染逻辑 |
| agent/ | 60%+ | LLM 调用用 Mock 覆盖主路径 |
| api/ | 80%+ | 接口校验和状态流转 |
