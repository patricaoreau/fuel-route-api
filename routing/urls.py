from django.urls import path

from routing.views import fuel_plan


urlpatterns = [
    path('routes/fuel-plan/', fuel_plan, name='fuel-plan'),
]
