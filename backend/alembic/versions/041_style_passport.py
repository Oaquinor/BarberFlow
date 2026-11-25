"""Add a private, consent-controlled customer style passport."""

from alembic import op
import sqlalchemy as sa

revision = "041_style_passport"
down_revision = "040_operating_expenses"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "style_passport_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_user_id", sa.Integer(), nullable=False),
        sa.Column("barbershop_id", sa.Integer(), nullable=False),
        sa.Column("appointment_id", sa.Integer(), nullable=False),
        sa.Column("haircut_type", sa.String(length=120), nullable=True),
        sa.Column("fade_style", sa.String(length=120), nullable=True),
        sa.Column("top_length", sa.String(length=120), nullable=True),
        sa.Column("sides_length", sa.String(length=120), nullable=True),
        sa.Column("beard_style", sa.String(length=120), nullable=True),
        sa.Column("products_used", sa.String(length=300), nullable=True),
        sa.Column("preferences", sa.Text(), nullable=True),
        sa.Column("barber_notes", sa.Text(), nullable=True),
        sa.Column("recommendations", sa.Text(), nullable=True),
        sa.Column(
            "share_with_shop",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("share_consent_updated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["barbershop_id"], ["barbershops.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("appointment_id", name="uq_style_passport_appointment"),
    )
    op.create_index(
        "ix_style_passport_account_shop_active",
        "style_passport_entries",
        ["account_user_id", "barbershop_id", "is_deleted"],
    )
    op.create_index(
        "ix_style_passport_shop_share_active",
        "style_passport_entries",
        ["barbershop_id", "share_with_shop", "is_deleted"],
    )
    op.create_table(
        "style_passport_photos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("photo_kind", sa.String(length=20), nullable=False),
        sa.Column("storage_key", sa.String(length=64), nullable=False),
        sa.Column(
            "content_type",
            sa.String(length=50),
            nullable=False,
            server_default="image/jpeg",
        ),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("byte_size > 0", name="ck_style_passport_photo_size_positive"),
        sa.CheckConstraint("byte_size <= 5242880", name="ck_style_passport_photo_size_limit"),
        sa.CheckConstraint(
            "photo_kind IN ('reference','result')",
            name="ck_style_passport_photo_kind",
        ),
        sa.ForeignKeyConstraint(["entry_id"], ["style_passport_entries.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uq_style_passport_photo_storage_key"),
    )
    op.create_index(
        "ix_style_passport_photo_entry",
        "style_passport_photos",
        ["entry_id", "is_deleted"],
    )


def downgrade():
    op.drop_index("ix_style_passport_photo_entry", table_name="style_passport_photos")
    op.drop_table("style_passport_photos")
    op.drop_index(
        "ix_style_passport_shop_share_active",
        table_name="style_passport_entries",
    )
    op.drop_index(
        "ix_style_passport_account_shop_active",
        table_name="style_passport_entries",
    )
    op.drop_table("style_passport_entries")
