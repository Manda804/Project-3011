import json

from django.db.models import Count
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from api.models import Device, Hazard, MapVersion, Road, Telemetry, TelemetryRecord, Violation


def index(request):
    return render(request, 'dashboard/index.html')


def _device_status(last_seen):
    if not last_seen:
        return 'offline'
    age = (timezone.now() - last_seen).total_seconds()
    if age <= 300:
        return 'online'
    if age <= 900:
        return 'recent'
    return 'offline'


def _serialize_road(road):
    return {
        'id': road.id,
        'name': road.name,
        'speed_limit': road.speed_limit,
        'node_count': road.nodes.count(),
        'hazard_count': road.hazards.count(),
        'nodes': [
            {
                'id': node.id,
                'latitude': float(node.latitude),
                'longitude': float(node.longitude),
                'sequence': node.sequence,
            }
            for node in road.nodes.all()
        ],
    }


def landing_view(request):
    return render(request, 'dashboard/landing.html')


def dashboard_home(request):
    roads_count = Road.objects.count()
    hazards_count = Hazard.objects.count()
    violations_count = Violation.objects.count()
    device_count = Device.objects.count()
    current_version = MapVersion.objects.current()

    recent_telemetry = Telemetry.objects.select_related('device', 'road').order_by('-uploaded_at')[:8]
    recent_violations = Violation.objects.select_related('device').order_by('-created_at')[:8]

    road_preview = [
        _serialize_road(road)
        for road in Road.objects.prefetch_related('nodes').all()
    ]
    hazard_preview = [
        {
            'id': hazard.id,
            'road_name': hazard.road.name,
            'hazard_type': hazard.hazard_type,
            'latitude': float(hazard.latitude),
            'longitude': float(hazard.longitude),
            'warning_distance': hazard.warning_distance,
        }
        for hazard in Hazard.objects.select_related('road').all()
    ]

    return render(request, 'dashboard/index.html', {
        'page': 'dashboard',
        'road_count': roads_count,
        'hazard_count': hazards_count,
        'violation_count': violations_count,
        'device_count': device_count,
        'current_map_version': current_version.version if current_version else 'N/A',
        'last_published_at': current_version.created_at.isoformat() if current_version else None,
        'recent_telemetry': recent_telemetry,
        'recent_violations': recent_violations,
        'road_preview_json': json.dumps(road_preview),
        'hazard_preview_json': json.dumps(hazard_preview),
    })


def roads_view(request):
    query = request.GET.get('q', '').strip()
    min_speed = request.GET.get('min_speed', '').strip()

    roads = Road.objects.annotate(
        node_count=Count('nodes'),
        hazard_count=Count('hazards'),
    ).order_by('name')

    if query:
        roads = roads.filter(name__icontains=query)
    if min_speed.isdigit():
        roads = roads.filter(speed_limit__gte=int(min_speed))

    return render(request, 'dashboard/roads.html', {
        'page': 'roads',
        'roads': roads,
        'query': query,
        'min_speed': min_speed,
    })


def road_editor_view(request):
    return render(request, 'dashboard/map_editor.html')


def hazards_view(request):
    hazard_type = request.GET.get('type', '').strip()
    road_query = request.GET.get('road', '').strip()

    hazards = Hazard.objects.select_related('road').order_by('-created_at')
    if hazard_type:
        hazards = hazards.filter(hazard_type__icontains=hazard_type)
    if road_query:
        hazards = hazards.filter(road__name__icontains=road_query)

    hazard_types = [choice[0] for choice in Hazard.HAZARD_CHOICES]

    return render(request, 'dashboard/hazards.html', {
        'page': 'hazards',
        'hazards': hazards,
        'hazard_types': hazard_types,
        'active_type': hazard_type,
        'road_query': road_query,
    })


def devices_view(request):
    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()

    devices = Device.objects.select_related('current_map_version').all()
    active_devices = []
    for device in devices:
        latest = TelemetryRecord.objects.filter(device=device).order_by('-timestamp').first()
        status = _device_status(device.last_seen)
        active_devices.append({
            'id': device.id,
            'device_id': device.device_id,
            'device_name': device.device_name,
            'current_speed': float(latest.speed) if latest else None,
            'current_road': latest.road_name if latest else None,
            'latitude': float(latest.latitude) if latest else None,
            'longitude': float(latest.longitude) if latest else None,
            'last_seen': device.last_seen,
            'status': status,
            'current_map_version': device.current_map_version.version if device.current_map_version else None,
        })

    if query:
        active_devices = [device for device in active_devices if query.lower() in device['device_id'].lower() or query.lower() in (device['device_name'] or '').lower()]
    if status_filter:
        active_devices = [device for device in active_devices if device['status'] == status_filter]

    return render(request, 'dashboard/devices.html', {
        'page': 'devices',
        'devices': active_devices,
        'query': query,
        'status_filter': status_filter,
    })


def device_detail_view(request, device_id):
    device = get_object_or_404(Device.objects.select_related('current_map_version'), device_id=device_id)
    telemetry = TelemetryRecord.objects.filter(device=device).order_by('-timestamp')
    latest = telemetry.first()
    # Keep the last usable GPS position on screen when a newer upload is still
    # waiting for a GPS fix and therefore contains 0, 0 coordinates.
    latest_location = telemetry.filter(has_fix=True).exclude(latitude=0).exclude(longitude=0).first()
    latest_version = telemetry.exclude(map_version='').first()
    history = telemetry[:100]
    violations = Violation.objects.filter(device=device).order_by('-created_at')[:50]
    status = _device_status(device.last_seen)

    return render(request, 'dashboard/device_detail.html', {
        'page': 'devices',
        'device': device,
        'latest': latest,
        'latest_location': latest_location,
        'reported_map_version': (
            latest_version.map_version if latest_version else
            (device.current_map_version.version if device.current_map_version else '')
        ),
        'history': history,
        'violations': violations,
        'device_status': status,
        'history_json': json.dumps([
            {
                'timestamp': telemetry.timestamp.isoformat(),
                'speed': float(telemetry.speed),
                'latitude': float(telemetry.latitude),
                'longitude': float(telemetry.longitude),
            }
            for telemetry in history
        ]),
        'latest_location_json': json.dumps(
            {
                'latitude': latest_location.latitude,
                'longitude': latest_location.longitude,
            }
            if latest_location else None
        ),
        'violations_json': json.dumps([
            {
                'timestamp': violation.created_at.isoformat(),
                'speed': float(violation.speed),
                'speed_limit': float(violation.speed_limit),
                'latitude': float(violation.latitude),
                'longitude': float(violation.longitude),
                'severity': violation.severity,
                'device_id': violation.device.device_id,
            }
            for violation in violations
        ]),
    })


def violations_view(request):
    severity = request.GET.get('severity', '').strip()
    device_search = request.GET.get('device', '').strip()

    violations = Violation.objects.select_related('device').order_by('-created_at')
    if severity:
        violations = violations.filter(severity__iexact=severity)
    if device_search:
        violations = violations.filter(device__device_id__icontains=device_search)

    return render(request, 'dashboard/violations.html', {
        'page': 'violations',
        'violations': violations,
        'severity': severity,
        'device_search': device_search,
    })


def versions_view(request):
    versions = MapVersion.objects.order_by('-created_at')[:10]
    return render(request, 'dashboard/versions.html', {
        'page': 'versions',
        'versions': versions,
    })


def analytics_view(request):
    status_counts = {'online': 0, 'recent': 0, 'offline': 0}
    for device in Device.objects.all():
        status_counts[_device_status(device.last_seen)] += 1

    road_usage = list(
        Road.objects.annotate(hazard_count=Count('hazards')).order_by('-hazard_count').values('name', 'hazard_count')[:8]
    )
    severity_counts = list(
        Violation.objects.values('severity').annotate(count=Count('id')).order_by('-count')
    )

    return render(request, 'dashboard/analytics.html', {
        'page': 'analytics',
        'status_counts': status_counts,
        'road_usage': road_usage,
        'severity_counts': severity_counts,
    })
