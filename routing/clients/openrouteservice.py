import logging
import math
import time

import httpx
from django.conf import settings

from routing.exceptions import (
    ProviderConfigurationError,
    ProviderResponseError,
    ProviderUnavailableError,
)


logger = logging.getLogger(__name__)


class OpenRouteServiceClient:
    profile = 'driving-car'

    def __init__(self, *, api_key=None, base_url=None, timeout=None, transport=None):
        self.api_key = api_key if api_key is not None else settings.OPENROUTESERVICE_API_KEY
        self.base_url = (base_url or settings.OPENROUTESERVICE_BASE_URL).rstrip('/')
        self.timeout = timeout or settings.OPENROUTESERVICE_TIMEOUT_SECONDS
        self.transport = transport

    def directions(self, start_coordinates, finish_coordinates):
        if not self.api_key:
            raise ProviderConfigurationError(
                'OPENROUTESERVICE_API_KEY is not configured.'
            )

        url = f'{self.base_url}/v2/directions/{self.profile}/geojson'
        started = time.monotonic()
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                response = client.post(
                    url,
                    headers={
                        'Authorization': self.api_key,
                        'Accept': 'application/geo+json, application/json',
                        'Content-Type': 'application/json',
                    },
                    json={
                        'coordinates': [start_coordinates, finish_coordinates],
                        'instructions': False,
                    },
                )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ProviderUnavailableError(
                'The routing provider is temporarily unavailable.'
            ) from exc
        finally:
            logger.info('routing_provider_request duration_ms=%.1f', (time.monotonic() - started) * 1000)

        if response.status_code in {401, 403, 429} or response.status_code >= 500:
            raise ProviderUnavailableError(
                'The routing provider rejected or could not complete the request.'
            )
        if response.status_code >= 400:
            raise ProviderResponseError('The routing provider could not route these locations.')

        try:
            payload = response.json()
            feature = payload['features'][0]
            geometry = feature['geometry']
            summary = feature['properties']['summary']
            coordinates = geometry['coordinates']
            distance_meters = float(summary['distance'])
            duration_seconds = float(summary['duration'])
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            raise ProviderResponseError(
                'The routing provider returned an invalid response.'
            ) from exc

        if (
            geometry.get('type') != 'LineString'
            or len(coordinates) < 2
            or any(
                not isinstance(point, list)
                or len(point) < 2
                or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in point[:2])
                or not -180 <= point[0] <= 180
                or not -90 <= point[1] <= 90
                for point in coordinates
            )
            or distance_meters <= 0
            or duration_seconds < 0
        ):
            raise ProviderResponseError('The routing provider returned an invalid route.')

        return {
            'geometry': {'type': 'LineString', 'coordinates': coordinates},
            'distance_meters': distance_meters,
            'duration_seconds': duration_seconds,
            'bbox': payload.get('bbox'),
        }
