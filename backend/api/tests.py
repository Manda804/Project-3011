import json

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from .models import Device, MapVersion, Road, RoadNode, TelemetryRecord


class RoadUpdateTests(TestCase):
    def test_telemetry_automatically_registers_and_tracks_a_new_device(self):
        response = self.client.post(
            reverse('telemetry-upload'),
            data=json.dumps({
                'device_id': 'ESP32-001',
                'device_name': 'Fleet unit 1',
                'speed': 42.5,
                'latitude': -12.8024,
                'longitude': 28.2132,
                'has_fix': True,
                'map_version': '1.0.0.0.2',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        device = Device.objects.get(device_id='ESP32-001')
        self.assertEqual(device.device_name, 'Fleet unit 1')
        self.assertIsNotNone(device.last_seen)
        self.assertTrue(TelemetryRecord.objects.filter(device=device, latitude=-12.8024, longitude=28.2132).exists())

        listing = self.client.get(reverse('device-list')).json()['devices']
        self.assertEqual(listing[0]['status'], 'online')
        self.assertEqual(listing[0]['latitude'], -12.8024)
        self.assertEqual(listing[0]['longitude'], 28.2132)

        latest = self.client.get(reverse('device-latest', args=['ESP32-001']))
        self.assertEqual(latest.status_code, 200)
        self.assertEqual(latest.json()['map_version'], '1.0.0.0.2')
        self.assertEqual(latest.json()['device_id'], 'ESP32-001')

    def test_repeated_device_name_does_not_create_a_duplicate_device(self):
        Device.objects.create(device_id='ESP32-001', device_name='Fleet unit 1')

        response = self.client.post(
            reverse('telemetry-upload'),
            data=json.dumps({
                'device_id': 'ESP32-CHANGED',
                'device_name': 'fleet UNIT 1',
                'speed': 20,
                'latitude': -12.8,
                'longitude': 28.2,
                'has_fix': True,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Device.objects.count(), 1)
        self.assertEqual(TelemetryRecord.objects.select_related('device').get().device.device_id, 'ESP32-001')
    def test_patch_road_updates_name_and_nodes(self):
        road = Road.objects.create(name='Old Road', speed_limit=40)
        RoadNode.objects.create(road=road, sequence=1, latitude='1.0000000', longitude='2.0000000')
        RoadNode.objects.create(road=road, sequence=2, latitude='3.0000000', longitude='4.0000000')

        payload = {
            'name': 'Updated Road',
            'speed_limit': 60,
            'nodes': [
                {'latitude': '1.1000000', 'longitude': '2.2000000'},
                {'latitude': '3.1000000', 'longitude': '4.2000000'},
                {'latitude': '5.1000000', 'longitude': '6.2000000'},
            ],
        }

        response = self.client.patch(
            reverse('road-detail', args=[road.id]),
            data=json.dumps(payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        road.refresh_from_db()
        self.assertEqual(road.name, 'Updated Road')
        self.assertEqual(road.speed_limit, 60)
        self.assertEqual(road.nodes.count(), 3)
        self.assertEqual(list(road.nodes.values_list('sequence', flat=True)), [1, 2, 3])

    def test_map_check_update_for_unknown_device_requires_update(self):
        MapVersion.objects.create(version='1.0.0.0.3', description='latest', is_current=True)

        response = self.client.post(
            reverse('map-check-update'),
            data=json.dumps({'device_id': 'ESP32_NEW', 'current_version': '1.0.0.0.2'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            'update_required': True,
            'latest_version': '1.0.0.0.3',
            'current_version': '1.0.0.0.2',
        })

    def test_map_check_update_for_existing_device_is_up_to_date(self):
        MapVersion.objects.create(version='1.0.0.0.3', description='latest', is_current=True)

        response = self.client.post(
            reverse('map-check-update'),
            data=json.dumps({'device_id': 'ESP32_001', 'current_version': '1.0.0.0.3'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            'update_required': False,
            'latest_version': '1.0.0.0.3',
            'current_version': '1.0.0.0.3',
        })

    def test_map_check_update_requires_current_version(self):
        MapVersion.objects.create(version='1.0.0.0.3', description='latest', is_current=True)

        response = self.client.post(
            reverse('map-check-update'),
            data=json.dumps({'device_id': 'ESP32_NEW'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)

    def test_map_check_update_regenerates_map_files_for_latest_version(self):
        MapVersion.objects.create(version='1.0.0.0.3', description='latest', is_current=True)

        for filename in ['roads.json', 'hazards.json', 'version.json']:
            path = settings.MAPS_DIR / filename
            if path.exists():
                path.unlink()

        response = self.client.post(
            reverse('map-check-update'),
            data=json.dumps({'device_id': 'ESP32_NEW', 'current_version': '1.0.0.0.2'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['latest_version'], '1.0.0.0.3')
        self.assertTrue((settings.MAPS_DIR / 'version.json').exists())
        self.assertEqual(json.loads((settings.MAPS_DIR / 'version.json').read_text(encoding='utf-8'))['version'], '1.0.0.0.3')
