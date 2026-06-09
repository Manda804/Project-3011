from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from .models import Device, Hazard, MapVersion, Road, RoadNode, Telemetry, Violation
from .services import create_telemetry_with_violation


class RoadNodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoadNode
        fields = ['id', 'sequence', 'latitude', 'longitude']


class HazardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hazard
        fields = ['id', 'road', 'hazard_type', 'latitude', 'longitude', 'warning_distance', 'created_at']
        read_only_fields = ['created_at']


class RoadSerializer(serializers.ModelSerializer):
    nodes = RoadNodeSerializer(many=True, read_only=True)
    hazards = HazardSerializer(many=True, read_only=True)

    class Meta:
        model = Road
        fields = ['id', 'name', 'speed_limit', 'created_at', 'updated_at', 'nodes', 'hazards']
        read_only_fields = ['created_at', 'updated_at']


class MapVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MapVersion
        fields = ['id', 'version', 'description', 'created_at', 'is_current']
        read_only_fields = ['id', 'version', 'created_at']


class DeviceRegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = ['device_id', 'device_name', 'current_map_version', 'registered_at', 'last_seen']
        read_only_fields = ['registered_at', 'last_seen']

    def create(self, validated_data):
        device, _ = Device.objects.get_or_create(
            device_id=validated_data['device_id'],
            defaults={
                'device_name': validated_data.get('device_name', ''),
            },
        )
        if validated_data.get('device_name') and device.device_name != validated_data['device_name']:
            device.device_name = validated_data['device_name']
            device.save(update_fields=['device_name'])
        return device


class DeviceDetailSerializer(serializers.ModelSerializer):
    current_map_version = MapVersionSerializer(read_only=True)

    class Meta:
        model = Device
        fields = ['id', 'device_id', 'device_name', 'current_map_version', 'registered_at', 'last_seen']
        read_only_fields = ['id', 'registered_at', 'last_seen']


class ViolationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Violation
        fields = [
            'id',
            'device',
            'telemetry',
            'violation_type',
            'speed',
            'speed_limit',
            'latitude',
            'longitude',
            'severity',
            'created_at',
        ]
        read_only_fields = ['id', 'telemetry', 'created_at']


class TelemetrySerializer(serializers.ModelSerializer):
    device_id = serializers.CharField(write_only=True)
    road = serializers.PrimaryKeyRelatedField(queryset=Road.objects.all())
    violation = ViolationSerializer(read_only=True, source='latest_violation')

    class Meta:
        model = Telemetry
        fields = [
            'id',
            'device_id',
            'device',
            'road',
            'speed',
            'latitude',
            'longitude',
            'uploaded_at',
            'violation',
        ]
        read_only_fields = ['id', 'device', 'uploaded_at', 'violation']

    def validate_device_id(self, value):
        try:
            return Device.objects.get(device_id=value)
        except Device.DoesNotExist:
            raise serializers.ValidationError('Device not registered.')

    def create(self, validated_data):
        device = validated_data.pop('device_id')
        road = validated_data.pop('road')
        telemetry = create_telemetry_with_violation(device=device, road=road, **validated_data)
        return telemetry


class TelemetryHistorySerializer(serializers.ModelSerializer):
    road = RoadSerializer(read_only=True)
    class Meta:
        model = Telemetry
        fields = ['id', 'device', 'road', 'speed', 'latitude', 'longitude', 'uploaded_at']
        read_only_fields = fields


class MapCheckUpdateSerializer(serializers.Serializer):
    device_id = serializers.CharField()
    current_version = serializers.CharField(required=False, allow_blank=True)

    def validate_device_id(self, value):
        try:
            return Device.objects.get(device_id=value)
        except Device.DoesNotExist:
            raise serializers.ValidationError('Device not registered.')


class MapDownloadSerializer(serializers.Serializer):
    version = serializers.CharField()


class DeviceLatestTelemetrySerializer(serializers.ModelSerializer):
    road = RoadSerializer(read_only=True)
    class Meta:
        model = Telemetry
        fields = ['id', 'road', 'speed', 'latitude', 'longitude', 'uploaded_at']
        read_only_fields = fields
