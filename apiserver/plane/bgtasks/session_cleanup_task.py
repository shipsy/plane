from django.utils import timezone
from plane.db.models import Session
from celery import shared_task

BATCH_SIZE = 5000


@shared_task
def delete_expired_sessions():
    # Expired sessions are never read again; delete them in batches so the
    # sessions table stays small (expire_date is indexed)
    now = timezone.now()
    while True:
        session_keys = list(
            Session.objects.filter(expire_date__lt=now).values_list(
                "session_key", flat=True
            )[:BATCH_SIZE]
        )
        if not session_keys:
            break
        Session.objects.filter(session_key__in=session_keys).delete()
