from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_telemetryrecord'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='telemetryrecord',
            name='device_id',
        ),
        migrations.AddField(
            model_name='telemetryrecord',
            name='device',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='telemetry_records', to='api.device'),
        ),
    ]
