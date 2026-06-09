from decimal import Decimal

from django.db import models
from django.db import transaction


class Road(models.Model):
    name = models.CharField(max_length=128)
    speed_limit = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class RoadNode(models.Model):
    road = models.ForeignKey(Road, related_name='nodes', on_delete=models.CASCADE)
    sequence = models.PositiveIntegerField()
    latitude = models.DecimalField(max_digits=10, decimal_places=7)
    longitude = models.DecimalField(max_digits=10, decimal_places=7)

    class Meta:
        ordering = ['road', 'sequence']
        unique_together = [('road', 'sequence')]

    def __str__(self):
        return f'{self.road.name} node {self.sequence}'


class Hazard(models.Model):
    HAZARD_SCHOOL_ZONE = 'School Zone'
    HAZARD_SHARP_CURVE = 'Sharp Curve'
    HAZARD_SPEED_BUMP = 'Speed Bump'
    HAZARD_RAILWAY = 'Railway Crossing'
    HAZARD_CONSTRUCTION = 'Construction Zone'

    HAZARD_CHOICES = [
        (HAZARD_SCHOOL_ZONE, 'School Zone'),
        (HAZARD_SHARP_CURVE, 'Sharp Curve'),
        (HAZARD_SPEED_BUMP, 'Speed Bump'),
        (HAZARD_RAILWAY, 'Railway Crossing'),
        (HAZARD_CONSTRUCTION, 'Construction Zone'),
    ]

    road = models.ForeignKey(Road, related_name='hazards', on_delete=models.CASCADE)
    hazard_type = models.CharField(max_length=32, choices=HAZARD_CHOICES)
    latitude = models.DecimalField(max_digits=10, decimal_places=7)
    longitude = models.DecimalField(max_digits=10, decimal_places=7)
    warning_distance = models.PositiveIntegerField(help_text='Warning radius in meters')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['road', 'created_at']

    def __str__(self):
        return f'{self.hazard_type} on {self.road.name}'


class MapVersionManager(models.Manager):
    def current(self):
        return self.filter(is_current=True).order_by('-created_at').first()


class MapVersion(models.Model):
    version = models.CharField(max_length=64, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_current = models.BooleanField(default=False)

    objects = MapVersionManager()

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.version:
            self.version = self._generate_next_version()

        with transaction.atomic():
            if self.is_current:
                self.__class__.objects.filter(is_current=True).exclude(pk=self.pk).update(is_current=False)
            super().save(*args, **kwargs)

    def _generate_next_version(self):
        previous = self.__class__.objects.order_by('-created_at').first()
        if previous and previous.version:
            parts = previous.version.split('.')
            if all(part.isdigit() for part in parts):
                parts[-1] = str(int(parts[-1]) + 1)
                return '.'.join(parts)
        return '1.0.0.0.1'

    def generate_package(self):
        roads = []
        for road in Road.objects.prefetch_related('nodes', 'hazards').all():
            roads.append({
                'id': road.id,
                'name': road.name,
                'speed_limit': int(road.speed_limit),
                'nodes': [
                    {
                        'sequence': node.sequence,
                        'latitude': float(node.latitude),
                        'longitude': float(node.longitude),
                    }
                    for node in road.nodes.all()
                ],
                'hazards': [
                    {
                        'id': hazard.id,
                        'hazard_type': hazard.hazard_type,
                        'latitude': float(hazard.latitude),
                        'longitude': float(hazard.longitude),
                        'warning_distance': hazard.warning_distance,
                    }
                    for hazard in road.hazards.all()
                ],
            })
        return {
            'version': self.version,
            'description': self.description,
            'created_at': self.created_at.isoformat(),
            'roads': roads,
        }

    def __str__(self):
        return f'{self.version}'


class Device(models.Model):
    device_id = models.CharField(max_length=128, unique=True)
    device_name = models.CharField(max_length=128, blank=True)
    current_map_version = models.ForeignKey(MapVersion, null=True, blank=True, on_delete=models.SET_NULL)
    registered_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['device_id']

    def __str__(self):
        return self.device_id


class Telemetry(models.Model):
    device = models.ForeignKey(Device, related_name='telemetry', on_delete=models.CASCADE)
    speed = models.DecimalField(max_digits=6, decimal_places=2)
    road = models.ForeignKey(Road, related_name='telemetry', on_delete=models.PROTECT)
    latitude = models.DecimalField(max_digits=10, decimal_places=7)
    longitude = models.DecimalField(max_digits=10, decimal_places=7)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'Telemetry #{self.pk} for {self.device}'

    @property
    def latest_violation(self):
        return self.violations.order_by('-created_at').first()


class Violation(models.Model):
    VIOLATION_SPEEDING = 'SPEEDING'
    VIOLATION_CHOICES = [
        (VIOLATION_SPEEDING, 'Speeding'),
    ]

    SEVERITY_LOW = 'LOW'
    SEVERITY_MEDIUM = 'MEDIUM'
    SEVERITY_HIGH = 'HIGH'
    SEVERITY_CHOICES = [
        (SEVERITY_LOW, 'Low'),
        (SEVERITY_MEDIUM, 'Medium'),
        (SEVERITY_HIGH, 'High'),
    ]

    device = models.ForeignKey(Device, related_name='violations', on_delete=models.CASCADE)
    telemetry = models.ForeignKey(Telemetry, related_name='violations', on_delete=models.CASCADE)
    violation_type = models.CharField(max_length=32, choices=VIOLATION_CHOICES, default=VIOLATION_SPEEDING)
    speed = models.DecimalField(max_digits=6, decimal_places=2)
    speed_limit = models.DecimalField(max_digits=6, decimal_places=2)
    latitude = models.DecimalField(max_digits=10, decimal_places=7)
    longitude = models.DecimalField(max_digits=10, decimal_places=7)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.violation_type} by {self.device} at {self.created_at}'
