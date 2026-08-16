from decimal import Decimal

from asgiref.sync import async_to_sync
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Device, Hazard, MapVersion, Road, RoadNode, Telemetry, Violation
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
from .services import build_map_package, create_telemetry_with_violation
from backend.asgi import websocket_manager


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
        return Response(RoadSerializer(road).data)

    def delete(self, request, road_id):
        road = get_object_or_404(Road, pk=road_id)
        road.delete()
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
        return Response(RoadSerializer(road).data)


class HazardListCreateAPIView(APIView):
    def get(self, request):
        hazards = Hazard.objects.select_related('road').all()
        return Response({'hazards': HazardSerializer(hazards, many=True).data})

    def post(self, request):
        serializer = HazardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        hazard = serializer.save()
        return Response(HazardSerializer(hazard).data, status=status.HTTP_201_CREATED)


class HazardDetailAPIView(APIView):
    def patch(self, request, pk):
        hazard = get_object_or_404(Hazard, pk=pk)
        serializer = HazardSerializer(hazard, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        hazard = serializer.save()
        return Response(HazardSerializer(hazard).data)

    def delete(self, request, pk):
        hazard = get_object_or_404(Hazard, pk=pk)
        hazard.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DeviceListAPIView(APIView):
    def get(self, request):
        latest_by_device = {}
        for telemetry in Telemetry.objects.select_related('road', 'device').order_by('-uploaded_at'):
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
                'current_road': telemetry.road.name if telemetry else None,
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
    def post(self, request):
        description = request.data.get('description', 'Published changes from dashboard')
        version = MapVersion.objects.create(is_current=True, description=description)
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
        telemetry = Telemetry.objects.filter(device=device).order_by('-uploaded_at').first()
        if not telemetry:
            return Response({'detail': 'No telemetry available for this device.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = DeviceLatestTelemetrySerializer(telemetry)
        return Response(serializer.data)


class DeviceHistoryAPIView(generics.ListAPIView):
    serializer_class = TelemetryHistorySerializer

    def get_queryset(self):
        device_id = self.kwargs['device_id']
        device = get_object_or_404(Device, device_id=device_id)
        return Telemetry.objects.filter(device=device).order_by('-uploaded_at')


class TelemetryUploadAPIView(APIView):
    def post(self, request):
        serializer = TelemetrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        telemetry = serializer.save()
        output = TelemetrySerializer(telemetry).data
        violation = telemetry.latest_violation
        message = {
            'type': 'telemetry_update',
            'device_id': telemetry.device.device_id,
            'device_name': telemetry.device.device_name,
            'latitude': float(telemetry.latitude),
            'longitude': float(telemetry.longitude),
            'speed': float(telemetry.speed),
            'road': telemetry.road.name,
            'last_seen': telemetry.device.last_seen.isoformat() if telemetry.device.last_seen else None,
            'status': 'online',
            'current_map_version': telemetry.device.current_map_version.version if telemetry.device.current_map_version else None,
            'violation': {
                'id': violation.id,
                'speed': float(violation.speed),
                'speed_limit': float(violation.speed_limit),
                'latitude': float(violation.latitude),
                'longitude': float(violation.longitude),
                'severity': violation.severity,
                'created_at': violation.created_at.isoformat(),
            } if violation else None,
        }
        async_to_sync(websocket_manager.broadcast)(message)
        return Response(output, status=status.HTTP_201_CREATED)


class MapCheckUpdateAPIView(APIView):
    def post(self, request):
        serializer = MapCheckUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device = serializer.validated_data['device_id']
        current_version = serializer.validated_data.get('current_version')
        active = MapVersion.objects.current()

        payload = {
            'device_id': device.device_id,
            'has_update': False,
            'current_version': active.version if active else None,
            'download_url': None,
        }

        if active and active.version != current_version:
            payload['has_update'] = True
            payload['download_url'] = request.build_absolute_uri(f'/api/maps/download/{active.version}/')

        return Response(payload)


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
