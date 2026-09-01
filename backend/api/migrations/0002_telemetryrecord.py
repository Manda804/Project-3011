from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='TelemetryRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('device_id', models.CharField(max_length=32)),
                ('speed', models.FloatField()),
                ('road_name', models.CharField(blank=True, max_length=64)),
                ('speed_limit', models.FloatField(default=0)),
                ('latitude', models.FloatField(default=0)),
                ('longitude', models.FloatField(default=0)),
                ('map_version', models.CharField(blank=True, max_length=16)),
                ('has_fix', models.BooleanField(default=False)),
                ('satellites', models.IntegerField(default=0)),
                ('obd_connected', models.BooleanField(default=False)),
                ('hazard', models.CharField(blank=True, max_length=32)),
                ('speeding', models.BooleanField(default=False)),
                ('on_road', models.BooleanField(default=False)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-timestamp'],
            },
        ),
    ]
