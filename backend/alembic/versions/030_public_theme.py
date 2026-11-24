"""Add a configurable light or dark public booking theme."""

from alembic import op
import sqlalchemy as sa


revision = "030_public_theme"
down_revision = "029_public_brand_gallery"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "barbershops",
        sa.Column("public_theme", sa.String(length=10), nullable=False, server_default="light"),
    )


def downgrade():
    op.drop_column("barbershops", "public_theme")
