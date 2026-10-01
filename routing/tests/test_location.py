from django.test import TestCase

from routing.exceptions import RequestValidationError
from routing.models import City
from routing.services.location import resolve_location, suggest_locations
from routing.services.planner import build_fuel_route_plan


class LocationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        City.objects.bulk_create([
            City(
                name='New York', normalized_name='new york', state_code='NY',
                state_name='New York', latitude=40.7128, longitude=-74.006,
            ),
            City(
                name='New Orleans', normalized_name='new orleans', state_code='LA',
                state_name='Louisiana', latitude=29.9511, longitude=-90.0715,
            ),
            City(
                name='Newark', normalized_name='newark', state_code='NJ',
                state_name='New Jersey', latitude=40.7357, longitude=-74.1724,
            ),
        ])

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

    def test_suggests_city_prefix_in_stable_order(self):
        suggestions = suggest_locations('new')
        self.assertEqual(
            [item['label'] for item in suggestions],
            ['New Orleans, LA', 'New York, NY', 'Newark, NJ'],
        )

    def test_suggestions_compare_city_names_case_insensitively(self):
        expected = [item['label'] for item in suggest_locations('new')]
        self.assertEqual(
            [item['label'] for item in suggest_locations('NEW')],
            expected,
        )
        self.assertEqual(
            [item['label'] for item in suggest_locations('NeW')],
            expected,
        )

    def test_suggestions_filter_by_state_code_or_name(self):
        self.assertEqual(suggest_locations('New, NY')[0]['label'], 'New York, NY')
        self.assertEqual(suggest_locations('New, Lou')[0]['label'], 'New Orleans, LA')

    def test_suggestions_require_two_city_characters(self):
        self.assertEqual(suggest_locations('N'), [])
