"""Background worker entry points live in ``scripts/notification_worker.py``.

The worker polls a MySQL outbox and schedules appointment reminders. Celery is
not configured or required by the current deployment.
"""
