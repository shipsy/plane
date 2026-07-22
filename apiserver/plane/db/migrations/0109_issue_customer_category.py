from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0108_issue_start_date_time_target_date_time'),
    ]

    operations = [
        migrations.AddField(
            model_name='issue',
            name='customer_category',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
