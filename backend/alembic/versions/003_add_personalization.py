"""Add personalization fields to barbershops

Revision ID: 003_add_personalization
Revises: 002_add_performance_affiliates
Create Date: 2024-05-30

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '003_add_personalization'
down_revision = '002_add_performance_affiliates'
branch_labels = None
depends_on = None


def upgrade():
    # Add personalization columns to barbershops table
    op.add_column('barbershops', sa.Column('primary_color', sa.String(7), nullable=True, server_default='#667eea'))
    op.add_column('barbershops', sa.Column('secondary_color', sa.String(7), nullable=True, server_default='#764ba2'))
    op.add_column('barbershops', sa.Column('style', sa.String(50), nullable=True))
    op.add_column('barbershops', sa.Column('primary_goal', sa.String(50), nullable=True))
    op.add_column('barbershops', sa.Column('team_size', sa.Integer, nullable=True))
    op.add_column('barbershops', sa.Column('avg_service_duration', sa.Integer, nullable=True))
    op.add_column('barbershops', sa.Column('personality', sa.String(50), nullable=True))
    op.add_column('barbershops', sa.Column('onboarding_completed', sa.Boolean, nullable=False, server_default='0'))


def downgrade():
    # Remove personalization columns
    op.drop_column('barbershops', 'primary_color')
    op.drop_column('barbershops', 'secondary_color')
    op.drop_column('barbershops', 'style')
    op.drop_column('barbershops', 'primary_goal')
    op.drop_column('barbershops', 'team_size')
    op.drop_column('barbershops', 'avg_service_duration')
    op.drop_column('barbershops', 'personality')
    op.drop_column('barbershops', 'onboarding_completed')
