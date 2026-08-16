import json

from django.test import TestCase
from django.urls import reverse

from .models import Road, RoadNode


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
