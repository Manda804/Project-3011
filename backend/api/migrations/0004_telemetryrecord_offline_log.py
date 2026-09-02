from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0003_telemetryrecord_device'),
    ]

    operations = [
        migrations.AddField(
            model_name='telemetryrecord',
            name='offline_log',
            field=models.BooleanField(default=False),
        ),
    ]
