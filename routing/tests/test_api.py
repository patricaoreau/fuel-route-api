from unittest.mock import patch

from django.test import TestCase, override_settings

from routing.exceptions import DataCoverageError


@override_settings(SECURE_SSL_REDIRECT=False)
class FuelPlanApiTests(TestCase):
    url = '/api/v1/routes/fuel-plan/'

    def test_rejects_get(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response['Allow'], 'POST')

    def test_requires_json_content_type(self):
        response = self.client.post(self.url, data='{}', content_type='text/plain')
        self.assertEqual(response.status_code, 415)

    def test_rejects_invalid_json(self):
        response = self.client.post(self.url, data='{', content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'validation_error')

    def test_rejects_oversized_request(self):
        response = self.client.post(
            self.url,
            data='{"start":"' + ('x' * 10_001) + '"}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()['error']['code'], 'request_too_large')

    @patch('routing.views.build_fuel_route_plan')
    def test_returns_completed_plan(self, build_plan):
        build_plan.return_value = {'total_fuel_cost': 42.50, 'fuel_stops': []}
        response = self.client.post(
            self.url,
            data={'start': 'A, PA', 'finish': 'B, OH'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['total_fuel_cost'], 42.5)

    @patch('routing.views.build_fuel_route_plan')
    def test_returns_data_coverage_error(self, build_plan):
        build_plan.side_effect = DataCoverageError('No feasible chain.')
        response = self.client.post(
            self.url,
            data={'start': 'A, PA', 'finish': 'B, OH'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['error']['code'], 'insufficient_fuel_data')
