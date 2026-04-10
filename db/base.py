from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import all models here so Alembic can detect them
from db.models import project, site, reference, asset, outline, slide, review, job, visual_theme, brief_doc, material_package, material_item, slide_material_binding  # noqa: F401, E402
