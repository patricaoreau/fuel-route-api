from dataclasses import dataclass, replace
from math import asin, cos, floor, radians, sin, sqrt

from django.conf import settings

from routing.exceptions import DataCoverageError
from routing.models import FuelStation


EARTH_RADIUS_MILES = 3958.7613
SEGMENT_GRID_DEGREES = 0.25


@dataclass(frozen=True)
class StationCandidate:
    station: FuelStation
    route_mile: float
    projected_route_mile: float
    detour_miles: float


def haversine_miles(first, second):
    lon1, lat1 = first
    lon2, lat2 = second
    lat_delta = radians(lat2 - lat1)
    lon_delta = radians(lon2 - lon1)
    a = (
        sin(lat_delta / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(lon_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * asin(min(1, sqrt(a)))


def _sample_route(coordinates, interval_miles=5):
    sampled = [(coordinates[0], 0.0)]
    cumulative = 0.0
    last_kept_distance = 0.0
    for index in range(1, len(coordinates)):
        cumulative += haversine_miles(coordinates[index - 1], coordinates[index])
        is_last = index == len(coordinates) - 1
        if is_last or cumulative - last_kept_distance >= interval_miles:
            if coordinates[index] != sampled[-1][0]:
                sampled.append((coordinates[index], cumulative))
                last_kept_distance = cumulative
    if len(sampled) < 2:
        raise DataCoverageError('The returned route geometry is too short to analyze.')
    return sampled, cumulative


def _project_to_segment(point, start, end):
    ref_lat = radians((start[1] + end[1] + point[1]) / 3)
    x_scale = 69.172 * max(0.01, cos(ref_lat))
    y_scale = 69.0
    segment_x = (end[0] - start[0]) * x_scale
    segment_y = (end[1] - start[1]) * y_scale
    point_x = (point[0] - start[0]) * x_scale
    point_y = (point[1] - start[1]) * y_scale
    length_squared = segment_x * segment_x + segment_y * segment_y
    if length_squared == 0:
        return 0.0, sqrt(point_x * point_x + point_y * point_y)
    fraction = max(0.0, min(1.0, (point_x * segment_x + point_y * segment_y) / length_squared))
    delta_x = point_x - fraction * segment_x
    delta_y = point_y - fraction * segment_y
    return fraction, sqrt(delta_x * delta_x + delta_y * delta_y)


def _grid_cell(longitude, latitude):
    return (
        floor(longitude / SEGMENT_GRID_DEGREES),
        floor(latitude / SEGMENT_GRID_DEGREES),
    )


def _build_segment_grid(sampled, corridor_miles):
    grid = {}
    latitude_buffer = corridor_miles / 69.0
    for index in range(1, len(sampled)):
        start = sampled[index - 1][0]
        end = sampled[index][0]
        min_abs_cos = max(
            0.15,
            min(abs(cos(radians(start[1]))), abs(cos(radians(end[1])))),
        )
        longitude_buffer = corridor_miles / (69.172 * min_abs_cos)
        min_lon_cell, min_lat_cell = _grid_cell(
            min(start[0], end[0]) - longitude_buffer,
            min(start[1], end[1]) - latitude_buffer,
        )
        max_lon_cell, max_lat_cell = _grid_cell(
            max(start[0], end[0]) + longitude_buffer,
            max(start[1], end[1]) + latitude_buffer,
        )
        for lon_cell in range(min_lon_cell, max_lon_cell + 1):
            for lat_cell in range(min_lat_cell, max_lat_cell + 1):
                grid.setdefault((lon_cell, lat_cell), []).append(index)
    return grid


def _station_projection(
    station,
    sampled,
    segment_indices,
    geometry_miles,
    provider_miles,
):
    point = (station.longitude, station.latitude)
    best_distance = float('inf')
    best_mile = 0.0
    for index in segment_indices:
        start, start_mile = sampled[index - 1]
        end, end_mile = sampled[index]
        fraction, distance = _project_to_segment(point, start, end)
        if distance < best_distance:
            best_distance = distance
            best_mile = start_mile + fraction * (end_mile - start_mile)
    scale = provider_miles / geometry_miles if geometry_miles > 0 else 1
    return best_mile * scale, best_distance


def find_station_candidates(route):
    coordinates = route['geometry']['coordinates']
    sampled, geometry_miles = _sample_route(coordinates)
    corridor = settings.ROUTE_CORRIDOR_MILES
    segment_grid = _build_segment_grid(sampled, corridor)

    latitudes = [point[1] for point in coordinates]
    longitudes = [point[0] for point in coordinates]
    latitude_buffer = corridor / 69.0
    min_abs_cos = max(
        0.15,
        min(abs(cos(radians(min(latitudes)))), abs(cos(radians(max(latitudes))))),
    )
    longitude_buffer = corridor / (69.172 * min_abs_cos)
    stations = FuelStation.objects.filter(
        latitude__gte=min(latitudes) - latitude_buffer,
        latitude__lte=max(latitudes) + latitude_buffer,
        longitude__gte=min(longitudes) - longitude_buffer,
        longitude__lte=max(longitudes) + longitude_buffer,
    ).only(
        'id', 'opis_id', 'name', 'address', 'city', 'state_code',
        'retail_price', 'latitude', 'longitude', 'location_accuracy',
    )

    candidates = []
    for station in stations:
        segment_indices = segment_grid.get(
            _grid_cell(station.longitude, station.latitude)
        )
        if not segment_indices:
            continue
        route_mile, detour_miles = _station_projection(
            station,
            sampled,
            segment_indices,
            geometry_miles,
            route['distance_miles'],
        )
        if detour_miles <= corridor:
            candidates.append(
                StationCandidate(
                    station=station,
                    route_mile=route_mile,
                    projected_route_mile=route_mile,
                    detour_miles=detour_miles,
                )
            )

    if not candidates:
        raise DataCoverageError('No priced fuel stations were found near this route.')

    # Several supplied stations share the same city-centroid coordinate. Keep the
    # cheapest option at an effectively identical route position.
    best_by_position = {}
    for candidate in candidates:
        key = (
            round(candidate.projected_route_mile, 1),
            round(candidate.station.latitude, 4),
            round(candidate.station.longitude, 4),
        )
        existing = best_by_position.get(key)
        ordering = (candidate.station.retail_price, candidate.station.id)
        if existing is None or ordering < (existing.station.retail_price, existing.station.id):
            best_by_position[key] = candidate
    candidates = sorted(
        best_by_position.values(),
        key=lambda item: (item.route_mile, item.station.retail_price, item.station.id),
    )

    origin_options = [
        candidate
        for candidate in candidates
        if candidate.projected_route_mile <= settings.ORIGIN_STATION_WINDOW_MILES
    ]
    if not origin_options:
        raise DataCoverageError(
            'No priced fuel station was found near the start of this route.'
        )
    origin = min(
        origin_options,
        key=lambda item: (item.station.retail_price, item.detour_miles, item.station.id),
    )
    origin = replace(origin, route_mile=0.0)
    remaining = [
        candidate
        for candidate in candidates
        if candidate.station.id != origin.station.id and candidate.route_mile > 0.1
    ]
    return [origin, *remaining]
