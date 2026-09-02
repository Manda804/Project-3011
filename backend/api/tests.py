import json
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from .models import Device, Hazard, MapVersion, Road, RoadNode, TelemetryRecord, Violation


class RoadUpdateTests(TestCase):
    def test_batch_upload_accepts_raw_array_and_isolates_bad_records(self):
        road = Road.objects.create(name='Cairo Road', speed_limit=60)
        payload = [
            {
                'device_id': 'ESP32-001',
                'speed': 80,
                'road_name': 'Cairo Road',
                'speed_limit': 60,
                'latitude': -12.8297,
                'longitude': 28.2001,
                'has_fix': True,
            },
            {'speed': 40, 'speed_limit': 60},
            {
                'device_id': 'ESP32-001',
                'speed': 50,
                'road_name': 'Cairo Road',
                'speed_limit': 60,
                'latitude': -12.8298,
                'longitude': 28.2002,
            },
        ]

        with patch('api.views._broadcast_telemetry') as broadcast:
            response = self.client.post(
                reverse('telemetry-batch-upload'),
                data=json.dumps(payload),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {
            'status': 'ok',
            'received': 3,
            'saved': 2,
            'violations': 1,
            'errors': 1,
            'device_id': 'ESP32-001',
        })
        self.assertEqual(TelemetryRecord.objects.filter(offline_log=True).count(), 2)
        self.assertEqual(Violation.objects.filter(device__device_id='ESP32-001').count(), 1)
        broadcast.assert_called_once()
        self.assertEqual(broadcast.call_args.args[0]['type'], 'offline_sync')
        self.assertEqual(broadcast.call_args.args[0]['record_count'], 2)
        self.assertEqual(broadcast.call_args.args[0]['device_id'], 'ESP32-001')
        self.assertTrue(Road.objects.filter(pk=road.id).exists())

    def test_batch_upload_accepts_records_wrapper_and_rejects_non_list(self):
        wrapped_response = self.client.post(
            reverse('telemetry-batch-upload'),
            data=json.dumps({'records': []}),
            content_type='application/json',
        )
        invalid_response = self.client.post(
            reverse('telemetry-batch-upload'),
            data=json.dumps({'records': {}}),
            content_type='application/json',
        )

        self.assertEqual(wrapped_response.status_code, 201)
        self.assertEqual(wrapped_response.json()['received'], 0)
        self.assertEqual(invalid_response.status_code, 400)

    def test_map_mutations_advance_version_and_regenerate_files(self):
        MapVersion.objects.create(version='1.0.0.0.2', is_current=True)
        road_response = self.client.post(
            reverse('road-list-create'),
            data=json.dumps({
                'name': 'Main Street',
                'speed_limit': 50,
                'nodes': [
                    {'latitude': '-12.8024', 'longitude': '28.2132'},
                    {'latitude': '-12.8030', 'longitude': '28.2140'},
                ],
            }),
            content_type='application/json',
        )

        self.assertEqual(road_response.status_code, 201)
        road = Road.objects.get(pk=road_response.json()['id'])
        self.assertEqual(MapVersion.objects.current().version, '1.0.0.0.3')
        self.assertEqual(json.loads((settings.MAPS_DIR / 'roads.json').read_text())['roads'][0]['id'], road.id)

        hazard_response = self.client.post(
            reverse('hazard-list-create'),
            data=json.dumps({
                'road': road.id,
                'hazard_type': Hazard.HAZARD_SCHOOL_ZONE,
                'latitude': '-12.8024',
                'longitude': '28.2132',
                'warning_distance': 50,
            }),
            content_type='application/json',
        )

        self.assertEqual(hazard_response.status_code, 201)
        self.assertEqual(MapVersion.objects.current().version, '1.0.0.0.4')
        self.assertEqual(json.loads((settings.MAPS_DIR / 'hazards.json').read_text())['hazards'][0]['type'], Hazard.HAZARD_SCHOOL_ZONE)

        patch_response = self.client.patch(
            reverse('road-detail', args=[road.id]),
            data=json.dumps({'speed_limit': 60}),
            content_type='application/json',
        )
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(MapVersion.objects.current().version, '1.0.0.0.5')

        delete_hazard_response = self.client.delete(reverse('hazard-detail', args=[hazard_response.json()['id']]))
        self.assertEqual(delete_hazard_response.status_code, 204)
        self.assertEqual(MapVersion.objects.current().version, '1.0.0.0.6')

        delete_road_response = self.client.delete(reverse('road-detail', args=[road.id]))
        self.assertEqual(delete_road_response.status_code, 204)
        self.assertEqual(MapVersion.objects.current().version, '1.0.0.0.7')

    def test_hazard_can_be_created_and_deleted(self):
        road = Road.objects.create(name='Main Street', speed_limit=50)
        create_response = self.client.post(
            reverse('hazard-list-create'),
            data=json.dumps({
                'road': road.id,
                'hazard_type': Hazard.HAZARD_SCHOOL_ZONE,
                'latitude': '-12.8024000',
                'longitude': '28.2132000',
                'warning_distance': 50,
            }),
            content_type='application/json',
        )

        self.assertEqual(create_response.status_code, 201)
        hazard_id = create_response.json()['id']
        self.assertTrue(Hazard.objects.filter(pk=hazard_id).exists())

        delete_response = self.client.delete(reverse('hazard-detail', args=[hazard_id]))

        self.assertEqual(delete_response.status_code, 204)
        self.assertFalse(Hazard.objects.filter(pk=hazard_id).exists())

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
