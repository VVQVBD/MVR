"""дни оказания услуг в акте (неполный месяц)

Revision ID: 0006
Revises: 0005
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("billing_acts") as batch:
        batch.add_column(sa.Column("service_from", sa.Date(), nullable=True))
        batch.add_column(sa.Column("service_to", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("billing_acts") as batch:
        batch.drop_column("service_to")
        batch.drop_column("service_from")
