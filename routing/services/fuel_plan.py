from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from routing.exceptions import DataCoverageError


MPG = Decimal('10')
MAX_RANGE_MILES = Decimal('500')
TANK_CAPACITY_GALLONS = MAX_RANGE_MILES / MPG
CENT = Decimal('0.01')


@dataclass(frozen=True)
class FuelPurchase:
    candidate: object
    gallons: Decimal
    cost: Decimal


def _decimal(value):
    return Decimal(str(value))


def optimize_fuel_plan(candidates, route_miles):
    destination_mile = _decimal(route_miles)
    if destination_mile <= 0:
        raise DataCoverageError('Route distance must be greater than zero.')
    if not candidates or _decimal(candidates[0].route_mile) != 0:
        raise DataCoverageError('No priced origin-area station is available.')

    current = candidates[0]
    current_fuel = Decimal('0')
    purchases = []
    visited_station_ids = set()

    while True:
        current_mile = _decimal(current.route_mile)
        if current.station.id in visited_station_ids:
            raise DataCoverageError('A feasible fuel-stop sequence could not be constructed.')
        visited_station_ids.add(current.station.id)

        reachable = [
            candidate
            for candidate in candidates
            if _decimal(candidate.route_mile) > current_mile
            and _decimal(candidate.route_mile) - current_mile <= MAX_RANGE_MILES
            and candidate.station.id not in visited_station_ids
        ]
        reachable.sort(key=lambda item: (_decimal(item.route_mile), item.station.id))
        destination_reachable = destination_mile - current_mile <= MAX_RANGE_MILES

        cheaper = next(
            (
                candidate for candidate in reachable
                if candidate.station.retail_price < current.station.retail_price
            ),
            None,
        )
        if cheaper is not None:
            target = cheaper
            desired_fuel = (_decimal(target.route_mile) - current_mile) / MPG
        elif destination_reachable:
            target = None
            desired_fuel = (destination_mile - current_mile) / MPG
        elif reachable:
            target = min(
                reachable,
                key=lambda item: (
                    item.station.retail_price,
                    _decimal(item.route_mile),
                    item.station.id,
                ),
            )
            desired_fuel = TANK_CAPACITY_GALLONS
        else:
            raise DataCoverageError(
                'Fuel-station coverage leaves a gap greater than the 500-mile vehicle range.'
            )

        gallons = max(Decimal('0'), desired_fuel - current_fuel)
        if gallons > TANK_CAPACITY_GALLONS + Decimal('0.000001'):
            raise DataCoverageError('The selected fuel plan exceeds tank capacity.')
        if gallons > Decimal('0.000001'):
            cost = (gallons * current.station.retail_price).quantize(CENT, rounding=ROUND_HALF_UP)
            purchases.append(FuelPurchase(current, gallons, cost))

        target_mile = destination_mile if target is None else _decimal(target.route_mile)
        current_fuel += gallons - (target_mile - current_mile) / MPG
        if current_fuel < Decimal('-0.000001'):
            raise DataCoverageError('The selected fuel plan runs out of fuel between stops.')
        current_fuel = max(Decimal('0'), current_fuel)

        if target is None:
            break
        current = target

    total_gallons = sum((purchase.gallons for purchase in purchases), Decimal('0'))
    expected_gallons = destination_mile / MPG
    if abs(total_gallons - expected_gallons) > Decimal('0.00001'):
        raise DataCoverageError('Fuel accounting did not reconcile with route distance.')

    return {
        'purchases': purchases,
        'total_gallons': total_gallons,
        'total_cost': sum((purchase.cost for purchase in purchases), Decimal('0')),
    }
