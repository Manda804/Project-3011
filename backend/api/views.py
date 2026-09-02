import asyncio
import json
from decimal import Decimal

from asgiref.sync import async_to_sync
from django.conf import settings
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Device, Hazard, MapVersion, Road, RoadNode, Telemetry, TelemetryRecord, Violation
from .serializers import (
    DeviceDetailSerializer,
    DeviceLatestTelemetrySerializer,
    DeviceRegisterSerializer,
    HazardSerializer,
    MapCheckUpdateSerializer,
    MapVersionSerializer,
    RoadSerializer,
    TelemetryHistorySerializer,
    TelemetrySerializer,
    ViolationSerializer,
)
from .services import (
    build_map_package,
    create_telemetry_with_violation,
    ensure_initial_map_version,
    generate_map_files,
    publish_map_update,
    determine_severity,
)
from backend.asgi import websocket_manager
from pathlib import Path


def _broadcast_telemetry(payload):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(websocket_manager.broadcast(payload))
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def _create_map_version_on_edit():
    """Publish a new map version whenever map data is edited."""
    return publish_map_update(description='Map updated from dashboard')


def _device_name_from_payload(payload):
    """Accept the common ESP32 name keys while keeping one canonical name."""
    for key in ('device_name', 'deviceName', 'name'):
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()[:128]
    return ''


def _register_or_touch_device(payload):
    """Register a device on first contact and refresh its connection state."""
    device_id = str(payload.get('device_id', '')).strip()
    if not device_id:
        return None

    reported_name = _device_name_from_payload(payload)
    device_name = reported_name or device_id
    now = timezone.now()
    with transaction.atomic():
        # A matching name is an existing inventory entry, so reconnects never
        # create a duplicate even if the sender supplies a different ID.
        device = Device.objects.select_for_update().filter(device_name__iexact=device_name).first()
        if device is None:
            device, created = Device.objects.select_for_update().get_or_create(
                device_id=device_id,
                defaults={'device_name': device_name, 'last_seen': now},
            )
            if not created and (not device.device_name or (reported_name and device.device_name == device_id)):
                device.device_name = device_name
        device.last_seen = now
        if payload.get('map_version'):
            device.current_map_version = (
                MapVersion.objects.filter(version=payload['map_version']).order_by('-created_at').first()
                or device.current_map_version
            )
        device.save(update_fields=['device_name', 'last_seen', 'current_map_version'])
    return device


class RoadListCreateAPIView(APIView):
    def get(self, request):
        roads = Road.objects.prefetch_related('nodes', 'hazards').all()
        data = [RoadSerializer(road).data for road in roads]
        return Response({'roads': data})

    @transaction.atomic
    def post(self, request):
        road_name = request.data.get('name')
        speed_limit = request.data.get('speed_limit')
        nodes = request.data.get('nodes', [])
        if not road_name or speed_limit is None:
            return Response({'detail': 'Road name and speed limit are required.'}, status=status.HTTP_400_BAD_REQUEST)

        road = Road.objects.create(name=road_name, speed_limit=int(speed_limit))
        for idx, node in enumerate(nodes, start=1):
            RoadNode.objects.create(
                road=road,
                sequence=idx,
                latitude=node['latitude'],
                longitude=node['longitude'],
            )

        # Create new map version when road is created
        _create_map_version_on_edit()

        return Response(RoadSerializer(road).data, status=status.HTTP_201_CREATED)


class RoadDetailAPIView(APIView):
    def get(self, request, road_id):
        road = get_object_or_404(Road, pk=road_id)
        return Response(RoadSerializer(road).data)

    @transaction.atomic
    def patch(self, request, road_id):
        road = get_object_or_404(Road, pk=road_id)

        if 'nodes' in request.data:
            nodes = request.data.get('nodes', [])
            if not isinstance(nodes, list):
                return Response({'detail': 'Nodes payload must be a list.'}, status=status.HTTP_400_BAD_REQUEST)

            road.nodes.all().delete()
            for idx, node in enumerate(nodes, start=1):
                RoadNode.objects.create(
                    road=road,
                    sequence=idx,
                    latitude=node['latitude'],
                    longitude=node['longitude'],
                )

        if 'name' in request.data:
            road.name = request.data['name']
        if 'speed_limit' in request.data:
            road.speed_limit = int(request.data['speed_limit'])
        road.save(update_fields=['name', 'speed_limit'])
        
        # Create new map version when road is edited
        _create_map_version_on_edit()
        
        return Response(RoadSerializer(road).data)

    @transaction.atomic
    def delete(self, request, road_id):
        road = get_object_or_404(Road, pk=road_id)
        road.delete()
        _create_map_version_on_edit()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RoadNodesUpdateAPIView(APIView):
    @transaction.atomic
    def patch(self, request, road_id):
        road = get_object_or_404(Road, pk=road_id)
        nodes = request.data.get('nodes', [])
        if not isinstance(nodes, list):
            return Response({'detail': 'Nodes payload must be a list.'}, status=status.HTTP_400_BAD_REQUEST)
        road.nodes.all().delete()
        for idx, node in enumerate(nodes, start=1):
            RoadNode.objects.create(
                road=road,
                sequence=idx,
                latitude=node['latitude'],
                longitude=node['longitude'],
            )
        _create_map_version_on_edit()
        return Response(RoadSerializer(road).data)


class HazardListCreateAPIView(APIView):
    def get(self, request):
        hazards = Hazard.objects.select_related('road').all()
        return Response({'hazards': HazardSerializer(hazards, many=True).data})

    @transaction.atomic
    def post(self, request):
        serializer = HazardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        hazard = serializer.save()
        _create_map_version_on_edit()
        return Response(HazardSerializer(hazard).data, status=status.HTTP_201_CREATED)


class HazardDetailAPIView(APIView):
    @transaction.atomic
    def patch(self, request, pk):
        hazard = get_object_or_404(Hazard, pk=pk)
        serializer = HazardSerializer(hazard, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        hazard = serializer.save()
        
        # Create new map version when hazard is edited
        _create_map_version_on_edit()
        
        return Response(HazardSerializer(hazard).data)

    @transaction.atomic
    def delete(self, request, pk):
        hazard = get_object_or_404(Hazard, pk=pk)
        hazard.delete()
        
        # Create new map version when hazard is deleted
        _create_map_version_on_edit()
        
        return Response(status=status.HTTP_204_NO_CONTENT)


class DeviceListAPIView(APIView):
    def get(self, request):
        latest_by_device = {}
        for telemetry in TelemetryRecord.objects.select_related('device').exclude(device=None).order_by('-timestamp'):
            latest_by_device.setdefault(telemetry.device.device_id, telemetry)

        devices = []
        now = timezone.now()
        for device in Device.objects.select_related('current_map_version').all():
            telemetry = latest_by_device.get(device.device_id)
            last_seen = device.last_seen
            age_seconds = (now - last_seen).total_seconds() if last_seen else None
            status = 'offline'
            if age_seconds is not None:
                status = 'online' if age_seconds <= 300 else 'recent' if age_seconds <= 900 else 'offline'
            devices.append({
                'id': device.id,
                'device_id': device.device_id,
                'device_name': device.device_name,
                'current_speed': float(telemetry.speed) if telemetry else None,
                'current_road': telemetry.road_name if telemetry else None,
                'latitude': float(telemetry.latitude) if telemetry else None,
                'longitude': float(telemetry.longitude) if telemetry else None,
                'last_seen': last_seen.isoformat() if last_seen else None,
                'status': status,
                'current_map_version': device.current_map_version.version if device.current_map_version else None,
            })
        return Response({'devices': devices})


class ViolationListAPIView(generics.ListAPIView):
    serializer_class = ViolationSerializer

    def get_queryset(self):
        return Violation.objects.select_related('device').order_by('-created_at')[:150]


class MapVersionListAPIView(generics.ListAPIView):
    serializer_class = MapVersionSerializer
    queryset = MapVersion.objects.order_by('-created_at')[:8]


class PublishMapVersionAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request):
        description = request.data.get('description', 'Published changes from dashboard')
        version = publish_map_update(description=description)
        package = build_map_package(version)
        payload = {
            'version': MapVersionSerializer(version).data,
            'package': package,
            'road_count': Road.objects.count(),
            'hazard_count': Hazard.objects.count(),
        }
        return Response(payload, status=status.HTTP_201_CREATED)


class DeviceRegisterAPIView(generics.CreateAPIView):
    serializer_class = DeviceRegisterSerializer
    queryset = Device.objects.all()


class DeviceDetailAPIView(generics.RetrieveAPIView):
    serializer_class = DeviceDetailSerializer
    lookup_field = 'device_id'
    queryset = Device.objects.all()


class DeviceLatestAPIView(APIView):
    def get(self, request, device_id):
        device = get_object_or_404(Device, device_id=device_id)
        telemetry = TelemetryRecord.objects.filter(device=device).order_by('-timestamp').first()
        if not telemetry:
            return Response({'detail': 'No telemetry available for this device.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = TelemetrySerializer(telemetry)
        return Response(serializer.data)


class DeviceHistoryAPIView(generics.ListAPIView):
    serializer_class = TelemetrySerializer

    def get_queryset(self):
        device_id = self.kwargs['device_id']
        device = get_object_or_404(Device, device_id=device_id)
        return TelemetryRecord.objects.filter(device=device).order_by('-timestamp')


class TelemetryUploadAPIView(APIView):
    def post(self, request):
        device = _register_or_touch_device(request.data)
        if device is None:
            return Response({'device_id': ['This field is required.']}, status=status.HTTP_400_BAD_REQUEST)
        serializer = TelemetrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = serializer.save(device=device)
        _broadcast_telemetry(TelemetrySerializer(record).data)
        return Response({'status': 'ok', 'id': record.id, 'device_id': device.device_id}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def telemetry_upload(request):
    payload = request.data.copy()
    device = _register_or_touch_device(payload)
    if device is None:
        return Response({'device_id': ['This field is required.']}, status=status.HTTP_400_BAD_REQUEST)

    serializer = TelemetrySerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    record = serializer.save(device=device)

    broadcast_payload = dict(serializer.data)
    broadcast_payload['device_id'] = device.device_id
    _broadcast_telemetry(broadcast_payload)
    return Response({'status': 'ok', 'id': record.id, 'device_id': device.device_id}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def batch_telemetry_upload(request):
    try:
        payload = request.data
        records = payload.get('records') if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            return Response({'error': 'Request body must be a JSON array or an object with a records array.'}, status=status.HTTP_400_BAD_REQUEST)

        saved_count = 0
        violation_count = 0
        error_count = 0
        device_ids = []
        synced_devices = {}

        for item in records:
            try:
                if not isinstance(item, dict):
                    raise ValueError('Each record must be an object.')
                device_id = str(item.get('device_id', '')).strip()
                if not device_id:
                    error_count += 1
                    continue

                with transaction.atomic():
                    device = _register_or_touch_device(item)
                    if device is None:
                        raise ValueError('device_id is required.')
                    record_data = dict(item)
                    record_data.pop('device_id', None)
                    record_data.pop('device', None)
                    record_data['offline_log'] = True
                    serializer = TelemetrySerializer(data=record_data)
                    serializer.is_valid(raise_exception=True)
                    telemetry = serializer.save(device=device)
                    speed = telemetry.speed
                    speed_limit = telemetry.speed_limit
                    if speed > 0 and speed_limit > 0 and speed > speed_limit:
                        road = Road.objects.filter(name__iexact=telemetry.road_name).first() or Road.objects.first()
                        if road is None:
                            raise ValueError('A road is required to create a violation.')
                        violation_telemetry = Telemetry.objects.create(
                            device=device,
                            road=road,
                            speed=speed,
                            latitude=telemetry.latitude,
                            longitude=telemetry.longitude,
                        )
                        Violation.objects.create(
                            device=device,
                            telemetry=violation_telemetry,
                            violation_type=Violation.VIOLATION_SPEEDING,
                            speed=speed,
                            speed_limit=speed_limit,
                            latitude=telemetry.latitude,
                            longitude=telemetry.longitude,
                            severity=determine_severity(Decimal(str(speed)), Decimal(str(speed_limit))),
                        )
                        violation_count += 1
                    device.last_seen = timezone.now()
                    device.save(update_fields=['last_seen'])

                saved_count += 1
                synced_devices[device.device_id] = synced_devices.get(device.device_id, 0) + 1
                if device.device_id not in device_ids:
                    device_ids.append(device.device_id)
            except Exception:
                error_count += 1

        summary_device_id = device_ids[0] if len(device_ids) == 1 else ('multiple' if device_ids else '')
        _broadcast_telemetry({
            'type': 'offline_sync',
            'device_id': summary_device_id,
            'record_count': saved_count,
            'violations': violation_count,
            'synced_at': timezone.now().isoformat(),
        })
        return Response({
            'status': 'ok',
            'received': len(records),
            'saved': saved_count,
            'violations': violation_count,
            'errors': error_count,
            'device_id': summary_device_id,
        }, status=status.HTTP_201_CREATED)
    except Exception as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class MapCheckUpdateAPIView(APIView):
    def post(self, request):
        serializer = MapCheckUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        device_id = serializer.validated_data['device_id']
        current_version = serializer.validated_data['current_version']
        latest = MapVersion.objects.current() or ensure_initial_map_version()
        generate_map_files(latest)

        payload = {
            'device_id': device_id,
            'update_required': current_version != latest.version,
            'latest_version': latest.version,
            'current_version': current_version,
        }

        return Response(payload)


@api_view(['POST'])
def map_check_update(request):
    try:
        payload = json.loads(request.body.decode('utf-8')) if request.body else {}
    except (TypeError, ValueError, UnicodeDecodeError):
        payload = {}

    serializer = MapCheckUpdateSerializer(data=payload)
    serializer.is_valid(raise_exception=True)

    device_id = serializer.validated_data['device_id']
    current_version = serializer.validated_data['current_version']
    _register_or_touch_device({
        'device_id': device_id,
        'device_name': _device_name_from_payload(payload),
        'map_version': current_version,
    })
    latest = MapVersion.objects.current() or ensure_initial_map_version()
    generate_map_files(latest)

    latest_version = latest.version
    update_required = current_version != latest_version
    response = {
        'update_required': update_required,
        'latest_version': latest_version,
        'current_version': current_version,
    }
    return Response(response)


def map_download(request, filename):
    allowed = {'roads.json', 'hazards.json', 'version.json'}
    if filename not in allowed:
        raise Http404('File not allowed')

    file_path = settings.MAPS_DIR / filename
    if not file_path.exists():
        latest = MapVersion.objects.current() or ensure_initial_map_version()
        generate_map_files(latest)
        if not file_path.exists():
            raise Http404('Map file not found')

    return FileResponse(file_path.open('rb'), content_type='application/json')


class MapDownloadAPIView(APIView):
    def get(self, request, version):
        map_version = get_object_or_404(MapVersion, version=version)
        package = map_version.generate_package()
        serializer = MapVersionSerializer(map_version)
        response_data = {
            'version': serializer.data,
            'package': package,
        }
        return Response(response_data)


@api_view(['GET'])
def telemetry_latest(request):
    records = TelemetryRecord.objects.order_by('-timestamp')[:50]
    serializer = TelemetrySerializer(records, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def device_telemetry_history(request, device_id):
    device = get_object_or_404(Device, device_id=device_id)
    records = TelemetryRecord.objects.filter(device=device).order_by('-timestamp')[:50]
    serializer = TelemetrySerializer(records, many=True)
    return Response(serializer.data)
