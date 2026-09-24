"""Add reporting_period and effective_date to fund_holding_snapshots

Revision ID: a1b2c3d4e5f6
Revises: cf16accedf03
Create Date: 2026-09-24

Nullable columns; guarded so `alembic upgrade head` works both on a clean DB
(initial migration's create_all already includes them) and on existing DBs.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'cf16accedf03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
    return column in columns


def upgrade() -> None:
    if not _has_column("fund_holding_snapshots", "reporting_period"):
        op.add_column("fund_holding_snapshots",
                      sa.Column("reporting_period", sa.String(32), nullable=True))
    if not _has_column("fund_holding_snapshots", "effective_date"):
        op.add_column("fund_holding_snapshots",
                      sa.Column("effective_date", sa.Date(), nullable=True))


def downgrade() -> None:
    if _has_column("fund_holding_snapshots", "effective_date"):
        op.drop_column("fund_holding_snapshots", "effective_date")
    if _has_column("fund_holding_snapshots", "reporting_period"):
        op.drop_column("fund_holding_snapshots", "reporting_period")
