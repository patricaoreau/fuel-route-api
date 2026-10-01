from django.urls import path

from routing.views import fuel_plan, location_suggestions


urlpatterns = [
    path('locations/', location_suggestions, name='location-suggestions'),
    path('routes/fuel-plan/', fuel_plan, name='fuel-plan'),
]
