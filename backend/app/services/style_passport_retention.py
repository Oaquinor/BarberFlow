"""Bounded, auditable retention cleanup for private Style Passport data."""

import logging
import re
from datetime import timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Barbershop, StylePassportEntry, StylePassportPhoto
from app.services.audit_service import record_audit
from app.utils.datetime import utc_now_naive

logger = logging.getLogger(__name__)
_STORAGE_KEY = re.compile(r"^[0-9a-f]{32}\.jpg$")
_BATCH_SIZE = 100


def _photo_path(account_user_id: int, storage_key: str) -> Path | None:
    if not _STORAGE_KEY.fullmatch(storage_key):
        logger.error("Ignoring invalid Style Passport storage key during cleanup")
        return None
    root = (Path(get_settings().UPLOAD_DIR).resolve() / "private" / "style-passport").resolve()
    account_dir = (root / str(account_user_id)).resolve()
    path = (account_dir / storage_key).resolve()
    if path.parent != account_dir:
        return None
    return path


def purge_expired_style_passports(db: Session) -> int:
    """Soft-delete expired records, scrub personal data, then remove private files.

    Tenants without an explicit retention choice are untouched. A bounded batch
    avoids a long transaction; soft-deleted photo files are retried on later runs.
    """
    now = utc_now_naive()
    shops = db.query(Barbershop).filter(
        Barbershop.is_deleted.is_(False),
        Barbershop.style_passport_retention_days.is_not(None),
    ).all()
    expired: list[StylePassportEntry] = []
    for shop in shops:
        cutoff = now - timedelta(days=shop.style_passport_retention_days)
        entries = (
            db.query(StylePassportEntry)
            .filter(
                StylePassportEntry.barbershop_id == shop.id,
                StylePassportEntry.is_deleted.is_(False),
                StylePassportEntry.created_at <= cutoff,
            )
            .order_by(StylePassportEntry.created_at.asc(), StylePassportEntry.id.asc())
            .with_for_update(skip_locked=True)
            .limit(_BATCH_SIZE - len(expired))
            .all()
        )
        for entry in entries:
            photos = db.query(StylePassportPhoto).filter(
                StylePassportPhoto.entry_id == entry.id,
                StylePassportPhoto.is_deleted.is_(False),
            ).all()
            for photo in photos:
                photo.soft_delete()
            entry.haircut_type = None
            entry.fade_style = None
            entry.top_length = None
            entry.sides_length = None
            entry.beard_style = None
            entry.products_used = None
            entry.preferences = None
            entry.barber_notes = None
            entry.recommendations = None
            entry.share_with_shop = False
            entry.share_consent_updated_at = now
            entry.soft_delete()
            record_audit(
                db, None, "style_passport.retention_purged", "style_passport_entry",
                entry.id, shop.id,
                {"retention_days": shop.style_passport_retention_days,
                 "photo_count": len(photos)},
            )
            expired.append(entry)
        if len(expired) >= _BATCH_SIZE:
            break

    if expired:
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

    # Retry physical cleanup for photos already soft-deleted by account actions
    # or by a prior retention run whose filesystem deletion could not complete.
    # Successful cleanup also removes the private metadata row, so a permanently
    # missing file cannot pin the first page of this bounded queue forever.
    pending_photos = (
        db.query(StylePassportPhoto)
        .filter(StylePassportPhoto.is_deleted.is_(True))
        .order_by(StylePassportPhoto.id.asc())
        .limit(_BATCH_SIZE)
        .all()
    )
    for photo in pending_photos:
        entry = db.get(StylePassportEntry, photo.entry_id)
        if entry:
            path = _photo_path(entry.account_user_id, photo.storage_key)
            if path:
                try:
                    path.unlink(missing_ok=True)
                    db.delete(photo)
                except OSError:
                    logger.exception("Could not remove soft-deleted Style Passport photo")
    if pending_photos:
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

    return len(expired)
