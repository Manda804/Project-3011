import json
from decimal import Decimal
from pathlib import Path

from django.conf import settings
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
def create_telemetry_with_violation(device, road, speed, latitude, longitude):
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


def increment_version(version: str) -> str:
    parts = version.split('.')
    if len(parts) < 2 or not all(part.isdigit() for part in parts):
        raise ValueError(f'Invalid version format: {version}')
    parts[-1] = str(int(parts[-1]) + 1)
    return '.'.join(parts)


def ensure_initial_map_version():
    current = MapVersion.objects.current()
    if current is not None:
        return current

    if MapVersion.objects.exists():
        latest = MapVersion.objects.order_by('-created_at').first()
        version_value = increment_version(latest.version) if latest and latest.version else '1.0.0.0.2'
    else:
        version_value = '1.0.0.0.2'

    version = MapVersion.objects.create(
        version=version_value,
        description='Initial published map version',
        is_current=True
    )
    generate_map_files(version)
    return version


def _write_json_file(filename: str, payload: dict) -> None:
    map_dir = Path(settings.MAPS_DIR)
    map_dir.mkdir(parents=True, exist_ok=True)
    file_path = map_dir / filename
    # Write minified — no indent — keeps file size small for ESP32 download
    file_path.write_text(
        json.dumps(payload, separators=(',', ':'), ensure_ascii=False),
        encoding='utf-8'
    )


def _sample_nodes(nodes, max_count=20):
    """
    Reduce node list to at most max_count points by even sampling.
    ESP32 MAX_ROAD_NODES = 32 — sending more wastes bandwidth and
    causes ArduinoJson to silently truncate or fail.
    Coordinates rounded to 5dp (~1m accuracy) to reduce file size.
    """
    if len(nodes) <= max_count:
        return [
            {'lat': round(float(n.latitude), 5), 'lon': round(float(n.longitude), 5)}
            for n in nodes
        ]
    step = len(nodes) / max_count
    sampled = [nodes[int(i * step)] for i in range(max_count)]
    return [
        {'lat': round(float(n.latitude), 5), 'lon': round(float(n.longitude), 5)}
        for n in sampled
    ]


def generate_map_files(version=None) -> dict:
    """
    Generate roads.json, hazards.json, version.json for ESP32 consumption.

    ESP32 StorageManager.cpp expects:

    roads.json:
    {
      "roads": [
        {
          "id": 1,
          "name": "Cairo Road",
          "speed_limit": 60,
          "nodes": [
            {"lat": -12.82976, "lon": 28.20012},
            ...
          ]
        }
      ]
    }

    hazards.json:
    {
      "hazards": [
        {
          "id": 1,
          "type": "School Zone",
          "description": "Primary school",
          "lat": -12.82976,
          "lon": 28.20012,
          "radius": 250
        }
      ]
    }

    version.json:
    { "version": "1.0.0.0.2" }

    Rules:
    - No top-level "version" key in roads.json or hazards.json
      (StorageManager only looks inside "roads" and "hazards" arrays)
    - Nodes use "lat"/"lon" keys (not "latitude"/"longitude")
    - Hazards use "lat"/"lon" and "radius" (not "latitude"/"longitude"
      and "warning_distance")
    - Hazards use "type" key (not "hazard_type")
    - Max 20 nodes per road — matches ESP32 MAX_ROAD_NODES to save DRAM
    - Coordinates at 5 decimal places (~1m) to keep file small
    - File is minified (no indentation) to reduce download size
    """
    if version is None:
        version = MapVersion.objects.current() or ensure_initial_map_version()

    # ── roads.json ───────────────────────────────────────────
    roads_payload = {
        'roads': [
            {
                'id':          road.id,
                'name':        road.name,
                'speed_limit': int(road.speed_limit),
                'nodes':       _sample_nodes(list(road.nodes.all())),
            }
            for road in Road.objects.prefetch_related('nodes').all()
        ]
    }

    # ── hazards.json ─────────────────────────────────────────
    hazards_payload = {
        'hazards': [
            {
                'id':          hazard.id,
                'type':        hazard.hazard_type,
                'description': hazard.hazard_type,
                'lat':         round(float(hazard.latitude), 5),
                'lon':         round(float(hazard.longitude), 5),
                'radius':      int(hazard.warning_distance),
            }
            for hazard in Hazard.objects.all()
        ]
    }

    # ── version.json ─────────────────────────────────────────
    version_payload = {'version': version.version}

    _write_json_file('roads.json',   roads_payload)
    _write_json_file('hazards.json', hazards_payload)
    _write_json_file('version.json', version_payload)

    return {
        'version':      version.version,
        'roads':        roads_payload,
        'hazards':      hazards_payload,
        'version_file': version_payload,
    }


def publish_map_update(description: str = 'Published map update') -> MapVersion:
    with transaction.atomic():
        current = MapVersion.objects.current()
        if current is None:
            if MapVersion.objects.exists():
                latest = MapVersion.objects.order_by('-created_at').first()
                next_version = increment_version(latest.version) if latest and latest.version else '1.0.0.0.2'
            else:
                next_version = '1.0.0.0.2'
        else:
            next_version = increment_version(current.version)

        version = MapVersion.objects.create(
            version=next_version,
            description=description,
            is_current=True
        )

    try:
        generate_map_files(version)
    except Exception:
        version.delete()
        raise

    return version


def build_map_package(version: MapVersion) -> dict:
    roads = []
    for road in Road.objects.prefetch_related('nodes', 'hazards').all():
        roads.append({
            'id':          road.id,
            'name':        road.name,
            'speed_limit': int(road.speed_limit),
            'nodes': [
                {
                    'sequence':  node.sequence,
                    'latitude':  float(node.latitude),
                    'longitude': float(node.longitude),
                }
                for node in road.nodes.all()
            ],
            'hazards': [
                {
                    'id':               hazard.id,
                    'hazard_type':      hazard.hazard_type,
                    'latitude':         float(hazard.latitude),
                    'longitude':        float(hazard.longitude),
                    'warning_distance': hazard.warning_distance,
                }
                for hazard in road.hazards.all()
            ],
        })

    return {
        'version':     version.version,
        'description': version.description,
        'created_at':  version.created_at.isoformat(),
        'roads':       roads,
    }
