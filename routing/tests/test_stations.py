from decimal import Decimal

from django.test import TestCase, override_settings

from routing.exceptions import DataCoverageError
from routing.models import FuelStation
from routing.services.stations import find_station_candidates


def station(opis_id, longitude, latitude, price='3.000'):
    return FuelStation.objects.create(
        fingerprint=f'fp-{opis_id}', opis_id=str(opis_id), name=f'Station {opis_id}',
        address='1 Road', city='City', state_code='PA', rack_id='',
        retail_price=Decimal(price), latitude=latitude, longitude=longitude,
    )


@override_settings(ROUTE_CORRIDOR_MILES=15, ORIGIN_STATION_WINDOW_MILES=25)
class StationCandidateTests(TestCase):
    def route(self):
        return {
            'distance_miles': 100,
            'geometry': {'type': 'LineString', 'coordinates': [[-80, 40], [-78.5, 40]]},
        }

    def test_filters_corridor_and_projects_route_mile(self):
        near_origin = station(1, -79.99, 40.01, '3.100')
        station(2, -79.25, 40.02, '3.200')
        station(3, -79.25, 41.0, '2.000')
        candidates = find_station_candidates(self.route())
        self.assertEqual(candidates[0].station.id, near_origin.id)
        self.assertEqual(candidates[0].route_mile, 0)
        self.assertEqual(len(candidates), 2)
        self.assertGreater(candidates[1].route_mile, 40)

    def test_keeps_cheapest_at_same_city_centroid(self):
        station(1, -79.99, 40, '3.500')
        cheap = station(2, -79.99, 40, '3.000')
        candidates = find_station_candidates(self.route())
        self.assertEqual(candidates[0].station.id, cheap.id)

    def test_requires_origin_area_station(self):
        station(1, -79, 40, '3.000')
        with self.assertRaises(DataCoverageError):
            find_station_candidates(self.route())

    def test_projects_station_on_north_south_route(self):
        origin = station(1, -80, 35.01, '3.000')
        middle = station(2, -79.99, 36, '3.100')
        route = {
            'distance_miles': 138,
            'geometry': {
                'type': 'LineString',
                'coordinates': [[-80, 35], [-80, 37]],
            },
        }
        candidates = find_station_candidates(route)
        self.assertEqual(candidates[0].station.id, origin.id)
        middle_candidate = next(item for item in candidates if item.station.id == middle.id)
        self.assertAlmostEqual(middle_candidate.route_mile, 69, delta=2)

    def test_handles_route_bend_and_repeated_coordinates(self):
        origin = station(1, -80, 40, '3.000')
        elbow = station(2, -79, 40.02, '3.100')
        route = {
            'distance_miles': 122,
            'geometry': {
                'type': 'LineString',
                'coordinates': [
                    [-80, 40], [-80, 40], [-79, 40], [-79, 41],
                ],
            },
        }
        candidates = find_station_candidates(route)
        self.assertEqual(candidates[0].station.id, origin.id)
        elbow_candidate = next(item for item in candidates if item.station.id == elbow.id)
        self.assertGreater(elbow_candidate.route_mile, 45)
        self.assertLess(elbow_candidate.route_mile, 75)
