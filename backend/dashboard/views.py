import json

from django.shortcuts import render

from api.models import Hazard, MapVersion, Road, Violation


def dashboard_home(request):
    roads = Road.objects.prefetch_related('nodes', 'hazards').all()
    hazards = Hazard.objects.select_related('road').all()
    violations = Violation.objects.select_related('device', 'telemetry').order_by('-created_at')[:150]
    map_version = MapVersion.objects.current()

    road_data = [
        {
            'id': road.id,
            'name': road.name,
            'speed_limit': road.speed_limit,
            'nodes': [
                {
                    'latitude': float(node.latitude),
                    'longitude': float(node.longitude),
                    'sequence': node.sequence,
                }
                for node in road.nodes.all()
            ],
        }
        for road in roads
    ]

    hazard_data = [
        {
            'id': hazard.id,
            'road_name': hazard.road.name,
            'hazard_type': hazard.hazard_type,
            'latitude': float(hazard.latitude),
            'longitude': float(hazard.longitude),
            'warning_distance': hazard.warning_distance,
        }
        for hazard in hazards
    ]

    violation_data = [
        {
            'id': violation.id,
            'device_id': violation.device.device_id,
            'speed': float(violation.speed),
            'speed_limit': float(violation.speed_limit),
            'latitude': float(violation.latitude),
            'longitude': float(violation.longitude),
            'severity': violation.severity,
            'created_at': violation.created_at.isoformat(),
        }
        for violation in violations
    ]

    return render(request, 'dashboard/index.html', {
        'road_data': road_data,
        'hazard_data': hazard_data,
        'violation_data': violation_data,
        'road_data_json': json.dumps(road_data),
        'hazard_data_json': json.dumps(hazard_data),
        'violation_data_json': json.dumps(violation_data),
        'map_version': map_version,
        'road_count': roads.count(),
        'hazard_count': hazards.count(),
        'violation_count': violations.count(),
    })
