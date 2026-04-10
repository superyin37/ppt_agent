"""
PPT 生成蓝图 — manus.md 40 页结构的完整代码化定义

每个 PageSlot / PageSlotGroup 对应 manus.md 中的一页或一组页面。
Outline Agent 读取此蓝图，结合 brief_doc 生成 SlotAssignmentList。
"""
from schema.page_slot import PageSlot, PageSlotGroup, GenerationMethod

M = GenerationMethod  # 简写

PPT_BLUEPRINT: list[PageSlot | PageSlotGroup] = [

    # ══════════════════════════════════════════════════════════
    # 封面 & 目录
    # ══════════════════════════════════════════════════════════
    PageSlot(
        slot_id="cover",
        title="封面",
        chapter="封面",
        content_task=(
            "生成封面。① 生成汇报标题、slogan（一句话点题）、英文翻译。"
            "② 调用 Nanobanana 生成项目 logo：简洁抽象线条画，与整体 PPT 风格统一。"
            "标题应简洁有力，英文翻译字面准确且有设计感。"
        ),
        required_inputs=["brief_doc", "project_name"],
        generation_methods=[M.NANOBANANA, M.LLM_TEXT],
        layout_hint="full-bleed 或 split 封面，呼应 CoverStyle.layout_mood",
        is_cover=True,
    ),

    PageSlot(
        slot_id="toc",
        title="目录",
        chapter="目录",
        content_task=(
            "生成目录页。① 调用 Nanobanana 生成目录插画：高度抽象概括设计意向，"
            "与设计主题呼应，具有艺术感。② 生成目录标题列表（章节名 + 页码）。"
        ),
        required_inputs=["brief_doc"],
        generation_methods=[M.NANOBANANA, M.LLM_TEXT],
        layout_hint="split-h：左侧大插画，右侧目录列表",
    ),

    # ══════════════════════════════════════════════════════════
    # 第一章：背景研究
    # ══════════════════════════════════════════════════════════
    PageSlot(
        slot_id="chapter-1-divider",
        title="背景研究",
        chapter="背景研究",
        content_task="章节过渡页。标题：背景研究，英文翻译：Background Research。",
        generation_methods=[M.LLM_TEXT],
        layout_hint="full-bleed，章节编号 + 中英文标题",
        is_chapter_divider=True,
    ),

    PageSlotGroup(
        group_id="policy-pages",
        slot_template=PageSlot(
            slot_id="policy",
            title="政策分析",
            chapter="背景研究",
            content_task=(
                "分析设计建议书大纲中相关政策信息，筛选时效性强、与项目匹配度高的政策条目。"
                "每条提供：政策名称、发布时间、核心要点、与项目的关联说明。"
                "提供政策来源网页链接。内容按发布时间倒序排列。"
            ),
            required_inputs=["brief_doc", "web_search_policy"],
            generation_methods=[M.LLM_TEXT, M.WEB_SEARCH],
            layout_hint="sidebar 或 single-column：政策条目列表 + 来源链接",
        ),
        repeat_count_min=2,
        repeat_count_max=2,
        repeat_hint="固定 2 页政策内容",
    ),

    PageSlot(
        slot_id="policy-impact",
        title="政策影响分析",
        chapter="背景研究",
        content_task=(
            "统筹政策分析内容，分析这些政策对项目的综合影响。"
            "绘制政策影响可视化图表（影响矩阵、雷达图或分类气泡图）。"
            "图表需清晰标注政策名称与影响维度（用地、业态、指标、运营等）。"
        ),
        required_inputs=["brief_doc"],
        generation_methods=[M.LLM_TEXT, M.CHART],
        layout_hint="split-h 或 hero-strip：大图表 + 文字分析",
    ),

    PageSlot(
        slot_id="upper-planning",
        title="上位规划分析",
        chapter="背景研究",
        content_task=(
            "分析设计建议书大纲中的上位规划信息（城市总规、控规、专项规划等）。"
            "注意规划时效性及与项目的匹配程度。"
            "分析上位规划对项目的影响并绘制对比表格（规划名称 / 核心要求 / 对项目影响）。"
            "提供规划文件来源链接。"
        ),
        required_inputs=["brief_doc", "web_search_planning"],
        generation_methods=[M.LLM_TEXT, M.WEB_SEARCH, M.CHART],
        layout_hint="sidebar：规划对比表格 + 文字说明 + 链接注释",
    ),

    PageSlot(
        slot_id="transport-map",
        title="交通与基础设施",
        chapter="背景研究",
        content_task=(
            "展示三张地图资产：枢纽站点分布图、外部交通站点图、周边基础设施建设规划图。"
            "标注各图的关键交通节点及其距离项目的步行/车行时间。"
        ),
        required_inputs=["map_hub_stations", "map_transport_nodes", "map_infra_plan"],
        generation_methods=[M.ASSET_REF],
        layout_hint="triptych：三图并排，下方简要说明条",
    ),

    PageSlot(
        slot_id="cultural-analysis",
        title="文化特征分析",
        chapter="背景研究",
        content_task=(
            "分析设计建议书大纲中的文化特征信息（历史文脉、地域文化、人文特色）。"
            "提炼核心文化意向词（3~5 个），阐述对项目设计的影响。"
            "调用 Nanobanana 生成描述本地文化的插画（风格与 VisualTheme 协调）。"
        ),
        required_inputs=["brief_doc"],
        generation_methods=[M.LLM_TEXT, M.NANOBANANA],
        layout_hint="split-h：左侧文化分析，右侧 Nanobanana 文化插画",
    ),

    PageSlotGroup(
        group_id="economic-pages",
        slot_template=PageSlot(
            slot_id="economic",
            title="经济背景分析",
            chapter="背景研究",
            content_task=(
                "展示城市经济图表资产（GDP 及增速、常驻人口及增速、城镇化率、"
                "第三产业发展情况及增速、产业结构、消费品零售总额、城镇居民人均收支）。"
                "简要分析数据，总结城市经济背景及对项目的机遇与挑战。"
            ),
            required_inputs=[
                "chart_gdp", "chart_population", "chart_urbanization",
                "chart_tertiary", "chart_industry_structure",
                "chart_retail", "chart_income_expense",
            ],
            generation_methods=[M.ASSET_REF, M.LLM_TEXT],
            layout_hint="grid 2×3 或 3×2：图表卡片 + 底部文字总结",
        ),
        repeat_count_min=3,
        repeat_count_max=3,
        repeat_hint="固定 3 页经济数据",
    ),

    # ══════════════════════════════════════════════════════════
    # 第二章：场地分析
    # ══════════════════════════════════════════════════════════
    PageSlot(
        slot_id="chapter-2-divider",
        title="场地分析",
        chapter="场地分析",
        content_task="章节过渡页。标题：场地分析，英文翻译：Site Analysis。",
        generation_methods=[M.LLM_TEXT],
        layout_hint="full-bleed 章节页",
        is_chapter_divider=True,
    ),

    PageSlotGroup(
        group_id="site-location-pages",
        slot_template=PageSlot(
            slot_id="site-location",
            title="场地区位与四至分析",
            chapter="场地分析",
            content_task=(
                "展示场地区位地图资产（周边基础设施规划、外部交通站点、枢纽站点、场地四至）。"
                "进行项目四至分析：地块优劣势、区位优势、设计注意事项（简洁条目式）。"
            ),
            required_inputs=["map_site_boundary", "map_transport_nodes", "map_hub_stations"],
            generation_methods=[M.ASSET_REF, M.LLM_TEXT],
            layout_hint="overlay-mosaic：大地图 + 浮动分析标注面板",
        ),
        repeat_count_min=4,
        repeat_count_max=4,
        repeat_hint="固定 4 页场地区位内容",
    ),

    PageSlot(
        slot_id="poi-analysis",
        title="场地 POI 业态分析",
        chapter="场地分析",
        content_task=(
            "分析场地 POI 数据，分析周边业态情况（餐饮、零售、文化、教育、交通等类型占比）。"
            "绘制业态可视化图表（饼图、环形图或气泡图）。"
            "提出 3~5 条设计注意事项（精简条目式）。"
        ),
        required_inputs=["poi_data"],
        generation_methods=[M.CHART, M.LLM_TEXT],
        layout_hint="split-h：左 POI 分类图表，右文字分析 + 注意事项",
    ),

    PageSlot(
        slot_id="site-summary",
        title="场地综合分析",
        chapter="场地分析",
        content_task=(
            "总结场地所有分析内容，从宏观（城市/区域）和微观（地块/周边）两个视角综合分析。"
            "以 SWOT 矩阵或结构化要点形式提出设计注意事项。"
        ),
        required_inputs=["brief_doc", "poi_data"],
        generation_methods=[M.LLM_TEXT, M.CHART],
        layout_hint="sidebar 或 single-column：SWOT 矩阵或分析框",
    ),

    # ══════════════════════════════════════════════════════════
    # 第三章：竞品分析
    # ══════════════════════════════════════════════════════════
    PageSlot(
        slot_id="chapter-3-divider",
        title="竞品分析",
        chapter="竞品分析",
        content_task="章节过渡页。标题：竞品分析，英文翻译：Competitive Analysis。",
        generation_methods=[M.LLM_TEXT],
        layout_hint="full-bleed 章节页",
        is_chapter_divider=True,
    ),

    PageSlot(
        slot_id="competitor-local",
        title="本地竞品分析",
        chapter="竞品分析",
        content_task=(
            "基于场地 POI 数据和场地坐标，分析附近同类或相关产品（竞品项目）。"
            "绘制竞品对比表格（名称、距离、规模、特色、竞争关系）。"
            "给出 2~3 条对本项目的启示。"
        ),
        required_inputs=["poi_data", "site_coordinate"],
        generation_methods=[M.LLM_TEXT, M.CHART],
        layout_hint="sidebar 或 grid：表格为主，配文字分析",
    ),

    PageSlot(
        slot_id="competitor-web",
        title="行业竞品搜索分析",
        chapter="竞品分析",
        content_task=(
            "联网搜索同类或相关产品（国内外标杆案例），分析特点、定位、市场表现。"
            "绘制对比表格（项目名称、地区、规模、特色亮点、对本项目的启示）。"
        ),
        required_inputs=["web_search_competitors"],
        generation_methods=[M.WEB_SEARCH, M.LLM_TEXT, M.CHART],
        layout_hint="sidebar 或 grid：对比表格为主",
    ),

    # ══════════════════════════════════════════════════════════
    # 第四章：参考案例
    # ══════════════════════════════════════════════════════════
    PageSlotGroup(
        group_id="reference-case-pages",
        slot_template=PageSlot(
            slot_id="reference-case",
            title="参考案例",
            chapter="参考案例",
            content_task=(
                "展示参考案例缩略图。分析案例核心特点（设计理念、空间特色、材质策略、建成效果）。"
                "基于设计建议书大纲，提出该案例对待建项目的具体启示（2~4 条）。"
            ),
            required_inputs=["case_thumbnail", "brief_doc", "case_meta"],
            generation_methods=[M.ASSET_REF, M.LLM_TEXT],
            layout_hint="split-h：左案例大图，右分析文字 + 启示条目",
        ),
        repeat_count_min=2,
        repeat_count_max=5,
        repeat_hint="按用户选择的参考案例数量 1:1，最少 2 页，最多 5 页",
    ),

    # ══════════════════════════════════════════════════════════
    # 第五章：项目定位
    # ══════════════════════════════════════════════════════════
    PageSlot(
        slot_id="project-positioning",
        title="项目定位",
        chapter="项目定位",
        content_task=(
            "综合前述所有分析，总结概括项目定位（一句话定位 + 展开说明）。"
            "从社会价值（城市贡献、文化价值、公共性）和经济价值（商业潜力、运营模式）分别说明。"
        ),
        required_inputs=["brief_doc"],
        generation_methods=[M.LLM_TEXT],
        layout_hint="single-column 或 split-v：大字定位标语 + 下方价值说明",
    ),

    # ══════════════════════════════════════════════════════════
    # 第六章：设计策略
    # ══════════════════════════════════════════════════════════
    PageSlot(
        slot_id="chapter-4-divider",
        title="设计策略",
        chapter="设计策略",
        content_task="章节过渡页。标题：设计策略，英文翻译：Design Strategy。",
        generation_methods=[M.LLM_TEXT],
        layout_hint="full-bleed 章节页",
        is_chapter_divider=True,
    ),

    PageSlot(
        slot_id="design-strategies",
        title="设计策略",
        chapter="设计策略",
        content_task=(
            "分析设计建议书大纲中的设计策略内容。"
            "既有概括性的策略标题（每条一句话），又有详细分项说明。"
            "设计策略需与场地分析、文化分析、项目定位形成逻辑呼应（3~5 条策略）。"
        ),
        required_inputs=["brief_doc"],
        generation_methods=[M.LLM_TEXT],
        layout_hint="triptych 或 grid：多策略并排，每条含标题 + 说明",
    ),

    # ══════════════════════════════════════════════════════════
    # 第七章：概念方案（3 方案 × 3 页 = 9 页）
    # ══════════════════════════════════════════════════════════
    PageSlotGroup(
        group_id="concept-proposal-pages",
        slot_template=PageSlot(
            slot_id="concept-intro",
            title="概念方案介绍",
            chapter="概念方案",
            content_task=(
                "生成概念方案介绍页（3 个方案之一）。"
                "包含：方案名称、一句设计理念（≤20字）、一段理念解析（100~150字）、"
                "两张支撑图（资产引用或分析示意图）。"
            ),
            required_inputs=["brief_doc"],
            generation_methods=[M.LLM_TEXT],
            layout_hint="split-h 或 hero-strip：理念大字 + 图",
        ),
        repeat_count_min=3,
        repeat_count_max=3,
        repeat_hint="固定 3 个概念方案",
    ),

    PageSlotGroup(
        group_id="concept-aerial-pages",
        slot_template=PageSlot(
            slot_id="concept-aerial",
            title="概念方案鸟瞰图",
            chapter="概念方案",
            content_task=(
                "调用 Nanobanana 生成该概念方案的精致建筑渲染鸟瞰图。"
                "要求：精致的建筑渲染表现图，展现建筑体量和场地关系。"
                "图片下方添加简短图注（≤30字）。"
            ),
            required_inputs=["brief_doc", "concept_description"],
            generation_methods=[M.NANOBANANA],
            layout_hint="full-bleed 或 split-v：大鸟瞰图 + 底部图注条",
        ),
        repeat_count_min=3,
        repeat_count_max=3,
        repeat_hint="固定 3 个概念方案各一张鸟瞰图",
    ),

    PageSlotGroup(
        group_id="concept-perspective-pages",
        slot_template=PageSlot(
            slot_id="concept-perspective",
            title="概念方案人视图",
            chapter="概念方案",
            content_task=(
                "调用 Nanobanana 生成室外人视图和室内人视图各一张（共两张）。"
                "要求：精致建筑摄影风格，光影真实，构图美感强。"
                "图片旁添加设计亮点注释（2~3 条，每条≤25字）。"
            ),
            required_inputs=["brief_doc", "concept_description"],
            generation_methods=[M.NANOBANANA, M.LLM_TEXT],
            layout_hint="split-h 或 triptych：两张效果图 + 注释文字",
        ),
        repeat_count_min=3,
        repeat_count_max=3,
        repeat_hint="固定 3 个概念方案各两张人视图",
    ),

    # ══════════════════════════════════════════════════════════
    # 第八章：深化比选
    # ══════════════════════════════════════════════════════════
    PageSlot(
        slot_id="material-economic",
        title="材质分析与经济技术指标",
        chapter="深化比选",
        content_task=(
            "生成三个概念方案各自的材质分析（外立面、内装、景观，各方案 2~3 条）。"
            "生成三个概念方案各自的经济技术指标（用地面积、总建筑面积、容积率、"
            "建筑密度、绿化率、建筑高度、停车位）。"
            "以三列对比表格呈现差异，清晰标注各方案优劣。"
        ),
        required_inputs=["brief_doc", "project_brief_data"],
        generation_methods=[M.LLM_TEXT, M.CHART],
        layout_hint="triptych 或 grid：三方案对比表格，上方材质样板",
    ),

    # ══════════════════════════════════════════════════════════
    # 第九章：设计任务书
    # ══════════════════════════════════════════════════════════
    PageSlot(
        slot_id="design-brief-doc",
        title="设计任务书",
        chapter="设计任务书",
        content_task=(
            "基于所有前述内容，拟定正式设计任务书。"
            "包含：项目概述、设计目标、功能需求（分类列表）、"
            "技术要求、时间节点、注意事项。语言正式规范，结构清晰。"
        ),
        required_inputs=["brief_doc", "project_brief_data"],
        generation_methods=[M.LLM_TEXT],
        layout_hint="single-column 或 sidebar：正式文档排版",
    ),

    # ══════════════════════════════════════════════════════════
    # 结尾
    # ══════════════════════════════════════════════════════════
    PageSlot(
        slot_id="closing",
        title="结尾",
        chapter="结尾",
        content_task=(
            "生成结尾章节。包含感谢语、团队/机构标识占位、联系方式占位。"
            "视觉上呼应封面风格，形成整体感。"
        ),
        required_inputs=["project_name", "client_name"],
        generation_methods=[M.LLM_TEXT],
        layout_hint="full-bleed 或 centered：与封面风格呼应",
        is_chapter_divider=True,
    ),
]


def get_total_page_range() -> tuple[int, int]:
    """返回蓝图的页数范围（最少, 最多）。"""
    min_pages = 0
    max_pages = 0
    for item in PPT_BLUEPRINT:
        if isinstance(item, PageSlot):
            min_pages += item.page_count_min
            max_pages += item.page_count_max
        else:  # PageSlotGroup
            min_pages += item.repeat_count_min * item.slot_template.page_count_min
            max_pages += item.repeat_count_max * item.slot_template.page_count_max
    return min_pages, max_pages


def get_slot_by_id(slot_id: str) -> PageSlot | None:
    for item in PPT_BLUEPRINT:
        if isinstance(item, PageSlot) and item.slot_id == slot_id:
            return item
        if isinstance(item, PageSlotGroup) and item.slot_template.slot_id == slot_id:
            return item.slot_template
    return None
