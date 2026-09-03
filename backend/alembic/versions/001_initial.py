"""
Create initial database schema.

Creates tables for:
- Users
- Barbershops
- Appointments
- Subscriptions
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime

revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create subscriptions table
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plan', sa.String(50), nullable=False),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('current_period_start', sa.DateTime(), nullable=False),
        sa.Column('current_period_end', sa.DateTime(), nullable=False),
        sa.Column('max_barbers', sa.Integer(), nullable=True),
        sa.Column('max_appointments_per_month', sa.Integer(), nullable=True),
        sa.Column('max_clients', sa.Integer(), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(255), nullable=True),
        sa.Column('stripe_customer_id', sa.String(255), nullable=True),
        sa.Column('trial_start', sa.DateTime(), nullable=True),
        sa.Column('trial_end', sa.DateTime(), nullable=True),
        sa.Column('is_trial', sa.Boolean(), default=False),
        sa.Column('auto_renew', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime(), default=datetime.utcnow, onupdate=datetime.utcnow),
        sa.Column('is_deleted', sa.Boolean(), default=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Create barbershops table
    op.create_table(
        'barbershops',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False, unique=True),
        sa.Column('description', sa.String(1000), nullable=True),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(20), nullable=False),
        sa.Column('website', sa.String(255), nullable=True),
        sa.Column('address_line1', sa.String(255), nullable=False),
        sa.Column('address_line2', sa.String(255), nullable=True),
        sa.Column('city', sa.String(100), nullable=False),
        sa.Column('state', sa.String(100), nullable=False),
        sa.Column('postal_code', sa.String(20), nullable=False),
        sa.Column('country', sa.String(100), nullable=False, default='USA'),
        sa.Column('latitude', sa.String(50), nullable=True),
        sa.Column('longitude', sa.String(50), nullable=True),
        sa.Column('logo_url', sa.String(500), nullable=True),
        sa.Column('cover_image_url', sa.String(500), nullable=True),
        sa.Column('opening_time', sa.Time(), nullable=True),
        sa.Column('closing_time', sa.Time(), nullable=True),
        sa.Column('timezone', sa.String(50), nullable=False, default='America/New_York'),
        sa.Column('currency', sa.String(3), nullable=False, default='USD'),
        sa.Column('appointment_duration_minutes', sa.Integer(), nullable=False, default=30),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('is_verified', sa.Boolean(), default=False),
        sa.Column('subscription_id', sa.Integer(), sa.ForeignKey('subscriptions.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime(), default=datetime.utcnow, onupdate=datetime.utcnow),
        sa.Column('is_deleted', sa.Boolean(), default=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_barbershops_slug', 'barbershops', ['slug'])

    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('first_name', sa.String(100), nullable=False),
        sa.Column('last_name', sa.String(100), nullable=False),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('role', sa.String(50), nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('is_verified', sa.Boolean(), default=False),
        sa.Column('barbershop_id', sa.Integer(), sa.ForeignKey('barbershops.id'), nullable=True),
        sa.Column('avatar_url', sa.String(500), nullable=True),
        sa.Column('bio', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime(), default=datetime.utcnow, onupdate=datetime.utcnow),
        sa.Column('is_deleted', sa.Boolean(), default=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_users_email', 'users', ['email'])

    # Create appointments table
    op.create_table(
        'appointments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('barbershop_id', sa.Integer(), sa.ForeignKey('barbershops.id'), nullable=False),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('barber_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('scheduled_time', sa.DateTime(), nullable=False),
        sa.Column('estimated_duration', sa.Integer(), nullable=False, default=30),
        sa.Column('actual_start_time', sa.DateTime(), nullable=True),
        sa.Column('actual_end_time', sa.DateTime(), nullable=True),
        sa.Column('service_type', sa.String(50), nullable=False),
        sa.Column('service_price', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('client_notes', sa.Text(), nullable=True),
        sa.Column('barber_notes', sa.Text(), nullable=True),
        sa.Column('cancelled_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('cancellation_reason', sa.Text(), nullable=True),
        sa.Column('checked_in_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime(), default=datetime.utcnow, onupdate=datetime.utcnow),
        sa.Column('is_deleted', sa.Boolean(), default=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_appointments_barbershop_id', 'appointments', ['barbershop_id'])
    op.create_index('ix_appointments_client_id', 'appointments', ['client_id'])
    op.create_index('ix_appointments_barber_id', 'appointments', ['barber_id'])
    op.create_index('ix_appointments_scheduled_time', 'appointments', ['scheduled_time'])
    op.create_index('ix_appointments_status', 'appointments', ['status'])


def downgrade() -> None:
    op.drop_table('appointments')
    op.drop_table('users')
    op.drop_table('barbershops')
    op.drop_table('subscriptions')
