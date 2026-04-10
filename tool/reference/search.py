"""
Vector search over reference_cases using pgvector.
Falls back to tag-based filtering when vector extension unavailable.
"""
import logging
from typing import Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from schema.reference import ReferenceCase
from schema.common import BuildingType

logger = logging.getLogger(__name__)


class CaseSearchInput(BaseModel):
    building_type: str
    style_tags: list[str] = []
    feature_tags: list[str] = []
    scale_category: Optional[str] = None
    top_k: int = 10
    exclude_ids: list[str] = []
    query_embedding: Optional[list[float]] = None   # None → tag-only search


class CaseSearchOutput(BaseModel):
    cases: list[ReferenceCase]
    search_vector: list[float] = []   # echo back for debugging
    used_vector_search: bool


def _orm_row_to_schema(row) -> ReferenceCase:
    return ReferenceCase(
        id=row.id,
        title=row.title,
        architect=row.architect,
        location=row.location,
        country=row.country,
        building_type=BuildingType(row.building_type),
        style_tags=row.style_tags or [],
        feature_tags=row.feature_tags or [],
        scale_category=row.scale_category,
        gfa_sqm=float(row.gfa_sqm) if row.gfa_sqm else None,
        year_completed=row.year_completed,
        images=row.images or [],
        summary=row.summary,
    )


def search_cases(input: CaseSearchInput, db: Session) -> CaseSearchOutput:
    """
    Search reference cases. Uses pgvector cosine similarity if embedding provided,
    else falls back to building_type + tag filter.
    timeout: 5s
    """
    from db.models.reference import ReferenceCase as ReferenceCaseORM

    exclude_uuids = input.exclude_ids or []

    # Try vector search first
    if input.query_embedding:
        try:
            return _vector_search(input, db, exclude_uuids)
        except Exception as e:
            logger.warning(f"Vector search failed, falling back to tag search: {e}")
            db.rollback()

    return _tag_search(input, db, exclude_uuids)


def _vector_search(
    input: CaseSearchInput,
    db: Session,
    exclude_ids: list[str],
) -> CaseSearchOutput:
    """pgvector cosine similarity search."""
    # Format embedding as PostgreSQL vector literal
    vec_str = "[" + ",".join(str(v) for v in input.query_embedding) + "]"

    exclude_clause = ""
    params: dict = {
        "building_type": input.building_type,
        "top_k": input.top_k,
        "vec": vec_str,
    }

    if exclude_ids:
        exclude_clause = "AND id != ALL(:exclude_ids)"
        params["exclude_ids"] = exclude_ids

    sql = text(f"""
        SELECT id, title, architect, location, country, building_type,
               style_tags, feature_tags, scale_category, gfa_sqm,
               year_completed, images, summary,
               1 - (embedding <=> CAST(:vec AS vector)) AS similarity
        FROM reference_cases
        WHERE is_active = true
          AND building_type = :building_type
          {exclude_clause}
        ORDER BY embedding <=> CAST(:vec AS vector)
        LIMIT :top_k
    """)

    rows = db.execute(sql, params).fetchall()
    cases = [_orm_row_to_schema(r) for r in rows]

    return CaseSearchOutput(
        cases=cases,
        search_vector=input.query_embedding[:8],   # first 8 dims for debug
        used_vector_search=True,
    )


def _tag_search(
    input: CaseSearchInput,
    db: Session,
    exclude_ids: list[str],
) -> CaseSearchOutput:
    """Fallback: filter by building_type and optionally style/feature tags."""
    from db.models.reference import ReferenceCase as ReferenceCaseORM

    query = db.query(ReferenceCaseORM).filter(
        ReferenceCaseORM.is_active == True,
        ReferenceCaseORM.building_type == input.building_type,
    )

    if exclude_ids:
        query = query.filter(~ReferenceCaseORM.id.in_(exclude_ids))

    if input.scale_category:
        query = query.filter(ReferenceCaseORM.scale_category == input.scale_category)

    # Style tag filter (PostgreSQL jsonb @> operator)
    if input.style_tags:
        for tag in input.style_tags[:2]:   # limit to 2 to avoid over-filtering
            query = query.filter(
                ReferenceCaseORM.style_tags.contains([tag])
            )

    orm_cases = query.limit(input.top_k).all()
    cases = [
        ReferenceCase(
            id=c.id,
            title=c.title,
            architect=c.architect,
            location=c.location,
            country=c.country,
            building_type=BuildingType(c.building_type),
            style_tags=c.style_tags or [],
            feature_tags=c.feature_tags or [],
            scale_category=c.scale_category,
            gfa_sqm=float(c.gfa_sqm) if c.gfa_sqm else None,
            year_completed=c.year_completed,
            images=c.images or [],
            summary=c.summary,
        )
        for c in orm_cases
    ]

    return CaseSearchOutput(cases=cases, used_vector_search=False)
