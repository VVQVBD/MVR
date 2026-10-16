"""часы в строках актов, дата выставления и итог акта

Revision ID: 0004
Revises: 0003
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("billing_act_lines") as batch:
        batch.add_column(sa.Column("hours", sa.Numeric(10, 2), nullable=True))
    with op.batch_alter_table("billing_acts") as batch:
        batch.add_column(sa.Column("issued_at", sa.Date(), nullable=True))
        batch.add_column(sa.Column("stated_total", sa.Numeric(18, 2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("billing_acts") as batch:
        batch.drop_column("stated_total")
        batch.drop_column("issued_at")
    with op.batch_alter_table("billing_act_lines") as batch:
        batch.drop_column("hours")
