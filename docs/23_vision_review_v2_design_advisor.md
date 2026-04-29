# 23. Vision Review v2 — 设计改善建议系统

## 1. 背景与动机

当前 Vision Review（Layer 3）只检测 4 类**硬伤**（V001 杂乱、V002 模糊、V004 文字可读性、V007 空白浪费），全部是 `auto_fixable: false` 的被动报告。

问题：
- Composer v3 的 HTML 直出模式给了 LLM 完全的设计自由，但缺乏质量反馈闭环
- 发现 V007 空白浪费后无法给出"应该怎么改"的具体建议
- 配色对比度、视觉层次、排版节奏等专业维度完全没有覆盖
- 没有"设计评分"，无法量化页面质量

**目标**：在现有 3 层审查基础上，扩展 Vision Review 为双模式：
- **Mode A — 缺陷检测**（现有，保持不变）
- **Mode B — 设计顾问**（新增，给出评分 + 改善建议 + 可操作的 CSS/HTML 修改指令）

---

## 2. 架构设计

### 2.1 调用时机

```
compose_slide() → render_slide_html_direct() → screenshot_slide()
                                                      │
                                    ┌─────────────────┤
                                    ▼                  ▼
                           Mode A: 缺陷检测     Mode B: 设计顾问
                           (现有, 快速)         (新增, 深度)
                                    │                  │
                                    ▼                  ▼
                              ReviewReport      DesignAdvice
                              (issues[])        (score + suggestions[])
                                    │                  │
                                    └──────┬───────────┘
                                           ▼
                                  决策: PASS / REPAIR / REDESIGN
```

### 2.2 Mode B 触发条件

不是每页都需要设计顾问，建议按策略触发：

| 策略 | 说明 |
|---|---|
| `always` | 所有页面都跑（成本最高，适合最终出品） |
| `on_defect` | Mode A 发现问题时才跑 Mode B（推荐默认） |
| `sample` | 每章抽 1 页 + 封面 + 末页（快速全局感知） |
| `cover_only` | 只对封面/章节页跑（这些页面设计权重最高） |

### 2.3 自动重写闭环状态

Phase 1 只输出建议，**不自动修改 HTML**。原因：
- 设计改善涉及大幅重写 HTML，单次 LLM 调用无法可靠完成
- 自动修改可能引入新问题，需要 re-render + re-review 循环
- Phase 1 先验证建议质量，Phase 2 再考虑闭环

**2026-04-25 更新（ADR-006）**：Bold Visual Design 升级将把 Design Advisor 从“建议报告”提升为返工 gate。低分或关键建议码会触发 `recompose_slide_html()`，再进入 re-render + re-review。structured 模式仍以 rule/semantic 修复为主,HTML 模式以 vision/design review 反馈为主。

---

## 3. 设计顾问评估维度

### 3.1 评分体系（5 维度 × 10 分）

| 维度 | 代号 | 满分 | 评估标准 |
|---|---|---|---|
| **配色与对比度** | `color` | 10 | 主色/辅色/强调色使用是否和谐；文字与背景对比度是否达标（WCAG AA ≥4.5:1）；色彩层次是否清晰 |
| **排版与层次** | `typography` | 10 | 字阶是否分明（标题 vs 正文 vs 注释）；行距/字距是否舒适；阅读顺序是否自然（F/Z 型） |
| **布局与平衡** | `layout` | 10 | 元素分布是否均衡（非对称也可以，但要有意为之）；网格感是否明确；留白是否有节奏 |
| **视觉焦点** | `focal_point` | 10 | 是否有明确的视觉锚点；信息优先级是否通过大小/颜色/位置体现；第一眼看向哪里 |
| **整体完成度** | `polish` | 10 | 装饰是否精致而非敷衍；元素边缘是否整洁；整体是否像"成品"而非"草稿" |

**总分 = 5 项均分**，分级：

| 总分范围 | 等级 | 含义 |
|---|---|---|
| 8.0 – 10.0 | A | 出品级，无需修改 |
| 6.0 – 7.9 | B | 合格，有改善空间 |
| 4.0 – 5.9 | C | 需要改善，建议修改后重新渲染 |
| 0.0 – 3.9 | D | 设计失败，建议重新生成 |

### 3.2 具体改善建议类型

| 建议代号 | 类别 | 典型建议示例 |
|---|---|---|
| `D001` | 对比度不足 | "标题文字 `var(--color-text-secondary)` 在 `var(--color-surface)` 背景上对比度不足，建议改用 `var(--color-text-primary)`" |
| `D002` | 配色冲突 | "强调色与主色饱和度过近，视觉上无法区分，建议降低强调色使用面积" |
| `D003` | 字阶混乱 | "正文使用了 `var(--text-h2)` 字号，与标题字号差异太小，建议降为 `var(--text-body)`" |
| `D004` | 行距过紧 | "多行文本行距 <1.3，密集感强，建议 `line-height: 1.6`" |
| `D005` | 布局偏重 | "内容集中在左上 1/4 区域，右下大片空白，建议用 CSS Grid 重新分布" |
| `D006` | 对齐偏移 | "标题与下方内容块左边距不一致，建议统一到 `var(--safe-margin)`" |
| `D007` | 缺少焦点 | "页面所有元素大小/颜色接近，缺乏视觉锚点，建议放大标题或增加强调色色块" |
| `D008` | 装饰过度 | "SVG 装饰元素 opacity 过高，喧宾夺主，建议降至 0.08~0.12" |
| `D009` | 装饰缺失 | "纯文字页面过于单调，建议添加几何线条或色块装饰增加层次" |
| `D010` | 图文比例 | "图片占比 >80%，文字信息被压缩，建议调整为 60:40 图文比" |
| `D011` | 留白节奏 | "区块之间留白不一致（上方 20px，下方 80px），建议统一使用 `var(--section-gap)`" |
| `D012` | 封面冲击力 | "封面视觉冲击力不足，建议使用全屏渐变背景或大面积图片" |

---

## 4. 数据模型

### 4.1 新增 Schema

```python
# schema/review.py 新增

class DesignDimension(BaseSchema):
    """单维度评分"""
    dimension: str          # "color" | "typography" | "layout" | "focal_point" | "polish"
    score: float            # 0.0 ~ 10.0
    comment: str            # 一句话评价

class DesignSuggestion(BaseSchema):
    """单条改善建议"""
    code: str               # "D001" ~ "D012"
    category: str           # "color" | "typography" | "layout" | "focal_point" | "polish"
    severity: str           # "critical" | "recommended" | "nice-to-have"
    message: str            # 人类可读描述
    css_hint: str = ""      # 可选：建议的 CSS 修改（如 "color: var(--color-text-primary)"）
    target_selector: str = ""  # 可选：目标 CSS 选择器（如 ".slide-root h1"）

class DesignAdvice(BaseSchema):
    """设计顾问完整输出"""
    slide_no: int
    dimensions: list[DesignDimension]   # 5 项评分
    overall_score: float                # 均分
    grade: str                          # "A" | "B" | "C" | "D"
    suggestions: list[DesignSuggestion] # 改善建议列表
    one_liner: str                      # 一句话总评（如"排版优秀但配色层次不足"）
```

### 4.2 ReviewReport 扩展

```python
# ReviewReport 新增可选字段
class ReviewReport(BaseSchema):
    # ... 现有字段 ...
    design_advice: Optional[DesignAdvice] = None   # Mode B 结果
```

### 4.3 数据库存储

`design_advice` 序列化为 JSON 存入 `reviews.issues_json` 的同级字段 `reviews.design_advice_json`（新增 nullable JSONB 列）。

```python
# db/models/review.py
design_advice_json = Column(JSONB, nullable=True)
```

---

## 5. Prompt 设计

### 5.1 设计顾问 System Prompt

```markdown
# Vision Review — Design Advisor

你是一位资深的演示文稿视觉设计教授。你将看到一张 1920×1080 的幻灯片截图，
需要从专业角度评估其视觉设计质量并给出改善建议。

## 评分维度（每项 0~10 分）

1. **color** — 配色与对比度
   - 文字/背景对比度是否足够（正文 ≥4.5:1，大标题 ≥3:1）
   - 主色/辅色/强调色的使用比例是否合理（推荐 60:30:10）
   - 色彩是否在整页中形成清晰的视觉层次

2. **typography** — 排版与文字层次
   - 标题、正文、注释是否有明显的字号差异（建议标题 ≥2x 正文）
   - 行距是否舒适（正文推荐 1.5~1.8）
   - 文字量是否适中（单页不宜超过 200 字）

3. **layout** — 布局与空间平衡
   - 元素是否形成清晰的网格或构图（三分法、黄金分割等）
   - 留白是否有节奏（不是均匀空白，而是有大小对比的呼吸感）
   - 内容区域是否集中在安全区内（边缘 60px 内不宜放核心内容）

4. **focal_point** — 视觉焦点
   - 是否有一个明确的"第一眼"焦点
   - 信息层级是否通过大小/颜色/位置清晰传达
   - 阅读路径是否自然（从焦点到次要信息有引导）

5. **polish** — 整体完成度
   - 装饰元素（线条/色块/SVG）是否精致
   - 元素间距是否一致
   - 整体是否有"专业成品"的感觉（vs "模板初稿"）

## 建议格式

每条建议需包含：
- `code`：D001~D012 中最匹配的代号
- `category`：对应维度
- `severity`："critical"（必须改）| "recommended"（建议改）| "nice-to-have"（锦上添花）
- `message`：具体描述问题和改法
- `css_hint`：如果能给出 CSS 修改建议就给（如 `font-size: var(--text-h1)`），给不出就留空
- `target_selector`：如果能识别到目标元素的 CSS 选择器就给，给不出就留空

## 特殊页面基准

- **封面页**：视觉冲击力权重最高，polish 和 focal_point 要严格
- **章节过渡页**：极简风预期，layout 评分不宜因极简而扣分
- **数据密集页**：typography 层次尤为重要，允许更紧凑的 layout
- **图片主导页**：focal_point 几乎由图片决定，重点看图文配合

## 输出

返回 JSON，不要输出 JSON 以外的内容：

{
  "dimensions": [
    {"dimension": "color", "score": 7.5, "comment": "..."},
    {"dimension": "typography", "score": 8.0, "comment": "..."},
    {"dimension": "layout", "score": 6.0, "comment": "..."},
    {"dimension": "focal_point", "score": 7.0, "comment": "..."},
    {"dimension": "polish", "score": 5.5, "comment": "..."}
  ],
  "suggestions": [
    {
      "code": "D005",
      "category": "layout",
      "severity": "recommended",
      "message": "内容集中在上半部分，下方 40% 为空白，建议将元素向下扩展或添加装饰",
      "css_hint": "padding-bottom: 0; display: grid; grid-template-rows: 1fr 1fr;",
      "target_selector": ".slide-root > .content-area"
    }
  ],
  "one_liner": "排版清晰但下半页空旷，配色层次可加强"
}
```

### 5.2 User Message 模板

```
Review slide {slide_no} ({page_type}) for design quality.

Context:
- Page type: {page_type} (cover / chapter_divider / content / data / case)
- Content summary: {content_summary}
- Theme colors: primary={primary}, secondary={secondary}, accent={accent}
```

提供 `page_type` 和主题色参数，让 LLM 能结合上下文评估（例如章节页不因极简扣分）。

---

## 6. 实现计划

### Phase 1：核心实现（本次）

| 步骤 | 文件 | 改动 |
|---|---|---|
| 1 | `schema/review.py` | 新增 `DesignDimension`, `DesignSuggestion`, `DesignAdvice`；`ReviewReport` 加 `design_advice` |
| 2 | `prompts/vision_design_advisor.md` | 新建 System Prompt 文件 |
| 3 | `agent/critic.py` | 新增 `_design_review()` 函数；`review_slide()` 加 `design_advisor: bool` 参数 |
| 4 | `config/llm.py` | `call_llm_multimodal()` 的 `max_tokens` 参数化（设计顾问需要更大输出） |
| 5 | `scripts/material_package_e2e.py` | `--design-review` 开关；输出 `design_scores.json` 汇总 |
| 6 | Smoke test | 用现有截图验证评分 + 建议输出 |

### Phase 2：闭环迭代（ADR-006 计划推进）

| 步骤 | 说明 |
|---|---|
| 2a | 根据 `DesignAdvice.suggestions` 生成修改指令，回传 Composer 重写 HTML |
| 2b | Re-render + Re-review 循环（最多 2 轮） |
| 2c | 评分低于阈值（如 C 级）自动触发 redesign |

建议 gate:

| 条件 | 动作 |
|---|---|
| `overall_score < 7.0` | recompose HTML |
| `focal_point < 6.5` | 强化视觉焦点和阅读路径 |
| `polish < 6.5` | 增加装饰层次和完成度 |
| `D009` | 增强视觉语言,避免纯文字草稿感 |
| `D012` 且页面为封面/章节/概念方案 | 重做重点页冲击力 |

### Phase 3：全局一致性审查（未来）

| 步骤 | 说明 |
|---|---|
| 3a | 收集所有页面的 `DesignAdvice`，做全局一致性评估 |
| 3b | 检查跨页配色偏移、字号不统一、装饰风格不一致 |
| 3c | 输出 deck-level 设计评分报告 |

---

## 7. `_design_review()` 函数签名

```python
async def _design_review(
    screenshot_url: str,
    slide_no: int,
    page_type: str,           # "cover" | "chapter_divider" | "content" | "data" | "case"
    content_summary: str,     # 来自 compose 输出
    theme_colors: dict,       # {"primary": "#xxx", "secondary": "#xxx", "accent": "#xxx"}
) -> DesignAdvice:
```

### 调用方修改

```python
# agent/critic.py :: review_slide()

async def review_slide(
    spec: LayoutSpec,
    brief: dict,
    layers: list[str] | None = None,
    screenshot_url: Optional[str] = None,
    max_repairs: int = 3,
    design_advisor: bool = False,      # 新增
    page_type: str = "content",        # 新增
    content_summary: str = "",         # 新增
    theme_colors: dict | None = None,  # 新增
) -> tuple[LayoutSpec, ReviewReport]:
    ...
    
    design_advice = None
    if design_advisor and screenshot_url:
        try:
            design_advice = await _design_review(
                screenshot_url, spec.slide_no, page_type,
                content_summary, theme_colors or {}
            )
        except Exception as exc:
            logger.warning("Design review failed for slide %s: %s", spec.slide_no, exc)

    report = ReviewReport(
        ...
        design_advice=design_advice,
    )
    return current_spec, report
```

---

## 8. E2E 脚本集成

```bash
# 开启设计顾问模式
python scripts/material_package_e2e.py test_material/project1 \
    --real-llm --composer-mode html --design-review

# 输出额外文件
test_output/xxx/run_xxx/
├── design_scores.json        # 所有页面评分汇总
├── design_scores_summary.txt # 人类可读报告
└── slides/
    └── slide_01_advice.json  # 单页详细建议
```

### design_scores_summary.txt 示例

```
=== Design Review Summary ===
Total slides: 41
Average score: 7.2 / 10  (Grade B)

Score distribution:
  A (8.0+):  12 slides (29%)
  B (6.0~7.9): 22 slides (54%)
  C (4.0~5.9):  6 slides (15%)
  D (<4.0):   1 slide  (2%)

Top issues:
  D005 LAYOUT_IMBALANCE:  18 occurrences
  D007 MISSING_FOCAL:     12 occurrences
  D001 LOW_CONTRAST:       8 occurrences

Weakest slides:
  Slide 08 (交通与基础设施): 3.5 — D grade
  Slide 15 (景观设计概念): 4.2 — C grade
  Slide 31 (造价估算): 4.8 — C grade

Strongest slides:
  Slide 03 (章节过渡-背景研究): 9.2 — A grade
  Slide 01 (封面): 8.8 — A grade
  Slide 13 (章节过渡-场地分析): 8.5 — A grade
```

---

## 9. 成本估算

| 模式 | 每页 token 消耗 | 41 页总计 | 预估费用（OpenRouter） |
|---|---|---|---|
| Mode A 缺陷检测 | ~500 input + ~200 output | ~29K tokens | ~$0.03 |
| Mode B 设计顾问 | ~800 input + ~800 output | ~66K tokens | ~$0.08 |
| A + B 同时 | ~1300 input + ~1000 output | ~95K tokens | ~$0.11 |

成本增量可控。主要瓶颈是**延迟**（每页增加一次 multimodal 调用，约 3~5 秒）。

可通过 `asyncio.gather` 并发 5~8 页来控制总耗时。

---

## 10. 与 Composer v3 的配合

设计顾问的输出格式刻意与 Composer v3 的 CSS 变量体系对齐：

- `css_hint` 使用 `var(--color-*)` / `var(--text-*)` / `var(--safe-margin)` 等 Composer 已知的变量
- `target_selector` 基于 `.slide-root` 内部结构
- `message` 引用 Composer 的设计规范用语

这为 Phase 2 的自动修改奠定基础：Composer 可以直接理解设计顾问的建议并应用到 HTML 中。ADR-006 后,这些建议会进入 `recompose_slide_html()` 的输入,作为低分页面自动返工的主要依据。
