"""add deleted_at to tenants

Revision ID: e7781e7a4b4e
Revises: dfae9f8a83df
Create Date: 2026-03-26 06:19:44.821611

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7781e7a4b4e'
down_revision: Union[str, Sequence[str], None] = 'dfae9f8a83df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('tenants', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tenants', 'deleted_at')
