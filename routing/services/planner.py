from decimal import Decimal, ROUND_HALF_UP

from routing.exceptions import RequestValidationError
from routing.services.fuel_plan import optimize_fuel_plan
from routing.services.location import resolve_location
from routing.services.route import get_route
from routing.services.stations import find_station_candidates


TWO_PLACES = Decimal('0.01')


def _round(value, places=2):
    return round(float(value), places)


def build_fuel_route_plan(start_value, finish_value, *, client=None):
    start = resolve_location(start_value, 'start')
    finish = resolve_location(finish_value, 'finish')
    if start['cache_key'] == finish['cache_key']:
        raise RequestValidationError(
            'Start and finish must be different locations.',
            fields={'finish': 'Choose a different destination.'},
        )
    route = get_route(start, finish, client=client)
    candidates = find_station_candidates(route)
    plan = optimize_fuel_plan(candidates, route['distance_miles'])

    stops = []
    for purchase in plan['purchases']:
        candidate = purchase.candidate
        station = candidate.station
        stops.append({
            'station_id': station.opis_id,
            'name': station.name,
            'address': station.address,
            'city': station.city,
            'state': station.state_code,
            'coordinates': [station.longitude, station.latitude],
            'location_accuracy': station.location_accuracy,
            'price_per_gallon': float(station.retail_price),
            'route_mile': _round(candidate.projected_route_mile, 1),
            'estimated_detour_miles': _round(candidate.detour_miles, 1),
            'gallons': float(purchase.gallons.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)),
            'cost': float(purchase.cost),
        })

    return {
        'start': {key: start[key] for key in ('label', 'coordinates')},
        'finish': {key: finish[key] for key in ('label', 'coordinates')},
        'route': {
            'distance_miles': _round(route['distance_miles'], 1),
            'duration_hours': _round(route['duration_hours'], 1),
            'geometry': route['geometry'],
        },
        'vehicle': {
            'mpg': 10,
            'max_range_miles': 500,
            'tank_capacity_gallons': 50,
        },
        'fuel_stops': stops,
        'total_gallons': float(plan['total_gallons'].quantize(TWO_PLACES, rounding=ROUND_HALF_UP)),
        'total_fuel_cost': float(plan['total_cost']),
        'currency': 'USD',
        'attribution': 'Routing data from openrouteservice and OpenStreetMap contributors.',
        'assumptions': [
            'Fuel prices are the supplied snapshot and are treated as USD per gallon.',
            'Station coordinates are approximate city centroids.',
            'Station detours are estimated and are not included in route distance or fuel cost.',
            'The initial origin-area fill is included and arrival reserve is zero gallons.',
        ],
    }
