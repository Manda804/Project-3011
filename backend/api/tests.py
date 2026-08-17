import json

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from .models import MapVersion, Road, RoadNode


class RoadUpdateTests(TestCase):
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
