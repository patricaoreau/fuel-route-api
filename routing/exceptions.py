class FuelRouteError(Exception):
    code = 'fuel_route_error'
    status = 500

    def __init__(self, message, *, fields=None):
        super().__init__(message)
        self.message = message
        self.fields = fields or {}


class RequestValidationError(FuelRouteError):
    code = 'validation_error'
    status = 400


class DataCoverageError(FuelRouteError):
    code = 'insufficient_fuel_data'
    status = 422


class ProviderConfigurationError(FuelRouteError):
    code = 'routing_provider_not_configured'
    status = 503


class ProviderUnavailableError(FuelRouteError):
    code = 'routing_provider_unavailable'
    status = 503


class ProviderResponseError(FuelRouteError):
    code = 'routing_provider_error'
    status = 502
