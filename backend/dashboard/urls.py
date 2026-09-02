from django.urls import path

from .views import (
    analytics_view,
    dashboard_home,
    device_detail_view,
    devices_view,
    hazards_view,
    index,
    landing_view,
    road_editor_view,
    roads_view,
    team_member_view,
    team_overview_view,
    versions_view,
    violations_view,
)

urlpatterns = [
    path('', landing_view, name='dashboard'),
    path('team/', team_overview_view, name='team-overview'),
    path('team/<slug:member_slug>/', team_member_view, name='team-member'),
    path('overview/', dashboard_home, name='dashboard-home'),
    path('roads/', roads_view, name='dashboard-roads'),
    path('road-editor/', road_editor_view, name='dashboard-road-editor'),
    path('hazards/', hazards_view, name='dashboard-hazards'),
    path('devices/', devices_view, name='dashboard-devices'),
    path('devices/<str:device_id>/', device_detail_view, name='dashboard-device-detail'),
    path('violations/', violations_view, name='dashboard-violations'),
    path('versions/', versions_view, name='dashboard-versions'),
    path('analytics/', analytics_view, name='dashboard-analytics'),
]