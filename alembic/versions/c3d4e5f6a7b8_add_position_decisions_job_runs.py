"""Add position_decisions and job_runs tables

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-09-24

Guarded create so it is safe on DBs where init_db()/create_all already made them.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.core.models.schema import PositionDecision, JobRun
    bind = op.get_bind()
    PositionDecision.__table__.create(bind, checkfirst=True)
    JobRun.__table__.create(bind, checkfirst=True)


def downgrade() -> None:
    from app.core.models.schema import PositionDecision, JobRun
    bind = op.get_bind()
    JobRun.__table__.drop(bind, checkfirst=True)
    PositionDecision.__table__.drop(bind, checkfirst=True)
