"""
端到端测试脚本 — 使用真实 LLM + 真实数据库

测试范围：
  ProjectBrief → BriefDoc → Outline → Compose(前5页) → Render HTML+PNG

运行方式：
  .venv/Scripts/python.exe scripts/e2e_test.py

输出：
  tmp/e2e_output/
    brief_doc.json         — 设计建议书大纲
    outline.json           — PPT 大纲（slot assignments）
    slides/slide_01.html   — 渲染 HTML
    slides/slide_01.png    — 截图
    ...
    report.txt             — 测试报告
"""
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from uuid import uuid4

# ── 路径修正 ─────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ── 日志 ─────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("e2e")

# ── 输出目录 ─────────────────────────────────────────────────────────────────
OUT = ROOT / "tmp" / "e2e_output"
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "slides").mkdir(exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────

def section(title: str):
    log.info("=" * 60)
    log.info(f"  {title}")
    log.info("=" * 60)


async def main():
    report_lines = []

    def record(label: str, value, ok: bool = True):
        icon = "✅" if ok else "❌"
        msg = f"{icon}  {label}: {value}"
        log.info(msg)
        report_lines.append(msg)

    total_start = time.time()

    # ── 1. DB Session ─────────────────────────────────────────────────────────
    section("1. 连接数据库")
    from db.session import SessionLocal
    db = SessionLocal()
    record("DB 连接", "ok")

    try:
        # ── 2. 创建测试项目 ───────────────────────────────────────────────────
        section("2. 创建项目 + 设计任务书")
        from db.models.project import Project, ProjectBrief
        from db.models.asset import Asset

        project = Project(name="苏州工业园区文化艺术中心 E2E Test", status="brief_ready")
        db.add(project)
        db.flush()
        record("Project created", str(project.id))

        brief = ProjectBrief(
            project_id=project.id,
            version=1,
            status="confirmed",
            building_type="cultural_center",
            client_name="苏州工业园区管委会",
            city="苏州",
            province="江苏",
            site_address="苏州工业园区星湖街88号",
            gross_floor_area=48000,
            site_area=18000,
            far=2.67,
            style_preferences=["现代主义", "在地文化", "绿色低碳"],
            special_requirements="需融入苏州园林元素，同时体现当代建筑语言；地下两层停车，地上最高六层。",
        )
        db.add(brief)
        db.flush()
        record("ProjectBrief created", f"building_type={brief.building_type}, GFA={brief.gross_floor_area}㎡")

        # ── 3. 植入种子资产（模拟已采集数据）────────────────────────────────
        section("3. 植入种子资产（模拟政策/场地/POI数据）")
        seed_assets = [
            Asset(
                project_id=project.id, version=1, status="ready",
                asset_type="policy", subtype="national",
                title="《关于推进文化和旅游深度融合发展的意见》（2023）",
                data_json={
                    "policy_name": "关于推进文化和旅游深度融合发展的意见",
                    "publish_date": "2023-11-01",
                    "key_points": [
                        "支持公共文化设施免费开放，推动文化场馆运营机制改革",
                        "鼓励建设复合型文化综合体，集展览、演艺、教育于一体",
                        "加大文化基础设施用地保障力度",
                    ],
                    "relevance": "直接支持本项目的文化综合体定位",
                },
            ),
            Asset(
                project_id=project.id, version=1, status="ready",
                asset_type="policy", subtype="local",
                title="《苏州工业园区第五轮总体规划（2021-2035）》",
                data_json={
                    "policy_name": "苏州工业园区第五轮总体规划",
                    "publish_date": "2021-06-15",
                    "key_points": [
                        "星湖街文化轴线规划：构建文化艺术集聚带",
                        "本地块规划用途：文化娱乐用地（A2），容积率≤3.0",
                        "要求建筑退让红线不低于10m，绿化率≥35%",
                    ],
                    "relevance": "明确了本项目的用地性质和开发指标边界",
                },
            ),
            Asset(
                project_id=project.id, version=1, status="ready",
                asset_type="site", subtype="poi_analysis",
                title="场地周边500m POI分析",
                data_json={
                    "poi_categories": {
                        "文化教育": 12,
                        "餐饮": 28,
                        "零售商业": 19,
                        "交通": 6,
                        "办公企业": 45,
                        "居住社区": 8,
                    },
                    "key_nodes": [
                        {"name": "苏州科技文化艺术中心（苏艺）", "distance_m": 380, "type": "竞品"},
                        {"name": "金鸡湖地铁站（1号线）", "distance_m": 420, "type": "交通"},
                        {"name": "苏州工业园区管委会", "distance_m": 650, "type": "政府"},
                    ],
                    "observations": "周边以科技企业为主，文化配套相对欠缺，消费人群以白领为主",
                },
            ),
            Asset(
                project_id=project.id, version=1, status="ready",
                asset_type="economic", subtype="city_gdp",
                title="苏州GDP及增速（2019-2023）",
                data_json={
                    "year_data": [
                        {"year": 2019, "gdp_billion_cny": 1927, "growth_rate": 0.062},
                        {"year": 2020, "gdp_billion_cny": 2015, "growth_rate": 0.038},
                        {"year": 2021, "gdp_billion_cny": 2272, "growth_rate": 0.087},
                        {"year": 2022, "gdp_billion_cny": 2394, "growth_rate": 0.020},
                        {"year": 2023, "gdp_billion_cny": 2469, "growth_rate": 0.031},
                    ],
                    "conclusion": "苏州GDP全国前五，经济韧性强，为高品质文化消费提供支撑",
                },
            ),
            Asset(
                project_id=project.id, version=1, status="ready",
                asset_type="reference", subtype="selected",
                title="苏州博物馆西馆（贝聿铭式现代传统融合）",
                data_json={
                    "case_name": "苏州博物馆西馆",
                    "architect": "贝聿铭建筑师事务所",
                    "location": "苏州",
                    "year": 2006,
                    "area_sqm": 19000,
                    "style_tags": ["现代主义", "在地文化", "白墙黑瓦"],
                    "highlights": "将苏州传统园林元素抽象化，以现代材料和空间手法重新诠释",
                    "inspiration": "在地文化融合现代建筑语言的典范，可借鉴其屋顶几何形式与水庭院处理",
                },
            ),
            Asset(
                project_id=project.id, version=1, status="ready",
                asset_type="reference", subtype="selected",
                title="上海浦东美术馆（当代艺术地标）",
                data_json={
                    "case_name": "上海浦东美术馆",
                    "architect": "Ateliers Jean Nouvel",
                    "location": "上海",
                    "year": 2021,
                    "area_sqm": 40000,
                    "style_tags": ["当代艺术", "玻璃幕墙", "滨水界面"],
                    "highlights": "通过连续的折叠玻璃立面创造独特的光影体验，与滨江景观形成对话",
                    "inspiration": "大型公共文化建筑的开放性设计策略，首层连续商业界面的处理方式",
                },
            ),
        ]
        for a in seed_assets:
            db.add(a)
        db.flush()
        record("种子资产", f"植入 {len(seed_assets)} 条")

        # ── 4. Brief Doc Agent ────────────────────────────────────────────────
        section("4. Brief Doc Agent（设计建议书大纲）")
        t0 = time.time()
        from agent.brief_doc import generate_brief_doc
        brief_doc_orm = await generate_brief_doc(project.id, db)
        t_brief = time.time() - t0

        brief_doc_data = brief_doc_orm.outline_json
        record("BriefDoc 生成耗时", f"{t_brief:.1f}s")
        record("定位主张", brief_doc_data.get("positioning_statement", "")[:80])
        record("叙事脉络", brief_doc_data.get("narrative_arc", "")[:80])
        record("设计原则数", len(brief_doc_data.get("design_principles", [])))

        (OUT / "brief_doc.json").write_text(
            json.dumps(brief_doc_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # ── 5. Outline Agent v2 ───────────────────────────────────────────────
        section("5. Outline Agent v2（蓝图驱动大纲）")
        t0 = time.time()
        from agent.outline import generate_outline
        outline_orm = await generate_outline(project.id, db)
        t_outline = time.time() - t0

        outline_spec = outline_orm.spec_json
        slides_in_outline = outline_spec.get("slides", [])
        record("Outline 生成耗时", f"{t_outline:.1f}s")
        record("总页数", outline_orm.total_pages)
        record("Deck Title", outline_orm.deck_title)
        record("章节数", len(outline_spec.get("sections", [])))

        # 打印前5页摘要
        for s in slides_in_outline[:5]:
            log.info(f"    页{s['slide_no']:02d}  [{s['section']}]  {s['title']}")

        (OUT / "outline.json").write_text(
            json.dumps(outline_spec, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # ── 6. Composer Agent（前5页）────────────────────────────────────────
        section("6. Composer Agent（组合前5页 LayoutSpec）")
        t0 = time.time()
        from agent.composer import compose_all_slides

        # 临时限制：只处理前5页，避免耗时过长
        # 通过临时 patch outline 只保留前5条
        original_slides = outline_spec["slides"]
        outline_spec["slides"] = original_slides[:5]
        outline_spec["total_pages"] = 5
        outline_orm.total_pages = 5
        outline_orm.spec_json = outline_spec
        db.flush()

        slides_orm = await compose_all_slides(project.id, db)
        t_compose = time.time() - t0

        record("Composer 耗时", f"{t_compose:.1f}s")
        record("生成 Slide 数", len(slides_orm))

        # 恢复 outline（不影响 DB 内容，只是 log）
        outline_spec["slides"] = original_slides

        # ── 7. Render HTML + Screenshot ───────────────────────────────────────
        section("7. Render HTML + Playwright 截图")
        from render.engine import render_slide_html
        from render.exporter import screenshot_slide
        from agent.visual_theme import get_latest_theme
        from tests.helpers.theme_factory import make_default_theme
        from schema.visual_theme import LayoutSpec

        # 尝试读 DB 中的 VisualTheme，没有则用默认
        theme = get_latest_theme(project.id, db) or make_default_theme(project.id)
        record("Visual Theme", f"primary={theme.colors.primary}, font={theme.typography.font_heading}")

        deck_meta = {
            "deck_title": outline_orm.deck_title,
            "client_name": brief.client_name,
            "total_slides": outline_orm.total_pages,
        }

        from db.models.asset import Asset as AssetModel
        assets_orm_list = db.query(AssetModel).filter_by(project_id=project.id).all()
        assets_dict = {
            str(a.id): {"image_url": a.image_url, "data_json": a.data_json}
            for a in assets_orm_list
        }

        render_times = []
        for slide in slides_orm:
            t0 = time.time()
            try:
                spec = LayoutSpec.model_validate(slide.spec_json)
                html = render_slide_html(spec, theme=theme, assets=assets_dict, deck_meta=deck_meta)

                # 保存 HTML
                html_path = OUT / "slides" / f"slide_{slide.slide_no:02d}.html"
                html_path.write_text(html, encoding="utf-8")

                # 截图
                png_bytes = await screenshot_slide(html)
                png_path = OUT / "slides" / f"slide_{slide.slide_no:02d}.png"
                png_path.write_bytes(png_bytes)

                t_render = time.time() - t0
                render_times.append(t_render)
                record(
                    f"Slide {slide.slide_no:02d} [{slide.title or ''}]",
                    f"HTML={len(html)}B  PNG={len(png_bytes)}B  {t_render:.1f}s"
                )
            except Exception as e:
                record(f"Slide {slide.slide_no:02d} 渲染失败", str(e)[:100], ok=False)

        if render_times:
            record("平均渲染耗时", f"{sum(render_times)/len(render_times):.1f}s/页")

        # ── 8. Critic Review ─────────────────────────────────────────────────
        section("8. Critic Review（rule + semantic）")
        from agent.critic import review_slide
        from schema.visual_theme import LayoutSpec

        brief_dict = {
            "building_type": brief.building_type,
            "client_name": brief.client_name,
            "style_preferences": brief.style_preferences or [],
            "gross_floor_area": float(brief.gross_floor_area) if brief.gross_floor_area else None,
            "far": float(brief.far) if brief.far else None,
        }

        review_results = []
        for slide in slides_orm:
            t0 = time.time()
            try:
                spec = LayoutSpec.model_validate(slide.spec_json)
                repaired_spec, report = await review_slide(
                    spec=spec,
                    brief=brief_dict,
                    layers=["rule", "semantic"],
                )
                t_rev = time.time() - t0
                issues_summary = ", ".join(
                    f"{i.rule_code}({i.severity.value})" for i in report.issues
                ) or "无问题"
                record(
                    f"Slide {slide.slide_no:02d} review [{report.final_decision.value}]",
                    f"{issues_summary}  {t_rev:.1f}s",
                    ok=report.final_decision.value != "escalate_human",
                )
                review_results.append(report)
                # 将修复后的 spec 写回
                slide.spec_json = repaired_spec.model_dump(mode="json")
            except Exception as e:
                record(f"Slide {slide.slide_no:02d} review 失败", str(e)[:120], ok=False)

        db.flush()
        passed = sum(1 for r in review_results if r.final_decision.value in ("pass", "repair_required"))
        record("Review 通过页数", f"{passed}/{len(slides_orm)}")

        # ── 9. 汇总 ──────────────────────────────────────────────────────────
        section("9. 测试汇总")
        total = time.time() - total_start
        record("总耗时", f"{total:.1f}s")
        record("输出目录", str(OUT))

        # 写报告
        report_path = OUT / "report.txt"
        report_path.write_text("\n".join(report_lines), encoding="utf-8")
        log.info(f"\n报告已写入: {report_path}")

        # ── 提交或回滚 ────────────────────────────────────────────────────────
        # 使用 commit 保留数据以便检查，也可改为 rollback()
        db.commit()
        log.info("✅ 数据已提交到 DB（project_id=%s）", project.id)
        log.info("   使用以下命令清理测试数据：")
        log.info(f"   DELETE FROM projects WHERE id = '{project.id}';")

    except Exception as e:
        log.exception(f"❌ E2E test failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
