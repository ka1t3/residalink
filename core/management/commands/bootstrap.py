"""Initialise la première résidence : groupes, modules, catégories d'incidents.
Usage : python manage.py bootstrap "Résidence Les Tilleuls"
"""
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from core.models import Residence, ResidenceModule
from incidents.models import IncidentCategory

DEFAULT_CATEGORIES = [
    ("Ascenseur", "arrow-up-down", 1), ("Fuite d'eau", "droplet", 2), ("Éclairage", "lightbulb", 3),
    ("Portail / porte", "door-open", 4), ("Propreté", "spray-can", 5), ("Autre", "wrench", 6),
]


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("name", help="Nom de la résidence")

    def handle(self, *args, **options):
        Group.objects.get_or_create(name="conseil_syndical")
        Group.objects.get_or_create(name="resident")
        for name, icon, order in DEFAULT_CATEGORIES:
            IncidentCategory.objects.get_or_create(name=name, defaults={"icon": icon, "order": order})
        residence, created = Residence.objects.get_or_create(name=options["name"])
        for module, _ in ResidenceModule.MODULES:
            ResidenceModule.objects.get_or_create(residence=residence, module=module, defaults={"enabled": True})
        self.stdout.write(self.style.SUCCESS(
            f"Résidence « {residence.name} » prête. Code d'invitation : {residence.invite_code}"
        ))
