"""
案例库初始化脚本 — Phase 5
从 scripts/seed_cases.json 加载案例数据，生成 embedding，写入数据库。
运行方式：python scripts/seed_cases.py [--force]
  --force: 清空现有数据重新导入
"""
import sys
import os
import json
import argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import text
from db.session import SessionLocal
from db.models.reference import ReferenceCase
from tool.reference._embedding import build_embedding_text, get_embedding_sync


SEED_JSON = os.path.join(os.path.dirname(__file__), "seed_cases.json")


def _load_seed_data() -> list[dict]:
    with open(SEED_JSON, encoding="utf-8") as f:
        return json.load(f)


def _build_orm(data: dict) -> ReferenceCase:
    """Build ReferenceCase ORM object from seed dict (without embedding)."""
    return ReferenceCase(
        title=data["title"],
        architect=data.get("architect"),
        location=data.get("location"),
        country=data.get("country", "中国"),
        building_type=data["building_type"],
        style_tags=data.get("style_tags", []),
        feature_tags=data.get("feature_tags", []),
        scale_category=data.get("scale_category", "medium"),
        gfa_sqm=data.get("gfa_sqm"),
        year_completed=data.get("year_completed"),
        images=data.get("images", []),
        summary=data.get("summary", ""),
        source=data.get("source"),
    )


def _set_embedding(db, case_id, embedding: list[float]):
    """Update embedding column via raw SQL (pgvector type)."""
    vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
    db.execute(
        text("UPDATE reference_cases SET embedding = CAST(:vec AS vector) WHERE id = :id"),
        {"vec": vec_str, "id": str(case_id)},
    )


def seed(force: bool = False):
    cases_data = _load_seed_data()
    print(f"从 JSON 加载 {len(cases_data)} 个案例")

    db = SessionLocal()
    try:
        existing_count = db.query(ReferenceCase).count()
        if existing_count > 0 and not force:
            print(f"案例库已有 {existing_count} 条数据，跳过。使用 --force 强制重新导入。")
            return

        if force and existing_count > 0:
            db.query(ReferenceCase).delete()
            db.commit()
            print(f"已清除 {existing_count} 条旧数据")

        inserted = 0
        errors = 0
        for i, case_data in enumerate(cases_data):
            title = case_data.get("title", f"case_{i}")
            try:
                # Generate embedding
                embedding_text = build_embedding_text(case_data)
                embedding = get_embedding_sync(embedding_text)

                # Insert via ORM (without embedding column)
                case_orm = _build_orm(case_data)
                db.add(case_orm)
                db.flush()  # get the generated UUID

                # Set embedding via raw SQL
                _set_embedding(db, case_orm.id, embedding)

                inserted += 1
                provider = os.environ.get("EMBEDDING_PROVIDER", "mock")
                print(f"  [{i+1}/{len(cases_data)}] {title} (embedding={provider})")
            except Exception as e:
                errors += 1
                db.rollback()
                print(f"  [ERROR] [{i+1}] {title}: {e}")

        db.commit()
        print(f"\n导入完成：成功 {inserted}，失败 {errors}，共 {len(cases_data)} 个。")

    except Exception as e:
        db.rollback()
        print(f"导入失败：{e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed reference cases into database")
    parser.add_argument("--force", action="store_true", help="清空现有数据后重新导入")
    args = parser.parse_args()
    seed(force=args.force)
