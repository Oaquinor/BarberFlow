"""Store barber shop gallery and service photography."""

from alembic import op
import sqlalchemy as sa


revision = "029_public_brand_gallery"
down_revision = "028_notification_recipient_user"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "barbershops",
        sa.Column("gallery_images", sa.JSON(), nullable=False, server_default=sa.text("('[]')")),
    )
    op.add_column("services", sa.Column("image_url", sa.String(length=500), nullable=True))


def downgrade():
    op.drop_column("services", "image_url")
    op.drop_column("barbershops", "gallery_images")
