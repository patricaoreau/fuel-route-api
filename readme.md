# Fuel Route API

A Django API that returns a US driving route, cost-effective fuel stops along it, and an estimated trip fuel cost. It uses the supplied station-price snapshot, assumes a 500-mile vehicle range and 10 MPG, and makes at most one openrouteservice request for each uncached origin/destination pair.

## What it returns

`POST /api/v1/routes/fuel-plan/` accepts US cities in `City, ST` or `City, State` format and returns:

- openrouteservice route geometry as a GeoJSON `LineString`;
- route distance and estimated duration;
- a feasible fuel-stop sequence with per-stop gallons and cost;
- total gallons and total fuel cost;
- the assumptions and attribution needed to interpret the result.

Station coordinates are supplied as city centroids because the price file has addresses but no coordinates. Detour distances are estimates; the route is not recalculated through fuel stops, preserving the one-call provider target.

## Setup

Requirements: Python 3.12+, an [openrouteservice API key](https://openrouteservice.org/dev/#/signup), and the two CSV files already under `data/`.

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:DJANGO_SECRET_KEY = "local-development-key"
$env:OPENROUTESERVICE_API_KEY = "your-key"
python manage.py migrate
python manage.py import_route_data
python manage.py collectstatic --noinput
python manage.py runserver
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export DJANGO_SECRET_KEY="local-development-key"
export OPENROUTESERVICE_API_KEY="your-key"
python manage.py migrate
python manage.py import_route_data
python manage.py collectstatic --noinput
python manage.py runserver
```

`.env.example` lists all supported settings. Django loads `.env` and an optional `.env.local` from the project root. Existing shell or deployment variables take priority, followed by `.env.local`, then `.env`. Restart the development server after changing either file.

The import is transactional and idempotent. It prints counts for created/updated records, duplicate reconciliation, non-US rows, unmatched locations, and invalid data. On the supplied files it imports 29,639 normalized US cities and 6,841 distinct priced station records.

## City predictions

The page inputs use the local city dataset through `GET /api/v1/locations/?q=`. Predictions begin after two city characters, support optional state filtering, return at most eight matches, and do not consume routing-provider quota.

```bash
curl "http://127.0.0.1:8000/api/v1/locations/?q=Fort%20S%2C%20AR"
```

```json
{
  "suggestions": [
    {
      "label": "Fort Smith, AR",
      "city": "Fort Smith",
      "state": "AR",
      "state_name": "Arkansas",
      "coordinates": [-94.411035, 35.365272]
    }
  ]
}
```

On page load, the browser makes a best-effort request directly to [ipwho.is](https://ipwhois.io/documentation), with [IPinfo](https://ipinfo.io/developers) as a fallback, so the lookup uses the frontend user's public IP instead of the Django server's IP. The returned US city and state must exactly match a prediction from the local city dataset before Start is populated. Lookup failures never block manual entry, and text already entered by the user is never replaced. These third-party providers receive the user's public IP as part of the network request. IP location is approximate and may identify an ISP location instead of the user's precise city.

## Request example

```bash
curl -X POST http://127.0.0.1:8000/api/v1/routes/fuel-plan/ \
  -H "Content-Type: application/json" \
  -d '{"start":"Fort Smith, AR","finish":"Mount Jackson, VA"}'
```

The response shape is:

```json
{
  "start": {"label": "Fort Smith, AR", "coordinates": [-94.411035, 35.365272]},
  "finish": {"label": "Mount Jackson, VA", "coordinates": [-78.676655, 38.768819]},
  "route": {
    "distance_miles": 1035.2,
    "duration_hours": 15.4,
    "geometry": {"type": "LineString", "coordinates": []}
  },
  "vehicle": {"mpg": 10, "max_range_miles": 500, "tank_capacity_gallons": 50},
  "fuel_stops": [
    {
      "station_id": "28",
      "name": "LITTLEFIELD EXPRESS #2",
      "address": "I-540, EXIT 12 & US-71",
      "city": "Fort Smith",
      "state": "AR",
      "coordinates": [-94.411035, 35.365272],
      "location_accuracy": "city_centroid",
      "price_per_gallon": 3.399,
      "route_mile": 0.0,
      "estimated_detour_miles": 0.0,
      "gallons": 50.0,
      "cost": 169.95
    }
  ],
  "total_gallons": 103.52,
  "total_fuel_cost": 335.41,
  "currency": "USD",
  "attribution": "Routing data from openrouteservice and OpenStreetMap contributors.",
  "assumptions": []
}
```

Values above illustrate the schema; live route geometry, duration, selected stops, and costs depend on the provider response and supplied data.

## Error responses

Errors use a stable envelope:

```json
{
  "error": {
    "code": "validation_error",
    "message": "One or more locations could not be resolved.",
    "fields": {"start": "No matching city was found in the local US cities dataset."}
  }
}
```

Expected status codes are `400` for invalid locations/JSON, `405` for the wrong method, `413` for oversized requests, `415` for the wrong content type, `422` when station coverage cannot satisfy the 500-mile range, `502` for malformed provider responses, and `503` for missing configuration, provider quota, timeout, or availability failures.

## Tests and checks

```bash
python manage.py test
python manage.py check
python manage.py check --deploy
```

Tests cover location resolution, imports and duplicate reconciliation, provider payloads/errors, route caching, geometry projection, fuel optimization against a dynamic-programming oracle, API errors, and a complete planner result. Provider tests use an HTTP mock and do not consume quota.

`check --deploy` intentionally warns under local development defaults. Production must set a strong `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=false`, the `DJANGO_SECURE_*` and secure-cookie settings after HTTPS is configured, explicit allowed hosts, and a shared production cache instead of the local-memory cache.

## Performance

Run the repeatable local benchmark after importing the supplied data and configuring the routing API key:

```bash
python manage.py benchmark_fuel_route --iterations 20
```

On October 1, 2026, the Windows development environment was measured with 6,841 imported stations and the Fort Smith, AR to Mount Jackson, VA route:

| Operation | Median | p95 | Database queries | Target |
| --- | ---: | ---: | ---: | --- |
| Station selection | 26.80 ms | 32.79 ms | 1 | p95 under 250 ms |
| Complete cached API view | 42.09 ms | 55.38 ms | 3 | p95 under 200 ms |

Both latency targets passed. Query counts stayed constant across all 20 iterations, so no N+1 query behavior was detected. The separate route warm-up, which included the external provider request, took 4,298.86 ms and was intentionally excluded from cached-request timing.

## Design

- `routing/clients/openrouteservice.py`: isolated one-call routing-provider adapter.
- `routing/services/location.py`: local US city parsing and geocoding.
- `routing/services/stations.py`: bounding-box filtering and route projection.
- `routing/services/fuel_plan.py`: deterministic fuel optimizer and accounting invariants.
- `routing/services/planner.py`: response orchestration and serialization.
- `routing/management/commands/import_route_data.py`: transactional CSV normalization.

Successful route results are cached by normalized origin, destination, provider, and profile. A cache hit makes no provider request. Station selection still uses current imported prices.

## Fuel model assumptions

- The vehicle gets exactly 10 MPG and has a 50-gallon tank, giving a 500-mile maximum range.
- The optimizer includes an initial fill at a priced station projected within the first 25 route miles and targets a zero-gallon arrival reserve.
- It buys only enough to reach the first cheaper reachable station; when none exists, it fills enough to use the cheapest reachable alternative.
- Money uses `Decimal`; per-stop costs are rounded to cents and the response total is the sum of those itemized costs.
- Supplied prices are treated as a USD-per-gallon snapshot, not live prices.
- Station city-centroid detours are estimates and are excluded from route mileage and fuel cost.

## Assignment

The original exercise asks for a latest-stable-Django API that accepts US start/finish locations, returns a route with cost-effective fuel stops for a 500-mile-range/10-MPG vehicle, minimizes map-provider calls, reports total fuel cost, and is demonstrated in a five-minute Postman/Loom walkthrough. The implementation plan and decisions are preserved in `PLAN.MD`; `DEMO.md` provides the delivery walkthrough.
