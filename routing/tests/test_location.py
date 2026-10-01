from django.test import SimpleTestCase, TestCase

from routing.exceptions import RequestValidationError
from routing.models import City
from routing.services.location import (
    normalize_name,
    normalize_state,
    resolve_location,
    suggest_locations,
)
from routing.services.planner import build_fuel_route_plan


class LocationNormalizationTests(SimpleTestCase):
    def test_normalize_name_collapses_whitespace_and_casefolds(self):
        cases = (
            ('  NEW   YORK  ', 'new york'),
            ('Fort\tWayne', 'fort wayne'),
            ('Straße', 'strasse'),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(normalize_name(value), expected)

    def test_normalize_state_accepts_codes_and_full_names_case_insensitively(self):
        cases = (
            ('ny', 'NY'),
            ('  New   York ', 'NY'),
            ('district OF columbia', 'DC'),
            ('not-a-state', None),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(normalize_state(value), expected)


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
        for query in ('NEW', 'NeW', '  nEw  '):
            with self.subTest(query=query):
                self.assertEqual(
                    [item['label'] for item in suggest_locations(query)],
                    expected,
                )

    def test_suggestions_filter_by_state_code_or_name(self):
        self.assertEqual(suggest_locations('New, NY')[0]['label'], 'New York, NY')
        self.assertEqual(suggest_locations('New, Lou')[0]['label'], 'New Orleans, LA')

    def test_suggestions_normalize_city_and_state_whitespace_and_case(self):
        suggestions = suggest_locations('  NeW   ,   lOu  ')
        self.assertEqual([item['label'] for item in suggestions], ['New Orleans, LA'])

    def test_suggestions_return_empty_for_invalid_or_unknown_queries(self):
        for query in (None, 42, '', ' ', 'N', 'Unknown'):
            with self.subTest(query=query):
                self.assertEqual(suggest_locations(query), [])

    def test_suggestions_respect_limit_and_use_one_query(self):
        with self.assertNumQueries(1):
            suggestions = suggest_locations('new', limit=2)
        self.assertEqual(
            [item['label'] for item in suggestions],
            ['New Orleans, LA', 'New York, NY'],
        )

    def test_suggestions_require_two_city_characters(self):
        self.assertEqual(suggest_locations('N'), [])
