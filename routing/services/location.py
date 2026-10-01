import re

from routing.exceptions import RequestValidationError
from routing.models import City


STATE_NAMES = {
    'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas',
    'CA': 'California', 'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware',
    'DC': 'District of Columbia', 'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii',
    'ID': 'Idaho', 'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa',
    'KS': 'Kansas', 'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine',
    'MD': 'Maryland', 'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota',
    'MS': 'Mississippi', 'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska',
    'NV': 'Nevada', 'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico',
    'NY': 'New York', 'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio',
    'OK': 'Oklahoma', 'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island',
    'SC': 'South Carolina', 'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas',
    'UT': 'Utah', 'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington',
    'WV': 'West Virginia', 'WI': 'Wisconsin', 'WY': 'Wyoming',
}
STATE_CODES_BY_NAME = {name.casefold(): code for code, name in STATE_NAMES.items()}


def normalize_name(value):
    return ' '.join(value.strip().casefold().split())


def normalize_state(value):
    state = ' '.join(value.strip().split())
    upper = state.upper()
    if upper in STATE_NAMES:
        return upper
    return STATE_CODES_BY_NAME.get(state.casefold())


def parse_location(value, field_name):
    if not isinstance(value, str) or not value.strip():
        raise RequestValidationError(
            'Both start and finish are required.',
            fields={field_name: 'Enter a location as City, ST.'},
        )
    parts = re.split(r'\s*,\s*', value.strip())
    if len(parts) != 2 or not all(parts):
        raise RequestValidationError(
            'Location must include a city and US state.',
            fields={field_name: 'Use the format City, ST or City, State.'},
        )
    state_code = normalize_state(parts[1])
    if state_code is None:
        raise RequestValidationError(
            'Location must be in the United States.',
            fields={field_name: 'Use a valid US state name or two-letter code.'},
        )
    return normalize_name(parts[0]), state_code


def resolve_location(value, field_name):
    normalized_city, state_code = parse_location(value, field_name)
    try:
        city = City.objects.get(
            normalized_name=normalized_city,
            state_code=state_code,
        )
    except City.DoesNotExist as exc:
        raise RequestValidationError(
            'One or more locations could not be resolved.',
            fields={field_name: 'No matching city was found in the local US cities dataset.'},
        ) from exc
    return {
        'label': f'{city.name}, {city.state_code}',
        'coordinates': [city.longitude, city.latitude],
        'cache_key': f'{city.state_code}:{city.normalized_name}',
    }
