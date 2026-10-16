from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    # Build the index without locking the sessions table
    atomic = False

    dependencies = [
        ("db", "0109_issue_customer_category"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="session",
            index=models.Index(fields=["user_id"], name="sessions_user_id_idx"),
        ),
    ]
