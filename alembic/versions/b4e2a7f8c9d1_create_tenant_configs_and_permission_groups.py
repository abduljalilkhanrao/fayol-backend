"""create tenant_configs and permission_groups tables

Revision ID: b4e2a7f8c9d1
Revises: a3f1b2c4d5e6
Create Date: 2026-03-28 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, UUID


# revision identifiers, used by Alembic.
revision: str = 'b4e2a7f8c9d1'
down_revision: Union[str, Sequence[str], None] = 'a3f1b2c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create tenant_configs and permission_groups tables."""
    op.create_table(
        'tenant_configs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id'), unique=True, nullable=False),
        sa.Column('sla_matrix', JSON, nullable=True),
        sa.Column('effort_bucket_type', sa.String(20), nullable=True),
        sa.Column('effort_bucket_hours', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('effort_rate_per_hour', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('billing_currency', sa.String(10), server_default='USD', nullable=False),
        sa.Column('billing_cycle', sa.String(20), nullable=True),
        sa.Column('milestone_billing_split', JSON, nullable=True),
        sa.Column('escalation_rules', JSON, nullable=True),
        sa.Column('health_score_weights', JSON, nullable=True),
        sa.Column('modules', JSON, nullable=True),
        sa.Column('notification_preferences', JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'permission_groups',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('permissions', JSON, nullable=True),
        sa.Column('is_default', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    """Drop tenant_configs and permission_groups tables."""
    op.drop_table('permission_groups')
    op.drop_table('tenant_configs')
