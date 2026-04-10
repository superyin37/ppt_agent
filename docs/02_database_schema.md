# 02. 数据库表设计

> 最后更新：2026-04-10

## 2.1 设计原则

- 所有核心表包含 `id`、`project_id`、`version`、`status`、`created_at`、`updated_at`
- 使用 UUID 作为主键
- 软删除（`deleted_at`），不物理删除业务数据
- JSON 字段使用 PostgreSQL `jsonb` 类型
- 向量字段使用 `pgvector` 扩展的 `vector` 类型

---

## 2.2 核心表定义

### projects — 项目主表

```sql
CREATE TABLE projects (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    status          VARCHAR(50) NOT NULL DEFAULT 'INIT',
    -- 状态枚举：INIT / INTAKE_IN_PROGRESS / INTAKE_CONFIRMED /
    --          REFERENCE_SELECTION / ASSET_GENERATING / MATERIAL_READY /
    --          OUTLINE_READY / BINDING / SLIDE_PLANNING / RENDERING /
    --          REVIEWING / READY_FOR_EXPORT / EXPORTED / FAILED
    current_phase   VARCHAR(50),
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);

CREATE INDEX idx_projects_status ON projects(status);
```

---

### project_briefs — 项目信息采集结果

```sql
CREATE TABLE project_briefs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL REFERENCES projects(id),
    version             INTEGER NOT NULL DEFAULT 1,
    status              VARCHAR(50) NOT NULL DEFAULT 'draft',
    -- status: draft / confirmed

    -- 建筑基本信息
    building_type       VARCHAR(100),           -- 建筑类型：museum / office / residential / mixed
    client_name         VARCHAR(255),           -- 甲方名称
    style_preferences   JSONB NOT NULL DEFAULT '[]',     -- 风格偏好：["modern", "minimal"]
    special_requirements TEXT,                  -- 特殊要求

    -- 指标
    gross_floor_area    FLOAT,                  -- 建筑面积（㎡）
    site_area           FLOAT,                  -- 用地面积（㎡）
    far                 FLOAT,                  -- 容积率

    -- 地址信息
    site_address        TEXT,
    province            VARCHAR(100),
    city                VARCHAR(100),
    district            VARCHAR(100),

    -- 原始输入缓存
    raw_input           TEXT,                   -- 用户原始输入
    missing_fields      JSONB NOT NULL DEFAULT '[]',     -- 当前缺失字段列表
    conversation_history JSONB NOT NULL DEFAULT '[]',    -- 对话历史摘要

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_project_briefs_project_id ON project_briefs(project_id);
CREATE UNIQUE INDEX idx_project_briefs_latest ON project_briefs(project_id, version);
```

---

### site_locations — 场地点位

```sql
CREATE TABLE site_locations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID NOT NULL REFERENCES projects(id),
    longitude   FLOAT NOT NULL,
    latitude    FLOAT NOT NULL,
    poi_name    VARCHAR(255),               -- 附近标志性地点
    address_resolved TEXT,                 -- 逆地理编码结果
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_site_locations_project_id ON site_locations(project_id);
```

---

### site_polygons — 地块范围

```sql
CREATE TABLE site_polygons (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id),
    version         INTEGER NOT NULL DEFAULT 1,
    geojson         JSONB NOT NULL,             -- GeoJSON Polygon
    area_calculated FLOAT,                      -- 计算面积（㎡）
    perimeter       FLOAT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_site_polygons_project_id ON site_polygons(project_id);
```

---

### reference_cases — 案例库

```sql
CREATE TABLE reference_cases (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           VARCHAR(500) NOT NULL,
    architect       VARCHAR(255),
    location        VARCHAR(255),
    country         VARCHAR(100),
    building_type   VARCHAR(100) NOT NULL,
    style_tags      JSONB NOT NULL DEFAULT '[]',     -- ["modern", "cultural"]
    feature_tags    JSONB NOT NULL DEFAULT '[]',     -- ["造型", "材质", "交通组织"]
    scale_category  VARCHAR(50),            -- small(<5000) / medium(5000-30000) / large(>30000)
    gfa_sqm         FLOAT,
    year_completed  INTEGER,
    images          JSONB NOT NULL DEFAULT '[]',     -- [{url, caption, type}]
    summary         TEXT,
    detail_url      VARCHAR(1000),
    source          VARCHAR(255),           -- ArchDaily / dezeen / 谷德

    -- 向量检索（pgvector 列通过 migration 添加，ORM 中不直接声明）
    -- embedding       vector(1536),

    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_reference_cases_building_type ON reference_cases(building_type);
CREATE INDEX idx_reference_cases_embedding ON reference_cases USING ivfflat (embedding vector_cosine_ops);
```

---

### project_reference_selections — 项目案例选择

```sql
CREATE TABLE project_reference_selections (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id),
    case_id         UUID NOT NULL REFERENCES reference_cases(id),
    selected_tags   JSONB NOT NULL DEFAULT '[]',         -- 用户勾选的标签
    selection_reason TEXT,                       -- Agent 生成的选择理由
    rank            INTEGER,                     -- 排序
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(project_id, case_id)
);

CREATE INDEX idx_ref_selections_project_id ON project_reference_selections(project_id);
```

---

### material_packages — 素材包

```sql
CREATE TABLE material_packages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id),
    version         INTEGER NOT NULL DEFAULT 1,
    status          VARCHAR(50) NOT NULL DEFAULT 'ready',
    source_hash     VARCHAR(128),               -- 素材来源哈希
    manifest_json   JSONB,                      -- 素材包清单
    summary_json    JSONB,                      -- 素材包摘要
    created_from    JSONB,                      -- 创建来源信息

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_material_packages_project_id ON material_packages(project_id);
```

---

### material_items — 素材条目

```sql
CREATE TABLE material_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    package_id      UUID NOT NULL REFERENCES material_packages(id),
    logical_key     VARCHAR(255) NOT NULL,      -- 素材逻辑键
    kind            VARCHAR(50) NOT NULL,       -- 素材类别
    format          VARCHAR(50) NOT NULL,       -- 素材格式
    title           VARCHAR(500),
    source_path     TEXT,                       -- 原始文件路径
    preview_url     VARCHAR(1000),              -- 预览 URL
    content_url     VARCHAR(1000),              -- 内容 URL
    text_content    TEXT,                       -- 文本内容
    structured_data JSONB,                      -- 结构化数据
    tags            JSONB,                      -- 标签列表
    source_hash     VARCHAR(128),               -- 来源哈希
    metadata_json   JSONB,                      -- 元数据

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_material_items_package_id ON material_items(package_id);
CREATE INDEX idx_material_items_logical_key ON material_items(logical_key);
CREATE INDEX idx_material_items_kind ON material_items(kind);
CREATE INDEX idx_material_items_format ON material_items(format);
```

---

### assets — 中间资产

```sql
CREATE TABLE assets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id),
    version         INTEGER NOT NULL DEFAULT 1,
    status          VARCHAR(50) NOT NULL DEFAULT 'pending',
    -- status: pending / generating / ready / failed

    asset_type      VARCHAR(100) NOT NULL,
    -- asset_type: image / chart / map / case_card / case_comparison /
    --             text_summary / kpi_table / outline / document

    subtype         VARCHAR(100),
    title           VARCHAR(500),
    data_json       JSONB,                      -- 原始数据
    config_json     JSONB,                      -- 生成配置
    image_url       VARCHAR(1000),              -- 图片/图表文件 URL
    summary         TEXT,                       -- 摘要文本
    source_info     JSONB,                      -- 数据来源
    error_message   TEXT,

    -- 素材包关联
    package_id      UUID,                       -- 关联素材包
    source_item_id  UUID,                       -- 来源素材条目
    logical_key     VARCHAR(255),               -- 素材逻辑键
    variant         VARCHAR(50),                -- 变体标识
    render_role     VARCHAR(100),               -- 渲染角色
    is_primary      BOOLEAN NOT NULL DEFAULT false,  -- 是否为主资产

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_assets_project_id ON assets(project_id);
CREATE INDEX idx_assets_type ON assets(project_id, asset_type);
CREATE INDEX idx_assets_package_id ON assets(package_id);
CREATE INDEX idx_assets_source_item_id ON assets(source_item_id);
CREATE INDEX idx_assets_logical_key ON assets(logical_key);
```

---

### brief_docs — 设计建议书大纲

```sql
CREATE TABLE brief_docs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id              UUID NOT NULL REFERENCES projects(id),
    package_id              UUID,                       -- 关联素材包
    version                 INTEGER NOT NULL DEFAULT 1,
    status                  VARCHAR(50) NOT NULL DEFAULT 'draft',
    -- status: draft / confirmed

    outline_json            JSONB NOT NULL,             -- 结构化大纲内容
    slot_assignments_json   JSONB,                      -- Outline Agent 槽位分配（SlotAssignment 数组）
    narrative_summary       TEXT,                       -- 叙事摘要
    material_summary_json   JSONB,                      -- 素材摘要
    evidence_keys_json      JSONB,                      -- 证据键列表

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_brief_docs_project_id ON brief_docs(project_id);
CREATE INDEX idx_brief_docs_package_id ON brief_docs(package_id);
```

---

### outlines — PPT 大纲

```sql
CREATE TABLE outlines (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id),
    package_id      UUID,                       -- 关联素材包
    version         INTEGER NOT NULL DEFAULT 1,
    status          VARCHAR(50) NOT NULL DEFAULT 'draft',
    -- status: draft / confirmed

    deck_title      VARCHAR(500),
    theme           VARCHAR(100),               -- modern-cultural-minimal
    total_pages     INTEGER,
    spec_json       JSONB NOT NULL,             -- 完整 OutlineSpec JSON
    coverage_json   JSONB,                      -- 素材覆盖度
    slot_binding_hints_json JSONB,              -- 槽位绑定提示
    confirmed_at    TIMESTAMPTZ,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_outlines_project_id ON outlines(project_id);
CREATE INDEX idx_outlines_package_id ON outlines(package_id);
```

---

### slide_material_bindings — 页面素材绑定

```sql
CREATE TABLE slide_material_bindings (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id              UUID NOT NULL REFERENCES projects(id),
    package_id              UUID NOT NULL REFERENCES material_packages(id),
    outline_id              UUID REFERENCES outlines(id),
    slide_id                UUID REFERENCES slides(id),
    slide_no                INTEGER NOT NULL,
    slot_id                 VARCHAR(100) NOT NULL,      -- 槽位 ID
    version                 INTEGER NOT NULL DEFAULT 1,
    status                  VARCHAR(50) NOT NULL DEFAULT 'ready',

    must_use_item_ids       JSONB,              -- 必须使用的素材 ID 列表
    optional_item_ids       JSONB,              -- 可选素材 ID 列表
    derived_asset_ids       JSONB,              -- 派生资产 ID 列表
    evidence_snippets       JSONB,              -- 证据片段
    coverage_score          FLOAT,              -- 覆盖度评分
    missing_requirements    JSONB,              -- 缺失需求
    binding_reason          TEXT,               -- 绑定理由

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_slide_material_bindings_project_id ON slide_material_bindings(project_id);
CREATE INDEX idx_slide_material_bindings_package_id ON slide_material_bindings(package_id);
CREATE INDEX idx_slide_material_bindings_slide_no ON slide_material_bindings(slide_no);
CREATE INDEX idx_slide_material_bindings_slot_id ON slide_material_bindings(slot_id);
```

---

### slides — 页面规格与渲染结果

```sql
CREATE TABLE slides (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL REFERENCES projects(id),
    package_id          UUID,                       -- 关联素材包
    outline_id          UUID REFERENCES outlines(id),
    binding_id          UUID,                       -- 关联素材绑定
    version             INTEGER NOT NULL DEFAULT 1,

    slide_no            INTEGER NOT NULL,
    section             VARCHAR(255),
    title               VARCHAR(500),
    purpose             TEXT,
    key_message         TEXT,
    layout_template     VARCHAR(100),

    spec_json           JSONB NOT NULL,         -- 完整 SlideSpec JSON
    source_refs_json    JSONB,                  -- 来源引用
    evidence_refs_json  JSONB,                  -- 证据引用
    html_content        TEXT,                   -- 渲染后 HTML
    screenshot_url      VARCHAR(1000),          -- 截图 URL
    repair_count        INTEGER NOT NULL DEFAULT 0,

    status              VARCHAR(50) NOT NULL DEFAULT 'pending',
    -- status: pending / spec_ready / rendered / review_pending /
    --         review_passed / repair_needed / repair_in_progress /
    --         ready / failed

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_slides_project_id ON slides(project_id);
CREATE INDEX idx_slides_outline_id ON slides(outline_id);
CREATE INDEX idx_slides_slide_no ON slides(project_id, slide_no);
CREATE INDEX idx_slides_package_id ON slides(package_id);
CREATE INDEX idx_slides_binding_id ON slides(binding_id);
```

---

### visual_themes — 视觉主题

```sql
CREATE TABLE visual_themes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id),
    version         INTEGER NOT NULL DEFAULT 1,
    status          VARCHAR(50) NOT NULL DEFAULT 'draft',
    -- status: draft / confirmed

    theme_json      JSONB NOT NULL,             -- 完整主题定义 JSON

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_visual_themes_project_id ON visual_themes(project_id);
```

---

### reviews — 审查报告

```sql
CREATE TABLE reviews (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id),
    target_type     VARCHAR(50) NOT NULL,       -- slide / deck
    target_id       UUID NOT NULL,
    review_layer    VARCHAR(50) NOT NULL,       -- rule / semantic / vision
    severity        VARCHAR(10),               -- P0 / P1 / P2 / PASS
    final_decision  VARCHAR(50),               -- pass / repair_required / escalate_human
    issues_json     JSONB NOT NULL DEFAULT '[]',
    repair_plan     JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_reviews_target ON reviews(target_type, target_id);
CREATE INDEX idx_reviews_project_id ON reviews(project_id);
```

---

### jobs — 异步任务记录

```sql
CREATE TABLE jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id),
    job_type        VARCHAR(100) NOT NULL,
    -- job_type: asset_generation / slide_render / review / export

    celery_task_id  VARCHAR(255),
    status          VARCHAR(50) NOT NULL DEFAULT 'queued',
    -- status: queued / running / success / failed / retrying

    input_json      JSONB,
    output_json     JSONB,
    error_message   TEXT,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_jobs_project_id ON jobs(project_id);
CREATE INDEX idx_jobs_celery_task_id ON jobs(celery_task_id);
```

---

### exports — 导出记录

```sql
CREATE TABLE exports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id),
    export_type     VARCHAR(20) NOT NULL,       -- pdf / pptx
    status          VARCHAR(50) NOT NULL DEFAULT 'pending',
    file_url        VARCHAR(1000),
    file_size_bytes INTEGER,
    page_count      INTEGER,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX idx_exports_project_id ON exports(project_id);
```

---

## 2.3 索引策略汇总

| 表 | 索引字段 | 类型 | 用途 |
|---|---------|------|------|
| reference_cases | embedding | ivfflat | 向量相似度检索 |
| reference_cases | building_type | btree | 按类型过滤 |
| material_packages | project_id | btree | 按项目查素材包 |
| material_items | package_id | btree | 按素材包查素材条目 |
| material_items | logical_key | btree | 按逻辑键查素材 |
| material_items | kind | btree | 按类别筛选 |
| material_items | format | btree | 按格式筛选 |
| assets | (project_id, asset_type) | btree | 按类型查询资产 |
| assets | package_id | btree | 按素材包查资产 |
| assets | source_item_id | btree | 按来源素材查资产 |
| assets | logical_key | btree | 按逻辑键查资产 |
| brief_docs | project_id | btree | 按项目查建议书 |
| brief_docs | package_id | btree | 按素材包查建议书 |
| outlines | package_id | btree | 按素材包查大纲 |
| slide_material_bindings | project_id | btree | 按项目查绑定 |
| slide_material_bindings | package_id | btree | 按素材包查绑定 |
| slide_material_bindings | slide_no | btree | 按页码查绑定 |
| slide_material_bindings | slot_id | btree | 按槽位查绑定 |
| slides | (project_id, slide_no) | btree | 按页码排序 |
| slides | package_id | btree | 按素材包查页面 |
| slides | binding_id | btree | 按绑定查页面 |
| visual_themes | project_id | btree | 按项目查主题 |
| reviews | (target_type, target_id) | btree | 按页面查审查 |

---

## 2.4 通用触发器：自动更新 updated_at

```sql
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 对每张需要的表执行：
CREATE TRIGGER trg_projects_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
-- （outlines、slides、assets、project_briefs、brief_docs、
--   visual_themes、material_packages、material_items、
--   slide_material_bindings 同理）
```
