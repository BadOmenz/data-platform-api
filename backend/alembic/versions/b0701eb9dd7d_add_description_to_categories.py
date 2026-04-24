"""add description to categories

Revision ID: b0701eb9dd7d
Revises: 9ead5437d254
Create Date: 2026-04-17 15:50:53.920020

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b0701eb9dd7d'
down_revision: Union[str, Sequence[str], None] = '9ead5437d254'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() :
    op.add_column(
        "categories",
        sa.Column("description", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    pass
