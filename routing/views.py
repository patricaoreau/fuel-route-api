import json
import logging

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from routing.exceptions import FuelRouteError, RequestValidationError
from routing.services.location import suggest_locations
from routing.services.planner import build_fuel_route_plan


logger = logging.getLogger(__name__)
MAX_REQUEST_BYTES = 10_000


def demo(request):
    return render(request, 'routing/index.html')


def location_suggestions(request):
    if request.method != 'GET':
        response = JsonResponse(
            {'error': {'code': 'method_not_allowed', 'message': 'Use GET for this endpoint.'}},
            status=405,
        )
        response['Allow'] = 'GET'
        return response

    query = request.GET.get('q', '')
    if len(query) > 120:
        return _error_response(RequestValidationError(
            'Location query is too long.',
            fields={'q': 'Use no more than 120 characters.'},
        ))
    return JsonResponse({'suggestions': suggest_locations(query)})


def _error_response(error):
    payload = {
        'error': {
            'code': error.code,
            'message': error.message,
        }
    }
    if error.fields:
        payload['error']['fields'] = error.fields
    return JsonResponse(payload, status=error.status)


@csrf_exempt
def fuel_plan(request):
    if request.method != 'POST':
        response = JsonResponse(
            {'error': {'code': 'method_not_allowed', 'message': 'Use POST for this endpoint.'}},
            status=405,
        )
        response['Allow'] = 'POST'
        return response
    if not request.content_type or request.content_type.split(';', 1)[0].strip() != 'application/json':
        return JsonResponse(
            {'error': {'code': 'unsupported_media_type', 'message': 'Content-Type must be application/json.'}},
            status=415,
        )
    if len(request.body) > MAX_REQUEST_BYTES:
        return JsonResponse(
            {'error': {'code': 'request_too_large', 'message': 'Request body is too large.'}},
            status=413,
        )

    try:
        payload = json.loads(request.body)
        if not isinstance(payload, dict):
            raise ValueError
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return _error_response(RequestValidationError('Request body must be a JSON object.'))

    try:
        result = build_fuel_route_plan(payload.get('start'), payload.get('finish'))
    except FuelRouteError as exc:
        logger.warning('fuel_plan_failed code=%s message=%s', exc.code, exc.message)
        return _error_response(exc)
    return JsonResponse(result)
