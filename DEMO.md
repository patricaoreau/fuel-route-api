# Five-Minute Demo Guide

## Before recording

```powershell
$env:OPENROUTESERVICE_API_KEY = "your-key"
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py import_route_data
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py runserver
```

Import `postman/Fuel Route API.postman_collection.json` into Postman. Keep the API key in the server environment, never in Postman or the recording.

## Recording outline

1. **0:00-0:30:** State the input, output, fixed 500-mile/10-MPG assumptions, and one-call routing target.
2. **0:30-1:30:** Send the valid fuel-plan request. Show route distance/duration, GeoJSON, fuel stops, gallons, itemized costs, total cost, and assumptions.
3. **1:30-2:00:** Paste the returned `route.geometry` into a GeoJSON viewer or show it in Postman's visualization tooling.
4. **2:00-2:40:** Repeat the request and explain that the normalized route key is cached, so it makes zero additional provider calls.
5. **2:40-3:20:** Send the invalid-location request and show the stable `400` error. Mention `422` for an impossible station-coverage gap.
6. **3:20-4:20:** Show the provider client, station projection service, fuel optimizer, and transactional import command.
7. **4:20-5:00:** Show the passing tests and summarize limitations: city-centroid station locations, snapshot prices, and estimated detours not included in route mileage.

Do one unrecorded real-provider request first so credentials, provider availability, and the chosen demo city pair are verified before the five-minute take.
