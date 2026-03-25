"""add lockout fields to users

Revision ID: 704d9ceeba92
Revises: 57684e516e15
Create Date: 2026-03-25 17:05:15.572892

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '704d9ceeba92'
down_revision: Union[str, Sequence[str], None] = '57684e516e15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('failed_login_attempts', sa.Integer(), server_default='0', nullable=False))
    op.add_column('users', sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'locked_until')
    op.drop_column('users', 'failed_login_attempts')
