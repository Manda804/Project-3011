from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Device, MapVersion, Telemetry
from .serializers import (
    DeviceDetailSerializer,
    DeviceLatestTelemetrySerializer,
    DeviceRegisterSerializer,
    MapCheckUpdateSerializer,
    MapVersionSerializer,
    TelemetryHistorySerializer,
    TelemetrySerializer,
)


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


class TelemetryUploadAPIView(generics.CreateAPIView):
    serializer_class = TelemetrySerializer
    queryset = Telemetry.objects.all()


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
