import csv
import hashlib
import math
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from routing.models import City, FuelStation
from routing.services.location import STATE_NAMES, normalize_name


def clean(value):
    return ' '.join((value or '').strip().split())


class Command(BaseCommand):
    help = 'Import US cities and supplied fuel prices into normalized database tables.'

    def add_arguments(self, parser):
        parser.add_argument('--cities', default='data/us_cities.csv')
        parser.add_argument('--fuel', default='data/fuel-prices.csv')

    def handle(self, *args, **options):
        cities_path = Path(options['cities'])
        fuel_path = Path(options['fuel'])
        if not cities_path.is_file():
            raise CommandError(f'City data file does not exist: {cities_path}')
        if not fuel_path.is_file():
            raise CommandError(f'Fuel data file does not exist: {fuel_path}')

        with transaction.atomic():
            city_records, city_stats = self._import_cities(cities_path)
            fuel_stats = self._import_fuel(fuel_path, city_records)

        self.stdout.write(self.style.SUCCESS(
            'Cities: {created} created, {updated} updated, {duplicates} duplicate rows skipped, '
            '{invalid} invalid/non-US rows skipped.'.format(**city_stats)
        ))
        self.stdout.write(self.style.SUCCESS(
            'Fuel stations: {created} created, {updated} updated, {duplicates} duplicate rows '
            'collapsed, {conflicts} conflicting duplicates reconciled, {non_us} non-US, '
            '{unmatched} unmatched, {invalid} invalid rows skipped.'.format(**fuel_stats)
        ))

    def _import_cities(self, path):
        records = {}
        invalid = 0
        duplicates = 0
        with path.open(encoding='utf-8-sig', newline='') as source:
            for row in csv.DictReader(source):
                state_code = clean(row.get('STATE_CODE')).upper()
                name = clean(row.get('CITY'))
                try:
                    latitude = float(row.get('LATITUDE', ''))
                    longitude = float(row.get('LONGITUDE', ''))
                except (TypeError, ValueError):
                    invalid += 1
                    continue
                if (
                    state_code not in STATE_NAMES
                    or not name
                    or not math.isfinite(latitude)
                    or not math.isfinite(longitude)
                    or not -90 <= latitude <= 90
                    or not -180 <= longitude <= 180
                ):
                    invalid += 1
                    continue
                key = (normalize_name(name), state_code)
                if key in records:
                    duplicates += 1
                    continue
                records[key] = {
                    'name': name,
                    'normalized_name': key[0],
                    'state_code': state_code,
                    'state_name': clean(row.get('STATE_NAME')) or STATE_NAMES[state_code],
                    'latitude': latitude,
                    'longitude': longitude,
                }

        existing = {
            (city.normalized_name, city.state_code): city
            for city in City.objects.all()
        }
        to_create = []
        to_update = []
        for key, values in records.items():
            city = existing.get(key)
            if city is None:
                to_create.append(City(**values))
                continue
            changed = False
            for field, value in values.items():
                if getattr(city, field) != value:
                    setattr(city, field, value)
                    changed = True
            if changed:
                to_update.append(city)
        City.objects.bulk_create(to_create, batch_size=1000)
        if to_update:
            City.objects.bulk_update(
                to_update,
                ('name', 'normalized_name', 'state_code', 'state_name', 'latitude', 'longitude'),
                batch_size=1000,
            )
        return records, {
            'created': len(to_create),
            'updated': len(to_update),
            'duplicates': duplicates,
            'invalid': invalid,
        }

    def _import_fuel(self, path, city_records):
        records = {}
        record_rows = {}
        stats = {
            'created': 0,
            'updated': 0,
            'duplicates': 0,
            'conflicts': 0,
            'non_us': 0,
            'unmatched': 0,
            'invalid': 0,
        }
        with path.open(encoding='utf-8-sig', newline='') as source:
            for row in csv.DictReader(source):
                state_code = clean(row.get('State')).upper()
                if state_code not in STATE_NAMES:
                    stats['non_us'] += 1
                    continue
                city_name = clean(row.get('City'))
                city_record = city_records.get((normalize_name(city_name), state_code))
                if city_record is None:
                    stats['unmatched'] += 1
                    continue
                try:
                    price = Decimal(clean(row.get('Retail Price'))).quantize(Decimal('0.001'))
                except (InvalidOperation, TypeError):
                    stats['invalid'] += 1
                    continue
                name = clean(row.get('Truckstop Name'))
                address = clean(row.get('Address'))
                opis_id = clean(row.get('OPIS Truckstop ID'))
                rack_id = clean(row.get('Rack ID'))
                if not all((name, address, opis_id)) or price <= 0 or price > 20:
                    stats['invalid'] += 1
                    continue

                identity = '|'.join((
                    opis_id.casefold(), normalize_name(name), normalize_name(address),
                    normalize_name(city_name), state_code, rack_id.casefold(),
                ))
                fingerprint = hashlib.sha256(identity.encode('utf-8')).hexdigest()
                values = {
                    'fingerprint': fingerprint,
                    'opis_id': opis_id,
                    'name': name,
                    'address': address,
                    'city': city_name,
                    'state_code': state_code,
                    'rack_id': rack_id,
                    'retail_price': price,
                    'latitude': city_record['latitude'],
                    'longitude': city_record['longitude'],
                    'location_accuracy': 'city_centroid',
                }
                if fingerprint in records:
                    if record_rows[fingerprint] == values:
                        stats['duplicates'] += 1
                    else:
                        stats['conflicts'] += 1
                    # Use the cheapest supplied price for identical station identity.
                    if price < records[fingerprint]['retail_price']:
                        records[fingerprint] = values
                    continue
                records[fingerprint] = values
                record_rows[fingerprint] = values.copy()

        existing = {
            station.fingerprint: station
            for station in FuelStation.objects.all()
        }
        to_create = []
        to_update = []
        update_fields = (
            'opis_id', 'name', 'address', 'city', 'state_code', 'rack_id',
            'retail_price', 'latitude', 'longitude', 'location_accuracy',
        )
        for fingerprint, values in records.items():
            station = existing.get(fingerprint)
            if station is None:
                to_create.append(FuelStation(**values))
                continue
            changed = False
            for field in update_fields:
                value = values[field]
                if getattr(station, field) != value:
                    setattr(station, field, value)
                    changed = True
            if changed:
                to_update.append(station)
        FuelStation.objects.bulk_create(to_create, batch_size=1000)
        if to_update:
            FuelStation.objects.bulk_update(to_update, update_fields, batch_size=1000)
        stats['created'] = len(to_create)
        stats['updated'] = len(to_update)
        return stats
