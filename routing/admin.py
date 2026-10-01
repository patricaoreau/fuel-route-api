from django.contrib import admin

from routing.models import City, FuelStation


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ('name', 'state_code', 'latitude', 'longitude')
    list_filter = ('state_code',)
    search_fields = ('name', 'normalized_name')


@admin.register(FuelStation)
class FuelStationAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'state_code', 'retail_price', 'opis_id')
    list_filter = ('state_code', 'location_accuracy')
    search_fields = ('name', 'city', 'address', 'opis_id')
