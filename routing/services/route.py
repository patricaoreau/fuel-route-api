import hashlib

from django.conf import settings
from django.core.cache import cache

from routing.clients.openrouteservice import OpenRouteServiceClient


METERS_PER_MILE = 1609.344


def get_route(start, finish, *, client=None):
    key_source = (
        f'{settings.OPENROUTESERVICE_BASE_URL}:ors:v1:'
        f'{start["cache_key"]}:{start["coordinates"]}:'
        f'{finish["cache_key"]}:{finish["coordinates"]}:driving-car'
    )
    cache_key = 'route:' + hashlib.sha256(key_source.encode('utf-8')).hexdigest()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    client = client or OpenRouteServiceClient()
    provider_route = client.directions(start['coordinates'], finish['coordinates'])
    route = {
        'distance_miles': provider_route['distance_meters'] / METERS_PER_MILE,
        'duration_hours': provider_route['duration_seconds'] / 3600,
        'geometry': provider_route['geometry'],
        'bbox': provider_route.get('bbox'),
    }
    cache.set(cache_key, route, settings.ROUTE_CACHE_SECONDS)
    return route
