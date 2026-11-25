"""Add tenant-configurable questions to public bookings."""

from alembic import op
import sqlalchemy as sa


revision = "031_booking_questions"
down_revision = "030_public_theme"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("barbershops", sa.Column("booking_questions", sa.JSON(), nullable=True))
    op.execute(sa.text("UPDATE barbershops SET booking_questions = JSON_ARRAY() WHERE booking_questions IS NULL"))


def downgrade():
    op.drop_column("barbershops", "booking_questions")
