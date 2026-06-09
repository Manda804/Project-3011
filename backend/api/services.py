from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import Device, Hazard, MapVersion, Road, RoadNode, Telemetry, Violation


def determine_severity(speed: Decimal, speed_limit: Decimal) -> str:
    delta = speed - speed_limit
    if delta <= Decimal('5'):
        return Violation.SEVERITY_LOW
    if delta <= Decimal('15'):
        return Violation.SEVERITY_MEDIUM
    return Violation.SEVERITY_HIGH


@transaction.atomic
def create_telemetry_with_violation(device: Device, road: Road, speed: Decimal, latitude: Decimal, longitude: Decimal) -> Telemetry:
    device.last_seen = timezone.now()
    device.save(update_fields=['last_seen'])

    telemetry = Telemetry.objects.create(
        device=device,
        road=road,
        speed=speed,
        latitude=latitude,
        longitude=longitude,
    )

    if speed > road.speed_limit:
        severity = determine_severity(speed, road.speed_limit)
        Violation.objects.create(
            device=device,
            telemetry=telemetry,
            violation_type=Violation.VIOLATION_SPEEDING,
            speed=speed,
            speed_limit=road.speed_limit,
            latitude=latitude,
            longitude=longitude,
            severity=severity,
        )

    return telemetry


def build_map_package(version: MapVersion) -> dict:
    roads = []
    for road in Road.objects.prefetch_related('nodes', 'hazards').all():
        roads.append({
            'id': road.id,
            'name': road.name,
            'speed_limit': int(road.speed_limit),
            'nodes': [
                {'sequence': node.sequence, 'latitude': float(node.latitude), 'longitude': float(node.longitude)}
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

    package = {
        'version': version.version,
        'description': version.description,
        'created_at': version.created_at.isoformat(),
        'roads': roads,
    }
    return package
