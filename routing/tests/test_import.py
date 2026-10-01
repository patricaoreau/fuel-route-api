import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from routing.models import City, FuelStation


CITIES = '''ID,STATE_CODE,STATE_NAME,CITY,COUNTY,LATITUDE,LONGITUDE
1,PA,Pennsylvania,Alpha,One,40.0,-80.0
2,PA,Pennsylvania,Alpha,Two,41.0,-81.0
3,ON,Ontario,Toronto,Toronto,43.6,-79.3
'''

FUEL = '''OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price
1,Alpha Fuel,1 Main St,Alpha,PA,10,3.500
1,Alpha Fuel,1 Main St,Alpha,PA,10,3.500
1,Alpha Fuel,1 Main St,Alpha,PA,10,3.400
2,Canada Fuel,2 Main St,Toronto,ON,20,3.000
3,Unknown Fuel,3 Main St,Missing,PA,30,3.000
4,Bad Fuel,4 Main St,Alpha,PA,40,invalid
'''


class ImportCommandTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.cities = root / 'cities.csv'
        self.fuel = root / 'fuel.csv'
        self.cities.write_text(CITIES, encoding='utf-8')
        self.fuel.write_text(FUEL, encoding='utf-8')

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_import(self):
        call_command('import_route_data', cities=str(self.cities), fuel=str(self.fuel), verbosity=0)

    def test_import_filters_and_reconciles_data(self):
        self.run_import()
        self.assertEqual(City.objects.count(), 1)
        self.assertEqual(FuelStation.objects.count(), 1)
        station = FuelStation.objects.get()
        self.assertEqual(str(station.retail_price), '3.400')
        self.assertEqual(station.latitude, 40.0)

    def test_import_is_idempotent(self):
        self.run_import()
        self.run_import()
        self.assertEqual(City.objects.count(), 1)
        self.assertEqual(FuelStation.objects.count(), 1)
