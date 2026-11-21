"""Add personalization fields to barbershops

Revision ID: 003_add_personalization
Revises: 002_add_performance_affiliates
Create Date: 2024-05-30

"""
from alembic import op
import sqlalchemy as sa
from migration_safety import require_no_matching_rows


# revision identifiers, used by Alembic.
revision = '003_add_personalization'
down_revision = '002_add_performance_affiliates'
branch_labels = None
depends_on = None


def upgrade():
    # Revisions 002 already create both color columns on barbershops.
    op.add_column('barbershops', sa.Column('style', sa.String(50), nullable=True))
    op.add_column('barbershops', sa.Column('primary_goal', sa.String(50), nullable=True))
    op.add_column('barbershops', sa.Column('team_size', sa.Integer, nullable=True))
    op.add_column('barbershops', sa.Column('avg_service_duration', sa.Integer, nullable=True))
    op.add_column('barbershops', sa.Column('personality', sa.String(50), nullable=True))
    op.add_column('barbershops', sa.Column('onboarding_completed', sa.Boolean, nullable=False, server_default='0'))


def downgrade():
    connection = op.get_bind()
    require_no_matching_rows(
        connection, 'barbershops',
        'style IS NOT NULL OR primary_goal IS NOT NULL OR team_size IS NOT NULL '
        'OR avg_service_duration IS NOT NULL OR personality IS NOT NULL OR onboarding_completed <> 0',
        'barbershop onboarding data',
    )
    # Remove personalization columns
    op.drop_column('barbershops', 'style')
    op.drop_column('barbershops', 'primary_goal')
    op.drop_column('barbershops', 'team_size')
    op.drop_column('barbershops', 'avg_service_duration')
    op.drop_column('barbershops', 'personality')
    op.drop_column('barbershops', 'onboarding_completed')
