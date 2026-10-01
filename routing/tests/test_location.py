from django.test import TestCase

from routing.exceptions import RequestValidationError
from routing.models import City
from routing.services.location import resolve_location
from routing.services.planner import build_fuel_route_plan


class LocationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        City.objects.create(
            name='New York', normalized_name='new york', state_code='NY',
            state_name='New York', latitude=40.7128, longitude=-74.006,
        )

    def test_resolves_state_code_case_insensitively(self):
        result = resolve_location('  New York, ny ', 'start')
        self.assertEqual(result['label'], 'New York, NY')
        self.assertEqual(result['coordinates'], [-74.006, 40.7128])

    def test_resolves_full_state_name(self):
        self.assertEqual(resolve_location('New York, New York', 'start')['cache_key'], 'NY:new york')

    def test_rejects_unknown_location(self):
        with self.assertRaises(RequestValidationError) as context:
            resolve_location('Nowhere, NY', 'start')
        self.assertIn('start', context.exception.fields)

    def test_rejects_malformed_location(self):
        with self.assertRaises(RequestValidationError):
            resolve_location('New York', 'start')

    def test_rejects_same_start_and_finish_before_routing(self):
        with self.assertRaises(RequestValidationError):
            build_fuel_route_plan('New York, NY', 'New York, New York')
