import httpx
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from routing.clients.openrouteservice import OpenRouteServiceClient
from routing.exceptions import ProviderResponseError, ProviderUnavailableError
from routing.services.route import get_route


class ProviderClientTests(SimpleTestCase):
    def test_parses_geojson_and_sends_longitude_latitude_coordinates(self):
        captured = {}

        def handler(request):
            captured['request'] = request
            return httpx.Response(200, json={
                'features': [{
                    'geometry': {'type': 'LineString', 'coordinates': [[-1, 1], [-2, 2]]},
                    'properties': {'summary': {'distance': 1609.344, 'duration': 3600}},
                }],
            })

        client = OpenRouteServiceClient(
            api_key='test-key', base_url='https://example.test',
            transport=httpx.MockTransport(handler),
        )
        result = client.directions([-1, 1], [-2, 2])
        self.assertEqual(result['distance_meters'], 1609.344)
        self.assertIn(b'"coordinates":[[-1,1],[-2,2]]', captured['request'].content)
        self.assertEqual(captured['request'].headers['Authorization'], 'test-key')

    def test_rejects_malformed_provider_response(self):
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={'features': []}))
        client = OpenRouteServiceClient(api_key='key', transport=transport)
        with self.assertRaises(ProviderResponseError):
            client.directions([0, 0], [1, 1])

    def test_rejects_invalid_geometry_coordinate(self):
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
            'features': [{
                'geometry': {'type': 'LineString', 'coordinates': [[0, 0], ['bad', 1]]},
                'properties': {'summary': {'distance': 1, 'duration': 1}},
            }],
        }))
        client = OpenRouteServiceClient(api_key='key', transport=transport)
        with self.assertRaises(ProviderResponseError):
            client.directions([0, 0], [1, 1])

    def test_translates_quota_failure(self):
        transport = httpx.MockTransport(lambda request: httpx.Response(429))
        client = OpenRouteServiceClient(api_key='key', transport=transport)
        with self.assertRaises(ProviderUnavailableError):
            client.directions([0, 0], [1, 1])


@override_settings(ROUTE_CACHE_SECONDS=60)
class RouteCacheTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_route_is_cached_and_units_are_converted(self):
        class FakeClient:
            calls = 0

            def directions(self, start, finish):
                self.calls += 1
                return {
                    'geometry': {'type': 'LineString', 'coordinates': [start, finish]},
                    'distance_meters': 1609.344,
                    'duration_seconds': 3600,
                    'bbox': None,
                }

        client = FakeClient()
        start = {'coordinates': [0, 0], 'cache_key': 'a'}
        finish = {'coordinates': [1, 1], 'cache_key': 'b'}
        first = get_route(start, finish, client=client)
        second = get_route(start, finish, client=client)
        self.assertEqual(client.calls, 1)
        self.assertEqual(first, second)
        self.assertEqual(first['distance_miles'], 1)
        self.assertEqual(first['duration_hours'], 1)
