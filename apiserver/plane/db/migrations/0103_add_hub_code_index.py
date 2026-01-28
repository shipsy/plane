# Generated for scoped issue access implementation
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('db', '0102_add_scoped_issue_access_to_workspace'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='issue',
            index=models.Index(
                fields=['hub_code'],
                name='idx_issues_hub_code',
                condition=models.Q(hub_code__isnull=False)
            ),
        ),
    ]
