# Generated for scoped issue access implementation
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('db', '0101_add_email_index'),
    ]

    operations = [
        migrations.AddField(
            model_name='workspace',
            name='scoped_issue_access',
            field=models.BooleanField(default=False),
        ),
    ]
