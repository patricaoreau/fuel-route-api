# Fuel Route API Completion Plan

## 1. Goal and Definition of Done

Build a Django JSON API that accepts a start and destination in the United States and returns:

- a drivable route as GeoJSON;
- route distance and estimated duration;
- cost-effective fuel stops that keep every leg within the vehicle's 500-mile range;
- gallons purchased and cost at each stop;
- total fuel purchased and total estimated fuel cost, using 10 MPG;
- clear validation and upstream-service errors.

The project is complete when a fresh clone can be configured from documented steps, import the supplied fuel data, serve the endpoint, pass its automated tests, make no more than one routing-provider request per cache miss, and support a short Postman/Loom demonstration.

## 2. Current Project State

The repository is an early Django skeleton, not a functioning API yet.

- Django 6.1.1 and Python 3.12.10 are present in the local virtual environment.
- `routing` exists but is not in `INSTALLED_APPS` and has no URL configuration.
- Views, models, admin, and tests are empty placeholders.
- There is no dependency manifest, environment example, API client, import command, schema, migration, or project setup documentation.
- `data/fuel-prices.csv` contains 8,151 rows and 6,738 distinct OPIS station IDs. It also contains Canadian provinces, duplicate IDs, and conflicting duplicate records.
- `data/us_cities.csv` contains 29,880 city coordinate rows. Exact normalized city/state matching supplies approximate coordinates for 7,516 of the 8,151 fuel rows (about 92%).
- The current Django system check passes only because the routing app has not been connected.

## 3. Product and Technical Decisions

### Endpoint

Implement `POST /api/v1/routes/fuel-plan/` with this request body:

```json
{
  "start": "New York, NY",
  "finish": "Los Angeles, CA"
}
```

For the first version, accept `City, ST` or `City, State` strings that resolve uniquely through the supplied US cities dataset. Normalize case and whitespace. Return `400` for malformed, unknown, non-US, or ambiguous locations and include a useful field-level error. Coordinates can be added as a backward-compatible enhancement later, but are not required for the assignment.

Return a stable response shape similar to:

```json
{
  "start": {"label": "New York, NY", "coordinates": [-74.006, 40.7128]},
  "finish": {"label": "Los Angeles, CA", "coordinates": [-118.2437, 34.0522]},
  "route": {
    "distance_miles": 2790.4,
    "duration_hours": 41.8,
    "geometry": {"type": "LineString", "coordinates": []}
  },
  "vehicle": {"mpg": 10, "max_range_miles": 500, "tank_capacity_gallons": 50},
  "fuel_stops": [],
  "total_gallons": 279.04,
  "total_fuel_cost": 925.31,
  "currency": "USD",
  "assumptions": []
}
```

Round display values only at serialization time; retain full precision during selection and cost calculation.

### Routing provider

Use openrouteservice with the `driving-car` directions GeoJSON endpoint. Its GeoJSON response provides the route `LineString`, distance, and duration in a single call. Store the API key in `OPENROUTESERVICE_API_KEY`; never commit it. Put provider access behind a small client interface so tests can use fixtures and another provider can replace it later.

The request path must make one directions call on a cache miss and zero on a cache hit. Start and finish geocoding will use the local US cities dataset, avoiding two additional external requests. Configure connect/read timeouts and translate authentication, quota, timeout, and invalid-response failures into consistent `502` or `503` API responses without exposing secrets.

Reference: [openrouteservice directions request and GeoJSON response](https://giscience.github.io/openrouteservice/v9.10.0/api-reference/endpoints/directions/requests-and-return-types).

### Fuel and cost assumptions

- Fixed fuel economy: 10 MPG.
- Effective tank capacity: `500 / 10 = 50` gallons.
- Treat the supplied retail prices as USD per gallon.
- Recommend stations within a configurable corridor of the returned route (start with 15 miles).
- Station coordinates derived from city centroids are approximate. Expose this as `location_accuracy: "city_centroid"`; do not imply turn-by-turn precision.
- Include an origin-area station as the initial fill and include that fill in the trip total. The plan starts with only enough fuel to reach the selected origin-area station; after that, the optimizer buys only the amount needed by its selected strategy and targets arrival with zero remaining trip fuel. This makes the reported total represent all fuel consumed by the trip and avoids an unexplained free starting tank.
- The displayed route remains the provider's start-to-finish route. Station detours are estimates and are reported separately; exact detour routing would violate the one-call target.

If no origin-area priced station can be matched, return `422` with a specific data-coverage message rather than silently inventing an origin fuel price.

## 4. Implementation Phases

### Phase 1: Make the repository reproducible

- Add `requirements.txt` with the tested Django and HTTP client versions.
- Add `.env.example` containing non-secret configuration names.
- Move `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, provider URL/key, timeouts, cache duration, and route-corridor distance into environment-backed settings with development defaults where safe.
- Register `routing`, add `routing/urls.py`, and mount it below `/api/v1/`.
- Add basic structured logging for request failures and provider timing; never log the API key.
- Replace the assignment-only README with setup, import, run, test, endpoint, example request/response, assumptions, and provider-attribution documentation. Preserve the original assignment in a clearly labeled section or separate file.

Acceptance check: a fresh environment can install dependencies and `python manage.py check` succeeds without a real provider call.

### Phase 2: Normalize and import local data

- Add `City` and `FuelStation` models and migrations.
- Store normalized city/state lookup fields, latitude, longitude, station identity, name, address, retail price as `Decimal`, and coordinate accuracy/source.
- Add indexes for normalized city/state lookup and latitude/longitude candidate filtering.
- Create an idempotent `import_route_data` management command using Python's CSV module and `Decimal`.
- Import only the 50 states plus DC; reject Canadian province rows and malformed/out-of-range prices.
- Normalize whitespace/case and map full state names to two-letter codes.
- Resolve each station through normalized city/state coordinates. Skip unmatched stations with an end-of-run summary; do not fabricate coordinates.
- Deduplicate carefully: use OPIS ID plus normalized identifying fields rather than OPIS ID alone, because 677 duplicate-ID groups contain conflicting rows. Collapse exact duplicates and retain distinct legitimate records with a documented rule.
- Make the import transactional and safe to rerun. Print counts for inserted, updated, exact duplicates, non-US, unmatched, and invalid rows.

Acceptance check: tests cover repeated imports, Canadian filtering, duplicates, invalid prices, and known coordinate matches; an actual import reports reconciled counts.

### Phase 3: Add location resolution and routing integration

- Parse and validate `start` and `finish` without accepting arbitrary provider-bound strings.
- Resolve coordinates locally and reject ambiguous city names unless a state is supplied.
- Implement an `OpenRouteServiceClient` that sends one POST to the GeoJSON directions endpoint.
- Validate the upstream payload before using it and convert meters/seconds to miles/hours.
- Cache normalized start/finish route results using Django's cache framework. Include routing profile/provider version in the cache key and use a configurable TTL.
- Preserve provider attribution in the API response or documentation as required by the provider terms.

Acceptance check: mocked tests prove one provider call per miss, zero per hit, correct coordinate ordering (`longitude, latitude`), unit conversion, timeouts, malformed responses, and quota/auth errors.

### Phase 4: Find stations along the route

- Reduce the provider geometry to a bounded number of representative segments while preserving cumulative route mileage.
- Use the route bounding box plus the configured corridor to narrow database candidates before geometry calculations.
- For each candidate, calculate nearest-route distance and projected mile marker. Keep stations inside the corridor and sort by mile marker.
- Treat stations sharing a city centroid as separate price options but discard dominated choices at effectively the same mile marker (retain the cheapest, then deterministic ID ordering).
- Track candidate coverage along the route and fail with `422` when no feasible chain of stops can keep every leg at or below 500 miles.
- Return estimated route mile marker and estimated detour distance for every selected stop.

Acceptance check: geometry tests cover east/west and north/south routes, route bends, stations just inside/outside the corridor, repeated coordinates, and stable ordering.

### Phase 5: Optimize the fuel plan

Implement the standard cheapest-reachable-station strategy over ordered candidates:

1. Add the selected origin-area station at mile 0 and a destination sentinel at total route miles.
2. From each stop, look ahead no farther than 500 route miles.
3. If a cheaper reachable station exists, buy only enough fuel to reach the first such station.
4. Otherwise, buy enough to reach the cheapest reachable next candidate, capped at the 50-gallon tank capacity.
5. Account for fuel already in the tank, gallons consumed on every leg, and the destination's zero required reserve.
6. Use `Decimal` for money and deterministic tie-breaking by price, mile marker, then station ID.

Before coding, verify this greedy method against a small dynamic-programming/brute-force oracle in tests. If route-corridor detour penalties or nonzero arrival reserve make greedy selection non-optimal, retain the oracle-style dynamic program for production instead.

Add invariant checks:

- no leg exceeds 500 miles;
- tank contents never fall below zero or exceed 50 gallons;
- gallons consumed equal route miles divided by 10, within rounding tolerance;
- itemized costs sum exactly to the serialized total;
- every recommended stop comes from imported price data.

Acceptance check: unit tests cover routes under 500 miles, exact 500-mile boundaries, multiple fills, cheaper stations ahead, expensive gaps, equal-price ties, impossible gaps, and rounding.

### Phase 6: API hardening and performance

- Keep request handling thin: validation, service invocation, and serialization should be separate modules.
- Add method/content-type handling (`405`/`415`) and consistent JSON errors with a stable `code`, `message`, and optional `fields` object.
- Add request-size limits and avoid returning provider internals.
- Measure import time, cold uncached response time, cached response time, database query count, and number of external calls.
- Set concrete local targets: station selection under 250 ms after the route response, cached complete requests under 200 ms, and no N+1 queries. Record observed results in the README rather than claiming unmeasured performance.
- Run Django's deployment checks and document which production settings must change.

Acceptance check: integration tests cover a successful long route, short route, bad input, no feasible station chain, missing key, provider timeout, and cached repeat request.

### Phase 7: Delivery and demonstration

- Add a Postman collection (or equivalent curl examples) with success, validation failure, and provider-failure cases.
- Ensure `data/us_cities.csv`, README changes, migrations, and dependency/config files are tracked by Git.
- Run the full test suite, `manage.py check`, and `manage.py check --deploy` with production-like settings; document any expected local warnings.
- Perform one real-provider smoke test without committing credentials or cached secret-bearing data.
- Prepare a five-minute Loom flow: setup summary, data import, one successful cross-country request, response/map geometry and fuel stops, cache/external-call behavior, test overview, and known city-centroid limitation.
- Push a clean GitHub branch/repository and verify the clone-and-run instructions from a clean directory.

## 5. Suggested Code Layout

```text
config/
  settings.py
  urls.py
routing/
  clients/openrouteservice.py
  management/commands/import_route_data.py
  migrations/
  services/location.py
  services/route.py
  services/stations.py
  services/fuel_plan.py
  tests/
    fixtures/
    test_api.py
    test_import.py
    test_location.py
    test_provider.py
    test_stations.py
    test_fuel_plan.py
  models.py
  urls.py
  views.py
.env.example
requirements.txt
```

Use plain Django `JsonResponse` unless API requirements grow enough to justify Django REST Framework. The current endpoint is small enough that adding a framework is not necessary.

## 6. Key Risks and Mitigations

- **Approximate station positions:** city centroids can place a station miles from its highway exit. Label accuracy honestly, use a corridor, and report estimated detour distance. Exact station geocoding is a future preprocessing enhancement, not a per-request API call.
- **Sparse or unmatched coverage:** fail explicitly when a valid 500-mile chain cannot be built and include import coverage statistics in documentation.
- **Duplicate OPIS IDs:** do not deduplicate solely by ID; preserve distinct records and document reconciliation counts.
- **Provider limits/outages:** cache successful routes, enforce timeouts, mock provider calls in tests, and return retryable service errors.
- **Cost ambiguity:** document that the initial origin-area fill is included, detours are estimated rather than routed, and the supplied snapshot prices may not be current.
- **Optimization correctness:** compare greedy results with an exhaustive oracle on many small randomized cases before relying on the faster method.

## 7. Execution Order

Complete phases in order. Phases 1-3 establish a testable route endpoint; phases 4-5 deliver the assignment's core value; phase 6 makes the result dependable; phase 7 packages the evidence. Do not record the Loom or publish the repository until the real-provider smoke test and clean-clone verification pass.
