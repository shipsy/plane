# Python imports
from datetime import timedelta

# Django imports
from django.conf import settings
from django.utils import timezone
from django.db.models import Q

# Third party imports
from celery import shared_task

# Module imports
from plane.db.models import ExporterHistory
from plane.utils.s3_client import get_s3_client


@shared_task
def delete_old_s3_link():
    # Get a list of keys and IDs to process
    expired_exporter_history = ExporterHistory.objects.filter(
        Q(url__isnull=False)
        & Q(created_at__lte=timezone.now() - timedelta(days=8))
    ).values_list("key", "id")
    if settings.USE_MINIO:
        s3 = get_s3_client(endpoint_url=settings.AWS_S3_ENDPOINT_URL)
    else:
        s3 = get_s3_client(region_name=settings.AWS_REGION)

    for file_name, exporter_id in expired_exporter_history:
        # Delete object from S3
        if file_name:
            if settings.USE_MINIO:
                s3.delete_object(
                    Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=file_name
                )
            else:
                s3.delete_object(
                    Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=file_name
                )

        ExporterHistory.objects.filter(id=exporter_id).update(url=None)
