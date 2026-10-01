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


@override_settings(SECURE_SSL_REDIRECT=False)
class DemoPageTests(TestCase):
    def test_demo_page_loads_api_workbench(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Fuel Route API')
        self.assertContains(response, '/api/v1/routes/fuel-plan/')
        self.assertContains(response, '/api/v1/locations/')


@override_settings(SECURE_SSL_REDIRECT=False)
class LocationSuggestionApiTests(TestCase):
    url = '/api/v1/locations/'

    @classmethod
    def setUpTestData(cls):
        from routing.models import City

        City.objects.bulk_create([
            City(
                name='Fort Smith', normalized_name='fort smith', state_code='AR',
                state_name='Arkansas', latitude=35.365, longitude=-94.411,
            ),
            City(
                name='Fort Wayne', normalized_name='fort wayne', state_code='IN',
                state_name='Indiana', latitude=41.079, longitude=-85.139,
            ),
        ])

    def test_returns_location_predictions(self):
        response = self.client.get(self.url, {'q': 'Fort S'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['suggestions'][0], {
            'label': 'Fort Smith, AR',
            'city': 'Fort Smith',
            'state': 'AR',
            'state_name': 'Arkansas',
            'coordinates': [-94.411, 35.365],
        })

    def test_prediction_query_is_case_insensitive(self):
        expected = self.client.get(self.url, {'q': 'fort s'}).json()
        self.assertEqual(self.client.get(self.url, {'q': 'FORT S'}).json(), expected)
        self.assertEqual(self.client.get(self.url, {'q': 'FoRt S'}).json(), expected)

    def test_short_query_returns_empty_list(self):
        response = self.client.get(self.url, {'q': 'F'})
        self.assertEqual(response.json(), {'suggestions': []})

    def test_rejects_long_query(self):
        response = self.client.get(self.url, {'q': 'x' * 121})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'validation_error')

    def test_rejects_post(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response['Allow'], 'GET')
