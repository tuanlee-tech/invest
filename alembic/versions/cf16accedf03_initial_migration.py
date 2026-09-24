"""Initial migration

Revision ID: cf16accedf03
Revises:
Create Date: 2026-09-22 15:55:30.562760

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cf16accedf03'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the full schema from Base.metadata on an empty database."""
    from app.core.models.schema import Base

    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    """Drop all application tables."""
    from app.core.models.schema import Base

    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
