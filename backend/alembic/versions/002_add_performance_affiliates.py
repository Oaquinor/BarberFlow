"""
Add new models for complete system.

Adds:
- Services
- Barber Performance
- Affiliates
- Commissions
- Achievements
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime

revision = '002_add_performance_affiliates'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create services table
    op.create_table(
        'services',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('barbershop_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('duration_minutes', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('price', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('display_order', sa.Integer(), server_default='0'),
        sa.Column('icon', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.Column('is_deleted', sa.Boolean(), server_default='0'),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['barbershop_id'], ['barbershops.id'])
    )
    op.create_index('ix_services_barbershop_id', 'services', ['barbershop_id'])

    # Create affiliates table
    op.create_table(
        'affiliates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('first_name', sa.String(100), nullable=False),
        sa.Column('last_name', sa.String(100), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('commission_rate', sa.Float(), nullable=False, server_default='0.15'),
        sa.Column('bank_account', sa.String(100), nullable=True),
        sa.Column('bank_name', sa.String(100), nullable=True),
        sa.Column('id_number', sa.String(50), nullable=True),
        sa.Column('total_referrals', sa.Integer(), server_default='0'),
        sa.Column('active_referrals', sa.Integer(), server_default='0'),
        sa.Column('total_commissions_earned', sa.Integer(), server_default='0'),
        sa.Column('total_commissions_paid', sa.Integer(), server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('joined_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.Column('is_deleted', sa.Boolean(), server_default='0'),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('code')
    )
    op.create_index('ix_affiliates_email', 'affiliates', ['email'])
    op.create_index('ix_affiliates_code', 'affiliates', ['code'])

    # Add affiliate reference to barbershops
    op.add_column('barbershops', sa.Column('referred_by_affiliate_id', sa.Integer(), nullable=True))
    op.add_column('barbershops', sa.Column('primary_color', sa.String(7), nullable=True))
    op.add_column('barbershops', sa.Column('secondary_color', sa.String(7), nullable=True))
    op.create_foreign_key('fk_barbershops_affiliate', 'barbershops', 'affiliates', ['referred_by_affiliate_id'], ['id'])

    # Create commissions table
    op.create_table(
        'commissions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('affiliate_id', sa.Integer(), nullable=False),
        sa.Column('barbershop_id', sa.Integer(), nullable=False),
        sa.Column('subscription_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('commission_rate', sa.Integer(), nullable=False),
        sa.Column('period_start', sa.DateTime(), nullable=False),
        sa.Column('period_end', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.Column('payment_method', sa.String(50), nullable=True),
        sa.Column('payment_reference', sa.String(100), nullable=True),
        sa.Column('payment_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.Column('is_deleted', sa.Boolean(), server_default='0'),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['affiliate_id'], ['affiliates.id']),
        sa.ForeignKeyConstraint(['barbershop_id'], ['barbershops.id']),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'])
    )
    op.create_index('ix_commissions_affiliate_id', 'commissions', ['affiliate_id'])
    op.create_index('ix_commissions_status', 'commissions', ['status'])

    # Create barber_performances table
    op.create_table(
        'barber_performances',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('barbershop_id', sa.Integer(), nullable=False),
        sa.Column('barber_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('appointments_completed', sa.Integer(), server_default='0'),
        sa.Column('appointments_cancelled', sa.Integer(), server_default='0'),
        sa.Column('appointments_no_show', sa.Integer(), server_default='0'),
        sa.Column('total_revenue', sa.Integer(), server_default='0'),
        sa.Column('total_service_time_minutes', sa.Integer(), server_default='0'),
        sa.Column('average_service_time_minutes', sa.Float(), nullable=True),
        sa.Column('time_efficiency_percentage', sa.Float(), nullable=True),
        sa.Column('consecutive_days_worked', sa.Integer(), server_default='0'),
        sa.Column('current_streak', sa.Integer(), server_default='0'),
        sa.Column('best_streak', sa.Integer(), server_default='0'),
        sa.Column('daily_goal_completed', sa.Integer(), server_default='0'),
        sa.Column('extra_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.Column('is_deleted', sa.Boolean(), server_default='0'),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['barbershop_id'], ['barbershops.id']),
        sa.ForeignKeyConstraint(['barber_id'], ['users.id'])
    )
    op.create_index('ix_barber_performances_barbershop_id', 'barber_performances', ['barbershop_id'])
    op.create_index('ix_barber_performances_barber_id', 'barber_performances', ['barber_id'])
    op.create_index('ix_barber_performances_date', 'barber_performances', ['date'])

    # Create achievements table
    op.create_table(
        'achievements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('icon', sa.String(50), nullable=False),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('requirement_type', sa.String(50), nullable=False),
        sa.Column('requirement_value', sa.Integer(), nullable=False),
        sa.Column('points', sa.Integer(), server_default='0'),
        sa.Column('rarity', sa.String(20), server_default='common'),
        sa.Column('is_active', sa.Boolean(), server_default='1'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.Column('is_deleted', sa.Boolean(), server_default='0'),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )
    op.create_index('ix_achievements_code', 'achievements', ['code'])

    # Create user_achievements table
    op.create_table(
        'user_achievements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('achievement_id', sa.Integer(), nullable=False),
        sa.Column('barbershop_id', sa.Integer(), nullable=False),
        sa.Column('earned_at', sa.DateTime(), nullable=False),
        sa.Column('progress', sa.Integer(), server_default='100'),
        sa.Column('is_viewed', sa.Boolean(), server_default='0'),
        sa.Column('context_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.Column('is_deleted', sa.Boolean(), server_default='0'),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['achievement_id'], ['achievements.id']),
        sa.ForeignKeyConstraint(['barbershop_id'], ['barbershops.id'])
    )
    op.create_index('ix_user_achievements_user_id', 'user_achievements', ['user_id'])
    op.create_index('ix_user_achievements_achievement_id', 'user_achievements', ['achievement_id'])


def downgrade() -> None:
    op.drop_table('user_achievements')
    op.drop_table('achievements')
    op.drop_table('barber_performances')
    op.drop_table('commissions')
    op.drop_constraint('fk_barbershops_affiliate', 'barbershops', type_='foreignkey')
    op.drop_column('barbershops', 'secondary_color')
    op.drop_column('barbershops', 'primary_color')
    op.drop_column('barbershops', 'referred_by_affiliate_id')
    op.drop_table('affiliates')
    op.drop_table('services')
