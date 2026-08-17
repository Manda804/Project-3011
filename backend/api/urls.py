from django.urls import path

from . import views

urlpatterns = [
    path('roads/', views.RoadListCreateAPIView.as_view(), name='road-list-create'),
    path('roads/<int:road_id>/', views.RoadDetailAPIView.as_view(), name='road-detail'),
    path('roads/<int:road_id>/nodes/', views.RoadNodesUpdateAPIView.as_view(), name='road-node-update'),
    path('hazards/', views.HazardListCreateAPIView.as_view(), name='hazard-list-create'),
    path('hazards/<int:pk>/', views.HazardDetailAPIView.as_view(), name='hazard-detail'),
    path('devices/', views.DeviceListAPIView.as_view(), name='device-list'),
    path('devices/register/', views.DeviceRegisterAPIView.as_view(), name='device-register'),
    path('devices/<str:device_id>/', views.DeviceDetailAPIView.as_view(), name='device-detail'),
    path('devices/<str:device_id>/latest/', views.DeviceLatestAPIView.as_view(), name='device-latest'),
    path('devices/<str:device_id>/history/', views.DeviceHistoryAPIView.as_view(), name='device-history'),
    path('devices/<str:device_id>/telemetry/', views.device_telemetry_history, name='device-telemetry-history'),
    path('telemetry/upload/', views.telemetry_upload, name='telemetry-upload'),
    path('telemetry/latest/', views.telemetry_latest, name='telemetry-latest'),
    path('violations/', views.ViolationListAPIView.as_view(), name='violation-list'),
    path('map-versions/', views.MapVersionListAPIView.as_view(), name='map-version-list'),
    path('map-versions/publish/', views.PublishMapVersionAPIView.as_view(), name='map-version-publish'),
    path('maps/check-update/', views.map_check_update, name='map-check-update'),
    path('maps/download/<str:filename>', views.map_download, name='map-download'),
    path('maps/download/<str:version>/', views.MapDownloadAPIView.as_view(), name='map-download-version'),
]
