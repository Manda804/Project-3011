from django.contrib import admin

from .models import Device, Hazard, MapVersion, Road, RoadNode, Telemetry, TelemetryRecord, Violation


class RoadNodeInline(admin.TabularInline):
    model = RoadNode
    extra = 1


class HazardInline(admin.TabularInline):
    model = Hazard
    extra = 1


@admin.register(Road)
class RoadAdmin(admin.ModelAdmin):
    list_display = ['name', 'speed_limit', 'created_at', 'updated_at']
    search_fields = ['name']
    list_filter = ['speed_limit']
    inlines = [RoadNodeInline, HazardInline]


@admin.register(RoadNode)
class RoadNodeAdmin(admin.ModelAdmin):
    list_display = ['road', 'sequence', 'latitude', 'longitude']
    search_fields = ['road__name']
    list_filter = ['road']


@admin.register(Hazard)
class HazardAdmin(admin.ModelAdmin):
    list_display = ['hazard_type', 'road', 'warning_distance', 'created_at']
    search_fields = ['road__name', 'hazard_type']
    list_filter = ['hazard_type', 'road']


@admin.register(MapVersion)
class MapVersionAdmin(admin.ModelAdmin):
    list_display = ['version', 'is_current', 'created_at']
    list_filter = ['is_current']
    actions = ['make_current']

    @admin.action(description='Mark selected version as current')
    def make_current(self, request, queryset):
        self.model.objects.filter(is_current=True).update(is_current=False)
        queryset.update(is_current=True)


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ['device_id', 'device_name', 'current_map_version', 'registered_at', 'last_seen']
    search_fields = ['device_id', 'device_name']
    list_filter = ['current_map_version']


@admin.register(TelemetryRecord)
class TelemetryRecordAdmin(admin.ModelAdmin):
    list_display = ['device_id', 'speed', 'road_name', 'speeding', 'hazard', 'has_fix', 'timestamp']
    list_filter = ['device_id', 'speeding', 'on_road', 'has_fix']
    search_fields = ['device_id', 'road_name']


@admin.register(Telemetry)
class TelemetryAdmin(admin.ModelAdmin):
    list_display = ['device', 'road', 'speed', 'latitude', 'longitude', 'uploaded_at']
    search_fields = ['device__device_id', 'road__name']
    list_filter = ['road', 'uploaded_at']


@admin.register(Violation)
class ViolationAdmin(admin.ModelAdmin):
    list_display = ['device', 'violation_type', 'speed', 'speed_limit', 'severity', 'created_at']
    search_fields = ['device__device_id', 'telemetry__id']
    list_filter = ['violation_type', 'severity', 'created_at']
