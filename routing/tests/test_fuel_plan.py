from decimal import Decimal
import random
from types import SimpleNamespace

from django.test import SimpleTestCase

from routing.exceptions import DataCoverageError
from routing.services.fuel_plan import optimize_fuel_plan
from routing.services.stations import StationCandidate


def candidate(station_id, mile, price):
    station = SimpleNamespace(id=station_id, retail_price=Decimal(price))
    return StationCandidate(station, mile, mile, 1)


class FuelPlanTests(SimpleTestCase):
    def test_short_route_buys_all_trip_fuel_at_origin(self):
        plan = optimize_fuel_plan([candidate(1, 0, '3.000')], 120)
        self.assertEqual(plan['total_gallons'], Decimal('12.0'))
        self.assertEqual(plan['total_cost'], Decimal('36.00'))

    def test_uses_first_cheaper_station_and_reconciles_gallons(self):
        plan = optimize_fuel_plan([
            candidate(1, 0, '4.000'),
            candidate(2, 400, '3.000'),
            candidate(3, 700, '4.500'),
        ], 900)
        self.assertEqual([item.candidate.station.id for item in plan['purchases']], [1, 2])
        self.assertEqual(plan['total_gallons'], Decimal('90.0'))
        self.assertEqual(plan['total_cost'], Decimal('310.00'))

    def test_exact_500_mile_route_is_feasible(self):
        plan = optimize_fuel_plan([candidate(1, 0, '3.000')], 500)
        self.assertEqual(plan['total_gallons'], Decimal('50'))

    def test_reports_gap_beyond_vehicle_range(self):
        with self.assertRaises(DataCoverageError):
            optimize_fuel_plan([candidate(1, 0, '3.000')], 501)

    def test_equal_price_tie_is_deterministic(self):
        plan = optimize_fuel_plan([
            candidate(1, 0, '3.000'),
            candidate(3, 450, '3.000'),
            candidate(2, 450, '3.000'),
        ], 800)
        self.assertEqual(plan['purchases'][1].candidate.station.id, 2)

    def test_buys_required_fuel_across_expensive_gap(self):
        plan = optimize_fuel_plan([
            candidate(1, 0, '2.000'),
            candidate(2, 450, '5.000'),
        ], 900)
        self.assertEqual([item.gallons for item in plan['purchases']], [Decimal('50'), Decimal('40')])
        self.assertEqual(plan['total_cost'], Decimal('300.00'))

    def test_rounds_itemized_cost_to_cents(self):
        plan = optimize_fuel_plan([candidate(1, 0, '3.333')], 123.45)
        self.assertEqual(plan['total_gallons'], Decimal('12.345'))
        self.assertEqual(plan['purchases'][0].cost, Decimal('41.15'))
        self.assertEqual(plan['total_cost'], Decimal('41.15'))

    def test_greedy_cost_matches_discrete_dynamic_programming_oracle(self):
        randomizer = random.Random(20260930)
        for case_number in range(50):
            destination = randomizer.choice((600, 700, 800, 900, 1000))
            prices = [Decimal(randomizer.randint(2, 6)) for _ in range(destination // 100)]
            candidates = [
                candidate(index + 1, index * 100, str(price))
                for index, price in enumerate(prices)
            ]
            greedy = optimize_fuel_plan(candidates, destination)['total_cost']
            oracle = self._oracle_cost(prices, destination // 100)
            self.assertEqual(greedy, oracle, f'randomized case {case_number}')

    @staticmethod
    def _oracle_cost(prices, destination_units):
        # One unit is 100 miles / 10 MPG = 10 gallons; capacity is five units.
        infinity = Decimal('Infinity')
        states = {(0, 0): Decimal('0')}
        for position in range(destination_units):
            next_states = {}
            for (state_position, fuel), cost in list(states.items()):
                if state_position != position:
                    continue
                for bought in range(6 - fuel):
                    available = fuel + bought
                    purchase_cost = cost + prices[position] * bought * 10
                    for travel in range(1, available + 1):
                        target = position + travel
                        if target > destination_units:
                            break
                        key = (target, available - travel)
                        next_states[key] = min(next_states.get(key, infinity), purchase_cost)
            states.update(next_states)
        return states[(destination_units, 0)].quantize(Decimal('0.01'))
