import os
import uuid

from django.conf import settings
from django.db import models
from core.models import Residence
from core.validators import validate_photo


def incident_photo_upload(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"incidents/{instance.incident.residence_id}/{uuid.uuid4().hex}{ext}"


class IncidentCategory(models.Model):
    """Catégories administrables depuis l'admin Django (communes à toutes les résidences)."""
    name = models.CharField("Nom", max_length=60, unique=True)
    icon = models.CharField("Icône (nom Lucide, ex. wrench)", max_length=32, default="wrench")
    order = models.PositiveSmallIntegerField("Ordre d'affichage", default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Catégorie d'incident"
        verbose_name_plural = "Catégories d'incident"

    def __str__(self):
        return self.name


class Incident(models.Model):
    STATUSES = [
        ("signale", "Signalé"),
        ("pris_en_compte", "Pris en compte"),
        ("en_cours", "En cours"),
        ("resolu", "Résolu"),
    ]
    residence = models.ForeignKey(Residence, on_delete=models.CASCADE, related_name="incidents")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="incidents")
    category = models.ForeignKey(IncidentCategory, on_delete=models.PROTECT, verbose_name="Catégorie", related_name="incidents")
    title = models.CharField("Titre", max_length=120)
    description = models.TextField("Description", blank=True)
    location = models.CharField("Localisation", max_length=120, blank=True)
    status = models.CharField("Statut", max_length=20, choices=STATUSES, default="signale")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def is_open(self):
        return self.status != "resolu"

    STATUS_BADGES = {
        "signale": "bg-red-100 text-red-800",
        "pris_en_compte": "bg-blue-100 text-blue-800",
        "en_cours": "bg-amber-100 text-amber-800",
        "resolu": "bg-green-100 text-green-800",
    }

    @property
    def badge_class(self):
        return self.STATUS_BADGES[self.status]

    @property
    def icon(self):
        return self.category.icon


class IncidentPhoto(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to=incident_photo_upload, validators=[validate_photo])


class IncidentUpdate(models.Model):
    """Journal unique : changements de statut ET commentaires."""
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="updates")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    old_status = models.CharField(max_length=20, choices=Incident.STATUSES, blank=True)
    new_status = models.CharField(max_length=20, choices=Incident.STATUSES, blank=True)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class IncidentFollower(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="followers")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("incident", "user")
