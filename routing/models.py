from django.db import models


class City(models.Model):
    name = models.CharField(max_length=120)
    normalized_name = models.CharField(max_length=120)
    state_code = models.CharField(max_length=2)
    state_name = models.CharField(max_length=80)
    latitude = models.FloatField()
    longitude = models.FloatField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('normalized_name', 'state_code'),
                name='routing_city_name_state_unique',
            )
        ]
        indexes = [
            models.Index(fields=('state_code', 'normalized_name')),
        ]
        ordering = ('state_code', 'name')

    def __str__(self):
        return f'{self.name}, {self.state_code}'


class FuelStation(models.Model):
    fingerprint = models.CharField(max_length=64, unique=True)
    opis_id = models.CharField(max_length=32)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=250)
    city = models.CharField(max_length=120)
    state_code = models.CharField(max_length=2)
    rack_id = models.CharField(max_length=32, blank=True)
    retail_price = models.DecimalField(max_digits=6, decimal_places=3)
    latitude = models.FloatField()
    longitude = models.FloatField()
    location_accuracy = models.CharField(max_length=32, default='city_centroid')

    class Meta:
        indexes = [
            models.Index(fields=('latitude', 'longitude')),
            models.Index(fields=('state_code', 'city')),
            models.Index(fields=('opis_id',)),
        ]
        ordering = ('state_code', 'city', 'name', 'id')

    def __str__(self):
        return f'{self.name} ({self.city}, {self.state_code})'
