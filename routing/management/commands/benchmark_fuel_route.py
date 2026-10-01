import json
import math
import statistics
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext

from routing.services.location import resolve_location
from routing.services.route import get_route
from routing.services.stations import find_station_candidates
from routing.views import fuel_plan


class Command(BaseCommand):
    help = 'Benchmark station selection and cached fuel-plan API performance.'

    def add_arguments(self, parser):
        parser.add_argument('--start', default='Fort Smith, AR')
        parser.add_argument('--finish', default='Mount Jackson, VA')
        parser.add_argument('--iterations', type=int, default=10)

    def handle(self, *args, **options):
        iterations = options['iterations']
        if iterations < 2:
            raise CommandError('--iterations must be at least 2.')

        start = resolve_location(options['start'], 'start')
        finish = resolve_location(options['finish'], 'finish')

        warm_started = time.perf_counter()
        route = get_route(start, finish)
        warm_ms = (time.perf_counter() - warm_started) * 1000

        station_times = []
        station_query_counts = []
        for _ in range(iterations):
            with CaptureQueriesContext(connection) as queries:
                started = time.perf_counter()
                find_station_candidates(route)
                station_times.append((time.perf_counter() - started) * 1000)
            station_query_counts.append(len(queries))

        request = RequestFactory().post(
            '/api/v1/routes/fuel-plan/',
            data=json.dumps({
                'start': options['start'],
                'finish': options['finish'],
            }),
            content_type='application/json',
        )
        request_times = []
        request_query_counts = []
        for _ in range(iterations):
            with CaptureQueriesContext(connection) as queries:
                started = time.perf_counter()
                response = fuel_plan(request)
                request_times.append((time.perf_counter() - started) * 1000)
            request_query_counts.append(len(queries))
            if response.status_code != 200:
                raise CommandError(
                    f'Benchmark request returned HTTP {response.status_code}: '
                    f'{response.content.decode("utf-8")}'
                )

        station_p95 = self._percentile(station_times, 0.95)
        request_p95 = self._percentile(request_times, 0.95)
        station_passed = station_p95 < 250
        request_passed = request_p95 < 200
        query_passed = max(station_query_counts) == 1 and max(request_query_counts) == 3

        self.stdout.write(
            f'Route warm-up (provider/cache): {warm_ms:.2f} ms'
        )
        self.stdout.write(
            'Station selection: '
            f'median {statistics.median(station_times):.2f} ms, '
            f'p95 {station_p95:.2f} ms, '
            f'{max(station_query_counts)} query per run'
        )
        self.stdout.write(
            'Cached API view: '
            f'median {statistics.median(request_times):.2f} ms, '
            f'p95 {request_p95:.2f} ms, '
            f'{max(request_query_counts)} queries per request'
        )
        self.stdout.write(
            self.style.SUCCESS('PASS: station selection p95 is under 250 ms.')
            if station_passed
            else self.style.WARNING('MISS: station selection p95 is not under 250 ms.')
        )
        self.stdout.write(
            self.style.SUCCESS('PASS: cached API p95 is under 200 ms.')
            if request_passed
            else self.style.WARNING('MISS: cached API p95 is not under 200 ms.')
        )
        self.stdout.write(
            self.style.SUCCESS('PASS: query counts are constant; no N+1 queries detected.')
            if query_passed
            else self.style.WARNING('MISS: query counts differ from the expected 1/3 queries.')
        )

    @staticmethod
    def _percentile(values, percentile):
        ordered = sorted(values)
        index = max(0, math.ceil(len(ordered) * percentile) - 1)
        return ordered[index]
