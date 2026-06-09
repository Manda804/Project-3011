from django.urls import path

from . import views

urlpatterns = [
    path('devices/register/', views.DeviceRegisterAPIView.as_view(), name='device-register'),
    path('devices/<str:device_id>/', views.DeviceDetailAPIView.as_view(), name='device-detail'),
    path('devices/<str:device_id>/latest/', views.DeviceLatestAPIView.as_view(), name='device-latest'),
    path('devices/<str:device_id>/history/', views.DeviceHistoryAPIView.as_view(), name='device-history'),
    path('telemetry/upload/', views.TelemetryUploadAPIView.as_view(), name='telemetry-upload'),
    path('maps/check-update/', views.MapCheckUpdateAPIView.as_view(), name='map-check-update'),
    path('maps/download/<str:version>/', views.MapDownloadAPIView.as_view(), name='map-download'),
]
