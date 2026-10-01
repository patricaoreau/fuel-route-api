import json
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from routing.exceptions import ProviderUnavailableError
from routing.models import City, FuelStation


@override_settings(SECURE_SSL_REDIRECT=False, ROUTE_CACHE_SECONDS=60)
class FuelPlanApiIntegrationTests(TestCase):
    url = '/api/v1/routes/fuel-plan/'

    @classmethod
    def setUpTestData(cls):
        City.objects.bulk_create([
            City(
                name='Alpha', normalized_name='alpha', state_code='PA',
                state_name='Pennsylvania', latitude=40, longitude=-80,
            ),
            City(
                name='Beta', normalized_name='beta', state_code='OH',
                state_name='Ohio', latitude=40, longitude=-78.5,
            ),
        ])
        FuelStation.objects.create(
            fingerprint='api-integration-origin', opis_id='1', name='Origin Fuel',
            address='1 Main Street', city='Alpha', state_code='PA', rack_id='',
            retail_price=Decimal('3.000'), latitude=40, longitude=-80,
        )

    def setUp(self):
        cache.clear()

    def post_plan(self):
        return self.client.post(
            self.url,
            data=json.dumps({'start': 'Alpha, PA', 'finish': 'Beta, OH'}),
            content_type='application/json',
        )

    @staticmethod
    def provider_route(start, finish):
        return {
            'geometry': {'type': 'LineString', 'coordinates': [start, finish]},
            'distance_meters': 100 * 1609.344,
            'duration_seconds': 7200,
            'bbox': [-80, 40, -78.5, 40],
        }

    @patch('routing.clients.openrouteservice.OpenRouteServiceClient.directions')
    def test_short_route_succeeds(self, directions):
        directions.side_effect = self.provider_route
        response = self.post_plan()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['total_gallons'], 10)
        self.assertEqual(response.json()['total_fuel_cost'], 30)

    @patch('routing.clients.openrouteservice.OpenRouteServiceClient.directions')
    def test_cached_repeat_uses_one_provider_call(self, directions):
        directions.side_effect = self.provider_route
        self.assertEqual(self.post_plan().status_code, 200)
        self.assertEqual(self.post_plan().status_code, 200)
        self.assertEqual(directions.call_count, 1)

    @override_settings(OPENROUTESERVICE_API_KEY='')
    def test_missing_key_returns_service_unavailable(self):
        response = self.post_plan()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()['error']['code'],
            'routing_provider_not_configured',
        )

    @patch('routing.clients.openrouteservice.OpenRouteServiceClient.directions')
    def test_provider_timeout_returns_service_unavailable(self, directions):
        directions.side_effect = ProviderUnavailableError(
            'The routing provider is temporarily unavailable.'
        )
        response = self.post_plan()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()['error']['code'],
            'routing_provider_unavailable',
        )
