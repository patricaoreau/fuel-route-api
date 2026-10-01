from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from routing.models import City, FuelStation
from routing.services.planner import build_fuel_route_plan


class PlannerIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        City.objects.bulk_create([
            City(name='Alpha', normalized_name='alpha', state_code='PA', state_name='Pennsylvania', latitude=40, longitude=-80),
            City(name='Beta', normalized_name='beta', state_code='OH', state_name='Ohio', latitude=40, longitude=-70),
        ])
        for index, (longitude, price) in enumerate(((-80, '4.000'), (-76, '3.000'), (-72, '3.500')), 1):
            FuelStation.objects.create(
                fingerprint=f'planner-{index}', opis_id=str(index), name=f'Station {index}',
                address=f'{index} Road', city='Alpha', state_code='PA', rack_id='',
                retail_price=Decimal(price), latitude=40, longitude=longitude,
            )

    @patch('routing.services.planner.get_route')
    def test_builds_serializable_end_to_end_plan(self, get_route):
        get_route.return_value = {
            'distance_miles': 700,
            'duration_hours': 10,
            'geometry': {'type': 'LineString', 'coordinates': [[-80, 40], [-70, 40]]},
            'bbox': [-80, 40, -70, 40],
        }
        result = build_fuel_route_plan('Alpha, PA', 'Beta, Ohio')
        self.assertEqual(result['total_gallons'], 70)
        self.assertEqual(sum(stop['cost'] for stop in result['fuel_stops']), result['total_fuel_cost'])
        self.assertEqual(result['route']['geometry']['type'], 'LineString')
        self.assertEqual(result['vehicle']['max_range_miles'], 500)
